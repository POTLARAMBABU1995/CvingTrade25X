from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from math import isfinite
from statistics import fmean
from typing import Any, Dict, Iterable, List, Optional, Sequence

try:
    from ..cache import TTLCache
    from ..db import (
        fetch_latest_trade_date_from_oracle,
        fetch_ohlc_series_from_oracle,
        fetch_recent_ohlc_series_from_oracle,
    )
    from .technical_utils import (
        aggregate_ohlc_series_by_timeframe,
        calculate_ema,
        calculate_support_resistance,
        detect_higher_high_higher_low,
        detect_resistance_breakout,
        detect_swing_pivots,
    )
except ImportError:  # pragma: no cover
    from cache import TTLCache  # type: ignore
    from db import (  # type: ignore
        fetch_latest_trade_date_from_oracle,
        fetch_ohlc_series_from_oracle,
        fetch_recent_ohlc_series_from_oracle,
    )
    from services.technical_utils import (  # type: ignore
        aggregate_ohlc_series_by_timeframe,
        calculate_ema,
        calculate_support_resistance,
        detect_higher_high_higher_low,
        detect_resistance_breakout,
        detect_swing_pivots,
    )

try:  # pragma: no cover
    try:
        from ..db_pool import fetchall_dict as _db_fetchall_dict, pool as _db_pool
    except ImportError:
        from db_pool import fetchall_dict as _db_fetchall_dict, pool as _db_pool  # type: ignore
except Exception:  # pragma: no cover
    _db_fetchall_dict = None
    _db_pool = None


_logger = logging.getLogger(__name__)
_CACHE_VERSION = "v1"
_CACHE_TTL_SECONDS = max(30, int(str(os.getenv("STRONG_UPTREND_REVERSAL_CACHE_TTL", "300")).strip() or "300"))
_LOOKBACK_TRADING_DAYS = max(260, min(int(str(os.getenv("STRONG_UPTREND_REVERSAL_LOOKBACK_DAYS", "260")).strip() or "260"), 1000))
_EVALUATION_LOOKBACK_CANDLES = max(260, min(int(str(os.getenv("STRONG_UPTREND_REVERSAL_EVAL_CANDLES", str(_LOOKBACK_TRADING_DAYS))).strip() or str(_LOOKBACK_TRADING_DAYS)), 1000))
_STRUCTURE_LOOKBACK_CANDLES = max(120, min(int(str(os.getenv("STRONG_UPTREND_REVERSAL_STRUCTURE_CANDLES", "160")).strip() or "160"), _EVALUATION_LOOKBACK_CANDLES))
_DELIVERY_LOOKBACK_DAYS = max(7, min(int(str(os.getenv("STRONG_UPTREND_REVERSAL_DELIVERY_LOOKBACK_DAYS", "30")).strip() or "30"), 365))
_DELIVERY_NORMALIZED_FALLBACK_LIMIT = max(0, min(int(str(os.getenv("STRONG_UPTREND_REVERSAL_DELIVERY_FALLBACK_LIMIT", "50")).strip() or "50"), 250))
_CACHE = TTLCache(ttl_seconds=_CACHE_TTL_SECONDS, max_items=8)

_SCORE_RULES: Sequence[tuple[str, int]] = (
    ("TREND_OK", 15),
    ("EMA_SLOPE_OK", 10),
    ("RSI_OK", 10),
    ("ADX_OK", 15),
    ("MACD_OK", 10),
    ("VOLUME_OK", 10),
    ("DELIVERY_OK", 10),
    ("HH_HL_STRUCTURE", 10),
    ("SUPPORT_CONFIRMED", 5),
    ("BULLISH_REVERSAL_CANDLE", 5),
)

_REJECT_REASON_LABELS: Sequence[tuple[str, str]] = (
    ("TREND_OK", "Trend filter failed"),
    ("EMA_SLOPE_OK", "EMA slope failed"),
    ("RSI_OK", "RSI below 50"),
    ("ADX_OK", "ADX / DI confirmation failed"),
    ("MACD_OK", "MACD confirmation failed"),
    ("VOLUME_OK", "Volume below SMA20"),
    ("DELIVERY_OK", "Delivery below 40%"),
    ("HH_HL_STRUCTURE", "HH-HL structure missing"),
    ("SUPPORT_CONFIRMED", "Support confirmation failed"),
    ("BULLISH_REVERSAL_CANDLE", "Bullish reversal candle missing"),
    ("BREAKOUT_OK", "Breakout confirmation failed"),
)


def _fallback_fetchall_dict(cursor: Any) -> List[Dict[str, Any]]:
    description = getattr(cursor, "description", None) or []
    cols = [item[0].lower() for item in description]
    fetchall = getattr(cursor, "fetchall", None)
    if not callable(fetchall):
        return []
    return [dict(zip(cols, row)) for row in fetchall()]


fetchall_dict = _db_fetchall_dict or _fallback_fetchall_dict
pool = _db_pool


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _get_delivery_service_module():
    try:
        from . import delivery_service as svc  # type: ignore
        return svc
    except Exception:
        try:
            from services import delivery_service as svc  # type: ignore
            return svc
        except Exception:
            return None


def _normalize_delivery_symbol(symbol: Any) -> str:
    svc = _get_delivery_service_module()
    text = str(symbol or "").strip()
    if svc is None:
        return text.upper()
    try:
        return svc.normalize_delivery_symbol(text)
    except Exception:
        return text.upper()


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(num):
        return None
    return num


def _round_or_none(value: Any, digits: int = 2) -> Optional[float]:
    num = _to_float(value)
    return round(num, digits) if num is not None else None


def _iso_date(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return None
    return None


def _ema_series(values: Sequence[float], period: int) -> List[float]:
    clean = [float(item) for item in values if item is not None]
    if not clean:
        return []
    multiplier = 2.0 / (float(period) + 1.0)
    output: List[float] = []
    previous = clean[0]
    for value in clean:
        previous = value if not output else (value * multiplier) + (previous * (1.0 - multiplier))
        output.append(previous)
    return output


def _rsi_series(values: Sequence[float], period: int = 14) -> List[Optional[float]]:
    closes = [float(item) for item in values if item is not None]
    if len(closes) < period + 1:
        return [None] * len(closes)

    output: List[Optional[float]] = [None] * len(closes)
    gains: List[float] = []
    losses: List[float] = []
    for idx in range(1, period + 1):
        delta = closes[idx] - closes[idx - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains) / float(period)
    avg_loss = sum(losses) / float(period)
    rs = avg_gain / avg_loss if avg_loss > 0 else float("inf")
    output[period] = 100.0 - (100.0 / (1.0 + rs))

    for idx in range(period + 1, len(closes)):
        delta = closes[idx] - closes[idx - 1]
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        avg_gain = ((avg_gain * (period - 1)) + gain) / float(period)
        avg_loss = ((avg_loss * (period - 1)) + loss) / float(period)
        rs = avg_gain / avg_loss if avg_loss > 0 else float("inf")
        output[idx] = 100.0 - (100.0 / (1.0 + rs))
    return output


def _macd_series(values: Sequence[float]) -> Dict[str, List[Optional[float]]]:
    closes = [float(item) for item in values if item is not None]
    if not closes:
        return {"macd": [], "signal": [], "hist": []}
    ema12 = _ema_series(closes, 12)
    ema26 = _ema_series(closes, 26)
    macd = [fast - slow for fast, slow in zip(ema12, ema26)]
    signal = _ema_series(macd, 9)
    hist = [macd_val - signal_val for macd_val, signal_val in zip(macd, signal)]
    return {
        "macd": macd,
        "signal": signal,
        "hist": hist,
    }


def _adx_series(candles: Sequence[Dict[str, Any]], period: int = 14) -> Dict[str, List[Optional[float]]]:
    if len(candles) < period + 1:
        empty = [None] * len(candles)
        return {"adx": empty, "plus_di": empty, "minus_di": empty, "atr": empty}

    highs = [_to_float(item.get("high")) for item in candles]
    lows = [_to_float(item.get("low")) for item in candles]
    closes = [_to_float(item.get("close")) for item in candles]
    plus_dm = [0.0]
    minus_dm = [0.0]
    true_ranges = [0.0]
    for idx in range(1, len(candles)):
        high = highs[idx]
        low = lows[idx]
        prev_high = highs[idx - 1]
        prev_low = lows[idx - 1]
        prev_close = closes[idx - 1]
        if None in (high, low, prev_high, prev_low, prev_close):
            plus_dm.append(0.0)
            minus_dm.append(0.0)
            true_ranges.append(0.0)
            continue
        up_move = high - prev_high
        down_move = prev_low - low
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)
        true_ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))

    smoothed_tr = [None] * len(candles)
    smoothed_plus = [None] * len(candles)
    smoothed_minus = [None] * len(candles)
    plus_di: List[Optional[float]] = [None] * len(candles)
    minus_di: List[Optional[float]] = [None] * len(candles)
    dx: List[Optional[float]] = [None] * len(candles)
    adx: List[Optional[float]] = [None] * len(candles)

    initial_tr = sum(true_ranges[1 : period + 1])
    initial_plus = sum(plus_dm[1 : period + 1])
    initial_minus = sum(minus_dm[1 : period + 1])
    smoothed_tr[period] = initial_tr
    smoothed_plus[period] = initial_plus
    smoothed_minus[period] = initial_minus
    if initial_tr > 0:
        plus_di[period] = (initial_plus / initial_tr) * 100.0
        minus_di[period] = (initial_minus / initial_tr) * 100.0
        denom = (plus_di[period] or 0.0) + (minus_di[period] or 0.0)
        dx[period] = abs((plus_di[period] or 0.0) - (minus_di[period] or 0.0)) / denom * 100.0 if denom > 0 else 0.0

    for idx in range(period + 1, len(candles)):
        prev_tr = smoothed_tr[idx - 1] or 0.0
        prev_plus = smoothed_plus[idx - 1] or 0.0
        prev_minus = smoothed_minus[idx - 1] or 0.0
        smoothed_tr[idx] = prev_tr - (prev_tr / float(period)) + true_ranges[idx]
        smoothed_plus[idx] = prev_plus - (prev_plus / float(period)) + plus_dm[idx]
        smoothed_minus[idx] = prev_minus - (prev_minus / float(period)) + minus_dm[idx]
        if smoothed_tr[idx] and smoothed_tr[idx] > 0:
            plus_di[idx] = (smoothed_plus[idx] / smoothed_tr[idx]) * 100.0
            minus_di[idx] = (smoothed_minus[idx] / smoothed_tr[idx]) * 100.0
            denom = (plus_di[idx] or 0.0) + (minus_di[idx] or 0.0)
            dx[idx] = abs((plus_di[idx] or 0.0) - (minus_di[idx] or 0.0)) / denom * 100.0 if denom > 0 else 0.0

    seed_values = [value for value in dx[period : period * 2] if value is not None]
    if seed_values:
        seed_index = period * 2 - 1
        if seed_index < len(candles):
            adx[seed_index] = sum(seed_values) / float(len(seed_values))
            for idx in range(seed_index + 1, len(candles)):
                if dx[idx] is None:
                    continue
                adx[idx] = (((adx[idx - 1] or 0.0) * (period - 1)) + dx[idx]) / float(period)

    atr = [None if value is None else value / float(period) for value in smoothed_tr]
    return {"adx": adx, "plus_di": plus_di, "minus_di": minus_di, "atr": atr}


def _is_bullish_reversal_candle(candles: Sequence[Dict[str, Any]]) -> bool:
    if len(candles) < 2:
        return False

    def o(idx: int) -> Optional[float]:
        return _to_float(candles[idx].get("open"))

    def h(idx: int) -> Optional[float]:
        return _to_float(candles[idx].get("high"))

    def l(idx: int) -> Optional[float]:
        return _to_float(candles[idx].get("low"))

    def c(idx: int) -> Optional[float]:
        return _to_float(candles[idx].get("close"))

    latest = -1
    prev = -2
    open_latest = o(latest)
    high_latest = h(latest)
    low_latest = l(latest)
    close_latest = c(latest)
    open_prev = o(prev)
    high_prev = h(prev)
    low_prev = l(prev)
    close_prev = c(prev)
    if None in (open_latest, high_latest, low_latest, close_latest, open_prev, high_prev, low_prev, close_prev):
        return False

    body_latest = abs(close_latest - open_latest)
    range_latest = max(high_latest - low_latest, 0.000001)
    upper_wick = high_latest - max(open_latest, close_latest)
    lower_wick = min(open_latest, close_latest) - low_latest

    bullish_engulfing = (
        close_prev < open_prev
        and close_latest > open_latest
        and close_latest >= open_prev
        and open_latest <= close_prev
    )
    hammer = lower_wick >= (body_latest * 2.0) and upper_wick <= body_latest and close_latest > open_latest
    bullish_marubozu = close_latest > open_latest and (body_latest / range_latest) >= 0.7 and upper_wick <= range_latest * 0.15

    morning_star = False
    if len(candles) >= 3:
        open_first = o(-3)
        close_first = c(-3)
        open_second = o(-2)
        close_second = c(-2)
        if None not in (open_first, close_first, open_second, close_second):
            first_body = abs(close_first - open_first)
            second_body = abs(close_second - open_second)
            midpoint_first = (open_first + close_first) / 2.0
            morning_star = (
                close_first < open_first
                and second_body <= first_body * 0.5
                and close_latest > open_latest
                and close_latest > midpoint_first
            )

    inside_bar_breakout = False
    if len(candles) >= 3:
        high_mother = h(-3)
        low_mother = l(-3)
        high_inside = h(-2)
        low_inside = l(-2)
        if None not in (high_mother, low_mother, high_inside, low_inside):
            inside_bar_breakout = high_inside < high_mother and low_inside > low_mother and close_latest > high_prev

    return any((bullish_engulfing, hammer, morning_star, bullish_marubozu, inside_bar_breakout))


def _volume_sma20(candles: Sequence[Dict[str, Any]]) -> Optional[float]:
    if len(candles) < 21:
        return None
    prior = [_to_float(item.get("volume")) for item in candles[-21:-1]]
    clean = [value for value in prior if value is not None and value >= 0]
    if not clean:
        return None
    return fmean(clean)


def _recent_support(candles: Sequence[Dict[str, Any]], window: int = 20) -> Optional[float]:
    recent = [_to_float(item.get("low")) for item in candles[-(window + 1) : -1]]
    clean = [value for value in recent if value is not None]
    return min(clean) if clean else None


def _recent_resistance(candles: Sequence[Dict[str, Any]], window: int = 20) -> Optional[float]:
    recent = [_to_float(item.get("high")) for item in candles[-(window + 1) : -1]]
    clean = [value for value in recent if value is not None]
    return max(clean) if clean else None


def _pullback_low(candles: Sequence[Dict[str, Any]], window: int = 10) -> Optional[float]:
    recent = [_to_float(item.get("low")) for item in candles[-(window + 1) : -1]]
    clean = [value for value in recent if value is not None]
    return min(clean) if clean else None


def _pick_support_candidate(
    *,
    close_price: float,
    low_price: float,
    ema20: Optional[float],
    ema50: Optional[float],
    rolling_support: Optional[float],
    breakout_level: Optional[float],
    nearest_support: Optional[float],
    tolerance_pct: float = 2.0,
) -> Optional[float]:
    candidates = [ema20, ema50, rolling_support, breakout_level, nearest_support]
    valid: List[float] = []
    for raw in candidates:
        candidate = _to_float(raw)
        if candidate is None or candidate <= 0 or candidate > close_price:
            continue
        distance_pct = abs(close_price - candidate) / close_price * 100.0
        support_breach_pct = max(0.0, (candidate - low_price) / candidate * 100.0)
        if distance_pct <= tolerance_pct or support_breach_pct <= tolerance_pct:
            valid.append(candidate)
    if not valid:
        return None
    return max(valid)


def _signal_for_score(score: int) -> str:
    if score >= 80:
        return "STRONG_BUY_SETUP"
    if score >= 65:
        return "WATCHLIST"
    if score >= 50:
        return "WEAK_SETUP"
    return "AVOID"


def _fetch_latest_trade_date() -> Optional[str]:
    try:
        latest_date = fetch_latest_trade_date_from_oracle()
        if latest_date is not None:
            return latest_date.isoformat()
    except Exception:
        _logger.warning("strong_uptrend_reversal direct latest-date lookup failed; falling back to OHLC probe", exc_info=True)

    snapshot = fetch_ohlc_series_from_oracle(months=1, cutoff_anchor="latest")
    latest: Optional[str] = None
    for candles in snapshot.values():
        if not candles:
            continue
        trade_date = _iso_date(candles[-1].get("date"))
        if trade_date and (latest is None or trade_date > latest):
            latest = trade_date
    return latest


def _fetch_latest_delivery_pct_map(symbols: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    svc = _get_delivery_service_module()
    if svc is None or pool is None:
        return {}
    normalized_symbols = {
        _normalize_delivery_symbol(symbol)
        for symbol in symbols
        if _normalize_delivery_symbol(symbol)
    }
    if not normalized_symbols:
        return {}

    def _fetch_latest_delivery_date(conn: Any, projection: Dict[str, Any]) -> Optional[Any]:
        table_sql = projection["table_sql"]
        date_col = projection["date_col"]
        sql = f"SELECT MAX(src.{date_col}) AS latest_ltc_date FROM {table_sql} src WHERE src.{date_col} IS NOT NULL"
        with conn.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()
            return row[0] if row else None

    def _query_latest_rows(
        conn: Any,
        projection: Dict[str, Any],
        requested_symbols: set[str],
        *,
        normalized_filter: bool,
        latest_delivery_date: Optional[Any],
    ) -> Dict[str, Dict[str, Any]]:
        if not requested_symbols:
            return {}
        symbol_col = projection["symbol_col"]
        date_col = projection["date_col"]
        pct_col = projection["pct_col"]
        table_sql = projection["table_sql"]
        symbol_expr = svc._normalized_delivery_symbol_expr(f"src.{symbol_col}") if normalized_filter else f"UPPER(TRIM(src.{symbol_col}))"
        symbol_binds = {f"sym_{idx}": symbol for idx, symbol in enumerate(sorted(requested_symbols))}
        symbol_placeholders = ", ".join(f":{key}" for key in symbol_binds)
        date_window_sql = ""
        if latest_delivery_date is not None:
            symbol_binds["latest_delivery_date"] = latest_delivery_date
            symbol_binds["delivery_lookback_days"] = _DELIVERY_LOOKBACK_DAYS
            date_window_sql = f"      AND src.{date_col} >= (:latest_delivery_date - :delivery_lookback_days)\n"
        sql = f"""
SELECT ranked.symbol_key,
       ranked.symbol,
       ranked.ltc_date,
       ranked.delivery_pct
FROM (
    SELECT {symbol_expr} AS symbol_key,
           src.{symbol_col} AS symbol,
           src.{date_col} AS ltc_date,
           CAST(src.{pct_col} AS NUMBER(12,6)) AS delivery_pct,
           ROW_NUMBER() OVER (
               PARTITION BY {symbol_expr}
               ORDER BY src.{date_col} DESC NULLS LAST
           ) AS rn
    FROM {table_sql} src
    WHERE {symbol_expr} IN ({symbol_placeholders})
      AND src.{date_col} IS NOT NULL
      AND src.{pct_col} IS NOT NULL
{date_window_sql.rstrip()}
) ranked
WHERE ranked.rn = 1
"""
        rows: Dict[str, Dict[str, Any]] = {}
        with conn.cursor() as cur:
            cur.execute(sql, symbol_binds)
            for row in fetchall_dict(cur):
                symbol_key = _normalize_delivery_symbol(row.get("symbol_key"))
                if not symbol_key or symbol_key not in requested_symbols:
                    continue
                rows[symbol_key] = {
                    "symbol": str(row.get("symbol") or "").strip().upper(),
                    "ltc_date": row.get("ltc_date"),
                    "delivery_pct": _to_float(row.get("delivery_pct")),
                }
        return rows

    results: Dict[str, Dict[str, Any]] = {}
    with pool.acquire() as conn:
        projection, _ = svc._resolve_runtime_metadata(conn)
        latest_delivery_date = _fetch_latest_delivery_date(conn, projection)
        results.update(_query_latest_rows(conn, projection, normalized_symbols, normalized_filter=False, latest_delivery_date=latest_delivery_date))
        missing_symbols = normalized_symbols.difference(results.keys())
        if 0 < len(missing_symbols) <= _DELIVERY_NORMALIZED_FALLBACK_LIMIT:
            results.update(_query_latest_rows(conn, projection, missing_symbols, normalized_filter=True, latest_delivery_date=latest_delivery_date))
    return results


def _build_reject_reason(flags: Dict[str, bool]) -> str:
    reasons = [label for key, label in _REJECT_REASON_LABELS if not bool(flags.get(key))]
    return "; ".join(reasons)


def _evaluate_symbol(
    symbol: str,
    candles: Sequence[Dict[str, Any]],
    latest_trade_date: str,
    delivery_row: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if len(candles) > _EVALUATION_LOOKBACK_CANDLES:
        candles = candles[-_EVALUATION_LOOKBACK_CANDLES:]
    if len(candles) < 60:
        return None

    candle_list = list(candles)
    structure_candles = candle_list[-_STRUCTURE_LOOKBACK_CANDLES:]
    last_trade_date = _iso_date(candles[-1].get("date"))
    if last_trade_date != latest_trade_date:
        return None

    closes = [_to_float(item.get("close")) for item in candles]
    opens = [_to_float(item.get("open")) for item in candles]
    highs = [_to_float(item.get("high")) for item in candles]
    lows = [_to_float(item.get("low")) for item in candles]
    volumes = [_to_float(item.get("volume")) for item in candles]
    if not closes or closes[-1] is None or opens[-1] is None or highs[-1] is None or lows[-1] is None:
        return None

    latest_close = closes[-1] or 0.0
    latest_open = opens[-1] or 0.0
    latest_high = highs[-1] or 0.0
    latest_low = lows[-1] or 0.0
    latest_volume = volumes[-1]

    clean_closes = [value for value in closes if value is not None]
    clean_closes_prev = clean_closes[:-1]
    ema20 = calculate_ema(clean_closes, 20)
    ema50 = calculate_ema(clean_closes, 50)
    ema100 = calculate_ema(clean_closes, 100)
    ema200 = calculate_ema(clean_closes, 200)
    ema20_prev = calculate_ema(clean_closes_prev, 20)
    ema50_prev = calculate_ema(clean_closes_prev, 50)
    ema20_slope_ok = bool(ema20 is not None and ema20_prev is not None and ema20 > ema20_prev)
    ema50_slope_ok = bool(ema50 is not None and ema50_prev is not None and ema50 > ema50_prev)
    ema_slope_ok = ema20_slope_ok and ema50_slope_ok

    rsi14_series = _rsi_series(clean_closes, 14)
    rsi14 = rsi14_series[-1] if rsi14_series else None
    rsi_ok = bool(rsi14 is not None and rsi14 > 50.0)

    macd_state = _macd_series(clean_closes)
    macd_value = macd_state["macd"][-1] if macd_state["macd"] else None
    macd_hist = macd_state["hist"][-1] if macd_state["hist"] else None
    prev_macd_hist = macd_state["hist"][-2] if len(macd_state["hist"]) >= 2 else None
    macd_ok = bool(
        macd_value is not None
        and macd_hist is not None
        and prev_macd_hist is not None
        and macd_value > 0
        and macd_hist > prev_macd_hist
    )

    adx_state = _adx_series(candles, 14)
    adx14 = adx_state["adx"][-1] if adx_state["adx"] else None
    plus_di = adx_state["plus_di"][-1] if adx_state["plus_di"] else None
    minus_di = adx_state["minus_di"][-1] if adx_state["minus_di"] else None
    atr14 = adx_state["atr"][-1] if adx_state["atr"] else None
    adx_ok = bool(adx14 is not None and plus_di is not None and minus_di is not None and adx14 > 25.0 and plus_di > minus_di)

    volume_sma20 = _volume_sma20(candles)
    volume_ok = bool(latest_volume is not None and volume_sma20 is not None and latest_volume > volume_sma20)

    pivots = detect_swing_pivots(structure_candles, window=3, atr_period=14, min_atr_multiple=0.75)
    hh_hl = detect_higher_high_higher_low(pivots)
    hh_hl_structure = bool(hh_hl.get("higherHigh") and hh_hl.get("higherLow"))
    previous_high = hh_hl.get("previousHigh") or {}
    latest_low_pivot = hh_hl.get("latestLow") or {}
    breakout_level = _to_float(previous_high.get("price"))

    sr = calculate_support_resistance(structure_candles, pivots)
    rolling_support = _recent_support(candles, 20)
    rolling_resistance = _recent_resistance(candles, 20)
    nearest_support = _to_float(sr.get("nearestSupport"))
    nearest_resistance = _to_float(sr.get("nearestResistance")) or rolling_resistance or breakout_level

    trend_ok = bool(ema20 is not None and ema50 is not None and latest_close > ema20 and ema20 > ema50)

    chosen_support = _pick_support_candidate(
        close_price=latest_close,
        low_price=latest_low,
        ema20=ema20,
        ema50=ema50,
        rolling_support=rolling_support,
        breakout_level=breakout_level,
        nearest_support=nearest_support,
        tolerance_pct=2.0,
    )
    bullish_close = latest_close > latest_open
    support_confirmed = bool(
        chosen_support is not None
        and bullish_close
        and latest_low >= chosen_support * 0.98
    )

    breakout_probe = detect_resistance_breakout(
        structure_candles,
        resistance=nearest_resistance or breakout_level or rolling_resistance,
        volume_ratio=(latest_volume / volume_sma20) if latest_volume and volume_sma20 else None,
        ema20=ema20,
        ema50=ema50,
    )
    previous_candle_high = highs[-2] if len(highs) >= 2 else None
    breakout_ok = bool(
        (previous_candle_high is not None and latest_close > previous_candle_high)
        or (nearest_resistance is not None and latest_close > nearest_resistance)
        or breakout_probe.get("confirmed")
    )

    bullish_reversal_candle = _is_bullish_reversal_candle(candles)

    delivery_pct = _to_float((delivery_row or {}).get("delivery_pct"))
    delivery_ok = bool(delivery_pct is not None and delivery_pct >= 40.0)

    score_flags = {
        "TREND_OK": trend_ok,
        "EMA_SLOPE_OK": ema_slope_ok,
        "RSI_OK": rsi_ok,
        "ADX_OK": adx_ok,
        "MACD_OK": macd_ok,
        "VOLUME_OK": volume_ok,
        "DELIVERY_OK": delivery_ok,
        "HH_HL_STRUCTURE": hh_hl_structure,
        "SUPPORT_CONFIRMED": support_confirmed,
        "BULLISH_REVERSAL_CANDLE": bullish_reversal_candle,
        "BREAKOUT_OK": breakout_ok,
    }
    score = sum(weight for key, weight in _SCORE_RULES if score_flags.get(key))
    signal = _signal_for_score(score)
    entry_trigger = all(
        (
            trend_ok,
            rsi_ok,
            adx_ok,
            macd_ok,
            volume_ok,
            hh_hl_structure,
            support_confirmed,
            bullish_reversal_candle,
            breakout_ok,
        )
    )

    buffer_seed = max(latest_close * 0.001, (atr14 or latest_close * 0.01) * 0.05)
    higher_low_stop = _to_float(latest_low_pivot.get("price")) if hh_hl.get("higherLow") else None
    pullback_low = _pullback_low(candles, 10)
    stop_reference_candidates = [value for value in (higher_low_stop, pullback_low) if value is not None]
    stop_reference = min(stop_reference_candidates) if stop_reference_candidates else None

    entry_price = latest_high + buffer_seed if breakout_ok else None
    stop_loss = (stop_reference - buffer_seed) if stop_reference is not None else None
    risk_amount = (entry_price - stop_loss) if entry_price is not None and stop_loss is not None else None
    if risk_amount is not None and risk_amount <= 0:
        risk_amount = None
        stop_loss = None

    resistance_candidates = []
    for value in sr.get("resistanceLevels") or []:
        num = _to_float(value)
        if num is not None and entry_price is not None and num > entry_price:
            resistance_candidates.append(num)
    if rolling_resistance is not None and entry_price is not None and rolling_resistance > entry_price:
        resistance_candidates.append(rolling_resistance)
    target_1 = min(resistance_candidates) if resistance_candidates else None
    target_2 = (entry_price + (risk_amount * 2.0)) if entry_price is not None and risk_amount is not None else None

    return {
        "SYMBOL": symbol,
        "TRADING_DATE": latest_trade_date,
        "CLOSE": _round_or_none(latest_close, 2),
        "EMA20": _round_or_none(ema20, 2),
        "EMA50": _round_or_none(ema50, 2),
        "EMA100": _round_or_none(ema100, 2),
        "EMA200": _round_or_none(ema200, 2),
        "RSI14": _round_or_none(rsi14, 2),
        "MACD": _round_or_none(macd_value, 4),
        "MACD_HIST": _round_or_none(macd_hist, 4),
        "ADX14": _round_or_none(adx14, 2),
        "PLUS_DI": _round_or_none(plus_di, 2),
        "MINUS_DI": _round_or_none(minus_di, 2),
        "VOLUME": int(round(latest_volume or 0)),
        "VOLUME_SMA20": _round_or_none(volume_sma20, 2),
        "DELIVERY_PCT": _round_or_none(delivery_pct, 2),
        "HH_HL_STRUCTURE": hh_hl_structure,
        "SUPPORT_CONFIRMED": support_confirmed,
        "BULLISH_REVERSAL_CANDLE": bullish_reversal_candle,
        "BREAKOUT_OK": breakout_ok,
        "SCORE": int(score),
        "SIGNAL": signal,
        "ENTRY_TRIGGER": entry_trigger,
        "ENTRY_PRICE": _round_or_none(entry_price, 2),
        "STOP_LOSS": _round_or_none(stop_loss, 2),
        "TARGET_1": _round_or_none(target_1, 2),
        "TARGET_2": _round_or_none(target_2, 2),
        "REJECT_REASON": "" if entry_trigger else _build_reject_reason(score_flags),
    }


def fetch_strong_uptrend_reversal_scan(*, refresh: bool = False) -> Dict[str, Any]:
    started = time.perf_counter()
    latest_started = time.perf_counter()
    latest_trade_date = _fetch_latest_trade_date()
    latest_date_ms = _elapsed_ms(latest_started)
    if not latest_trade_date:
        payload = {
            "data": [],
            "status": "SUCCESS",
            "meta": {
                "tradingDate": None,
                "rows": 0,
                "cacheState": "MISS",
                "latestDateMs": latest_date_ms,
                "durationMs": _elapsed_ms(started),
            },
        }
        _logger.info(
            "strong_uptrend_reversal latest_trade_date=None rows_returned=0 cache=MISS latest_date_ms=%s duration_ms=%s",
            latest_date_ms,
            payload["meta"]["durationMs"],
        )
        return payload

    cache_key = f"strong-uptrend-reversal:{_CACHE_VERSION}:{latest_trade_date}"
    if not refresh:
        cached = _CACHE.get(cache_key)
        if isinstance(cached, dict):
            payload = dict(cached)
            meta = dict(payload.get("meta") or {})
            meta["cacheState"] = "HIT"
            meta["latestDateMs"] = latest_date_ms
            meta["durationMs"] = _elapsed_ms(started)
            payload["meta"] = meta
            _logger.info(
                "strong_uptrend_reversal latest_trade_date=%s symbols=%s rows_returned=%s delivery_hits=%s delivery_missing=%s cache=HIT latest_date_ms=%s duration_ms=%s",
                latest_trade_date,
                meta.get("symbolUniverse", 0),
                meta.get("rows", 0),
                meta.get("deliveryHits", 0),
                meta.get("deliveryMissing", 0),
                latest_date_ms,
                meta["durationMs"],
            )
            return payload

    oracle_started = time.perf_counter()
    raw_series = fetch_recent_ohlc_series_from_oracle(trading_days=_LOOKBACK_TRADING_DAYS)
    raw_row_count = sum(len(candles) for candles in raw_series.values())
    oracle_ms = _elapsed_ms(oracle_started)

    transform_started = time.perf_counter()
    series_by_symbol = aggregate_ohlc_series_by_timeframe(raw_series, "daily")
    transform_ms = _elapsed_ms(transform_started)

    symbols = sorted(series_by_symbol.keys())
    delivery_started = time.perf_counter()
    delivery_map = _fetch_latest_delivery_pct_map(symbols)
    delivery_ms = _elapsed_ms(delivery_started)

    compute_started = time.perf_counter()
    rows: List[Dict[str, Any]] = []
    delivery_hits = 0
    delivery_missing = 0
    for symbol in symbols:
        delivery_row = delivery_map.get(_normalize_delivery_symbol(symbol))
        if delivery_row:
            delivery_hits += 1
        else:
            delivery_missing += 1
        row = _evaluate_symbol(symbol, series_by_symbol[symbol], latest_trade_date, delivery_row)
        if row is not None:
            rows.append(row)
    rows.sort(key=lambda item: (-int(item.get("SCORE") or 0), str(item.get("SYMBOL") or "")))
    compute_ms = _elapsed_ms(compute_started)

    payload = {
        "data": rows,
        "status": "SUCCESS",
        "meta": {
            "tradingDate": latest_trade_date,
            "rows": len(rows),
            "symbolUniverse": len(symbols),
            "rawRows": raw_row_count,
            "lookbackTradingDays": _LOOKBACK_TRADING_DAYS,
            "evaluationCandles": _EVALUATION_LOOKBACK_CANDLES,
            "structureCandles": _STRUCTURE_LOOKBACK_CANDLES,
            "deliveryLookbackDays": _DELIVERY_LOOKBACK_DAYS,
            "deliveryHits": delivery_hits,
            "deliveryMissing": delivery_missing,
            "cacheState": "MISS",
            "latestDateMs": latest_date_ms,
            "oracleLoadMs": oracle_ms,
            "transformMs": transform_ms,
            "deliveryLoadMs": delivery_ms,
            "computeMs": compute_ms,
            "durationMs": _elapsed_ms(started),
        },
    }
    _CACHE.set(cache_key, payload)
    _logger.info(
        "strong_uptrend_reversal latest_trade_date=%s symbols=%s raw_rows=%s rows_returned=%s delivery_hits=%s delivery_missing=%s cache=MISS latest_date_ms=%s oracle_ms=%s transform_ms=%s delivery_ms=%s compute_ms=%s duration_ms=%s",
        latest_trade_date,
        len(symbols),
        raw_row_count,
        len(rows),
        delivery_hits,
        delivery_missing,
        latest_date_ms,
        oracle_ms,
        transform_ms,
        delivery_ms,
        compute_ms,
        payload["meta"]["durationMs"],
    )
    return payload


__all__ = ["fetch_strong_uptrend_reversal_scan"]
