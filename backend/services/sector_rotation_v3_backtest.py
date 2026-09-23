"""Point-in-time research validation for the Sector Rotation V3 model.

This module deliberately has no database, API, cache, or UI dependencies.  The
caller supplies already-built daily rank snapshots together with explicitly
dated forward returns.  That boundary keeps the research path separate from
the production V1/V2 sector-rotation flows and makes look-ahead checks
auditable.

Return values are expected as decimal returns (``0.02`` means two percent).
Transaction cost and slippage inputs are one-way basis-point assumptions.  A
long-short spread deducts four one-way executions: enter and exit both legs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math
from statistics import fmean
from typing import Mapping, Sequence


@dataclass(frozen=True)
class ForwardReturn:
    """A dated forward return for one configured trading horizon."""

    horizon: int
    start_date: date
    end_date: date
    value: float


@dataclass(frozen=True)
class SectorRankSnapshot:
    """One sector's score, phase, and future outcomes at a signal date."""

    as_of_date: date
    sector: str
    score: float
    phase: str | None
    forward_returns: tuple[ForwardReturn, ...]


@dataclass(frozen=True)
class BacktestConfig:
    """Research settings; costs are one-way basis-point assumptions."""

    horizons: tuple[int, ...] = (5, 20, 60)
    top_n: int = 3
    bottom_n: int = 3
    leading_phases: tuple[str, ...] = ("Leading",)
    lagging_phases: tuple[str, ...] = ("Lagging",)
    transaction_cost_bps: float = 0.0
    slippage_bps: float = 0.0
    min_ic_cross_section: int = 3


@dataclass(frozen=True)
class CostAssumptions:
    transaction_cost_bps: float
    slippage_bps: float
    one_way_total_bps: float
    long_short_round_trip_drag: float
    application: str = "four one-way executions per long-short spread"


@dataclass(frozen=True)
class HorizonMetrics:
    horizon: int
    evaluated_dates: int
    sector_observations: int
    ic_observations: int
    mean_spearman_rank_ic: float | None
    top_bottom_observations: int
    mean_top_bottom_gross_spread: float | None
    mean_top_bottom_net_spread: float | None
    leading_lagging_observations: int
    mean_leading_lagging_gross_spread: float | None
    mean_leading_lagging_net_spread: float | None


@dataclass(frozen=True)
class RankDynamicsMetrics:
    consecutive_date_comparisons: int
    mean_rank_stability: float | None
    turnover_comparisons: int
    mean_top_turnover: float | None
    mean_bottom_turnover: float | None
    mean_selection_turnover: float | None


@dataclass(frozen=True)
class BacktestMetadata:
    first_as_of_date: date
    last_as_of_date: date
    as_of_date_count: int
    snapshot_count: int
    score_direction: str
    return_unit: str
    forward_window_rule: str
    cost_assumptions: CostAssumptions


@dataclass(frozen=True)
class BacktestResult:
    config: BacktestConfig
    metadata: BacktestMetadata
    horizons: tuple[HorizonMetrics, ...]
    rank_dynamics: RankDynamicsMetrics


def _finite_number(value: object, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a finite number")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a finite number") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{field_name} must be a finite number")
    return parsed


def _normalized_sector(value: object) -> str:
    sector = str(value or "").strip()
    if not sector:
        raise ValueError("sector must be non-empty")
    return sector.casefold()


def _validate_config(config: BacktestConfig) -> None:
    if not config.horizons:
        raise ValueError("at least one horizon is required")
    if any(not isinstance(horizon, int) or isinstance(horizon, bool) or horizon <= 0 for horizon in config.horizons):
        raise ValueError("horizons must contain positive integers")
    if len(set(config.horizons)) != len(config.horizons):
        raise ValueError("horizons must be unique")
    if config.top_n <= 0 or config.bottom_n <= 0:
        raise ValueError("top_n and bottom_n must be positive")
    if config.min_ic_cross_section < 2:
        raise ValueError("min_ic_cross_section must be at least 2")
    if not config.leading_phases or not config.lagging_phases:
        raise ValueError("leading_phases and lagging_phases must be non-empty")
    leading = {phase.strip().casefold() for phase in config.leading_phases if phase.strip()}
    lagging = {phase.strip().casefold() for phase in config.lagging_phases if phase.strip()}
    if not leading or not lagging:
        raise ValueError("phase labels must be non-empty")
    if leading & lagging:
        raise ValueError("leading and lagging phase labels must not overlap")
    for field_name, value in (
        ("transaction_cost_bps", config.transaction_cost_bps),
        ("slippage_bps", config.slippage_bps),
    ):
        parsed = _finite_number(value, field_name)
        if parsed < 0:
            raise ValueError(f"{field_name} must be non-negative")


def _validate_and_group(
    snapshots: Sequence[SectorRankSnapshot],
) -> dict[date, list[SectorRankSnapshot]]:
    if not snapshots:
        raise ValueError("at least one sector rank snapshot is required")

    grouped: dict[date, list[SectorRankSnapshot]] = {}
    seen: set[tuple[date, str]] = set()
    windows: dict[tuple[date, int], tuple[date, date]] = {}

    for snapshot in snapshots:
        if not isinstance(snapshot.as_of_date, date):
            raise ValueError("as_of_date must be a date")
        sector_key = _normalized_sector(snapshot.sector)
        key = (snapshot.as_of_date, sector_key)
        if key in seen:
            raise ValueError(
                f"duplicate sector snapshot for {snapshot.as_of_date.isoformat()} / {snapshot.sector.strip()}"
            )
        seen.add(key)
        _finite_number(snapshot.score, "score")

        horizon_seen: set[int] = set()
        for outcome in snapshot.forward_returns:
            if not isinstance(outcome.horizon, int) or isinstance(outcome.horizon, bool) or outcome.horizon <= 0:
                raise ValueError("forward-return horizon must be a positive integer")
            if outcome.horizon in horizon_seen:
                raise ValueError(
                    f"duplicate forward-return horizon {outcome.horizon} for {snapshot.sector.strip()}"
                )
            horizon_seen.add(outcome.horizon)
            if not isinstance(outcome.start_date, date) or not isinstance(outcome.end_date, date):
                raise ValueError("forward-return boundaries must be dates")
            if outcome.start_date < snapshot.as_of_date:
                raise ValueError("forward-return start_date cannot precede as_of_date")
            if outcome.end_date <= snapshot.as_of_date or outcome.end_date <= outcome.start_date:
                raise ValueError("forward-return end_date must be after both as_of_date and start_date")
            _finite_number(outcome.value, "forward return")

            window_key = (snapshot.as_of_date, outcome.horizon)
            window = (outcome.start_date, outcome.end_date)
            previous_window = windows.setdefault(window_key, window)
            if previous_window != window:
                raise ValueError(
                    "forward-return windows must match across sectors for the same as_of_date and horizon"
                )

        grouped.setdefault(snapshot.as_of_date, []).append(snapshot)

    return grouped


def _average_ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(order):
        end = cursor + 1
        while end < len(order) and values[order[end]] == values[order[cursor]]:
            end += 1
        average_rank = ((cursor + 1) + end) / 2.0
        for ordered_index in order[cursor:end]:
            ranks[ordered_index] = average_rank
        cursor = end
    return ranks


def _pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = fmean(left)
    right_mean = fmean(right)
    left_delta = [value - left_mean for value in left]
    right_delta = [value - right_mean for value in right]
    denominator = math.sqrt(
        sum(value * value for value in left_delta)
        * sum(value * value for value in right_delta)
    )
    if denominator == 0.0:
        return None
    return sum(a * b for a, b in zip(left_delta, right_delta)) / denominator


def _spearman(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    return _pearson(_average_ranks(left), _average_ranks(right))


def _mean_or_none(values: Sequence[float]) -> float | None:
    return fmean(values) if values else None


def _return_for(snapshot: SectorRankSnapshot, horizon: int) -> float | None:
    for outcome in snapshot.forward_returns:
        if outcome.horizon == horizon:
            return float(outcome.value)
    return None


def _ranked(rows: Sequence[SectorRankSnapshot]) -> list[SectorRankSnapshot]:
    return sorted(
        rows,
        key=lambda row: (-float(row.score), _normalized_sector(row.sector)),
    )


def _replacement_fraction(
    previous: Sequence[SectorRankSnapshot], current: Sequence[SectorRankSnapshot]
) -> float:
    previous_keys = {_normalized_sector(row.sector) for row in previous}
    current_keys = {_normalized_sector(row.sector) for row in current}
    denominator = max(len(previous_keys), len(current_keys))
    if denominator == 0:
        return 0.0
    return 1.0 - (len(previous_keys & current_keys) / denominator)


def _rank_dynamics(
    grouped: Mapping[date, Sequence[SectorRankSnapshot]], config: BacktestConfig
) -> RankDynamicsMetrics:
    ordered_dates = sorted(grouped)
    stability_values: list[float] = []
    top_turnovers: list[float] = []
    bottom_turnovers: list[float] = []

    for previous_date, current_date in zip(ordered_dates, ordered_dates[1:]):
        previous = {_normalized_sector(row.sector): row for row in grouped[previous_date]}
        current = {_normalized_sector(row.sector): row for row in grouped[current_date]}
        common = sorted(previous.keys() & current.keys())
        if len(common) >= 2:
            stability = _spearman(
                [float(previous[sector].score) for sector in common],
                [float(current[sector].score) for sector in common],
            )
            if stability is not None:
                stability_values.append(stability)

        previous_ranked = _ranked(grouped[previous_date])
        current_ranked = _ranked(grouped[current_date])
        if (
            len(previous_ranked) >= config.top_n + config.bottom_n
            and len(current_ranked) >= config.top_n + config.bottom_n
        ):
            top_turnovers.append(
                _replacement_fraction(
                    previous_ranked[: config.top_n], current_ranked[: config.top_n]
                )
            )
            bottom_turnovers.append(
                _replacement_fraction(
                    previous_ranked[-config.bottom_n :], current_ranked[-config.bottom_n :]
                )
            )

    selection_turnovers = [
        (top + bottom) / 2.0 for top, bottom in zip(top_turnovers, bottom_turnovers)
    ]
    return RankDynamicsMetrics(
        consecutive_date_comparisons=len(stability_values),
        mean_rank_stability=_mean_or_none(stability_values),
        turnover_comparisons=len(selection_turnovers),
        mean_top_turnover=_mean_or_none(top_turnovers),
        mean_bottom_turnover=_mean_or_none(bottom_turnovers),
        mean_selection_turnover=_mean_or_none(selection_turnovers),
    )


def _horizon_metrics(
    grouped: Mapping[date, Sequence[SectorRankSnapshot]],
    config: BacktestConfig,
    horizon: int,
    long_short_cost_drag: float,
) -> HorizonMetrics:
    daily_ics: list[float] = []
    top_bottom: list[float] = []
    leading_lagging: list[float] = []
    sector_observations = 0
    evaluated_dates = 0
    leading_labels = {phase.strip().casefold() for phase in config.leading_phases}
    lagging_labels = {phase.strip().casefold() for phase in config.lagging_phases}

    for as_of_date in sorted(grouped):
        eligible = [
            row for row in grouped[as_of_date] if _return_for(row, horizon) is not None
        ]
        if not eligible:
            continue
        evaluated_dates += 1
        sector_observations += len(eligible)

        if len(eligible) >= config.min_ic_cross_section:
            ic = _spearman(
                [float(row.score) for row in eligible],
                [float(_return_for(row, horizon)) for row in eligible],
            )
            if ic is not None:
                daily_ics.append(ic)

        ranked = _ranked(eligible)
        if len(ranked) >= config.top_n + config.bottom_n:
            top = ranked[: config.top_n]
            bottom = ranked[-config.bottom_n :]
            top_bottom.append(
                fmean(float(_return_for(row, horizon)) for row in top)
                - fmean(float(_return_for(row, horizon)) for row in bottom)
            )

        leading = [
            row
            for row in eligible
            if str(row.phase or "").strip().casefold() in leading_labels
        ]
        lagging = [
            row
            for row in eligible
            if str(row.phase or "").strip().casefold() in lagging_labels
        ]
        if leading and lagging:
            leading_lagging.append(
                fmean(float(_return_for(row, horizon)) for row in leading)
                - fmean(float(_return_for(row, horizon)) for row in lagging)
            )

    return HorizonMetrics(
        horizon=horizon,
        evaluated_dates=evaluated_dates,
        sector_observations=sector_observations,
        ic_observations=len(daily_ics),
        mean_spearman_rank_ic=_mean_or_none(daily_ics),
        top_bottom_observations=len(top_bottom),
        mean_top_bottom_gross_spread=_mean_or_none(top_bottom),
        mean_top_bottom_net_spread=(
            _mean_or_none(top_bottom) - long_short_cost_drag if top_bottom else None
        ),
        leading_lagging_observations=len(leading_lagging),
        mean_leading_lagging_gross_spread=_mean_or_none(leading_lagging),
        mean_leading_lagging_net_spread=(
            _mean_or_none(leading_lagging) - long_short_cost_drag
            if leading_lagging
            else None
        ),
    )


def evaluate_sector_rotation_v3(
    snapshots: Sequence[SectorRankSnapshot],
    config: BacktestConfig | None = None,
) -> BacktestResult:
    """Validate and evaluate supplied point-in-time Sector Rotation V3 snapshots."""

    selected_config = config or BacktestConfig()
    _validate_config(selected_config)
    grouped = _validate_and_group(snapshots)

    one_way_bps = float(selected_config.transaction_cost_bps) + float(
        selected_config.slippage_bps
    )
    long_short_cost_drag = 4.0 * one_way_bps / 10_000.0
    costs = CostAssumptions(
        transaction_cost_bps=float(selected_config.transaction_cost_bps),
        slippage_bps=float(selected_config.slippage_bps),
        one_way_total_bps=one_way_bps,
        long_short_round_trip_drag=long_short_cost_drag,
    )
    ordered_dates = sorted(grouped)
    metadata = BacktestMetadata(
        first_as_of_date=ordered_dates[0],
        last_as_of_date=ordered_dates[-1],
        as_of_date_count=len(ordered_dates),
        snapshot_count=len(snapshots),
        score_direction="higher score ranks first",
        return_unit="decimal return; 0.02 means two percent",
        forward_window_rule=(
            "start_date is on or after as_of_date; end_date is strictly after both"
        ),
        cost_assumptions=costs,
    )
    horizons = tuple(
        _horizon_metrics(
            grouped,
            selected_config,
            horizon,
            long_short_cost_drag,
        )
        for horizon in selected_config.horizons
    )
    return BacktestResult(
        config=selected_config,
        metadata=metadata,
        horizons=horizons,
        rank_dynamics=_rank_dynamics(grouped, selected_config),
    )


def sensitivity_rank_correlation(
    baseline_scores: Mapping[str, float],
    candidate_scores: Mapping[str, float],
) -> float | None:
    """Return Spearman rank correlation for two equal sector score universes.

    ``None`` means the correlation is undefined because at least one scenario
    assigns an identical score to every sector.  Universe mismatches are
    rejected so sensitivity results cannot silently ignore missing sectors.
    """

    def normalize(scores: Mapping[str, float], label: str) -> dict[str, float]:
        normalized: dict[str, float] = {}
        for sector, score in scores.items():
            key = _normalized_sector(sector)
            if key in normalized:
                raise ValueError(f"{label} contains duplicate normalized sector {sector!r}")
            normalized[key] = _finite_number(score, f"{label} score")
        return normalized

    baseline = normalize(baseline_scores, "baseline")
    candidate = normalize(candidate_scores, "candidate")
    if baseline.keys() != candidate.keys():
        raise ValueError("baseline and candidate sector universes must match")
    if len(baseline) < 2:
        raise ValueError("at least two sectors are required for sensitivity correlation")
    sectors = sorted(baseline)
    return _spearman(
        [baseline[sector] for sector in sectors],
        [candidate[sector] for sector in sectors],
    )


__all__ = [
    "BacktestConfig",
    "BacktestMetadata",
    "BacktestResult",
    "CostAssumptions",
    "ForwardReturn",
    "HorizonMetrics",
    "RankDynamicsMetrics",
    "SectorRankSnapshot",
    "evaluate_sector_rotation_v3",
    "sensitivity_rank_correlation",
]
