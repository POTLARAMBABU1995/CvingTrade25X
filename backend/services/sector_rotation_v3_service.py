from __future__ import annotations

import os
import time
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal
import math
from typing import Any, Mapping, Sequence

from services.sector_rotation_v3_factors import (
    DEFAULT_CONFIG,
    MODEL_VERSION,
    ConfidenceResult,
    FactorResult,
    V3Config,
    as_number,
    clamp_score,
    classify_confidence,
    classify_phase,
    compute_risk_adjusted_return,
    percentile_scores,
    rotation_band,
    score_breadth,
    score_data_quality,
    score_final_rotation,
    score_money_flow,
    score_momentum,
    score_risk,
    score_trend,
    weighted_score,
)


class V3FeatureDisabledError(RuntimeError):
    pass


_BREADTH_ALIASES: Mapping[str, tuple[str, ...]] = {
    "rsi55": ("rsi55Percent", "rsi55Pct", "rsi55"),
    "rsi50": ("rsi50Percent", "rsi50Pct", "rsi50"),
    "sma20": ("sma20Percent", "sma20Pct", "sma20"),
    "sma50": ("sma50Percent", "sma50Pct", "sma50"),
    "sma100": ("sma100Percent", "sma100Pct", "sma100"),
    "sma200": ("sma200Percent", "sma200Pct", "sma200"),
    "bullishStack": ("bullishStackPercent", "bullishSmaStackPercent"),
}


def is_sector_rotation_v3_enabled(engine_version: str | None = None) -> bool:
    selected = engine_version if engine_version is not None else os.getenv("SECTOR_ROTATION_ENGINE_VERSION", "v2")
    return str(selected or "").strip().lower() == "v3"


def _first(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] is not None and row[key] != "":
            return row[key]
    return None


def _json_safe(value: Any) -> Any:
    """Recursively remove non-finite numerics without changing valid zero/null semantics."""

    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return value
    if isinstance(value, (float, Decimal)):
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _date_text(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value or "").strip()
    return text[:10] if len(text) >= 10 else (text or None)


def _to_date(value: Any) -> date | None:
    text = _date_text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _as_int(value: Any) -> int:
    number = as_number(value)
    return max(int(round(number)), 0) if number is not None else 0


def _ratio_percent(numerator: Any, denominator: Any) -> float | None:
    top = as_number(numerator)
    bottom = as_number(denominator)
    if top is None or bottom is None or bottom <= 0:
        return None
    return clamp_score(100.0 * top / bottom)


def _binary_score(left: Any, right: Any, *, greater: bool = True) -> float | None:
    left_value = as_number(left)
    right_value = as_number(right)
    if left_value is None or right_value is None:
        return None
    condition = left_value > right_value if greater else left_value >= right_value
    return 100.0 if condition else 0.0


def _positive_score(value: Any) -> float | None:
    number = as_number(value)
    return None if number is None else (100.0 if number > 0 else 0.0)


def _resolve_common_as_of_date(rows: Sequence[Mapping[str, Any]], explicit: Any = None) -> str | None:
    explicit_text = _date_text(explicit)
    if explicit_text:
        return explicit_text
    dates = [
        text
        for text in (_date_text(_first(row, "asOfDate", "latestDataDate")) for row in rows)
        if text
    ]
    if not dates:
        return None
    counts = Counter(dates)
    return sorted(counts, key=lambda item: (counts[item], item), reverse=True)[0]


def _freshness_score(latest_data_date: Any, as_of_date: Any) -> float | None:
    latest = _to_date(latest_data_date)
    anchor = _to_date(as_of_date)
    if latest is None or anchor is None:
        return None
    days_stale = max((anchor - latest).days, 0)
    if days_stale == 0:
        return 100.0
    if days_stale == 1:
        return 70.0
    return clamp_score(70.0 - (days_stale - 1) * 25.0)


def _metric_equal_percent(row: Mapping[str, Any], metric: str) -> float | None:
    aliases = _BREADTH_ALIASES[metric]
    direct = clamp_score(_first(row, *aliases, f"{metric}EqualWeightPercent"))
    if direct is not None:
        return direct
    numerator = _first(row, f"{metric}Count", f"{metric}AboveCount", f"{metric}MatchCount")
    denominator = _first(row, f"{metric}ValidCount", f"valid{metric[0].upper()}{metric[1:]}Count")
    return _ratio_percent(numerator, denominator)


def _metric_blend(
    row: Mapping[str, Any],
    metric: str,
    config: V3Config,
) -> tuple[float | None, float | None, float]:
    equal_weight = _metric_equal_percent(row, metric)
    ffmc_weight = clamp_score(
        _first(row, f"{metric}FfmcWeightedPercent", f"{metric}FFMCWeightedPercent")
    )
    market_cap_weight = clamp_score(
        _first(row, f"{metric}MarketCapWeightedPercent", f"{metric}McapWeightedPercent")
    )
    blended, source_coverage = weighted_score(
        {
            "equalWeight": equal_weight,
            "ffmcWeight": ffmc_weight,
            "marketCapWeight": market_cap_weight,
        },
        config.breadth_blend_weights,
    )
    return equal_weight, blended, source_coverage


def _trend_components(row: Mapping[str, Any]) -> dict[str, float | None]:
    close = _first(row, "sectorIndexClose", "sector_index_close")
    sma20 = _first(row, "sectorSMA20", "sectorSma20")
    sma50 = _first(row, "sectorSMA50", "sectorSma50")
    sma100 = _first(row, "sectorSMA100", "sectorSma100")
    sma200 = _first(row, "sectorSMA200", "sectorSma200")
    moving_averages = [as_number(value) for value in (sma20, sma50, sma100, sma200)]
    bullish_structure = None
    if all(value is not None for value in moving_averages):
        assert all(value is not None for value in moving_averages)
        bullish_structure = 100.0 if moving_averages[0] > moving_averages[1] > moving_averages[2] > moving_averages[3] else 0.0
    return {
        "aboveSma20": _binary_score(close, sma20),
        "aboveSma50": _binary_score(close, sma50),
        "aboveSma100": _binary_score(close, sma100),
        "aboveSma200": _binary_score(close, sma200),
        "bullishStructure": bullish_structure,
        "positiveSma50Slope": _positive_score(_first(row, "sectorSMA50Slope", "sectorSma50Slope")),
        "positiveSma100Slope": _positive_score(_first(row, "sectorSMA100Slope", "sectorSma100Slope")),
        "positiveReturn252": _positive_score(_first(row, "sectorReturn252", "absoluteReturn252")),
    }


def _volume_ratio_score(value: Any) -> float | None:
    ratio = as_number(value)
    if ratio is None or ratio < 0:
        return None
    return clamp_score(50.0 + 50.0 * (ratio - 1.0))


def _money_flow_components(row: Mapping[str, Any]) -> dict[str, float | None]:
    return {
        "volumeRatio": _volume_ratio_score(_first(row, "volumeRatio20", "volumeRatio")),
        "deliveryParticipation": clamp_score(_first(row, "deliveryParticipationScore")),
        "obvSlope": clamp_score(_first(row, "obvSlopeScore")),
        "accumulation": clamp_score(_first(row, "accumulationScore", "accumulationDistributionScore")),
        "upDownVolume": clamp_score(_first(row, "upDownVolumeScore")),
        "breadthVolume": clamp_score(_first(row, "breadthVolumeScore")),
    }


def _history_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value]


def _prepare_contexts(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    for source in rows:
        row = dict(source)
        precomputed_v3 = str(row.get("modelVersion") or "").strip().upper() == MODEL_VERSION
        context: dict[str, Any] = {
            "source": row,
            "precomputedV3": precomputed_v3,
            "normalizedRam": {},
            "rawRam": {},
            "riskComponents": {},
            "factorReasons": [],
        }
        for horizon in (21, 63, 126, 252):
            explicit = clamp_score(
                _first(row, f"normalizedRam{horizon}", f"normalizedRAM{horizon}")
            )
            context["normalizedRam"][horizon] = explicit
            context["rawRam"][horizon] = compute_risk_adjusted_return(
                _first(row, f"relativeReturn{horizon}", f"excessReturn{horizon}", f"relRet{horizon}"),
                _first(row, f"realizedVolatility{horizon}", f"volatility{horizon}", f"sigma{horizon}"),
            )

        drawdowns = [
            abs(value)
            for value in (
                as_number(_first(row, "maxDrawdown126", "drawdown126")),
                as_number(_first(row, "maxDrawdown252", "drawdown252")),
            )
            if value is not None
        ]
        context["riskRaw"] = {
            "volatility": as_number(_first(row, "volatility63", "sigma63")),
            "downsideVolatility": as_number(_first(row, "downsideVolatility126")),
            "drawdown": max(drawdowns) if drawdowns else None,
            "betaInstability": as_number(_first(row, "betaInstability")),
            "concentration": as_number(_first(row, "concentrationHhi", "concentrationHHI")),
            "liquidity": as_number(_first(row, "liquidityRisk")),
        }
        context["riskComponents"] = {
            "volatility": clamp_score(_first(row, "volatilityRiskScore")),
            "downsideVolatility": clamp_score(_first(row, "downsideVolatilityRiskScore")),
            "drawdown": clamp_score(_first(row, "drawdownRiskScore")),
            "betaInstability": clamp_score(_first(row, "betaInstabilityRiskScore")),
            "concentration": clamp_score(_first(row, "concentrationRiskScore")),
            "liquidity": clamp_score(_first(row, "liquidityScore", "liquidityCoveragePercent")),
        }
        contexts.append(context)

    for horizon in (21, 63, 126, 252):
        ranks = percentile_scores([context["rawRam"][horizon] for context in contexts])
        for context, rank in zip(contexts, ranks):
            if context["normalizedRam"][horizon] is None:
                context["normalizedRam"][horizon] = rank

    momentum_proxy_ranks = percentile_scores(
        [_first(context["source"], "relativeMomentum") for context in contexts]
    )
    risk_proxy_ranks = percentile_scores(
        [_first(context["source"], "riskAdjustment", "riskAdjustmentMin") for context in contexts]
    )
    for context, momentum_proxy, risk_proxy in zip(contexts, momentum_proxy_ranks, risk_proxy_ranks):
        context["momentumProxy"] = momentum_proxy
        context["riskProxy"] = risk_proxy

    for component in ("volatility", "downsideVolatility", "drawdown", "betaInstability", "concentration", "liquidity"):
        inverse_ranks = percentile_scores(
            [context["riskRaw"][component] for context in contexts],
            higher_is_better=False,
        )
        for context, rank in zip(contexts, inverse_ranks):
            if context["riskComponents"][component] is None:
                context["riskComponents"][component] = rank
    return contexts


def _coverage_fields(row: Mapping[str, Any]) -> tuple[int, int, int, float | None, float | None]:
    eligible = _as_int(_first(row, "eligibleStockCount", "totalStocks", "totalSymbols"))
    valid_price = _as_int(_first(row, "validPriceCount", "screenedStocks", "availableSymbols"))
    valid_indicator = _as_int(_first(row, "validIndicatorCount", "screenedStocks", "availableSymbols"))
    coverage = clamp_score(_first(row, "coveragePercent"))
    if coverage is None:
        coverage = _ratio_percent(valid_indicator, eligible)
    history_coverage = clamp_score(_first(row, "historyCoveragePercent"))
    return eligible, valid_price, valid_indicator, coverage, history_coverage


def _null_outlier_quality(row: Mapping[str, Any], eligible: int) -> float | None:
    explicit = clamp_score(_first(row, "nullOutlierQualityScore"))
    if explicit is not None:
        return explicit
    count_keys_present = any(key in row for key in ("outlierCount", "missingCriticalFieldCount"))
    if not count_keys_present or eligible <= 0:
        return None
    issues = _as_int(row.get("outlierCount")) + _as_int(row.get("missingCriticalFieldCount"))
    return clamp_score(100.0 * (1.0 - min(issues / eligible, 1.0)))


def _data_quality_state(score: float | None) -> str:
    if score is None:
        return "DATA_INSUFFICIENT"
    if score >= 90:
        return "EXCELLENT"
    if score >= 80:
        return "GOOD"
    if score >= 65:
        return "ACCEPTABLE"
    if score >= 40:
        return "WEAK"
    return "DATA_INSUFFICIENT"


def _trend_state(score: float | None) -> str:
    if score is None:
        return "DATA_WEAK"
    if score >= 80:
        return "STRONG_UPTREND"
    if score >= 65:
        return "UPTREND"
    if score >= 55:
        return "EARLY_UPTREND"
    if score >= 45:
        return "SIDEWAYS"
    if score >= 35:
        return "WEAKENING"
    if score >= 20:
        return "DOWNTREND"
    return "STRONG_DOWNTREND"


def _factor_result_from_precomputed(score: Any, state: str, coverage: Any = 100.0) -> FactorResult:
    parsed_score = clamp_score(score)
    return FactorResult(parsed_score, clamp_score(coverage) or 0.0, state if parsed_score is not None else "DATA_WEAK")


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _build_summary(row: Mapping[str, Any]) -> str:
    sector_name = str(row.get("sectorName") or row.get("sectorCode") or "Sector")
    final_score = clamp_score(row.get("finalRotationScore"))
    if final_score is None:
        return f"{sector_name} has insufficient core-factor coverage for a valid V3 rotation score."
    summary = (
        f"{sector_name} is in the {str(row.get('rotationBand') or 'DATA_WEAK').replace('_', ' ').lower()} "
        f"score band with {str(row.get('rotationPhase') or 'DATA_WEAK').replace('_', ' ').lower()} phase dynamics."
    )
    warnings = list(row.get("riskWarnings") or [])
    if warnings:
        summary += f" Primary warning: {warnings[0].replace('_', ' ').lower()}."
    return summary


def _enrich_context(context: dict[str, Any], as_of_date: str | None, config: V3Config) -> dict[str, Any]:
    source = context["source"]
    enriched = dict(source)
    precomputed_v3 = bool(context["precomputedV3"])

    momentum_result = score_momentum(
        context["normalizedRam"],
        normalized_rank_improvement_21d=_first(source, "normalizedRankImprovement21D"),
        explicit_acceleration_raw=_first(source, "momentumAccelerationRaw"),
        config=config,
    )
    momentum_score = momentum_result.score
    factor_reasons: list[str] = []
    if precomputed_v3 and clamp_score(source.get("momentumScore")) is not None:
        momentum_score = clamp_score(source.get("momentumScore"))
    elif momentum_score is None and context.get("momentumProxy") is not None:
        momentum_score = clamp_score(context["momentumProxy"])
        factor_reasons.append("LEGACY_MOMENTUM_PROXY_USED")

    breadth_equal: dict[str, float | None] = {}
    breadth_metrics: dict[str, float | None] = {}
    metric_source_coverage: dict[str, float] = {}
    for metric in config.breadth_weights:
        equal_value, blended_value, source_coverage = _metric_blend(source, metric, config)
        breadth_equal[metric] = equal_value
        breadth_metrics[metric] = blended_value
        metric_source_coverage[metric] = source_coverage
    if precomputed_v3 and clamp_score(source.get("breadthScore")) is not None:
        breadth_result = _factor_result_from_precomputed(
            source.get("breadthScore"),
            str(source.get("breadthDirection") or "STABLE"),
            source.get("breadthMetricCoveragePercent", 100),
        )
    else:
        breadth_result = score_breadth(breadth_metrics, config=config)

    if precomputed_v3 and clamp_score(source.get("trendScore")) is not None:
        trend_score = clamp_score(source.get("trendScore"))
        trend_result = _factor_result_from_precomputed(
            trend_score,
            str(source.get("trendState") or _trend_state(trend_score)),
            source.get("trendCoveragePercent", 100),
        )
    else:
        trend_result = score_trend(
            _trend_components(source),
            proxy_score=_first(source, "absoluteTrend"),
            config=config,
        )

    if precomputed_v3 and clamp_score(source.get("moneyFlowScore")) is not None:
        flow_result = _factor_result_from_precomputed(
            source.get("moneyFlowScore"),
            str(source.get("moneyFlowDirection") or "NEUTRAL"),
            source.get("moneyFlowCoveragePercent", 100),
        )
    else:
        flow_result = score_money_flow(_money_flow_components(source), config=config)

    if precomputed_v3 and clamp_score(source.get("riskScore")) is not None:
        risk_score = clamp_score(source.get("riskScore"))
        risk_result = _factor_result_from_precomputed(
            risk_score,
            str(source.get("riskRegime") or "NORMAL"),
            source.get("riskCoveragePercent", 100),
        )
    else:
        risk_result = score_risk(
            context["riskComponents"],
            proxy_score=context.get("riskProxy"),
            config=config,
        )

    eligible, valid_price, valid_indicator, coverage, history_coverage = _coverage_fields(source)
    latest_data_date = _date_text(_first(source, "latestDataDate", "asOfDate"))
    liquidity_coverage = clamp_score(_first(source, "liquidityCoveragePercent"))
    if liquidity_coverage is None and flow_result.coverage_percent > 0:
        liquidity_coverage = flow_result.coverage_percent
    quality_components = {
        "freshness": _freshness_score(latest_data_date, as_of_date),
        "indicatorCoverage": coverage,
        "historyCoverage": history_coverage,
        "nullOutlierQuality": _null_outlier_quality(source, eligible),
        "liquidityCoverage": liquidity_coverage,
    }
    if precomputed_v3 and clamp_score(source.get("dataQualityScore")) is not None:
        quality_score = clamp_score(source.get("dataQualityScore"))
        quality_result = _factor_result_from_precomputed(
            quality_score,
            str(source.get("dataQualityStatus") or _data_quality_state(quality_score)),
            source.get("dataQualityCoveragePercent", 100),
        )
    else:
        quality_result = score_data_quality(quality_components, config=config)

    final_result = score_final_rotation(
        {
            "momentum": momentum_score,
            "breadth": breadth_result.score,
            "trend": trend_result.score,
            "moneyFlow": flow_result.score,
            "risk": risk_result.score,
            "dataQuality": quality_result.score,
        },
        config=config,
    )

    core_available = all(
        value is not None for value in (momentum_score, breadth_result.score, trend_result.score)
    )
    relative_strength = clamp_score(_first(source, "relativeStrengthLevel"))
    if relative_strength is None:
        relative_strength = momentum_score
    breadth_delta_5d = as_number(_first(source, "breadthDelta5D", "breadthDelta5"))
    phase_result = classify_phase(
        relative_strength_level=relative_strength,
        momentum_acceleration_raw=momentum_result.acceleration_raw,
        trend_score=trend_result.score,
        breadth_delta_5d=breadth_delta_5d,
        previous_phase=_first(source, "previousPhase") if precomputed_v3 else None,
        recent_phase_candidates=(
            _history_list(_first(source, "recentPhaseCandidates", "phaseHistory"))
            if precomputed_v3
            else ()
        ),
        config=config,
    )
    if final_result.score is None:
        phase_result = type(phase_result)("DATA_WEAK", "LOW", ("CORE_FACTORS_INCOMPLETE",))

    proxy_used = any("PROXY_USED" in code for code in factor_reasons + list(trend_result.reason_codes) + list(risk_result.reason_codes))
    severe_warning = bool(
        _first(source, "sectorMappingConflict", "corporateActionOutlier", "unresolvedConstituentMapping")
    )
    confidence: ConfidenceResult = classify_confidence(
        data_quality_score=quality_result.score,
        coverage_percent=coverage,
        history_coverage_percent=history_coverage,
        latest_data_date=latest_data_date,
        as_of_date=as_of_date,
        core_factors_available=core_available and final_result.score is not None,
        money_flow_available=flow_result.score is not None,
        severe_warning=severe_warning,
        proxy_used=proxy_used,
    )

    legacy_values = [breadth_equal[name] for name in ("rsi55", "rsi50", "sma20", "sma50", "sma100")]
    valid_legacy_values = [value for value in legacy_values if value is not None]
    legacy_display_score = clamp_score(_first(source, "legacyDisplayScore", "score"))
    if legacy_display_score is None and valid_legacy_values:
        legacy_display_score = round(sum(valid_legacy_values) / len(valid_legacy_values), 4)

    positive_reasons: list[str] = []
    risk_warnings: list[str] = []
    relative_return_63 = as_number(_first(source, "relativeReturn63", "excessReturn63", "relRet63"))
    relative_return_126 = as_number(_first(source, "relativeReturn126", "excessReturn126", "relRet126"))
    if relative_return_63 is not None and relative_return_63 > 0:
        positive_reasons.append("OUTPERFORMING_BENCHMARK_63D")
    if relative_return_126 is not None and relative_return_126 > 0:
        positive_reasons.append("OUTPERFORMING_BENCHMARK_126D")
    if momentum_score is not None and momentum_score >= 70:
        positive_reasons.append("RISK_ADJUSTED_MOMENTUM_STRONG")
    if momentum_result.direction == "ACCELERATING":
        positive_reasons.append("MOMENTUM_ACCELERATING")
    elif momentum_result.direction == "DECELERATING":
        risk_warnings.append("MOMENTUM_DECELERATING")
    breadth_delta_21d = as_number(_first(source, "breadthDelta21D", "breadthDelta21"))
    if breadth_delta_5d is not None and breadth_delta_5d > 0:
        positive_reasons.append("BREADTH_EXPANDING")
    if breadth_result.score is not None and breadth_result.score < 40:
        risk_warnings.append("BREADTH_NARROW")
    if breadth_equal.get("sma50") is not None and breadth_equal["sma50"] >= 70:
        positive_reasons.append("SMA50_BREADTH_STRONG")
    if breadth_equal.get("sma200") is not None and breadth_equal["sma200"] >= 60:
        positive_reasons.append("SMA200_BREADTH_CONFIRMED")
    if trend_result.state in {"STRONG_UPTREND", "UPTREND"}:
        positive_reasons.append("BULLISH_SECTOR_MA_STACK")
    elif trend_result.state in {"DOWNTREND", "STRONG_DOWNTREND"}:
        risk_warnings.append("SECTOR_BELOW_SMA200")
    if flow_result.score is None:
        risk_warnings.append("MONEY_FLOW_DATA_INCOMPLETE")
    elif flow_result.score >= 60:
        positive_reasons.append("MONEY_FLOW_POSITIVE")
    elif flow_result.score <= 40:
        risk_warnings.append("MONEY_FLOW_NEGATIVE")
    if risk_result.score is not None and risk_result.score >= 70:
        positive_reasons.extend(("DRAWDOWN_CONTROLLED", "VOLATILITY_ACCEPTABLE"))
    elif risk_result.score is not None and risk_result.score < 40:
        risk_warnings.extend(("VOLATILITY_HIGH", "DRAWDOWN_ELEVATED"))
    hhi = as_number(_first(source, "concentrationHhi", "concentrationHHI"))
    if hhi is not None and hhi >= 0.18:
        risk_warnings.append("CONCENTRATION_HIGH")
    if coverage is None or coverage < 65:
        risk_warnings.append("LOW_COVERAGE")
    if latest_data_date and as_of_date and latest_data_date != as_of_date:
        risk_warnings.append("DATA_STALE")
    if history_coverage is None or history_coverage < 75:
        risk_warnings.append("INSUFFICIENT_HISTORY")
    if severe_warning:
        if bool(source.get("corporateActionOutlier")):
            risk_warnings.append("CORPORATE_ACTION_OUTLIER")
        if bool(_first(source, "sectorMappingConflict", "unresolvedConstituentMapping")):
            risk_warnings.append("SECTOR_MAPPING_CONFLICT")
    if phase_result.phase == "LEADING":
        positive_reasons.append("ROTATION_LEADING")

    reason_codes = _unique(
        positive_reasons
        + risk_warnings
        + factor_reasons
        + list(breadth_result.reason_codes)
        + list(trend_result.reason_codes)
        + list(flow_result.reason_codes)
        + list(risk_result.reason_codes)
        + list(quality_result.reason_codes)
        + list(final_result.reason_codes)
        + list(phase_result.reason_codes)
        + list(confidence.reason_codes)
    )

    total_stocks = _as_int(_first(source, "totalStocks", "totalSymbols"))
    enriched.update(
        {
            "version": "v3",
            "modelVersion": MODEL_VERSION,
            "sectorCode": str(_first(source, "sectorCode") or "").strip().upper(),
            "sectorName": str(_first(source, "sectorName", "sectorCode") or "").strip(),
            "asOfDate": as_of_date,
            "latestDataDate": latest_data_date,
            "totalStocks": total_stocks,
            "eligibleStockCount": eligible,
            "validPriceCount": valid_price,
            "validIndicatorCount": valid_indicator,
            "coveragePercent": coverage,
            "historyCoveragePercent": history_coverage,
            "staleStockCount": _as_int(_first(source, "staleStockCount")),
            "excludedStockCount": _as_int(_first(source, "excludedStockCount")),
            "rsi55Percent": breadth_equal["rsi55"],
            "rsi50Percent": breadth_equal["rsi50"],
            "sma20Percent": breadth_equal["sma20"],
            "sma50Percent": breadth_equal["sma50"],
            "sma100Percent": breadth_equal["sma100"],
            "sma200Percent": breadth_equal["sma200"],
            "bullishStackPercent": breadth_equal["bullishStack"],
            "breadthMetricSourceCoverage": metric_source_coverage,
            "legacyDisplayScore": legacy_display_score,
            "relativeReturn21": as_number(_first(source, "relativeReturn21", "excessReturn21", "relRet21")),
            "relativeReturn63": relative_return_63,
            "relativeReturn126": relative_return_126,
            "relativeReturn252": as_number(_first(source, "relativeReturn252", "excessReturn252", "relRet252")),
            "momentumScore": momentum_score,
            "momentumAccelerationRaw": momentum_result.acceleration_raw,
            "momentumAccelerationScore": momentum_result.acceleration_score,
            "momentumDirection": momentum_result.direction,
            "breadthScore": breadth_result.score,
            "breadthDelta1D": as_number(_first(source, "breadthDelta1D", "breadthDelta1")),
            "breadthDelta5D": breadth_delta_5d,
            "breadthDelta21D": breadth_delta_21d,
            "breadthDirection": "EXPANDING" if breadth_delta_5d is not None and breadth_delta_5d > 0 else "CONTRACTING" if breadth_delta_5d is not None and breadth_delta_5d < 0 else "STABLE",
            "trendScore": trend_result.score,
            "trendState": trend_result.state,
            "moneyFlowScore": flow_result.score,
            "moneyFlowDirection": flow_result.state,
            "moneyFlowCoveragePercent": flow_result.coverage_percent,
            "riskScore": risk_result.score,
            "volatility63": as_number(_first(source, "volatility63", "sigma63")),
            "maxDrawdown126": as_number(_first(source, "maxDrawdown126", "drawdown126")),
            "maxDrawdown252": as_number(_first(source, "maxDrawdown252", "drawdown252")),
            "concentrationHhi": hhi,
            "riskRegime": risk_result.state,
            "dataQualityScore": quality_result.score,
            "dataQualityStatus": quality_result.state,
            "finalRotationScore": final_result.score,
            "rotationBand": rotation_band(final_result.score),
            "rotationPhase": phase_result.phase,
            "phaseConfidence": phase_result.confidence,
            "phaseReasonCodes": list(phase_result.reason_codes),
            "previousPhase": _first(source, "previousPhase") if precomputed_v3 else None,
            "phaseChangedAt": _date_text(_first(source, "phaseChangedAt")) if precomputed_v3 else None,
            "phaseDurationDays": _as_int(_first(source, "phaseDurationDays")) if precomputed_v3 else 0,
            "confidence": confidence.label,
            "confidenceScore": confidence.score,
            "confidenceReasonCodes": list(confidence.reason_codes),
            "reasonCodes": reason_codes,
            "positiveReasons": _unique(positive_reasons),
            "riskWarnings": _unique(risk_warnings),
            "configuredWeights": dict(final_result.configured_weights),
            "effectiveWeights": {key: round(value, 8) for key, value in final_result.effective_weights.items()},
            "weightRedistributionApplied": final_result.redistribution_applied,
            "rsi55": breadth_equal["rsi55"],
            "rsi50": breadth_equal["rsi50"],
            "sma20": breadth_equal["sma20"],
            "sma50": breadth_equal["sma50"],
            "sma100": breadth_equal["sma100"],
            "score": legacy_display_score,
            "rotation": final_result.score,
            "momentum": momentum_score,
            "breadth": breadth_result.score,
            "moneyFlow": flow_result.score,
            "risk": risk_result.score,
            "trend": trend_result.score,
            "phase": phase_result.phase,
            "_v3HistorySource": precomputed_v3,
        }
    )
    return enriched


def _rank_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows.sort(
        key=lambda row: (
            clamp_score(row.get("finalRotationScore")) is None,
            -(clamp_score(row.get("finalRotationScore")) or 0.0),
            -(clamp_score(row.get("confidenceScore")) or 0.0),
            -(clamp_score(row.get("coveragePercent")) or 0.0),
            str(row.get("sectorName") or ""),
        )
    )
    valid_rank = 0
    for row in rows:
        row.pop("_v3HistorySource", False)
        if clamp_score(row.get("finalRotationScore")) is None:
            row["currentRank"] = None
        else:
            valid_rank += 1
            row["currentRank"] = valid_rank

        current_rank = as_number(row.get("currentRank"))
        rank_change_1d = as_number(_first(row, "rankChange1D"))
        if rank_change_1d is None and current_rank is not None:
            previous_rank = as_number(_first(row, "previousTradingDayRank"))
            rank_change_1d = previous_rank - current_rank if previous_rank is not None else None
        rank_change_1w = as_number(_first(row, "rankChange1W", "rankChange5"))
        if rank_change_1w is None and current_rank is not None:
            previous_rank = as_number(_first(row, "rankFiveTradingDaysAgo"))
            rank_change_1w = previous_rank - current_rank if previous_rank is not None else None
        rank_change_1m = as_number(_first(row, "rankChange1M", "rankChange21"))
        if rank_change_1m is None and current_rank is not None:
            previous_rank = as_number(_first(row, "rankTwentyOneTradingDaysAgo"))
            rank_change_1m = previous_rank - current_rank if previous_rank is not None else None
        row["rankChange1D"] = rank_change_1d
        row["rankChange1W"] = rank_change_1w
        row["rankChange1M"] = rank_change_1m
        if bool(row.get("isNew")):
            movement = "NEW"
        elif rank_change_1w is None:
            movement = "NOT_AVAILABLE"
        elif rank_change_1w > 0:
            movement = "UP"
        elif rank_change_1w < 0:
            movement = "DOWN"
        else:
            movement = "UNCHANGED"
        row["rankMovement"] = movement
        if movement == "UP":
            row["positiveReasons"] = _unique(list(row.get("positiveReasons") or []) + ["RANK_IMPROVING"])
            row["reasonCodes"] = _unique(list(row.get("reasonCodes") or []) + ["RANK_IMPROVING"])

        divergence_codes: list[str] = []
        return_21 = as_number(row.get("relativeReturn21"))
        breadth_delta_21 = as_number(row.get("breadthDelta21D"))
        acceleration = as_number(row.get("momentumAccelerationRaw"))
        flow_score = clamp_score(row.get("moneyFlowScore"))
        if return_21 is not None and return_21 > 0 and breadth_delta_21 is not None and breadth_delta_21 < 0:
            divergence_codes.append("PRICE_UP_BREADTH_DOWN")
        if return_21 is not None and return_21 < 0 and breadth_delta_21 is not None and breadth_delta_21 > 0:
            divergence_codes.append("PRICE_DOWN_BREADTH_UP")
        if acceleration is not None and acceleration > 0 and flow_score is not None and flow_score < 40:
            divergence_codes.append("MOMENTUM_UP_FLOW_DOWN")
        if acceleration is not None and acceleration < 0 and flow_score is not None and flow_score > 60:
            divergence_codes.append("MOMENTUM_DOWN_FLOW_UP")
        hhi = as_number(row.get("concentrationHhi"))
        if hhi is not None and hhi >= 0.18:
            divergence_codes.append("HIGH_CONCENTRATION_DEPENDENCY")
        strength = clamp_score(row.get("momentumScore"))
        if strength is not None and 50 <= strength < 55 and acceleration is not None and acceleration > 0:
            divergence_codes.append("NEAR_LEADING_TRANSITION")
        if strength is not None and 55 <= strength <= 60 and acceleration is not None and acceleration < 0:
            divergence_codes.append("NEAR_LAGGING_TRANSITION")
        row["divergenceCodes"] = _unique(divergence_codes)
        row["divergenceStatus"] = "WARNING" if divergence_codes else "NONE"
        row["earlyWarningStatus"] = "ATTENTION" if divergence_codes else "NONE"
        row["reasonCodes"] = _unique(list(row.get("reasonCodes") or []) + divergence_codes)
        row["summaryExplanation"] = _build_summary(row)
    return rows


def build_sector_rotation_v3_envelope(
    rows: Sequence[Mapping[str, Any]],
    *,
    engine_version: str | None = None,
    benchmark: str = "NIFTY500",
    as_of_date: Any = None,
    generated_at: str | None = None,
    cache_status: str = "MISS",
    is_stale: bool = False,
    calculation_duration_ms: float | None = None,
    enforce_feature_gate: bool = True,
    config: V3Config = DEFAULT_CONFIG,
) -> dict[str, Any]:
    """Build an additive V3 response without mutating or invoking V1/V2 code paths."""

    if enforce_feature_gate and not is_sector_rotation_v3_enabled(engine_version):
        raise V3FeatureDisabledError(
            "Sector Rotation V3 is disabled; pass engine_version='v3' or set SECTOR_ROTATION_ENGINE_VERSION=v3."
        )
    started_at = time.perf_counter()
    source_rows = [dict(row) for row in rows]
    resolved_as_of_date = _resolve_common_as_of_date(source_rows, as_of_date)
    contexts = _prepare_contexts(source_rows)
    enriched_rows = [_enrich_context(context, resolved_as_of_date, config) for context in contexts]
    ranked_rows = [_json_safe(row) for row in _rank_rows(enriched_rows)]
    duration = calculation_duration_ms
    if duration is None:
        duration = (time.perf_counter() - started_at) * 1000.0
    return {
        "version": "v3",
        "modelVersion": MODEL_VERSION,
        "benchmark": str(benchmark or "NIFTY500"),
        "asOfDate": resolved_as_of_date,
        "generatedAt": generated_at or datetime.now(timezone.utc).isoformat(),
        "cacheStatus": str(cache_status or "MISS").upper(),
        "isStale": bool(is_stale),
        "calculationDurationMs": round(max(float(duration), 0.0), 3),
        "rows": ranked_rows,
    }


def enrich_sector_rotation_v3_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    engine_version: str | None = None,
    enforce_feature_gate: bool = True,
    config: V3Config = DEFAULT_CONFIG,
) -> list[dict[str, Any]]:
    """List-only adapter for route code that must retain the legacy top-level response shape."""

    return build_sector_rotation_v3_envelope(
        rows,
        engine_version=engine_version,
        enforce_feature_gate=enforce_feature_gate,
        config=config,
    )["rows"]


__all__ = [
    "MODEL_VERSION",
    "V3FeatureDisabledError",
    "build_sector_rotation_v3_envelope",
    "enrich_sector_rotation_v3_rows",
    "is_sector_rotation_v3_enabled",
]
