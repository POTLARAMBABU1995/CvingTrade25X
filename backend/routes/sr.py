from __future__ import annotations

import hashlib
import logging
import math
import os
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

from flask import Blueprint, jsonify, request

from cache import TTLCache, background_refresh, load_json_snapshot, save_json_snapshot

try:
    from ..config import settings
    from ..db_pool import fetchall_dict, pool
    from ..db import fetch_ohlc_series_from_oracle
    from ..sr_levels import build_sr_levels_payload
    from ..services import nse_mcap_service as nse_mcap_svc
except ImportError:
    from config import settings  # type: ignore
    from db_pool import fetchall_dict, pool  # type: ignore
    from db import fetch_ohlc_series_from_oracle  # type: ignore
    from sr_levels import build_sr_levels_payload  # type: ignore
    from services import nse_mcap_service as nse_mcap_svc  # type: ignore


_logger = logging.getLogger(__name__)
_SOURCE_SCHEMA = (os.getenv('ORACLE_SCHEMA') or '').strip()
_SOURCE_TABLE = (os.getenv('ORACLE_TABLE') or 'NSE_NIFTY500_DAILY_RAW_DATA_DEV').strip()
_MANUAL_SR_SCHEMA = (os.getenv('PRICE_ACTION_SR_SCHEMA') or os.getenv('ORACLE_SCHEMA') or '').strip()
_MANUAL_SR_TABLE = (os.getenv('PRICE_ACTION_SR_LEVELS_MANUALLY_TABLE') or 'PRICE_ACTION_SR_LEVELS_MANUALLY').strip()
_IDENT_RE = re.compile(r'^[A-Za-z0-9_.$#]+$')
_MANUAL_TF_MAP = {
    '1D': 'daily',
    'D': 'daily',
    'DAILY': 'daily',
    '1W': 'weekly',
    'W': 'weekly',
    'WEEKLY': 'weekly',
    '1M': 'monthly',
    'M': 'monthly',
    'MONTHLY': 'monthly',
    '1Y': 'yearly',
    'Y': 'yearly',
    'YEARLY': 'yearly',
    'ANNUAL': 'yearly',
}
SR_TIMEFRAME_OPTIONS = ('daily', 'weekly', 'monthly', 'yearly')
SR_TOLERANCE_OPTIONS = [0.05, 0.10, 0.15, 0.20]
SR_MAX_LOOKBACK_DAYS = 504
TRADING_DAYS_LOOKBACK = max(0, min(SR_MAX_LOOKBACK_DAYS, settings.sr_trading_days_lookback))
SR_CUTOFF_MONTHS = 24
SR_DEFAULT_SORT_FIELD = 'score'
SR_DEFAULT_SORT_DIRECTION = 'desc'
SR_SORTABLE_FIELDS = ('score', 'trend_direction')
SR_DEFAULT_LOOKBACK = 'max'
SR_PRICE_ACTION_FILTERS = {
    'all',
    'neutral',
    'range',
    'breakout',
    'breakdown',
    'bullish_rejection',
    'bearish_rejection',
    'bullish_engulfing',
    'bearish_engulfing',
    'inside_bar',
}
SR_TREND_DIRECTION_FILTERS = {
    'all',
    'uptrend',
    'downtrend',
    'consolidation',
}
_SORT_FIELD_ALIASES = {
    'score': 'score',
    'scoresort': 'score',
    'score_sort': 'score',
    'trenddirection': 'trend_direction',
    'trend_direction': 'trend_direction',
    'trend': 'trend_direction',
    'trenddir': 'trend_direction',
}
_SORT_DEFAULTS = {
    'score': 'desc',
    'trend_direction': 'asc',
}

bp = Blueprint('sr', __name__)

_cache = TTLCache(ttl_seconds=int((os.getenv('SR_CACHE_TTL') or '600')))
_snapshot_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
_BASE_CACHE_PREFIX = "sr:base"
_TRADING_WINDOW_CACHE_KEY = "sr:trading-window"


def _source_table_name() -> str:
    if _SOURCE_SCHEMA and _SOURCE_TABLE:
        return f"{_SOURCE_SCHEMA}.{_SOURCE_TABLE}"
    return _SOURCE_TABLE


def _safe_identifier(value: str) -> str:
    name = (value or '').strip()
    if not name or not _IDENT_RE.match(name):
        raise ValueError(f'Invalid identifier: {value!r}')
    return name


def _manual_sr_table_name() -> str:
    table = _safe_identifier(_MANUAL_SR_TABLE)
    if '.' in table:
        return table
    schema = _safe_identifier(_MANUAL_SR_SCHEMA) if _MANUAL_SR_SCHEMA else ''
    return f'{schema}.{table}' if schema else table


def _normalize_manual_timeframe(value: Any) -> Optional[str]:
    token = str(value or '').strip().upper()
    if not token:
        return 'daily'
    return _MANUAL_TF_MAP.get(token)


def _chunked(values: List[str], size: int = 900) -> Iterable[List[str]]:
    for index in range(0, len(values), size):
        yield values[index:index + size]


def _fetch_manual_sr_levels(symbols: List[str]) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    normalized_symbols = sorted({normalize_symbol(symbol) for symbol in (symbols or []) if normalize_symbol(symbol)})
    if not normalized_symbols:
        return {}

    table = _manual_sr_table_name()
    timeframe_tokens = sorted(_MANUAL_TF_MAP.keys())
    grouped: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    with pool.acquire() as conn:
        for chunk in _chunked(normalized_symbols):
            symbol_binds = {f'sym_{idx}': symbol for idx, symbol in enumerate(chunk)}
            timeframe_binds = {f'tf_{idx}': token for idx, token in enumerate(timeframe_tokens)}
            symbol_placeholders = ', '.join(f':sym_{idx}' for idx in range(len(chunk)))
            timeframe_placeholders = ', '.join(f':tf_{idx}' for idx in range(len(timeframe_tokens)))
            sql = f'''
                SELECT SYMBOL,
                       TF,
                       LEVEL_TYPE,
                       SR_LEVEL,
                       CREATED_AT,
                       UPDATED_AT
                FROM {table}
                WHERE TRIM(UPPER(SYMBOL)) IN ({symbol_placeholders})
                  AND TRIM(UPPER(NVL(TF, '1D'))) IN ({timeframe_placeholders})
                ORDER BY SYMBOL ASC, SR_LEVEL ASC, UPDATED_AT DESC, CREATED_AT DESC
            '''
            binds = {**symbol_binds, **timeframe_binds}
            with conn.cursor() as cur:
                cur.execute(sql, binds)
                rows = fetchall_dict(cur)
            for row in rows:
                symbol = normalize_symbol(row.get('symbol'))
                timeframe = _normalize_manual_timeframe(row.get('tf'))
                price = _to_float(row.get('sr_level'))
                if not symbol or not timeframe or price is None:
                    continue
                grouped.setdefault(symbol, {}).setdefault(timeframe, []).append({
                    'level_type': row.get('level_type'),
                    'price': price,
                    'created_at': _format_date(row.get('created_at')),
                    'updated_at': _format_date(row.get('updated_at')),
                })
    return grouped


def _normalize_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    return None


def _format_iso(value: Optional[datetime]) -> Optional[str]:
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d')
    return None


def _parse_lookback_days(raw_value: Optional[str]) -> str | int:
    token = str(raw_value or '').strip().lower()
    if not token or token in {'auto', 'max', 'all', 'full'}:
        return 'max'
    try:
        numeric = int(token)
    except ValueError:
        return SR_DEFAULT_LOOKBACK
    return max(66, min(SR_MAX_LOOKBACK_DAYS, numeric))


def _is_max_lookback(lookback_days: str | int) -> bool:
    return isinstance(lookback_days, str) and str(lookback_days).strip().lower() == 'max'


def _parse_min_touches(raw_value: Optional[str]) -> int:
    try:
        numeric = int(str(raw_value or '').strip() or '1')
    except ValueError:
        return 1
    return max(1, min(10, numeric))


def _normalize_price_action_filter(raw_value: Optional[str]) -> str:
    token = str(raw_value or '').strip().lower()
    if not token:
        return 'all'
    return token if token in SR_PRICE_ACTION_FILTERS else 'all'


def _normalize_trend_direction_filter(raw_value: Optional[str]) -> str:
    token = str(raw_value or '').strip().lower()
    if not token or token in {'all', 'total'}:
        return 'all'
    if 'range' in token or 'sideways' in token or 'consolidation' in token:
        normalized = 'consolidation'
    elif 'up' in token:
        normalized = 'uptrend'
    elif 'down' in token:
        normalized = 'downtrend'
    else:
        normalized = token
    return normalized if normalized in SR_TREND_DIRECTION_FILTERS else 'all'


def _fetch_month_span(lookback_days: str | int) -> Optional[int]:
    if _is_max_lookback(lookback_days):
        return None
    if isinstance(lookback_days, int):
        requested_days = lookback_days
    else:
        requested_days = max(TRADING_DAYS_LOOKBACK, SR_MAX_LOOKBACK_DAYS)
    target_days = requested_days
    return max(SR_CUTOFF_MONTHS, min(48, int(math.ceil(target_days / 21.0))))


def _resolve_trading_window(lookback_days: str | int = SR_DEFAULT_LOOKBACK) -> Dict[str, Any]:
    """Inspect the OHLC source table to determine the latest and cutoff trading dates."""
    table = _source_table_name()

    if _is_max_lookback(lookback_days):
        with pool.acquire() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                        SELECT MIN(TRADING_DATE) AS cutoff_date,
                               MAX(TRADING_DATE) AS ltc_date,
                               COUNT(DISTINCT TRADING_DATE) AS trading_days
                        FROM {table}
                    """
                )
                row = cur.fetchone()
                cutoff = _normalize_datetime(row[0]) if row else None
                latest = _normalize_datetime(row[1]) if row else None
                trading_days = int(row[2] or 0) if row and len(row) > 2 else 0
        if latest is None:
            return {"ltc_date": None, "cutoff_date": None, "trading_day_count": 0}
        if cutoff is None:
            cutoff = latest
        if trading_days <= 0:
            trading_days = 1
        return {
            "ltc_date": latest,
            "cutoff_date": cutoff,
            "trading_day_count": trading_days,
        }

    if isinstance(lookback_days, int):
        requested_lookback = lookback_days
    else:
        requested_lookback = max(1, TRADING_DAYS_LOOKBACK or SR_MAX_LOOKBACK_DAYS)
    lookback = max(1, requested_lookback)
    with pool.acquire() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT MAX(TRADING_DATE) FROM {table}")
            row = cur.fetchone()
            latest = _normalize_datetime(row[0]) if row else None
        cutoff = None
        trading_days = 0
        if latest:
            cutoff_sql = f"""
                SELECT MIN(trading_date) AS cutoff, COUNT(*) AS trading_days
                FROM (
                    SELECT DISTINCT TRADING_DATE
                    FROM {table}
                    WHERE TRADING_DATE <= :ltc_date
                    ORDER BY TRADING_DATE DESC
                    FETCH FIRST {lookback} ROWS ONLY
                )
            """
            with conn.cursor() as cur:
                cur.execute(cutoff_sql, {"ltc_date": latest})
                row = cur.fetchone()
                if row:
                    cutoff = _normalize_datetime(row[0])
                    trading_days = int(row[1] or 0) if len(row) > 1 else 0
    if latest is None:
        return {"ltc_date": None, "cutoff_date": None, "trading_day_count": 0}
    if cutoff is None:
        cutoff = latest
    if trading_days <= 0 and cutoff:
        trading_days = 1
    return {
        "ltc_date": latest,
        "cutoff_date": cutoff,
        "trading_day_count": trading_days,
    }


def _get_cached_trading_window(lookback_days: str | int = SR_DEFAULT_LOOKBACK, force_refresh: bool = False) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    cache_key = f"{_TRADING_WINDOW_CACHE_KEY}|lookback:{lookback_days}"
    if not force_refresh:
        cached = _cache.get(cache_key)
        if isinstance(cached, dict):
            return cached, _format_iso(cached.get('ltc_date'))
    try:
        window = _resolve_trading_window(lookback_days)
    except Exception:  # pragma: no cover
        _logger.exception("Unable to resolve trading window for SR levels")
        return None, None
    _cache.set(cache_key, window)
    return window, _format_iso(window.get('ltc_date'))


def _derive_window_from_series(series: Dict[str, List[Dict[str, Any]]], lookback_days: str | int = SR_DEFAULT_LOOKBACK) -> Tuple[Optional[datetime], Optional[datetime], int]:
    dates: List[datetime] = []
    for candles in series.values():
        for candle in candles:
            dt = candle.get('date')
            if isinstance(dt, datetime):
                dates.append(dt)
    if not dates:
        return None, None, 0
    dates.sort()
    if _is_max_lookback(lookback_days):
        requested = len(dates)
    elif isinstance(lookback_days, int):
        requested = lookback_days
    else:
        requested = max(1, TRADING_DAYS_LOOKBACK or min(len(dates), SR_MAX_LOOKBACK_DAYS))
    lookback = max(1, requested)
    slice_size = min(len(dates), lookback)
    window = dates[-slice_size:]
    return window[-1], window[0], slice_size


def _trim_series_to_window(
    series: Dict[str, List[Dict[str, Any]]],
    cutoff: Optional[datetime],
    latest: Optional[datetime],
) -> Dict[str, List[Dict[str, Any]]]:
    trimmed: Dict[str, List[Dict[str, Any]]] = {}
    for symbol, candles in series.items():
        scoped: List[Dict[str, Any]] = []
        for candle in candles:
            dt = candle.get('date')
            if not isinstance(dt, datetime):
                continue
            if cutoff and dt < cutoff:
                continue
            if latest and dt > latest:
                continue
            scoped.append(candle)
        if scoped:
            trimmed[symbol] = scoped
    return trimmed


def _sanitize_sort_token(value: str) -> str:
    return ''.join(ch for ch in value.lower() if ch.isalnum())


def _resolve_sort_params(sort_field: Optional[str], sort_dir: Optional[str]) -> Tuple[str, str]:
    field = SR_DEFAULT_SORT_FIELD
    if sort_field:
        token = _sanitize_sort_token(sort_field)
        field = _SORT_FIELD_ALIASES.get(token, SR_DEFAULT_SORT_FIELD)
    default_dir = _SORT_DEFAULTS.get(field, SR_DEFAULT_SORT_DIRECTION)
    direction = default_dir
    if sort_dir:
        dir_token = sort_dir.strip().lower()
        if dir_token in ('asc', 'desc'):
            direction = dir_token
    return field, direction


def _score_sort_value(row: Dict[str, Any]) -> Optional[float]:
    score = _to_float(row.get('scoreSort'))
    if score is None:
        score = _to_float(row.get('score'))
    return score


def _trend_sort_value(row: Dict[str, Any]) -> str:
    candidates = (
        row.get('trendDirectionSort'),
        row.get('trend_direction_sort'),
        row.get('trendDirection'),
        row.get('trend_direction'),
    )
    for value in candidates:
        if value is None:
            continue
        label = str(value).strip().upper()
        if not label or label in {'-', 'N/A', 'NA'}:
            continue
        return label
    return ''


def _sort_rows(rows: List[Dict[str, Any]], sort_by: str, sort_dir: str) -> None:
    if sort_by == 'trend_direction':
        rank_map = {'up': 0, 'down': 1, 'consolidation': 2}
        if sort_dir == 'desc':
            rank_map = {'consolidation': 0, 'down': 1, 'up': 2}

        def trend_key(row: Dict[str, Any]) -> Tuple[int, int, str]:
            bucket = _trend_bucket(_trend_sort_value(row))
            missing = 1 if not bucket else 0
            rank = rank_map.get(bucket or '', 99)
            return (missing, rank, str(row.get('symbol') or '').upper())

        rows.sort(key=trend_key)
        return

    reverse = sort_dir == 'desc'
    def score_key(row: Dict[str, Any]) -> Tuple[int, float, str]:
        score = _score_sort_value(row)
        missing = 1 if score is None else 0
        value = score if score is not None else 0.0
        return (missing, value, str(row.get('symbol') or '').upper())

    rows.sort(key=score_key, reverse=reverse)


def _trend_bucket(value: Any) -> Optional[str]:
    token = str(value or '').strip().lower()
    if not token:
        return None
    if 'up' in token:
        return 'up'
    if 'down' in token:
        return 'down'
    if 'consolidation' in token or 'range' in token:
        return 'consolidation'
    return None


def _summarize_trends(rows: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    counts = {
        "up": 0,
        "down": 0,
        "consolidation": 0,
        "total": 0,
    }
    for row in rows:
        counts["total"] += 1
        bucket = _trend_bucket(row.get('trend_direction') or row.get('trendDirection'))
        if bucket:
            counts[bucket] += 1
    return counts


def _apply_trend_direction_filter(
    rows: Iterable[Dict[str, Any]],
    trend_direction_filter: str = 'all',
) -> List[Dict[str, Any]]:
    normalized = _normalize_trend_direction_filter(trend_direction_filter)
    if normalized == 'all':
        return list(rows)

    target_bucket = _trend_bucket(normalized)
    if not target_bucket:
        return list(rows)

    filtered: List[Dict[str, Any]] = []
    for row in rows:
        bucket = _trend_bucket(row.get('trend_direction') or row.get('trendDirection'))
        if bucket == target_bucket:
            filtered.append(row)
    return filtered


def _filter_rows(
    rows: Iterable[Dict[str, Any]],
    symbols_filter: Optional[List[str]],
    search_term: Optional[str],
    price_action_filter: str = 'all',
) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    symbols_set = set(symbols_filter) if symbols_filter else None
    for row in rows:
        symbol = normalize_symbol(row.get('symbol'))
        if symbols_set and symbol not in symbols_set:
            continue
        if search_term and (not symbol or not symbol.startswith(search_term)):
            continue
        if price_action_filter != 'all':
            state = str((row.get('priceAction') or {}).get('state') or '').strip().lower()
            if state != price_action_filter:
                continue
        filtered.append(row)
    return filtered


def _format_window_meta(window: Dict[str, Any]) -> Dict[str, Any]:
    ltc = window.get('ltc_date')
    cutoff = window.get('cutoff_date')
    trading_days = int(window.get('trading_day_count') or 0)
    return {
        "ltcDateIso": _format_iso(ltc),
        "cutoffDateIso": _format_iso(cutoff),
        "tradingDayCount": trading_days,
        "startDate": _format_iso(cutoff),
        "endDate": _format_iso(ltc),
    }


def _base_cache_key(tolerance: float, timeframe: str, ltc_iso: Optional[str], lookback_days: str | int, min_touches: int) -> str:
    token = ltc_iso or 'unknown'
    return f"{_BASE_CACHE_PREFIX}|tf:{timeframe}|tol:{tolerance:.4f}|ltc:{token}|lookback:{lookback_days}|touches:{min_touches}"


def _is_base_valid(payload: Dict[str, Any] | None, expected_ltc_iso: Optional[str], lookback_days: str | int, min_touches: int) -> bool:
    if not isinstance(payload, dict):
        return False
    cached_ltc = payload.get('ltcDateIso') or (payload.get('window_meta') or {}).get('ltcDateIso')
    if expected_ltc_iso and cached_ltc and cached_ltc != expected_ltc_iso:
        return False
    if payload.get('lookbackDays') != lookback_days:
        return False
    if int(payload.get('minTouches') or 1) != int(min_touches or 1):
        return False
    return True


def _compute_base_payload(
    tolerance: float,
    timeframe: str,
    trading_window: Optional[Dict[str, Any]],
    lookback_days: str | int = SR_DEFAULT_LOOKBACK,
    min_touches: int = 1,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    latest_ltc_iso = _format_iso(trading_window.get('ltc_date')) if trading_window else None
    base_key = _base_cache_key(tolerance, timeframe, latest_ltc_iso, lookback_days, min_touches)
    if not force_refresh:
        cached = _cache.get(base_key)
        if cached is not None and _is_base_valid(cached, latest_ltc_iso, lookback_days, min_touches):
            return cached

    try:
        raw_series = fetch_ohlc_series_from_oracle(months=_fetch_month_span(lookback_days), cutoff_anchor='latest')
    except Exception:  # pragma: no cover
        _logger.exception("Failed to load OHLC series for SR levels")
        raise

    window = trading_window or {}
    ltc_date = _normalize_datetime(window.get('ltc_date'))
    cutoff_date = _normalize_datetime(window.get('cutoff_date'))
    trading_day_count = int(window.get('trading_day_count') or 0)
    if ltc_date is None or cutoff_date is None or trading_day_count <= 0:
        derived_ltc, derived_cutoff, derived_days = _derive_window_from_series(raw_series, lookback_days)
        ltc_date = ltc_date or derived_ltc
        cutoff_date = cutoff_date or derived_cutoff
        trading_day_count = trading_day_count or derived_days

    scoped_series = _trim_series_to_window(raw_series, cutoff_date, ltc_date)
    if not scoped_series:
        _logger.warning(
            "No scoped OHLC data for cutoff %s - using raw series as fallback",
            cutoff_date,
        )
        scoped_series = raw_series

    manual_levels_by_symbol: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    try:
        manual_levels_by_symbol = _fetch_manual_sr_levels(list(scoped_series.keys()))
    except Exception:  # pragma: no cover
        _logger.warning("Unable to load manual PriceAction SR levels; continuing with generated levels", exc_info=True)

    sr_payload = build_sr_levels_payload(
        scoped_series,
        [],
        tolerance,
        timeframe,
        lookback_days=lookback_days,
        min_touches=min_touches,
        manual_levels_by_symbol=manual_levels_by_symbol,
    )
    rows_all = sr_payload.get('rows', [])
    window_meta = _format_window_meta({
        "ltc_date": ltc_date,
        "cutoff_date": cutoff_date,
        "trading_day_count": trading_day_count,
    })
    base_payload: Dict[str, Any] = {
        "rows": rows_all,
        "window_meta": window_meta,
        "ltcDateIso": window_meta.get('ltcDateIso'),
        "cutoffDateIso": window_meta.get('cutoffDateIso'),
        "tradingDayCount": window_meta.get('tradingDayCount'),
        "lookbackDays": lookback_days,
        "minTouches": min_touches,
    }
    _cache.set(base_key, base_payload)
    return base_payload


def normalize_symbol(symbol: str | None) -> str:
    if symbol is None:
        return ''
    sym = str(symbol).strip()
    if not sym:
        return ''
    sym_upper = sym.upper()
    if sym_upper.startswith('NSE:'):
        sym = sym[4:]
        sym_upper = sym.upper()
    if sym_upper.endswith('-EQ'):
        sym = sym[:-3]
    return sym.strip().upper()


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _format_date(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d')
    if isinstance(value, str):
        return value
    return None


def _key_for(
    tolerance: float,
    timeframe: str,
    symbols: Optional[List[str]],
    search: str | None,
    page: int,
    page_size: int,
    sort_by: str,
    sort_dir: str,
    lookback_days: str | int,
    min_touches: int,
    price_action_filter: str,
    trend_direction_filter: str,
) -> str:
    joined = ','.join(symbols or [])
    search_token = (search or '').upper()
    return (
        f"tf:{timeframe}|tol:{tolerance:.4f}|symbols:{joined}|search:{search_token}"
        f"|page:{page}|size:{page_size}|sort:{sort_by}:{sort_dir}"
        f"|lookback:{lookback_days}|touches:{min_touches}|price_action:{price_action_filter}"
        f"|trend_direction:{trend_direction_filter}"
    )


def _snapshot_path(
    tolerance: float,
    timeframe: str,
    symbols: Optional[List[str]],
    search: str | None,
    page: int,
    page_size: int,
    sort_by: str,
    sort_dir: str,
    lookback_days: str | int,
    min_touches: int,
    price_action_filter: str,
    trend_direction_filter: str,
) -> str:
    os.makedirs(_snapshot_dir, exist_ok=True)
    tol_part = f"{tolerance:.3f}".replace('.', '_')
    tf_part = timeframe.lower()
    search_suffix = ''
    if search:
        digest = hashlib.sha1(search.encode('utf-8')).hexdigest()[:8]
        search_suffix = f"_search_{digest}"
    page_part = f"_p{page}_s{page_size}"
    sort_suffix = ''
    if not (sort_by == SR_DEFAULT_SORT_FIELD and sort_dir == SR_DEFAULT_SORT_DIRECTION):
        sort_suffix = f"_sort_{sort_by}_{sort_dir}"
    option_suffix = ''
    if lookback_days != SR_DEFAULT_LOOKBACK:
        option_suffix += f"_lb_{lookback_days}"
    if int(min_touches or 1) != 1:
        option_suffix += f"_mt_{int(min_touches)}"
    if price_action_filter and price_action_filter != 'all':
        option_suffix += f"_pa_{price_action_filter}"
    if trend_direction_filter and trend_direction_filter != 'all':
        option_suffix += f"_td_{trend_direction_filter}"
    if symbols:
        digest = hashlib.sha1(','.join(symbols).encode('utf-8')).hexdigest()
        name = (
            f"snapshot_sr_levels_tf_{tf_part}_tol_{tol_part}_sym_{digest}"
            f"{sort_suffix}{option_suffix}{page_part}{search_suffix}.json"
        )
    else:
        name = f"snapshot_sr_levels_tf_{tf_part}_tol_{tol_part}_all{sort_suffix}{option_suffix}{page_part}{search_suffix}.json"
    return os.path.join(_snapshot_dir, name)


def _determine_cutoff_date(conn, timeframe: str):
    """Try to resolve a rolling cutoff if the MV exists; swallow ORA-942."""
    if TRADING_DAYS_LOOKBACK <= 0:
        return None
    lookup_sql = f"""
        SELECT MIN(trading_date) FROM (
            SELECT DISTINCT trading_date
            FROM {settings.oracle_schema}.{settings.oracle_table_mv}
            WHERE timeframe = :timeframe
            ORDER BY trading_date DESC
            FETCH FIRST {TRADING_DAYS_LOOKBACK} ROWS ONLY
        )
    """
    with conn.cursor() as cur:
        try:
            cur.execute(lookup_sql, {"timeframe": timeframe})
            row = cur.fetchone()
            return row[0] if row and row[0] is not None else None
        except Exception as exc:
            if getattr(exc, "code", None) == 942:
                return None
            raise


def _is_valid(
    payload: Dict[str, Any] | None,
    expected_ltc_iso: Optional[str],
    lookback_days: str | int,
    min_touches: int,
    price_action_filter: str,
    trend_direction_filter: str,
) -> bool:
    if not isinstance(payload, dict):
        return False
    meta = payload.get('meta') or {}
    if meta.get('cutoffMonths') != SR_CUTOFF_MONTHS:
        return False
    cached_ltc = meta.get('ltcDateIso')
    if expected_ltc_iso and cached_ltc and cached_ltc != expected_ltc_iso:
        return False
    if meta.get('lookbackDays') != lookback_days:
        return False
    if int(meta.get('minTouches') or 1) != int(min_touches or 1):
        return False
    if str(meta.get('priceActionFilter') or 'all') != str(price_action_filter or 'all'):
        return False
    if str(meta.get('trendDirectionFilter') or 'all') != str(trend_direction_filter or 'all'):
        return False
    return True


def _compute_payload(
    tolerance: float,
    timeframe: str,
    symbols_filter: Optional[List[str]],
    search_term: str | None,
    page: int,
    page_size: int,
    sort_by: str,
    sort_dir: str,
    lookback_days: str | int,
    min_touches: int,
    price_action_filter: str,
    trend_direction_filter: str,
    trading_window: Optional[Dict[str, Any]] = None,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    offset = (page - 1) * page_size
    base_payload = _compute_base_payload(
        tolerance,
        timeframe,
        trading_window,
        lookback_days=lookback_days,
        min_touches=min_touches,
        force_refresh=force_refresh,
    )
    rows_all = list(base_payload.get('rows', []))
    _sort_rows(rows_all, sort_by, sort_dir)
    candidate_rows = _filter_rows(rows_all, symbols_filter, search_term, price_action_filter)
    trend_counts = _summarize_trends(candidate_rows)
    filtered_rows = _apply_trend_direction_filter(candidate_rows, trend_direction_filter)
    total_rows = len(filtered_rows)
    page_rows = [dict(row) for row in filtered_rows[offset: offset + page_size]]
    for index, row in enumerate(page_rows, start=offset + 1):
        row['sNo'] = index

    total_pages = max(1, (total_rows + page_size - 1) // page_size)
    window_meta = base_payload.get('window_meta') or {}
    meta: Dict[str, Any] = {
        "page": page,
        "page_size": page_size,
        "total_rows": total_rows,
        "total_pages": total_pages,
        "timeframe": timeframe,
        "tolerance": tolerance,
        "cutoffMonths": SR_CUTOFF_MONTHS,
        "sortColumn": sort_by,
        "sortDirection": sort_dir,
        "lookbackDays": lookback_days,
        "minTouches": min_touches,
        "priceActionFilter": price_action_filter,
        "trendDirectionFilter": trend_direction_filter,
        "trendCounts": trend_counts,
        **window_meta,
    }
    payload: Dict[str, Any] = {
        "rows": page_rows,
        "count": len(page_rows),
        "generatedAt": datetime.utcnow().isoformat() + 'Z',
        "tolerance": tolerance,
        "toleranceOptions": SR_TOLERANCE_OPTIONS,
        "timeframe": timeframe,
        "filters": {
            "symbols": symbols_filter or [],
            "tolerance": tolerance,
            "timeframe": timeframe,
            "search": search_term or '',
            "lookbackDays": lookback_days,
            "minTouches": min_touches,
            "priceActionFilter": price_action_filter,
            "trendDirection": trend_direction_filter,
            "trendDirectionFilter": trend_direction_filter,
            "sort": {
                "column": sort_by,
                "direction": sort_dir,
            },
        },
        "meta": meta,
    }
    _logger.info(
        "SR payload built timeframe=%s tolerance=%.3f ltc=%s cutoff=%s trading_days=%s lookback=%s min_touches=%s price_action=%s trend_direction=%s rows=%s",
        timeframe,
        tolerance,
        meta.get('endDate'),
        meta.get('startDate'),
        meta.get('tradingDayCount'),
        lookback_days,
        min_touches,
        price_action_filter,
        trend_direction_filter,
        total_rows,
    )
    return payload


def _build_refreshing_placeholder(
    tolerance: float,
    timeframe: str,
    symbols_filter: Optional[List[str]],
    search_term: Optional[str],
    page: int,
    page_size: int,
    sort_by: str,
    sort_dir: str,
    lookback_days: str | int,
    min_touches: int,
    price_action_filter: str,
    trend_direction_filter: str,
    trading_window: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    window_meta = _format_window_meta(trading_window or {})
    meta: Dict[str, Any] = {
        "page": page,
        "page_size": page_size,
        "total_rows": 0,
        "total_pages": 1,
        "timeframe": timeframe,
        "tolerance": tolerance,
        "cutoffMonths": SR_CUTOFF_MONTHS,
        "sortColumn": sort_by,
        "sortDirection": sort_dir,
        "lookbackDays": lookback_days,
        "minTouches": min_touches,
        "priceActionFilter": price_action_filter,
        "trendDirectionFilter": trend_direction_filter,
        "trendCounts": {
            "up": 0,
            "down": 0,
            "consolidation": 0,
            "total": 0,
        },
        **window_meta,
    }
    return {
        "rows": [],
        "count": 0,
        "generatedAt": datetime.utcnow().isoformat() + 'Z',
        "tolerance": tolerance,
        "toleranceOptions": SR_TOLERANCE_OPTIONS,
        "timeframe": timeframe,
        "filters": {
            "symbols": symbols_filter or [],
            "tolerance": tolerance,
            "timeframe": timeframe,
            "search": search_term or '',
            "lookbackDays": lookback_days,
            "minTouches": min_touches,
            "priceActionFilter": price_action_filter,
            "trendDirection": trend_direction_filter,
            "trendDirectionFilter": trend_direction_filter,
            "sort": {
                "column": sort_by,
                "direction": sort_dir,
            },
        },
        "meta": meta,
    }


def _compute_and_persist(
    cache_key: str,
    tolerance: float,
    timeframe: str,
    symbols_filter: Optional[List[str]],
    search_term: str | None,
    page: int,
    page_size: int,
    sort_by: str,
    sort_dir: str,
    lookback_days: str | int,
    min_touches: int,
    price_action_filter: str,
    trend_direction_filter: str,
    trading_window: Optional[Dict[str, Any]],
    force_refresh: bool = False,
) -> Dict[str, Any]:
    payload = _compute_payload(
        tolerance,
        timeframe,
        symbols_filter,
        search_term,
        page,
        page_size,
        sort_by,
        sort_dir,
        lookback_days,
        min_touches,
        price_action_filter,
        trend_direction_filter,
        trading_window,
        force_refresh=force_refresh,
    )
    payload = nse_mcap_svc.enrich_payload_marketcap_index(payload, row_keys=("rows",))
    _cache.set(cache_key, payload)
    save_json_snapshot(
        _snapshot_path(
            tolerance,
            timeframe,
            symbols_filter,
            search_term,
            page,
            page_size,
            sort_by,
            sort_dir,
            lookback_days,
            min_touches,
            price_action_filter,
            trend_direction_filter,
        ),
        payload,
    )
    return payload


def _schedule_refresh(
    cache_key: str,
    tolerance: float,
    timeframe: str,
    symbols_filter: Optional[List[str]],
    search_term: str | None,
    page: int,
    page_size: int,
    sort_by: str,
    sort_dir: str,
    lookback_days: str | int,
    min_touches: int,
    price_action_filter: str,
    trend_direction_filter: str,
    trading_window: Optional[Dict[str, Any]],
    force_refresh: bool = False,
) -> None:
    def _runner() -> Dict[str, Any]:
        return _compute_and_persist(
            cache_key,
            tolerance,
            timeframe,
            symbols_filter,
            search_term,
            page,
            page_size,
            sort_by,
            sort_dir,
            lookback_days,
            min_touches,
            price_action_filter,
            trend_direction_filter,
            trading_window,
            force_refresh=force_refresh,
        )

    background_refresh(_cache, cache_key, _runner)


def _with_marketcap(payload: Dict[str, Any]) -> Dict[str, Any]:
    return nse_mcap_svc.enrich_payload_marketcap_index(payload, row_keys=("rows",))


@bp.get('/api/sr-levels')
def api_sr_levels():
    tol_param = request.args.get('tolerance')
    try:
        tolerance = float(tol_param) if tol_param is not None else 0.05
    except ValueError:
        return jsonify({'ok': False, 'error': 'Invalid tolerance parameter'}), 400
    tolerance = max(0.005, min(tolerance, 0.25))

    timeframe_param = (request.args.get('timeframe') or 'daily').strip().lower()
    if timeframe_param not in SR_TIMEFRAME_OPTIONS:
        return jsonify({'ok': False, 'error': 'Invalid timeframe parameter'}), 400

    page = request.args.get('page', type=int) or 1
    page_size = request.args.get('page_size', type=int) or settings.default_page_size
    page = max(page, 1)
    page_size = max(1, min(page_size, settings.max_page_size))

    search_param = request.args.get('search')
    search_term = search_param.strip().upper() if isinstance(search_param, str) and search_param.strip() else None

    symbols_param = request.args.get('symbols') or request.args.get('symbol')
    symbols_filter = None
    if symbols_param:
        symbols_set = {normalize_symbol(s) for s in symbols_param.split(',') if s.strip()}
        symbols_filter = sorted(sym for sym in symbols_set if sym)
        if not symbols_filter:
            symbols_filter = None

    sort_param = request.args.get('sort') or request.args.get('sort_by') or request.args.get('sortBy')
    sort_dir_param = request.args.get('direction') or request.args.get('sort_dir') or request.args.get('sortDir')
    sort_by, sort_dir = _resolve_sort_params(sort_param, sort_dir_param)
    lookback_days = _parse_lookback_days(request.args.get('lookback_days') or request.args.get('lookbackDays'))
    min_touches = _parse_min_touches(request.args.get('min_touches') or request.args.get('minTouches'))
    price_action_filter = _normalize_price_action_filter(
        request.args.get('price_action') or request.args.get('priceAction')
    )
    trend_direction_filter = _normalize_trend_direction_filter(
        request.args.get('trend_direction')
        or request.args.get('trendDirection')
        or request.args.get('trend')
        or request.args.get('trendFilter')
    )

    force_refresh = request.args.get('refresh') in ('1', 'true', 'yes')

    trading_window, latest_ltc_iso = _get_cached_trading_window(lookback_days, force_refresh=force_refresh)

    cache_key = _key_for(
        tolerance,
        timeframe_param,
        symbols_filter,
        search_term,
        page,
        page_size,
        sort_by,
        sort_dir,
        lookback_days,
        min_touches,
        price_action_filter,
        trend_direction_filter,
    )
    cached = _cache.get(cache_key)
    if cached is not None and not _is_valid(cached, latest_ltc_iso, lookback_days, min_touches, price_action_filter, trend_direction_filter):
        cached = None

    snap_path = _snapshot_path(
        tolerance,
        timeframe_param,
        symbols_filter,
        search_term,
        page,
        page_size,
        sort_by,
        sort_dir,
        lookback_days,
        min_touches,
        price_action_filter,
        trend_direction_filter,
    )
    snapshot = load_json_snapshot(snap_path)
    snapshot_stale = False
    if snapshot and not _is_valid(snapshot, latest_ltc_iso, lookback_days, min_touches, price_action_filter, trend_direction_filter):
        snapshot_stale = True

    if force_refresh:
        if cached is not None:
            _schedule_refresh(
                cache_key,
                tolerance,
                timeframe_param,
                symbols_filter,
                search_term,
                page,
                page_size,
                sort_by,
                sort_dir,
                lookback_days,
                min_touches,
                price_action_filter,
                trend_direction_filter,
                trading_window,
                force_refresh=True,
            )
            return jsonify({**_with_marketcap(cached), 'cached': True, 'refreshing': True})
        if snapshot is not None:
            _schedule_refresh(
                cache_key,
                tolerance,
                timeframe_param,
                symbols_filter,
                search_term,
                page,
                page_size,
                sort_by,
                sort_dir,
                lookback_days,
                min_touches,
                price_action_filter,
                trend_direction_filter,
                trading_window,
                force_refresh=True,
            )
            return jsonify({**_with_marketcap(snapshot), 'cached': True, 'refreshing': True, 'stale': snapshot_stale})
        # Keep refresh requests non-blocking even when this page key is cold.
        # Heavy SR recomputation runs in background and UI can poll while refreshing.
        _schedule_refresh(
            cache_key,
            tolerance,
            timeframe_param,
            symbols_filter,
            search_term,
            page,
            page_size,
            sort_by,
            sort_dir,
            lookback_days,
            min_touches,
            price_action_filter,
            trend_direction_filter,
            trading_window,
            force_refresh=True,
        )
        base_fast_key = _base_cache_key(tolerance, timeframe_param, latest_ltc_iso, lookback_days, min_touches)
        base_cached = _cache.get(base_fast_key)
        if base_cached is not None and _is_base_valid(base_cached, latest_ltc_iso, lookback_days, min_touches):
            try:
                fast_payload = _compute_and_persist(
                    cache_key,
                    tolerance,
                    timeframe_param,
                    symbols_filter,
                    search_term,
                    page,
                    page_size,
                    sort_by,
                    sort_dir,
                    lookback_days,
                    min_touches,
                    price_action_filter,
                    trend_direction_filter,
                    trading_window,
                    force_refresh=False,
                )
                return jsonify({**fast_payload, 'cached': True, 'refreshing': True, 'stale': True})
            except Exception:  # pragma: no cover
                _logger.exception("Failed to build fast SR payload from cached base during refresh fallback")
        placeholder = _build_refreshing_placeholder(
            tolerance,
            timeframe_param,
            symbols_filter,
            search_term,
            page,
            page_size,
            sort_by,
            sort_dir,
            lookback_days,
            min_touches,
            price_action_filter,
            trend_direction_filter,
            trading_window,
        )
        return jsonify({**placeholder, 'cached': True, 'refreshing': True, 'stale': True})

    if cached is not None:
        return jsonify({**_with_marketcap(cached), 'cached': True})

    if snapshot is not None:
        if snapshot_stale:
            _schedule_refresh(
                cache_key,
                tolerance,
                timeframe_param,
                symbols_filter,
                search_term,
                page,
            page_size,
            sort_by,
            sort_dir,
            lookback_days,
            min_touches,
            price_action_filter,
            trend_direction_filter,
            trading_window,
            force_refresh=True,
        )
        return jsonify({**_with_marketcap(snapshot), 'cached': True, 'stale': True, 'refreshing': True})
        return jsonify({**_with_marketcap(snapshot), 'cached': True})

    try:
        payload = _compute_and_persist(
            cache_key,
            tolerance,
            timeframe_param,
            symbols_filter,
            search_term,
            page,
            page_size,
            sort_by,
            sort_dir,
            lookback_days,
            min_touches,
            price_action_filter,
            trend_direction_filter,
            trading_window,
        )
        return jsonify(payload)
    except Exception as exc:  # pragma: no cover
        _logger.exception("SR levels computation failed")
        if snapshot:
            fallback = {**snapshot, 'cached': True, 'stale': True, 'error': str(exc)}
            return jsonify(fallback)
        return jsonify({'ok': False, 'error': 'Unable to compute Support & Resistance levels'}), 500
