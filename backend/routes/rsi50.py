from __future__ import annotations

import os
from typing import Any, Dict

from flask import Blueprint, jsonify, request

from cache import background_refresh, load_json_snapshot, save_json_snapshot, TTLCache
from services import nse_mcap_service as nse_mcap_svc
from services.rsi50_service import CUTOFF_MONTHS as RSI_MONTHS, load_rsi50_payload
from services.technical_utils import normalize_timeframe


bp = Blueprint('rsi50', __name__)

_ttl = int(os.getenv('RSI50_CACHE_TTL', '900'))
_cache = TTLCache(ttl_seconds=_ttl)
_snapshot_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')


def _compute_payload(timeframe: str) -> Dict[str, Any]:
    return load_rsi50_payload(timeframe=timeframe)


def _snapshot_path(timeframe: str) -> str:
    os.makedirs(_snapshot_dir, exist_ok=True)
    if timeframe == 'daily':
        return os.path.join(_snapshot_dir, 'snapshot_rsi50.json')
    return os.path.join(_snapshot_dir, f'snapshot_rsi50_{timeframe}.json')


def _persist_payload(timeframe: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    save_json_snapshot(_snapshot_path(timeframe), payload)
    return payload


def _refresh_payload(timeframe: str) -> Dict[str, Any]:
    return _persist_payload(timeframe, load_rsi50_payload(timeframe=timeframe))


def _with_marketcap(payload: Dict[str, Any]) -> Dict[str, Any]:
    return nse_mcap_svc.enrich_payload_marketcap_index(payload, row_keys=("rows",))


def _is_valid(payload: Dict[str, Any] | None, timeframe: str) -> bool:
    if not isinstance(payload, dict):
        return False
    meta = payload.get('meta') or {}
    base_months = meta.get('baseCutoffMonths', meta.get('cutoffMonths'))
    payload_tf = meta.get('timeframe') or payload.get('timeframe') or 'daily'
    return base_months == RSI_MONTHS and payload_tf == timeframe


@bp.get('/api/rsi50')
def api_rsi50():
    try:
        timeframe = normalize_timeframe(request.args.get('tf', 'daily'))
    except ValueError:
        return jsonify({'detail': 'Invalid timeframe'}), 400
    force_refresh = request.args.get('refresh') in ('1', 'true', 'yes')
    cache_key = f'rsi50:{timeframe}'
    cached = _cache.get(cache_key)
    if cached is not None and not _is_valid(cached, timeframe):
        cached = None

    snapshot = load_json_snapshot(_snapshot_path(timeframe))
    if snapshot and not _is_valid(snapshot, timeframe):
        snapshot = None

    if force_refresh:
        if cached is not None:
            background_refresh(_cache, cache_key, lambda: _refresh_payload(timeframe))
            return jsonify(_with_marketcap({**cached, 'cached': True, 'refreshing': True}))
        if snapshot:
            background_refresh(_cache, cache_key, lambda: _refresh_payload(timeframe))
            return jsonify(_with_marketcap({**dict(snapshot), 'cached': True, 'refreshing': True}))
        payload = _persist_payload(timeframe, load_rsi50_payload(timeframe=timeframe))
        _cache.set(cache_key, payload)
        return jsonify(_with_marketcap({**payload, 'cached': False}))

    if cached is not None:
        return jsonify(_with_marketcap({**cached, 'cached': True}))

    if snapshot:
        background_refresh(_cache, cache_key, lambda: _refresh_payload(timeframe))
        return jsonify(_with_marketcap({**dict(snapshot), 'cached': True, 'refreshing': True}))

    payload = _persist_payload(timeframe, load_rsi50_payload(timeframe=timeframe))
    _cache.set(cache_key, payload)
    return jsonify(_with_marketcap({**payload, 'cached': False}))
