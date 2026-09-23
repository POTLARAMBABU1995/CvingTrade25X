from __future__ import annotations

import logging
import os
import re
import time
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from math import isfinite
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from cache import TTLCache, background_refresh, load_json_snapshot, save_json_snapshot
from db import fetch_latest_trade_date_from_oracle, fetch_recent_ohlc_series_from_oracle
from services.ath_service import get_all_time_high_for_symbols
from services.strong_uptrend_reversal_service import (
    _adx_series,
    _fetch_latest_delivery_pct_map,
    _is_bullish_reversal_candle,
    _macd_series,
    _rsi_series,
    _volume_sma20,
)
from services.technical_utils import aggregate_ohlc_series_by_timeframe, calculate_atr, calculate_ema, classify_trend_structure, detect_swing_pivots

try:
    from ..db_pool import fetchall_dict, pool
except ImportError:  # pragma: no cover
    from db_pool import fetchall_dict, pool  # type: ignore


_logger = logging.getLogger(__name__)
_CACHE_VERSION = "v4"
_CACHE_TTL_SECONDS = max(30, int(str(os.getenv("PRUDVI_STRATEGY_CACHE_TTL", "300")).strip() or "300"))
_LOOKBACK_TRADING_DAYS = max(252, min(int(str(os.getenv("PRUDVI_STRATEGY_LOOKBACK_DAYS", "252")).strip() or "252"), 1000))
_SR_TOLERANCE_PCT = max(
    0.1,
    float(
        str(
            os.getenv(
                "PRUDVI_SR_TOLERANCE_PCT",
                os.getenv("PRUDVI_SUPPORT_TOLERANCE_PCT", "1.0"),
            )
        ).strip()
        or "1.0"
    ),
)
_SUPPORT_CANDLE_LOOKBACK = max(3, min(int(str(os.getenv("PRUDVI_SUPPORT_CANDLE_LOOKBACK", "5")).strip() or "5"), 10))
_REACTION_LOOKAHEAD_CANDLES = max(1, min(int(str(os.getenv("PRUDVI_REACTION_LOOKAHEAD_CANDLES", "5")).strip() or "5"), 8))
_CACHE = TTLCache(ttl_seconds=_CACHE_TTL_SECONDS, max_items=8)
_SNAPSHOT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_SNAPSHOT_FILE = "snapshot_prudvi_strategy.json"

_IDENT_RE = re.compile(r"^[A-Za-z0-9_.$#]+$")
_SCHEMA = (os.getenv("PRICE_ACTION_SR_SCHEMA") or os.getenv("ORACLE_SCHEMA") or "").strip()
_TABLE = (os.getenv("PRICE_ACTION_SR_LEVELS_MANUALLY_TABLE") or "PRICE_ACTION_SR_LEVELS_MANUALLY").strip()
_NUMERIC_LEVEL_RE = re.compile(r"(?<![A-Za-z])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?(?![A-Za-z])")

_BULLISH_CANDLE_PATTERNS = {
    "BULLISH_ENGULFING",
    "HAMMER",
    "INVERTED_HAMMER",
    "DRAGONFLY_DOJI",
    "BULLISH_HARAMI",
    "PIERCING_LINE",
    "MORNING_STAR",
    "THREE_WHITE_SOLDIERS",
    "BULLISH_MARUBOZU",
    "THREE_INSIDE_UP",
}
_BEARISH_CANDLE_PATTERNS = {
    "BEARISH_ENGULFING",
    "SHOOTING_STAR",
    "HANGING_MAN",
    "EVENING_STAR",
    "BEARISH_HARAMI",
    "DARK_CLOUD_COVER",
    "THREE_BLACK_CROWS",
    "BEARISH_MARUBOZU",
}
_NEUTRAL_CANDLE_PATTERNS = {"DOJI", "SPINNING_TOP", "NONE", "-"}


def _safe_identifier(value: str) -> str:
    name = str(value or "").strip()
    if not name or not _IDENT_RE.match(name):
        raise ValueError(f"Invalid identifier: {value!r}")
    return name


def _qualified_manual_sr_table() -> str:
    table = _safe_identifier(_TABLE)
    if "." in table:
        return table
    schema = _safe_identifier(_SCHEMA) if _SCHEMA else ""
    return f"{schema}.{table}" if schema else table


def _normalize_symbol_token(value: Any) -> str:
    token = str(value or "").strip().upper()
    for prefix in ("NSE:", "BSE:"):
        if token.startswith(prefix):
            token = token[len(prefix):].strip()
            break
    for suffix in (":EQ", "-EQ"):
        if token.endswith(suffix):
            token = token[:-len(suffix)].strip()
            break
    return token


def _normalized_symbol_expr(expr: str) -> str:
    return (
        "UPPER(TRIM(REGEXP_REPLACE("
        "REGEXP_REPLACE("
        "REGEXP_REPLACE(TRIM("
        f"{expr}"
        "), '^(NSE|BSE):', '', 1, 0, 'i'), "
        "'(:EQ|-EQ)$', '', 1, 0, 'i'), "
        "'[[:space:]]+', '')))"
    )


def _tf_filter_clause() -> str:
    return "TRIM(UPPER(NVL(TF, '1D'))) IN ('1D', 'D')"


def _to_decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    text = str(value).replace(",", "").strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _format_decimal(value: Any) -> str:
    dec = _to_decimal(value)
    if dec is None:
        return "-"
    text = format(dec.quantize(Decimal("0.000001")), "f")
    text = text.rstrip("0").rstrip(".")
    return text or "0"


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _round_or_none(value: Any, digits: int = 2) -> Optional[float]:
    number = _to_float(value)
    return round(number, digits) if number is not None else None


def _iso_date(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return None
    return None


def _parse_iso_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value or "").strip())
    except ValueError:
        return None


def _gap_pct(price: Any, ath: Any) -> Optional[float]:
    price_num = _to_float(price)
    ath_num = _to_float(ath)
    if price_num is None or ath_num is None or ath_num == 0:
        return None
    return ((price_num - ath_num) / ath_num) * 100.0


def _format_gap(value: Any) -> str:
    number = _to_float(value)
    if number is None:
        return "-"
    return f"{number:+.2f}%"


def parse_manual_sr_levels(sr_level_text: Any) -> List[float]:
    text = str(sr_level_text or "").strip()
    if not text:
        return []
    levels: set[float] = set()
    for match in _NUMERIC_LEVEL_RE.finditer(text):
        token = match.group(0).strip()
        if not token or token.endswith("%"):
            continue
        number = _to_float(token.replace(",", ""))
        if number is None or number <= 0:
            continue
        levels.add(round(float(number), 6))
    return sorted(levels)


def classify_sr_candidates(levels: Sequence[float], current_price: Any) -> Tuple[List[float], List[float]]:
    price = _to_float(current_price)
    clean = sorted({float(level) for level in levels if _to_float(level) is not None and float(level) > 0})
    if price is None or price <= 0:
        return [], []
    support_candidates = sorted((level for level in clean if level <= price), reverse=True)
    resistance_candidates = [level for level in clean if level > price]
    return support_candidates, resistance_candidates


def _sr_tolerance(level: Any, candles: Sequence[Dict[str, Any]] | None = None) -> float:
    level_num = _to_float(level)
    if level_num is None or level_num <= 0:
        return 0.0
    pct_tolerance = level_num * (_SR_TOLERANCE_PCT / 100.0)
    atr14 = calculate_atr(list(candles or [])[-40:], 14) if candles else None
    if atr14 is not None and atr14 > 0:
        return max(pct_tolerance, 0.5 * float(atr14))
    return pct_tolerance


def _row_volume_avg(candles: Sequence[Dict[str, Any]], index: int, window: int = 20) -> Optional[float]:
    start = max(0, index - window)
    values = [
        _to_float(item.get("volume"))
        for item in candles[start:index]
        if _to_float(item.get("volume")) is not None
    ]
    if not values:
        return None
    return sum(values) / float(len(values))


def _volume_confirms(volume: Any, volume_avg: Any) -> bool:
    volume_num = _to_float(volume)
    avg_num = _to_float(volume_avg)
    return bool(volume_num is not None and avg_num is not None and volume_num > avg_num)


def _delivery_confirms(delivery_pct: Any) -> bool:
    delivery_num = _to_float(delivery_pct)
    return bool(delivery_num is not None and delivery_num > 60)


def _candle_numbers(row: Dict[str, Any]) -> Optional[Tuple[float, float, float, float]]:
    open_price = _to_float(row.get("open"))
    high_price = _to_float(row.get("high"))
    low_price = _to_float(row.get("low"))
    close_price = _to_float(row.get("close"))
    if None in (open_price, high_price, low_price, close_price):
        return None
    if high_price < low_price:
        return None
    return float(open_price), float(high_price), float(low_price), float(close_price)


def _is_near_support(row: Dict[str, Any], support: float, tolerance: float) -> bool:
    numbers = _candle_numbers(row)
    if numbers is None:
        return False
    _open_price, _high_price, low_price, close_price = numbers
    return (
        abs(low_price - support) <= tolerance
        or abs(close_price - support) <= tolerance
        or (low_price <= support + tolerance and close_price >= support)
    )


def _is_near_resistance(row: Dict[str, Any], resistance: float, tolerance: float) -> bool:
    numbers = _candle_numbers(row)
    if numbers is None:
        return False
    _open_price, high_price, _low_price, close_price = numbers
    return (
        abs(high_price - resistance) <= tolerance
        or abs(close_price - resistance) <= tolerance
        or (high_price >= resistance - tolerance and close_price <= resistance)
    )


def _candle_direction_from_prices(open_price: float, high_price: float, low_price: float, close_price: float) -> str:
    candle_range = max(high_price - low_price, 0.000001)
    if abs(close_price - open_price) <= candle_range * 0.1:
        return "NEUTRAL"
    if close_price > open_price and close_price >= low_price + (candle_range * 0.5):
        return "BULLISH"
    if close_price < open_price and close_price <= low_price + (candle_range * 0.5):
        return "BEARISH"
    return "NEUTRAL"


def _pattern_direction(pattern: str, fallback_direction: str) -> str:
    if pattern in _BULLISH_CANDLE_PATTERNS:
        return "BULLISH"
    if pattern in _BEARISH_CANDLE_PATTERNS:
        return "BEARISH"
    if pattern in _NEUTRAL_CANDLE_PATTERNS:
        return "NEUTRAL" if pattern != "NONE" else fallback_direction
    return fallback_direction


def detect_candle_pattern(row: Dict[str, Any], previous_rows: Sequence[Dict[str, Any]] | None = None) -> Tuple[str, str]:
    numbers = _candle_numbers(row)
    if numbers is None:
        return "-", "-"
    open_price, high_price, low_price, close_price = numbers
    candle_range = max(high_price - low_price, 0.000001)
    body = abs(close_price - open_price)
    upper_wick = high_price - max(open_price, close_price)
    lower_wick = min(open_price, close_price) - low_price
    fallback_direction = _candle_direction_from_prices(open_price, high_price, low_price, close_price)
    previous = list(previous_rows or [])

    def prev_numbers(offset: int) -> Optional[Tuple[float, float, float, float]]:
        if len(previous) < abs(offset):
            return None
        return _candle_numbers(previous[offset])

    prev = prev_numbers(-1)
    if prev is not None:
        prev_open, prev_high, prev_low, prev_close = prev
        prev_body = abs(prev_close - prev_open)
        prev_midpoint = (prev_open + prev_close) / 2.0
        if prev_close < prev_open and close_price > open_price and open_price <= prev_close and close_price >= prev_open:
            return "BULLISH_ENGULFING", "BULLISH"
        if prev_close > prev_open and close_price < open_price and open_price >= prev_close and close_price <= prev_open:
            return "BEARISH_ENGULFING", "BEARISH"
        if prev_close < prev_open and close_price > open_price and open_price >= prev_close and close_price <= prev_open and body < prev_body:
            return "BULLISH_HARAMI", "BULLISH"
        if prev_close > prev_open and close_price < open_price and open_price <= prev_close and close_price >= prev_open and body < prev_body:
            return "BEARISH_HARAMI", "BEARISH"
        if prev_close < prev_open and close_price > open_price and open_price < prev_close and prev_midpoint < close_price < prev_open:
            return "PIERCING_LINE", "BULLISH"
        if prev_close > prev_open and close_price < open_price and open_price > prev_close and prev_midpoint > close_price > prev_open:
            return "DARK_CLOUD_COVER", "BEARISH"
        if len(previous) >= 2:
            first = prev_numbers(-2)
            if first is not None:
                first_open, _first_high, _first_low, first_close = first
                middle_body = prev_body
                first_body = abs(first_close - first_open)
                if first_close < first_open and middle_body <= first_body * 0.45 and close_price > open_price and close_price > ((first_open + first_close) / 2.0):
                    return "MORNING_STAR", "BULLISH"
                if first_close > first_open and middle_body <= first_body * 0.45 and close_price < open_price and close_price < ((first_open + first_close) / 2.0):
                    return "EVENING_STAR", "BEARISH"
                if first_close < first_open and prev_high < max(first_open, first_close) and prev_low > min(first_open, first_close) and close_price > prev_high:
                    return "THREE_INSIDE_UP", "BULLISH"

    if len(previous) >= 2:
        last_three = [*previous[-2:], row]
        nums = [_candle_numbers(item) for item in last_three]
        if all(item is not None for item in nums):
            triples = [item for item in nums if item is not None]
            bullish = all(item[3] > item[0] for item in triples)
            bearish = all(item[3] < item[0] for item in triples)
            strong_bodies = all(abs(item[3] - item[0]) / max(item[1] - item[2], 0.000001) >= 0.5 for item in triples)
            closes = [item[3] for item in triples]
            if bullish and strong_bodies and closes[0] < closes[1] < closes[2]:
                return "THREE_WHITE_SOLDIERS", "BULLISH"
            if bearish and strong_bodies and closes[0] > closes[1] > closes[2]:
                return "THREE_BLACK_CROWS", "BEARISH"

    if body <= candle_range * 0.1:
        if lower_wick >= candle_range * 0.6 and upper_wick <= candle_range * 0.15:
            return "DRAGONFLY_DOJI", "BULLISH"
        return "DOJI", "NEUTRAL"
    if body <= candle_range * 0.3 and upper_wick >= candle_range * 0.2 and lower_wick >= candle_range * 0.2:
        return "SPINNING_TOP", "NEUTRAL"
    if close_price > open_price and body / candle_range >= 0.85:
        return "BULLISH_MARUBOZU", "BULLISH"
    if close_price < open_price and body / candle_range >= 0.85:
        return "BEARISH_MARUBOZU", "BEARISH"
    if lower_wick >= max(body * 2.0, candle_range * 0.45) and upper_wick <= max(body, candle_range * 0.15):
        return ("HAMMER", "BULLISH") if close_price >= open_price else ("HANGING_MAN", "BEARISH")
    if upper_wick >= max(body * 2.0, candle_range * 0.45) and lower_wick <= max(body, candle_range * 0.15):
        return ("INVERTED_HAMMER", "BULLISH") if close_price >= open_price else ("SHOOTING_STAR", "BEARISH")
    return "NONE", _pattern_direction("NONE", fallback_direction)


def _flag_gt(value: Any, threshold: float) -> str:
    number = _to_float(value)
    if number is None:
        return "-"
    return "Y" if number > threshold else "N"


def _flag_price_gt(close_price: Any, indicator_value: Any) -> str:
    close = _to_float(close_price)
    indicator = _to_float(indicator_value)
    if close is None or indicator is None:
        return "-"
    return "Y" if close > indicator else "N"


def _flag_volume_gt(volume: Any, volume_sma20: Any) -> str:
    latest_volume = _to_float(volume)
    average_volume = _to_float(volume_sma20)
    if latest_volume is None or average_volume is None:
        return "-"
    return "Y" if latest_volume > average_volume else "N"


def _normalize_trend(value: Any) -> str:
    token = str(value or "").strip().upper()
    if not token:
        return "-"
    if "UPTREND" in token:
        return "UPTREND"
    if "DOWNTREND" in token:
        return "DOWNTREND"
    if token in {"RANGE", "RANGE BOUND", "RANGEBOUND", "ACCUMULATION", "CONSOLIDATION", "SIDEWAYS"}:
        return "CONSOLIDATION"
    return "-"


def calculate_prudvi_trend_score(row: Dict[str, Any]) -> int:
    score = 0
    score += 15 if row.get("SUPPORT_REVERSAL") == "Y" else 0
    score += 10 if row.get("SUPPORT_REACTION") == "BOUNCE" else 0
    score += 10 if row.get("CANDLE_DIRECTION") == "BULLISH" else 0
    score += 10 if row.get("BULLISH_CANDLE") == "Y" else 0
    score += 10 if row.get("EMA_GT_20") == "Y" else 0
    score += 10 if row.get("EMA_GT_50") == "Y" else 0
    score += 10 if row.get("RSI_GT_50") == "Y" else 0
    score += 10 if row.get("ADX_GT_25") == "Y" else 0
    score += 10 if row.get("MACD_GT_0") == "Y" else 0
    score += 5 if row.get("VOLUME_GT_20") == "Y" else 0
    score += 5 if row.get("DELIVERY_GT_60") == "Y" else 0
    return max(0, min(100, int(round((score / 105.0) * 100.0))))


def _trend_score(row: Dict[str, Any]) -> int:
    return calculate_prudvi_trend_score(row)


def _fetch_manual_sr_level_map(symbols: Optional[Iterable[Any]] = None) -> Dict[str, Dict[str, Any]]:
    requested_symbols = sorted({
        _normalize_symbol_token(symbol)
        for symbol in (symbols or [])
        if _normalize_symbol_token(symbol)
    })
    table = _qualified_manual_sr_table()
    symbol_expr = _normalized_symbol_expr("SYMBOL")
    sql = f"""
        SELECT SYMBOL,
               SR_LEVEL
          FROM {table}
         WHERE {_tf_filter_clause()}
    """
    binds: Dict[str, Any] = {}
    if requested_symbols:
        binds = {f"sym_{index}": symbol for index, symbol in enumerate(requested_symbols)}
        placeholders = ", ".join(f":sym_{index}" for index in range(len(requested_symbols)))
        sql += f" AND {symbol_expr} IN ({placeholders})"
    sql += " ORDER BY SYMBOL ASC, SR_LEVEL ASC"

    grouped: Dict[str, Dict[str, Any]] = {}
    with pool.acquire() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, binds)
            rows = fetchall_dict(cur)

    for row in rows:
        raw_symbol = row.get("symbol") or row.get("SYMBOL")
        symbol = _normalize_symbol_token(raw_symbol)
        parsed_levels = parse_manual_sr_levels(row.get("sr_level") or row.get("SR_LEVEL"))
        if not symbol or not parsed_levels:
            continue
        bucket = grouped.setdefault(symbol, {"symbol": symbol, "levels": [], "levelTexts": []})
        for level in parsed_levels:
            level_text = _format_decimal(level)
            if level_text in bucket["levelTexts"]:
                continue
            bucket["levels"].append(float(level))
            bucket["levelTexts"].append(level_text)

    for bucket in grouped.values():
        pairs = sorted(zip(bucket["levels"], bucket["levelTexts"]), key=lambda item: item[0])
        bucket["levels"] = [pair[0] for pair in pairs]
        bucket["levelTexts"] = [pair[1] for pair in pairs]
    return grouped


def fetch_manual_sr_level_map(symbols: Optional[Iterable[Any]] = None) -> Dict[str, Dict[str, Any]]:
    return _fetch_manual_sr_level_map(symbols)


def _split_support_resistance(levels: Sequence[float], close_price: Optional[float]) -> Tuple[List[float], List[float]]:
    support_candidates, resistance_candidates = classify_sr_candidates(levels, close_price)
    support = support_candidates[:3]
    resistance = resistance_candidates[:3]
    return support, resistance


def _format_levels(levels: Sequence[float], prefix: str = "") -> str:
    if not levels:
        return "-"
    normalized_prefix = str(prefix or "").strip().upper()
    if normalized_prefix:
        return ", ".join(f"{normalized_prefix}{index} {_format_decimal(level)}" for index, level in enumerate(levels, start=1))
    return ", ".join(_format_decimal(level) for level in levels)


def _support_hold(close_price: Optional[float], low_price: Optional[float], support_levels: Sequence[float]) -> bool:
    if close_price is None or low_price is None or close_price <= 0 or not support_levels:
        return False
    nearest_support = max((level for level in support_levels if level <= close_price), default=None)
    if nearest_support is None or nearest_support <= 0:
        return False
    tolerance = _sr_tolerance(nearest_support)
    low_distance = abs(low_price - nearest_support)
    close_distance_pct = (close_price - nearest_support) / close_price * 100.0
    return low_distance <= tolerance or (0 <= close_distance_pct <= _SR_TOLERANCE_PCT)


def _score_support_candidate(
    level: float,
    current_price: float,
    candles: Sequence[Dict[str, Any]],
    delivery_pct: Any = None,
) -> Dict[str, Any]:
    tolerance = _sr_tolerance(level, candles)
    score = 0
    touches = 0
    bounces = 0
    volume_hits = 0
    bullish_hits = 0
    recent_touch_index: Optional[int] = None

    if level <= current_price:
        score += 5
    distance_pct = ((current_price - level) / current_price * 100.0) if current_price else 999.0
    if 0 <= distance_pct <= max(12.0, _SR_TOLERANCE_PCT * 6.0):
        score += 10

    candle_list = list(candles or [])
    for idx, candle in enumerate(candle_list):
        if not _is_near_support(candle, level, tolerance):
            continue
        touches += 1
        recent_touch_index = idx
        current_close = _to_float(candle.get("close"))
        future = candle_list[idx + 1:idx + 1 + _REACTION_LOOKAHEAD_CANDLES]
        bounced = any(
            _to_float(item.get("close")) is not None
            and current_close is not None
            and _to_float(item.get("close")) > max(current_close, level)
            for item in future
        )
        if bounced:
            bounces += 1
        volume_avg = _row_volume_avg(candle_list, idx)
        if _volume_confirms(candle.get("volume"), volume_avg):
            volume_hits += 1
        pattern, direction = detect_candle_pattern(candle, candle_list[:idx])
        if pattern in _BULLISH_CANDLE_PATTERNS or direction == "BULLISH":
            bullish_hits += 1

    if touches:
        score += min(10, touches * 2)
    if bounces:
        score += 20
    if volume_hits:
        score += 15
    if _delivery_confirms(delivery_pct):
        score += 15
    if bullish_hits:
        score += 15
    if recent_touch_index is not None and recent_touch_index >= max(0, len(candle_list) - 30):
        score += 10
    if current_price >= level:
        score += 5

    return {
        "level": level,
        "score": score,
        "touches": touches,
        "reactions": bounces,
        "distancePct": distance_pct,
        "recentIndex": recent_touch_index,
    }


def _score_resistance_candidate(
    level: float,
    current_price: float,
    candles: Sequence[Dict[str, Any]],
    delivery_pct: Any = None,
) -> Dict[str, Any]:
    tolerance = _sr_tolerance(level, candles)
    score = 0
    touches = 0
    rejections = 0
    volume_hits = 0
    bearish_hits = 0
    recent_touch_index: Optional[int] = None

    if level > current_price:
        score += 5
    distance_pct = ((level - current_price) / current_price * 100.0) if current_price else 999.0
    if 0 <= distance_pct <= max(12.0, _SR_TOLERANCE_PCT * 6.0):
        score += 10

    candle_list = list(candles or [])
    for idx, candle in enumerate(candle_list):
        if not _is_near_resistance(candle, level, tolerance):
            continue
        touches += 1
        recent_touch_index = idx
        current_close = _to_float(candle.get("close"))
        future = candle_list[idx + 1:idx + 1 + _REACTION_LOOKAHEAD_CANDLES]
        rejected = any(
            _to_float(item.get("close")) is not None
            and current_close is not None
            and _to_float(item.get("close")) < min(current_close, level)
            for item in future
        )
        if rejected:
            rejections += 1
        volume_avg = _row_volume_avg(candle_list, idx)
        if _volume_confirms(candle.get("volume"), volume_avg):
            volume_hits += 1
        pattern, direction = detect_candle_pattern(candle, candle_list[:idx])
        if pattern in _BEARISH_CANDLE_PATTERNS or direction == "BEARISH":
            bearish_hits += 1

    if touches:
        score += min(10, touches * 2)
    if rejections:
        score += 20
    if volume_hits:
        score += 15
    if _delivery_confirms(delivery_pct):
        score += 15
    if bearish_hits:
        score += 15
    if recent_touch_index is not None and recent_touch_index >= max(0, len(candle_list) - 30):
        score += 10
    if current_price < level:
        score += 5

    return {
        "level": level,
        "score": score,
        "touches": touches,
        "reactions": rejections,
        "distancePct": distance_pct,
        "recentIndex": recent_touch_index,
    }


def pick_active_support(
    symbol: str,
    current_price: Any,
    manual_sr_levels: Sequence[float],
    historical_rows: Sequence[Dict[str, Any]],
    delivery_pct: Any = None,
) -> Optional[Dict[str, Any]]:
    price = _to_float(current_price)
    if price is None or price <= 0:
        return None
    support_candidates, _resistance_candidates = classify_sr_candidates(manual_sr_levels, price)
    scored = [
        _score_support_candidate(level, price, historical_rows, delivery_pct)
        for level in support_candidates
    ]
    valid = [item for item in scored if int(item.get("score") or 0) > 0 and int(item.get("touches") or 0) > 0]
    if not valid:
        return None
    valid.sort(key=lambda item: (-int(item["score"]), abs(price - float(item["level"])), -float(item["level"])))
    return valid[0]


def pick_active_resistance(
    symbol: str,
    current_price: Any,
    manual_sr_levels: Sequence[float],
    historical_rows: Sequence[Dict[str, Any]],
    delivery_pct: Any = None,
) -> Optional[Dict[str, Any]]:
    price = _to_float(current_price)
    if price is None or price <= 0:
        return None
    _support_candidates, resistance_candidates = classify_sr_candidates(manual_sr_levels, price)
    scored = [
        _score_resistance_candidate(level, price, historical_rows, delivery_pct)
        for level in resistance_candidates
    ]
    valid = [item for item in scored if int(item.get("score") or 0) > 0 and int(item.get("touches") or 0) > 0]
    if not valid:
        return None
    valid.sort(key=lambda item: (-int(item["score"]), abs(float(item["level"]) - price), float(item["level"])))
    return valid[0]


def _select_ranked_manual_levels(
    scored_levels: Sequence[Dict[str, Any]],
    fallback_levels: Sequence[float],
    current_price: float,
    limit: int,
    *,
    kind: str,
) -> List[Dict[str, Any]]:
    if limit <= 0:
        return []
    ranked: List[Dict[str, Any]] = []
    seen: set[float] = set()
    valid = [item for item in scored_levels if int(item.get("score") or 0) > 0 and int(item.get("touches") or 0) > 0]
    if kind == "support":
        valid.sort(key=lambda item: (-int(item["score"]), abs(current_price - float(item["level"])), -float(item["level"])))
    else:
        valid.sort(key=lambda item: (-int(item["score"]), abs(float(item["level"]) - current_price), float(item["level"])))
    for item in valid:
        level = _to_float(item.get("level"))
        if level is None or level in seen:
            continue
        ranked.append(item)
        seen.add(level)
        if len(ranked) >= limit:
            return ranked
    for level in fallback_levels:
        level_num = _to_float(level)
        if level_num is None or level_num in seen:
            continue
        ranked.append({
            "level": float(level_num),
            "score": 0,
            "touches": 0,
            "reactions": 0,
            "distancePct": abs(current_price - float(level_num)) / current_price * 100.0 if current_price else None,
            "recentIndex": None,
        })
        seen.add(level_num)
        if len(ranked) >= limit:
            break
    return ranked


def select_ranked_support_levels(
    symbol: str,
    current_price: Any,
    manual_sr_levels: Sequence[float],
    historical_rows: Sequence[Dict[str, Any]],
    delivery_pct: Any = None,
    limit: int = 3,
) -> List[Dict[str, Any]]:
    price = _to_float(current_price)
    if price is None or price <= 0 or limit <= 0:
        return []
    support_candidates, _resistance_candidates = classify_sr_candidates(manual_sr_levels, price)
    scored = [
        _score_support_candidate(level, price, historical_rows, delivery_pct)
        for level in support_candidates
    ]
    return _select_ranked_manual_levels(scored, support_candidates, price, limit, kind="support")


def select_ranked_resistance_levels(
    symbol: str,
    current_price: Any,
    manual_sr_levels: Sequence[float],
    historical_rows: Sequence[Dict[str, Any]],
    delivery_pct: Any = None,
    limit: int = 3,
) -> List[Dict[str, Any]]:
    price = _to_float(current_price)
    if price is None or price <= 0 or limit <= 0:
        return []
    _support_candidates, resistance_candidates = classify_sr_candidates(manual_sr_levels, price)
    scored = [
        _score_resistance_candidate(level, price, historical_rows, delivery_pct)
        for level in resistance_candidates
    ]
    return _select_ranked_manual_levels(scored, resistance_candidates, price, limit, kind="resistance")


def _find_support_candle(
    active_support: Any,
    recent_rows: Sequence[Dict[str, Any]],
    all_rows: Sequence[Dict[str, Any]],
) -> Optional[Tuple[int, Dict[str, Any], str, str]]:
    support = _to_float(active_support)
    if support is None or support <= 0:
        return None
    tolerance = _sr_tolerance(support, all_rows)
    base_count = len(all_rows) - len(recent_rows)
    for offset in range(len(recent_rows) - 1, -1, -1):
        candle = recent_rows[offset]
        if not _is_near_support(candle, support, tolerance):
            continue
        absolute_index = max(0, base_count + offset)
        pattern, direction = detect_candle_pattern(candle, list(all_rows)[:absolute_index])
        return absolute_index, candle, pattern, direction
    return None


def detect_support_reaction(
    active_support: Any,
    recent_rows: Sequence[Dict[str, Any]],
    volume_avg: Any = None,
    delivery_pct: Any = None,
) -> Tuple[str, str]:
    support = _to_float(active_support)
    rows = list(recent_rows or [])
    if support is None or support <= 0 or not rows:
        return "-", "-"
    latest = rows[-1]
    latest_numbers = _candle_numbers(latest)
    if latest_numbers is None:
        return "-", "-"
    latest_close = latest_numbers[3]
    tolerance = _sr_tolerance(support, rows)
    support_entry: Optional[Tuple[int, Dict[str, Any], str, str]] = None
    for offset in range(len(rows) - 1, -1, -1):
        candle = rows[offset]
        if _is_near_support(candle, support, tolerance):
            pattern, direction = detect_candle_pattern(candle, rows[:offset])
            support_entry = (offset, candle, pattern, direction)
            break
    if support_entry is None:
        return "NO_REACTION", "N"

    idx, support_candle, pattern, direction = support_entry
    numbers = _candle_numbers(support_candle)
    if numbers is None:
        return "-", "-"
    open_price, _high_price, _low_price, close_price = numbers
    following = rows[idx + 1:]
    next_confirms = True
    if following:
        next_confirms = any(
            _to_float(item.get("close")) is not None and _to_float(item.get("close")) > close_price
            for item in following
        )
    high_volume = _volume_confirms(support_candle.get("volume"), volume_avg) or _volume_confirms(latest.get("volume"), volume_avg)
    confirmed = high_volume or _delivery_confirms(delivery_pct)

    if (
        close_price > support
        and (close_price > open_price or pattern in _BULLISH_CANDLE_PATTERNS)
        and next_confirms
        and confirmed
    ):
        return "BOUNCE", "Y"
    if (
        close_price < support
        and (pattern in _BEARISH_CANDLE_PATTERNS or direction == "BEARISH")
        and high_volume
        and (not following or any(_to_float(item.get("close")) is not None and _to_float(item.get("close")) < support for item in following))
    ):
        return "BREAKDOWN", "N"
    if latest_close >= support and abs(latest_close - support) <= max(tolerance * 3.0, support * 0.03):
        return "HOLDING", "N"
    return "NO_REACTION", "N"


def _empty_row(symbol: str, sr_levels: Dict[str, Any], latest_trade_date: Optional[str] = None) -> Dict[str, Any]:
    row = {
        "SYMBOL": symbol,
        "ATH": None,
        "PRICE": None,
        "GAP": None,
        "GAP_DISPLAY": "-",
        "LTC_DATE": latest_trade_date,
        "SUPPORT": "-",
        "RESISTANCE": "-",
        "SUPPORT_REACTION": "-",
        "SUPPORT_CANDLE": "-",
        "CANDLE_DIRECTION": "-",
        "SUPPORT_REVERSAL": "-",
        "BULLISH_CANDLE": "-",
        "EMA_GT_20": "-",
        "EMA_GT_50": "-",
        "RSI_GT_50": "-",
        "ADX_GT_25": "-",
        "MACD_GT_0": "-",
        "VOLUME_GT_20": "-",
        "DELIVERY_GT_60": "-",
        "TREND": "-",
        "TREND_SCORE": 0,
    }
    return row


def _evaluate_symbol(
    symbol: str,
    candles: Sequence[Dict[str, Any]] | None,
    sr_levels: Dict[str, Any],
    latest_trade_date: Optional[str],
    delivery_row: Optional[Dict[str, Any]],
    ath_row: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not candles:
        return _empty_row(symbol, sr_levels, latest_trade_date)

    candle_list = list(candles)
    if len(candle_list) > _LOOKBACK_TRADING_DAYS:
        candle_list = candle_list[-_LOOKBACK_TRADING_DAYS:]

    latest_candle = candle_list[-1]
    latest_candle_date = _iso_date(latest_candle.get("date"))
    if latest_trade_date and latest_candle_date != latest_trade_date:
        return _empty_row(symbol, sr_levels, latest_trade_date)

    closes = [_to_float(item.get("close")) for item in candle_list]
    clean_closes = [value for value in closes if value is not None]
    latest_close = _to_float(latest_candle.get("close"))
    latest_open = _to_float(latest_candle.get("open"))
    latest_low = _to_float(latest_candle.get("low"))
    latest_volume = _to_float(latest_candle.get("volume"))
    ath_value = _to_float((ath_row or {}).get("ath"))
    ath_date = (ath_row or {}).get("ath_date")
    gap_percent = _gap_pct(latest_close, ath_value)

    ema20 = calculate_ema(clean_closes, 20) if len(clean_closes) >= 20 else None
    ema50 = calculate_ema(clean_closes, 50) if len(clean_closes) >= 50 else None
    rsi_values = _rsi_series(clean_closes, 14)
    rsi14 = rsi_values[-1] if rsi_values else None
    macd_state = _macd_series(clean_closes) if len(clean_closes) >= 26 else {"macd": []}
    macd_value = macd_state["macd"][-1] if macd_state.get("macd") else None
    adx_state = _adx_series(candle_list, 14)
    adx14 = adx_state["adx"][-1] if adx_state.get("adx") else None
    volume_sma20 = _volume_sma20(candle_list)
    delivery_pct = _to_float((delivery_row or {}).get("delivery_pct"))

    manual_levels = sr_levels.get("levels") or []
    support_candidates, resistance_candidates = classify_sr_candidates(manual_levels, latest_close)
    support_level = support_candidates[0] if support_candidates else None
    resistance_level = resistance_candidates[0] if resistance_candidates else None
    recent_support_rows = candle_list[-_SUPPORT_CANDLE_LOOKBACK:]
    support_candle = "-"
    candle_direction = "-"
    support_reaction = "-"
    support_reversal = "-"
    bullish_candle = "-"
    if support_level is not None:
        support_entry = _find_support_candle(support_level, recent_support_rows, candle_list)
        if support_entry is not None:
            _support_idx, support_candle_row, support_candle, candle_direction = support_entry
            support_holds = bool(_to_float(support_candle_row.get("close")) is not None and _to_float(support_candle_row.get("close")) >= support_level)
            bullish_candle = "Y" if support_candle in _BULLISH_CANDLE_PATTERNS and candle_direction == "BULLISH" and support_holds else "N"
        elif candle_list:
            bullish_candle = "N"
        support_reaction, support_reversal = detect_support_reaction(
            support_level,
            recent_support_rows,
            volume_sma20,
            delivery_pct,
        )
    support_display = _format_levels([support_level], "") if support_level is not None else "-"
    resistance_display = _format_levels([resistance_level], "") if resistance_level is not None else "-"

    trend = "-"
    if len(candle_list) >= 40:
        try:
            pivots = detect_swing_pivots(candle_list[-160:], window=3, atr_period=14, min_atr_multiple=0.75)
            trend = _normalize_trend((classify_trend_structure(candle_list[-160:], pivots) or {}).get("status"))
        except Exception:
            _logger.warning("Prudvi trend classification failed for symbol=%s", symbol, exc_info=True)

    ema_gt_20 = _flag_price_gt(latest_close, ema20)
    ema_gt_50 = _flag_price_gt(latest_close, ema50)
    rsi_gt_50 = _flag_gt(rsi14, 50)
    adx_gt_25 = _flag_gt(adx14, 25)
    macd_gt_0 = _flag_gt(macd_value, 0)
    volume_gt_20 = _flag_volume_gt(latest_volume, volume_sma20)
    delivery_gt_60 = _flag_gt(delivery_pct, 60)
    if support_reversal == "Y":
        early_uptrend_reversal = trend == "UPTREND" or ema_gt_20 == "Y" or ema_gt_50 == "Y"
        if not (
            support_reaction == "BOUNCE"
            and bullish_candle == "Y"
            and candle_direction == "BULLISH"
            and latest_close is not None
            and support_level is not None
            and latest_close >= support_level
            and (volume_gt_20 == "Y" or delivery_gt_60 == "Y")
            and early_uptrend_reversal
        ):
            support_reversal = "N"

    row = {
        "SYMBOL": symbol,
        "ATH": _round_or_none(ath_value, 2),
        "ATH_DATE": ath_date,
        "ath": _round_or_none(ath_value, 2),
        "ath_date": ath_date,
        "PRICE": _round_or_none(latest_close, 2),
        "price": _round_or_none(latest_close, 2),
        "GAP": _round_or_none(gap_percent, 2),
        "GAP_SORT": _round_or_none(gap_percent, 4),
        "GAP_DISPLAY": _format_gap(gap_percent),
        "gap": _format_gap(gap_percent),
        "gapSort": _round_or_none(gap_percent, 4),
        "LTC_DATE": latest_candle_date,
        "ltcDate": latest_candle_date,
        "SUPPORT": support_display,
        "RESISTANCE": resistance_display,
        "SUPPORT_REACTION": support_reaction,
        "SUPPORT_CANDLE": support_candle,
        "CANDLE_DIRECTION": candle_direction,
        "SUPPORT_REVERSAL": support_reversal,
        "BULLISH_CANDLE": bullish_candle,
        "EMA_GT_20": ema_gt_20,
        "EMA_GT_50": ema_gt_50,
        "RSI_GT_50": rsi_gt_50,
        "ADX_GT_25": adx_gt_25,
        "MACD_GT_0": macd_gt_0,
        "VOLUME_GT_20": volume_gt_20,
        "DELIVERY_GT_60": delivery_gt_60,
        "TREND": trend,
        "TREND_SCORE": 0,
        "TRADING_DATE": latest_candle_date,
        "CLOSE": _round_or_none(latest_close, 2),
        "EMA20": _round_or_none(ema20, 2),
        "EMA50": _round_or_none(ema50, 2),
        "RSI14": _round_or_none(rsi14, 2),
        "ADX14": _round_or_none(adx14, 2),
        "MACD": _round_or_none(macd_value, 4),
        "VOLUME": int(round(latest_volume)) if latest_volume is not None else None,
        "VOLUME_SMA20": _round_or_none(volume_sma20, 2),
        "DELIVERY_PCT": _round_or_none(delivery_pct, 2),
    }
    row["TREND_SCORE"] = _trend_score(row)
    return row


def _fetch_latest_trade_date() -> Optional[str]:
    latest_date = fetch_latest_trade_date_from_oracle()
    return latest_date.isoformat() if latest_date is not None else None


def _snapshot_path() -> str:
    os.makedirs(_SNAPSHOT_DIR, exist_ok=True)
    return os.path.join(_SNAPSHOT_DIR, _SNAPSHOT_FILE)


def _is_valid_snapshot(payload: Optional[Dict[str, Any]], latest_trade_date: Optional[str]) -> bool:
    if not isinstance(payload, dict):
        return False
    if not isinstance(payload.get("data"), list):
        return False
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    if meta.get("cacheVersion") != _CACHE_VERSION:
        return False
    snapshot_date = str(meta.get("tradingDate") or "").strip()
    if latest_trade_date and snapshot_date != latest_trade_date:
        return False
    return True


def _is_compatible_legacy_snapshot(payload: Optional[Dict[str, Any]], latest_trade_date: Optional[str]) -> bool:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return False
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    snapshot_date = str(meta.get("tradingDate") or "").strip()
    return bool(not latest_trade_date or snapshot_date == latest_trade_date)


def _with_prudvi_field_defaults(payload: Dict[str, Any]) -> Dict[str, Any]:
    upgraded = dict(payload)
    rows = []
    for row in upgraded.get("data") or []:
        if not isinstance(row, dict):
            continue
        next_row = dict(row)
        next_row.setdefault("SUPPORT_REACTION", "-")
        next_row.setdefault("SUPPORT_CANDLE", "-")
        next_row.setdefault("CANDLE_DIRECTION", "-")
        next_row.setdefault("SUPPORT_REVERSAL", "-")
        rows.append(next_row)
    meta = dict(upgraded.get("meta") or {})
    meta["cacheVersion"] = _CACHE_VERSION
    meta["legacySnapshotUpgraded"] = True
    upgraded["data"] = rows
    upgraded["meta"] = meta
    upgraded["status"] = upgraded.get("status") or "success"
    return upgraded


def _load_snapshot_payload(latest_trade_date: Optional[str]) -> Optional[Dict[str, Any]]:
    snapshot = load_json_snapshot(_snapshot_path())
    if _is_valid_snapshot(snapshot, latest_trade_date):
        return snapshot
    if _is_compatible_legacy_snapshot(snapshot, latest_trade_date):
        return _with_prudvi_field_defaults(snapshot)
    return None


def _mark_payload(
    payload: Dict[str, Any],
    *,
    cache_state: str,
    started: float,
    cached: bool,
    refreshing: bool = False,
    stale: bool = False,
) -> Dict[str, Any]:
    response = dict(payload)
    meta = dict(response.get("meta") or {})
    meta["cacheState"] = cache_state
    meta["durationMs"] = int((time.perf_counter() - started) * 1000)
    if refreshing:
        meta["refreshing"] = True
    if stale:
        meta["stale"] = True
    response["meta"] = meta
    response["cached"] = cached
    if refreshing:
        response["refreshing"] = True
    if stale:
        response["stale"] = True
    return response


def _refreshing_placeholder(
    *,
    latest_trade_date: Optional[str],
    started: float,
    refresh_scheduled: bool,
) -> Dict[str, Any]:
    return {
        "data": [],
        "status": "success",
        "cached": False,
        "refreshing": True,
        "stale": True,
        "meta": {
            "tradingDate": latest_trade_date,
            "rows": 0,
            "manualSrSymbols": 0,
            "cacheVersion": _CACHE_VERSION,
            "cacheState": "COLD_START_REFRESHING",
            "refreshing": True,
            "refreshScheduled": refresh_scheduled,
            "stale": True,
            "durationMs": int((time.perf_counter() - started) * 1000),
        },
    }


def _build_prudvi_strategy_payload(latest_trade_date: Optional[str]) -> Dict[str, Any]:
    started = time.perf_counter()
    manual_started = time.perf_counter()
    manual_levels = _fetch_manual_sr_level_map()
    manual_ms = int((time.perf_counter() - manual_started) * 1000)
    if not manual_levels or not latest_trade_date:
        payload = {
            "data": [],
            "status": "success",
            "meta": {
                "tradingDate": latest_trade_date,
                "rows": 0,
                "manualSrSymbols": len(manual_levels),
                "cacheVersion": _CACHE_VERSION,
                "cacheState": "MISS",
                "manualSrLoadMs": manual_ms,
                "durationMs": int((time.perf_counter() - started) * 1000),
            },
        }
        return payload

    oracle_started = time.perf_counter()
    raw_series = fetch_recent_ohlc_series_from_oracle(trading_days=_LOOKBACK_TRADING_DAYS)
    oracle_ms = int((time.perf_counter() - oracle_started) * 1000)

    transform_started = time.perf_counter()
    series_by_symbol = aggregate_ohlc_series_by_timeframe(raw_series, "daily")
    normalized_series = {
        _normalize_symbol_token(symbol): candles
        for symbol, candles in series_by_symbol.items()
        if _normalize_symbol_token(symbol)
    }
    transform_ms = int((time.perf_counter() - transform_started) * 1000)

    symbols = sorted(manual_levels.keys())
    delivery_started = time.perf_counter()
    delivery_map = _fetch_latest_delivery_pct_map(symbols)
    delivery_ms = int((time.perf_counter() - delivery_started) * 1000)

    ath_started = time.perf_counter()
    try:
        ath_map = get_all_time_high_for_symbols(
            symbols,
            as_of_date=_parse_iso_date(latest_trade_date),
            include_date=True,
            endpoint="/api/strategy/prudvi",
        )
    except Exception:
        _logger.warning("Prudvi ATH lookup failed; continuing with missing ATH values", exc_info=True)
        ath_map = {}
    ath_ms = int((time.perf_counter() - ath_started) * 1000)

    compute_started = time.perf_counter()
    rows = [
        _evaluate_symbol(
            symbol,
            normalized_series.get(symbol),
            manual_levels[symbol],
            latest_trade_date,
            delivery_map.get(symbol),
            ath_map.get(symbol),
        )
        for symbol in symbols
    ]
    rows.sort(key=lambda item: (-int(item.get("TREND_SCORE") or 0), str(item.get("SYMBOL") or "")))
    for index, row in enumerate(rows, start=1):
        row["S_NO"] = index
    compute_ms = int((time.perf_counter() - compute_started) * 1000)

    payload = {
        "data": rows,
        "status": "success",
        "meta": {
            "tradingDate": latest_trade_date,
            "rows": len(rows),
            "manualSrSymbols": len(manual_levels),
            "source": "PRICE_ACTION_SR_LEVELS_MANUALLY",
            "cacheVersion": _CACHE_VERSION,
            "cacheState": "MISS",
            "manualSrLoadMs": manual_ms,
            "oracleLoadMs": oracle_ms,
            "transformMs": transform_ms,
            "deliveryLoadMs": delivery_ms,
            "athLoadMs": ath_ms,
            "computeMs": compute_ms,
            "durationMs": int((time.perf_counter() - started) * 1000),
        },
    }
    _logger.info(
        "prudvi_strategy latest_trade_date=%s manual_symbols=%s rows_returned=%s cache=MISS manual_ms=%s oracle_ms=%s transform_ms=%s delivery_ms=%s ath_ms=%s compute_ms=%s duration_ms=%s",
        latest_trade_date,
        len(manual_levels),
        len(rows),
        manual_ms,
        oracle_ms,
        transform_ms,
        delivery_ms,
        ath_ms,
        compute_ms,
        payload["meta"]["durationMs"],
    )
    return payload


def _build_payload_and_persist(latest_trade_date: Optional[str]) -> Dict[str, Any]:
    payload = _build_prudvi_strategy_payload(latest_trade_date)
    try:
        from services import nse_mcap_service as nse_mcap_svc

        payload = nse_mcap_svc.enrich_payload_marketcap_index(
            payload,
            row_keys=("data",),
            symbol_keys=("SYMBOL", "symbol"),
        )
    except Exception:
        _logger.warning("Prudvi market-cap enrichment failed during snapshot persist", exc_info=True)
    save_json_snapshot(_snapshot_path(), payload)
    return payload


def _schedule_refresh(cache_key: str, latest_trade_date: Optional[str]) -> None:
    background_refresh(_CACHE, cache_key, lambda: _build_payload_and_persist(latest_trade_date))


def fetch_prudvi_strategy_scan(*, refresh: bool = False) -> Dict[str, Any]:
    started = time.perf_counter()
    latest_trade_date = _fetch_latest_trade_date()
    cache_key = f"prudvi:{_CACHE_VERSION}:{latest_trade_date or 'none'}"

    cached = _CACHE.get(cache_key)
    if isinstance(cached, dict):
        if refresh:
            _schedule_refresh(cache_key, latest_trade_date)
            return _mark_payload(
                cached,
                cache_state="CACHE_REFRESHING",
                started=started,
                cached=True,
                refreshing=True,
            )
        return _mark_payload(cached, cache_state="HIT", started=started, cached=True)

    snapshot = _load_snapshot_payload(latest_trade_date)
    if isinstance(snapshot, dict):
        _CACHE.set(cache_key, snapshot)
        _schedule_refresh(cache_key, latest_trade_date)
        return _mark_payload(
            snapshot,
            cache_state="SNAPSHOT_REFRESHING" if refresh else "SNAPSHOT",
            started=started,
            cached=True,
            refreshing=refresh,
            stale=True,
        )

    _schedule_refresh(cache_key, latest_trade_date)
    _logger.info(
        "prudvi_strategy latest_trade_date=%s rows_returned=0 cache=COLD_START_REFRESHING duration_ms=%s",
        latest_trade_date,
        int((time.perf_counter() - started) * 1000),
    )
    return _refreshing_placeholder(
        latest_trade_date=latest_trade_date,
        started=started,
        refresh_scheduled=True,
    )


__all__ = [
    "calculate_prudvi_trend_score",
    "classify_sr_candidates",
    "detect_candle_pattern",
    "detect_support_reaction",
    "fetch_manual_sr_level_map",
    "fetch_prudvi_strategy_scan",
    "parse_manual_sr_levels",
    "pick_active_resistance",
    "pick_active_support",
    "select_ranked_resistance_levels",
    "select_ranked_support_levels",
]
