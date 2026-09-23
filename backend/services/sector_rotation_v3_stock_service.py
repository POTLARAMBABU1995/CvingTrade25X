from __future__ import annotations

import json
import logging
import math
import os
import re
import threading
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from cache import TTLCache
from db import get_oracle_connection
from services.nse_symbol_normalization import canonical_nse_symbol
from services.sector_rotation_v3_repository import read_latest_published_v3_snapshot
from services.strong_technicals_service import fetch_strong_technicals_universe


logger = logging.getLogger(__name__)

MODEL_VERSION = "SECTOR_ROTATION_V3_STOCK_STRENGTH_1"
SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[2]
    / "runtime"
    / "snapshots"
    / "sector_rotation_v3_stocks_latest.json"
)
SECTOR_TABLES_SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[2]
    / "runtime"
    / "snapshots"
    / "sector_rotation_tables.json"
)
SECTOR_OVERVIEW_SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[2]
    / "runtime"
    / "snapshots"
    / "sector_overview_latest.json"
)

_STOCK_LOOKUP_CACHE_TTL_SECONDS = max(
    1,
    int(os.getenv("SECTOR_ROTATION_V3_STOCK_LOOKUP_CACHE_TTL_SECONDS", "300")),
)
_STOCK_SNAPSHOT_CACHE = TTLCache(
    ttl_seconds=_STOCK_LOOKUP_CACHE_TTL_SECONDS,
    max_items=1,
)
_STOCK_SYMBOL_INDEX_CACHE = TTLCache(
    ttl_seconds=_STOCK_LOOKUP_CACHE_TTL_SECONDS,
    max_items=1,
)
_STOCK_SNAPSHOT_READ_LOCK = threading.Lock()
_STOCK_SYMBOL_INDEX_LOCK = threading.Lock()

FACTOR_WEIGHTS = {
    "relativeMomentum": 0.20,
    "emaTrend": 0.20,
    "momentumConfirmation": 0.15,
    "priceActionBreakout": 0.15,
    "volumeDelivery": 0.10,
    "multiTimeframe": 0.10,
    "riskQuality": 0.10,
}

SEVERE_WARNING_TOKENS = (
    "DATA_STALE",
    "STALE_DATA",
    "MAPPING_CONFLICT",
    "CORPORATE_ACTION",
    "SEVERE",
    "RUN_DATE_MISMATCH",
    "SOURCE_DATE_MISMATCH",
)


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(str(value).replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _round(value: float | None, digits: int = 2) -> float | None:
    return round(value, digits) if value is not None and math.isfinite(value) else None


def _date_key(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    token = str(value or "").strip()
    if not token:
        return ""
    if len(token) >= 10 and token[4:5] == "-" and token[7:8] == "-":
        return token[:10]
    if len(token) >= 10 and token[2:3] in {"-", "/"} and token[5:6] in {"-", "/"}:
        day, month, year = token[:10].replace("/", "-").split("-")
        return f"{year}-{month}-{day}"
    return token[:10]


def _token(value: Any) -> str:
    return str(value or "").strip().upper()


def _trend_label(trend_state: Any) -> str:
    """Expose the V3 state through the legacy table trend contract."""
    labels = {
        "STRONG_UPTREND": "Strong Uptrend",
        "UPTREND": "Uptrend",
        "DOWNTREND": "Downtrend",
        "SIDEWAYS": "Sideways",
        "DATA_WEAK": "Unknown / Insufficient Data",
    }
    return labels.get(_token(trend_state), "Unknown / Insufficient Data")


def _symbol(value: Any) -> str:
    canonical = canonical_nse_symbol(str(value or ""))
    return str(canonical or value or "").strip().upper()


def _snapshot_file_identity(path: Path) -> str:
    try:
        stat = path.stat()
    except (FileNotFoundError, OSError):
        return f"{path}:missing"
    return f"{path}:{stat.st_mtime_ns}:{stat.st_size}"


def _clear_stock_lookup_caches() -> None:
    _STOCK_SNAPSHOT_CACHE.clear()
    _STOCK_SYMBOL_INDEX_CACHE.clear()


def _warnings(row: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("riskWarnings", "warnings", "divergenceCodes"):
        current = row.get(key)
        if isinstance(current, Sequence) and not isinstance(current, (str, bytes)):
            values.extend(str(item).strip() for item in current if str(item).strip())
    return list(dict.fromkeys(values))


def evaluate_sector_v3_eligibility(
    row: Mapping[str, Any],
    snapshot_date: Any,
) -> dict[str, Any]:
    """Apply the published V3 Best Sectors gates without score-only shortcuts."""

    as_of_date = _date_key(snapshot_date)
    latest_data_date = _date_key(row.get("latestDataDate"))
    final_score = _number(row.get("finalRotationScore"))
    coverage = _number(row.get("coveragePercent"))
    data_quality = _number(row.get("dataQualityScore"))
    risk = _number(row.get("riskScore"))
    money_flow = _number(row.get("moneyFlowScore"))
    warning_values = _warnings(row)
    severe = [
        warning
        for warning in warning_values
        if any(token in _token(warning) for token in SEVERE_WARNING_TOKENS)
    ]

    gates = {
        "score": final_score is not None and final_score >= 70,
        "band": _token(row.get("rotationBand")) in {"STRONG", "VERY_STRONG"},
        "phase": _token(row.get("rotationPhase")) in {"LEADING", "IMPROVING"},
        "confidence": _token(row.get("confidence")) == "HIGH",
        "coverage": coverage is not None and coverage >= 85,
        "dataQuality": data_quality is not None and data_quality >= 80,
        "risk": risk is not None and risk >= 60,
        "currentDate": bool(as_of_date) and latest_data_date == as_of_date,
        "moneyFlow": money_flow is not None and money_flow >= 50,
        "severeWarnings": not severe,
    }
    failed = [name for name, passed in gates.items() if not passed]
    return {
        "eligible": not failed,
        "gates": gates,
        "failedGates": failed,
        "severeWarnings": severe,
    }


def _weighted_return(row: Mapping[str, Any]) -> float | None:
    horizons = (
        (_number(row.get("return21")), 0.30),
        (_number(row.get("return63")), 0.40),
        (_number(row.get("return126")), 0.30),
    )
    available = [(value, weight) for value, weight in horizons if value is not None]
    if len(available) < 2:
        return None
    total_weight = sum(weight for _, weight in available)
    return sum(value * weight for value, weight in available) / total_weight


def _percentiles(rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    ranked = sorted(
        (
            (_weighted_return(row), _symbol(row.get("symbol") or row.get("stock")))
            for row in rows
        ),
        key=lambda item: ((item[0] is None), item[0] if item[0] is not None else 0.0, item[1]),
    )
    valid = [(value, symbol) for value, symbol in ranked if value is not None and symbol]
    if not valid:
        return {}
    if len(valid) == 1:
        return {valid[0][1]: 50.0}
    return {
        symbol: round(index * 100.0 / (len(valid) - 1), 2)
        for index, (_, symbol) in enumerate(valid)
    }


def _average(values: Sequence[float | None]) -> float | None:
    available = [value for value in values if value is not None]
    return sum(available) / len(available) if available else None


def _ema_factor(row: Mapping[str, Any]) -> float | None:
    price = _number(row.get("price"))
    ema20 = _number(row.get("ema20"))
    ema50 = _number(row.get("ema50"))
    ema100 = _number(row.get("ema100"))
    ema200 = _number(row.get("ema200"))
    if price is None or ema200 is None:
        return None
    checks = (
        ema20 is not None and price > ema20,
        ema50 is not None and price > ema50,
        ema100 is not None and price > ema100,
        price > ema200,
        ema20 is not None and ema50 is not None and ema20 > ema50,
        ema50 is not None and ema100 is not None and ema50 > ema100,
        ema100 is not None and ema100 > ema200,
    )
    return sum(1 for passed in checks if passed) * 100.0 / len(checks)


def _momentum_factor(row: Mapping[str, Any]) -> float | None:
    rsi = _number(row.get("rsi"))
    macd = _number(row.get("macd"))
    hist = _number(row.get("macdHist"))
    adx = _number(row.get("adx14"))
    values: list[float | None] = [
        None if rsi is None else min(100.0, max(0.0, (rsi - 30.0) * 2.5)),
        None if macd is None else (100.0 if macd > 0 else 20.0),
        None if hist is None else (100.0 if hist >= 0 else 20.0),
        None if adx is None else min(100.0, max(0.0, adx * 2.5)),
    ]
    return _average(values)


def _price_action_factor(row: Mapping[str, Any]) -> float | None:
    return _average(
        (
            _number(row.get("priceActionScore")),
            _number(row.get("breakoutScore")),
            _number(row.get("trendlineScore")),
        )
    )


def _volume_delivery_factor(row: Mapping[str, Any]) -> float | None:
    ratio = _number(row.get("volumeRatio"))
    volume_score = None
    if ratio is not None:
        volume_score = 100.0 if ratio >= 2 else 85.0 if ratio >= 1.5 else 70.0 if ratio >= 1.2 else 50.0 if ratio >= 1 else 25.0
    return _average((volume_score, _number(row.get("deliveryScore"))))


def _factor_scores(row: Mapping[str, Any], relative_momentum: float | None) -> dict[str, float | None]:
    return {
        "relativeMomentum": relative_momentum,
        "emaTrend": _ema_factor(row),
        "momentumConfirmation": _momentum_factor(row),
        "priceActionBreakout": _price_action_factor(row),
        "volumeDelivery": _volume_delivery_factor(row),
        "multiTimeframe": _number(row.get("multiTimeframeScore")),
        "riskQuality": _number(row.get("riskQualityScore")),
    }


def _risk_is_acceptable(row: Mapping[str, Any]) -> bool:
    return _token(row.get("riskLevel") or row.get("riskStatus")) not in {
        "HIGH",
        "EXTREME",
        "HIGH RISK",
        "EXTREME RISK",
    }


def _ema_alignment_trend_state(row: Mapping[str, Any]) -> str | None:
    """Return the direction implied by the four displayed EMA flags."""
    price = _number(row.get("price"))
    ema_values = tuple(_number(row.get(key)) for key in ("ema20", "ema50", "ema100", "ema200"))
    if price is None or any(value is None for value in ema_values):
        return None

    bullish_count = sum(price > value for value in ema_values if value is not None)
    if bullish_count == 4:
        return "STRONG_UPTREND"
    if bullish_count == 3:
        return "UPTREND"
    if bullish_count == 2:
        return "SIDEWAYS"
    return "DOWNTREND"


def _classify_trend_state(
    row: Mapping[str, Any],
    *,
    edge_score: float,
    factor_coverage: float,
    relative_momentum: float | None,
    confidence: str,
    parent_eligible: bool,
    as_of_date: str,
) -> tuple[str, list[str], list[str]]:
    price = _number(row.get("price"))
    ema20 = _number(row.get("ema20"))
    ema50 = _number(row.get("ema50"))
    ema100 = _number(row.get("ema100"))
    ema200 = _number(row.get("ema200"))
    rsi = _number(row.get("rsi"))
    macd = _number(row.get("macd"))
    hist = _number(row.get("macdHist"))
    adx = _number(row.get("adx14"))
    volume_ratio = _number(row.get("volumeRatio"))
    delivery = _number(row.get("deliveryScore"))
    atr = _number(row.get("atr14"))
    td = _number(row.get("td"))
    support = _number(row.get("support") or row.get("nearestSupport"))
    price_action_score = _number(row.get("priceActionScore"))
    breakout_score = _number(row.get("breakoutScore"))
    trendline_score = _number(row.get("trendlineScore"))
    chart_pattern_score = _number(row.get("chartPatternScore"))
    technical_score = _number(row.get("techScore") or row.get("score"))
    market_cap = _number(row.get("totalMcap") or row.get("mcap") or row.get("MCAP"))
    free_float_mcap = _number(row.get("ffmc") or row.get("ffmcCr") or row.get("FFMC_CR"))
    stock_date = _date_key(row.get("ltcDate"))
    warnings: list[str] = []
    reasons: list[str] = []

    current = bool(stock_date) and stock_date == as_of_date
    inadequate = (
        not current
        or price is None
        or ema200 is None
        or td is None
        or td < 200
        or factor_coverage < 0.70
    )
    ema_alignment_state = _ema_alignment_trend_state(row)
    if inadequate and ema_alignment_state is None:
        if not current:
            warnings.append("DATA_STALE")
        if price is None:
            warnings.append("PRICE_MISSING")
        if ema200 is None:
            warnings.append("EMA200_MISSING")
        if td is None or td < 200:
            warnings.append("HISTORY_INADEQUATE")
        if factor_coverage < 0.70:
            warnings.append("CORE_FACTOR_COVERAGE_LOW")
        return "DATA_WEAK", reasons, warnings

    bullish_flags = (
        ema20 is not None and price > ema20,
        ema50 is not None and price > ema50,
        ema100 is not None and price > ema100,
        price > ema200,
    )
    bullish_count = sum(1 for passed in bullish_flags if passed)
    strong_stack = bool(
        ema20 is not None
        and ema50 is not None
        and ema100 is not None
        and price > ema20 > ema50 > ema100 > ema200
    )
    volume_confirmed = bool(
        (volume_ratio is not None and volume_ratio >= 1.2)
        or (delivery is not None and delivery >= 60)
    )
    pullback = bool(ema20 is not None and ema50 is not None and price <= ema20 and price > ema50)
    acceptable_risk = _risk_is_acceptable(row)
    price_action_labels = " ".join(str(label) for label in (row.get("priceActionLabels") or ())).upper()
    trendline_status = _token(row.get("trendlineStatus"))
    breakout_status = _token(row.get("breakoutStatus"))
    pattern_status = _token(row.get("patternStatus"))
    pattern_name = _token(row.get("patternName"))
    positive_price_action = bool(
        (price_action_score is not None and price_action_score >= 60)
        or "HIGHER HIGH" in price_action_labels
        or "HIGHER LOW" in price_action_labels
    )
    positive_breakout = bool(
        (breakout_score is not None and breakout_score >= 60)
        or ("BREAKOUT" in breakout_status and "FAILED" not in breakout_status)
    )
    positive_trendline = bool(
        (trendline_score is not None and trendline_score >= 60)
        or trendline_status in {"STRONG SUPPORT TRENDLINE", "NEAR TRENDLINE SUPPORT"}
    )
    positive_pattern = bool(
        (chart_pattern_score is not None and chart_pattern_score >= 60)
        or (pattern_name not in {"", "-"} and pattern_status in {"CONFIRMED", "DETECTED"})
    )
    strong_technicals = bool(
        (technical_score is not None and technical_score >= 70)
        or _token(row.get("techStatus")) in {"VERY STRONG TECHNICALS", "STRONG TECHNICALS"}
    )
    atr_available = atr is not None or _token(row.get("atrGt14")) in {"Y", "N"}
    atr_supportive = not atr_available or (atr is not None and atr > 0) or _token(row.get("atrGt14")) == "Y"
    sr_intact = support is None or price >= support
    liquidity_confirmed = market_cap is not None and market_cap > 0 and (free_float_mcap is None or free_float_mcap > 0)

    if ema_alignment_state == "STRONG_UPTREND":
        if (
            confidence == "HIGH"
            and strong_stack
            and rsi is not None
            and rsi >= 55
            and macd is not None
            and macd > 0
            and hist is not None
            and hist >= 0
            and adx is not None
            and adx >= 25
            and volume_confirmed
            and acceptable_risk
            and positive_price_action
            and (positive_breakout or positive_trendline or positive_pattern)
            and strong_technicals
            and atr_supportive
            and sr_intact
            and liquidity_confirmed
        ):
            reasons.extend(("EMA_ALIGNMENT_4Y_0N", "EMA_FULL_BULLISH_STACK", "MOMENTUM_CONFIRMED", "PRICE_ACTION_CONFIRMED", "SR_TRENDLINE_PATTERN_CONFIRMED", "VOLUME20_DELIVERY_CONFIRMED", "ATR_RISK_CONFIRMED", "STRONG_TECHNICALS_CONFIRMED", "MCAP_FFMC_LIQUIDITY_CONFIRMED"))
            return "STRONG_UPTREND", reasons, warnings
        reasons.append("EMA_ALIGNMENT_4Y_0N_UNCONFIRMED")
        return "UPTREND", reasons, warnings

    if ema_alignment_state == "UPTREND":
        if pullback:
            warnings.append("EMA20_PULLBACK")
        reasons.append("EMA_ALIGNMENT_3Y_1N")
        return "UPTREND", reasons, warnings

    if ema_alignment_state == "SIDEWAYS":
        reasons.append("EMA_ALIGNMENT_2Y_2N")
        return "SIDEWAYS", reasons, warnings

    if ema_alignment_state == "DOWNTREND":
        reasons.append(f"EMA_ALIGNMENT_{bullish_count}Y_{4 - bullish_count}N")
        return "DOWNTREND", reasons, warnings

    if (
        parent_eligible
        and edge_score >= 80
        and confidence == "HIGH"
        and strong_stack
        and rsi is not None
        and rsi >= 55
        and macd is not None
        and macd > 0
        and hist is not None
        and hist >= 0
        and adx is not None
        and adx >= 25
        and volume_confirmed
        and acceptable_risk
    ):
        reasons.extend(("PARENT_SECTOR_ELIGIBLE", "EMA_FULL_BULLISH_STACK", "MOMENTUM_CONFIRMED", "PARTICIPATION_CONFIRMED"))
        return "STRONG_UPTREND", reasons, warnings

    if (
        edge_score >= 65
        and ema50 is not None
        and ema100 is not None
        and price > ema50
        and price > ema100
        and price > ema200
        and bullish_count >= 3
        and rsi is not None
        and rsi >= 50
        and adx is not None
        and adx >= 20
        and acceptable_risk
    ):
        reasons.extend(("EMA_TREND_BULLISH", "UPTREND_MOMENTUM_ACCEPTABLE"))
        if pullback:
            warnings.append("EMA20_PULLBACK")
        return "UPTREND", reasons, warnings

    bearish_structure = bool(
        ema50 is not None
        and ema100 is not None
        and price < ema50 < ema100 < ema200
        and relative_momentum is not None
        and relative_momentum < 40
    )
    support_break = support is not None and price < support
    if bearish_structure or support_break:
        reasons.append("BEARISH_EMA_STRUCTURE" if bearish_structure else "SUPPORT_BREAKDOWN")
        return "DOWNTREND", reasons, warnings

    if adx is not None and adx < 20:
        reasons.append("ADX_RANGE_BOUND")
    else:
        reasons.append("MIXED_TECHNICAL_STRUCTURE")
    return "SIDEWAYS", reasons, warnings


def _stock_edge_band(score: float) -> str:
    if score >= 80:
        return "VERY_STRONG"
    if score >= 65:
        return "STRONG"
    if score >= 50:
        return "NEUTRAL"
    if score >= 35:
        return "WEAK"
    return "VERY_WEAK"


def build_sector_rotation_v3_stock_snapshot(
    parent_envelope: Mapping[str, Any],
    technical_rows: Sequence[Mapping[str, Any]],
    memberships: Mapping[str, Sequence[str]],
    *,
    technical_source_date: Any,
) -> dict[str, Any]:
    run_id = str(parent_envelope.get("runId") or "").strip()
    as_of_date = _date_key(parent_envelope.get("asOfDate"))
    technical_date = _date_key(technical_source_date)
    if not run_id or not as_of_date:
        raise ValueError("Published parent V3 runId and asOfDate are required")
    if technical_date and technical_date > as_of_date:
        raise ValueError("Technical source date is later than the parent V3 asOfDate")

    parent_rows = {
        _token(row.get("sectorCode")): row
        for row in parent_envelope.get("rows", [])
        if isinstance(row, Mapping) and _token(row.get("sectorCode"))
    }
    rows_by_sector: dict[str, list[Mapping[str, Any]]] = {code: [] for code in parent_rows}
    for technical_row in technical_rows:
        symbol = _symbol(technical_row.get("symbol") or technical_row.get("stock"))
        for sector_code in memberships.get(symbol, ()):
            code = _token(sector_code)
            if code in rows_by_sector:
                rows_by_sector[code].append(technical_row)

    sectors: dict[str, dict[str, Any]] = {}
    for sector_code, parent in parent_rows.items():
        eligibility = evaluate_sector_v3_eligibility(parent, as_of_date)
        source_rows = rows_by_sector.get(sector_code, [])
        relative_percentiles = _percentiles(source_rows)
        stock_rows: list[dict[str, Any]] = []
        for source in source_rows:
            symbol = _symbol(source.get("symbol") or source.get("stock"))
            relative_momentum = relative_percentiles.get(symbol)
            factors = _factor_scores(source, relative_momentum)
            factor_coverage = sum(value is not None for value in factors.values()) / len(FACTOR_WEIGHTS)
            edge_score = sum((factors.get(name) or 0.0) * weight for name, weight in FACTOR_WEIGHTS.items())
            row_date = _date_key(source.get("ltcDate"))
            confidence = (
                "HIGH"
                if factor_coverage >= 0.85 and row_date == as_of_date and (_number(source.get("td")) or 0) >= 200
                else "MEDIUM"
                if factor_coverage >= 0.70
                else "LOW"
            )
            trend_state, reasons, warnings = _classify_trend_state(
                source,
                edge_score=edge_score,
                factor_coverage=factor_coverage,
                relative_momentum=relative_momentum,
                confidence=confidence,
                parent_eligible=bool(eligibility["eligible"]),
                as_of_date=as_of_date,
            )
            if not eligibility["eligible"]:
                warnings.append("PARENT_SECTOR_INELIGIBLE")
            stock_rows.append(
                {
                    **dict(source),
                    "version": "v3",
                    "modelVersion": MODEL_VERSION,
                    "runId": run_id,
                    "asOfDate": as_of_date,
                    "technicalSourceDate": technical_date or None,
                    "sectorCode": sector_code,
                    "sectorName": parent.get("sectorName") or sector_code,
                    "stock": symbol,
                    "symbol": symbol,
                    "stockEdgeScore": _round(edge_score),
                    "stockEdgeBand": _stock_edge_band(edge_score),
                    "trendState": trend_state,
                    "trend": _trend_label(trend_state),
                    "trendDirection": _trend_label(trend_state),
                    "confidence": confidence,
                    "coverage": _round(factor_coverage * 100.0),
                    "factorScores": {key: _round(value) for key, value in factors.items()},
                    "relativeMomentumScore": _round(relative_momentum),
                    "returnMomentumRaw": _round(_weighted_return(source)),
                    "reasonCodes": list(dict.fromkeys(reasons)),
                    "warnings": list(dict.fromkeys(warnings)),
                    "parentSectorEligible": bool(eligibility["eligible"]),
                    "parentSectorScore": _round(_number(parent.get("finalRotationScore"))),
                    "parentSectorBand": parent.get("rotationBand"),
                    "parentSectorPhase": parent.get("rotationPhase"),
                    "parentSectorConfidence": parent.get("confidence"),
                    "parentFailedGates": eligibility["failedGates"],
                }
            )
        stock_rows.sort(
            key=lambda row: (
                -(_number(row.get("stockEdgeScore")) or 0.0),
                str(row.get("symbol") or ""),
            )
        )
        for index, row in enumerate(stock_rows, 1):
            row["sNo"] = index
        sectors[sector_code] = {
            "sectorCode": sector_code,
            "sectorName": parent.get("sectorName") or sector_code,
            "parent": {
                "runId": run_id,
                "asOfDate": as_of_date,
                "score": parent.get("finalRotationScore"),
                "band": parent.get("rotationBand"),
                "phase": parent.get("rotationPhase"),
                "confidence": parent.get("confidence"),
                **eligibility,
            },
            "rows": stock_rows,
            "totalRows": len(stock_rows),
        }

    return {
        "ok": True,
        "status": "success",
        "version": "v3",
        "modelVersion": MODEL_VERSION,
        "runId": run_id,
        "asOfDate": as_of_date,
        "technicalSourceDate": technical_date or None,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "factorWeights": FACTOR_WEIGHTS,
        "sectors": sectors,
        "sectorCount": len(sectors),
        "stockCount": sum(int(sector.get("totalRows") or 0) for sector in sectors.values()),
    }


def _load_memberships() -> dict[str, list[str]]:
    conn = get_oracle_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT UPPER(TRIM(symbol)), UPPER(TRIM(sector_code))
                FROM nse_symbol_sector_map
                WHERE symbol IS NOT NULL
                  AND sector_code IS NOT NULL
                """
            )
            result: dict[str, list[str]] = {}
            for raw_symbol, raw_sector in cursor.fetchall():
                symbol = _symbol(raw_symbol)
                sector_code = _token(raw_sector)
                if symbol and sector_code:
                    result.setdefault(symbol, []).append(sector_code)
            return {symbol: list(dict.fromkeys(codes)) for symbol, codes in result.items()}
    finally:
        conn.close()


def _sector_code_from_staging_table(table_name: Any) -> str:
    token = _token(table_name)
    if token.startswith("NSE_NIFTY_") and token.endswith("_STAGING"):
        return token[10:-8]
    if token.startswith("NSE_NIFTY500_") and token.endswith("_STAGING"):
        return f"NIFTY500_{token[13:-8]}"
    return ""


def _supplement_memberships_from_staging(
    memberships: dict[str, list[str]],
    *,
    sector_codes: Sequence[str] | None = None,
) -> dict[str, list[str]]:
    """Fill incomplete map membership from the read-only canonical staging snapshot.

    The map is normally synchronized from staging, but a failed sync must not
    publish a V3 stock snapshot with a smaller universe than Sector Rotation.
    """
    try:
        snapshot = json.loads(SECTOR_TABLES_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return memberships
    except (OSError, ValueError, json.JSONDecodeError):
        logger.exception("sector_rotation_v3_staging_snapshot_read_failed path=%s", SECTOR_TABLES_SNAPSHOT_PATH)
        return memberships

    tables = snapshot.get("tables") if isinstance(snapshot, Mapping) else None
    if not isinstance(tables, list):
        return memberships

    requested_codes = {_token(code) for code in (sector_codes or ()) if _token(code)}
    result = {symbol: list(dict.fromkeys(codes)) for symbol, codes in memberships.items()}
    pending: list[tuple[str, str, int]] = []
    for entry in tables:
        if not isinstance(entry, Mapping):
            continue
        table_name = _token(entry.get("tableName") or entry.get("table_name"))
        sector_code = _token(entry.get("sectorCode")) or _sector_code_from_staging_table(table_name)
        if requested_codes and sector_code not in requested_codes:
            continue
        expected_count = int(_number(entry.get("stockCount")) or 0)
        if not table_name or not sector_code or expected_count <= 0:
            continue
        if not re.fullmatch(r"[A-Z][A-Z0-9_$#]*", table_name):
            continue
        mapped_count = sum(1 for codes in result.values() if sector_code in codes)
        if mapped_count < expected_count:
            pending.append((table_name, sector_code, expected_count))

    if not pending:
        return result

    conn = get_oracle_connection()
    try:
        with conn.cursor() as cursor:
            cursor.arraysize = 1000
            for table_name, sector_code, expected_count in pending:
                cursor.execute(
                    f"""
                    SELECT DISTINCT UPPER(TRIM(symbol))
                    FROM {table_name}
                    WHERE symbol IS NOT NULL
                      AND TRIM(symbol) IS NOT NULL
                    """
                )
                staged_symbols = {
                    _symbol(row[0])
                    for row in (cursor.fetchall() or [])
                    if row and _symbol(row[0])
                }
                for symbol in staged_symbols:
                    codes = result.setdefault(symbol, [])
                    if sector_code not in codes:
                        codes.append(sector_code)
                logger.warning(
                    "sector_rotation_v3_staging_membership_backfill sector=%s table=%s map_expected=%s staged=%s",
                    sector_code,
                    table_name,
                    expected_count,
                    len(staged_symbols),
                )
    finally:
        conn.close()

    return result


def _load_technical_universe() -> tuple[list[dict[str, Any]], str]:
    payload = fetch_strong_technicals_universe(
        required_fields=("return21", "return63", "return126"),
    )
    rows = [dict(row) for row in payload.get("rows", []) if isinstance(row, Mapping)]
    source_date = _date_key((payload.get("meta") or {}).get("latestTradingDate"))
    return rows, source_date


def _unavailable_membership_row(symbol: str, sector_code: str, sector_name: str) -> dict[str, Any]:
    """Expose a canonical sector member without inventing technical values."""
    return {
        "symbol": symbol,
        "stock": symbol,
        "sectorCode": sector_code,
        "sectorName": sector_name,
        "trendState": "DATA_WEAK",
        "trend": _trend_label("DATA_WEAK"),
        "trendDirection": _trend_label("DATA_WEAK"),
        "confidence": "LOW",
        "stockEdgeScore": 0.0,
        "score": 0.0,
        "warnings": ["TECHNICAL_ROW_UNAVAILABLE"],
    }


def _overview_rows_by_symbol() -> dict[str, dict[str, Any]]:
    """Read the compact overview snapshot without triggering a live recompute."""
    try:
        payload = json.loads(SECTOR_OVERVIEW_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
        return {}
    return {
        _symbol(row.get("stock") or row.get("symbol")): dict(row)
        for row in payload.get("rows", [])
        if isinstance(row, Mapping) and _symbol(row.get("stock") or row.get("symbol"))
    } if isinstance(payload, Mapping) else {}


def _overview_membership_row(
    symbol: str,
    sector_code: str,
    sector_name: str,
    overview_row: Mapping[str, Any] | None,
) -> dict[str, Any]:
    row = _unavailable_membership_row(symbol, sector_code, sector_name)
    return _apply_overview_trend(row, overview_row)


def _apply_overview_trend(row: dict[str, Any], overview_row: Mapping[str, Any] | None) -> dict[str, Any]:
    """Use the Overview's resolved trend only when V3 lacks a technical row."""
    trend = str((overview_row or {}).get("trend") or "").strip()
    if not trend or trend == "Unknown / Insufficient Data":
        return row
    trend_state = {
        "STRONG UPTREND": "STRONG_UPTREND",
        "UPTREND": "UPTREND",
        "DOWNTREND": "DOWNTREND",
        "SIDEWAY": "SIDEWAYS",
        "SIDEWAYS": "SIDEWAYS",
    }.get(_token(trend).replace("_", " "), "DATA_WEAK")
    row.update({
        "price": (overview_row or {}).get("price"),
        "ltcDate": (overview_row or {}).get("ltc_date"),
        "trendState": trend_state,
        "trend": trend,
        "trendDirection": trend,
        "warnings": list(dict.fromkeys([
            *(row.get("warnings") or []),
            "OVERVIEW_TREND_FALLBACK",
        ])),
    })
    return row


def publish_sector_rotation_v3_stock_snapshot(payload: Mapping[str, Any]) -> Path:
    if not payload.get("runId") or not payload.get("asOfDate") or not payload.get("sectors"):
        raise ValueError("A complete V3 stock snapshot is required")
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = SNAPSHOT_PATH.with_suffix(f"{SNAPSHOT_PATH.suffix}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str),
            encoding="utf-8",
        )
        os.replace(temporary, SNAPSHOT_PATH)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    _clear_stock_lookup_caches()
    return SNAPSHOT_PATH


def refresh_sector_rotation_v3_stock_snapshot(
    parent_envelope: Mapping[str, Any],
) -> dict[str, Any]:
    technical_rows, technical_source_date = _load_technical_universe()
    memberships = _supplement_memberships_from_staging(_load_memberships())
    payload = build_sector_rotation_v3_stock_snapshot(
        parent_envelope,
        technical_rows,
        memberships,
        technical_source_date=technical_source_date,
    )
    publish_sector_rotation_v3_stock_snapshot(payload)
    logger.info(
        "sector_rotation_v3_stock_snapshot_published run_id=%s as_of_date=%s technical_source_date=%s sectors=%s stocks=%s",
        payload.get("runId"),
        payload.get("asOfDate"),
        payload.get("technicalSourceDate"),
        payload.get("sectorCount"),
        payload.get("stockCount"),
    )
    return payload


def read_sector_rotation_v3_stock_snapshot() -> dict[str, Any] | None:
    for attempt in range(2):
        identity_before = _snapshot_file_identity(SNAPSHOT_PATH)
        cached = _STOCK_SNAPSHOT_CACHE.get(identity_before)
        if isinstance(cached, dict):
            return cached

        with _STOCK_SNAPSHOT_READ_LOCK:
            identity_before = _snapshot_file_identity(SNAPSHOT_PATH)
            cached = _STOCK_SNAPSHOT_CACHE.get(identity_before)
            if isinstance(cached, dict):
                return cached
            try:
                payload = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
            except FileNotFoundError:
                return None
            except (OSError, ValueError, json.JSONDecodeError):
                logger.exception("sector_rotation_v3_stock_snapshot_read_failed path=%s", SNAPSHOT_PATH)
                return None

            identity_after = _snapshot_file_identity(SNAPSHOT_PATH)
            if identity_before != identity_after and attempt == 0:
                continue
            if not isinstance(payload, dict):
                return None
            _STOCK_SNAPSHOT_CACHE.set(identity_after, payload)
            return payload
    return None


def _reconcile_published_stock_rows(
    rows: list[dict[str, Any]],
    snapshot: Mapping[str, Any],
    overview_rows: Mapping[str, Mapping[str, Any]],
) -> None:
    for row in rows:
        ema_alignment_state = _ema_alignment_trend_state(row)
        if ema_alignment_state is not None:
            coverage = _number(row.get("coverage"))
            trend_state, reasons, warnings = _classify_trend_state(
                row,
                edge_score=_number(row.get("stockEdgeScore")) or 0.0,
                factor_coverage=(coverage / 100.0) if coverage is not None else 0.0,
                relative_momentum=_number(row.get("relativeMomentumScore")),
                confidence=_token(row.get("confidence")),
                parent_eligible=bool(row.get("parentSectorEligible")),
                as_of_date=_date_key(snapshot.get("asOfDate")),
            )
            row["trendState"] = trend_state
            row["trend"] = _trend_label(trend_state)
            row["trendDirection"] = _trend_label(trend_state)
            row["reasonCodes"] = list(dict.fromkeys(reasons))
            row["warnings"] = list(dict.fromkeys([*(row.get("warnings") or []), *warnings]))
        elif _token(row.get("trendState")) == "DATA_WEAK":
            _apply_overview_trend(
                row,
                overview_rows.get(_symbol(row.get("symbol") or row.get("stock"))),
            )


def _normalize_published_trend_fields(rows: Sequence[dict[str, Any]]) -> None:
    for row in rows:
        if "OVERVIEW_TREND_FALLBACK" in (row.get("warnings") or []):
            continue
        trend_state = row.get("trendState")
        if _token(trend_state):
            row["trend"] = _trend_label(trend_state)
            row["trendDirection"] = _trend_label(trend_state)


def _stock_symbol_index_cache_key(
    snapshot: Mapping[str, Any],
    parent: Mapping[str, Any],
) -> str:
    return "|".join((
        _snapshot_file_identity(SNAPSHOT_PATH),
        f"snapshot-object:{id(snapshot)}",
        f"stock-run:{snapshot.get('runId') or ''}",
        f"stock-date:{_date_key(snapshot.get('asOfDate'))}",
        f"parent-run:{parent.get('runId') or ''}",
        f"parent-date:{_date_key(parent.get('asOfDate'))}",
        _snapshot_file_identity(SECTOR_TABLES_SNAPSHOT_PATH),
        _snapshot_file_identity(SECTOR_OVERVIEW_SNAPSHOT_PATH),
    ))


def _build_stock_symbol_index(snapshot: Mapping[str, Any]) -> dict[str, tuple[dict[str, Any], ...]]:
    sectors = snapshot.get("sectors")
    if not isinstance(sectors, Mapping):
        return {}

    overview_rows = _overview_rows_by_symbol()
    rows_by_symbol: dict[str, list[dict[str, Any]]] = {}
    sector_metadata: dict[str, Mapping[str, Any]] = {}
    existing_pairs: set[tuple[str, str]] = set()

    for raw_code, sector in sectors.items():
        if not isinstance(sector, Mapping):
            continue
        code = _token(raw_code)
        if not code:
            continue
        sector_metadata[code] = sector
        sector_rows = [
            {
                **dict(row),
                "sectorCode": code,
                "sectorName": sector.get("sectorName") or code,
                "parent": sector.get("parent"),
            }
            for row in (sector.get("rows") or [])
            if isinstance(row, Mapping)
        ]
        _reconcile_published_stock_rows(sector_rows, snapshot, overview_rows)
        _normalize_published_trend_fields(sector_rows)
        for row in sector_rows:
            symbol = _symbol(row.get("symbol") or row.get("stock"))
            if not symbol:
                continue
            existing_pairs.add((symbol, code))
            rows_by_symbol.setdefault(symbol, []).append(row)

    try:
        memberships = _supplement_memberships_from_staging(
            {},
            sector_codes=list(sector_metadata),
        )
    except Exception:
        logger.warning(
            "sector_rotation_v3_stock_symbol_membership_supplement_failed",
            exc_info=True,
        )
        memberships = {}

    for symbol, codes in memberships.items():
        normalized_symbol = _symbol(symbol)
        if not normalized_symbol:
            continue
        for raw_code in codes:
            code = _token(raw_code)
            sector = sector_metadata.get(code)
            if sector is None or (normalized_symbol, code) in existing_pairs:
                continue
            row = _overview_membership_row(
                normalized_symbol,
                code,
                str(sector.get("sectorName") or code),
                overview_rows.get(normalized_symbol),
            )
            rows_by_symbol.setdefault(normalized_symbol, []).append(row)
            existing_pairs.add((normalized_symbol, code))

    return {
        symbol: tuple(rows)
        for symbol, rows in rows_by_symbol.items()
    }


def _get_stock_symbol_index(
    snapshot: Mapping[str, Any],
    parent: Mapping[str, Any],
) -> Mapping[str, tuple[dict[str, Any], ...]]:
    cache_key = _stock_symbol_index_cache_key(snapshot, parent)
    cached = _STOCK_SYMBOL_INDEX_CACHE.get(cache_key)
    if isinstance(cached, Mapping):
        return cached

    with _STOCK_SYMBOL_INDEX_LOCK:
        cached = _STOCK_SYMBOL_INDEX_CACHE.get(cache_key)
        if isinstance(cached, Mapping):
            return cached
        index = _build_stock_symbol_index(snapshot)
        _STOCK_SYMBOL_INDEX_CACHE.set(cache_key, index)
        return index


def _published_symbol_matches(
    snapshot: Mapping[str, Any],
    target: str,
) -> list[dict[str, Any]]:
    sectors = snapshot.get("sectors")
    if not isinstance(sectors, Mapping):
        return []
    matches: list[dict[str, Any]] = []
    for raw_code, sector in sectors.items():
        if not isinstance(sector, Mapping):
            continue
        code = _token(raw_code)
        for raw_row in sector.get("rows") or []:
            if not isinstance(raw_row, Mapping):
                continue
            if _symbol(raw_row.get("symbol") or raw_row.get("stock")) != target:
                continue
            matches.append({
                **dict(raw_row),
                "sectorCode": code,
                "sectorName": sector.get("sectorName") or code,
                "parent": sector.get("parent"),
            })
    return matches


def _overlay_current_parent_fields(
    matches: Sequence[dict[str, Any]],
    parent: Mapping[str, Any],
) -> None:
    parent_rows = {
        _token(row.get("sectorCode")): row
        for row in parent.get("rows") or []
        if isinstance(row, Mapping) and _token(row.get("sectorCode"))
    }
    for row in matches:
        current = parent_rows.get(_token(row.get("sectorCode")))
        if not isinstance(current, Mapping):
            continue
        existing_parent = row.get("parent") if isinstance(row.get("parent"), Mapping) else {}
        current_score = _number(current.get("finalRotationScore"))
        resolved_score = (
            _round(current_score)
            if current_score is not None
            else row.get("parentSectorScore", existing_parent.get("score"))
        )
        resolved_band = (
            current.get("rotationBand")
            or row.get("parentSectorBand")
            or existing_parent.get("band")
        )
        resolved_phase = (
            current.get("rotationPhase")
            or row.get("parentSectorPhase")
            or existing_parent.get("phase")
        )
        resolved_confidence = (
            current.get("confidence")
            or row.get("parentSectorConfidence")
            or existing_parent.get("confidence")
        )
        row["sectorName"] = current.get("sectorName") or row.get("sectorName")
        row["parentSectorScore"] = resolved_score
        row["parentSectorBand"] = resolved_band
        row["parentSectorPhase"] = resolved_phase
        row["parentSectorConfidence"] = resolved_confidence
        row["parent"] = {
            "runId": parent.get("runId"),
            "asOfDate": parent.get("asOfDate"),
            "score": resolved_score,
            "band": resolved_band,
            "phase": resolved_phase,
            "confidence": resolved_confidence,
        }


def get_sector_rotation_v3_stock_page(
    sector_code: str,
    *,
    page: int,
    page_size: int,
    search: str = "",
    sort_key: str = "STOCK_EDGE_SCORE",
    sort_dir: str = "DESC",
) -> tuple[dict[str, Any], int]:
    snapshot = read_sector_rotation_v3_stock_snapshot()
    parent = read_latest_published_v3_snapshot()
    if not snapshot or not parent:
        return {
            "ok": False,
            "status": "unavailable",
            "version": "v3",
            "error": "Published V3 sector and stock snapshots are required.",
            "reason": "V3_SNAPSHOT_UNAVAILABLE",
        }, 503
    same_as_of_date = _date_key(snapshot.get("asOfDate")) == _date_key(parent.get("asOfDate"))
    if not same_as_of_date:
        return {
            "ok": False,
            "status": "unavailable",
            "version": "v3",
            "error": "V3 sector and stock snapshots do not share the same run and date.",
            "reason": "V3_RUN_DATE_MISMATCH",
            "runId": snapshot.get("runId"),
            "asOfDate": snapshot.get("asOfDate"),
            "parentRunId": parent.get("runId"),
            "parentAsOfDate": parent.get("asOfDate"),
        }, 503

    code = _token(sector_code)
    sector = (snapshot.get("sectors") or {}).get(code)
    if not isinstance(sector, Mapping):
        return {
            "ok": False,
            "status": "unavailable",
            "version": "v3",
            "error": f"No published V3 stock snapshot exists for sector {code}.",
            "reason": "V3_SECTOR_NOT_FOUND",
        }, 404

    rows = [dict(row) for row in sector.get("rows", []) if isinstance(row, Mapping)]
    overview_rows = _overview_rows_by_symbol()
    _reconcile_published_stock_rows(rows, snapshot, overview_rows)
    # A reference-map sync can fail after sector discovery. Resolve just this
    # page's canonical staging membership so the UI does not hide constituents
    # while the costly full technical snapshot refresh is pending.
    memberships = _supplement_memberships_from_staging(
        {},
        sector_codes=[code],
    )
    existing_symbols = {_symbol(row.get("symbol") or row.get("stock")) for row in rows}
    sector_name = str(sector.get("sectorName") or code)
    rows.extend(
        _overview_membership_row(symbol, code, sector_name, overview_rows.get(symbol))
        for symbol, codes in memberships.items()
        if code in codes and symbol not in existing_symbols
    )
    _normalize_published_trend_fields(rows)
    search_token = _token(search)
    if search_token:
        rows = [row for row in rows if search_token in _token(row.get("symbol") or row.get("stock"))]
    sort_fields = {
        "STOCK": "symbol",
        "SYMBOL": "symbol",
        "STOCK_EDGE_SCORE": "stockEdgeScore",
        "SCORE": "stockEdgeScore",
        "TREND_STATE": "trendState",
        "CONFIDENCE": "confidence",
        "RETURN21": "return21",
        "RETURN63": "return63",
        "RETURN126": "return126",
        "MCAP": "totalMcap",
        "LTC_DATE": "ltcDate",
    }
    field = sort_fields.get(_token(sort_key), "stockEdgeScore")
    reverse = _token(sort_dir) != "ASC"
    if field in {"symbol", "trendState", "confidence", "ltcDate"}:
        rows.sort(key=lambda row: _token(row.get(field)), reverse=reverse)
    else:
        rows.sort(key=lambda row: _number(row.get(field)) or 0.0, reverse=reverse)
        rows.sort(key=lambda row: _number(row.get(field)) is None)
    total = len(rows)
    resolved_page = max(1, int(page or 1))
    resolved_size = max(1, min(500, int(page_size or 25)))
    start = (resolved_page - 1) * resolved_size
    page_rows = rows[start:start + resolved_size]
    for index, row in enumerate(page_rows, start + 1):
        row["sNo"] = index
    return {
        "ok": True,
        "status": "success",
        "source": "V3_ATOMIC_STOCK_SNAPSHOT",
        "version": "v3",
        "modelVersion": snapshot.get("modelVersion"),
        "runId": parent.get("runId"),
        "asOfDate": parent.get("asOfDate"),
        "technicalSourceDate": snapshot.get("technicalSourceDate"),
        "generatedAt": snapshot.get("generatedAt"),
        "factorWeights": snapshot.get("factorWeights"),
        "sector": code,
        "sectorName": sector.get("sectorName") or code,
        "parent": sector.get("parent"),
        "rows": page_rows,
        "page": resolved_page,
        "pageSize": resolved_size,
        "totalRows": total,
        "totalCount": total,
        "totalPages": max(1, math.ceil(total / resolved_size)),
        "stock_count": total,
        "isStale": str(snapshot.get("runId") or "") != str(parent.get("runId") or ""),
    }, 200


def get_sector_rotation_v3_stock_symbol(symbol: str) -> tuple[dict[str, Any], int]:
    """Return an exact symbol from the published Sector Wise stock snapshot."""
    target = _symbol(symbol)
    if not target:
        return {
            "ok": False,
            "status": "invalid",
            "version": "v3",
            "error": "A valid NSE symbol is required.",
            "reason": "V3_SYMBOL_REQUIRED",
        }, 400

    snapshot = read_sector_rotation_v3_stock_snapshot()
    parent = read_latest_published_v3_snapshot()
    sectors = snapshot.get("sectors") if isinstance(snapshot, Mapping) else None
    if not isinstance(sectors, Mapping) or not isinstance(parent, Mapping):
        return {
            "ok": False,
            "status": "unavailable",
            "version": "v3",
            "error": "Published V3 stock snapshot is required.",
            "reason": "V3_SNAPSHOT_UNAVAILABLE",
        }, 503
    snapshot_date = _date_key(snapshot.get("asOfDate"))
    parent_date = _date_key(parent.get("asOfDate"))
    is_stale = snapshot_date != parent_date
    if is_stale:
        # The full Sector Wise page remains atomic and rejects mixed dates. The
        # exact Watchlist lookup can safely reuse the last published symbol-to-
        # sector identity, then overlay only the current parent rotation fields.
        matches = _published_symbol_matches(snapshot, target)
        _overlay_current_parent_fields(matches, parent)
    else:
        index = _get_stock_symbol_index(snapshot, parent)
        matches = [dict(row) for row in index.get(target, ())]

    if not matches:
        return {
            "ok": False,
            "status": "not_found",
            "version": "v3",
            "symbol": target,
            "error": f"No published Sector Wise row exists for {target}.",
            "reason": "V3_SYMBOL_NOT_FOUND",
        }, 404

    sector_codes = list(dict.fromkeys(_token(row.get("sectorCode")) for row in matches))

    return {
        "ok": True,
        "status": "success",
        "source": "V3_STALE_IDENTITY_FALLBACK" if is_stale else "V3_ATOMIC_STOCK_SNAPSHOT",
        "version": "v3",
        "modelVersion": snapshot.get("modelVersion"),
        "runId": snapshot.get("runId"),
        "asOfDate": snapshot.get("asOfDate"),
        "isStale": is_stale,
        "parentRunId": parent.get("runId"),
        "parentAsOfDate": parent.get("asOfDate"),
        "technicalSourceDate": snapshot.get("technicalSourceDate"),
        "symbol": target,
        "sectorCodes": sector_codes,
        "totalMatches": len(matches),
        "row": matches[0],
        "matches": matches,
    }, 200


__all__ = [
    "FACTOR_WEIGHTS",
    "MODEL_VERSION",
    "SNAPSHOT_PATH",
    "build_sector_rotation_v3_stock_snapshot",
    "evaluate_sector_v3_eligibility",
    "get_sector_rotation_v3_stock_page",
    "get_sector_rotation_v3_stock_symbol",
    "publish_sector_rotation_v3_stock_snapshot",
    "read_sector_rotation_v3_stock_snapshot",
    "refresh_sector_rotation_v3_stock_snapshot",
]
