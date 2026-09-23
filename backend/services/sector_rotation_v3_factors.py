from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence


MODEL_VERSION = "SECTOR_ROTATION_V3"


@dataclass(frozen=True)
class V3Config:
    """Central, immutable defaults for the deterministic V3 scoring engine."""

    momentum_weights: Mapping[int, float] = field(
        default_factory=lambda: {21: 0.15, 63: 0.30, 126: 0.30, 252: 0.25}
    )
    trend_weights: Mapping[str, float] = field(
        default_factory=lambda: {
            "aboveSma20": 0.20,
            "aboveSma50": 0.15,
            "aboveSma100": 0.15,
            "aboveSma200": 0.15,
            "bullishStructure": 0.15,
            "positiveSma50Slope": 0.10,
            "positiveSma100Slope": 0.05,
            "positiveReturn252": 0.05,
        }
    )
    breadth_weights: Mapping[str, float] = field(
        default_factory=lambda: {
            "rsi55": 0.15,
            "rsi50": 0.10,
            "sma20": 0.20,
            "sma50": 0.20,
            "sma100": 0.15,
            "sma200": 0.10,
            "bullishStack": 0.10,
        }
    )
    breadth_blend_weights: Mapping[str, float] = field(
        default_factory=lambda: {"equalWeight": 0.60, "ffmcWeight": 0.25, "marketCapWeight": 0.15}
    )
    money_flow_weights: Mapping[str, float] = field(
        default_factory=lambda: {
            "volumeRatio": 0.25,
            "deliveryParticipation": 0.20,
            "obvSlope": 0.20,
            "accumulation": 0.15,
            "upDownVolume": 0.10,
            "breadthVolume": 0.10,
        }
    )
    risk_weights: Mapping[str, float] = field(
        default_factory=lambda: {
            "volatility": 0.30,
            "downsideVolatility": 0.20,
            "drawdown": 0.25,
            "betaInstability": 0.10,
            "concentration": 0.10,
            "liquidity": 0.05,
        }
    )
    data_quality_weights: Mapping[str, float] = field(
        default_factory=lambda: {
            "freshness": 0.30,
            "indicatorCoverage": 0.30,
            "historyCoverage": 0.20,
            "nullOutlierQuality": 0.10,
            "liquidityCoverage": 0.10,
        }
    )
    factor_weights: Mapping[str, float] = field(
        default_factory=lambda: {
            "momentum": 0.30,
            "breadth": 0.25,
            "trend": 0.20,
            "moneyFlow": 0.10,
            "risk": 0.10,
            "dataQuality": 0.05,
        }
    )
    minimum_momentum_horizons: int = 3
    minimum_trend_weight: float = 0.70
    minimum_breadth_weight: float = 0.70
    minimum_money_flow_weight: float = 0.60
    minimum_risk_weight: float = 0.70
    minimum_data_quality_weight: float = 0.50
    positive_acceleration_threshold: float = 5.0
    negative_acceleration_threshold: float = -5.0
    relative_strength_threshold: float = 55.0
    trend_confirmation_threshold: float = 55.0
    missing_money_flow_penalty: float = 3.0


DEFAULT_CONFIG = V3Config()


@dataclass(frozen=True)
class MomentumResult:
    score: float | None
    acceleration_raw: float | None
    acceleration_score: float | None
    direction: str
    coverage_percent: float


@dataclass(frozen=True)
class FactorResult:
    score: float | None
    coverage_percent: float
    state: str
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class FinalScoreResult:
    score: float | None
    configured_weights: Mapping[str, float]
    effective_weights: Mapping[str, float]
    redistribution_applied: bool
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class PhaseResult:
    phase: str
    confidence: str
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class ConfidenceResult:
    label: str
    score: float
    reason_codes: tuple[str, ...]


def as_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def clamp_score(value: Any) -> float | None:
    number = as_number(value)
    if number is None:
        return None
    return round(min(100.0, max(0.0, number)), 4)


def weighted_score(
    components: Mapping[Any, float | None],
    weights: Mapping[Any, float],
    *,
    minimum_available_weight: float = 0.0,
) -> tuple[float | None, float]:
    """Return a reweighted score and configured-weight coverage without zero-filling nulls."""

    configured_total = sum(max(float(weight), 0.0) for weight in weights.values())
    available: list[tuple[float, float]] = []
    for key, weight in weights.items():
        score = clamp_score(components.get(key))
        normalized_weight = max(float(weight), 0.0)
        if score is not None and normalized_weight > 0:
            available.append((score, normalized_weight))
    available_weight = sum(weight for _, weight in available)
    coverage = 100.0 * available_weight / configured_total if configured_total > 0 else 0.0
    if configured_total <= 0 or available_weight <= 0 or available_weight + 1e-12 < minimum_available_weight:
        return None, round(coverage, 4)
    score = sum(value * weight for value, weight in available) / available_weight
    return round(score, 4), round(coverage, 4)


def percentile_scores(values: Sequence[Any], *, higher_is_better: bool = True) -> list[float | None]:
    """Robust cross-sectional percentile ranks with deterministic average ranks for ties."""

    parsed = [as_number(value) for value in values]
    valid = [(index, value) for index, value in enumerate(parsed) if value is not None]
    result: list[float | None] = [None] * len(values)
    if not valid:
        return result
    distinct = {value for _, value in valid}
    if len(valid) == 1 or len(distinct) == 1:
        for index, _ in valid:
            result[index] = 50.0
        return result

    ordered_values = sorted(value for _, value in valid)
    positions: dict[float, list[int]] = {}
    for position, value in enumerate(ordered_values):
        positions.setdefault(value, []).append(position)
    denominator = len(valid) - 1
    for index, value in valid:
        average_position = sum(positions[value]) / len(positions[value])
        percentile = 100.0 * average_position / denominator
        result[index] = round(percentile if higher_is_better else 100.0 - percentile, 4)
    return result


def compute_participation_percent(
    matches: Iterable[bool | None],
    weights: Iterable[Any] | None = None,
) -> float | None:
    """Compute equal- or value-weighted breadth using only valid metric observations."""

    match_values = list(matches)
    if weights is None:
        valid = [match for match in match_values if match is not None]
        if not valid:
            return None
        return round(100.0 * sum(1 for match in valid if match) / len(valid), 4)

    weight_values = list(weights)
    if len(weight_values) != len(match_values):
        raise ValueError("matches and weights must have identical lengths")
    numerator = 0.0
    denominator = 0.0
    for match, raw_weight in zip(match_values, weight_values):
        weight = as_number(raw_weight)
        if match is None or weight is None or weight <= 0:
            continue
        denominator += weight
        if match:
            numerator += weight
    if denominator <= 0:
        return None
    return round(100.0 * numerator / denominator, 4)


def compute_hhi(weights: Iterable[Any]) -> float | None:
    parsed = [value for value in (as_number(weight) for weight in weights) if value is not None and value > 0]
    total = sum(parsed)
    if total <= 0:
        return None
    return round(sum((value / total) ** 2 for value in parsed), 6)


def compute_risk_adjusted_return(excess_return: Any, realized_volatility: Any) -> float | None:
    excess = as_number(excess_return)
    volatility = as_number(realized_volatility)
    if excess is None or volatility is None or abs(volatility) < 1e-12:
        return None
    return round(excess / abs(volatility), 8)


def score_momentum(
    normalized_ram: Mapping[int, float | None],
    *,
    normalized_rank_improvement_21d: Any = None,
    explicit_acceleration_raw: Any = None,
    config: V3Config = DEFAULT_CONFIG,
) -> MomentumResult:
    score, coverage = weighted_score(normalized_ram, config.momentum_weights)
    valid_horizons = sum(clamp_score(normalized_ram.get(horizon)) is not None for horizon in config.momentum_weights)
    if valid_horizons < config.minimum_momentum_horizons:
        score = None

    acceleration = as_number(explicit_acceleration_raw)
    if acceleration is None:
        ram21 = clamp_score(normalized_ram.get(21))
        ram63 = clamp_score(normalized_ram.get(63))
        ram126 = clamp_score(normalized_ram.get(126))
        if ram21 is not None and ram63 is not None and ram126 is not None:
            rank_score = clamp_score(normalized_rank_improvement_21d)
            centered_rank = (rank_score - 50.0) if rank_score is not None else 0.0
            acceleration = 0.50 * (ram21 - ram63) + 0.30 * (ram63 - ram126) + 0.20 * centered_rank
    acceleration = round(acceleration, 4) if acceleration is not None else None
    acceleration_score = clamp_score(50.0 + acceleration) if acceleration is not None else None
    if acceleration is None:
        direction = "DATA_WEAK"
    elif acceleration >= config.positive_acceleration_threshold:
        direction = "ACCELERATING"
    elif acceleration <= config.negative_acceleration_threshold:
        direction = "DECELERATING"
    else:
        direction = "STABLE"
    return MomentumResult(score, acceleration, acceleration_score, direction, coverage)


def score_trend(
    components: Mapping[str, float | None],
    *,
    proxy_score: Any = None,
    config: V3Config = DEFAULT_CONFIG,
) -> FactorResult:
    score, coverage = weighted_score(
        components,
        config.trend_weights,
        minimum_available_weight=config.minimum_trend_weight,
    )
    reasons: list[str] = []
    if score is None:
        proxy = as_number(proxy_score)
        if proxy is not None:
            score = clamp_score(proxy * 100.0 if abs(proxy) <= 1.0 else proxy)
            coverage = 0.0
            reasons.append("LEGACY_TREND_PROXY_USED")
    if score is None:
        state = "DATA_WEAK"
    elif score >= 80:
        state = "STRONG_UPTREND"
    elif score >= 65:
        state = "UPTREND"
    elif score >= 55:
        state = "EARLY_UPTREND"
    elif score >= 45:
        state = "SIDEWAYS"
    elif score >= 35:
        state = "WEAKENING"
    elif score >= 20:
        state = "DOWNTREND"
    else:
        state = "STRONG_DOWNTREND"
    return FactorResult(score, coverage, state, tuple(reasons))


def score_breadth(
    metrics: Mapping[str, float | None],
    *,
    config: V3Config = DEFAULT_CONFIG,
) -> FactorResult:
    score, coverage = weighted_score(
        metrics,
        config.breadth_weights,
        minimum_available_weight=config.minimum_breadth_weight,
    )
    reasons: list[str] = []
    if 0 < coverage < 100:
        reasons.append("BREADTH_COMPONENTS_INCOMPLETE")
    if score is None:
        state = "DATA_WEAK"
    elif score >= 60:
        state = "STRONG"
    elif score >= 45:
        state = "NEUTRAL"
    else:
        state = "NARROW"
    return FactorResult(score, coverage, state, tuple(reasons))


def score_money_flow(
    components: Mapping[str, float | None],
    *,
    config: V3Config = DEFAULT_CONFIG,
) -> FactorResult:
    score, coverage = weighted_score(
        components,
        config.money_flow_weights,
        minimum_available_weight=config.minimum_money_flow_weight,
    )
    reasons: list[str] = []
    if score is None:
        reasons.append("MONEY_FLOW_DATA_INCOMPLETE")
        state = "DATA_WEAK"
    elif score >= 60:
        state = "POSITIVE"
    elif score <= 40:
        state = "NEGATIVE"
    else:
        state = "NEUTRAL"
    return FactorResult(score, coverage, state, tuple(reasons))


def score_risk(
    component_scores: Mapping[str, float | None],
    *,
    proxy_score: Any = None,
    config: V3Config = DEFAULT_CONFIG,
) -> FactorResult:
    score, coverage = weighted_score(
        component_scores,
        config.risk_weights,
        minimum_available_weight=config.minimum_risk_weight,
    )
    reasons: list[str] = []
    if score is None:
        proxy = clamp_score(proxy_score)
        if proxy is not None:
            score = proxy
            coverage = 0.0
            reasons.append("LEGACY_RISK_PROXY_USED")
    if score is None:
        state = "DATA_WEAK"
    elif score >= 80:
        state = "LOW"
    elif score >= 60:
        state = "NORMAL"
    elif score >= 40:
        state = "ELEVATED"
    elif score >= 20:
        state = "HIGH"
    else:
        state = "EXTREME"
    return FactorResult(score, coverage, state, tuple(reasons))


def score_data_quality(
    components: Mapping[str, float | None],
    *,
    config: V3Config = DEFAULT_CONFIG,
) -> FactorResult:
    score, coverage = weighted_score(
        components,
        config.data_quality_weights,
        minimum_available_weight=config.minimum_data_quality_weight,
    )
    if score is not None:
        # Missing quality dimensions are not assigned zero, but incomplete
        # evidence cannot earn a quality score above its component coverage.
        score = min(score, coverage)
    reasons: list[str] = []
    if components.get("historyCoverage") is None:
        reasons.append("INSUFFICIENT_HISTORY")
    if components.get("liquidityCoverage") is None:
        reasons.append("LIQUIDITY_DATA_INCOMPLETE")
    if score is None:
        state = "DATA_INSUFFICIENT"
    elif score >= 90:
        state = "EXCELLENT"
    elif score >= 80:
        state = "GOOD"
    elif score >= 65:
        state = "ACCEPTABLE"
    elif score >= 40:
        state = "WEAK"
    else:
        state = "DATA_INSUFFICIENT"
    return FactorResult(score, coverage, state, tuple(reasons))


def score_final_rotation(
    factor_scores: Mapping[str, float | None],
    *,
    config: V3Config = DEFAULT_CONFIG,
) -> FinalScoreResult:
    configured = dict(config.factor_weights)
    required = ("momentum", "breadth", "trend", "risk", "dataQuality")
    missing_required = [name for name in required if clamp_score(factor_scores.get(name)) is None]
    if missing_required:
        reasons = tuple(f"{name.upper()}_DATA_INSUFFICIENT" for name in missing_required)
        return FinalScoreResult(None, configured, configured.copy(), False, reasons)

    effective = configured.copy()
    redistribution_applied = clamp_score(factor_scores.get("moneyFlow")) is None
    if redistribution_applied:
        missing_weight = effective["moneyFlow"]
        effective["moneyFlow"] = 0.0
        redistribution_targets = ("momentum", "breadth", "trend", "risk")
        target_total = sum(configured[name] for name in redistribution_targets)
        for name in redistribution_targets:
            effective[name] += missing_weight * configured[name] / target_total

    composite = 0.0
    for name, weight in effective.items():
        if weight <= 0:
            continue
        value = clamp_score(factor_scores.get(name))
        if value is None:
            return FinalScoreResult(None, configured, effective, redistribution_applied, (f"{name.upper()}_DATA_INSUFFICIENT",))
        composite += value * weight
    reasons: list[str] = []
    if redistribution_applied:
        composite -= config.missing_money_flow_penalty
        reasons.extend(("MONEY_FLOW_DATA_INCOMPLETE", "MONEY_FLOW_WEIGHT_REDISTRIBUTED"))
    return FinalScoreResult(clamp_score(composite), configured, effective, redistribution_applied, tuple(reasons))


def rotation_band(score: Any) -> str:
    value = clamp_score(score)
    if value is None:
        return "DATA_WEAK"
    if value >= 85:
        return "VERY_STRONG"
    if value >= 70:
        return "STRONG"
    if value >= 55:
        return "POSITIVE"
    if value >= 45:
        return "NEUTRAL"
    if value >= 30:
        return "WEAK"
    return "VERY_WEAK"


def classify_phase(
    *,
    relative_strength_level: Any,
    momentum_acceleration_raw: Any,
    trend_score: Any,
    breadth_delta_5d: Any,
    previous_phase: str | None = None,
    recent_phase_candidates: Sequence[str] = (),
    config: V3Config = DEFAULT_CONFIG,
) -> PhaseResult:
    strength = clamp_score(relative_strength_level)
    acceleration = as_number(momentum_acceleration_raw)
    trend = clamp_score(trend_score)
    breadth_delta = as_number(breadth_delta_5d)
    previous = str(previous_phase or "").strip().upper()
    valid_phases = {"LEADING", "IMPROVING", "WEAKENING", "LAGGING"}
    if strength is None or acceleration is None or trend is None:
        return PhaseResult("DATA_WEAK", "LOW", ("PHASE_INPUTS_INSUFFICIENT",))

    positive = config.positive_acceleration_threshold
    negative = config.negative_acceleration_threshold
    if strength >= config.relative_strength_threshold and acceleration >= positive and trend >= config.trend_confirmation_threshold:
        candidate = "LEADING"
        reasons = ["RELATIVE_STRENGTH_HIGH", "MOMENTUM_ACCELERATING", "TREND_CONFIRMED"]
    elif strength < config.relative_strength_threshold and acceleration >= positive and breadth_delta is not None and breadth_delta > 0:
        candidate = "IMPROVING"
        reasons = ["MOMENTUM_ACCELERATING", "BREADTH_EXPANDING"]
    elif strength >= config.relative_strength_threshold and acceleration <= negative:
        candidate = "WEAKENING"
        reasons = ["RELATIVE_STRENGTH_HIGH", "MOMENTUM_DECELERATING"]
    elif strength < config.relative_strength_threshold and acceleration <= negative:
        candidate = "LAGGING"
        reasons = ["RELATIVE_STRENGTH_LOW", "MOMENTUM_DECELERATING"]
    elif previous in valid_phases:
        return PhaseResult(previous, "MEDIUM", ("PHASE_DEAD_BAND_PRESERVED",))
    elif strength >= config.relative_strength_threshold:
        candidate = "LEADING" if trend >= config.trend_confirmation_threshold else "WEAKENING"
        reasons = ["PHASE_DEAD_BAND_FALLBACK"]
    else:
        candidate = "IMPROVING" if breadth_delta is not None and breadth_delta > 0 else "LAGGING"
        reasons = ["PHASE_DEAD_BAND_FALLBACK"]

    history = [str(value).strip().upper() for value in recent_phase_candidates if str(value).strip().upper() in valid_phases]
    confirmation_window = (history + [candidate])[-3:]
    if previous in valid_phases and candidate != previous and confirmation_window.count(candidate) < 2:
        return PhaseResult(previous, "MEDIUM", ("PHASE_HYSTERESIS_PRESERVED",))
    margin = min(abs(acceleration - positive), abs(acceleration - negative))
    confidence = "HIGH" if margin >= 5 and trend >= 65 else "MEDIUM"
    return PhaseResult(candidate, confidence, tuple(reasons))


def classify_confidence(
    *,
    data_quality_score: Any,
    coverage_percent: Any,
    history_coverage_percent: Any,
    latest_data_date: Any,
    as_of_date: Any,
    core_factors_available: bool,
    money_flow_available: bool,
    severe_warning: bool = False,
    proxy_used: bool = False,
) -> ConfidenceResult:
    quality = clamp_score(data_quality_score)
    coverage = clamp_score(coverage_percent)
    history = clamp_score(history_coverage_percent)
    dates_match = bool(latest_data_date and as_of_date and str(latest_data_date)[:10] == str(as_of_date)[:10])
    score_inputs = [value for value in (quality, coverage, history) if value is not None]
    score = sum(score_inputs) / len(score_inputs) if score_inputs else 0.0
    reasons: list[str] = []
    if not core_factors_available:
        reasons.append("CORE_FACTORS_INCOMPLETE")
    if coverage is None or coverage < 65:
        reasons.append("LOW_COVERAGE")
    if history is None or history < 75:
        reasons.append("INSUFFICIENT_HISTORY")
    if not dates_match:
        reasons.append("DATA_STALE")
    if not money_flow_available:
        reasons.append("MONEY_FLOW_DATA_INCOMPLETE")
    if severe_warning:
        reasons.append("SEVERE_DATA_WARNING")
    if proxy_used:
        reasons.append("LEGACY_FACTOR_PROXY_USED")

    high = (
        core_factors_available
        and money_flow_available
        and not severe_warning
        and not proxy_used
        and quality is not None
        and quality >= 90
        and coverage is not None
        and coverage >= 85
        and history is not None
        and history >= 90
        and dates_match
    )
    medium = (
        core_factors_available
        and not severe_warning
        and quality is not None
        and quality >= 75
        and coverage is not None
        and coverage >= 65
    )
    if high:
        label = "HIGH"
    elif medium:
        label = "MEDIUM"
        score = min(score, 84.99)
    else:
        label = "LOW"
        score = min(score, 64.99)
    return ConfidenceResult(label, round(max(0.0, min(100.0, score)), 4), tuple(dict.fromkeys(reasons)))
