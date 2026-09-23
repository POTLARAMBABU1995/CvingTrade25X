from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import sys

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.sector_rotation_v3_backtest import (
    BacktestConfig,
    ForwardReturn,
    SectorRankSnapshot,
    evaluate_sector_rotation_v3,
    sensitivity_rank_correlation,
)


def _snapshot(
    as_of: date,
    sector: str,
    score: float,
    phase: str,
    returns: dict[int, float],
) -> SectorRankSnapshot:
    return SectorRankSnapshot(
        as_of_date=as_of,
        sector=sector,
        score=score,
        phase=phase,
        forward_returns=tuple(
            ForwardReturn(
                horizon=horizon,
                start_date=as_of,
                end_date=as_of + timedelta(days=horizon + 2),
                value=value,
            )
            for horizon, value in returns.items()
        ),
    )


def test_evaluates_point_in_time_rank_metrics_and_cost_metadata() -> None:
    first = date(2026, 1, 5)
    second = date(2026, 1, 12)
    snapshots = [
        _snapshot(first, "A", 4, "Leading", {5: 0.04, 20: 0.08}),
        _snapshot(first, "B", 3, "Leading", {5: 0.03, 20: 0.06}),
        _snapshot(first, "C", 2, "Lagging", {5: 0.02, 20: 0.04}),
        _snapshot(first, "D", 1, "Lagging", {5: 0.01, 20: 0.02}),
        _snapshot(second, "A", 4, "Leading", {5: 0.04, 20: 0.08}),
        _snapshot(second, "B", 2, "Lagging", {5: 0.02, 20: 0.04}),
        _snapshot(second, "C", 3, "Leading", {5: 0.03, 20: 0.06}),
        _snapshot(second, "D", 1, "Lagging", {5: 0.01, 20: 0.02}),
    ]
    config = BacktestConfig(
        horizons=(5, 20),
        top_n=1,
        bottom_n=1,
        transaction_cost_bps=5,
        slippage_bps=2,
    )

    result = evaluate_sector_rotation_v3(snapshots, config)

    assert result.metadata.as_of_date_count == 2
    assert result.metadata.snapshot_count == 8
    assert result.metadata.cost_assumptions.one_way_total_bps == 7
    assert result.metadata.cost_assumptions.long_short_round_trip_drag == pytest.approx(
        0.0028
    )
    five_day = result.horizons[0]
    assert five_day.horizon == 5
    assert five_day.mean_spearman_rank_ic == pytest.approx(1.0)
    assert five_day.mean_top_bottom_gross_spread == pytest.approx(0.03)
    assert five_day.mean_top_bottom_net_spread == pytest.approx(0.0272)
    assert five_day.mean_leading_lagging_gross_spread == pytest.approx(0.02)
    assert five_day.mean_leading_lagging_net_spread == pytest.approx(0.0172)
    assert result.rank_dynamics.consecutive_date_comparisons == 1
    assert result.rank_dynamics.mean_rank_stability == pytest.approx(0.8)
    assert result.rank_dynamics.mean_selection_turnover == pytest.approx(0.0)


def test_selection_turnover_tracks_top_and_bottom_membership_changes() -> None:
    first = date(2026, 2, 2)
    second = date(2026, 2, 9)
    snapshots = [
        _snapshot(first, "A", 4, "Leading", {5: 0.04}),
        _snapshot(first, "B", 3, "Leading", {5: 0.03}),
        _snapshot(first, "C", 2, "Lagging", {5: 0.02}),
        _snapshot(first, "D", 1, "Lagging", {5: 0.01}),
        _snapshot(second, "A", 1, "Lagging", {5: 0.01}),
        _snapshot(second, "B", 4, "Leading", {5: 0.04}),
        _snapshot(second, "C", 2, "Lagging", {5: 0.02}),
        _snapshot(second, "D", 3, "Leading", {5: 0.03}),
    ]

    result = evaluate_sector_rotation_v3(
        snapshots, BacktestConfig(horizons=(5,), top_n=1, bottom_n=1)
    )

    assert result.rank_dynamics.turnover_comparisons == 1
    assert result.rank_dynamics.mean_top_turnover == pytest.approx(1.0)
    assert result.rank_dynamics.mean_bottom_turnover == pytest.approx(1.0)
    assert result.rank_dynamics.mean_selection_turnover == pytest.approx(1.0)


def test_rejects_duplicate_date_and_normalized_sector() -> None:
    as_of = date(2026, 3, 2)
    snapshots = [
        _snapshot(as_of, "Technology", 80, "Leading", {5: 0.04}),
        _snapshot(as_of, " technology ", 70, "Improving", {5: 0.03}),
    ]

    with pytest.raises(ValueError, match="duplicate sector snapshot"):
        evaluate_sector_rotation_v3(snapshots, BacktestConfig(horizons=(5,)))


@pytest.mark.parametrize(
    ("start_offset", "end_offset"),
    [(-1, 5), (0, 0), (2, 1)],
)
def test_rejects_non_forward_return_windows(
    start_offset: int, end_offset: int
) -> None:
    as_of = date(2026, 3, 9)
    snapshot = SectorRankSnapshot(
        as_of_date=as_of,
        sector="Banks",
        score=90,
        phase="Leading",
        forward_returns=(
            ForwardReturn(
                horizon=5,
                start_date=as_of + timedelta(days=start_offset),
                end_date=as_of + timedelta(days=end_offset),
                value=0.02,
            ),
        ),
    )

    with pytest.raises(ValueError, match="forward-return"):
        evaluate_sector_rotation_v3([snapshot], BacktestConfig(horizons=(5,)))


def test_rejects_inconsistent_cross_section_return_windows() -> None:
    as_of = date(2026, 4, 6)
    first = _snapshot(as_of, "A", 2, "Leading", {5: 0.02})
    second = SectorRankSnapshot(
        as_of_date=as_of,
        sector="B",
        score=1,
        phase="Lagging",
        forward_returns=(
            ForwardReturn(
                horizon=5,
                start_date=as_of + timedelta(days=1),
                end_date=as_of + timedelta(days=7),
                value=0.01,
            ),
        ),
    )

    with pytest.raises(ValueError, match="windows must match"):
        evaluate_sector_rotation_v3(
            [first, second], BacktestConfig(horizons=(5,), min_ic_cross_section=2)
        )


def test_sensitivity_rank_correlation_and_universe_validation() -> None:
    baseline = {"A": 3.0, "B": 2.0, "C": 1.0}

    assert sensitivity_rank_correlation(baseline, baseline) == pytest.approx(1.0)
    assert sensitivity_rank_correlation(
        baseline, {"A": 1.0, "B": 2.0, "C": 3.0}
    ) == pytest.approx(-1.0)
    assert sensitivity_rank_correlation(
        baseline, {"A": 5.0, "B": 5.0, "C": 5.0}
    ) is None
    with pytest.raises(ValueError, match="universes must match"):
        sensitivity_rank_correlation(baseline, {"A": 3.0, "B": 2.0})
