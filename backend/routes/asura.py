from __future__ import annotations

import hashlib
import logging
import os
import re
import sys
import uuid
import threading
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, Optional, List, Tuple, Iterable

from flask import Blueprint, jsonify, request

from cache import TTLCache, background_refresh, load_json_snapshot, save_json_snapshot

try:
    from ..db_pool import pool
except ImportError:  # pragma: no cover
    from db_pool import pool  # type: ignore
try:
    from ..services.asura_trade_service import sync_asura_bullish_strategy
except ImportError:  # pragma: no cover
    from services.asura_trade_service import sync_asura_bullish_strategy  # type: ignore
try:
    from ..db import fetch_latest_trade_date_from_oracle, fetch_ohlc_series_from_oracle
except ImportError:  # pragma: no cover
    from db import fetch_latest_trade_date_from_oracle, fetch_ohlc_series_from_oracle  # type: ignore
try:
    from ..services.strategy_agent_service import get_strategy_params
except ImportError:  # pragma: no cover
    from services.strategy_agent_service import get_strategy_params  # type: ignore
try:
    from ..services.strategy_agent_runtime_service import start_strategy_agent_execution
except ImportError:  # pragma: no cover
    from services.strategy_agent_runtime_service import start_strategy_agent_execution  # type: ignore
try:
    from ..services.ui_notification_service import publish_notification
except ImportError:  # pragma: no cover
    from services.ui_notification_service import publish_notification  # type: ignore
try:
    from ..services.ath_service import get_all_time_high_for_symbols, log_stale_snapshot_warning
except ImportError:  # pragma: no cover
    from services.ath_service import get_all_time_high_for_symbols, log_stale_snapshot_warning  # type: ignore
try:
    from ..services import nse_mcap_service as nse_mcap_svc
except ImportError:  # pragma: no cover
    from services import nse_mcap_service as nse_mcap_svc  # type: ignore
try:
    from ..services.technical_score_engine import enrich_row_with_master_score_fields
except ImportError:  # pragma: no cover
    try:
        from services.technical_score_engine import enrich_row_with_master_score_fields  # type: ignore
    except Exception:  # pragma: no cover
        enrich_row_with_master_score_fields = None  # type: ignore
bp = Blueprint('asura', __name__)
_logger = logging.getLogger(__name__)

ASURA_DEFAULT_MIN_SIGNAL = float(os.getenv('ASURA_DEFAULT_MIN_SIGNAL', '60'))
ASURA_DEFAULT_MIN_ADX = float(os.getenv('ASURA_DEFAULT_MIN_ADX', '20'))
ASURA_DEFAULT_PAGE_SIZE = int(os.getenv('ASURA_DEFAULT_PAGE_SIZE', '50'))
ASURA_MAX_PAGE_SIZE = int(os.getenv('ASURA_MAX_PAGE_SIZE', '200'))
ASURA_MIXED_ADX_MIN = float(os.getenv('ASURA_MIXED_ADX_MIN', '30'))
ASURA_STOP_PCT = float(os.getenv('ASURA_STOP_PCT', '0.05'))
ASURA_TARGET1_PCT = float(os.getenv('ASURA_TARGET1_PCT', '0.10'))
ASURA_TARGET2_PCT = float(os.getenv('ASURA_TARGET2_PCT', '0.15'))
ASURA_LOCAL_LOOKBACK_MONTHS = int(os.getenv('ASURA_LOCAL_LOOKBACK_MONTHS', '24'))
ASURA_LOCAL_CACHE_TTL = int(os.getenv('ASURA_LOCAL_CACHE_TTL', '600'))
ASURA_LOCAL_LEVEL_WINDOW = int(os.getenv('ASURA_LOCAL_LEVEL_WINDOW', '60'))
ASURA_LOCAL_LEVEL_TOL = float(os.getenv('ASURA_LOCAL_LEVEL_TOL', '0.015'))
ASURA_INSERT_EMA_FROM_OHLC = os.getenv('ASURA_INSERT_EMA_FROM_OHLC', '1').strip().lower() not in ('0', 'false', 'no')
ASURA_CACHE_TTL = int(os.getenv('ASURA_CACHE_TTL', '30'))
ASURA_BACKTESTING_DATE = os.getenv('ASURA_BACKTESTING_DATE', '2025-12-12')
ASURA_AUTO_SYNC = os.getenv('ASURA_AUTO_SYNC', '1').strip().lower() not in ('0', 'false', 'no')
ASURA_AUTO_INSERT_ENABLED = os.getenv('ASURA_AUTO_INSERT_ENABLED', '1').strip().lower() not in ('0', 'false', 'no')
ASURA_AUTO_INSERT_TIME = os.getenv('ASURA_AUTO_INSERT_TIME', '18:00').strip() or '18:00'
ASURA_AUTO_INSERT_PAGE_SIZE = int(os.getenv('ASURA_AUTO_INSERT_PAGE_SIZE', '100000'))
ASURA_MASTER_SCORE_ENABLED = os.getenv('ASURA_MASTER_SCORE_ENABLED', '1').strip().lower() not in ('0', 'false', 'no')
ASURA_BULLISH_TREND_TABLE = (
    os.getenv("ASURA_BULLISH_TREND_TABLE") or "ASURA_BULLISH_TREND_STRATEGY_TESTING"
).strip()
_ASURA_SCHEMA = (os.getenv("ASURA_SCHEMA") or os.getenv("ORACLE_SCHEMA") or "").strip()
if _ASURA_SCHEMA and "." not in ASURA_BULLISH_TREND_TABLE:
    ASURA_BULLISH_TREND_TABLE = f"{_ASURA_SCHEMA}.{ASURA_BULLISH_TREND_TABLE}"
ASURA_BTS_SEQ = (os.getenv("ASURA_BTS_SEQ") or "ASURA_BTS_SEQ").strip()

_cache = TTLCache(ttl_seconds=ASURA_CACHE_TTL, max_items=512)
_snapshot_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_ASYNC_COLD_WAIT_MS = max(0, int(os.getenv("ASURA_ASYNC_COLD_WAIT_MS") or "1500"))
_ASYNC_COLD_POLL_MS = max(25, int(os.getenv("ASURA_ASYNC_COLD_POLL_MS") or "50"))
_SOURCE_RECHECK_TTL_MS = max(5000, int(os.getenv("ASURA_SOURCE_RECHECK_TTL_MS") or "60000"))
_MARKETCAP_SORT_FIELDS = {"index", "mcap", "mcap_rank"}
_asura_source_probe: Optional[Tuple[float, bool]] = None


def _apply_master_score_fields(item: Dict[str, Any]) -> Dict[str, Any]:
    if not ASURA_MASTER_SCORE_ENABLED or enrich_row_with_master_score_fields is None:
        return item
    try:
        return enrich_row_with_master_score_fields(item, replace_existing=False)
    except Exception:
        _logger.exception('asura_master_score_enrich_failed symbol=%s', item.get('symbol'))
        return item


def _with_marketcap(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return nse_mcap_svc.enrich_payload_marketcap_index(payload, row_keys=('items', 'rows'))
    except Exception:
        _logger.exception('asura_marketcap_enrich_failed')
        return payload


_ASURA_DIAGNOSTIC_FIELDS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ('SignalScore', ('signalScore', 'signal_score', 'SIGNAL_SCORE', 'SIGNALSCORE')),
    ('1D', ('move1dPct', 'move_1d_pct', 'MOVE_1D_PCT')),
    ('1WEEK', ('move1wPct', 'move_1w_pct', 'MOVE_1W_PCT')),
    ('1MONTH', ('move1mPct', 'move_1m_pct', 'MOVE_1M_PCT')),
    ('VolumeRatio20', ('volumeRatio20', 'volumeRatio', 'volume_ratio20', 'volume_ratio', 'VOLUME_RATIO20')),
    ('52 Week Low', ('low52w', 'low_52w', 'LOW_52W', 'fiftyTwoWeekLow')),
    ('52 Week High', ('high52w', 'high_52w', 'HIGH_52W', 'fiftyTwoWeekHigh')),
    ('MACD > 0', ('macdHist', 'macd_hist', 'MACD_HIST')),
    ('ATR', ('atr', 'atr14', 'ATR', 'ATR14')),
    ('ADX14', ('adx14', 'adx', 'ADX14', 'ADX')),
    ('Support', ('support', 'support_price', 'SUPPORT', 'SUPPORT_PRICE')),
    ('Resistance', ('resistance', 'resistance_price', 'RESISTANCE', 'RESISTANCE_PRICE')),
    ('TrendDirection', ('trendDirection', 'trend_direction', 'TREND_DIRECTION', 'TRENDDIRECTION')),
    ('EMA_Stack', ('emaStack', 'ema_stack', 'EMA_STACK', 'EMASTACK')),
    ('SetupType', ('setupType', 'setup_type', 'SETUP_TYPE', 'SETUPTYPE')),
    ('EntryPrice', ('entryPrice', 'entry_price', 'ENTRY_PRICE', 'ENTRYPRICE')),
    ('StopLoss', ('stopLoss', 'stop_loss', 'STOP_LOSS', 'STOPLOSS')),
)


def _diagnostic_first_value(row: Dict[str, Any], keys: Tuple[str, ...]) -> Any:
    for key in keys:
        if key in row:
            value = row.get(key)
            if value is not None and (not isinstance(value, str) or value.strip()):
                return value
    return None


def _diagnostic_is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == '')


def _diagnostic_latest_trade_date(items: List[Dict[str, Any]]) -> Optional[str]:
    dates = [
        _to_iso_date(_diagnostic_first_value(item, ('tradeDate', 'trade_date', 'TRADING_DATE', 'buyingDate', 'BUYING_DATE')))
        for item in items
    ]
    dates = [value for value in dates if value]
    return max(dates) if dates else None


def _log_asura_payload_diagnostics(payload: Dict[str, Any], *, cached: bool, refreshing: bool) -> None:
    raw_items = payload.get('items') if isinstance(payload, dict) else None
    if not isinstance(raw_items, list):
        raw_items = payload.get('rows') if isinstance(payload, dict) else None
    items = [item for item in (raw_items or []) if isinstance(item, dict)]
    blank_counts: Dict[str, int] = {}
    rows_with_blank_major_fields = 0

    for item in items:
        missing_names: List[str] = []
        for label, keys in _ASURA_DIAGNOSTIC_FIELDS:
            if _diagnostic_is_blank(_diagnostic_first_value(item, keys)):
                blank_counts[label] = blank_counts.get(label, 0) + 1
                missing_names.append(label)
        if missing_names:
            rows_with_blank_major_fields += 1

    samples = []
    for item in items[:3]:
        sample_missing = [
            label
            for label, keys in _ASURA_DIAGNOSTIC_FIELDS
            if _diagnostic_is_blank(_diagnostic_first_value(item, keys))
        ]
        samples.append({
            'symbol': _diagnostic_first_value(item, ('symbol', 'SYMBOL', 'stock', 'STOCK')),
            'tradeDate': _to_iso_date(_diagnostic_first_value(item, ('tradeDate', 'trade_date', 'TRADING_DATE', 'buyingDate', 'BUYING_DATE'))),
            'blankFields': sample_missing[:8],
        })

    _logger.info(
        'asura_api_diag endpoint=/api/asura rows=%s latest_trade_date=%s blank_major_rows=%s blank_counts=%s sample=%s cached=%s refreshing=%s',
        len(items),
        _diagnostic_latest_trade_date(items),
        rows_with_blank_major_fields,
        blank_counts,
        samples,
        int(cached),
        int(refreshing),
    )


_SORT_COLUMN_MAP: dict[str, str] = {
    'symbol': 's.SYMBOL',
    'stock_name': 's.STOCK_NAME',
    'trade_date': 's.TRADE_DATE',
    'buying_date': 's.TRADE_DATE',
    'price': 's.CLOSE_PRICE',
    'volume': 's.VOLUME',
    'move_1d_pct': 's.MOVE_1D_PCT',
    'move_1w_pct': 's.MOVE_1W_PCT',
    'move_1m_pct': 's.MOVE_1M_PCT',
    'avg_volume20': 's.AVG_VOLUME20',
    'volume_ratio': 's.VOLUME_RATIO20',
    'volume_ratio20': 's.VOLUME_RATIO20',
    'high_52w': 's.HIGH_52W',
    'low_52w': 's.LOW_52W',
    'ath': 's.ATH',
    'high_1y': 's.HIGH_1Y',
    'high_2y': 's.HIGH_2Y',
    'ema20': 's.EMA20',
    'ema50': 's.EMA50',
    'ema100': 's.EMA100',
    'ema200': 's.EMA200',
    'ema50_slopepct_10d': 's.EMA50_SLOPEPCT_10D',
    'rsi': 's.RSI14',
    'rsi14': 's.RSI14',
    'macd_line': 's.MACD_LINE',
    'macd_signal': 's.MACD_SIGNAL',
    'macd_hist': 's.MACD_HIST',
    'atr14': 's.ATR14',
    'atr_pct': 's.ATR_PCT',
    'adx': 's.ADX14',
    'adx14': 's.ADX14',
    'di_plus14': 's.DI_PLUS14',
    'di_minus14': 's.DI_MINUS14',
    'trend_direction': 's.TREND_DIRECTION',
    'ema_stack': 's.EMA_STACK',
    'support_price': 's.SUPPORT_PRICE',
    'resistance_price': 's.RESISTANCE_PRICE',
    'dist_to_support_pct': 's.DIST_TO_SUPPORT_PCT',
    'dist_to_resistance_pct': 's.DIST_TO_RESISTANCE_PCT',
    'support_strength': 's.SUPPORT_STRENGTH',
    'resistance_strength': 's.RESISTANCE_STRENGTH',
    'level_score': 's.LEVEL_SCORE',
    'level_proximity_score': 's.LEVEL_PROXIMITY_SCORE',
    'level_touch_score': 's.LEVEL_TOUCH_SCORE',
    'level_recency_score': 's.LEVEL_RECENCY_SCORE',
    'level_confluence_score': 's.LEVEL_CONFLUENCE_SCORE',
    'breakout_flag': 's.BREAKOUT_FLAG',
    'retest_ready': 's.RETEST_READY',
    'setup_type': 's.SETUP_TYPE',
    'entry_price': 's.ENTRY_PRICE',
    'stop_loss': 's.STOP_LOSS',
    'target1': 's.TARGET1',
    'target2': 's.TARGET2',
    'status': 's.SYMBOL',
    'exit_price': 's.CLOSE_PRICE',
    'exit_reason': 's.SYMBOL',
    'rr_1': 's.RR_1',
    'rr_2': 's.RR_2',
    'signal_score': 's.SIGNAL_SCORE',
    'index': 's.SYMBOL',
    'mcap': 's.SYMBOL',
    'mcap_rank': 's.SYMBOL',
}

_ASURA_SOURCE: Optional[str] = None
_ASURA_SOURCE_INFO: Optional[Tuple[str, set[str]]] = None
_FALLBACK_READY = False

try:
    _repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    if _repo_root not in sys.path:
        sys.path.insert(0, _repo_root)
    from backend.jobs.asura_refresh import OhlcvBar as _OhlcvBar  # type: ignore
    from backend.jobs.asura_refresh import _compute_latest_scan_row as _compute_latest_scan_row  # type: ignore

    _FALLBACK_READY = True
except Exception:  # pragma: no cover
    _FALLBACK_READY = False

_fallback_snapshot_cache = TTLCache(ttl_seconds=int(os.getenv('ASURA_FALLBACK_SNAPSHOT_TTL', '600')), max_items=4)
_local_snapshot_cache = TTLCache(ttl_seconds=ASURA_LOCAL_CACHE_TTL, max_items=4)
_asura_ath_cache = TTLCache(
    ttl_seconds=int(os.getenv('ASURA_ATH_CACHE_TTL', '900')),
    max_items=int(os.getenv('ASURA_ATH_CACHE_MAX', '256')),
)
_fallback_lookback_days = int(os.getenv('ASURA_FALLBACK_LOOKBACK_DAYS', '800'))
_fallback_source_view = os.getenv('ASURA_FALLBACK_OHLCV_VIEW', 'V_NSE500_EMA_DAILY')

def invalidate_asura_cache() -> None:
    _cache.clear()
    _fallback_snapshot_cache.clear()
    _local_snapshot_cache.clear()
    _asura_ath_cache.clear()


def _snapshot_path(timeframe: str) -> str:
    os.makedirs(_snapshot_dir, exist_ok=True)
    tf_suffix = (timeframe or 'daily').strip().lower() or 'daily'
    return os.path.join(_snapshot_dir, f"snapshot_asura_tf_{tf_suffix}.json")


def _snapshot_has_ath_source(payload: Dict[str, Any] | None) -> bool:
    if not payload or not isinstance(payload, dict):
        return False
    return str(payload.get('athSource') or '').strip().upper() == 'NSE_NIFTY500_DAILY_RAW_DATA_DEV'


def _snapshot_has_current_trade_date(payload: Dict[str, Any] | None) -> bool:
    if not payload or not isinstance(payload, dict):
        return False
    payload_as_of = str(payload.get('as_of_date') or '').strip()[:10]
    if not payload_as_of:
        return False
    try:
        latest_trade_date = fetch_latest_trade_date_from_oracle()
    except Exception:
        _logger.exception('Asura snapshot latest trade-date check failed')
        return True
    return (not latest_trade_date) or payload_as_of >= latest_trade_date.isoformat()


def _fetch_latest_ltc_date_key() -> Optional[str]:
    try:
        return _to_iso_date(fetch_latest_trade_date_from_oracle())
    except Exception:
        _logger.exception('Asura latest LTC_DATE lookup failed')
        return None


def _snapshot_stale_reasons(payload: Dict[str, Any] | None) -> list[str]:
    reasons: list[str] = []
    if not _snapshot_has_ath_source(payload):
        reasons.append('ath_source')
    if not _snapshot_has_current_trade_date(payload):
        reasons.append('trade_date')
    return reasons


def _load_local_snapshot_payload(timeframe: str) -> Tuple[Optional[Dict[str, Any]], list[str]]:
    cache_key = f'local:asura_snapshot:{timeframe}'
    cached = _local_snapshot_cache.get(cache_key)
    if isinstance(cached, dict):
        stale_reasons = _snapshot_stale_reasons(cached)
        return ({**cached, 'cached': True}, stale_reasons)

    snapshot = load_json_snapshot(_snapshot_path(timeframe))
    if isinstance(snapshot, dict):
        _local_snapshot_cache.set(cache_key, snapshot)
        stale_reasons = _snapshot_stale_reasons(snapshot)
        return ({**snapshot, 'cached': True}, stale_reasons)

    return None, ['cold_start']


def _build_and_save_local_snapshot(timeframe: str) -> Dict[str, Any]:
    payload = _compute_local_snapshot(
        timeframe=timeframe,
        trade_start_date=None,
        trade_cutoff_date=None,
        apply_authoritative_ath=False,
    )
    save_json_snapshot(_snapshot_path(timeframe), payload)
    return payload


def _wait_for_local_snapshot(timeframe: str, wait_ms: int) -> Optional[Dict[str, Any]]:
    if wait_ms <= 0:
        return None
    cache_key = f'local:asura_snapshot:{timeframe}'
    deadline = time.perf_counter() + (wait_ms / 1000.0)
    while time.perf_counter() < deadline:
        warmed = _local_snapshot_cache.get(cache_key)
        if isinstance(warmed, dict):
            return {**warmed, 'cached': True}
        time.sleep(_ASYNC_COLD_POLL_MS / 1000.0)
    return None


def _schedule_local_snapshot_refresh(timeframe: str) -> None:
    cache_key = f'local:asura_snapshot:{timeframe}'
    background_refresh(_local_snapshot_cache, cache_key, lambda: _build_and_save_local_snapshot(timeframe))


def _local_warming_payload(*, timeframe: str, page: int, page_size: int, stale_reasons: list[str]) -> Dict[str, Any]:
    return {
        'items': [],
        'total': 0,
        'page': page,
        'page_size': page_size,
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'cached': True,
        'refreshing': True,
        'fallback': True,
        'local': True,
        'as_of_date': None,
        'athSource': 'NSE_NIFTY500_DAILY_RAW_DATA_DEV',
        'meta': {
            'db_time_ms': 0,
            'page': page,
            'page_size': page_size,
            'snapshot_used': False,
            'source': 'warming',
            'stale_reasons': stale_reasons,
            'timeframe': timeframe,
            'total': 0,
        },
    }


def _has_precomputed_source() -> bool:
    global _asura_source_probe
    if _ASURA_SOURCE_INFO:
        return True

    now_ms = time.monotonic() * 1000.0
    if _asura_source_probe and (now_ms - _asura_source_probe[0]) <= _SOURCE_RECHECK_TTL_MS:
        return _asura_source_probe[1]

    try:
        with pool.acquire() as conn:
            _resolve_source(conn)
        available = True
    except RuntimeError as exc:
        if 'Asura source not found' not in str(exc):
            raise
        available = False

    _asura_source_probe = (now_ms, available)
    return available


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except Exception:
        return None


def _to_iso_date(value: Any) -> Optional[str]:
    if isinstance(value, date):
        return value.strftime('%Y-%m-%d')
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d')
    return None


def _apply_authoritative_ath(items: List[Dict[str, Any]], *, endpoint: str) -> Dict[str, Any]:
    started_at = time.perf_counter()
    if not items:
        return {'symbols': 0, 'cache_hit': False, 'elapsed_ms': 0}

    symbols = sorted({
        _normalize_symbol_code(item.get('symbol') or item.get('stockName') or item.get('stock'))
        for item in items
        if isinstance(item, dict)
    } - {''})
    if not symbols:
        return {'symbols': 0, 'cache_hit': False, 'elapsed_ms': int((time.perf_counter() - started_at) * 1000)}

    cache_key = '|'.join(symbols)
    ath_records = _asura_ath_cache.get(cache_key)
    cache_hit = isinstance(ath_records, dict)

    if not cache_hit:
        try:
            ath_records = get_all_time_high_for_symbols(
                symbols,
                include_date=True,
                endpoint=endpoint,
            )
            if isinstance(ath_records, dict):
                _asura_ath_cache.set(cache_key, ath_records)
        except Exception as exc:
            _logger.exception('[ATH] Failed to fetch authoritative ATH map endpoint=%s error=%s', endpoint, exc)
            return {
                'symbols': len(symbols),
                'cache_hit': False,
                'elapsed_ms': int((time.perf_counter() - started_at) * 1000),
                'error': str(exc),
            }

    stale_detected = False
    for item in items:
        if not isinstance(item, dict):
            continue
        symbol = _normalize_symbol_code(item.get('symbol') or item.get('stockName') or item.get('stock'))
        if not symbol:
            continue
        record = ath_records.get(symbol) or {}
        authoritative_ath = _to_float(record.get('ath'))
        authoritative_ath_date = record.get('ath_date')
        existing_ath = _to_float(item.get('ath'))
        if authoritative_ath is not None:
            item['ath'] = authoritative_ath
            item['ath_date'] = authoritative_ath_date
            item['athDate'] = authoritative_ath_date
            if existing_ath is not None and abs(existing_ath - authoritative_ath) > 0.0001:
                stale_detected = True
        else:
            item['ath'] = None
            item['ath_date'] = None
            item['athDate'] = None

    if stale_detected:
        log_stale_snapshot_warning(endpoint=endpoint, source='asura_payload')
    return {
        'symbols': len(symbols),
        'cache_hit': cache_hit,
        'elapsed_ms': int((time.perf_counter() - started_at) * 1000),
    }


def _calc_stop_loss_pct(entry: Any, stop: Any) -> Optional[float]:
    try:
        entry_val = float(entry)
        stop_val = float(stop)
    except Exception:
        return None
    if entry_val == 0:
        return None
    return (entry_val - stop_val) / entry_val * 100.0


def _calc_target_pct(entry: Any, target: Any) -> Optional[float]:
    try:
        entry_val = float(entry)
        target_val = float(target)
    except Exception:
        return None
    if entry_val == 0:
        return None
    return (target_val - entry_val) / entry_val * 100.0


def _ema_flag(price: Optional[float], ema_val: Optional[float], label: str) -> Optional[str]:
    if price is None or ema_val is None:
        return None
    try:
        return label if float(price) >= float(ema_val) else None
    except Exception:
        return None


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    return None


def _normalize_candles(entries: Iterable[Any]) -> List[Dict[str, Any]]:
    candles: List[Dict[str, Any]] = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        dt = _coerce_datetime(entry.get('date') or entry.get('trading_date') or entry.get('trade_date'))
        if not dt:
            continue
        close_val = _to_float(entry.get('close'))
        if close_val is None:
            continue
        open_val = _to_float(entry.get('open')) if entry.get('open') is not None else close_val
        high_val = _to_float(entry.get('high')) if entry.get('high') is not None else close_val
        low_val = _to_float(entry.get('low')) if entry.get('low') is not None else close_val
        volume_val = _to_float(entry.get('volume'))
        candles.append({
            'date': dt,
            'open': open_val if open_val is not None else close_val,
            'high': high_val if high_val is not None else close_val,
            'low': low_val if low_val is not None else close_val,
            'close': close_val,
            'volume': volume_val,
        })
    candles.sort(key=lambda c: c['date'])
    return candles


def _aggregate_candles(candles: List[Dict[str, Any]], timeframe: str) -> List[Dict[str, Any]]:
    tf = (timeframe or 'daily').strip().lower()
    if tf == 'daily':
        return candles
    buckets: Dict[date, Dict[str, Any]] = {}
    for candle in candles:
        dt = candle.get('date')
        if not isinstance(dt, datetime):
            continue
        if tf == 'weekly':
            bucket = dt.date() - timedelta(days=dt.weekday())
        elif tf == 'monthly':
            bucket = date(dt.year, dt.month, 1)
        elif tf == 'yearly':
            bucket = date(dt.year, 1, 1)
        else:
            return candles
        agg = buckets.get(bucket)
        if agg is None:
            buckets[bucket] = {
                'date': dt,
                'open': candle.get('open'),
                'high': candle.get('high'),
                'low': candle.get('low'),
                'close': candle.get('close'),
                'volume': candle.get('volume') if candle.get('volume') is not None else 0.0,
            }
            continue
        if candle.get('high') is not None:
            agg['high'] = candle['high'] if agg.get('high') is None else max(agg['high'], candle['high'])
        if candle.get('low') is not None:
            agg['low'] = candle['low'] if agg.get('low') is None else min(agg['low'], candle['low'])
        if candle.get('close') is not None:
            agg['close'] = candle['close']
        if candle.get('open') is not None and agg.get('open') is None:
            agg['open'] = candle['open']
        if candle.get('volume') is not None:
            agg['volume'] = (agg.get('volume') or 0.0) + float(candle['volume'])
        agg['date'] = dt

    aggregated = sorted(buckets.values(), key=lambda c: c.get('date') or datetime.min)
    return aggregated


def _ema_series(values: List[float], period: int) -> List[Optional[float]]:
    if not values:
        return []
    k = 2 / (period + 1)
    out: List[Optional[float]] = []
    prev: Optional[float] = None
    for value in values:
        if value is None:
            out.append(prev)
            continue
        if prev is None:
            prev = float(value)
        else:
            prev = (float(value) - prev) * k + prev
        out.append(prev)
    return out


def _next_ema(prev: Optional[float], price: float, period: int) -> float:
    k = 2 / (period + 1)
    return price if prev is None else (price - prev) * k + prev


def _compute_rsi_last(closes: List[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, period + 1):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    rsi = 100.0 if avg_loss == 0 else 100 - (100 / (1 + (avg_gain / avg_loss)))
    for idx in range(period + 1, len(closes)):
        delta = closes[idx] - closes[idx - 1]
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
        rsi = 100.0 if avg_loss == 0 else 100 - (100 / (1 + (avg_gain / avg_loss)))
    return rsi


def _compute_macd_last(closes: List[float]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if len(closes) < 26:
        return None, None, None
    ema_fast = _ema_series(closes, 12)
    ema_slow = _ema_series(closes, 26)
    macd_line: List[float] = []
    for fast, slow in zip(ema_fast, ema_slow):
        if fast is None or slow is None:
            macd_line.append(0.0)
        else:
            macd_line.append(float(fast) - float(slow))
    signal_line = _ema_series(macd_line, 9)
    if not macd_line or not signal_line:
        return None, None, None
    macd_val = macd_line[-1]
    signal_val = signal_line[-1]
    hist_val = macd_val - (signal_val or 0.0) if macd_val is not None else None
    return macd_val, signal_val, hist_val


def _true_ranges(candles: List[Dict[str, Any]]) -> List[float]:
    ranges: List[float] = []
    prev_close: Optional[float] = None
    for candle in candles:
        high = candle.get('high')
        low = candle.get('low')
        close = candle.get('close')
        if high is None or low is None or close is None:
            continue
        if prev_close is None:
            tr = high - low
        else:
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        ranges.append(tr)
        prev_close = close
    return ranges


def _compute_atr_last(candles: List[Dict[str, Any]], period: int = 14) -> Optional[float]:
    trs = _true_ranges(candles)
    if len(trs) < period:
        return None
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = ((atr * (period - 1)) + tr) / period
    return atr


def _compute_adx_last(candles: List[Dict[str, Any]], period: int = 14) -> Optional[float]:
    if len(candles) < period + 1:
        return None
    highs = [c.get('high') for c in candles]
    lows = [c.get('low') for c in candles]
    closes = [c.get('close') for c in candles]
    if any(v is None for v in highs + lows + closes):
        return None

    tr_list: List[float] = []
    plus_dm_list: List[float] = []
    minus_dm_list: List[float] = []

    for i in range(1, len(candles)):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        plus_dm = up_move if up_move > down_move and up_move > 0 else 0.0
        minus_dm = down_move if down_move > up_move and down_move > 0 else 0.0
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        tr_list.append(tr)
        plus_dm_list.append(plus_dm)
        minus_dm_list.append(minus_dm)

    if len(tr_list) < period:
        return None

    tr14 = sum(tr_list[:period])
    plus_dm14 = sum(plus_dm_list[:period])
    minus_dm14 = sum(minus_dm_list[:period])

    def _di(dm: float, tr: float) -> float:
        return 100.0 * dm / tr if tr else 0.0

    plus_di = _di(plus_dm14, tr14)
    minus_di = _di(minus_dm14, tr14)
    dx_list: List[float] = []
    denom = plus_di + minus_di
    dx_list.append(100.0 * abs(plus_di - minus_di) / denom if denom else 0.0)

    for i in range(period, len(tr_list)):
        tr14 = tr14 - (tr14 / period) + tr_list[i]
        plus_dm14 = plus_dm14 - (plus_dm14 / period) + plus_dm_list[i]
        minus_dm14 = minus_dm14 - (minus_dm14 / period) + minus_dm_list[i]
        plus_di = _di(plus_dm14, tr14)
        minus_di = _di(minus_dm14, tr14)
        denom = plus_di + minus_di
        dx_list.append(100.0 * abs(plus_di - minus_di) / denom if denom else 0.0)

    if len(dx_list) < period:
        return None
    adx = sum(dx_list[:period]) / period
    for dx in dx_list[period:]:
        adx = ((adx * (period - 1)) + dx) / period
    return adx


def _avg_volume_ratio(candles: List[Dict[str, Any]], period: int = 20) -> Tuple[Optional[float], Optional[float]]:
    volumes = [c.get('volume') for c in candles if c.get('volume') is not None and c.get('volume') > 0]
    if not volumes:
        return None, None
    window = volumes[-period:] if len(volumes) >= period else volumes
    avg = sum(window) / len(window) if window else None
    if avg is None or avg <= 0:
        return None, None
    ratio = volumes[-1] / avg
    return avg, ratio


def _pct_change(latest: float, past: float) -> Optional[float]:
    try:
        if past is None or past == 0 or latest is None:
            return None
        return (latest - past) / past * 100.0
    except Exception:
        return None


def _pct_move(closes: List[float], days: int) -> Optional[float]:
    if days <= 0 or len(closes) <= days:
        return None
    return _pct_change(closes[-1], closes[-(days + 1)])


def _calc_high_low(values: List[float]) -> Tuple[Optional[float], Optional[float]]:
    if not values:
        return None, None
    return max(values), min(values)


def _calc_ema_stack(ema20: Optional[float], ema50: Optional[float], ema100: Optional[float], ema200: Optional[float]) -> str:
    if ema20 is not None and ema50 is not None and ema100 is not None and ema200 is not None:
        if ema20 > ema50 > ema100 > ema200:
            return 'BULL_STACK'
        if ema20 < ema50 < ema100 < ema200:
            return 'BEAR_STACK'
        return 'MIXED'
    if ema20 is not None and ema50 is not None and ema100 is not None:
        if ema20 > ema50 > ema100:
            return 'BULL_STACK'
        if ema20 < ema50 < ema100:
            return 'BEAR_STACK'
    if ema20 is not None and ema50 is not None:
        if ema20 > ema50:
            return 'BULL_STACK'
        if ema20 < ema50:
            return 'BEAR_STACK'
    return 'MIXED'


def _calc_trend_direction(price: float, ema50: Optional[float], ema200: Optional[float]) -> str:
    if ema200 is not None:
        if price > ema200 and (ema50 is None or ema50 >= ema200):
            return 'UPTREND'
        if price < ema200 and (ema50 is None or ema50 <= ema200):
            return 'DOWNTREND'
    if ema50 is not None:
        if price > ema50:
            return 'UPTREND'
        if price < ema50:
            return 'DOWNTREND'
    return 'CONSOLIDATION'


def _calc_level_metrics(
    candles: List[Dict[str, Any]],
    window: int,
    tolerance: float,
) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float], Optional[float]]:
    subset = candles[-window:] if window > 0 and len(candles) > window else candles
    lows = [c.get('low') for c in subset if c.get('low') is not None]
    highs = [c.get('high') for c in subset if c.get('high') is not None]
    if not lows or not highs:
        return None, None, None, None, None
    support = min(lows)
    resistance = max(highs)
    support_strength = sum(1 for low in lows if support and abs(low - support) / support <= tolerance)
    resistance_strength = sum(1 for high in highs if resistance and abs(high - resistance) / resistance <= tolerance)
    level_score = min(100.0, (support_strength + resistance_strength) * 5.0)
    return support, resistance, float(support_strength), float(resistance_strength), level_score


def _compute_signal_score(
    *,
    price: float,
    ema20: Optional[float],
    ema50: Optional[float],
    ema100: Optional[float],
    ema200: Optional[float],
    rsi: Optional[float],
    macd_hist: Optional[float],
    volume_ratio20: Optional[float],
    adx14: Optional[float],
    trend_direction: Optional[str],
    breakout_flag: Optional[str],
) -> float:
    score = 0.0
    if ema20 is not None and price >= ema20:
        score += 10
    if ema50 is not None and price >= ema50:
        score += 10
    if ema100 is not None and price >= ema100:
        score += 10
    if ema200 is not None and price >= ema200:
        score += 10
    if rsi is not None and rsi >= 50:
        score += 10
    if macd_hist is not None and macd_hist > 0:
        score += 10
    if volume_ratio20 is not None and volume_ratio20 >= 1:
        score += 10
    if adx14 is not None and adx14 >= ASURA_DEFAULT_MIN_ADX:
        score += 10
    if trend_direction == 'UPTREND':
        score += 10
    if breakout_flag == 'BREAKOUT':
        score += 10
    return score


_IDENT_RE = re.compile(r'^[A-Za-z0-9_.$#]+$')


def _safe_identifier(value: str) -> str:
    candidate = (value or '').strip()
    if not candidate or not _IDENT_RE.match(candidate):
        raise ValueError('Invalid identifier')
    return candidate


_SOURCE_SCORE_COLUMNS = {
    'SYMBOL',
    'STOCK',
    'TRADE_DATE',
    'TRADING_DATE',
    'BUYING_DATE',
    'RUN_DATE',
    'CLOSE_PRICE',
    'PRICE',
    'BUYING_PRICE',
    'LTP',
    'LAST_PRICE',
    'CLOSE',
    'SIGNAL_SCORE',
    'EMA20',
    'EMA_20',
    'EMA50',
    'EMA_50',
    'EMA100',
    'EMA_100',
    'EMA200',
    'EMA_200',
    'ADX14',
    'EMA_STACK',
    'TREND_DIRECTION',
    'BREAKOUT_FLAG',
}


def _has_min_scan_columns(columns: set[str]) -> bool:
    if not columns:
        return False
    has_symbol = ('SYMBOL' in columns) or ('STOCK' in columns)
    has_date = any(col in columns for col in ('TRADE_DATE', 'TRADING_DATE', 'BUYING_DATE', 'RUN_DATE'))
    has_price = any(col in columns for col in ('CLOSE_PRICE', 'PRICE', 'BUYING_PRICE', 'LTP', 'LAST_PRICE', 'CLOSE'))
    has_signal = 'SIGNAL_SCORE' in columns
    return has_symbol and has_date and has_price and has_signal


def _get_source_columns(conn, source: str) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT * FROM {source} WHERE ROWNUM = 0")
        return {str(col[0]).upper() for col in (cur.description or []) if col and col[0]}


def _score_source_columns(columns: set[str]) -> int:
    return len(columns.intersection(_SOURCE_SCORE_COLUMNS))


def _first_of(row: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if not key:
            continue
        val = row.get(key)
        if val is not None:
            return val
    return None


def _normalize_symbol_code(value: Any) -> str:
    text = str(value or '').strip().upper()
    if not text:
        return ''
    if ':' in text:
        text = text.split(':', 1)[1]
    if '-' in text:
        text = text.rsplit('-', 1)[0]
    return text.strip()


def _parse_symbol_filters(value: Optional[str]) -> tuple[str, ...]:
    if not value:
        return ()
    items: list[str] = []
    for raw in str(value).split(','):
        symbol = _normalize_symbol_code(raw)
        if symbol and symbol not in items:
            items.append(symbol)
    return tuple(items)


def _to_bool_flag(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        try:
            return bool(int(value))
        except Exception:
            return False
    text = str(value).strip().lower()
    if text in ('1', 'y', 'yes', 'true', 't'):
        return True
    if text in ('0', 'n', 'no', 'false', 'f'):
        return False
    try:
        return bool(int(float(text)))
    except Exception:
        return False


_SORT_COLUMN_CANDIDATES: dict[str, list[str]] = {
    'symbol': ['SYMBOL', 'STOCK'],
    'stock_name': ['STOCK_NAME', 'STOCK', 'SYMBOL'],
    'trade_date': ['TRADE_DATE', 'TRADING_DATE', 'BUYING_DATE', 'RUN_DATE'],
    'buying_date': ['BUYING_DATE', 'TRADE_DATE', 'TRADING_DATE', 'RUN_DATE'],
    'price': ['CLOSE_PRICE', 'PRICE', 'BUYING_PRICE', 'LTP', 'LAST_PRICE', 'CLOSE'],
    'volume': ['VOLUME'],
    'move_1d_pct': ['MOVE_1D_PCT'],
    'move_1w_pct': ['MOVE_1W_PCT'],
    'move_1m_pct': ['MOVE_1M_PCT'],
    'avg_volume20': ['AVG_VOLUME20'],
    'volume_ratio': ['VOLUME_RATIO20', 'VOLUME_RATIO'],
    'volume_ratio20': ['VOLUME_RATIO20', 'VOLUME_RATIO'],
    'high_52w': ['HIGH_52W'],
    'low_52w': ['LOW_52W'],
    'ath': ['ATH'],
    'high_1y': ['HIGH_1Y'],
    'high_2y': ['HIGH_2Y'],
    'ema20': ['EMA20'],
    'ema50': ['EMA50'],
    'ema100': ['EMA100'],
    'ema200': ['EMA200'],
    'ema50_slopepct_10d': ['EMA50_SLOPEPCT_10D'],
    'rsi': ['RSI14', 'RSI'],
    'rsi14': ['RSI14', 'RSI'],
    'macd_line': ['MACD_LINE'],
    'macd_signal': ['MACD_SIGNAL'],
    'macd_hist': ['MACD_HIST'],
    'atr14': ['ATR14'],
    'atr_pct': ['ATR_PCT'],
    'adx': ['ADX14'],
    'adx14': ['ADX14'],
    'di_plus14': ['DI_PLUS14'],
    'di_minus14': ['DI_MINUS14'],
    'trend_direction': ['TREND_DIRECTION'],
    'ema_stack': ['EMA_STACK'],
    'support_price': ['SUPPORT_PRICE'],
    'resistance_price': ['RESISTANCE_PRICE'],
    'dist_to_support_pct': ['DIST_TO_SUPPORT_PCT'],
    'dist_to_resistance_pct': ['DIST_TO_RESISTANCE_PCT'],
    'support_strength': ['SUPPORT_STRENGTH'],
    'resistance_strength': ['RESISTANCE_STRENGTH'],
    'level_score': ['LEVEL_SCORE'],
    'level_proximity_score': ['LEVEL_PROXIMITY_SCORE'],
    'level_touch_score': ['LEVEL_TOUCH_SCORE'],
    'level_recency_score': ['LEVEL_RECENCY_SCORE'],
    'level_confluence_score': ['LEVEL_CONFLUENCE_SCORE'],
    'breakout_flag': ['BREAKOUT_FLAG'],
    'retest_ready': ['RETEST_READY'],
    'setup_type': ['SETUP_TYPE'],
    'entry_price': ['ENTRY_PRICE'],
    'stop_loss': ['STOP_LOSS'],
    'target1': ['TARGET1'],
    'target2': ['TARGET2'],
    'rr_1': ['RR_1'],
    'rr_2': ['RR_2'],
    'signal_score': ['SIGNAL_SCORE'],
    'index': ['SYMBOL'],
    'mcap': ['SYMBOL'],
    'mcap_rank': ['SYMBOL'],
}


def _resolve_sort_column(sort_key: str, available: set[str]) -> Optional[str]:
    candidates = _SORT_COLUMN_CANDIDATES.get(sort_key, [])
    for cand in candidates:
        if cand in available:
            return cand
    for fallback in ('SYMBOL', 'STOCK', 'TRADE_DATE', 'TRADING_DATE', 'BUYING_DATE', 'RUN_DATE'):
        if fallback in available:
            return fallback
    if available:
        return sorted(available)[0]
    return None


def _parse_date_value(value: Any) -> Optional[date]:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return datetime.strptime(text[:10], '%Y-%m-%d').date()
        except Exception:
            return None
    return None


_INSERT_FIELD_MAP: List[Tuple[str, Tuple[str, ...]]] = [
    ("stock", ("STOCK", "SYMBOL")),
    ("buying_date", ("BUYING_DATE", "TRADE_DATE", "TRADING_DATE")),
    ("buying_price", ("BUYING_PRICE", "PRICE", "CLOSE_PRICE", "ENTRY_PRICE", "ENTRYPRICE")),
    ("entry_price", ("ENTRY_PRICE", "ENTRYPRICE")),
    ("signal_score", ("SIGNAL_SCORE", "SIGNALSCORE")),
    ("volume_ratio20", ("VOLUME_RATIO20", "VOLUMERATIO20", "VOLUME_RATIO")),
    ("ema20", ("EMA20", "EMA_20")),
    ("ema50", ("EMA50", "EMA_50")),
    ("ema100", ("EMA100", "EMA_100")),
    ("ema200", ("EMA200", "EMA_200")),
    ("rsi", ("RSI14", "RSI")),
    ("macd", ("MACD_HIST", "MACD")),
    ("volume", ("VOLUME",)),
    ("atr", ("ATR14", "ATR")),
    ("adx14", ("ADX14", "ADX")),
    ("support", ("SUPPORT_PRICE", "SUPPORT")),
    ("resistance", ("RESISTANCE_PRICE", "RESISTANCE")),
    ("trend_direction", ("TREND_DIRECTION", "TRENDIRECTION")),
    ("ema_stack", ("EMA_STACK",)),
    ("support_strength", ("SUPPORT_STRENGTH", "S_STRENGTH")),
    ("resistance_strength", ("RESISTANCE_STRENGTH", "R_STRENGTH")),
    ("level_score", ("LEVEL_SCORE", "LEVELSCORE")),
    ("bo_flag", ("BREAKOUT_FLAG", "BO_FLAG")),
    ("retest_ready", ("RETEST_READY", "RETESTREADY")),
    ("setup_type", ("SETUP_TYPE", "SETUPTYPE")),
    ("status", ("STATUS",)),
    ("bt_date", ("BT_DATE", "BACKTESTING_DATE")),
    ("stop_loss", ("STOP_LOSS", "STOPLOSS", "SL")),
    ("target1", ("TARGET1", "T1")),
    ("target2", ("TARGET2", "T2")),
    ("rr1", ("RR_1", "RRR1", "RR1")),
    ("rr2", ("RR_2", "RRR2", "RR2")),
]

_INSERT_KEYS = [key for key, _ in _INSERT_FIELD_MAP]


def _pick_available_column(available: set[str], candidates: Tuple[str, ...]) -> Optional[str]:
    for cand in candidates:
        if cand in available:
            return cand
    return None


def _has_ema_columns(columns: set[str]) -> bool:
    return any(col in columns for col in ("EMA20", "EMA_20", "EMA50", "EMA_50", "EMA100", "EMA_100", "EMA200", "EMA_200"))


def _normalize_ema_periods(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        row['ema20'] = 20
        row['ema50'] = 50
        row['ema100'] = 100
        row['ema200'] = 200
    return rows


def _resolve_ema_source(conn) -> Tuple[Optional[str], Optional[set[str]]]:
    explicit = (os.getenv("ASURA_EMA_SOURCE_VIEW") or "").strip()
    if explicit:
        try:
            cols = _get_source_columns(conn, _safe_identifier(explicit))
            if _has_ema_columns(cols):
                return explicit, cols
        except Exception:
            pass

    fallback_view = (_fallback_source_view or "").strip()
    if fallback_view:
        try:
            cols = _get_source_columns(conn, _safe_identifier(fallback_view))
            if _has_ema_columns(cols):
                return fallback_view, cols
        except Exception:
            pass

    try:
        source, cols = _resolve_source(conn)
        if _has_ema_columns(cols):
            return source, cols
    except Exception:
        pass

    for name in _build_source_candidates():
        try:
            cols = _get_source_columns(conn, name)
        except Exception:
            continue
        if _has_ema_columns(cols):
            return name, cols

    return None, None


def _enrich_rows_with_ema(conn, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not rows:
        return rows
    source, columns = _resolve_ema_source(conn)
    if not source or not columns:
        # Use OHLC-derived EMA when no EMA source is available (local DB mode).
        if ASURA_INSERT_EMA_FROM_OHLC:
            return _enrich_rows_with_ema_from_ohlc(rows)
        return rows
    symbol_col = _pick_available_column(columns, ("SYMBOL", "STOCK"))
    if not symbol_col:
        return rows
    trade_col = _pick_available_column(columns, ("TRADE_DATE", "TRADING_DATE", "BUYING_DATE", "RUN_DATE", "DATE"))
    ema_cols = {
        "ema20": _pick_available_column(columns, ("EMA20", "EMA_20")),
        "ema50": _pick_available_column(columns, ("EMA50", "EMA_50")),
        "ema100": _pick_available_column(columns, ("EMA100", "EMA_100")),
        "ema200": _pick_available_column(columns, ("EMA200", "EMA_200")),
    }
    if not any(ema_cols.values()):
        return rows

    symbols = sorted({row.get("stock") for row in rows if row.get("stock")})
    if not symbols:
        return rows

    ema_map: Dict[Tuple[str, Optional[date]], Dict[str, Optional[float]]] = {}
    ema_latest: Dict[str, Dict[str, Optional[float]]] = {}
    chunk_size = 900
    select_parts = [f"{symbol_col} AS SYMBOL"]
    if trade_col:
        select_parts.append(f"{trade_col} AS TRADE_DATE")
    for key, col in ema_cols.items():
        if col:
            select_parts.append(f"{col} AS {key.upper()}")
    select_sql = ", ".join(select_parts)

    if trade_col:
        date_groups: Dict[date, List[str]] = {}
        for row in rows:
            sym = row.get("stock")
            dt = row.get("buying_date")
            if not sym or not isinstance(dt, date):
                continue
            date_groups.setdefault(dt, []).append(sym)

        for dt, syms in date_groups.items():
            unique_syms = sorted(set(syms))
            for idx in range(0, len(unique_syms), chunk_size):
                chunk = unique_syms[idx:idx + chunk_size]
                binds: Dict[str, Any] = {"trade_date": dt}
                placeholders = []
                for jdx, sym in enumerate(chunk):
                    key = f"sym{dt.strftime('%Y%m%d')}_{idx}_{jdx}"
                    placeholders.append(f":{key}")
                    binds[key] = sym
                sql = f"""
                  SELECT {select_sql}
                  FROM {source} s
                  WHERE s.{trade_col} = :trade_date
                    AND s.{symbol_col} IN ({", ".join(placeholders)})
                """
                with conn.cursor() as cur:
                    cur.execute(sql, binds)
                    cols = [str(d[0]).lower() for d in (cur.description or [])]
                    for raw in cur.fetchall() or []:
                        row = dict(zip(cols, raw))
                        sym = str(row.get("symbol") or "").strip().upper()
                        if not sym:
                            continue
                        trade_dt = _parse_date_value(row.get("trade_date"))
                        ema_map[(sym, trade_dt)] = {
                            "ema20": _to_float(row.get("ema20")),
                            "ema50": _to_float(row.get("ema50")),
                            "ema100": _to_float(row.get("ema100")),
                            "ema200": _to_float(row.get("ema200")),
                        }

    for idx in range(0, len(symbols), chunk_size):
        chunk = symbols[idx:idx + chunk_size]
        binds: Dict[str, Any] = {}
        placeholders = []
        for jdx, sym in enumerate(chunk):
            key = f"sym_latest_{idx}_{jdx}"
            placeholders.append(f":{key}")
            binds[key] = sym
        if trade_col:
            sql_latest = f"""
              SELECT {select_sql}
              FROM (
                  SELECT s.*,
                         ROW_NUMBER() OVER (PARTITION BY s.{symbol_col} ORDER BY s.{trade_col} DESC) AS RN
                  FROM {source} s
                  WHERE s.{symbol_col} IN ({", ".join(placeholders)})
              )
              WHERE RN = 1
            """
        else:
            sql_latest = f"""
              SELECT {select_sql}
              FROM {source} s
              WHERE s.{symbol_col} IN ({", ".join(placeholders)})
            """
        with conn.cursor() as cur:
            cur.execute(sql_latest, binds)
            cols = [str(d[0]).lower() for d in (cur.description or [])]
            for raw in cur.fetchall() or []:
                row = dict(zip(cols, raw))
                sym = str(row.get("symbol") or "").strip().upper()
                if not sym:
                    continue
                ema_latest[sym] = {
                    "ema20": _to_float(row.get("ema20")),
                    "ema50": _to_float(row.get("ema50")),
                    "ema100": _to_float(row.get("ema100")),
                    "ema200": _to_float(row.get("ema200")),
                }

    for row in rows:
        sym = row.get("stock")
        if not sym:
            continue
        dt = row.get("buying_date") if isinstance(row.get("buying_date"), date) else None
        values = ema_map.get((sym, dt)) or ema_latest.get(sym)
        if not values:
            continue
        for key in ("ema20", "ema50", "ema100", "ema200"):
            value = values.get(key)
            if value is not None:
                row[key] = value
    return rows


def _enrich_rows_with_ema_from_ohlc(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    symbols = sorted({row.get("stock") for row in rows if row.get("stock")})
    if not symbols:
        return rows
    try:
        raw_series = fetch_ohlc_series_from_oracle(months=ASURA_LOCAL_LOOKBACK_MONTHS)
    except Exception:
        _logger.exception("Failed to load OHLC series for EMA enrichment")
        return rows

    ema_cache: Dict[str, Dict[date, Dict[str, Optional[float]]]] = {}
    ema_latest: Dict[str, Dict[str, Optional[float]]] = {}

    for sym in symbols:
        entries = raw_series.get(sym)
        if not entries:
            continue
        candles = _normalize_candles(entries)
        if not candles:
            continue
        ema_state: Dict[int, Optional[float]] = {20: None, 50: None, 100: None, 200: None}
        ema_by_date: Dict[date, Dict[str, Optional[float]]] = {}
        for candle in candles:
            close_val = candle.get("close")
            if close_val is None:
                continue
            ema_state[20] = _next_ema(ema_state[20], close_val, 20)
            ema_state[50] = _next_ema(ema_state[50], close_val, 50)
            ema_state[100] = _next_ema(ema_state[100], close_val, 100)
            ema_state[200] = _next_ema(ema_state[200], close_val, 200)
            trade_dt = candle["date"].date()
            ema_by_date[trade_dt] = {
                "ema20": ema_state[20],
                "ema50": ema_state[50],
                "ema100": ema_state[100],
                "ema200": ema_state[200],
            }
        if ema_by_date:
            ema_cache[sym] = ema_by_date
            ema_latest[sym] = ema_by_date[sorted(ema_by_date.keys())[-1]]

    for row in rows:
        sym = row.get("stock")
        if not sym or sym not in ema_cache:
            continue
        dt = row.get("buying_date") if isinstance(row.get("buying_date"), date) else None
        values = ema_cache[sym].get(dt) if dt else None
        if not values:
            values = ema_latest.get(sym)
        if not values:
            continue
        for key in ("ema20", "ema50", "ema100", "ema200"):
            value = values.get(key)
            if value is not None:
                row[key] = value
    return rows


def _normalize_insert_rows(payload: Any) -> Tuple[List[Dict[str, Any]], int, List[Dict[str, Any]]]:
    rows = []
    errors: List[Dict[str, Any]] = []
    skipped = 0
    items = payload if isinstance(payload, list) else payload.get('rows') if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return [], 0, [{'row': None, 'error': 'rows must be a list'}]

    for idx, raw in enumerate(items):
        if not isinstance(raw, dict):
            skipped += 1
            errors.append({'row': idx, 'error': 'invalid row type'})
            continue
        row_out = {key: None for key in _INSERT_KEYS}
        stock = raw.get('stock') or raw.get('symbol') or raw.get('STOCK') or raw.get('SYMBOL')
        buying_date = _first_of(
            raw,
            'buying_date',
            'buyingDate',
            'trade_date',
            'tradeDate',
            'BUYING_DATE',
            'TRADE_DATE',
            'TRADING_DATE',
        )
        entry_price_raw = _first_of(raw, 'entryPrice', 'entry_price', 'ENTRY_PRICE', 'ENTRYPRICE')
        buying_price_raw = _first_of(raw, 'buying_price', 'buyingPrice', 'BUYING_PRICE', 'price', 'PRICE')
        date_val = _parse_date_value(buying_date)
        entry_price_val = _to_float(entry_price_raw)
        price_val = _to_float(buying_price_raw)
        if price_val is None:
            price_val = entry_price_val
        stock = str(stock).strip().upper() if stock else ''
        if not stock or not date_val or price_val is None:
            skipped += 1
            errors.append({'row': idx, 'error': 'missing/invalid stock, buying_date, or buying_price'})
            continue
        row_out['stock'] = stock
        row_out['buying_date'] = date_val
        row_out['buying_price'] = price_val
        row_out['entry_price'] = entry_price_val if entry_price_val is not None else price_val

        row_out['signal_score'] = _to_float(_first_of(raw, 'signal_score', 'signalScore', 'SIGNAL_SCORE', 'SIGNALSCORE'))
        row_out['volume_ratio20'] = _to_float(
            _first_of(raw, 'volume_ratio20', 'volumeRatio20', 'VOLUME_RATIO20', 'VOLUMERATIO20')
        )
        row_out['ema20'] = _to_float(_first_of(raw, 'ema20', 'EMA20', 'ema_20', 'EMA_20'))
        row_out['ema50'] = _to_float(_first_of(raw, 'ema50', 'EMA50', 'ema_50', 'EMA_50'))
        row_out['ema100'] = _to_float(_first_of(raw, 'ema100', 'EMA100', 'ema_100', 'EMA_100'))
        row_out['ema200'] = _to_float(_first_of(raw, 'ema200', 'EMA200', 'ema_200', 'EMA_200'))
        row_out['rsi'] = _to_float(_first_of(raw, 'rsi', 'rsi14', 'RSI', 'RSI14'))
        row_out['macd'] = _to_float(_first_of(raw, 'macd', 'macdHist', 'macd_hist', 'MACD', 'MACD_HIST'))
        row_out['volume'] = _to_float(_first_of(raw, 'volume', 'VOLUME'))
        row_out['atr'] = _to_float(_first_of(raw, 'atr', 'atr14', 'ATR', 'ATR14'))
        row_out['adx14'] = _to_float(_first_of(raw, 'adx14', 'adx', 'ADX14', 'ADX'))
        row_out['support'] = _to_float(_first_of(raw, 'support', 'support_price', 'SUPPORT', 'SUPPORT_PRICE'))
        row_out['resistance'] = _to_float(
            _first_of(raw, 'resistance', 'resistance_price', 'RESISTANCE', 'RESISTANCE_PRICE')
        )
        trend_direction = _first_of(raw, 'trend_direction', 'trendDirection', 'TREND_DIRECTION', 'TRENDIRECTION')
        if trend_direction is not None:
            row_out['trend_direction'] = str(trend_direction).strip().upper()
        ema_stack = _first_of(raw, 'ema_stack', 'emaStack', 'EMA_STACK')
        if ema_stack is not None:
            row_out['ema_stack'] = str(ema_stack).strip().upper()
        row_out['support_strength'] = _to_float(
            _first_of(raw, 'support_strength', 'supportStrength', 'SUPPORT_STRENGTH', 'S_STRENGTH')
        )
        row_out['resistance_strength'] = _to_float(
            _first_of(raw, 'resistance_strength', 'resistanceStrength', 'RESISTANCE_STRENGTH', 'R_STRENGTH')
        )
        row_out['level_score'] = _to_float(_first_of(raw, 'level_score', 'levelScore', 'LEVEL_SCORE', 'LEVELSCORE'))
        row_out['bo_flag'] = _first_of(
            raw, 'breakout_flag', 'breakoutFlag', 'bo_flag', 'BO_FLAG', 'BREAKOUT_FLAG'
        )
        retest_raw = _first_of(raw, 'retest_ready', 'retestReady', 'RETEST_READY', 'RETESTREADY')
        if retest_raw is not None:
            row_out['retest_ready'] = 1 if _to_bool_flag(retest_raw) else 0
        row_out['setup_type'] = _first_of(raw, 'setup_type', 'setupType', 'SETUP_TYPE', 'SETUPTYPE')
        row_out['status'] = _first_of(raw, 'status', 'STATUS')
        row_out['bt_date'] = _parse_date_value(
            _first_of(raw, 'bt_date', 'BT_DATE', 'backtestingDate', 'backtesting_date', 'BACKTESTING_DATE')
        )
        row_out['stop_loss'] = _to_float(
            _first_of(raw, 'stop_loss', 'stopLoss', 'STOP_LOSS', 'stoploss', 'STOPLOSS', 'sl', 'SL')
        )
        row_out['target1'] = _to_float(_first_of(raw, 'target1', 'TARGET1', 't1', 'T1'))
        row_out['target2'] = _to_float(_first_of(raw, 'target2', 'TARGET2', 't2', 'T2'))
        row_out['rr1'] = _to_float(_first_of(raw, 'rr1', 'rr_1', 'RR1', 'RR_1', 'RRR1'))
        row_out['rr2'] = _to_float(_first_of(raw, 'rr2', 'rr_2', 'RR2', 'RR_2', 'RRR2'))
        rows.append(row_out)
    return rows, skipped, errors


def _resolve_sequence_name(conn, seq_name: str) -> Optional[str]:
    name = (seq_name or '').strip().upper()
    if not name:
        return None
    with conn.cursor() as cur:
        try:
            cur.execute("SELECT SEQUENCE_NAME FROM USER_SEQUENCES WHERE SEQUENCE_NAME = :name", {'name': name})
            if cur.fetchone():
                return name
        except Exception:
            pass
        try:
            cur.execute(
                "SELECT SEQUENCE_OWNER, SEQUENCE_NAME FROM ALL_SEQUENCES WHERE SEQUENCE_NAME = :name",
                {'name': name},
            )
            row = cur.fetchone()
            if row and row[0]:
                owner = str(row[0]).strip()
                return f"{owner}.{name}"
        except Exception:
            return None
    return None


def _load_max_s_no(conn, table: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SELECT NVL(MAX(S_NO), 0) FROM {table}")
        row = cur.fetchone()
        return int(row[0] or 0) if row else 0


def _build_rows_from_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for row in items or []:
        row_out = {key: None for key in _INSERT_KEYS}
        stock = row.get('symbol') or row.get('stock')
        buying_date = row.get('tradeDate') or row.get('buyingDate') or row.get('trade_date') or row.get('buying_date')
        entry_price_val = _to_float(row.get('entryPrice') if row.get('entryPrice') is not None else None)
        price_val = _to_float(row.get('buyingPrice') if row.get('buyingPrice') is not None else row.get('price'))
        if price_val is None:
            price_val = entry_price_val
        stock = str(stock).strip().upper() if stock else ''
        date_val = _parse_date_value(buying_date)
        if not stock or not date_val or price_val is None:
            continue
        row_out['stock'] = stock
        row_out['buying_date'] = date_val
        row_out['buying_price'] = price_val
        row_out['entry_price'] = entry_price_val if entry_price_val is not None else price_val

        row_out['signal_score'] = _to_float(row.get('signalScore'))
        row_out['volume_ratio20'] = _to_float(row.get('volumeRatio20'))
        row_out['ema20'] = _to_float(row.get('ema20'))
        row_out['ema50'] = _to_float(row.get('ema50'))
        row_out['ema100'] = _to_float(row.get('ema100'))
        row_out['ema200'] = _to_float(row.get('ema200'))
        row_out['rsi'] = _to_float(row.get('rsi'))
        row_out['macd'] = _to_float(row.get('macdHist'))
        row_out['volume'] = _to_float(row.get('volume'))
        row_out['atr'] = _to_float(row.get('atr'))
        row_out['adx14'] = _to_float(row.get('adx14'))
        row_out['support'] = _to_float(row.get('support'))
        row_out['resistance'] = _to_float(row.get('resistance'))
        trend_direction = row.get('trendDirection')
        if trend_direction is not None:
            row_out['trend_direction'] = str(trend_direction).strip().upper()
        ema_stack = row.get('emaStack')
        if ema_stack is not None:
            row_out['ema_stack'] = str(ema_stack).strip().upper()
        row_out['support_strength'] = _to_float(row.get('supportStrength'))
        row_out['resistance_strength'] = _to_float(row.get('resistanceStrength'))
        row_out['level_score'] = _to_float(row.get('levelScore'))
        row_out['bo_flag'] = row.get('breakoutFlag')
        retest_val = row.get('retestReady')
        if retest_val is not None:
            row_out['retest_ready'] = 1 if _to_bool_flag(retest_val) else 0
        row_out['setup_type'] = row.get('setupType')
        row_out['status'] = row.get('status')
        row_out['bt_date'] = _parse_date_value(row.get('backtestingDate') or row.get('btDate'))
        row_out['stop_loss'] = _to_float(row.get('stopLoss'))
        row_out['target1'] = _to_float(row.get('target1'))
        row_out['target2'] = _to_float(row.get('target2'))
        row_out['rr1'] = _to_float(row.get('rr1'))
        row_out['rr2'] = _to_float(row.get('rr2'))
        rows.append(row_out)
    return rows


def _insert_rows(conn, rows: List[Dict[str, Any]]) -> int:
    table = _safe_identifier(ASURA_BULLISH_TREND_TABLE)
    seq_name = _resolve_sequence_name(conn, ASURA_BTS_SEQ) if ASURA_BTS_SEQ else None
    if not rows:
        return 0
    rows = _normalize_ema_periods(rows)

    available = _get_source_columns(conn, table)
    stock_col = _pick_available_column(available, ("STOCK", "SYMBOL"))
    if not stock_col:
        raise RuntimeError("Target table missing STOCK/SYMBOL column")

    columns: List[str] = []
    values: List[str] = []

    def _add(col: Optional[str], expr: str) -> None:
        if not col or col in columns:
            return
        columns.append(col)
        values.append(expr)

    if "S_NO" in available:
        if seq_name:
            _add("S_NO", f"{seq_name}.NEXTVAL")
        else:
            max_s_no = _load_max_s_no(conn, table)
            for offset, row in enumerate(rows, start=1):
                row['s_no'] = max_s_no + offset
            _add("S_NO", ":s_no")

    for key, candidates in _INSERT_FIELD_MAP:
        col = _pick_available_column(available, candidates)
        if not col:
            continue
        _add(col, f":{key}")

    if not columns:
        return 0

    if rows:
        sample = {
            'stock': rows[0].get('stock'),
            'buying_date': rows[0].get('buying_date'),
            'buying_price': rows[0].get('buying_price'),
            'ema20': rows[0].get('ema20'),
            'ema50': rows[0].get('ema50'),
            'ema100': rows[0].get('ema100'),
            'ema200': rows[0].get('ema200'),
        }
        _logger.info('Asura insert binds columns=%s sample=%s', columns, sample)

    insert_sql = f"""
    INSERT INTO {table} ({", ".join(columns)})
    SELECT {", ".join(values)}
    FROM dual
    WHERE NOT EXISTS (
        SELECT 1 FROM {table} t WHERE t.{stock_col} = :stock
    )
    """

    with conn.cursor() as cur:
        cur.executemany(insert_sql, rows)
        inserted = cur.rowcount or 0
    return int(inserted or 0)


def _build_source_candidates() -> list[str]:
    schema = (os.getenv('ASURA_SCHEMA') or os.getenv('ORACLE_SCHEMA') or '').strip()
    explicit = (os.getenv('ASURA_VIEW') or '').strip()
    candidates: list[str] = []

    def add(name: str) -> None:
        name = name.strip()
        if not name:
            return
        try:
            name = _safe_identifier(name)
        except ValueError:
            return
        if name not in candidates:
            candidates.append(name)

    if explicit:
        add(explicit)

    add(ASURA_BULLISH_TREND_TABLE)

    for base in ('V_ASURA_SCAN_LATEST', 'MV_ASURA_SCAN_DAILY', 'ASURA_SCAN_DAILY_FACT'):
        add(base)
        if schema:
            add(f'{schema}.{base}')

    return candidates


def _resolve_source(conn) -> Tuple[str, set[str]]:
    global _ASURA_SOURCE, _ASURA_SOURCE_INFO
    if _ASURA_SOURCE_INFO:
        return _ASURA_SOURCE_INFO

    candidates = _build_source_candidates()
    if not candidates:
        raise RuntimeError('No Asura source candidates configured')

    best_name = None
    best_cols: set[str] = set()
    best_score = -1

    for name in candidates:
        try:
            cols = _get_source_columns(conn, name)
        except Exception as exc:
            if 'ORA-00942' in str(exc):
                continue
            raise
        # Require minimal scan columns; otherwise fallback to computed snapshot.
        if not _has_min_scan_columns(cols):
            continue
        score = _score_source_columns(cols)
        if score > best_score:
            best_name = name
            best_cols = cols
            best_score = score

    if not best_name:
        raise RuntimeError(
            "Asura source not found (tried: %s). Set ASURA_VIEW or ASURA_SCHEMA/ORACLE_SCHEMA, and ensure grants/synonyms exist."
            % (', '.join(candidates))
        )

    _ASURA_SOURCE = best_name
    _ASURA_SOURCE_INFO = (best_name, best_cols)
    _logger.info("Asura source resolved: %s (score=%s cols=%s)", best_name, best_score, len(best_cols))
    return _ASURA_SOURCE_INFO


def _parse_int(value: Any, default: int, min_value: int, max_value: int) -> int:
    try:
        num = int(value)
    except Exception:
        num = default
    return max(min_value, min(max_value, num))


def _parse_float(value: Any, default: float, min_value: float, max_value: float) -> float:
    try:
        num = float(value)
    except Exception:
        num = default
    return max(min_value, min(max_value, num))


def _parse_bool(value: Any) -> bool:
    if value is None:
        return False
    token = str(value).strip().lower()
    return token in ('1', 'true', 'yes', 'y', 'on')


_LOCAL_TIMEFRAMES = ('daily', 'weekly', 'monthly', 'yearly')


def _compute_local_snapshot(
    *,
    timeframe: str,
    trade_start_date: Optional[date],
    trade_cutoff_date: Optional[date],
    apply_authoritative_ath: bool = True,
) -> Dict[str, Any]:
    tf = (timeframe or 'daily').strip().lower()
    if tf not in _LOCAL_TIMEFRAMES:
        tf = 'daily'
    cacheable = trade_start_date is None and trade_cutoff_date is None
    cache_key = f'local:asura_snapshot:{tf}'
    expected_ath_source = 'NSE_NIFTY500_DAILY_RAW_DATA_DEV'
    if cacheable:
        cached = _local_snapshot_cache.get(cache_key)
        if cached is not None:
            cached_source = str(cached.get('athSource') or '').strip().upper() if isinstance(cached, dict) else ''
            if cached_source == expected_ath_source:
                return {**cached, 'cached': True}
            log_stale_snapshot_warning(endpoint='/api/asura/local-snapshot', source='local-cache')

    raw_series = fetch_ohlc_series_from_oracle(months=ASURA_LOCAL_LOOKBACK_MONTHS)
    items: List[Dict[str, Any]] = []
    as_of_date: Optional[date] = None

    periods_per_year = {
        'daily': 252,
        'weekly': 52,
        'monthly': 12,
        'yearly': 1,
    }.get(tf, 252)

    for symbol, entries in raw_series.items():
        candles = _normalize_candles(entries)
        if not candles:
            continue
        if trade_cutoff_date:
            candles = [c for c in candles if c['date'].date() <= trade_cutoff_date]
            if not candles:
                continue
        if tf != 'daily':
            candles = _aggregate_candles(candles, tf)
            if not candles:
                continue
        trade_dt = candles[-1]['date'].date()
        if trade_start_date and trade_dt < trade_start_date:
            continue

        closes = [c['close'] for c in candles if c.get('close') is not None]
        if len(closes) < 30:
            continue
        price = closes[-1]
        if price is None:
            continue

        ema20_series = _ema_series(closes, 20) if len(closes) >= 20 else []
        ema50_series = _ema_series(closes, 50) if len(closes) >= 50 else []
        ema100_series = _ema_series(closes, 100) if len(closes) >= 100 else []
        ema200_series = _ema_series(closes, 200) if len(closes) >= 200 else []
        ema20 = ema20_series[-1] if ema20_series else None
        ema50 = ema50_series[-1] if ema50_series else None
        ema100 = ema100_series[-1] if ema100_series else None
        ema200 = ema200_series[-1] if ema200_series else None

        ema50_slope = None
        if len(ema50_series) >= 11:
            base = ema50_series[-11]
            if base:
                ema50_slope = ((ema50_series[-1] - base) / base) * 100.0

        rsi = _compute_rsi_last(closes, 14)
        macd_line, macd_signal, macd_hist = _compute_macd_last(closes)
        atr = _compute_atr_last(candles, 14)
        adx14 = _compute_adx_last(candles, 14)
        avg_vol20, volume_ratio20 = _avg_volume_ratio(candles, 20)

        move1d = _pct_move(closes, 1)
        move1w = _pct_move(closes, 5)
        move1m = _pct_move(closes, 22)

        highs = [c.get('high') for c in candles if c.get('high') is not None]
        lows = [c.get('low') for c in candles if c.get('low') is not None]
        ath = max(highs) if highs else None
        window_highs = highs[-periods_per_year:] if highs and len(highs) >= periods_per_year else highs
        window_lows = lows[-periods_per_year:] if lows and len(lows) >= periods_per_year else lows
        high52w = max(window_highs) if window_highs else None
        low52w = min(window_lows) if window_lows else None
        window_1y = highs[-periods_per_year:] if highs and len(highs) >= periods_per_year else highs
        window_2y = highs[-(periods_per_year * 2):] if highs and len(highs) >= (periods_per_year * 2) else highs
        high1y = max(window_1y) if window_1y else None
        high2y = max(window_2y) if window_2y else None

        support, resistance, support_strength, resistance_strength, level_score = _calc_level_metrics(
            candles, ASURA_LOCAL_LEVEL_WINDOW, ASURA_LOCAL_LEVEL_TOL
        )

        ema_stack = _calc_ema_stack(ema20, ema50, ema100, ema200)
        trend_direction = _calc_trend_direction(price, ema50, ema200)

        breakout_flag = 'NONE'
        if resistance is not None and price > resistance * 1.01:
            breakout_flag = 'BREAKOUT'
        elif support is not None and price < support * 0.99:
            breakout_flag = 'BREAKDOWN'

        retest_ready = False
        if support is not None and support > 0 and price >= support and price <= support * 1.02:
            retest_ready = True
        if breakout_flag == 'BREAKOUT' and resistance is not None and price <= resistance * 1.03:
            retest_ready = True

        setup_type = 'BREAKOUT' if breakout_flag == 'BREAKOUT' else 'PULLBACK'

        entry_price = price
        stop_loss = entry_price * (1 - ASURA_STOP_PCT)
        target1 = entry_price * (1 + ASURA_TARGET1_PCT)
        target2 = entry_price * (1 + ASURA_TARGET2_PCT)
        risk = entry_price - stop_loss
        rr1 = ((target1 - entry_price) / risk) if risk else None
        rr2 = ((target2 - entry_price) / risk) if risk else None

        signal_score = _compute_signal_score(
            price=price,
            ema20=ema20,
            ema50=ema50,
            ema100=ema100,
            ema200=ema200,
            rsi=rsi,
            macd_hist=macd_hist,
            volume_ratio20=volume_ratio20,
            adx14=adx14,
            trend_direction=trend_direction,
            breakout_flag=breakout_flag,
        )

        atr_pct = (atr / price * 100.0) if atr is not None and price else None
        dist_to_support_pct = ((price - support) / price * 100.0) if support is not None and price else None
        dist_to_resistance_pct = ((resistance - price) / price * 100.0) if resistance is not None and price else None

        item = {
            'symbol': str(symbol).strip().upper(),
            'stockName': str(symbol).strip().upper(),
            'tradeDate': trade_dt.isoformat(),
            'price': price,
            'volume': candles[-1].get('volume'),
            'move1dPct': move1d,
            'move1wPct': move1w,
            'move1mPct': move1m,
            'avgVolume20': avg_vol20,
            'volumeRatio20': volume_ratio20,
            'high52w': high52w,
            'low52w': low52w,
            'ath': ath,
            'high1y': high1y,
            'high2y': high2y,
            'ema20': ema20,
            'ema50': ema50,
            'ema100': ema100,
            'ema200': ema200,
            'ema20Flag': _ema_flag(price, ema20, '20'),
            'ema50Flag': _ema_flag(price, ema50, '50'),
            'ema100Flag': _ema_flag(price, ema100, '100'),
            'ema200Flag': _ema_flag(price, ema200, '200'),
            'ema50SlopePct10d': ema50_slope,
            'rsi': rsi,
            'macdLine': macd_line,
            'macdSignal': macd_signal,
            'macdHist': macd_hist,
            'atr': atr,
            'atrPct': atr_pct,
            'adx14': adx14,
            'trendDirection': trend_direction,
            'emaStack': ema_stack,
            'support': support,
            'resistance': resistance,
            'distToSupportPct': dist_to_support_pct,
            'distToResistancePct': dist_to_resistance_pct,
            'supportStrength': support_strength,
            'resistanceStrength': resistance_strength,
            'levelScore': level_score,
            'breakoutFlag': breakout_flag,
            'retestReady': retest_ready,
            'setupType': setup_type,
            'status': 'ACTIVE',
            'entryPrice': entry_price,
            'stopLoss': stop_loss,
            'target1': target1,
            'target2': target2,
            'rr1': rr1,
            'rr2': rr2,
            'signalScore': signal_score,
            'buyingDate': trade_dt.isoformat(),
            'backtestingDate': ASURA_BACKTESTING_DATE,
            'stopLossPct': _calc_stop_loss_pct(entry_price, stop_loss),
            'target1Pct': _calc_target_pct(entry_price, target1),
            'target2Pct': _calc_target_pct(entry_price, target2),
        }
        items.append(_apply_master_score_fields(item))

        if as_of_date is None or trade_dt > as_of_date:
            as_of_date = trade_dt

    if apply_authoritative_ath:
        _apply_authoritative_ath(items, endpoint='/api/asura/local-snapshot')

    payload = {
        'items': items,
        'total': len(items),
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'as_of_date': as_of_date.isoformat() if as_of_date else None,
        'athSource': 'NSE_NIFTY500_DAILY_RAW_DATA_DEV',
    }
    if cacheable:
        _local_snapshot_cache.set(cache_key, payload)
    return payload


def _compute_local_payload(
    *,
    timeframe: str,
    min_signal: float,
    min_adx: float,
    breakout_only: bool,
    sort: str,
    order: str,
    page: int,
    page_size: int,
    search: Optional[str],
    symbols: tuple[str, ...],
    trade_start_date: Optional[date],
    trade_cutoff_date: Optional[date],
) -> Dict[str, Any]:
    snapshot = _compute_local_snapshot(
        timeframe=timeframe,
        trade_start_date=trade_start_date,
        trade_cutoff_date=trade_cutoff_date,
        apply_authoritative_ath=False,
    )
    base_items = list(snapshot.get('items') or [])
    query_payload = _apply_query_filters(
        base_items,
        min_signal=min_signal,
        min_adx=min_adx,
        breakout_only=breakout_only,
        sort=sort,
        order=order,
        search=search,
        symbols=symbols,
        page=page,
        page_size=page_size,
    )
    _apply_authoritative_ath(query_payload.get('items') or [], endpoint='/api/asura/local-query')
    return {
        **query_payload,
        'generated_at': snapshot.get('generated_at'),
        'cached': bool(snapshot.get('cached')),
        'fallback': True,
        'local': True,
        'as_of_date': snapshot.get('as_of_date'),
        'athSource': 'NSE_NIFTY500_DAILY_RAW_DATA_DEV',
    }


def _compute_payload(
    *,
    timeframe: str,
    min_signal: float,
    min_adx: float,
    breakout_only: bool,
    sort: str,
    order: str,
    page: int,
    page_size: int,
    search: Optional[str],
    symbols: tuple[str, ...],
    conditions_only: bool,
    include_exited: bool,
    trade_start_date: Optional[date],
    trade_cutoff_date: Optional[date],
    apply_authoritative_ath: bool = True,
    latest_ltc_date: Optional[str] = None,
) -> Dict[str, Any]:
    exact_symbols_mode = bool(symbols)
    if sort not in _SORT_COLUMN_MAP:
        raise ValueError('Invalid sort field')
    if order not in ('asc', 'desc'):
        raise ValueError('Invalid sort order')
    if timeframe != 'daily':
        return _compute_local_payload(
            timeframe=timeframe,
            min_signal=min_signal,
            min_adx=min_adx,
            breakout_only=breakout_only,
            sort=sort,
            order=order,
            page=page,
            page_size=page_size,
            search=search,
            symbols=symbols,
            trade_start_date=trade_start_date,
            trade_cutoff_date=trade_cutoff_date,
        )
    if trade_start_date and trade_cutoff_date and trade_start_date > trade_cutoff_date:
        raise ValueError('start_date must be on or before cutoff_date')
    latest_ltc_date_key = str(latest_ltc_date or '').strip()[:10] or None

    sort_dir = 'DESC' if order == 'desc' else 'ASC'
    offset = (max(page, 1) - 1) * page_size
    started_at = time.perf_counter()
    acquire_started_at = time.perf_counter()
    connection_acquire_ms = 0
    source_resolve_ms = 0
    query_elapsed_ms = 0
    count_elapsed_ms = 0
    row_materialize_ms = 0

    try:
        with pool.acquire() as conn:
            connection_acquire_ms = int((time.perf_counter() - acquire_started_at) * 1000)
            source_started_at = time.perf_counter()
            source, available = _resolve_source(conn)
            source_resolve_ms = int((time.perf_counter() - source_started_at) * 1000)
            available = {str(col).upper() for col in (available or set())}
            with conn.cursor() as cur:
                where_parts = ["1=1"]
                bind: Dict[str, Any] = {}
                trade_col = _pick_available_column(available, ('TRADE_DATE', 'TRADING_DATE', 'BUYING_DATE', 'RUN_DATE'))
                status_col = _pick_available_column(available, ('STATUS',))
                sell_col = _pick_available_column(available, ('SELLING_DATE', 'EXIT_DATE', 'SELL_DATE'))

                if (not exact_symbols_mode) and trade_col and conditions_only and trade_start_date is None and trade_cutoff_date is None:
                    safe_trade_col = _safe_identifier(trade_col)
                    where_parts.append(f"s.{safe_trade_col} = (SELECT MAX(s2.{safe_trade_col}) FROM {source} s2)")

                if trade_col:
                    safe_trade_col = _safe_identifier(trade_col)
                    if trade_start_date and trade_cutoff_date:
                        where_parts.append(f"s.{safe_trade_col} BETWEEN :trade_start_date AND :trade_cutoff_date")
                        bind['trade_start_date'] = trade_start_date
                        bind['trade_cutoff_date'] = trade_cutoff_date
                    elif trade_start_date:
                        where_parts.append(f"s.{safe_trade_col} >= :trade_start_date")
                        bind['trade_start_date'] = trade_start_date
                    elif trade_cutoff_date:
                        where_parts.append(f"s.{safe_trade_col} <= :trade_cutoff_date")
                        bind['trade_cutoff_date'] = trade_cutoff_date

                if (not exact_symbols_mode) and 'TREND_DIRECTION' in available:
                    where_parts.append("s.TREND_DIRECTION = 'UPTREND'")
                if (not exact_symbols_mode) and 'SIGNAL_SCORE' in available:
                    where_parts.append("NVL(s.SIGNAL_SCORE, 0) >= :min_signal")
                    bind['min_signal'] = min_signal
                if (not exact_symbols_mode) and 'ADX14' in available:
                    where_parts.append("NVL(s.ADX14, 0) >= :min_adx")
                    bind['min_adx'] = min_adx
                if (not exact_symbols_mode) and 'EMA_STACK' in available:
                    if 'ADX14' in available:
                        where_parts.append(
                            "(s.EMA_STACK = 'BULL_STACK' OR (s.EMA_STACK = 'MIXED' AND NVL(s.ADX14,0) >= :mixed_adx_min))"
                        )
                        bind['mixed_adx_min'] = ASURA_MIXED_ADX_MIN
                    else:
                        where_parts.append("s.EMA_STACK = 'BULL_STACK'")
                if (not exact_symbols_mode) and breakout_only and 'BREAKOUT_FLAG' in available:
                    where_parts.append("s.BREAKOUT_FLAG = 'BREAKOUT'")
                if (not exact_symbols_mode) and 'STOP_LOSS' in available and 'TARGET1' in available and 'TARGET2' in available:
                    where_parts.append("(s.STOP_LOSS < s.TARGET1 AND s.STOP_LOSS < s.TARGET2)")
                if status_col and not include_exited:
                    where_parts.append(
                        f"(s.{_safe_identifier(status_col)} IS NULL OR UPPER(TRIM(s.{_safe_identifier(status_col)})) "
                        "NOT IN ('EXITED', 'CLOSED', 'SELL', 'SOLD'))"
                    )
                elif sell_col and not include_exited:
                    where_parts.append(f"s.{_safe_identifier(sell_col)} IS NULL")

                symbol_col = 'SYMBOL' if 'SYMBOL' in available else ('STOCK' if 'STOCK' in available else None)
                name_col = 'STOCK_NAME' if 'STOCK_NAME' in available else None
                if symbols and symbol_col:
                    symbol_bind_names = []
                    for index, symbol_code in enumerate(symbols):
                        bind_name = f"symbol_{index}"
                        bind[bind_name] = symbol_code
                        symbol_bind_names.append(f":{bind_name}")
                    where_parts.append(
                        f"UPPER(TRIM(REGEXP_REPLACE(REGEXP_REPLACE(s.{_safe_identifier(symbol_col)}, '^[^:]+:', ''), '-[^-]+$', ''))) "
                        f"IN ({', '.join(symbol_bind_names)})"
                    )
                if search and (symbol_col or name_col):
                    search_parts = []
                    if symbol_col:
                        search_parts.append(f"UPPER(s.{_safe_identifier(symbol_col)}) LIKE :search")
                    if name_col:
                        search_parts.append(f"UPPER(s.{_safe_identifier(name_col)}) LIKE :search")
                    if search_parts:
                        where_parts.append("(" + " OR ".join(search_parts) + ")")
                        bind['search'] = f"{search.strip().upper()}%"
                where = " WHERE " + " AND ".join(where_parts)

                sort_col = _resolve_sort_column(sort, available)
                if not sort_col:
                    raise RuntimeError('No sortable columns available for Asura source')
                sort_col = _safe_identifier(sort_col)
                order_by = f"{sort_col} {sort_dir} NULLS LAST"
                if symbol_col:
                    safe_symbol_col = _safe_identifier(symbol_col)
                    if safe_symbol_col != sort_col:
                        order_by += f", {safe_symbol_col} ASC"

                bind_page = {**bind, 'offset': offset, 'limit': page_size}
                sql = f"""
                  SELECT q.*
                  FROM (
                    SELECT
                      s.*,
                      COUNT(1) OVER () AS TOTAL_COUNT
                    FROM {source} s
                    {where}
                  ) q
                  ORDER BY {order_by}
                  OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY
                """

                cur.arraysize = max(200, page_size)
                cur.prefetchrows = cur.arraysize
                query_started_at = time.perf_counter()
                cur.execute(sql, bind_page)
                cols = [str(d[0]).lower() for d in (cur.description or [])]
                raw_rows = cur.fetchall() or []
                query_elapsed_ms = int((time.perf_counter() - query_started_at) * 1000)
                items = []
                total = 0
                if raw_rows:
                    total_idx = cols.index('total_count') if 'total_count' in cols else -1
                    if total_idx >= 0:
                        try:
                            total = int(raw_rows[0][total_idx] or 0)
                        except Exception:
                            total = 0
                elif offset > 0:
                    # Preserve total-count semantics for high page numbers when the page slice is empty.
                    count_sql = f"SELECT COUNT(*) AS CNT FROM {source} s {where}"
                    count_started_at = time.perf_counter()
                    cur.execute(count_sql, bind)
                    total = int((cur.fetchone() or [0])[0] or 0)
                    count_elapsed_ms = int((time.perf_counter() - count_started_at) * 1000)

                row_materialize_started_at = time.perf_counter()
                for raw in raw_rows:
                    row = dict(zip(cols, raw))
                    symbol = _first_of(row, 'symbol', 'stock')
                    stock_name = _first_of(row, 'stock_name', 'stock', 'symbol')
                    trade_date_val = _first_of(row, 'trade_date', 'trading_date', 'buying_date', 'run_date')
                    buying_date_val = _first_of(row, 'buying_date', 'trade_date', 'trading_date', 'run_date')
                    price_val = _first_of(row, 'close_price', 'price', 'buying_price', 'ltp', 'last_price', 'close')
                    volume_val = _first_of(row, 'volume', 'tottrdqty', 'tot_trdqty', 'qty', 'deliv_qty')
                    rsi_val = _first_of(row, 'rsi14', 'rsi')
                    atr_val = _first_of(row, 'atr14', 'atr')
                    breakout_val = _first_of(row, 'breakout_flag', 'breakout')
                    entry_price_val = _first_of(row, 'entry_price', 'buying_price', 'price', 'close_price')

                    price = _to_float(price_val)
                    ema20_val = _to_float(row.get('ema20'))
                    ema50_val = _to_float(row.get('ema50'))
                    ema100_val = _to_float(row.get('ema100'))
                    ema200_val = _to_float(row.get('ema200'))

                    item = {
                        'symbol': symbol,
                        'stockName': stock_name or symbol,
                        'tradeDate': _to_iso_date(trade_date_val),
                        'price': price,
                        'volume': _to_float(volume_val),
                        'move1dPct': _to_float(row.get('move_1d_pct')),
                        'move1wPct': _to_float(row.get('move_1w_pct')),
                        'move1mPct': _to_float(row.get('move_1m_pct')),
                        'avgVolume20': _to_float(row.get('avg_volume20')),
                        'volumeRatio20': _to_float(_first_of(row, 'volume_ratio20', 'volume_ratio')),
                        'high52w': _to_float(row.get('high_52w')),
                        'low52w': _to_float(row.get('low_52w')),
                        'ath': _to_float(row.get('ath')),
                        'high1y': _to_float(row.get('high_1y')),
                        'high2y': _to_float(row.get('high_2y')),
                        'ema20': ema20_val,
                        'ema50': ema50_val,
                        'ema100': ema100_val,
                        'ema200': ema200_val,
                        'ema20Flag': _ema_flag(price, ema20_val, '20'),
                        'ema50Flag': _ema_flag(price, ema50_val, '50'),
                        'ema100Flag': _ema_flag(price, ema100_val, '100'),
                        'ema200Flag': _ema_flag(price, ema200_val, '200'),
                        'ema50SlopePct10d': _to_float(row.get('ema50_slopepct_10d')),
                        'rsi': _to_float(rsi_val),
                        'macdLine': _to_float(row.get('macd_line')),
                        'macdSignal': _to_float(row.get('macd_signal')),
                        'macdHist': _to_float(row.get('macd_hist')),
                        'atr': _to_float(atr_val),
                        'atrPct': _to_float(row.get('atr_pct')),
                        'adx14': _to_float(row.get('adx14')),
                        'diPlus14': _to_float(row.get('di_plus14')),
                        'diMinus14': _to_float(row.get('di_minus14')),
                        'trendDirection': row.get('trend_direction'),
                        'emaStack': row.get('ema_stack'),
                        'support': _to_float(row.get('support_price')),
                        'resistance': _to_float(row.get('resistance_price')),
                        'distToSupportPct': _to_float(row.get('dist_to_support_pct')),
                        'distToResistancePct': _to_float(row.get('dist_to_resistance_pct')),
                        'supportStrength': _to_float(row.get('support_strength')),
                        'resistanceStrength': _to_float(row.get('resistance_strength')),
                        'levelScore': _to_float(row.get('level_score')),
                        'levelProximityScore': _to_float(row.get('level_proximity_score')),
                        'levelTouchScore': _to_float(row.get('level_touch_score')),
                        'levelRecencyScore': _to_float(row.get('level_recency_score')),
                        'levelConfluenceScore': _to_float(row.get('level_confluence_score')),
                        'breakoutFlag': breakout_val,
                        'retestReady': _to_bool_flag(row.get('retest_ready')),
                        'setupType': row.get('setup_type') or 'PULLBACK',
                        'entryPrice': _to_float(entry_price_val),
                        'stopLoss': _to_float(row.get('stop_loss')),
                        'target1': _to_float(row.get('target1')),
                        'target2': _to_float(row.get('target2')),
                        'rr1': _to_float(row.get('rr_1')),
                        'rr2': _to_float(row.get('rr_2')),
                        'signalScore': _to_float(row.get('signal_score')),
                        'buyingDate': _to_iso_date(buying_date_val),
                        'sellingDate': _to_iso_date(_first_of(row, 'selling_date', 'exit_date', 'sell_date')),
                        'stopLossPct': _to_float(row.get('stop_loss_pct')),
                        'target1Pct': _to_float(row.get('target1_pct')),
                        'target2Pct': _to_float(row.get('target2_pct')),
                        'backtestingDate': _to_iso_date(_first_of(row, 'backtesting_date', 'run_date')),
                        'status': row.get('status'),
                        'exitPrice': _to_float(row.get('exit_price')),
                        'exitReason': row.get('exit_reason'),
                        'target1HitFlag': row.get('target1_hit_flag'),
                    }
                    if latest_ltc_date_key:
                        item['ltcDate'] = latest_ltc_date_key
                        item['ltc_date'] = latest_ltc_date_key
                        item['latestLtcDate'] = latest_ltc_date_key
                    items.append(_apply_master_score_fields(item))
                row_materialize_ms = int((time.perf_counter() - row_materialize_started_at) * 1000)
    except RuntimeError as exc:
        if 'Asura source not found' in str(exc):
            raise
        raise

    ath_stats = {'elapsed_ms': 0, 'cache_hit': False}
    if apply_authoritative_ath:
        ath_stats = _apply_authoritative_ath(items, endpoint='/api/asura')
    ath_elapsed_ms = int((ath_stats or {}).get('elapsed_ms') or 0)
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    _logger.info(
        'asura_query source=%s page=%s page_size=%s rows=%s total=%s acquire_ms=%s source_ms=%s query_ms=%s count_ms=%s row_ms=%s ath_ms=%s ath_cache_hit=%s elapsed_ms=%s conditions_only=%s include_exited=%s start_date=%s cutoff_date=%s symbols=%s search=%s',
        source,
        page,
        page_size,
        len(items),
        total,
        connection_acquire_ms,
        source_resolve_ms,
        query_elapsed_ms,
        count_elapsed_ms,
        row_materialize_ms,
        ath_elapsed_ms,
        int(bool((ath_stats or {}).get('cache_hit'))),
        elapsed_ms,
        int(conditions_only),
        int(include_exited),
        trade_start_date.isoformat() if isinstance(trade_start_date, date) else None,
        trade_cutoff_date.isoformat() if isinstance(trade_cutoff_date, date) else None,
        len(symbols or ()),
        bool(search),
    )

    now = datetime.utcnow().isoformat() + 'Z'
    return {
        'items': items,
        'total': total,
        'page': page,
        'page_size': page_size,
        'generated_at': now,
        'athSource': 'NSE_NIFTY500_DAILY_RAW_DATA_DEV',
        'ltcDate': latest_ltc_date_key,
        'maxLtcDate': latest_ltc_date_key,
        'latestLtcDate': latest_ltc_date_key,
        'meta': {
            'db_time_ms': query_elapsed_ms + count_elapsed_ms,
            'connection_acquire_ms': connection_acquire_ms,
            'source_resolve_ms': source_resolve_ms,
            'query_time_ms': query_elapsed_ms,
            'count_time_ms': count_elapsed_ms,
            'serialization_time_ms': row_materialize_ms,
            'ath_time_ms': ath_elapsed_ms,
            'page': page,
            'page_size': page_size,
            'snapshot_used': False,
            'source': 'db',
            'total': total,
            'latest_ltc_date': latest_ltc_date_key,
        },
    }


def _snake_row_to_item(row: Dict[str, Any]) -> Dict[str, Any]:
    price = _to_float(row.get('close_price'))
    ema20_val = _to_float(row.get('ema20'))
    ema50_val = _to_float(row.get('ema50'))
    ema100_val = _to_float(row.get('ema100'))
    ema200_val = _to_float(row.get('ema200'))
    item = {
        'symbol': row.get('symbol'),
        'stockName': row.get('stock_name') or row.get('symbol'),
        'tradeDate': _to_iso_date(row.get('trade_date')),
        'price': price,
        'volume': _to_float(row.get('volume')),
        'move1dPct': _to_float(row.get('move_1d_pct')),
        'move1wPct': _to_float(row.get('move_1w_pct')),
        'move1mPct': _to_float(row.get('move_1m_pct')),
        'avgVolume20': _to_float(row.get('avg_volume20')),
        'volumeRatio20': _to_float(row.get('volume_ratio20')),
        'high52w': _to_float(row.get('high_52w')),
        'low52w': _to_float(row.get('low_52w')),
        'ath': _to_float(row.get('ath')),
        'high1y': _to_float(row.get('high_1y')),
        'high2y': _to_float(row.get('high_2y')),
        'ema20': ema20_val,
        'ema50': ema50_val,
        'ema100': ema100_val,
        'ema200': ema200_val,
        'ema20Flag': _ema_flag(price, ema20_val, '20'),
        'ema50Flag': _ema_flag(price, ema50_val, '50'),
        'ema100Flag': _ema_flag(price, ema100_val, '100'),
        'ema200Flag': _ema_flag(price, ema200_val, '200'),
        'ema50SlopePct10d': _to_float(row.get('ema50_slopepct_10d')),
        'rsi': _to_float(row.get('rsi14')),
        'macdLine': _to_float(row.get('macd_line')),
        'macdSignal': _to_float(row.get('macd_signal')),
        'macdHist': _to_float(row.get('macd_hist')),
        'atr': _to_float(row.get('atr14')),
        'atrPct': _to_float(row.get('atr_pct')),
        'adx14': _to_float(row.get('adx14')),
        'diPlus14': _to_float(row.get('di_plus14')),
        'diMinus14': _to_float(row.get('di_minus14')),
        'trendDirection': row.get('trend_direction'),
        'emaStack': row.get('ema_stack'),
        'support': _to_float(row.get('support_price')),
        'resistance': _to_float(row.get('resistance_price')),
        'distToSupportPct': _to_float(row.get('dist_to_support_pct')),
        'distToResistancePct': _to_float(row.get('dist_to_resistance_pct')),
        'supportStrength': _to_float(row.get('support_strength')),
        'resistanceStrength': _to_float(row.get('resistance_strength')),
        'levelScore': _to_float(row.get('level_score')),
        'levelProximityScore': _to_float(row.get('level_proximity_score')),
        'levelTouchScore': _to_float(row.get('level_touch_score')),
        'levelRecencyScore': _to_float(row.get('level_recency_score')),
        'levelConfluenceScore': _to_float(row.get('level_confluence_score')),
        'breakoutFlag': row.get('breakout_flag'),
        'retestReady': bool(int(row.get('retest_ready') or 0)),
        'setupType': row.get('setup_type') or 'PULLBACK',
        'entryPrice': _to_float(row.get('entry_price')),
        'stopLoss': _to_float(row.get('stop_loss')),
        'target1': _to_float(row.get('target1')),
        'target2': _to_float(row.get('target2')),
        'rr1': _to_float(row.get('rr_1')),
        'rr2': _to_float(row.get('rr_2')),
        'signalScore': _to_float(row.get('signal_score')),
        'buyingDate': _to_iso_date(row.get('trade_date')),
        'sellingDate': None,
        'stopLossPct': _calc_stop_loss_pct(row.get('entry_price'), row.get('stop_loss')),
        'target1Pct': _calc_target_pct(row.get('entry_price'), row.get('target1')),
        'target2Pct': _calc_target_pct(row.get('entry_price'), row.get('target2')),
        'backtestingDate': ASURA_BACKTESTING_DATE,
    }
    return _apply_master_score_fields(item)


def _fallback_snapshot() -> Dict[str, Any]:
    cache_key = 'fallback:asura_snapshot'
    cached = _fallback_snapshot_cache.get(cache_key)
    expected_ath_source = 'NSE_NIFTY500_DAILY_RAW_DATA_DEV'
    if cached is not None:
        cached_source = str(cached.get('athSource') or '').strip().upper() if isinstance(cached, dict) else ''
        if cached_source == expected_ath_source:
            return {**cached, 'cached': True}
        log_stale_snapshot_warning(endpoint='/api/asura/fallback', source='fallback-cache')
    if not _FALLBACK_READY:
        return _compute_local_snapshot(timeframe='daily', trade_start_date=None, trade_cutoff_date=None)

    try:
        with pool.acquire() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT MAX(TRADING_DATE) FROM {_fallback_source_view}")
                scan_row = cur.fetchone()
                scan_dt = scan_row[0] if scan_row else None
                if scan_dt is None:
                    raise RuntimeError(f'{_fallback_source_view} has no rows')
                if isinstance(scan_dt, datetime):
                    scan_date = scan_dt.date()
                elif isinstance(scan_dt, date):
                    scan_date = scan_dt
                else:
                    raise RuntimeError('Invalid scan date type from OHLCV view')

                start_date = scan_date - __import__('datetime').timedelta(days=max(200, _fallback_lookback_days))

                cur.execute(
                    f"""
                    SELECT SYMBOL, TRADING_DATE, OPEN, HIGH, LOW, PRICE_FOR_EMA AS CLOSE_PRICE, VOLUME
                    FROM {_fallback_source_view}
                    WHERE TRADING_DATE >= :start_date
                      AND TRADING_DATE <= :end_date
                    ORDER BY SYMBOL, TRADING_DATE
                    """,
                    {'start_date': start_date, 'end_date': scan_date},
                )

                history: Dict[str, list[Any]] = {}
                cur.arraysize = 5000
                cur.prefetchrows = cur.arraysize
                for sym, dt_val, op, hi, lo, cl, vol in cur:
                    if not sym:
                        continue
                    symbol = str(sym).upper()
                    trade_dt = dt_val.date() if isinstance(dt_val, datetime) else dt_val
                    open_val = _to_float(op)
                    high_val = _to_float(hi)
                    low_val = _to_float(lo)
                    close_val = _to_float(cl)
                    vol_val = _to_float(vol)
                    bar = _OhlcvBar(
                        trade_date=trade_dt,
                        open=open_val if open_val is not None else float('nan'),
                        high=high_val if high_val is not None else float('nan'),
                        low=low_val if low_val is not None else float('nan'),
                        close=close_val if close_val is not None else float('nan'),
                        volume=vol_val if vol_val is not None else float('nan'),
                    )
                    history.setdefault(symbol, []).append(bar)

        ath_map: Dict[str, float] = {}
        if history:
            try:
                ath_records = get_all_time_high_for_symbols(
                    list(history.keys()),
                    include_date=False,
                    endpoint='/api/asura/fallback',
                )
                for symbol, record in ath_records.items():
                    ath_value = _to_float(record.get('ath'))
                    if ath_value is not None:
                        ath_map[symbol] = ath_value
            except Exception as exc:
                _logger.exception('[ATH] fallback ATH map build failed endpoint=/api/asura/fallback error=%s', exc)

        computed_items: list[Dict[str, Any]] = []
        skipped = 0
        for symbol, bars in history.items():
            if not bars or bars[-1].trade_date != scan_date:
                continue
            row = _compute_latest_scan_row(symbol=symbol, bars=bars, ath=ath_map.get(symbol))
            if row is None:
                skipped += 1
                continue
            computed_items.append(_snake_row_to_item(row))

        _apply_authoritative_ath(computed_items, endpoint='/api/asura/fallback')

        payload = {
            'items': computed_items,
            'total': len(computed_items),
            'generated_at': datetime.utcnow().isoformat() + 'Z',
            'as_of_date': scan_date.isoformat(),
            'skipped': skipped,
            'athSource': 'NSE_NIFTY500_DAILY_RAW_DATA_DEV',
        }
        _fallback_snapshot_cache.set(cache_key, payload)
        return payload
    except Exception:
        _logger.exception('Asura fallback compute failed; using local snapshot')
        return _compute_local_snapshot(timeframe='daily', trade_start_date=None, trade_cutoff_date=None)


def _apply_query_filters(
    items: list[Dict[str, Any]],
    *,
    min_signal: float,
    min_adx: float,
    breakout_only: bool,
    sort: str,
    order: str,
    search: Optional[str],
    symbols: tuple[str, ...],
    page: int,
    page_size: int,
) -> Dict[str, Any]:
    exact_symbols_mode = bool(symbols)
    filtered: list[Dict[str, Any]] = []
    items = list(items or [])
    marketcap_sort = sort in _MARKETCAP_SORT_FIELDS
    if marketcap_sort:
        try:
            items = nse_mcap_svc.enrich_rows_with_marketcap_index(items)
        except Exception:
            _logger.exception('asura_marketcap_sort_enrich_failed sort=%s', sort)
    search_upper = search.upper() if search else None
    symbol_filter = set(symbols or ())
    for item in items:
        if symbol_filter and _normalize_symbol_code(item.get('symbol')) not in symbol_filter:
            continue
        if (not exact_symbols_mode) and item.get('trendDirection') != 'UPTREND':
            continue
        stop_loss = item.get('stopLoss')
        target1 = item.get('target1')
        target2 = item.get('target2')
        if (not exact_symbols_mode) and stop_loss is not None and target1 is not None and target2 is not None:
            try:
                if float(stop_loss) >= float(target1) or float(stop_loss) >= float(target2):
                    continue
            except Exception:
                pass
        signal_score = float(item.get('signalScore') or 0.0)
        if (not exact_symbols_mode) and signal_score < min_signal:
            continue
        adx14 = float(item.get('adx14') or 0.0)
        if (not exact_symbols_mode) and adx14 < min_adx:
            continue
        ema_stack = item.get('emaStack')
        if (not exact_symbols_mode) and ema_stack not in ('BULL_STACK', 'MIXED'):
            continue
        if (not exact_symbols_mode) and ema_stack == 'MIXED' and adx14 < ASURA_MIXED_ADX_MIN:
            continue
        if (not exact_symbols_mode) and breakout_only and item.get('breakoutFlag') != 'BREAKOUT':
            continue
        if search_upper:
            symbol = str(item.get('symbol') or '').upper()
            name = str(item.get('stockName') or '').upper()
            if not (symbol.startswith(search_upper) or name.startswith(search_upper)):
                continue
        filtered.append(item)

    sort_key = sort
    sort_field = {
        'symbol': 'symbol',
        'stock_name': 'stockName',
        'trade_date': 'tradeDate',
        'buying_date': 'buyingDate',
        'price': 'price',
        'volume': 'volume',
        'move_1d_pct': 'move1dPct',
        'move_1w_pct': 'move1wPct',
        'move_1m_pct': 'move1mPct',
        'avg_volume20': 'avgVolume20',
        'volume_ratio': 'volumeRatio20',
        'volume_ratio20': 'volumeRatio20',
        'high_52w': 'high52w',
        'low_52w': 'low52w',
        'ath': 'ath',
        'high_1y': 'high1y',
        'high_2y': 'high2y',
        'ema20': 'ema20',
        'ema50': 'ema50',
        'ema100': 'ema100',
        'ema200': 'ema200',
        'ema50_slopepct_10d': 'ema50SlopePct10d',
        'rsi': 'rsi',
        'rsi14': 'rsi',
        'macd_line': 'macdLine',
        'macd_signal': 'macdSignal',
        'macd_hist': 'macdHist',
        'atr14': 'atr',
        'atr_pct': 'atrPct',
        'adx': 'adx14',
        'adx14': 'adx14',
        'di_plus14': 'diPlus14',
        'di_minus14': 'diMinus14',
        'trend_direction': 'trendDirection',
        'ema_stack': 'emaStack',
        'support_price': 'support',
        'resistance_price': 'resistance',
        'dist_to_support_pct': 'distToSupportPct',
        'dist_to_resistance_pct': 'distToResistancePct',
        'support_strength': 'supportStrength',
        'resistance_strength': 'resistanceStrength',
        'level_score': 'levelScore',
        'level_proximity_score': 'levelProximityScore',
        'level_touch_score': 'levelTouchScore',
        'level_recency_score': 'levelRecencyScore',
        'level_confluence_score': 'levelConfluenceScore',
        'breakout_flag': 'breakoutFlag',
        'retest_ready': 'retestReady',
        'setup_type': 'setupType',
        'entry_price': 'entryPrice',
        'stop_loss': 'stopLoss',
        'target1': 'target1',
        'target2': 'target2',
        'rr_1': 'rr1',
        'rr_2': 'rr2',
        'signal_score': 'signalScore',
        'index': 'INDEX',
        'mcap': 'mcapSort',
        'mcap_rank': 'mcapRankSort',
    }.get(sort_key, 'signalScore')
    reverse = order == 'desc'

    string_fields = {'symbol', 'stockName', 'tradeDate', 'buyingDate', 'sellingDate', 'trendDirection', 'emaStack', 'breakoutFlag', 'setupType'}
    bool_fields = {'retestReady'}

    def _sort_value(it: Dict[str, Any]):
        val = it.get(sort_field)
        if sort_field in bool_fields:
            missing = 1 if val is None else 0
            return (missing, 1 if bool(val) else 0)
        if sort_field in string_fields:
            text = '' if val is None else str(val).strip().upper()
            missing = 1 if not text else 0
            return (missing, text)
        try:
            if val is None:
                return (1, 0.0)
            num = float(val)
            return (0, num)
        except Exception:
            return (1, 0.0)

    # Match DB behavior: primary sort by metric, tie-break by SYMBOL ASC.
    filtered.sort(key=lambda it: str(it.get('symbol') or '').upper())
    filtered.sort(key=_sort_value, reverse=reverse)

    total = len(filtered)
    pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(pages, page))
    start = (page - 1) * page_size
    end = start + page_size
    paged_items = filtered[start:end]
    if not marketcap_sort:
        try:
            paged_items = nse_mcap_svc.enrich_rows_with_marketcap_index(paged_items)
        except Exception:
            _logger.exception('asura_marketcap_page_enrich_failed sort=%s', sort)
    return {
        'items': paged_items,
        'total': total,
        'page': page,
        'page_size': page_size,
    }


def _with_response_meta(
    payload: Dict[str, Any],
    *,
    load_time_ms: int,
    page: int,
    page_size: int,
    source: str,
    snapshot_used: bool,
    sync_skipped: bool,
    stale_reasons: Optional[list[str]] = None,
) -> Dict[str, Any]:
    response = dict(payload or {})
    meta = dict(response.get('meta') or {})
    meta.update({
        'load_time_ms': int(load_time_ms),
        'page': page,
        'page_size': page_size,
        'snapshot_used': bool(snapshot_used),
        'source': source,
        'sync_skipped': bool(sync_skipped),
        'total': int(response.get('total') or 0),
    })
    if stale_reasons is not None:
        meta['stale_reasons'] = list(stale_reasons)
    response['meta'] = meta
    return response


def _build_local_snapshot_response(
    snapshot: Dict[str, Any],
    *,
    timeframe: str,
    min_signal: float,
    min_adx: float,
    breakout_only: bool,
    sort: str,
    order: str,
    page: int,
    page_size: int,
    search: Optional[str],
    symbols: tuple[str, ...],
    refreshing: bool,
    stale_reasons: list[str],
    apply_authoritative_ath: bool,
) -> Dict[str, Any]:
    filter_started_at = time.perf_counter()
    query_payload = _apply_query_filters(
        list(snapshot.get('items') or []),
        min_signal=min_signal,
        min_adx=min_adx,
        breakout_only=breakout_only,
        sort=sort,
        order=order,
        search=search,
        symbols=symbols,
        page=page,
        page_size=page_size,
    )
    filter_elapsed_ms = int((time.perf_counter() - filter_started_at) * 1000)
    ath_stats = {'elapsed_ms': 0, 'cache_hit': False}
    if apply_authoritative_ath:
        ath_stats = _apply_authoritative_ath(query_payload.get('items') or [], endpoint='/api/asura/local-query')
    return {
        **query_payload,
        'generated_at': snapshot.get('generated_at'),
        'cached': True,
        'refreshing': refreshing,
        'fallback': True,
        'local': True,
        'as_of_date': snapshot.get('as_of_date'),
        'athSource': 'NSE_NIFTY500_DAILY_RAW_DATA_DEV',
        'meta': {
            'db_time_ms': 0,
            'filter_time_ms': filter_elapsed_ms,
            'ath_time_ms': int((ath_stats or {}).get('elapsed_ms') or 0),
            'page': page,
            'page_size': page_size,
            'snapshot_used': True,
            'source': 'local_snapshot',
            'stale_reasons': list(stale_reasons),
            'timeframe': timeframe,
            'total': int(query_payload.get('total') or 0),
        },
    }


def _serve_local_snapshot_fast_path(
    *,
    timeframe: str,
    min_signal: float,
    min_adx: float,
    breakout_only: bool,
    sort: str,
    order: str,
    page: int,
    page_size: int,
    search: Optional[str],
    symbols: tuple[str, ...],
    force_refresh: bool,
    apply_authoritative_ath: bool,
) -> Dict[str, Any]:
    snapshot, stale_reasons = _load_local_snapshot_payload(timeframe)
    if snapshot is not None:
        refreshing = bool(force_refresh or stale_reasons)
        if refreshing:
            if stale_reasons:
                log_stale_snapshot_warning(endpoint='/api/asura', source='snapshot_' + ','.join(stale_reasons))
            _schedule_local_snapshot_refresh(timeframe)
        return _build_local_snapshot_response(
            snapshot,
            timeframe=timeframe,
            min_signal=min_signal,
            min_adx=min_adx,
            breakout_only=breakout_only,
            sort=sort,
            order=order,
            page=page,
            page_size=page_size,
            search=search,
            symbols=symbols,
            refreshing=refreshing,
            stale_reasons=stale_reasons,
            apply_authoritative_ath=apply_authoritative_ath,
        )

    _schedule_local_snapshot_refresh(timeframe)
    warmed = _wait_for_local_snapshot(timeframe, _ASYNC_COLD_WAIT_MS)
    if warmed is not None:
        return _build_local_snapshot_response(
            warmed,
            timeframe=timeframe,
            min_signal=min_signal,
            min_adx=min_adx,
            breakout_only=breakout_only,
            sort=sort,
            order=order,
            page=page,
            page_size=page_size,
            search=search,
            symbols=symbols,
            refreshing=False,
            stale_reasons=[],
            apply_authoritative_ath=apply_authoritative_ath,
        )

    return _local_warming_payload(
        timeframe=timeframe,
        page=page,
        page_size=page_size,
        stale_reasons=['cold_start'],
    )


def _get_runtime_agent_defaults() -> Dict[str, Any]:
    defaults: Dict[str, Any] = {
        'min_signal': ASURA_DEFAULT_MIN_SIGNAL,
        'min_adx': ASURA_DEFAULT_MIN_ADX,
        'breakout_only': False,
    }
    try:
        params = get_strategy_params('asura')
    except Exception:
        _logger.exception('Failed to load Asura strategy params; using env defaults.')
        return defaults

    min_signal = _to_float(params.get('min_signal'))
    if min_signal is not None:
        defaults['min_signal'] = max(0.0, min(100.0, min_signal))
    min_adx = _to_float(params.get('min_adx'))
    if min_adx is not None:
        defaults['min_adx'] = max(0.0, min(100.0, min_adx))
    defaults['breakout_only'] = _to_bool_flag(params.get('breakout_only'))
    return defaults


@bp.get('/api/asura')
def api_asura():
    api_started_at = time.perf_counter()
    request_id = request.headers.get('X-Request-ID') or request.headers.get('X-Request-Id') or str(uuid.uuid4())
    runtime_defaults = _get_runtime_agent_defaults()
    timeframe = (request.args.get('timeframe') or 'daily').strip().lower()
    min_signal = _parse_float(request.args.get('min_signal'), float(runtime_defaults['min_signal']), 0.0, 100.0)
    min_adx = _parse_float(request.args.get('min_adx'), float(runtime_defaults['min_adx']), 0.0, 100.0)
    breakout_arg = request.args.get('breakout_only')
    breakout_only = _parse_bool(breakout_arg) if breakout_arg is not None else bool(runtime_defaults['breakout_only'])
    sort = (request.args.get('sort') or 'signal_score').strip().lower()
    order = (request.args.get('order') or 'desc').strip().lower()
    page = _parse_int(request.args.get('page'), 1, 1, 1000000)
    page_size = _parse_int(request.args.get('page_size'), ASURA_DEFAULT_PAGE_SIZE, 1, ASURA_MAX_PAGE_SIZE)
    search = (request.args.get('search') or '').strip()
    search = search if search else None
    symbols = _parse_symbol_filters((request.args.get('symbols') or request.args.get('symbol') or '').strip())
    conditions_only = _parse_bool(request.args.get('conditions_only'))
    include_exited = _parse_bool(request.args.get('include_exited'))
    trade_start_raw = (request.args.get('start_date') or '').strip()
    trade_cutoff_raw = (request.args.get('cutoff_date') or '').strip()
    try:
        trade_start_date = datetime.strptime(trade_start_raw, '%Y-%m-%d').date() if trade_start_raw else None
        trade_cutoff_date = datetime.strptime(trade_cutoff_raw, '%Y-%m-%d').date() if trade_cutoff_raw else None
    except ValueError:
        return jsonify({'detail': 'Dates must be supplied as YYYY-MM-DD'}), 400
    latest_ltc_date = (
        _fetch_latest_ltc_date_key()
        if timeframe == 'daily' and trade_start_date is None and trade_cutoff_date is None
        else None
    )
    strategy_sync = None
    strategy_sync_error = None

    symbol_lookup_mode = bool(symbols)

    key_raw = (
        f"{timeframe}|{min_signal}|{min_adx}|{int(breakout_only)}|"
        f"{sort}|{order}|{page}|{page_size}|{search or ''}|"
        f"{','.join(symbols)}|"
        f"{int(conditions_only)}|{int(include_exited)}|"
        f"{trade_start_raw}|{trade_cutoff_raw}|{latest_ltc_date or ''}"
    )
    cache_key = "asura:" + hashlib.sha256(key_raw.encode('utf-8')).hexdigest()
    cached = None if symbol_lookup_mode else _cache.get(cache_key)
    expected_ath_source = 'NSE_NIFTY500_DAILY_RAW_DATA_DEV'
    if isinstance(cached, dict):
        cached_source = str(cached.get('athSource') or '').strip().upper()
        if cached_source != expected_ath_source:
            log_stale_snapshot_warning(endpoint='/api/asura', source='cache')
            cached = None
    force_refresh = request.args.get('refresh') in ('1', 'true', 'yes')
    if force_refresh:
        cached = None
    skip_sync_requested = _parse_bool(request.args.get('skip_sync'))
    skip_sync = skip_sync_requested and not force_refresh
    run_strategy_sync = _parse_bool(request.args.get('track_trades')) or force_refresh
    if symbols:
        run_strategy_sync = False
    elif skip_sync:
        run_strategy_sync = False
    elif not run_strategy_sync and ASURA_AUTO_SYNC and page == 1:
        run_strategy_sync = True
    _logger.info(
        'asura_api_begin request_id=%s timeframe=%s force_refresh=%s skip_sync=%s page=%s page_size=%s sort=%s order=%s search=%s conditions_only=%s include_exited=%s symbols=%s',
        request_id,
        timeframe,
        int(force_refresh),
        int(skip_sync),
        page,
        page_size,
        sort,
        order,
        bool(search),
        int(conditions_only),
        int(include_exited),
        len(symbols or ()),
    )
    use_local_snapshot_fast_path = False
    if skip_sync and trade_start_date is None and trade_cutoff_date is None and timeframe in _LOCAL_TIMEFRAMES:
        try:
            use_local_snapshot_fast_path = timeframe != 'daily' or (not _has_precomputed_source())
        except Exception:
            _logger.exception('Asura source-availability check failed request_id=%s', request_id)
    _logger.info(
        'asura_api_sync_decision request_id=%s decision_ms=%s skip_sync=%s force_refresh=%s run_strategy_sync=%s local_snapshot_fast_path=%s',
        request_id,
        int((time.perf_counter() - api_started_at) * 1000),
        int(skip_sync),
        int(force_refresh),
        int(run_strategy_sync),
        int(use_local_snapshot_fast_path),
    )
    if use_local_snapshot_fast_path:
        payload = _serve_local_snapshot_fast_path(
            timeframe=timeframe,
            min_signal=min_signal,
            min_adx=min_adx,
            breakout_only=breakout_only,
            sort=sort,
            order=order,
            page=page,
            page_size=page_size,
            search=search,
            symbols=symbols,
            force_refresh=force_refresh,
            apply_authoritative_ath=not skip_sync,
        )
        payload_meta = payload.get('meta') if isinstance(payload, dict) else {}
        source_name = str((payload_meta or {}).get('source') or 'local_snapshot')
        stale_reasons = list((payload_meta or {}).get('stale_reasons') or [])
        response_payload = _with_response_meta(
            payload,
            load_time_ms=int((time.perf_counter() - api_started_at) * 1000),
            page=page,
            page_size=page_size,
            source=source_name,
            snapshot_used=source_name != 'warming',
            sync_skipped=skip_sync,
            stale_reasons=stale_reasons,
        )
        _logger.info(
            'asura_api request_ms=%s request_id=%s cached=%s refreshing=%s skip_sync=%s page=%s page_size=%s timeframe=%s sort=%s order=%s search=%s conditions_only=%s include_exited=%s symbols=%s source=%s',
            int((time.perf_counter() - api_started_at) * 1000),
            request_id,
            int(bool(response_payload.get('cached'))),
            int(bool(response_payload.get('refreshing'))),
            int(skip_sync),
            page,
            page_size,
            timeframe,
            sort,
            order,
            bool(search),
            int(conditions_only),
            int(include_exited),
            len(symbols or ()),
            source_name,
        )
        _log_asura_payload_diagnostics(
            response_payload,
            cached=bool(response_payload.get('cached')),
            refreshing=bool(response_payload.get('refreshing')),
        )
        return jsonify(response_payload)
    if cached is not None and force_refresh:
        background_refresh(
            _cache,
            cache_key,
            lambda: _compute_payload(
                timeframe=timeframe,
                min_signal=min_signal,
                min_adx=min_adx,
                breakout_only=breakout_only,
                sort=sort,
                order=order,
                page=page,
                page_size=page_size,
                search=search,
                symbols=symbols,
                conditions_only=conditions_only,
                include_exited=include_exited,
                trade_start_date=trade_start_date,
                trade_cutoff_date=trade_cutoff_date,
                apply_authoritative_ath=not skip_sync,
                latest_ltc_date=latest_ltc_date,
            ),
        )
        payload = {**cached, 'cached': True, 'refreshing': True}
        _logger.info(
            'asura_api request_ms=%s cached=1 refreshing=1 skip_sync=%s page=%s page_size=%s timeframe=%s sort=%s order=%s search=%s conditions_only=%s include_exited=%s symbols=%s',
            int((time.perf_counter() - api_started_at) * 1000),
            int(skip_sync),
            page,
            page_size,
            timeframe,
            sort,
            order,
            bool(search),
            int(conditions_only),
            int(include_exited),
            len(symbols or ()),
        )
        response_payload = _with_response_meta(
            _with_marketcap(payload),
            load_time_ms=int((time.perf_counter() - api_started_at) * 1000),
            page=page,
            page_size=page_size,
            source='request_cache',
            snapshot_used=False,
            sync_skipped=skip_sync,
        )
        _log_asura_payload_diagnostics(response_payload, cached=True, refreshing=True)
        return jsonify(response_payload)

    if cached is not None and not force_refresh:
        if run_strategy_sync:
            try:
                strategy_sync = sync_asura_bullish_strategy(
                    timeframe=timeframe,
                    min_signal=min_signal,
                    min_adx=min_adx,
                    breakout_only=breakout_only,
                )
            except Exception as exc:
                strategy_sync_error = str(exc)
                _logger.exception("Asura bullish strategy sync failed")
        payload = {**cached, 'cached': True}
        if strategy_sync is not None:
            payload['strategySync'] = strategy_sync
        if strategy_sync_error:
            payload['strategySyncError'] = strategy_sync_error
        _logger.info(
            'asura_api request_ms=%s cached=1 refreshing=0 skip_sync=%s page=%s page_size=%s timeframe=%s sort=%s order=%s search=%s conditions_only=%s include_exited=%s symbols=%s',
            int((time.perf_counter() - api_started_at) * 1000),
            int(skip_sync),
            page,
            page_size,
            timeframe,
            sort,
            order,
            bool(search),
            int(conditions_only),
            int(include_exited),
            len(symbols or ()),
        )
        response_payload = _with_response_meta(
            _with_marketcap(payload),
            load_time_ms=int((time.perf_counter() - api_started_at) * 1000),
            page=page,
            page_size=page_size,
            source='request_cache',
            snapshot_used=False,
            sync_skipped=skip_sync,
        )
        _log_asura_payload_diagnostics(response_payload, cached=True, refreshing=False)
        return jsonify(response_payload)

    if run_strategy_sync:
        try:
            strategy_sync = sync_asura_bullish_strategy(
                timeframe=timeframe,
                min_signal=min_signal,
                min_adx=min_adx,
                breakout_only=breakout_only,
            )
        except Exception as exc:
            strategy_sync_error = str(exc)
            _logger.exception("Asura bullish strategy sync failed")

    payload = None
    try:
        payload = _compute_payload(
            timeframe=timeframe,
            min_signal=min_signal,
            min_adx=min_adx,
            breakout_only=breakout_only,
            sort=sort,
            order=order,
            page=page,
            page_size=page_size,
            search=search,
            symbols=symbols,
            conditions_only=conditions_only,
            include_exited=include_exited,
            trade_start_date=trade_start_date,
            trade_cutoff_date=trade_cutoff_date,
            apply_authoritative_ath=not skip_sync,
            latest_ltc_date=latest_ltc_date,
        )
    except ValueError as exc:
        return jsonify({'detail': str(exc)}), 400
    except RuntimeError as exc:
        # If the precomputed Asura objects do not exist, fall back to computing
        # the latest scan snapshot from the OHLCV view (slower, but unblocks UI).
        msg = str(exc)
        if 'Asura source not found' not in msg:
            _logger.exception('Asura request failed')
            return jsonify({'detail': msg}), 500

        try:
            snapshot = _fallback_snapshot()
            base_items = list(snapshot.get('items') or [])
            query_payload = _apply_query_filters(
                base_items,
                min_signal=min_signal,
                min_adx=min_adx,
                breakout_only=breakout_only,
                sort=sort,
                order=order,
                search=search,
                symbols=symbols,
                page=page,
                page_size=page_size,
            )
            payload = {
                **query_payload,
                'generated_at': snapshot.get('generated_at'),
                'cached': bool(snapshot.get('cached')),
                'fallback': True,
                'as_of_date': snapshot.get('as_of_date'),
                'athSource': 'NSE_NIFTY500_DAILY_RAW_DATA_DEV',
            }
        except Exception as inner:  # pragma: no cover
            _logger.exception('Asura fallback compute failed')
            return jsonify({'detail': str(inner)}), 500
    except Exception as exc:  # pragma: no cover
        _logger.exception('Asura request failed')
        return jsonify({'detail': str(exc)}), 500

    if not symbol_lookup_mode:
        _cache.set(cache_key, payload)
    if strategy_sync is not None:
        payload['strategySync'] = strategy_sync
    if strategy_sync_error:
        payload['strategySyncError'] = strategy_sync_error
    _logger.info(
        'asura_api request_ms=%s cached=%s refreshing=0 skip_sync=%s page=%s page_size=%s timeframe=%s sort=%s order=%s search=%s conditions_only=%s include_exited=%s symbols=%s',
        int((time.perf_counter() - api_started_at) * 1000),
        int(bool(payload.get('cached'))),
        int(skip_sync),
        page,
        page_size,
        timeframe,
        sort,
        order,
        bool(search),
        int(conditions_only),
        int(include_exited),
        len(symbols or ()),
    )
    response_payload = _with_response_meta(
        _with_marketcap(payload),
        load_time_ms=int((time.perf_counter() - api_started_at) * 1000),
        page=page,
        page_size=page_size,
        source='db' if not payload.get('local') else 'local_compute',
        snapshot_used=False,
        sync_skipped=skip_sync,
    )
    _log_asura_payload_diagnostics(
        response_payload,
        cached=bool(payload.get('cached')),
        refreshing=False,
    )
    return jsonify(response_payload)


@bp.get('/api/asura/last-buying-date')
def api_asura_last_buying_date():
    table = _safe_identifier(ASURA_BULLISH_TREND_TABLE)
    latest_ltc_date = _fetch_latest_ltc_date_key()
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT MAX(BUYING_DATE) FROM {table}")
                row = cur.fetchone()
        max_buying_date = row[0] if row else None
        return jsonify({
            'status': 'ok',
            'maxBuyingDate': _to_iso_date(max_buying_date),
            'maxLtcDate': latest_ltc_date,
            'latestLtcDate': latest_ltc_date,
        })
    except Exception as exc:
        _logger.exception('Asura last-buying-date query failed')
        return jsonify({
            'status': 'error',
            'message': str(exc),
            'maxBuyingDate': None,
            'maxLtcDate': latest_ltc_date,
            'latestLtcDate': latest_ltc_date,
        }), 500


@bp.post('/api/asura/insert')
def api_asura_insert():
    correlation_id = request.headers.get('X-Correlation-Id') or str(uuid.uuid4())
    payload = request.get_json(silent=True) or {}
    raw_items = payload if isinstance(payload, list) else payload.get('rows') if isinstance(payload, dict) else None
    if isinstance(raw_items, list) and raw_items:
        raw = raw_items[0] if isinstance(raw_items[0], dict) else None
        if raw:
            sample = {
                'stock': raw.get('stock') or raw.get('symbol'),
                'buying_date': raw.get('buying_date') or raw.get('trade_date') or raw.get('tradeDate'),
                'buying_price': raw.get('buying_price') or raw.get('price') or raw.get('entryPrice'),
                'ema20': raw.get('ema20'),
                'ema50': raw.get('ema50'),
                'ema100': raw.get('ema100'),
                'ema200': raw.get('ema200'),
            }
            _logger.info('Asura insert payload sample correlationId=%s sample=%s', correlation_id, sample)
    rows, skipped, errors = _normalize_insert_rows(payload)
    if not rows:
        return jsonify({
            'ok': False,
            'correlationId': correlation_id,
            'insertedCount': 0,
            'skippedCount': skipped,
            'errors': errors,
            'detail': 'No valid rows to insert.',
        }), 400

    table = _safe_identifier(ASURA_BULLISH_TREND_TABLE)
    inserted = 0
    try:
        with pool.acquire() as conn:
            rows = _enrich_rows_with_ema(conn, rows)
            rows = _normalize_ema_periods(rows)
            if rows:
                _logger.info(
                    'Asura insert normalized sample correlationId=%s sample=%s',
                    correlation_id,
                    {
                        'stock': rows[0].get('stock'),
                        'buying_date': rows[0].get('buying_date'),
                        'buying_price': rows[0].get('buying_price'),
                        'ema20': rows[0].get('ema20'),
                        'ema50': rows[0].get('ema50'),
                        'ema100': rows[0].get('ema100'),
                        'ema200': rows[0].get('ema200'),
                    },
                )
            inserted = _insert_rows(conn, rows)
            conn.commit()
        invalidate_asura_cache()
    except Exception as exc:
        _logger.exception('Asura insert failed correlationId=%s', correlation_id)
        return jsonify({
            'ok': False,
            'correlationId': correlation_id,
            'insertedCount': 0,
            'skippedCount': skipped + len(rows),
            'errors': errors + [{'row': None, 'error': str(exc)}],
        }), 500

    total_rows = len(rows)
    inserted = int(inserted or 0)
    skipped_total = skipped + max(total_rows - inserted, 0)
    _logger.info(
        'Asura insert correlationId=%s rows=%s inserted=%s skipped=%s',
        correlation_id,
        total_rows,
        inserted,
        skipped_total,
    )
    agent_result = None
    if inserted > 0:
        try:
            agent_result = start_strategy_agent_execution('asura', run_source='asura_insert')
        except Exception as exc:
            _logger.warning('Asura agent trigger failed correlationId=%s error=%s', correlation_id, exc)
    return jsonify({
        'ok': True,
        'correlationId': correlation_id,
        'insertedCount': inserted,
        'skippedCount': skipped_total,
        'errors': errors,
        'agent': agent_result,
    })


def _compute_payload_with_fallback(
    *,
    timeframe: str,
    min_signal: float,
    min_adx: float,
    breakout_only: bool,
) -> Dict[str, Any]:
    try:
        return _compute_payload(
            timeframe=timeframe,
            min_signal=min_signal,
            min_adx=min_adx,
            breakout_only=breakout_only,
            sort='signal_score',
            order='desc',
            page=1,
            page_size=ASURA_AUTO_INSERT_PAGE_SIZE,
            search=None,
            symbols=(),
            conditions_only=True,
            include_exited=False,
            trade_start_date=None,
            trade_cutoff_date=None,
        )
    except RuntimeError as exc:
        if 'Asura source not found' not in str(exc):
            raise
        snapshot = _fallback_snapshot()
        base_items = list(snapshot.get('items') or [])
        query_payload = _apply_query_filters(
            base_items,
            min_signal=min_signal,
            min_adx=min_adx,
            breakout_only=breakout_only,
            sort='signal_score',
            order='desc',
            search=None,
            symbols=(),
            page=1,
            page_size=ASURA_AUTO_INSERT_PAGE_SIZE,
        )
        return {
            **query_payload,
            'generated_at': snapshot.get('generated_at'),
            'fallback': True,
            'as_of_date': snapshot.get('as_of_date'),
            'athSource': 'NSE_NIFTY500_DAILY_RAW_DATA_DEV',
        }


def _auto_insert_once(reason: str = 'schedule') -> None:
    if not ASURA_AUTO_INSERT_ENABLED:
        return
    correlation_id = str(uuid.uuid4())
    try:
        payload = _compute_payload_with_fallback(
            timeframe='daily',
            min_signal=ASURA_DEFAULT_MIN_SIGNAL,
            min_adx=ASURA_DEFAULT_MIN_ADX,
            breakout_only=False,
        )
        items = list(payload.get('items') or [])
        rows = _build_rows_from_items(items)
        if not rows:
            _logger.info('Asura auto-insert: no rows to insert correlationId=%s reason=%s', correlation_id, reason)
            return
        with pool.acquire() as conn:
            inserted = _insert_rows(conn, rows)
            conn.commit()
        if inserted > 0:
            try:
                start_strategy_agent_execution('asura', run_source='asura_auto_insert')
            except Exception as exc:
                _logger.warning('Asura auto-insert agent trigger failed correlationId=%s error=%s', correlation_id, exc)
            try:
                latest_date = max(
                    (row.get('buying_date') for row in rows if isinstance(row.get('buying_date'), date)),
                    default=None,
                )
                publish_notification(
                    source='asura_auto_insert',
                    message=f"Asura auto insertion completed successfully for {inserted} rows.",
                    metadata={
                        'reason': reason,
                        'insertedRows': inserted,
                        'ltcDate': latest_date.isoformat() if latest_date else '',
                    },
                )
            except Exception as exc:
                _logger.warning('Asura auto-insert notification failed correlationId=%s error=%s', correlation_id, exc)
        _logger.info(
            'Asura auto-insert done correlationId=%s reason=%s rows=%s inserted=%s',
            correlation_id,
            reason,
            len(rows),
            inserted,
        )
    except Exception:
        _logger.exception('Asura auto-insert failed correlationId=%s reason=%s', correlation_id, reason)


_auto_insert_started = False


def start_asura_auto_insert() -> None:
    global _auto_insert_started
    if _auto_insert_started or not ASURA_AUTO_INSERT_ENABLED:
        return
    _auto_insert_started = True

    def _loop() -> None:
        startup_delay = max(5, int(os.getenv('ASURA_AUTO_INSERT_STARTUP_DELAY_SEC', '20')))
        try:
            time.sleep(startup_delay)
            _auto_insert_once(reason='startup')
        except Exception:
            _logger.exception('Asura startup auto-insert failed')
        while True:
            try:
                now = datetime.now()
                parts = ASURA_AUTO_INSERT_TIME.split(':', 1)
                hour = int(parts[0]) if parts and parts[0].isdigit() else 18
                minute = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
                target = datetime(now.year, now.month, now.day, hour, minute)
                if target <= now:
                    target = target + __import__('datetime').timedelta(days=1)
                sleep_seconds = max(30, int((target - now).total_seconds()))
                time.sleep(sleep_seconds)
                _auto_insert_once(reason='schedule')
            except Exception:
                _logger.exception('Asura auto-insert scheduler error')
                time.sleep(300)

    threading.Thread(target=_loop, name='asura-auto-insert', daemon=True).start()





