from __future__ import annotations

import calendar
import logging
import os
import re
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime
from statistics import fmean
from typing import Any, Dict, List, Optional, Tuple

from db import fetch_ohlc_series_from_oracle
from services.trend_service import ema
from sr_levels import build_sr_levels_payload, normalize_symbol as normalize_sr_symbol
try:
    from services.ath_service import get_all_time_high_for_symbols, log_stale_snapshot_warning
except Exception:  # pragma: no cover
    from .ath_service import get_all_time_high_for_symbols, log_stale_snapshot_warning  # type: ignore
try:
    from services.prudvi_strategy_service import (
        fetch_manual_sr_level_map,
        select_ranked_resistance_levels,
        select_ranked_support_levels,
    )
except Exception:  # pragma: no cover
    from .prudvi_strategy_service import (  # type: ignore
        fetch_manual_sr_level_map,
        select_ranked_resistance_levels,
        select_ranked_support_levels,
    )

try:
    from db_pool import pool
except Exception:  # pragma: no cover
    pool = None  # type: ignore


_logger = logging.getLogger(__name__)

CUTOFF_MONTHS = int(os.getenv("BHRAMHAPUTRA_CUTOFF_MONTHS", "24"))
EMA_PERIOD = 20
RSI_PERIOD = 14
ATR_PERIOD = 14
VOL_PERIOD = 20
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BHRAMHAPUTRA_STOP_LOSS_PCT = 0.05
BHRAMHAPUTRA_TARGET1_PCT = 0.10
BHRAMHAPUTRA_TARGET2_PCT = 0.15

SR_TOLERANCE = float(os.getenv("BHRAMHAPUTRA_SR_TOLERANCE", "0.05"))
SR_TIMEFRAME = os.getenv("BHRAMHAPUTRA_SR_TIMEFRAME", "daily")
VALID_TIMEFRAMES = ("daily", "weekly", "monthly", "yearly")

LEVEL_GAP_MIN = 0.05
LEVEL_GAP_MAX = 0.15
NO_SR_LEVELS_TEXT = "SR LEVELS NOT EXISTS"

BHRAMHAPUTRA_TABLE = (os.getenv("BHRAMHAPUTRA_TABLE") or "BHRAMHAPUTRA_SCAN").strip()
_BHRAMHAPUTRA_SCHEMA = (os.getenv("BHRAMHAPUTRA_SCHEMA") or os.getenv("ORACLE_SCHEMA") or "").strip()
if _BHRAMHAPUTRA_SCHEMA and "." not in BHRAMHAPUTRA_TABLE:
    BHRAMHAPUTRA_TABLE = f"{_BHRAMHAPUTRA_SCHEMA}.{BHRAMHAPUTRA_TABLE}"

BHRAMHAPUTRA_INSERT_TABLE = (
    os.getenv("BHRAMHAPUTRA_INSERT_TABLE")
    or os.getenv("BHRAMHAPUTRA_BULLISH_TABLE")
    or "BULLISH_BHRAMHAPUTRA"
).strip()
if _BHRAMHAPUTRA_SCHEMA and "." not in BHRAMHAPUTRA_INSERT_TABLE:
    BHRAMHAPUTRA_INSERT_TABLE = f"{_BHRAMHAPUTRA_SCHEMA}.{BHRAMHAPUTRA_INSERT_TABLE}"

_IDENT_RE = re.compile(r"^[A-Za-z0-9_.$#]+$")


@dataclass
class Candle:
    date: datetime
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float]


def _normalize_timeframe(value: Optional[str]) -> str:
    if value is None or not str(value).strip():
        fallback = (SR_TIMEFRAME or "daily").strip().lower()
        return fallback if fallback in VALID_TIMEFRAMES else "daily"
    tf = str(value).strip().lower()
    if tf not in VALID_TIMEFRAMES:
        raise ValueError("Invalid timeframe")
    return tf


def _min_required_candles(timeframe: str) -> int:
    baseline = max(EMA_PERIOD, RSI_PERIOD, ATR_PERIOD)
    if timeframe in ("daily", "weekly"):
        baseline = max(baseline, MACD_SLOW)
    return baseline + 2


def _cutoff_months_for_timeframe(timeframe: str) -> int:
    base = max(1, CUTOFF_MONTHS)
    if timeframe == "monthly":
        return max(base, _min_required_candles(timeframe))
    if timeframe == "yearly":
        return max(base, _min_required_candles(timeframe) * 12)
    return base


def _months_ago(base: date, months: int) -> date:
    year = base.year
    month = base.month - months
    while month <= 0:
        month += 12
        year -= 1
    day = min(base.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _cutoff_date_iso(months: int, anchor_date: Optional[date] = None) -> Optional[str]:
    if months <= 0:
        return None
    cutoff = _months_ago(anchor_date or datetime.utcnow().date(), months)
    return cutoff.strftime("%Y-%m-%d")


def _latest_trade_date_from_series(raw_series: Dict[str, List[Dict[str, Any]]]) -> Optional[date]:
    latest: Optional[date] = None
    for entries in raw_series.values():
        for entry in entries:
            dt = entry.get("date")
            if isinstance(dt, datetime):
                day = dt.date()
            elif isinstance(dt, date):
                day = dt
            else:
                continue
            if latest is None or day > latest:
                latest = day
    return latest


def _safe_identifier(name: str) -> str:
    token = str(name or "").strip()
    if not token or not _IDENT_RE.match(token):
        raise ValueError("Invalid Oracle identifier")
    return token


def _split_owner_and_table(name: str) -> Tuple[str, str]:
    raw = str(name or "").strip()
    if "." in raw:
        owner, table = raw.rsplit(".", 1)
    else:
        owner, table = _BHRAMHAPUTRA_SCHEMA, raw
    return owner.strip('"').upper(), table.strip('"').upper()


def _table_columns(conn, table_name: str) -> set[str]:
    owner, table = _split_owner_and_table(table_name)
    with conn.cursor() as cur:
        if owner:
            cur.execute(
                """
                SELECT COLUMN_NAME
                FROM ALL_TAB_COLUMNS
                WHERE OWNER = :owner AND TABLE_NAME = :table_name
                """,
                {"owner": owner, "table_name": table},
            )
        else:
            cur.execute(
                """
                SELECT COLUMN_NAME
                FROM USER_TAB_COLUMNS
                WHERE TABLE_NAME = :table_name
                """,
                {"table_name": table},
            )
        return {str(row[0]).upper() for row in (cur.fetchall() or []) if row and row[0]}


def _periods_per_year(timeframe: str) -> int:
    return {
        "daily": 252,
        "weekly": 52,
        "monthly": 12,
        "yearly": 1,
    }.get(timeframe, 252)


def _aggregate_candles(candles: List[Candle], timeframe: str) -> List[Candle]:
    if timeframe == "daily":
        return candles

    buckets: OrderedDict = OrderedDict()
    for candle in candles:
        dt = candle.date
        if not isinstance(dt, datetime):
            continue
        if timeframe == "weekly":
            iso = dt.isocalendar()
            bucket_key = (iso[0], iso[1])
        elif timeframe == "monthly":
            bucket_key = (dt.year, dt.month)
        elif timeframe == "yearly":
            bucket_key = (dt.year,)
        else:
            return candles

        bucket = buckets.get(bucket_key)
        if bucket is None:
            open_val = candle.open if candle.open is not None else candle.close
            high_val = candle.high if candle.high is not None else candle.close
            low_val = candle.low if candle.low is not None else candle.close
            buckets[bucket_key] = {
                "open": float(open_val) if open_val is not None else None,
                "high": float(high_val) if high_val is not None else None,
                "low": float(low_val) if low_val is not None else None,
                "close": float(candle.close) if candle.close is not None else None,
                "volume": float(candle.volume) if candle.volume is not None else None,
                "date": dt,
            }
            continue

        if candle.high is not None:
            high_val = float(candle.high)
            bucket["high"] = high_val if bucket["high"] is None else max(bucket["high"], high_val)
        if candle.low is not None:
            low_val = float(candle.low)
            bucket["low"] = low_val if bucket["low"] is None else min(bucket["low"], low_val)
        if candle.close is not None:
            bucket["close"] = float(candle.close)
        if candle.open is not None and bucket["open"] is None:
            bucket["open"] = float(candle.open)
        if candle.volume is not None:
            bucket["volume"] = (bucket["volume"] or 0.0) + float(candle.volume)
        bucket["date"] = dt

    aggregated: List[Candle] = []
    for bucket in buckets.values():
        close_val = bucket.get("close")
        if close_val is None:
            continue
        open_val = bucket.get("open") if bucket.get("open") is not None else close_val
        high_val = bucket.get("high") if bucket.get("high") is not None else close_val
        low_val = bucket.get("low") if bucket.get("low") is not None else close_val
        aggregated.append(Candle(
            date=bucket.get("date"),
            open=float(open_val),
            high=float(high_val),
            low=float(low_val),
            close=float(close_val),
            volume=bucket.get("volume"),
        ))
    return aggregated


def _fmt_iso(value: Optional[datetime]) -> Optional[str]:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    return None


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_round(value: Optional[float], digits: int = 2) -> Optional[float]:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _ema_series(values: List[float], period: int) -> List[Optional[float]]:
    if not values:
        return []
    k = 2 / (period + 1)
    out: List[Optional[float]] = []
    prev: Optional[float] = None
    for value in values:
        prev = value if prev is None else (value - prev) * k + prev
        out.append(prev)
    return out


def _compute_macd(closes: List[float]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if len(closes) < MACD_SLOW + 1:
        return None, None, None
    ema_fast = _ema_series(closes, MACD_FAST)
    ema_slow = _ema_series(closes, MACD_SLOW)
    macd_line: List[float] = []
    for fast, slow in zip(ema_fast, ema_slow):
        if fast is None or slow is None:
            macd_line.append(0.0)
        else:
            macd_line.append(float(fast) - float(slow))
    signal_line = _ema_series(macd_line, MACD_SIGNAL)
    if not signal_line:
        return None, None, None
    return macd_line[-1], signal_line[-1], macd_line[-1] - (signal_line[-1] or 0.0)


def _compute_rsi_series(closes: List[float], period: int = RSI_PERIOD) -> List[Optional[float]]:
    if len(closes) < period + 1:
        return [None] * len(closes)
    rsi_values: List[Optional[float]] = [None] * len(closes)
    gains = []
    losses = []
    for i in range(1, period + 1):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    rs = (avg_gain / avg_loss) if avg_loss > 0 else None
    rsi_values[period] = 100.0 if rs is None else 100 - (100 / (1 + rs))
    for idx in range(period + 1, len(closes)):
        delta = closes[idx] - closes[idx - 1]
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
        if avg_loss == 0:
            rsi_values[idx] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi_values[idx] = 100 - (100 / (1 + rs))
    return rsi_values


def _true_ranges(candles: List[Candle]) -> List[float]:
    ranges: List[float] = []
    prev_close: Optional[float] = None
    for candle in candles:
        high = candle.high
        low = candle.low
        close = candle.close
        if prev_close is None:
            tr = high - low
        else:
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        ranges.append(tr)
        prev_close = close
    return ranges


def _wilder_atr(trs: List[float], period: int) -> List[Optional[float]]:
    length = len(trs)
    if length < period:
        return [None] * length
    atrs: List[Optional[float]] = [None] * length
    first_avg = sum(trs[:period]) / period
    atrs[period - 1] = first_avg
    for idx in range(period, length):
        prev_atr = atrs[idx - 1]
        if prev_atr is None:
            prev_atr = first_avg
        atrs[idx] = ((prev_atr * (period - 1)) + trs[idx]) / period
    return atrs


def _build_candles(entries: List[Dict[str, Any]]) -> List[Candle]:
    candles: List[Candle] = []
    for entry in entries:
        dt = entry.get("date")
        close_val = _safe_float(entry.get("close"))
        if not isinstance(dt, datetime) or close_val is None:
            continue
        open_val = _safe_float(entry.get("open"))
        high_val = _safe_float(entry.get("high"))
        low_val = _safe_float(entry.get("low"))
        volume_val = _safe_float(entry.get("volume"))
        if open_val is None:
            open_val = close_val
        if high_val is None:
            high_val = close_val
        if low_val is None:
            low_val = close_val
        candles.append(Candle(
            date=dt,
            open=open_val,
            high=high_val,
            low=low_val,
            close=close_val,
            volume=volume_val,
        ))
    candles.sort(key=lambda c: c.date)
    return candles


def _avg_volume(candles: List[Candle]) -> Tuple[Optional[float], Optional[float]]:
    volumes = [c.volume for c in candles if c.volume is not None and c.volume > 0]
    if not volumes:
        return None, None
    window = volumes[-VOL_PERIOD:] if len(volumes) >= VOL_PERIOD else volumes
    avg = fmean(window) if window else None
    if avg is None or avg <= 0:
        return None, None
    latest = volumes[-1]
    ratio = latest / avg
    return avg, ratio


def _calc_high_low(candles: List[Candle], window: int) -> Tuple[Optional[float], Optional[float]]:
    if not candles:
        return None, None
    subset = candles[-window:] if len(candles) >= window else candles
    highs = [c.high for c in subset if c.high is not None]
    lows = [c.low for c in subset if c.low is not None]
    return (max(highs) if highs else None, min(lows) if lows else None)


def _calc_ath(candles: List[Candle]) -> Optional[float]:
    highs = [c.high for c in candles if c.high is not None]
    return max(highs) if highs else None


def _calc_ytd_pct(candles: List[Candle], latest_price: float) -> Optional[float]:
    if not candles:
        return None
    year_start = date(datetime.utcnow().year, 1, 1)
    start_price = None
    for candle in candles:
        if candle.date.date() >= year_start:
            start_price = candle.close
            break
    if start_price is None or start_price == 0:
        return None
    return (latest_price - start_price) / start_price * 100.0


def _pct_move(closes: List[float], days: int) -> Optional[float]:
    if days <= 0 or len(closes) <= days:
        return None
    past = closes[-(days + 1)]
    if past == 0:
        return None
    return (closes[-1] - past) / past * 100.0


def _pivot_candidates(high: float, low: float, close: float) -> Tuple[List[float], List[float]]:
    pivot = (high + low + close) / 3.0
    r1 = 2 * pivot - low
    s1 = 2 * pivot - high
    r2 = pivot + (high - low)
    s2 = pivot - (high - low)
    return [s1, s2], [r1, r2]


def _fib_candidates(candles: List[Candle]) -> Tuple[List[float], List[float]]:
    window = candles[-60:] if len(candles) >= 60 else candles
    highs = [c.high for c in window if c.high is not None]
    lows = [c.low for c in window if c.low is not None]
    if not highs or not lows:
        return [], []
    swing_high = max(highs)
    swing_low = min(lows)
    if swing_high <= swing_low:
        return [], []
    span = swing_high - swing_low
    retrace = [
        swing_high - span * 0.382,
        swing_high - span * 0.5,
        swing_high - span * 0.618,
    ]
    extension = [
        swing_high + span * 0.272,
        swing_high + span * 0.618,
    ]
    return retrace, extension


def _normalize_levels(levels: List[Optional[float]]) -> List[float]:
    normalized: List[float] = []
    for level in levels:
        if level is None:
            continue
        try:
            value = float(level)
        except (TypeError, ValueError):
            continue
        if value > 0:
            normalized.append(value)
    return normalized


def _pick_primary(levels: List[float], price: float, kind: str) -> Optional[float]:
    if kind == "support":
        candidates = [lvl for lvl in levels if lvl < price]
        candidates.sort(reverse=True)
    else:
        candidates = [lvl for lvl in levels if lvl > price]
        candidates.sort()
    for lvl in candidates:
        gap = abs(price - lvl) / price
        if LEVEL_GAP_MIN <= gap <= LEVEL_GAP_MAX:
            return lvl
    return None


def _pick_secondary(levels: List[float], primary: Optional[float], kind: str) -> Optional[float]:
    if primary is None:
        return None
    if kind == "support":
        candidates = [lvl for lvl in levels if lvl < primary]
        candidates.sort(reverse=True)
    else:
        candidates = [lvl for lvl in levels if lvl > primary]
        candidates.sort()
    for lvl in candidates:
        gap = abs(primary - lvl) / primary
        if LEVEL_GAP_MIN <= gap <= LEVEL_GAP_MAX:
            return lvl
    return None


def _synthesize_levels(price: float, kind: str) -> Tuple[float, float]:
    if kind == "support":
        primary = price * (1 - LEVEL_GAP_MIN)
        secondary = price * (1 - LEVEL_GAP_MIN * 2)
        return primary, secondary
    primary = price * (1 + LEVEL_GAP_MIN)
    secondary = price * (1 + LEVEL_GAP_MIN * 2.1)
    return primary, secondary


def _resolve_levels(
    sr_row: Dict[str, Any],
    price: float,
    pivot: Tuple[List[float], List[float]],
    fib: Tuple[List[float], List[float]],
    extras: Tuple[List[float], List[float]],
) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    base_supports = [sr_row.get(f"S{i}") for i in range(1, 11)]
    base_resistances = [sr_row.get(f"R{i}") for i in range(1, 11)]
    support_levels = _normalize_levels(base_supports + pivot[0] + fib[0] + extras[0])
    resistance_levels = _normalize_levels(base_resistances + pivot[1] + fib[1] + extras[1])

    s1 = _pick_primary(support_levels, price, "support")
    s2 = _pick_secondary(support_levels, s1, "support")
    r1 = _pick_primary(resistance_levels, price, "resistance")
    r2 = _pick_secondary(resistance_levels, r1, "resistance")

    if s1 is None or s2 is None:
        synth_s1, synth_s2 = _synthesize_levels(price, "support")
        s1 = s1 or synth_s1
        s2 = s2 or synth_s2
    if r1 is None or r2 is None:
        synth_r1, synth_r2 = _synthesize_levels(price, "resistance")
        r1 = r1 or synth_r1
        r2 = r2 or synth_r2
    return s1, s2, r1, r2


def _candles_to_history_rows(candles: List[Candle]) -> List[Dict[str, Any]]:
    return [
        {
            "date": candle.date,
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
        }
        for candle in candles
    ]


def _normalize_manual_sr_symbol(symbol: Any) -> str:
    token = normalize_sr_symbol(str(symbol or "").strip())
    if token.endswith(":EQ"):
        token = token[:-3]
    return token.strip().upper()


def _format_manual_sr_value(value: Any) -> str:
    number = _safe_float(value)
    if number is None:
        return "-"
    if abs(number - round(number)) < 0.000001:
        return str(int(round(number)))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _format_manual_sr_display(levels: List[float], prefix: str) -> str:
    if not levels:
        return "-"
    return ", ".join(f"{prefix}{index}: {_format_manual_sr_value(level)}" for index, level in enumerate(levels, start=1))


def _resolve_manual_sr_display(
    symbol: str,
    price: Optional[float],
    candles: List[Candle],
    manual_sr_record: Optional[Dict[str, Any]],
) -> Dict[str, str]:
    manual_levels = list((manual_sr_record or {}).get("levels") or [])
    if price is None or price <= 0 or not manual_levels:
        return {
            "supportDisplay": NO_SR_LEVELS_TEXT,
            "resistanceDisplay": NO_SR_LEVELS_TEXT,
        }
    history_rows = _candles_to_history_rows(candles)
    support_ranked = select_ranked_support_levels(symbol, price, manual_levels, history_rows, limit=3)
    resistance_ranked = select_ranked_resistance_levels(symbol, price, manual_levels, history_rows, limit=3)
    support_levels = [
        float(level)
        for level in (_safe_float(item.get("level")) for item in support_ranked)
        if level is not None
    ][:3]
    resistance_levels = [
        float(level)
        for level in (_safe_float(item.get("level")) for item in resistance_ranked)
        if level is not None
    ][:3]
    return {
        "supportDisplay": _format_manual_sr_display(support_levels, "S") if support_levels else "-",
        "resistanceDisplay": _format_manual_sr_display(resistance_levels, "R") if resistance_levels else "-",
    }


def backfill_manual_sr_display_rows(
    rows: List[Dict[str, Any]],
    timeframe: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if not rows:
        return rows
    tf = _normalize_timeframe(timeframe)
    requested_symbols = sorted({
        str(row.get("symbol") or "").strip().upper()
        for row in rows
        if str(row.get("symbol") or "").strip()
    })
    raw_series = fetch_ohlc_series_from_oracle(
        months=_cutoff_months_for_timeframe(tf),
        cutoff_anchor="current",
        symbols=requested_symbols,
    )
    candles_by_manual_symbol: Dict[str, List[Candle]] = {}
    latest_price_by_manual_symbol: Dict[str, float] = {}
    for symbol, entries in raw_series.items():
        manual_sr_key = _normalize_manual_sr_symbol(symbol)
        candles = _aggregate_candles(_build_candles(entries), tf)
        if not candles:
            continue
        candles_by_manual_symbol[manual_sr_key] = candles
        latest_price_by_manual_symbol[manual_sr_key] = candles[-1].close

    manual_sr_symbols = sorted({
        _normalize_manual_sr_symbol(row.get("symbol"))
        for row in rows
        if _normalize_manual_sr_symbol(row.get("symbol"))
    })
    manual_sr_map = fetch_manual_sr_level_map(manual_sr_symbols) if manual_sr_symbols else {}

    enriched_rows: List[Dict[str, Any]] = []
    for row in rows:
        normalized_row = dict(row)
        manual_sr_key = _normalize_manual_sr_symbol(normalized_row.get("symbol"))
        price = _safe_float(normalized_row.get("priceSort"))
        if price is None:
            price = _safe_float(normalized_row.get("price"))
        if price is None:
            price = _safe_float(latest_price_by_manual_symbol.get(manual_sr_key))
        manual_sr_display = _resolve_manual_sr_display(
            manual_sr_key,
            price,
            candles_by_manual_symbol.get(manual_sr_key) or [],
            manual_sr_map.get(manual_sr_key),
        )
        normalized_row["supportDisplay"] = manual_sr_display["supportDisplay"]
        normalized_row["resistanceDisplay"] = manual_sr_display["resistanceDisplay"]
        enriched_rows.append(normalized_row)
    return enriched_rows


def _bullish_pattern(candles: List[Candle]) -> bool:
    if len(candles) < 3:
        return False
    last = candles[-3:]
    highs = [c.high for c in last]
    lows = [c.low for c in last]
    return highs[2] > highs[1] > highs[0] and lows[2] > lows[1] > lows[0]


def compute_bhramhaputra_payload(timeframe: Optional[str] = None) -> Dict[str, Any]:
    tf = _normalize_timeframe(timeframe)
    cutoff_months = _cutoff_months_for_timeframe(tf)
    # Anchor cut-off to current date (not latest available trade date).
    raw_series = fetch_ohlc_series_from_oracle(months=cutoff_months, cutoff_anchor="current")
    ath_records: Dict[str, Dict[str, Any]] = {}
    try:
        ath_records = get_all_time_high_for_symbols(
            list(raw_series.keys()),
            include_date=True,
            endpoint='/api/bhramhaputra',
        )
    except Exception:
        _logger.exception('[ATH] Failed to fetch ATH map for Bhramhaputra payload')
        ath_records = {}
    source_latest_trade_date = _latest_trade_date_from_series(raw_series)
    cutoff_date_iso = _cutoff_date_iso(CUTOFF_MONTHS)
    sr_payload = build_sr_levels_payload(raw_series, [], SR_TOLERANCE, tf)
    sr_map = {
        normalize_sr_symbol(row.get("symbol")): row
        for row in (sr_payload.get("rows") or [])
        if row.get("symbol")
    }
    strict_rows: List[Dict[str, Any]] = []
    relaxed_rows: List[Dict[str, Any]] = []
    sr_context_by_symbol: Dict[str, Dict[str, Any]] = {}
    overall_first: Optional[datetime] = None
    overall_last: Optional[datetime] = None
    min_required = _min_required_candles(tf)
    periods_per_year = _periods_per_year(tf)
    stale_ath_detected = False

    for symbol, entries in raw_series.items():
        symbol_key = str(symbol).strip().upper()
        manual_sr_key = _normalize_manual_sr_symbol(symbol)
        candles = _build_candles(entries)
        candles = _aggregate_candles(candles, tf)
        if len(candles) < min_required:
            continue

        latest = candles[-1]
        closes = [c.close for c in candles]
        price = latest.close

        ema20 = ema(closes, EMA_PERIOD)
        rsi_series = _compute_rsi_series(closes, RSI_PERIOD)
        rsi_now = rsi_series[-1]
        macd_line, macd_signal, macd_hist = _compute_macd(closes)
        avg_volume20, volume_ratio20 = _avg_volume(candles)

        trs = _true_ranges(candles)
        atr_series = _wilder_atr(trs, ATR_PERIOD)
        atr_now = atr_series[-1] if atr_series else None

        high52w, low52w = _calc_high_low(candles, periods_per_year)
        high1y, _ = _calc_high_low(candles, periods_per_year)
        high2y, _ = _calc_high_low(candles, periods_per_year * 2)
        fallback_ath = _calc_ath(candles)
        ath_record = ath_records.get(symbol_key) or {}
        authoritative_ath = _safe_float(ath_record.get('ath'))
        ath = authoritative_ath if authoritative_ath is not None else fallback_ath
        ath_date = ath_record.get('ath_date')
        if authoritative_ath is not None and fallback_ath is not None and abs(float(authoritative_ath) - float(fallback_ath)) > 0.0001:
            stale_ath_detected = True
        ytd_pct = _calc_ytd_pct(candles, price)

        move_22d = _pct_move(closes, 22) if tf == "daily" else None
        move_44d = _pct_move(closes, 44) if tf == "daily" else None
        move_66d = _pct_move(closes, 66) if tf == "daily" else None
        move_88d = _pct_move(closes, 88) if tf == "daily" else None
        move_110d = _pct_move(closes, 110) if tf == "daily" else None
        move_132d = _pct_move(closes, 132) if tf == "daily" else None
        move_154d = _pct_move(closes, 154) if tf == "daily" else None
        move_176d = _pct_move(closes, 176) if tf == "daily" else None
        move_198d = _pct_move(closes, 198) if tf == "daily" else None

        sr_row = sr_map.get(normalize_sr_symbol(symbol)) or {}
        trend_direction = sr_row.get("trendDirection") or sr_row.get("trend_direction") or "Consolidation"

        pivot = _pivot_candidates(latest.high, latest.low, latest.close)
        fib = _fib_candidates(candles)
        primary_support = sr_row.get("primarySupport")
        primary_support_price = primary_support.get("price") if isinstance(primary_support, dict) else None
        primary_resistance = sr_row.get("primaryResistance")
        primary_resistance_price = primary_resistance.get("price") if isinstance(primary_resistance, dict) else None
        extras_support = [low52w, sr_row.get("low52w"), primary_support_price]
        extras_resistance = [high52w, ath, sr_row.get("high52w"), primary_resistance_price]
        s1, s2, r1, r2 = _resolve_levels(
            sr_row,
            price,
            pivot,
            fib,
            (_normalize_levels(extras_support), _normalize_levels(extras_resistance)),
        )
        ema_ok = ema20 is not None and price > ema20
        rsi_ok = rsi_now is not None and rsi_now > 30
        macd_ok = macd_hist is not None and macd_hist > 0
        volume_ok = avg_volume20 is not None and latest.volume is not None and latest.volume > avg_volume20
        uptrend_ok = str(trend_direction).strip().lower() == "uptrend"
        bullish_ok = _bullish_pattern(candles)
        atr_ok = atr_now is not None and atr_now > 0

        conditions_met = macd_ok and rsi_ok and volume_ok and bullish_ok and atr_ok
        signal_score = int(bool(macd_ok)) + int(bool(rsi_ok)) + int(bool(volume_ok)) + int(bool(bullish_ok)) + int(bool(atr_ok))
        first_date = candles[0].date
        if overall_first is None or first_date < overall_first:
            overall_first = first_date
        if overall_last is None or latest.date > overall_last:
            overall_last = latest.date

        buy_price = price
        stop_loss = buy_price * (1 - BHRAMHAPUTRA_STOP_LOSS_PCT)
        target1 = buy_price * (1 + BHRAMHAPUTRA_TARGET1_PCT)
        target2 = buy_price * (1 + BHRAMHAPUTRA_TARGET2_PCT)
        row_payload = {
            "symbol": symbol,
            "tradeDate": _fmt_iso(latest.date),
            "ltcDate": _fmt_iso(latest.date),
            "ltc_date": _fmt_iso(latest.date),
            "buyingDate": _fmt_iso(latest.date),
            "buying_date": _fmt_iso(latest.date),
            "buyDate": _fmt_iso(latest.date),
            "buy_date": _fmt_iso(latest.date),
            "cutoffDate": cutoff_date_iso,
            "price": _safe_round(price, 2),
            "priceSort": price,
            "buyPrice": _safe_round(buy_price, 2),
            "sellDate": None,
            "sellPrice": None,
            "stopLoss": _safe_round(stop_loss, 2),
            "target1": _safe_round(target1, 2),
            "target2": _safe_round(target2, 2),
            "ema20": _safe_round(ema20, 2),
            "ema20Sort": ema20,
            "emaSignal": "YES" if ema_ok else "NO",
            "rsi14": _safe_round(rsi_now, 2),
            "rsi14Sort": rsi_now,
            "rsiSignal": "YES" if rsi_ok else "NO",
            "macdLine": _safe_round(macd_line, 4),
            "macdSignalLine": _safe_round(macd_signal, 4),
            "macdHist": _safe_round(macd_hist, 4),
            "macdHistSort": macd_hist,
            "macdSignal": "YES" if macd_ok else "NO",
            "volume": _safe_round(latest.volume, 2) if latest.volume is not None else None,
            "volumeSort": latest.volume,
            "avgVolume20": _safe_round(avg_volume20, 2),
            "avgVolume20Sort": avg_volume20,
            "volumeRatio20": _safe_round(volume_ratio20, 2),
            "volumeRatio20Sort": volume_ratio20,
            "volumeSignal": "YES" if volume_ok else "NO",
            "atr14": _safe_round(atr_now, 2),
            "atr14Sort": atr_now,
            "trendDirection": trend_direction,
            "bullishPattern": "YES" if bullish_ok else "NO",
            "support1": _safe_round(s1, 2),
            "support2": _safe_round(s2, 2),
            "resistance1": _safe_round(r1, 2),
            "resistance2": _safe_round(r2, 2),
            "support": _safe_round(s1, 2),
            "resistance": _safe_round(r1, 2),
            "high52w": _safe_round(high52w, 2),
            "low52w": _safe_round(low52w, 2),
            "move22dPct": _safe_round(move_22d, 2),
            "move44dPct": _safe_round(move_44d, 2),
            "move66dPct": _safe_round(move_66d, 2),
            "move88dPct": _safe_round(move_88d, 2),
            "move110dPct": _safe_round(move_110d, 2),
            "move132dPct": _safe_round(move_132d, 2),
            "move154dPct": _safe_round(move_154d, 2),
            "move176dPct": _safe_round(move_176d, 2),
            "move198dPct": _safe_round(move_198d, 2),
            "high1y": _safe_round(high1y, 2),
            "high2y": _safe_round(high2y, 2),
            "ath": _safe_round(ath, 2),
            "athDate": ath_date,
            "ath_date": ath_date,
            "ytdPct": _safe_round(ytd_pct, 2),
            "conditionsMet": "YES" if conditions_met else "NO",
            "signalScore": signal_score,
        }
        if conditions_met:
            strict_rows.append(row_payload)
            sr_context_by_symbol[manual_sr_key] = {
                "candles": candles,
                "price": price,
            }
        elif ema_ok and signal_score >= 3:
            relaxed_rows.append(row_payload)
            sr_context_by_symbol[manual_sr_key] = {
                "candles": candles,
                "price": price,
            }

    strict_rows.sort(key=lambda item: (item.get("symbol") or "").upper())
    relaxed_rows.sort(
        key=lambda item: (
            -(int(item.get("signalScore") or 0)),
            -(_safe_float(item.get("volumeRatio20Sort")) or 0.0),
            -(_safe_float(item.get("macdHistSort")) or 0.0),
            -(_safe_float(item.get("rsi14Sort")) or 0.0),
            (item.get("symbol") or "").upper(),
        )
    )
    fallback_applied = False
    rows = strict_rows
    if not rows and relaxed_rows:
        fallback_applied = True
        rows = relaxed_rows[:200]
    manual_sr_map: Dict[str, Dict[str, Any]] = {}
    selected_manual_symbols = sorted({
        _normalize_manual_sr_symbol(row.get("symbol"))
        for row in rows
        if _normalize_manual_sr_symbol(row.get("symbol"))
    })
    if selected_manual_symbols:
        try:
            manual_sr_map = fetch_manual_sr_level_map(selected_manual_symbols)
        except Exception:
            _logger.exception("Failed to load manual Price Action SR levels for selected Bhramhaputra rows")
            manual_sr_map = {}
    for row in rows:
        manual_sr_key = _normalize_manual_sr_symbol(row.get("symbol"))
        sr_context = sr_context_by_symbol.get(manual_sr_key) or {}
        manual_sr_display = _resolve_manual_sr_display(
            manual_sr_key,
            _safe_float(sr_context.get("price")),
            sr_context.get("candles") or [],
            manual_sr_map.get(manual_sr_key),
        )
        row["supportDisplay"] = manual_sr_display["supportDisplay"]
        row["resistanceDisplay"] = manual_sr_display["resistanceDisplay"]
    for index, row in enumerate(rows, 1):
        row["sNo"] = index
        row["sNoSort"] = index

    effective_end_date_iso = (
        source_latest_trade_date.strftime("%Y-%m-%d")
        if source_latest_trade_date
        else (overall_last.strftime("%Y-%m-%d") if overall_last else None)
    )
    if stale_ath_detected:
        log_stale_snapshot_warning(endpoint='/api/bhramhaputra', source='computed-candles')
    return {
        "rows": rows,
        "count": len(rows),
        "generatedAt": datetime.utcnow().isoformat() + "Z",
        "timeframe": tf,
        "cutoffDateIso": cutoff_date_iso,
        "athSource": "NSE_NIFTY500_DAILY_RAW_DATA_DEV",
        "meta": {
            "cutoffMonths": cutoff_months,
            "cutoffDateIso": cutoff_date_iso,
            "cutoffAnchor": "current",
            "fallbackApplied": fallback_applied,
            "strictMatchCount": len(strict_rows),
            "relaxedCandidateCount": len(relaxed_rows),
            "startDate": overall_first.strftime("%Y-%m-%d") if overall_first else None,
            "endDate": effective_end_date_iso,
            "timeframe": tf,
            "athSource": "NSE_NIFTY500_DAILY_RAW_DATA_DEV",
        },
    }


def _parse_row_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    token = text[:10]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(token, fmt).date()
        except ValueError:
            continue
    return None


def _yes_flag(value: Any) -> str:
    text = str(value or "").strip().upper()
    return "Y" if text in {"Y", "YES", "TRUE", "1"} or "YES" in text else "N"


def _first_present(row: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row.get(key) not in (None, ""):
            return row.get(key)
    return None


def _first_numeric(row: Dict[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        value = _first_present(row, key)
        if value is None:
            continue
        number = _safe_float(value)
        if number is not None:
            return number
    return None


def _copy_first_alias(
    row: Dict[str, Any],
    target: str,
    *aliases: str,
    round_digits: Optional[int] = None,
) -> None:
    if _first_present(row, target) is not None:
        return
    value = _first_present(row, *aliases)
    if value is None:
        return
    if round_digits is not None:
        numeric = _safe_float(value)
        row[target] = _safe_round(numeric, round_digits) if numeric is not None else value
        return
    row[target] = value


def _normalize_bhramhaputra_row_display_fields(
    row: Dict[str, Any],
    cutoff_date_iso: Optional[str],
) -> Dict[str, Any]:
    normalized = dict(row)
    if _first_present(normalized, "cutoffDate", "cutoff_date", "CUTOFF_DATE") is None and cutoff_date_iso:
        normalized["cutoffDate"] = cutoff_date_iso

    _copy_first_alias(
        normalized,
        "buyPrice",
        "buy_price",
        "BUY_PRICE",
        "entryPrice",
        "entry_price",
        "ENTRY_PRICE",
        "priceSort",
        "price",
        "PRICE",
        round_digits=2,
    )
    _copy_first_alias(normalized, "sellDate", "sell_date", "SELL_DATE", "exitDate", "exit_date", "EXIT_DATE")
    _copy_first_alias(
        normalized,
        "sellPrice",
        "sell_price",
        "SELL_PRICE",
        "exitPrice",
        "exit_price",
        "EXIT_PRICE",
        round_digits=2,
    )
    _copy_first_alias(normalized, "stopLoss", "stop_loss", "STOP_LOSS", "STOPLOSS", round_digits=2)
    _copy_first_alias(normalized, "target1", "TARGET1", "t1", "T1", round_digits=2)
    _copy_first_alias(normalized, "target2", "TARGET2", "t2", "T2", round_digits=2)
    _copy_first_alias(
        normalized,
        "support",
        "support1",
        "support_1",
        "support_s1",
        "SUPPORT",
        "SUPPORT1",
        "SUPPORT_S1",
        "S1",
        round_digits=2,
    )
    _copy_first_alias(
        normalized,
        "resistance",
        "resistance1",
        "resistance_1",
        "resistance_r1",
        "RESISTANCE",
        "RESISTANCE1",
        "RESISTANCE_R1",
        "R1",
        round_digits=2,
    )

    buy_price = _first_numeric(
        normalized,
        "buyPrice",
        "buy_price",
        "BUY_PRICE",
        "entryPrice",
        "entry_price",
        "ENTRY_PRICE",
        "priceSort",
        "price",
        "PRICE",
    )
    if buy_price is not None:
        if _first_present(normalized, "stopLoss", "stop_loss", "STOP_LOSS", "STOPLOSS") is None:
            normalized["stopLoss"] = _safe_round(buy_price * (1 - BHRAMHAPUTRA_STOP_LOSS_PCT), 2)
        if _first_present(normalized, "target1", "TARGET1", "t1", "T1") is None:
            normalized["target1"] = _safe_round(buy_price * (1 + BHRAMHAPUTRA_TARGET1_PCT), 2)
        if _first_present(normalized, "target2", "TARGET2", "t2", "T2") is None:
            normalized["target2"] = _safe_round(buy_price * (1 + BHRAMHAPUTRA_TARGET2_PCT), 2)
    return normalized


def normalize_bhramhaputra_payload_fields(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return payload
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return payload
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    cutoff_date_iso = (
        payload.get("cutoffDateIso")
        or payload.get("cutoffDate")
        or (meta or {}).get("cutoffDateIso")
        or (meta or {}).get("cutoffDate")
    )
    normalized_rows = [
        _normalize_bhramhaputra_row_display_fields(row, str(cutoff_date_iso) if cutoff_date_iso else None)
        if isinstance(row, dict)
        else row
        for row in rows
    ]
    return {
        **payload,
        "rows": normalized_rows,
    }


def _bhramhaputra_insert_bind(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    symbol = str(_first_present(row, "symbol", "stock", "stockName", "STOCK_NAME") or "").strip().upper()
    buy_date = _parse_row_date(
        _first_present(
            row,
            "ltcDate",
            "ltc_date",
            "LTC_DATE",
            "buyingDate",
            "buying_date",
            "buyDate",
            "buy_date",
            "tradeDate",
            "trade_date",
            "TRADE_DATE",
        )
    )
    price = _safe_float(_first_present(row, "priceSort", "price", "PRICE"))
    buy_price = _safe_float(_first_present(row, "buyPrice", "buy_price", "entryPrice", "priceSort", "price"))
    if buy_price is None:
        buy_price = price
    if not symbol or not buy_date or buy_price is None:
        return None
    stop_loss = _safe_float(_first_present(row, "stopLoss", "stop_loss"))
    target1 = _safe_float(_first_present(row, "target1"))
    target2 = _safe_float(_first_present(row, "target2"))
    if stop_loss is None:
        stop_loss = buy_price * (1 - BHRAMHAPUTRA_STOP_LOSS_PCT)
    if target1 is None:
        target1 = buy_price * (1 + BHRAMHAPUTRA_TARGET1_PCT)
    if target2 is None:
        target2 = buy_price * (1 + BHRAMHAPUTRA_TARGET2_PCT)
    return {
        "s_no": row.get("sNo") or row.get("s_no"),
        "stock_name": symbol,
        "price": price if price is not None else buy_price,
        "buy_price": buy_price,
        "buy_date": buy_date,
        "stop_loss": _safe_round(stop_loss, 4),
        "target1": _safe_round(target1, 4),
        "target2": _safe_round(target2, 4),
        "ema_gt_20": _yes_flag(_first_present(row, "emaSignal", "ema_signal", "EMA_GT_20")),
        "rsi_gt_30": _yes_flag(_first_present(row, "rsiSignal", "rsi_signal", "RSI_GT_30")),
        "macd_gt_0": _yes_flag(_first_present(row, "macdSignal", "macd_signal", "MACD_GT_0")),
        "volume_gt_20": _yes_flag(_first_present(row, "volumeSignal", "volume_signal", "VOLUME_GT_20")),
        "atr14": _safe_float(_first_present(row, "atr14Sort", "atr14", "atr_14", "ATR14")),
        "bullish": _yes_flag(_first_present(row, "bullishPattern", "bullish_pattern", "BULLISH")),
        "trend": str(_first_present(row, "trendDirectionRaw", "trendDirection", "trend_direction", "TREND") or "").strip()[:30],
    }


def _normalize_bhramhaputra_insert_rows(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    normalized: List[Dict[str, Any]] = []
    skipped = 0
    seen: set[Tuple[str, date]] = set()
    for row in rows or []:
        if not isinstance(row, dict):
            skipped += 1
            continue
        bind = _bhramhaputra_insert_bind(row)
        if not bind:
            skipped += 1
            continue
        key = (str(bind["stock_name"]).upper(), bind["buy_date"])
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        normalized.append(bind)
    return normalized, skipped


def fetch_bhramhaputra_last_ltc_date() -> Optional[str]:
    if pool is None:
        raise RuntimeError("Oracle pool is unavailable for Bhramhaputra date query")
    table = _safe_identifier(BHRAMHAPUTRA_INSERT_TABLE)
    with pool.acquire() as conn:
        available = _table_columns(conn, table)
        if "BUY_DATE" not in available:
            raise RuntimeError(f"Bhramhaputra insert table {table} is missing BUY_DATE")
        with conn.cursor() as cur:
            cur.execute(f"SELECT TO_CHAR(MAX(BUY_DATE), 'YYYY-MM-DD') FROM {table}")
            row = cur.fetchone()
    return str(row[0]).strip() if row and row[0] else None


def insert_bhramhaputra_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if pool is None:
        raise RuntimeError("Oracle pool is unavailable for Bhramhaputra insert")
    started = datetime.utcnow()
    table = _safe_identifier(BHRAMHAPUTRA_INSERT_TABLE)
    binds, invalid_skipped = _normalize_bhramhaputra_insert_rows(rows)
    total_processed = len(rows or [])
    if not binds:
        return {
            "insertedCount": 0,
            "skippedCount": invalid_skipped,
            "updatedCount": 0,
            "totalProcessed": total_processed,
            "latestLtcDate": None,
            "message": "No valid Bhramhaputra rows to insert.",
        }

    latest_ltc_date = max((bind["buy_date"] for bind in binds), default=None)
    inserted = 0
    skipped_existing = 0
    with pool.acquire() as conn:
        available = _table_columns(conn, table)
        required = {"STOCK_NAME", "BUY_DATE"}
        missing = required - available
        if missing:
            raise RuntimeError(f"Bhramhaputra insert table {table} missing required columns: {', '.join(sorted(missing))}")
        existing: set[Tuple[str, date]] = set()
        date_binds = sorted({bind["buy_date"] for bind in binds if bind.get("buy_date")})
        if date_binds:
            placeholders = ", ".join(f":dt_{idx}" for idx in range(len(date_binds)))
            params = {f"dt_{idx}": value for idx, value in enumerate(date_binds)}
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT UPPER(STOCK_NAME), BUY_DATE
                    FROM {table}
                    WHERE BUY_DATE IN ({placeholders})
                    """,
                    params,
                )
                for stock, buy_date in cur.fetchall() or []:
                    parsed = _parse_row_date(buy_date)
                    normalized = str(stock or "").strip().upper()
                    if normalized and parsed:
                        existing.add((normalized, parsed))

        inserts = []
        for bind in binds:
            key = (str(bind["stock_name"]).strip().upper(), bind["buy_date"])
            if key in existing:
                skipped_existing += 1
                continue
            inserts.append(bind)

        if inserts:
            if "S_NO" in available:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT NVL(MAX(S_NO), 0) FROM {table}")
                    max_s_no = int((cur.fetchone() or [0])[0] or 0)
                for offset, bind in enumerate(inserts, start=1):
                    bind["s_no"] = max_s_no + offset
            columns = [
                "STOCK_NAME",
                "PRICE",
                "BUY_PRICE",
                "BUY_DATE",
                "STOP_LOSS",
                "TARGET1",
                "TARGET2",
                "EMA_GT_20",
                "RSI_GT_30",
                "MACD_GT_0",
                "VOLUME_GT_20",
                "ATR14",
                "BULLISH",
                "TREND",
                "CREATED_AT",
                "UPDATED_AT",
            ]
            values = [
                ":stock_name",
                ":price",
                ":buy_price",
                ":buy_date",
                ":stop_loss",
                ":target1",
                ":target2",
                ":ema_gt_20",
                ":rsi_gt_30",
                ":macd_gt_0",
                ":volume_gt_20",
                ":atr14",
                ":bullish",
                ":trend",
                "CURRENT_TIMESTAMP",
                "CURRENT_TIMESTAMP",
            ]
            if "S_NO" in available:
                columns.insert(0, "S_NO")
                values.insert(0, ":s_no")
            insert_sql = f"""
                INSERT INTO {table} ({", ".join(columns)})
                VALUES ({", ".join(values)})
            """
            with conn.cursor() as cur:
                cur.executemany(insert_sql, inserts)
                inserted = int(cur.rowcount or len(inserts))
            conn.commit()

    skipped_count = invalid_skipped + skipped_existing
    elapsed_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
    _logger.info(
        "Bhramhaputra insert table=%s latest_ltc_date=%s processed=%s inserted=%s skipped=%s updated=%s elapsed_ms=%s",
        table,
        latest_ltc_date.isoformat() if latest_ltc_date else None,
        total_processed,
        inserted,
        skipped_count,
        0,
        elapsed_ms,
    )
    if inserted > 0 and skipped_count > 0:
        message = f"Inserted {inserted} Bhramhaputra rows, skipped {skipped_count} existing/invalid rows."
    elif inserted > 0:
        message = f"Inserted {inserted} new Bhramhaputra rows."
    else:
        message = "No new Bhramhaputra rows. Existing rows skipped."
    return {
        "insertedCount": inserted,
        "skippedCount": skipped_count,
        "updatedCount": 0,
        "totalProcessed": total_processed,
        "latestLtcDate": latest_ltc_date.strftime("%Y-%m-%d") if latest_ltc_date else None,
        "message": message,
    }


def upsert_bhramhaputra_rows(rows: List[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    if pool is None:
        raise RuntimeError("Oracle pool is unavailable for Bhramhaputra upsert")

    merge_sql = f"""
        MERGE INTO {BHRAMHAPUTRA_TABLE} t
        USING (
            SELECT :symbol AS symbol, :trade_date AS trade_date FROM dual
        ) src
        ON (t.SYMBOL = src.symbol AND t.TRADE_DATE = src.trade_date)
        WHEN MATCHED THEN UPDATE SET
            PRICE = :price,
            EMA20 = :ema20,
            EMA20_FLAG = :ema20_flag,
            RSI14 = :rsi14,
            RSI_FLAG = :rsi_flag,
            MACD_HIST = :macd_hist,
            MACD_FLAG = :macd_flag,
            VOLUME = :volume,
            AVG_VOLUME20 = :avg_volume20,
            VOLUME_RATIO20 = :volume_ratio20,
            VOLUME_FLAG = :volume_flag,
            ATR14 = :atr14,
            TREND_DIRECTION = :trend_direction,
            BULLISH_PATTERN = :bullish_pattern,
            SUPPORT_S1 = :support_s1,
            SUPPORT_S2 = :support_s2,
            RESISTANCE_R1 = :resistance_r1,
            RESISTANCE_R2 = :resistance_r2,
            HIGH_52W = :high_52w,
            LOW_52W = :low_52w,
            HIGH_1Y = :high_1y,
            HIGH_2Y = :high_2y,
            ATH = :ath,
            YTD_PCT = :ytd_pct,
            CONDITIONS_MET = :conditions_met,
            UPDATED_AT = CURRENT_TIMESTAMP
        WHEN NOT MATCHED THEN INSERT (
            SYMBOL,
            TRADE_DATE,
            PRICE,
            EMA20,
            EMA20_FLAG,
            RSI14,
            RSI_FLAG,
            MACD_HIST,
            MACD_FLAG,
            VOLUME,
            AVG_VOLUME20,
            VOLUME_RATIO20,
            VOLUME_FLAG,
            ATR14,
            TREND_DIRECTION,
            BULLISH_PATTERN,
            SUPPORT_S1,
            SUPPORT_S2,
            RESISTANCE_R1,
            RESISTANCE_R2,
            HIGH_52W,
            LOW_52W,
            HIGH_1Y,
            HIGH_2Y,
            ATH,
            YTD_PCT,
            CONDITIONS_MET,
            CREATED_AT,
            UPDATED_AT
        ) VALUES (
            :symbol,
            :trade_date,
            :price,
            :ema20,
            :ema20_flag,
            :rsi14,
            :rsi_flag,
            :macd_hist,
            :macd_flag,
            :volume,
            :avg_volume20,
            :volume_ratio20,
            :volume_flag,
            :atr14,
            :trend_direction,
            :bullish_pattern,
            :support_s1,
            :support_s2,
            :resistance_r1,
            :resistance_r2,
            :high_52w,
            :low_52w,
            :high_1y,
            :high_2y,
            :ath,
            :ytd_pct,
            :conditions_met,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        )
    """

    binds: List[Dict[str, Any]] = []
    for row in rows:
        trade_date = row.get("tradeDate")
        if isinstance(trade_date, str):
            try:
                trade_date = datetime.strptime(trade_date, "%Y-%m-%d").date()
            except ValueError:
                trade_date = None
        binds.append({
            "symbol": row.get("symbol"),
            "trade_date": trade_date,
            "price": row.get("priceSort") or row.get("price"),
            "ema20": row.get("ema20Sort") or row.get("ema20"),
            "ema20_flag": "Y" if row.get("emaSignal") == "YES" else "N",
            "rsi14": row.get("rsi14Sort") or row.get("rsi14"),
            "rsi_flag": "Y" if row.get("rsiSignal") == "YES" else "N",
            "macd_hist": row.get("macdHistSort") or row.get("macdHist"),
            "macd_flag": "Y" if row.get("macdSignal") == "YES" else "N",
            "volume": row.get("volumeSort") or row.get("volume"),
            "avg_volume20": row.get("avgVolume20Sort") or row.get("avgVolume20"),
            "volume_ratio20": row.get("volumeRatio20Sort") or row.get("volumeRatio20"),
            "volume_flag": "Y" if row.get("volumeSignal") == "YES" else "N",
            "atr14": row.get("atr14Sort") or row.get("atr14"),
            "trend_direction": row.get("trendDirection"),
            "bullish_pattern": "Y" if row.get("bullishPattern") == "YES" else "N",
            "support_s1": row.get("support1"),
            "support_s2": row.get("support2"),
            "resistance_r1": row.get("resistance1"),
            "resistance_r2": row.get("resistance2"),
            "high_52w": row.get("high52w"),
            "low_52w": row.get("low52w"),
            "high_1y": row.get("high1y"),
            "high_2y": row.get("high2y"),
            "ath": row.get("ath"),
            "ytd_pct": row.get("ytdPct"),
            "conditions_met": "Y" if row.get("conditionsMet") == "YES" else "N",
        })

    inserted = 0
    with pool.acquire() as conn:
        with conn.cursor() as cur:
            cur.executemany(merge_sql, binds)
            inserted = cur.rowcount or len(binds)
        conn.commit()
    return inserted
