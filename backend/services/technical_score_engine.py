from __future__ import annotations

import json
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

ENGINE_SOURCE = "MASTER_TECHNICAL_SCORE_ENGINE"

TREND_LABELS = (
    "Strong Uptrend",
    "Uptrend",
    "Pullback in Uptrend",
    "Sideways",
    "Consolidation",
    "Possible Reversal",
    "Downtrend",
    "Unknown / Insufficient Data",
)

TREND_SORT_ASC = {
    "STRONG UPTREND": 1,
    "UPTREND": 2,
    "PULLBACK IN UPTREND": 3,
    "SIDEWAYS": 4,
    "CONSOLIDATION": 5,
    "POSSIBLE REVERSAL": 6,
    "DOWNTREND": 7,
    "UNKNOWN / INSUFFICIENT DATA": 8,
}

TREND_SCORE_POINTS = {
    "Strong Uptrend": 20,
    "Uptrend": 16,
    "Pullback in Uptrend": 14,
    "Sideways": 8,
    "Consolidation": 6,
    "Possible Reversal": 4,
    "Downtrend": 0,
    "Unknown / Insufficient Data": 0,
}

TREND_SCORE_CAP = {
    "Strong Uptrend": 100,
    "Uptrend": 95,
    "Pullback in Uptrend": 90,
    "Sideways": 65,
    "Consolidation": 60,
    "Possible Reversal": 50,
    "Downtrend": 30,
    "Unknown / Insufficient Data": 20,
}

DEFAULT_CONFIG = {
    "near_high_pct": 5.0,
    "near_low_pct": 5.0,
    "near_level_pct": 2.0,
    "breakout_buffer_pct": 0.25,
    "breakdown_buffer_pct": 0.25,
    "ema20_overextension_pct": 8.0,
    "atr_overextension_multiple": 2.5,
    "low_volume_ratio20": 0.70,
}


def _config_value(config: dict[str, Any] | None, key: str) -> Any:
    if isinstance(config, dict) and key in config:
        return config.get(key)
    return DEFAULT_CONFIG.get(key)


def _cfg_float(config: dict[str, Any] | None, key: str) -> float:
    value = _config_value(config, key)
    try:
        return float(value)
    except Exception:
        return float(DEFAULT_CONFIG[key])


def _key_token(value: Any) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _row_get(row: dict[str, Any], *aliases: str) -> Any:
    if not isinstance(row, dict):
        return None
    for alias in aliases:
        if alias in row:
            return row.get(alias)
    normalized = {_key_token(key): value for key, value in row.items()}
    for alias in aliases:
        token = _key_token(alias)
        if token in normalized:
            return normalized[token]
    return None


def _ctx_get(sr_context: dict[str, Any] | None, *aliases: str) -> Any:
    if not isinstance(sr_context, dict):
        return None
    return _row_get(sr_context, *aliases)


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text or text in {"-", "NA", "N/A", "NULL", "None"}:
        return None
    try:
        return float(text.replace(",", "").replace("%", ""))
    except Exception:
        return None


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value).strip()


def _normalize_flag(value: Any) -> str:
    token = str(value or "").strip().upper().replace("_", " ")
    if token in {"Y", "YES", "TRUE", "1", "BREAKOUT"}:
        return "Y"
    if token in {"N", "NO", "FALSE", "0", "NONE"}:
        return "N"
    return ""


def normalize_trend_label(value: Any) -> str:
    token = str(value or "").strip()
    if not token or token.upper() in {"-", "NA", "N/A", "NONE", "NULL"}:
        return "Unknown / Insufficient Data"
    compact = token.upper().replace("_", " ")
    if "STRONG" in compact and "UP" in compact:
        return "Strong Uptrend"
    if "PULLBACK" in compact and "UP" in compact:
        return "Pullback in Uptrend"
    if "POSSIBLE" in compact and "REVERSAL" in compact:
        return "Possible Reversal"
    if "REVERSAL" in compact:
        return "Possible Reversal"
    if "SIDEWAYS" in compact:
        return "Sideways"
    if "CONSOLIDATION" in compact or "RANGE" in compact:
        return "Consolidation"
    if "DOWN" in compact or "BREAKDOWN" in compact:
        return "Downtrend"
    if "UP" in compact:
        return "Uptrend"
    if "UNKNOWN" in compact or "INSUFFICIENT" in compact:
        return "Unknown / Insufficient Data"
    return token if token in TREND_LABELS else "Unknown / Insufficient Data"


def calculate_score_grade(score: Any) -> str:
    value = _to_float(score)
    if value is None:
        return "NA"
    if value >= 90:
        return "A+"
    if value >= 80:
        return "A"
    if value >= 70:
        return "B"
    if value >= 60:
        return "C"
    if value >= 50:
        return "D"
    return "E"


def calculate_trend_sort(trend: Any) -> int:
    normalized = normalize_trend_label(trend)
    return TREND_SORT_ASC.get(normalized.upper(), TREND_SORT_ASC["UNKNOWN / INSUFFICIENT DATA"])


def _pct_below_level(price: float | None, level: float | None) -> float | None:
    if price is None or level is None or level <= 0:
        return None
    return ((level - price) / level) * 100.0


def _pct_above_level(price: float | None, level: float | None) -> float | None:
    if price is None or level is None or level <= 0:
        return None
    return ((price - level) / level) * 100.0


def _is_near_high(price: float | None, level: float | None, pct: float) -> bool:
    gap = _pct_below_level(price, level)
    return gap is not None and 0.0 <= gap <= max(0.0, pct)


def _is_near_low(price: float | None, level: float | None, pct: float) -> bool:
    gap = _pct_above_level(price, level)
    return gap is not None and 0.0 <= gap <= max(0.0, pct)


def _level_price(value: Any) -> float | None:
    if isinstance(value, dict):
        return _to_float(_first_present(value.get("price"), value.get("level"), value.get("value")))
    if isinstance(value, (list, tuple)) and value:
        return _level_price(value[0])
    return _to_float(value)


def _extract_inputs(
    row: dict[str, Any],
    sr_context: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    trend_metrics = _row_get(row, "trendMetrics", "trend_metrics")
    if not isinstance(trend_metrics, dict):
        trend_metrics = {}
    price_action = _row_get(row, "priceAction", "price_action")
    if not isinstance(price_action, dict):
        price_action = {}

    close = _to_float(_first_present(
        _row_get(row, "close", "closePrice", "close_price", "price", "currentPrice", "current_price", "ltp", "LTP"),
        _row_get(row, "previousClose", "previous_close", "PREVIOUS_CLOSE"),
    ))
    high = _to_float(_row_get(row, "high", "highPrice", "high_price", "HIGH"))
    low = _to_float(_row_get(row, "low", "lowPrice", "low_price", "LOW"))
    open_price = _to_float(_row_get(row, "open", "openPrice", "open_price", "OPEN"))

    support = _level_price(_first_present(
        _ctx_get(sr_context, "supportPrice", "support", "primarySupport"),
        _row_get(row, "supportPrice", "support_price", "support", "primarySupport", "dominantSupport"),
    ))
    resistance = _level_price(_first_present(
        _ctx_get(sr_context, "resistancePrice", "resistance", "primaryResistance"),
        _row_get(row, "resistancePrice", "resistance_price", "resistance", "primaryResistance", "dominantResistance"),
    ))

    dist_support = _to_float(_first_present(
        _ctx_get(sr_context, "distanceToSupportPct", "distToSupportPct", "dist_to_support_pct"),
        _row_get(row, "distanceToSupportPct", "distToSupportPct", "dist_to_support_pct"),
    ))
    dist_resistance = _to_float(_first_present(
        _ctx_get(sr_context, "distanceToResistancePct", "distToResistancePct", "dist_to_resistance_pct"),
        _row_get(row, "distanceToResistancePct", "distToResistancePct", "dist_to_resistance_pct"),
    ))
    if dist_support is None:
        dist_support = _pct_above_level(close, support)
    if dist_resistance is None:
        dist_resistance = _pct_below_level(close, resistance)

    close_location = _to_float(_row_get(row, "closeLocationPct", "close_location_pct"))
    if close_location is None and close is not None and high is not None and low is not None and high > low:
        close_location = ((close - low) / (high - low)) * 100.0

    macd_hist = _to_float(_row_get(row, "macdHist", "macd_hist", "MACD_HIST", "macd"))
    prev_macd_hist = _to_float(_row_get(row, "prevMacdHist", "previousMacdHist", "prev_macd_hist", "MACD_HIST_PREV"))
    macd_hist_slope = _to_float(_row_get(row, "macdHistSlope", "macd_hist_slope", "MACD_HIST_SLOPE"))
    if macd_hist_slope is None and macd_hist is not None and prev_macd_hist is not None:
        macd_hist_slope = macd_hist - prev_macd_hist

    adx = _to_float(_first_present(
        _ctx_get(sr_context, "adx14", "ADX14", "strength"),
        trend_metrics.get("strength"),
        _row_get(row, "adx14", "adx", "ADX14", "ADX"),
    ))
    adx_prev = _to_float(_row_get(row, "prevAdx14", "previousAdx14", "prev_adx14"))
    adx_slope = _to_float(_row_get(row, "adx14Slope", "adxSlope", "adx14_slope", "adx_slope"))
    if adx_slope is None and adx is not None and adx_prev is not None:
        adx_slope = adx - adx_prev

    delivery_pct = _to_float(_row_get(row, "deliveryPct", "delivery_pct", "DELIVERY_PCT", "deliveryPercent"))
    volume = _to_float(_row_get(row, "volume", "VOLUME", "totalTradedQty", "total_traded_qty"))
    deliverable_value = _to_float(_row_get(row, "deliverableValue", "deliverable_value", "DELIVERABLE_VALUE"))
    if deliverable_value is None and close is not None and volume is not None and delivery_pct is not None:
        pct_value = delivery_pct / 100.0 if delivery_pct > 1 else delivery_pct
        deliverable_value = close * volume * pct_value

    breakout_raw = _first_present(
        _ctx_get(sr_context, "breakoutFlag", "breakout_flag"),
        _row_get(row, "breakoutFlag", "breakout_flag", "boFlag", "bo_flag"),
        price_action.get("state"),
    )
    breakout_token = str(breakout_raw or "").strip().upper()
    breakdown_raw = _first_present(
        _ctx_get(sr_context, "breakdownFlag", "breakdown_flag"),
        _row_get(row, "breakdownFlag", "breakdown_flag"),
        price_action.get("state"),
    )
    breakdown_token = str(breakdown_raw or "").strip().upper()

    data = {
        "symbol": _to_text(_row_get(row, "symbol", "stock", "SYMBOL", "STOCK")),
        "tradingDate": _to_text(_row_get(row, "tradingDate", "tradeDate", "ltcDate", "ltc_date", "TRADING_DATE", "TRADE_DATE", "LTC_DATE")),
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "ema20": _to_float(_row_get(row, "ema20", "EMA20", "_e20")),
        "ema50": _to_float(_row_get(row, "ema50", "EMA50", "_e50")),
        "ema100": _to_float(_row_get(row, "ema100", "EMA100", "_e100")),
        "ema200": _to_float(_row_get(row, "ema200", "EMA200", "_e200")),
        "ema20SlopePct": _to_float(_first_present(_ctx_get(sr_context, "ema20SlopePct"), trend_metrics.get("ema20SlopePct"), _row_get(row, "ema20SlopePct", "ema20_slope_pct"))),
        "ema50SlopePct": _to_float(_row_get(row, "ema50SlopePct", "ema50_slope_pct", "ema50SlopePct10d", "ema50_slopepct_10d")),
        "rsi": _to_float(_row_get(row, "rsi", "rsi14", "RSI", "RSI14")),
        "prevRsi": _to_float(_row_get(row, "prevRsi", "previousRsi", "prev_rsi", "previous_rsi")),
        "macdHist": macd_hist,
        "macdHistSlope": macd_hist_slope,
        "adx14": adx,
        "adx14Slope": adx_slope,
        "plusDi14": _to_float(_row_get(row, "plusDi14", "plus_di14", "diPlus14", "di_plus14", "PLUS_DI14")),
        "minusDi14": _to_float(_row_get(row, "minusDi14", "minus_di14", "diMinus14", "di_minus14", "MINUS_DI14")),
        "atr14": _to_float(_first_present(_ctx_get(sr_context, "atr14", "atr"), trend_metrics.get("atr"), _row_get(row, "atr14", "atr", "ATR14"))),
        "volumeRatio20": _to_float(_row_get(row, "volumeRatio20", "volume_ratio20", "volume_ratio_20", "VOLUME_RATIO20", "VOLUME_RATIO_20", "volumeRatio")),
        "volumePrevDayFlag": _row_get(row, "volumePrevDayFlag", "volume_prev_day_flag"),
        "volumePrevWeekFlag": _row_get(row, "volumePrevWeekFlag", "volume_prev_week_flag"),
        "volumePrevMonthFlag": _row_get(row, "volumePrevMonthFlag", "volume_prev_month_flag"),
        "deliveryPct": delivery_pct,
        "deliveryRel20": _to_float(_row_get(row, "deliveryRel20", "delivery_rel20", "delivery_rel_20", "DELIVERY_REL_20")),
        "deliverableValue": deliverable_value,
        "deliverableValueRel20": _to_float(_row_get(row, "deliverableValueRel20", "deliverable_value_rel20", "deliverable_value_rel_20", "DELIVERABLE_VALUE_REL_20")),
        "deliveryPrevDayFlag": _row_get(row, "deliveryPrevDayFlag", "delivery_prev_day_flag"),
        "deliveryPrevWeekFlag": _row_get(row, "deliveryPrevWeekFlag", "delivery_prev_week_flag"),
        "deliveryPrevMonthFlag": _row_get(row, "deliveryPrevMonthFlag", "delivery_prev_month_flag"),
        "ath": _to_float(_row_get(row, "ath", "ATH", "allTimeHigh", "all_time_high")),
        "high52w": _to_float(_row_get(row, "high52w", "high_52w", "HIGH_52W", "52wh", "W52H")),
        "low52w": _to_float(_row_get(row, "low52w", "low_52w", "LOW_52W", "52wl", "W52L")),
        "support": support,
        "resistance": resistance,
        "distanceToSupportPct": dist_support,
        "distanceToResistancePct": dist_resistance,
        "closeLocationPct": close_location,
        "breakoutFlag": "BREAKOUT" if "BREAKOUT" in breakout_token else "",
        "breakdownFlag": "BREAKDOWN" if "BREAKDOWN" in breakdown_token else "",
        "retestReady": bool(_row_get(row, "retestReady", "retest_ready")),
        "legacyTrend": normalize_trend_label(_first_present(
            _ctx_get(sr_context, "trend", "trendDirection", "trend_direction"),
            _row_get(row, "trend", "trendDirection", "trend_direction", "TREND", "TREND_DIRECTION"),
        )),
        "priceActionState": str(price_action.get("state") or "").strip().lower(),
    }
    return data


def _missing_inputs(inputs: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    missing: list[str] = []
    for key in keys:
        if inputs.get(key) is None:
            missing.append(key)
    return missing


def calculate_master_trend(
    row: dict[str, Any],
    sr_context: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    inputs = _extract_inputs(row, sr_context, config)
    close = inputs["close"]
    if close is None:
        trend = "Unknown / Insufficient Data"
        return {
            "trend": trend,
            "trendSort": calculate_trend_sort(trend),
            "trendDecisionReason": "PRICE_MISSING",
            "trendSource": ENGINE_SOURCE,
            "missingInputs": _missing_inputs(inputs, ("close", "ema20", "ema50", "ema100", "ema200")),
            "riskFlags": [],
            "debug": inputs,
        }

    near_high_pct = _cfg_float(config, "near_high_pct")
    near_low_pct = _cfg_float(config, "near_low_pct")
    near_level_pct = _cfg_float(config, "near_level_pct")
    breakout_buffer = _cfg_float(config, "breakout_buffer_pct")
    breakdown_buffer = _cfg_float(config, "breakdown_buffer_pct")

    ema_values = [inputs["ema20"], inputs["ema50"], inputs["ema100"], inputs["ema200"]]
    ema_known = [value for value in ema_values if value is not None]
    bullish_ema_count = sum(1 for value in ema_known if close > value)
    bearish_ema_count = sum(1 for value in ema_known if close < value)
    bullish_majority = bullish_ema_count >= 3
    bearish_majority = bearish_ema_count >= 3
    mixed_ema = bullish_ema_count > 0 and bearish_ema_count > 0
    e20, e50, e100, e200 = ema_values
    bullish_stack = (
        e20 is not None and e50 is not None and e100 is not None and e200 is not None
        and close > e20 > e50 > e100 > e200
    )
    bearish_stack = (
        e20 is not None and e50 is not None and e100 is not None and e200 is not None
        and close < e20 < e50 < e100 < e200
    )
    ema20_pullback_structure = (
        e20 is not None and close <= e20
        and e50 is not None and e100 is not None and e200 is not None
        and close > e50 and close > e100 and close > e200
    )

    support_gap = inputs["distanceToSupportPct"]
    resistance_gap = inputs["distanceToResistancePct"]
    near_support = support_gap is not None and support_gap >= (0 - breakdown_buffer) and abs(support_gap) <= near_level_pct
    near_resistance = resistance_gap is not None and resistance_gap >= (0 - breakout_buffer) and abs(resistance_gap) <= near_level_pct
    above_resistance = (
        inputs["resistance"] is not None
        and close > inputs["resistance"] * (1 + breakout_buffer / 100.0)
    )
    below_support = (
        inputs["support"] is not None
        and close < inputs["support"] * (1 - breakdown_buffer / 100.0)
    )
    breakout = bool(inputs["breakoutFlag"]) or above_resistance
    breakdown = bool(inputs["breakdownFlag"]) or below_support

    near_ath = _is_near_high(close, inputs["ath"], near_high_pct)
    near_52w_high = _is_near_high(close, inputs["high52w"], near_high_pct)
    near_52w_low = _is_near_low(close, inputs["low52w"], near_low_pct)
    at_or_above_high = any(
        level is not None and level > 0 and close >= level * (1 + breakout_buffer / 100.0)
        for level in (inputs["ath"], inputs["high52w"])
    )

    adx = inputs["adx14"]
    rsi = inputs["rsi"]
    macd_hist = inputs["macdHist"]
    volume_ratio = inputs["volumeRatio20"]
    delivery_rel = inputs["deliveryRel20"]
    plus_di = inputs["plusDi14"]
    minus_di = inputs["minusDi14"]
    legacy_trend = inputs["legacyTrend"]

    adx_weak = adx is not None and adx < 18
    adx_supportive = adx is None or adx >= 25
    momentum_supportive = (
        (rsi is None or 50 <= rsi <= 75)
        and (macd_hist is None or macd_hist > 0)
    )
    participation_supportive = (
        (volume_ratio is None and delivery_rel is None)
        or (volume_ratio is not None and volume_ratio >= 1.2)
        or (delivery_rel is not None and delivery_rel >= 1.1)
    )
    slopes_supportive = (
        (inputs["ema20SlopePct"] is None or inputs["ema20SlopePct"] > 0)
        and (inputs["ema50SlopePct"] is None or inputs["ema50SlopePct"] > 0)
    )
    bullish_di = plus_di is None or minus_di is None or plus_di >= minus_di
    bearish_di = plus_di is not None and minus_di is not None and minus_di > plus_di

    risk_flags: list[str] = []
    if near_resistance and not breakout:
        risk_flags.append("NEAR_RESISTANCE_WITHOUT_BREAKOUT")
    if adx_weak and bullish_majority:
        risk_flags.append("BULLISH_EMA_WEAK_ADX")
    if rsi is not None and rsi > 75:
        risk_flags.append("RSI_OVEREXTENDED")

    if breakdown and (bearish_majority or bearish_stack or bearish_di):
        trend = "Downtrend"
        reason = "SUPPORT_BREAKDOWN_BEARISH_CONFIRMATION"
    elif bearish_stack or (bearish_majority and (breakdown or bearish_di or close < (e100 or close))):
        trend = "Downtrend"
        reason = "BEARISH_EMA_MAJORITY"
    elif bullish_majority and adx_weak:
        trend = "Consolidation"
        reason = "BULLISH_EMA_BUT_ADX_WEAK"
    elif (at_or_above_high or near_ath or near_52w_high or breakout) and not bullish_majority and not bullish_stack:
        trend = "Consolidation"
        reason = "NEAR_HIGH_BUT_EMA_MIXED"
    elif (
        (at_or_above_high or near_ath or near_52w_high or breakout or legacy_trend == "Strong Uptrend")
        and (bullish_stack or bullish_majority or legacy_trend == "Strong Uptrend")
        and slopes_supportive
        and adx_supportive
        and momentum_supportive
        and participation_supportive
        and bullish_di
        and "NEAR_RESISTANCE_WITHOUT_BREAKOUT" not in risk_flags
    ):
        trend = "Strong Uptrend"
        reason = "NEAR_52W_HIGH_BULLISH_EMA_ADX_VOLUME"
    elif ema20_pullback_structure or legacy_trend == "Pullback in Uptrend":
        trend = "Pullback in Uptrend"
        reason = "EMA20_PULLBACK_LONG_EMAS_BULLISH"
    elif near_52w_low:
        early_bullish = (
            (macd_hist is not None and macd_hist > 0)
            or (rsi is not None and rsi >= 45)
            or (plus_di is not None and minus_di is not None and plus_di > minus_di)
            or near_support
        )
        trend = "Possible Reversal" if early_bullish else "Downtrend"
        reason = "NEAR_52W_LOW_EARLY_BULLISH_SIGNS" if early_bullish else "NEAR_52W_LOW_WEAK_STRUCTURE"
    elif near_resistance and not breakout:
        trend = "Consolidation"
        reason = "NEAR_RESISTANCE_NO_BREAKOUT"
    elif mixed_ema and (adx is None or adx < 25):
        trend = "Sideways"
        reason = "MIXED_EMA_WEAK_OR_MISSING_ADX"
    elif bullish_majority or legacy_trend == "Uptrend":
        trend = "Uptrend"
        reason = "BULLISH_EMA_MAJORITY"
    elif normalize_trend_label(legacy_trend) in {"Sideways", "Consolidation", "Possible Reversal", "Downtrend"}:
        trend = normalize_trend_label(legacy_trend)
        reason = "LEGACY_STANDARD_TREND_FALLBACK"
    else:
        trend = "Consolidation"
        reason = "DEFAULT_CONSOLIDATION"

    trend = normalize_trend_label(trend)
    missing = _missing_inputs(inputs, (
        "ema20SlopePct",
        "ema50SlopePct",
        "macdHistSlope",
        "adx14Slope",
        "plusDi14",
        "minusDi14",
        "atr14",
        "volumeRatio20",
        "deliveryRel20",
        "deliverableValue",
        "deliverableValueRel20",
        "distanceToSupportPct",
        "distanceToResistancePct",
        "closeLocationPct",
    ))
    return {
        "trend": trend,
        "trendSort": calculate_trend_sort(trend),
        "trendDecisionReason": reason,
        "trendSource": ENGINE_SOURCE,
        "missingInputs": missing,
        "riskFlags": risk_flags,
        "debug": {
            **inputs,
            "bullishEmaCount": bullish_ema_count,
            "bearishEmaCount": bearish_ema_count,
            "bullishStack": bullish_stack,
            "breakout": breakout,
            "breakdown": breakdown,
            "nearAth": near_ath,
            "near52wHigh": near_52w_high,
            "near52wLow": near_52w_low,
        },
    }


def _volume_score(inputs: dict[str, Any]) -> int:
    ratio = inputs.get("volumeRatio20")
    if ratio is not None:
        if ratio >= 2.0:
            return 10
        if ratio >= 1.5:
            return 8
        if ratio >= 1.2:
            return 5
        if ratio >= 1.0:
            return 3
        return 0
    flags = [
        _normalize_flag(_row_get(inputs, "volumePrevDayFlag")),
        _normalize_flag(_row_get(inputs, "volumePrevWeekFlag")),
        _normalize_flag(_row_get(inputs, "volumePrevMonthFlag")),
    ]
    count = sum(1 for flag in flags if flag == "Y")
    return {0: 0, 1: 3, 2: 6, 3: 10}.get(count, 0)


def _delivery_score(inputs: dict[str, Any]) -> int:
    score = 0
    rel = inputs.get("deliveryRel20")
    if rel is not None:
        if rel >= 1.25:
            score += 7
        elif rel >= 1.1:
            score += 5
        elif rel >= 1.0:
            score += 3
    value_rel = inputs.get("deliverableValueRel20")
    if value_rel is not None and value_rel >= 1.2:
        score += 3
    if rel is None and value_rel is None:
        flags = [
            _normalize_flag(_row_get(inputs, "deliveryPrevDayFlag")),
            _normalize_flag(_row_get(inputs, "deliveryPrevWeekFlag")),
            _normalize_flag(_row_get(inputs, "deliveryPrevMonthFlag")),
        ]
        count = sum(1 for flag in flags if flag == "Y")
        score = {0: 0, 1: 3, 2: 6, 3: 10}.get(count, 0)
    return min(10, score)


def build_score_breakdown(
    row: dict[str, Any],
    trend_result: dict[str, Any],
    sr_context: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    inputs = _extract_inputs(row, sr_context, config)
    close = inputs["close"]
    trend = normalize_trend_label(trend_result.get("trend"))
    risk_flags = list(trend_result.get("riskFlags") or [])

    trend_score = TREND_SCORE_POINTS.get(trend, 0)

    ema_score = 0
    ema_values = [inputs["ema20"], inputs["ema50"], inputs["ema100"], inputs["ema200"]]
    if close is not None:
        ema_score += sum(3 for value in ema_values if value is not None and close > value)
        e20, e50, e100, e200 = ema_values
        if e20 is not None and e50 is not None and e100 is not None and e200 is not None and close > e20 > e50 > e100 > e200:
            ema_score += 3
        elif (inputs["ema20SlopePct"] or 0) > 0 and (inputs["ema50SlopePct"] or 0) > 0:
            ema_score += 2
    ema_score = min(15, ema_score)

    momentum_score = 0
    rsi = inputs["rsi"]
    prev_rsi = inputs["prevRsi"]
    macd_hist = inputs["macdHist"]
    macd_slope = inputs["macdHistSlope"]
    if rsi is not None:
        if 55 <= rsi <= 70:
            momentum_score += 6
        elif 50 <= rsi < 55:
            momentum_score += 3
        elif 70 < rsi <= 75:
            momentum_score += 5
        elif rsi > 75:
            momentum_score += 2
    if rsi is not None and prev_rsi is not None and prev_rsi < 50 <= rsi:
        momentum_score += 3
    if macd_hist is not None and macd_hist > 0:
        momentum_score += 3
    if macd_slope is not None and macd_slope > 0:
        momentum_score += 3
    momentum_score = min(15, momentum_score)

    adx = inputs["adx14"]
    adx_slope = inputs["adx14Slope"]
    if adx is None or adx < 18:
        adx_score = 0
    elif adx < 20:
        adx_score = 2
    elif adx < 25:
        adx_score = 4
    elif adx < 35:
        adx_score = 8
    else:
        adx_score = 10 if adx_slope is None or adx_slope >= 0 else 6

    volume_score = _volume_score(inputs)
    delivery_score = _delivery_score(inputs)

    structure_score = 0
    near_support = inputs["distanceToSupportPct"] is not None and abs(inputs["distanceToSupportPct"]) <= _cfg_float(config, "near_level_pct")
    near_resistance = inputs["distanceToResistancePct"] is not None and abs(inputs["distanceToResistancePct"]) <= _cfg_float(config, "near_level_pct")
    breakout = bool(inputs["breakoutFlag"])
    breakdown = bool(inputs["breakdownFlag"])
    if breakout:
        structure_score += 8
        if volume_score >= 5:
            structure_score += 4
    if inputs["retestReady"]:
        structure_score += 3
    if near_support and trend in {"Strong Uptrend", "Uptrend", "Pullback in Uptrend"}:
        structure_score += 5
    if breakdown:
        risk_flags.append("SUPPORT_BREAKDOWN")
    structure_score = min(15, structure_score)

    risk_penalty = 0
    e20 = inputs["ema20"]
    if close is not None and e20 is not None and e20 > 0:
        dist_ema20 = ((close - e20) / e20) * 100.0
        if dist_ema20 > _cfg_float(config, "ema20_overextension_pct"):
            risk_penalty -= 4
            risk_flags.append("PRICE_FAR_ABOVE_EMA20")
    atr = inputs["atr14"]
    if close is not None and e20 is not None and atr is not None and close > e20 + (atr * _cfg_float(config, "atr_overextension_multiple")):
        risk_penalty -= 4
        risk_flags.append("PRICE_ABOVE_ATR_BAND")
    weak_close = (
        (inputs["closeLocationPct"] is not None and inputs["closeLocationPct"] < 50)
        or (inputs["open"] is not None and close is not None and close < inputs["open"])
    )
    if rsi is not None and rsi > 75 and weak_close:
        risk_penalty -= 3
        risk_flags.append("RSI_OVEREXTENDED_WEAK_CLOSE")
    if near_resistance and not breakout:
        risk_penalty -= 4
        risk_flags.append("NEAR_RESISTANCE_WITHOUT_BREAKOUT")
    volume_ratio = inputs["volumeRatio20"]
    if volume_ratio is not None and volume_ratio < _cfg_float(config, "low_volume_ratio20"):
        risk_penalty -= 5
        risk_flags.append("LOW_VOLUME_RATIO20")
    if weak_close:
        risk_penalty -= 3
        risk_flags.append("WEAK_CLOSE_BELOW_MIDPOINT")
    if volume_score >= 5 and delivery_score == 0:
        risk_penalty -= 2
        risk_flags.append("VOLUME_WITHOUT_DELIVERY_CONFIRMATION")
    risk_penalty = max(-15, risk_penalty)

    raw_score = trend_score + ema_score + momentum_score + adx_score + volume_score + delivery_score + structure_score + risk_penalty
    trend_cap = TREND_SCORE_CAP.get(trend, 20)
    if trend in {"Strong Uptrend", "Uptrend", "Pullback in Uptrend"} and adx is not None and adx < 18:
        trend_cap = min(trend_cap, 60)
    capped = max(0, min(100, min(raw_score, trend_cap)))

    missing = sorted(set((trend_result.get("missingInputs") or []) + _missing_inputs(inputs, (
        "rsi",
        "macdHist",
        "adx14",
        "volumeRatio20",
        "deliveryRel20",
        "deliverableValueRel20",
        "ema20",
        "ema50",
        "ema100",
        "ema200",
    ))))
    return {
        "trend": trend_score,
        "ema": ema_score,
        "momentum": momentum_score,
        "adx": adx_score,
        "volume": volume_score,
        "delivery": delivery_score,
        "structure": structure_score,
        "riskPenalty": risk_penalty,
        "rawScore": int(round(max(0, min(100, raw_score)))),
        "trendCap": trend_cap,
        "capApplied": capped < raw_score,
        "total": int(round(capped)),
        "missingInputs": missing,
        "riskFlags": sorted(set(risk_flags)),
    }


def calculate_master_score(
    row: dict[str, Any],
    trend_result: dict[str, Any],
    sr_context: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        breakdown = build_score_breakdown(row, trend_result, sr_context, config)
        score = int(round(_to_float(breakdown.get("total")) or 0))
    except Exception:
        logger.exception("technical_score_engine_score_failed")
        breakdown = {
            "trend": 0,
            "ema": 0,
            "momentum": 0,
            "adx": 0,
            "volume": 0,
            "delivery": 0,
            "structure": 0,
            "riskPenalty": 0,
            "total": 0,
            "missingInputs": ["engineError"],
            "riskFlags": [],
        }
        score = 0
    score = max(0, min(100, score))
    return {
        "score": score,
        "scoreSort": score,
        "scoreGrade": calculate_score_grade(score),
        "scoreBreakdown": breakdown,
        "scoreSource": ENGINE_SOURCE,
    }


def enrich_row_with_master_score_fields(
    row: dict[str, Any],
    sr_context: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    *,
    replace_existing: bool = False,
) -> dict[str, Any]:
    if not isinstance(row, dict):
        return row
    try:
        trend_result = calculate_master_trend(row, sr_context=sr_context, config=config)
        score_result = calculate_master_score(row, trend_result, sr_context=sr_context, config=config)
    except Exception:
        logger.exception("technical_score_engine_enrich_failed")
        return row

    row["masterTrend"] = trend_result["trend"]
    row["masterTrendSort"] = trend_result["trendSort"]
    row["masterTrendDecisionReason"] = trend_result["trendDecisionReason"]
    row["masterTrendSource"] = trend_result["trendSource"]
    row["masterScore"] = score_result["score"]
    row["masterScoreSort"] = score_result["scoreSort"]
    row["masterScoreGrade"] = score_result["scoreGrade"]
    row["masterScoreBreakdown"] = score_result["scoreBreakdown"]

    if replace_existing or not _row_get(row, "trend", "trendDirection", "trend_direction"):
        row["trend"] = trend_result["trend"]
        row["trendDirection"] = trend_result["trend"]
        row["trendSort"] = trend_result["trendSort"]
        row["trendDirectionSort"] = trend_result["trendSort"]
        row["trendDecisionReason"] = trend_result["trendDecisionReason"]
        row["trendSource"] = trend_result["trendSource"]

    if replace_existing or _row_get(row, "score", "scoreSort", "score_breakdown") is None:
        row["score"] = score_result["score"]
        row["scoreSort"] = score_result["scoreSort"]
        row["scoreGrade"] = score_result["scoreGrade"]
        row["scoreBreakdown"] = score_result["scoreBreakdown"]

    return row


def dumps_json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=True, sort_keys=True, default=str)
