from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict

from flask import Blueprint, jsonify, request

from cache import TTLCache, background_refresh, load_json_snapshot, save_json_snapshot
from db import get_oracle_connection
from services import nse_mcap_service as nse_mcap_svc
from services.trend_service import RETURN_SCHEMA_VERSION, build_rows, categorize, fetch_series, return_column_metadata_for_series
from services.ath_service import log_stale_snapshot_warning


bp = Blueprint('trend', __name__)

_trend_cache = TTLCache(ttl_seconds=int((os.getenv('TREND_CACHE_TTL') or '3600')))
_trading_days_cache = TTLCache(ttl_seconds=int((os.getenv('TREND_TRADING_DAYS_CACHE_TTL') or '3600')), max_items=8)
_latest_date_cache_ttl = int((os.getenv('TREND_LATEST_DATE_CACHE_TTL') or '5'))
_latest_date_cache = TTLCache(ttl_seconds=_latest_date_cache_ttl, max_items=8)
_source_meta_cache = TTLCache(ttl_seconds=300, max_items=8)
_source_universe_cache = TTLCache(ttl_seconds=int((os.getenv('TREND_SOURCE_UNIVERSE_CACHE_TTL') or '300')), max_items=4)
_snapshot_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
_logger = logging.getLogger(__name__)
_latest_date_key = 'trend:latestDate'
_date_column_candidates = ('LTC_DATE', 'TRADING_DATE', 'TRADE_DATE', 'DATE')
_ath_source_table = 'NSE_NIFTY500_DAILY_RAW_DATA_DEV'
_latest_state_lock = threading.Lock()
_refresh_state_lock = threading.Lock()
_refreshing_trend_keys: set[str] = set()
_compatible_return_schema_versions = {2, RETURN_SCHEMA_VERSION}
_latest_date_metrics: Dict[str, Any] = {
    'requests_total': 0,
    'cache_hit': 0,
    'cache_miss': 0,
    'queries_total': 0,
    'query_ms_total': 0.0,
    'query_ms_avg': 0.0,
    'query_ms_last': None,
    'errors_total': 0,
    'last_error': None,
    'last_ltc_date': None,
    'last_cache_state': None,
    'last_event_utc': None,
}
_last_announced_ltc_date: str | None = None
_trend_marketcap_row_keys = ('ema20', 'ema50', 'ema200', 'ema200100', 'ema20010050', 'ema2001005020')
_marketcap_index_keys = ('INDEX', 'index', 'market_cap_index')
_marketcap_value_keys = ('MCAP', 'mcap', 'marketCap')
_marketcap_rank_keys = ('MCAP_RANK', 'mcapRank', 'mcap_rank')


def _snapshot_path(timeframe: str) -> str:
    os.makedirs(_snapshot_dir, exist_ok=True)
    return os.path.join(_snapshot_dir, f'snapshot_trend_{timeframe}.json')


def _load_snapshot(timeframe: str) -> Dict[str, Any] | None:
    snap = load_json_snapshot(_snapshot_path(timeframe))
    if snap and _is_compatible(snap):
        return snap
    if snap:
        log_stale_snapshot_warning(endpoint='/api/trend', source=f'snapshot:{timeframe}')
    return None


def _trend_source() -> tuple[str, str, str]:
    schema = os.getenv('ORACLE_SCHEMA', '').strip()
    table = os.getenv('ORACLE_TABLE', 'NSE_NIFTY500_DAILY_RAW_DATA_DEV').strip()
    qualified = f"{schema}.{table}" if schema else table
    return schema, table, qualified


def _resolve_source_meta(conn) -> Dict[str, Any]:
    schema, table, qualified_table = _trend_source()
    cache_key = f"{schema}.{table}".strip('.').upper() or qualified_table.upper()
    cached = _source_meta_cache.get(cache_key)
    if isinstance(cached, dict):
        return dict(cached)

    with conn.cursor() as meta_cur:
        meta_cur.execute(f"SELECT * FROM {qualified_table} WHERE ROWNUM = 0")
        desc = meta_cur.description or []
    columns = {str(col[0]).upper() for col in desc if col and col[0]}
    date_column = next((col for col in _date_column_candidates if col in columns), None)
    if not date_column:
        raise RuntimeError(
            f"None of {_date_column_candidates} found in {qualified_table}. "
            f"Set ORACLE_TABLE to a source with an LTC/TRADING date column."
        )
    meta = {
        'schema': schema,
        'table': table,
        'qualified_table': qualified_table,
        'date_column': date_column,
        'columns': sorted(columns),
    }
    _source_meta_cache.set(cache_key, meta)
    return meta


def _latest_source_symbol_count() -> Dict[str, Any]:
    cache_key = 'trend:source-symbol-universe'
    cached = _source_universe_cache.get(cache_key)
    if isinstance(cached, dict):
        return dict(cached)

    started = time.perf_counter()
    mcap_table = getattr(nse_mcap_svc, '_TABLE_SQL', 'CVING_NSE_MARKET_CAP_HIST')
    with get_oracle_connection() as conn:
        sql = (
            f"WITH latest AS ("
            f"  SELECT MAX(trade_date) AS latest_date "
            f"  FROM {mcap_table} "
            f"  WHERE total_mcap_cr IS NOT NULL"
            f") "
            f"SELECT COUNT(DISTINCT UPPER(TRIM(t.SYMBOL))) AS TOTAL_SYMBOLS, "
            f"       TO_CHAR(MAX(latest.latest_date), 'YYYY-MM-DD') AS LTC_DATE "
            f"FROM {mcap_table} t "
            f"CROSS JOIN latest "
            f"WHERE t.SYMBOL IS NOT NULL "
            f"  AND latest.latest_date IS NOT NULL "
            f"  AND t.trade_date = latest.latest_date "
            f"  AND t.total_mcap_cr IS NOT NULL"
        )
        with conn.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()

    result = {
        'totalSymbols': int(row[0] or 0) if row else 0,
        'latestDate': str(row[1]).strip() if row and row[1] is not None else None,
        'queryMs': round((time.perf_counter() - started) * 1000, 2),
        'source': mcap_table,
    }
    _source_universe_cache.set(cache_key, result)
    return result


def _query_trading_days_payload(timeframe: str) -> Dict[str, Any]:
    bucket_expressions = {
        'daily': None,
        'weekly': "TO_CHAR({date_col}, 'IYYY-IW')",
        'monthly': "TO_CHAR({date_col}, 'YYYY-MM')",
        'yearly': "TO_CHAR({date_col}, 'YYYY')",
    }
    if timeframe not in bucket_expressions:
        raise ValueError('Invalid timeframe')

    started = time.perf_counter()
    with get_oracle_connection() as conn:
        source_meta = _resolve_source_meta(conn)
        date_col = source_meta['date_column']
        qualified_table = source_meta['qualified_table']
        columns = set(source_meta.get('columns') or [])
        close_col = next(
            (
                column
                for column in (
                    'CLOSE_PRICE', 'CLOSE', 'ADJ_CLOSE', 'LTP', 'LAST_PRICE',
                    'CLOSING_PRICE', 'PREVIOUS_CLOSE', 'PRICE',
                )
                if column in columns
            ),
            None,
        )
        if not close_col:
            raise RuntimeError(f'No close/price column found in {qualified_table}.')
        bucket_template = bucket_expressions[timeframe]
        count_expression = (
            f'COUNT({close_col})'
            if bucket_template is None
            else f"COUNT(DISTINCT {bucket_template.format(date_col=date_col)})"
        )
        sql = (
            f"SELECT UPPER(TRIM(SYMBOL)) AS SYMBOL, {count_expression} AS TRADING_DAYS "
            f"FROM {qualified_table} "
            f"WHERE SYMBOL IS NOT NULL "
            f"  AND {date_col} IS NOT NULL "
            f"  AND {close_col} IS NOT NULL "
            f"GROUP BY UPPER(TRIM(SYMBOL)) "
            f"ORDER BY UPPER(TRIM(SYMBOL))"
        )
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = [
                {'symbol': str(symbol or '').strip().upper(), 'tradingDays': int(trading_days or 0)}
                for symbol, trading_days in cur
                if str(symbol or '').strip()
            ]

    return {
        'rows': rows,
        'count': len(rows),
        'timeframe': timeframe,
        'cachedAt': datetime.utcnow().isoformat() + 'Z',
        'queryMs': round((time.perf_counter() - started) * 1000, 2),
    }


def _with_source_universe_total(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    output = dict(payload)
    try:
        universe = _latest_source_symbol_count()
    except Exception as exc:
        _logger.warning("Trend totalSymbols market-cap universe query failed; keeping existing total. error=%s", exc)
        return output

    total_symbols = int(universe.get('totalSymbols') or 0)
    if total_symbols <= 0:
        return output

    summary = output.get('summary')
    summary = dict(summary) if isinstance(summary, dict) else {}
    summary['totalSymbols'] = total_symbols
    if output.get('technicalRows') is not None:
        summary.setdefault('technicalRows', output.get('technicalRows'))

    output['totalSymbols'] = total_symbols
    output['summary'] = summary
    output['totalSymbolsSource'] = universe.get('source') or _ath_source_table
    output['totalSymbolsLatestDate'] = universe.get('latestDate')
    return output


def _query_latest_ltc_date() -> Dict[str, Any]:
    started = time.perf_counter()
    with get_oracle_connection() as conn:
        source_meta = _resolve_source_meta(conn)
        date_col = source_meta['date_column']
        qualified_table = source_meta['qualified_table']
        sql = (
            f"SELECT TO_CHAR(MAX({date_col}), 'YYYY-MM-DD') AS LTC_DATE "
            f"FROM {qualified_table} "
            f"WHERE {date_col} IS NOT NULL"
        )
        with conn.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()
    query_ms = round((time.perf_counter() - started) * 1000, 2)
    ltc_date = None
    if row and row[0] is not None:
        ltc_date = str(row[0]).strip() or None
    return {
        'ltc_date': ltc_date,
        'query_ms': query_ms,
        'rows': 1,
        'source': source_meta,
        'sql': sql,
    }


def _record_latest_date_metric(
    *,
    cache_state: str,
    query_ms: float | None = None,
    ltc_date: str | None = None,
    error: str | None = None,
) -> None:
    now = datetime.utcnow().isoformat() + 'Z'
    with _latest_state_lock:
        _latest_date_metrics['requests_total'] += 1
        cache_label = str(cache_state or '').upper()
        if cache_label == 'HIT':
            _latest_date_metrics['cache_hit'] += 1
        else:
            _latest_date_metrics['cache_miss'] += 1

        if query_ms is not None:
            _latest_date_metrics['queries_total'] += 1
            _latest_date_metrics['query_ms_total'] += float(query_ms)
            count = _latest_date_metrics['queries_total']
            total = _latest_date_metrics['query_ms_total']
            _latest_date_metrics['query_ms_avg'] = round(total / count, 2) if count else 0.0
            _latest_date_metrics['query_ms_last'] = float(query_ms)
        if error:
            _latest_date_metrics['errors_total'] += 1
            _latest_date_metrics['last_error'] = str(error)
        if ltc_date is not None:
            _latest_date_metrics['last_ltc_date'] = ltc_date
        _latest_date_metrics['last_cache_state'] = cache_label
        _latest_date_metrics['last_event_utc'] = now


def _notify_trend_cache_on_date_change(new_ltc_date: str | None) -> None:
    global _last_announced_ltc_date
    if not new_ltc_date:
        return
    with _latest_state_lock:
        previous = _last_announced_ltc_date
        if previous == new_ltc_date:
            return
        _last_announced_ltc_date = new_ltc_date
    if previous and previous != new_ltc_date:
        _logger.info(
            "latestDate changed from %s to %s; scheduling trend daily refresh",
            previous,
            new_ltc_date,
        )
        _schedule_refresh('daily', 'trend:daily')


def invalidate_trend_cache(*, clear_latest_date: bool = True) -> None:
    _trend_cache.clear()
    _trading_days_cache.clear()
    with _refresh_state_lock:
        _refreshing_trend_keys.clear()
    if clear_latest_date:
        _latest_date_cache.delete(_latest_date_key)


def warm_trend_cache(timeframes: tuple[str, ...] = ('daily',)) -> None:
    for timeframe in timeframes:
        cache_key = f'trend:{timeframe}'
        _schedule_refresh(timeframe, cache_key)


def _get_latest_date_payload(force_refresh: bool = False) -> Dict[str, Any]:
    if not force_refresh:
        cached = _latest_date_cache.get(_latest_date_key)
        if isinstance(cached, dict) and 'ltc_date' in cached:
            source = cached.get('_source') or {}
            _record_latest_date_metric(cache_state='HIT', ltc_date=cached.get('ltc_date'))
            _logger.info(
                "latestDate query ms=0 rows=1 cache=HIT ltc_date=%s source=%s.%s(%s)",
                cached.get('ltc_date'),
                source.get('schema') or '',
                source.get('table') or source.get('qualified_table') or '',
                source.get('date_column') or '',
            )
            return {'ltc_date': cached.get('ltc_date')}

    result = _query_latest_ltc_date()
    ltc_date = result.get('ltc_date')
    source = result.get('source') or {}
    cache_payload = {
        'ltc_date': ltc_date,
        '_source': source,
        '_cached_at': datetime.utcnow().isoformat() + 'Z',
    }
    _latest_date_cache.set(_latest_date_key, cache_payload)
    _record_latest_date_metric(cache_state='MISS', query_ms=result.get('query_ms'), ltc_date=ltc_date)
    _logger.info(
        "latestDate query ms=%s rows=%s cache=MISS ltc_date=%s source=%s.%s(%s)",
        result.get('query_ms'),
        result.get('rows'),
        ltc_date,
        source.get('schema') or '',
        source.get('table') or source.get('qualified_table') or '',
        source.get('date_column') or '',
    )
    _notify_trend_cache_on_date_change(ltc_date)
    return {'ltc_date': ltc_date}


def _parse_cached_at(payload: Dict[str, Any] | None) -> datetime | None:
    if not payload:
        return None
    ts = payload.get('cachedAt')
    if isinstance(ts, str):
        try:
            if ts.endswith('Z'):
                ts = ts[:-1] + '+00:00'
            return datetime.fromisoformat(ts)
        except ValueError:
            return None
    return None


def _snapshot_newer(snapshot: Dict[str, Any], cached: Dict[str, Any] | None) -> bool:
    snapshot_at = _parse_cached_at(snapshot)
    if snapshot_at is None:
        return False
    cached_at = _parse_cached_at(cached)
    if cached_at is None:
        return True
    return snapshot_at > cached_at


def _is_valid(payload: Dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    timeframe = payload.get('timeframe')
    if not (isinstance(timeframe, str) and timeframe in ('daily', 'weekly', 'monthly', 'yearly')):
        return False
    required_keys = ('ema20', 'ema50', 'ema200', 'ema200100', 'ema20010050', 'ema2001005020')
    return all(isinstance(payload.get(key), list) for key in required_keys)


def _has_ath_gap(payload: Dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    table_keys = ('ema20', 'ema50', 'ema200', 'ema200100', 'ema20010050', 'ema2001005020')
    for key in table_keys:
        rows = payload.get(key)
        if not isinstance(rows, list) or not rows:
            continue
        sample = next((row for row in rows if isinstance(row, dict)), None)
        if sample is None:
            continue
        has_ath = ('ath' in sample) or ('ATH' in sample)
        has_gap = ('gap' in sample) or ('GAP' in sample)
        return has_ath and has_gap
    # If there are no rows, payload is compatible.
    return True


def _is_compatible(payload: Dict[str, Any] | None) -> bool:
    if not (_is_valid(payload) and _has_ath_gap(payload)):
        return False
    try:
        return_schema_version = int(payload.get('returnSchemaVersion'))
    except (TypeError, ValueError):
        return False
    if return_schema_version not in _compatible_return_schema_versions:
        return False
    if not isinstance(payload.get('yearReturnColumns'), list):
        return False
    source = str((payload or {}).get('athSource') or '').strip().upper()
    return source == _ath_source_table


def _compute_trend_payload(timeframe: str) -> Dict[str, Any]:
    try:
        series = fetch_series(timeframe=timeframe)
        return_columns = return_column_metadata_for_series(series)
        year_return_columns = [column for column in return_columns if column.get('kind') == 'year']
        rows = build_rows(series)
        technical_rows = len(rows)
        try:
            universe = _latest_source_symbol_count()
            total_symbols = int(universe.get('totalSymbols') or 0) or technical_rows
        except Exception as exc:
            _logger.warning("Trend totalSymbols market-cap universe query failed during compute; using technical rows. error=%s", exc)
            universe = {}
            total_symbols = technical_rows
        ema20, ema50, ema5020, ema100, ema200, ema200100, ema20010050, ema2001005020 = categorize(rows)
        now = datetime.utcnow().isoformat() + 'Z'
        return {
            'ema20': ema20,
            'ema50': ema50,
            'ema5020': ema5020,
            'ema100': ema100,
            'ema200': ema200,
            'ema200100': ema200100,
            'ema20010050': ema20010050,
            'ema2001005020': ema2001005020,
            'cachedAt': now,
            'timeframe': timeframe,
            'totalSymbols': total_symbols,
            'technicalRows': technical_rows,
            'summary': {'totalSymbols': total_symbols, 'technicalRows': technical_rows},
            'totalSymbolsSource': universe.get('source') or _ath_source_table,
            'totalSymbolsLatestDate': universe.get('latestDate'),
            'athSource': _ath_source_table,
            'returnSchemaVersion': RETURN_SCHEMA_VERSION,
            'returnColumns': return_columns,
            'yearReturnColumns': year_return_columns,
            'yearReturnMaxYear': max((int(column.get('years') or 0) for column in year_return_columns), default=0),
        }
    except Exception as exc:
        snapshot = _load_snapshot(timeframe)
        if snapshot:
            _logger.warning(
                "Trend payload refresh failed (tf=%s, %s); using snapshot fallback",
                timeframe, exc,
            )
            payload = dict(snapshot)
            payload['error'] = str(exc)
            payload['stale'] = True
            payload['fallback'] = True
            payload.setdefault('cachedAt', datetime.utcnow().isoformat() + 'Z')
            payload.setdefault('timeframe', timeframe)
            return payload
        raise


def _first_present_marketcap_value(row: Dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key not in row:
            continue
        value = row.get(key)
        if value is None:
            continue
        if isinstance(value, str) and value.strip() == '':
            continue
        return value
    return None


def _has_marketcap_text(value: Any) -> bool:
    text = str(value or '').strip().upper()
    return bool(text) and text not in {'-', 'NULL', 'NONE', 'UNDEFINED'}


def _has_marketcap_number(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return True
    text = str(value).replace(',', '').strip().upper()
    if not text or text in {'-', 'NULL', 'NONE', 'UNDEFINED'}:
        return False
    try:
        float(text)
        return True
    except ValueError:
        return False


def _row_has_marketcap_values(row: Dict[str, Any]) -> bool:
    index_value = _first_present_marketcap_value(row, _marketcap_index_keys)
    mcap_value = _first_present_marketcap_value(row, _marketcap_value_keys)
    rank_value = _first_present_marketcap_value(row, _marketcap_rank_keys)
    return (
        _has_marketcap_text(index_value)
        and _has_marketcap_number(mcap_value)
        and _has_marketcap_number(rank_value)
    )


def _has_marketcap_fields(payload: Dict[str, Any]) -> bool:
    saw_row = False
    for key in _trend_marketcap_row_keys:
        rows = payload.get(key)
        if not isinstance(rows, list) or not rows:
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            saw_row = True
            if not _row_has_marketcap_values(row):
                return False
    return saw_row


def _with_marketcap(payload: Dict[str, Any]) -> Dict[str, Any]:
    if _has_marketcap_fields(payload):
        return payload
    return nse_mcap_svc.enrich_payload_marketcap_index(
        payload,
        row_keys=_trend_marketcap_row_keys,
    )


def _trend_json(payload: Dict[str, Any]):
    response_payload = dict(payload)
    response_payload.pop('allRows', None)
    return jsonify(_with_source_universe_total(_with_marketcap(response_payload)))


def _persist_payload(timeframe: str, cache_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    _trend_cache.set(cache_key, payload)
    save_json_snapshot(_snapshot_path(timeframe), payload)
    return payload


def _compute_and_persist(timeframe: str, cache_key: str) -> Dict[str, Any]:
    return _persist_payload(timeframe, cache_key, _compute_trend_payload(timeframe))


def _is_refresh_inflight(cache_key: str) -> bool:
    with _refresh_state_lock:
        return cache_key in _refreshing_trend_keys


def _schedule_refresh(timeframe: str, cache_key: str) -> None:
    with _refresh_state_lock:
        if cache_key in _refreshing_trend_keys:
            return
        _refreshing_trend_keys.add(cache_key)

    def _run_refresh() -> Dict[str, Any]:
        try:
            return _compute_and_persist(timeframe, cache_key)
        finally:
            with _refresh_state_lock:
                _refreshing_trend_keys.discard(cache_key)

    background_refresh(_trend_cache, cache_key, _run_refresh)


@bp.get('/api/trend/latestDate')
def api_trend_latest_date():
    force_refresh = request.args.get('refresh') in ('1', 'true', 'yes')
    try:
        payload = _get_latest_date_payload(force_refresh=force_refresh)
        return jsonify(payload)
    except Exception as exc:
        _record_latest_date_metric(cache_state='MISS', error=str(exc))
        _logger.exception("latestDate query failed")
        return jsonify({'ltc_date': None, 'detail': 'Failed to resolve latest date', 'error': str(exc)}), 500


@bp.get('/api/trend/ping')
def api_trend_ping():
    started = time.perf_counter()
    try:
        with get_oracle_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT 1 FROM DUAL')
                cur.fetchone()
        db_latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return jsonify({
            'ok': True,
            'db': 'up',
            'db_latency_ms': db_latency_ms,
            'timestamp_utc': datetime.utcnow().isoformat() + 'Z',
        })
    except Exception as exc:
        db_latency_ms = round((time.perf_counter() - started) * 1000, 2)
        _logger.warning("trend ping failed in %sms: %s", db_latency_ms, exc)
        return jsonify({
            'ok': False,
            'db': 'down',
            'db_latency_ms': db_latency_ms,
            'error': str(exc),
            'timestamp_utc': datetime.utcnow().isoformat() + 'Z',
        }), 503


@bp.get('/api/trend/metrics')
def api_trend_metrics():
    with _latest_state_lock:
        latest_metrics = dict(_latest_date_metrics)
    latest_metrics['latest_date_cache_ttl_seconds'] = _latest_date_cache_ttl
    latest_metrics['trend_cache_ttl_seconds'] = int((os.getenv('TREND_CACHE_TTL') or '3600'))
    return jsonify({'latestDate': latest_metrics})


@bp.get('/api/trend/trading-days')
def api_trend_trading_days():
    timeframe = request.args.get('tf', 'daily').lower()
    if timeframe not in ('daily', 'weekly', 'monthly', 'yearly'):
        return jsonify({'detail': 'Invalid timeframe'}), 400

    cache_key = f'trend:trading-days:{timeframe}'
    force_refresh = request.args.get('refresh') in ('1', 'true', 'yes')
    cached = _trading_days_cache.get(cache_key)
    if isinstance(cached, dict):
        if force_refresh:
            background_refresh(
                _trading_days_cache,
                cache_key,
                lambda: _query_trading_days_payload(timeframe),
            )
            return jsonify({**cached, 'cached': True, 'refreshing': True})
        return jsonify({**cached, 'cached': True})

    payload = _query_trading_days_payload(timeframe)
    _trading_days_cache.set(cache_key, payload)
    return jsonify(payload)


@bp.get('/api/trend')
def api_trend():
    timeframe_param = request.args.get('tf', 'daily').lower()
    if timeframe_param not in ('daily', 'weekly', 'monthly', 'yearly'):
        return jsonify({'detail': 'Invalid timeframe'}), 400

    cache_key = f"trend:{timeframe_param}"
    force_refresh = request.args.get('refresh') in ('1', 'true', 'yes')
    cached = _trend_cache.get(cache_key)
    if cached is not None and not _is_compatible(cached):
        log_stale_snapshot_warning(endpoint='/api/trend', source='cache')
        cached = None
    snapshot = _load_snapshot(timeframe_param)

    def _fallback_response(exc: Exception):
        payload = cached or snapshot
        if payload:
            _logger.warning(
                "Trend refresh failed (tf=%s); serving fallback: %s",
                timeframe_param, exc,
            )
            return _trend_json({**dict(payload), 'cached': True, 'fallback': True, 'error': str(exc)})
        raise exc

    if force_refresh:
        if cached is not None or snapshot is not None:
            payload = cached or snapshot
            _schedule_refresh(timeframe_param, cache_key)
            return _trend_json({**dict(payload), 'cached': True, 'refreshing': True})
        try:
            payload = _compute_and_persist(timeframe_param, cache_key)
            return _trend_json({**payload, 'cached': False})
        except Exception as exc:
            return _fallback_response(exc)

    snapshot_used = False
    if snapshot and _snapshot_newer(snapshot, cached):
        cached = dict(snapshot)
        _trend_cache.set(cache_key, cached)
        snapshot_used = True

    if cached is not None:
        if snapshot_used:
            _schedule_refresh(timeframe_param, cache_key)
            return _trend_json({**cached, 'cached': True, 'refreshing': True})
        if _is_refresh_inflight(cache_key):
            return _trend_json({**cached, 'cached': True, 'refreshing': True})
        return _trend_json({**cached, 'cached': True})

    try:
        payload = _compute_and_persist(timeframe_param, cache_key)
        return _trend_json(payload)
    except Exception as exc:  # pragma: no cover
        return _fallback_response(exc)

