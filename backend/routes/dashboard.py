from __future__ import annotations

import os
import time
from typing import Any, Dict
from threading import Lock

from flask import Blueprint, jsonify, request, current_app
from .request_validators import parse_int

from cache import TTLCache, background_refresh, load_json_snapshot, save_json_snapshot
from services.dashboard_service import (
    AVAILABLE_SEGMENTS,
    DEFAULT_SEGMENT,
    DEFAULT_MOVERS_LIMIT,
    get_dashboard_latest_trading_date,
    load_nifty50_top_movers_payload,
    load_dashboard_payload,
)
try:
    from services import nse_mcap_service as nse_mcap_svc
except ImportError:  # pragma: no cover
    from ..services import nse_mcap_service as nse_mcap_svc  # type: ignore

bp = Blueprint('dashboard', __name__)

_ttl = int(os.getenv('DASHBOARD_CACHE_TTL', '900'))
_cache = TTLCache(ttl_seconds=_ttl)
_data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
_segment_locks: dict[str, Lock] = {}
_locks_guard = Lock()
_refreshing_segments: set[tuple[str, int]] = set()
_refresh_guard = Lock()


def _normalize_mover_rows(rows: Any, *, enrich_marketcap: bool = True) -> list[dict[str, Any]]:
    source_rows = [row for row in (rows or []) if isinstance(row, dict)]
    # Persisted dashboard snapshots are already enriched by dashboard_service.
    # Do not make the request fast path depend on a fresh Oracle metadata lookup.
    enriched = nse_mcap_svc.enrich_rows_with_marketcap_index(source_rows) if enrich_marketcap else source_rows
    normalized: list[dict[str, Any]] = []
    for row in enriched:
        output = dict(row)
        symbol = str(output.get('symbol') or output.get('stock') or output.get('stockName') or '').strip().upper()
        if symbol:
            output['symbol'] = symbol
            output.setdefault('SYMBOL', symbol)
            output.setdefault('stock', symbol)
            output.setdefault('STOCK', symbol)
            output.setdefault('stockName', symbol)
        ltc_date = str(output.get('ltcDate') or output.get('ltc_date') or output.get('LTC_DATE') or output.get('tradingDate') or '').strip()
        if ltc_date:
            output['ltcDate'] = ltc_date
            output['ltc_date'] = ltc_date
            output['LTC_DATE'] = ltc_date
        rank_value = output.get('mcapRank')
        if rank_value is None:
            rank_value = output.get('MCAP_RANK')
        if rank_value is not None:
            output['mcapRank'] = rank_value
            output['mcap_rank'] = rank_value
            output['MCAP_RANK'] = rank_value
        mcap_value = output.get('mcap')
        if mcap_value is None:
            mcap_value = output.get('MCAP')
        if mcap_value is not None:
            output['mcap'] = mcap_value
            output['MCAP'] = mcap_value
            output['market_cap'] = mcap_value
        index_value = output.get('index')
        if index_value in (None, ''):
            index_value = output.get('INDEX')
        if index_value not in (None, ''):
            output['index'] = index_value
            output['INDEX'] = index_value
        volume_value = output.get('volume')
        if volume_value is None:
            volume_value = output.get('VOLUME')
        if volume_value is not None:
            output['volume'] = volume_value
            output['VOLUME'] = volume_value
        normalized.append(output)
    return normalized


def _hydrate_movers_payload(payload: Dict[str, Any], *, enrich_marketcap: bool = True) -> Dict[str, Any]:
    output = dict(payload or {})
    for key in ('gainers', 'losers'):
        if isinstance(output.get(key), list):
            output[key] = _normalize_mover_rows(output.get(key), enrich_marketcap=enrich_marketcap)
    return output


def _movers_payload_has_required_fields(payload: Dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    def _is_missing_value(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            token = value.strip()
            return token == '' or token == '-'
        return False

    required = ('symbol', 'index', 'mcap', 'mcap_rank', 'volume', 'ltc_date')
    for bucket in ('gainers', 'losers'):
        rows = payload.get(bucket)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            for key in required:
                if _is_missing_value(row.get(key)) and _is_missing_value(row.get(key.upper())):
                    return False
    return True


def _breadth_payload_is_current(payload: Dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    rows = payload.get('breadthRows')
    if not isinstance(rows, list):
        return False
    segments = {str((row or {}).get('segment') or '').strip().lower() for row in rows if isinstance(row, dict)}
    required = {'nifty50', 'next50', 'midcap', 'smallcap', 'nifty500'}
    if required.issubset(segments):
        return True
    # Accept near-complete breadth payloads when Nifty500 aggregate is present;
    # this prevents permanent stale mode if one constituent index snapshot lags.
    constituent_segments = {'nifty50', 'next50', 'midcap', 'smallcap'}
    present_constituents = len(segments.intersection(constituent_segments))
    return 'nifty500' in segments and present_constituents >= 3


def _payload_has_dashboard_data(payload: Dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    if _breadth_payload_is_current(payload):
        return True
    return any(isinstance(payload.get(key), list) and len(payload.get(key) or []) > 0 for key in ('gainers', 'losers', 'breadthRows'))


def _current_fallback_payload(*candidates: Dict[str, Any] | None) -> Dict[str, Any] | None:
    for candidate in candidates:
        if _payload_has_dashboard_data(candidate):
            return dict(candidate)
    return None


def _payload_matches_latest_date(payload: Dict[str, Any] | None, latest_trading_date: str) -> bool:
    if not latest_trading_date:
        return True
    if not isinstance(payload, dict):
        return False
    return str(payload.get('tradingDate') or '').strip() == latest_trading_date


def _resolve_segment(raw: str | None) -> str:
    segment = (raw or DEFAULT_SEGMENT).strip().lower() or DEFAULT_SEGMENT
    if segment not in AVAILABLE_SEGMENTS:
        raise ValueError(f"Unsupported segment '{raw}'. Options: {', '.join(AVAILABLE_SEGMENTS)}")
    return segment


def _cache_key(segment: str, limit: int) -> str:
    return f'movers:{segment}:{limit}'


def _snapshot_path_for(segment: str, limit: int) -> str:
    if limit == DEFAULT_MOVERS_LIMIT:
        filename = f'snapshot_dashboard_{segment}.json'
    else:
        filename = f'snapshot_dashboard_{segment}_{limit}.json'
    return os.path.join(_data_dir, filename)


def _compute_payload(segment: str, limit: int) -> Dict[str, Any]:
    return load_dashboard_payload(segment, mover_limit=limit)


def _resolve_limit(raw: str | None) -> int:
    if raw is None or str(raw).strip() == '':
        return DEFAULT_MOVERS_LIMIT
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError('Invalid limit parameter')
    if value < 1:
        raise ValueError('Limit must be at least 1')
    return min(value, 50)


def _schedule_background_refresh(segment: str, limit: int, key: str) -> None:
    token = (segment, limit)
    with _refresh_guard:
        if token in _refreshing_segments:
            return
        _refreshing_segments.add(token)

    def _compute(seg: str = segment, lim: int = limit) -> Dict[str, Any]:
        try:
            return _refresh_payload_sync(seg, lim)
        finally:
            with _refresh_guard:
                _refreshing_segments.discard(token)

    background_refresh(_cache, key, _compute)


def _refresh_payload_sync(segment: str, limit: int) -> Dict[str, Any]:
    """Compute payload now, updating cache + snapshot under lock."""
    key = _cache_key(segment, limit)
    with _locks_guard:
        lock = _segment_locks.setdefault(segment, Lock())
    with lock:
        payload = _compute_payload(segment, limit)
        _cache.set(key, payload)
        save_json_snapshot(_snapshot_path_for(segment, limit), payload)
        return payload


def invalidate_dashboard_cache() -> None:
    _cache.clear()
    with _refresh_guard:
        _refreshing_segments.clear()


def warm_dashboard_cache() -> None:
    targets = [
        (DEFAULT_SEGMENT, DEFAULT_MOVERS_LIMIT),
        ('nifty500', 25),
    ]
    for segment, limit in targets:
        _schedule_background_refresh(segment, limit, _cache_key(segment, limit))


@bp.get('/api/dashboard/movers')
def api_dashboard_movers():
    started = time.perf_counter()
    try:
        segment = _resolve_segment(request.args.get('segment'))
        limit = parse_int(request.args.get('limit'), DEFAULT_MOVERS_LIMIT, min_value=1, max_value=50, field='limit')
    except ValueError as exc:
        return jsonify({'status': 'error', 'message': str(exc)}), 400

    force_refresh = request.args.get('refresh') in ('1', 'true', 'yes')
    key = _cache_key(segment, limit)
    snapshot_path = _snapshot_path_for(segment, limit)
    cached = _cache.get(key)
    if isinstance(cached, dict):
        cached = _hydrate_movers_payload(dict(cached), enrich_marketcap=False)
        if _payload_has_dashboard_data(cached):
            _cache.set(key, dict(cached))
        else:
            current_app.logger.info(
                'api_dashboard_movers cache_miss_required_fields endpoint=/api/dashboard/movers segment=%s limit=%s',
                segment,
                limit,
            )
            cached = None
    request_id = getattr(request, 'request_id', '') or request.headers.get('X-Request-ID', '')
    snapshot = None
    if cached is not None and _breadth_payload_is_current(cached):
        if force_refresh:
            _schedule_background_refresh(segment, limit, key)
            current_app.logger.info(
                'api_dashboard_movers request_id=%s endpoint=/api/dashboard/movers segment=%s limit=%s trading_date=%s gainers=%s losers=%s duration_ms=%s fallback_used=true source=cache_refreshing_fast_path',
                request_id,
                segment,
                limit,
                cached.get('tradingDate'),
                len(cached.get('gainers') or []),
                len(cached.get('losers') or []),
                round((time.perf_counter() - started) * 1000, 2),
            )
            return jsonify({**cached, 'cached': True, 'refreshing': True})
        current_app.logger.info(
            'api_dashboard_movers request_id=%s endpoint=/api/dashboard/movers segment=%s limit=%s trading_date=%s gainers=%s losers=%s duration_ms=%s fallback_used=true source=cache_fast_path',
            request_id,
            segment,
            limit,
            cached.get('tradingDate'),
            len(cached.get('gainers') or []),
            len(cached.get('losers') or []),
            round((time.perf_counter() - started) * 1000, 2),
        )
        return jsonify({**cached, 'cached': True})

    if not force_refresh:
        snapshot = load_json_snapshot(snapshot_path)
        if isinstance(snapshot, dict):
            snapshot = _hydrate_movers_payload(dict(snapshot), enrich_marketcap=False)
        if snapshot and _payload_has_dashboard_data(snapshot):
            payload = _hydrate_movers_payload(dict(snapshot), enrich_marketcap=False)
            _cache.set(key, dict(payload))
            current_app.logger.info(
                'api_dashboard_movers request_id=%s endpoint=/api/dashboard/movers segment=%s limit=%s trading_date=%s gainers=%s losers=%s duration_ms=%s fallback_used=true source=snapshot_fast_path',
                request_id,
                segment,
                limit,
                payload.get('tradingDate'),
                len(payload.get('gainers') or []),
                len(payload.get('losers') or []),
                round((time.perf_counter() - started) * 1000, 2),
            )
            return jsonify({**payload, 'cached': True})

    if force_refresh and snapshot and _payload_has_dashboard_data(snapshot):
        payload = _hydrate_movers_payload(dict(snapshot), enrich_marketcap=False)
        _cache.set(key, dict(payload))
        _schedule_background_refresh(segment, limit, key)
        current_app.logger.info(
            'api_dashboard_movers request_id=%s endpoint=/api/dashboard/movers segment=%s limit=%s trading_date=%s gainers=%s losers=%s duration_ms=%s fallback_used=true source=snapshot_refreshing_fast_path',
            request_id,
            segment,
            limit,
            payload.get('tradingDate'),
            len(payload.get('gainers') or []),
            len(payload.get('losers') or []),
            round((time.perf_counter() - started) * 1000, 2),
        )
        return jsonify({**payload, 'cached': True, 'refreshing': True})

    if force_refresh:
        try:
            payload = _hydrate_movers_payload(_refresh_payload_sync(segment, limit), enrich_marketcap=False)
            _cache.set(key, dict(payload))
            current_app.logger.info(
                'api_dashboard_movers request_id=%s endpoint=/api/dashboard/movers segment=%s limit=%s latest_db_date=%s trading_date=%s gainers=%s losers=%s duration_ms=%s fallback_used=false source=oracle_force_refresh',
                request_id,
                segment,
                limit,
                get_dashboard_latest_trading_date(segment),
                payload.get('tradingDate'),
                len(payload.get('gainers') or []),
                len(payload.get('losers') or []),
                round((time.perf_counter() - started) * 1000, 2),
            )
            return jsonify({**payload, 'cached': False})
        except Exception:
            current_app.logger.exception(
                'Dashboard force refresh failed for segment=%s limit=%s; serving fallback if available.',
                segment,
                limit,
            )
    latest_trading_date = ''
    try:
        latest_trading_date = get_dashboard_latest_trading_date(segment)
    except Exception:
        current_app.logger.exception(
            'api_dashboard_movers latest_date_resolve_failed request_id=%s endpoint=/api/dashboard/movers segment=%s limit=%s',
            request_id,
            segment,
            limit,
        )

    snapshot = load_json_snapshot(snapshot_path)
    if isinstance(snapshot, dict):
        snapshot = _hydrate_movers_payload(dict(snapshot), enrich_marketcap=False)
    if snapshot and _payload_has_dashboard_data(snapshot):
        payload = _hydrate_movers_payload(dict(snapshot), enrich_marketcap=False)
        _cache.set(key, dict(payload))
        response_payload = {**payload, 'cached': True}
        if force_refresh:
            response_payload['refreshing'] = True
            _schedule_background_refresh(segment, limit, key)
        current_app.logger.info(
            'api_dashboard_movers request_id=%s endpoint=/api/dashboard/movers segment=%s limit=%s latest_db_date=%s trading_date=%s gainers=%s losers=%s duration_ms=%s fallback_used=true source=snapshot',
            request_id,
            segment,
            limit,
            latest_trading_date,
            payload.get('tradingDate'),
            len(payload.get('gainers') or []),
            len(payload.get('losers') or []),
            round((time.perf_counter() - started) * 1000, 2),
        )
        return jsonify(response_payload)

    try:
        payload = _hydrate_movers_payload(_refresh_payload_sync(segment, limit), enrich_marketcap=False)
        _cache.set(key, dict(payload))
        current_app.logger.info(
            'api_dashboard_movers request_id=%s endpoint=/api/dashboard/movers segment=%s limit=%s latest_db_date=%s trading_date=%s gainers=%s losers=%s duration_ms=%s fallback_used=false source=oracle',
            request_id,
            segment,
            limit,
            latest_trading_date,
            payload.get('tradingDate'),
            len(payload.get('gainers') or []),
            len(payload.get('losers') or []),
            round((time.perf_counter() - started) * 1000, 2),
        )
        return jsonify({**payload, 'cached': False})
    except Exception as exc:
        current_app.logger.exception(
            'Dashboard refresh failed for segment=%s limit=%s; serving fallback if available.',
            segment,
            limit,
        )
        fallback = _current_fallback_payload(cached, load_json_snapshot(snapshot_path))
        if fallback is not None and _payload_matches_latest_date(fallback, latest_trading_date):
            fallback = _hydrate_movers_payload(dict(fallback), enrich_marketcap=False)
            _cache.set(key, dict(fallback))
            fallback['cached'] = True
            fallback['stale'] = True
            fallback['error'] = 'Dashboard data refresh failed.'
            fallback['refreshing'] = True
            # Attempt async refresh in the background for next call.
            _schedule_background_refresh(segment, limit, key)
            return jsonify(fallback)
        return jsonify({'status': 'error', 'message': 'Dashboard data unavailable'}), 503


@bp.get('/api/nifty50/top-movers')
def api_nifty50_top_movers():
    try:
        limit = parse_int(request.args.get('limit'), DEFAULT_MOVERS_LIMIT, min_value=1, max_value=50, field='limit')
    except ValueError as exc:
        return jsonify({'status': 'error', 'message': str(exc)}), 400

    try:
        payload = load_nifty50_top_movers_payload(limit=limit)
        return jsonify(payload)
    except Exception:
        return jsonify({
            'trading_date': '',
            'gainers': [],
            'losers': [],
            'status': 'error',
            'message': 'Data unavailable',
        }), 503


