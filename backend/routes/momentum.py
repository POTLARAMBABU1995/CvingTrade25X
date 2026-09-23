from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict

from flask import Blueprint, jsonify, request

from cache import TTLCache, background_refresh, load_json_snapshot, save_json_snapshot
from services import nse_mcap_service as nse_mcap_svc
from services.momentum_service import CUTOFF_MONTHS as MACD_MONTHS, macd_rows
from services.technical_utils import normalize_timeframe


bp = Blueprint('momentum', __name__)

_cache = TTLCache(ttl_seconds=int((__import__('os').getenv('MOMENTUM_CACHE_TTL') or '3600')))
_snapshot_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')


def _snapshot_path(timeframe: str) -> str:
    os.makedirs(_snapshot_dir, exist_ok=True)
    if timeframe == 'daily':
        return os.path.join(_snapshot_dir, 'snapshot_momentum_macd.json')
    return os.path.join(_snapshot_dir, f'snapshot_momentum_macd_{timeframe}.json')


def _compute_payload(timeframe: str) -> Dict[str, Any]:
    rows, meta = macd_rows(timeframe=timeframe)
    return {
        'rows': rows,
        'count': len(rows),
        'meta': meta,
        'timeframe': timeframe,
        'generatedAt': datetime.utcnow().isoformat() + 'Z',
    }


def _with_marketcap(payload: Dict[str, Any]) -> Dict[str, Any]:
    return nse_mcap_svc.enrich_payload_marketcap_index(payload, row_keys=("rows",))


def _is_valid(payload: Dict[str, Any] | None, timeframe: str) -> bool:
    if not isinstance(payload, dict):
        return False
    meta = payload.get('meta') or {}
    base_months = meta.get('baseCutoffMonths', meta.get('cutoffMonths'))
    payload_tf = meta.get('timeframe') or payload.get('timeframe') or 'daily'
    return base_months == MACD_MONTHS and payload_tf == timeframe


@bp.get('/api/momentum/macd')
def api_momentum_macd():
    try:
        timeframe = normalize_timeframe(request.args.get('tf', 'daily'))
    except ValueError:
        return jsonify({'detail': 'Invalid timeframe'}), 400
    force_refresh = request.args.get('refresh') in ('1', 'true', 'yes')
    cache_key = f'macd:{timeframe}'
    cached = _cache.get(cache_key)
    if cached is not None and not _is_valid(cached, timeframe):
        cached = None
    if cached is not None and not force_refresh:
        return jsonify(_with_marketcap({**cached, 'cached': True}))
    if cached is not None and force_refresh:
        background_refresh(_cache, cache_key, lambda: _compute_payload(timeframe))
        return jsonify(_with_marketcap({**cached, 'cached': True, 'refreshing': True}))

    snap = load_json_snapshot(_snapshot_path(timeframe))
    if snap and not _is_valid(snap, timeframe):
        snap = None
    if snap and not force_refresh:
        background_refresh(_cache, cache_key, lambda: _compute_payload(timeframe))
        return jsonify(_with_marketcap({**snap, 'cached': True, 'refreshing': True}))
    if snap and force_refresh:
        background_refresh(_cache, cache_key, lambda: _compute_payload(timeframe))
        return jsonify(_with_marketcap({**snap, 'cached': True, 'refreshing': True}))

    payload = _compute_payload(timeframe)
    _cache.set(cache_key, payload)
    save_json_snapshot(_snapshot_path(timeframe), payload)
    return jsonify(_with_marketcap(payload))
