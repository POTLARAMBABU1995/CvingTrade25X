from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict

from flask import Blueprint, jsonify, request

from cache import TTLCache, background_refresh, load_json_snapshot, save_json_snapshot
from services import nse_mcap_service as nse_mcap_svc
from services.atr14_service import CUTOFF_MONTHS as ATR_MONTHS, compute_atr_rows
from services.technical_utils import normalize_timeframe


bp = Blueprint('atr14', __name__)

_cache = TTLCache(ttl_seconds=int(os.getenv('ATR14_CACHE_TTL') or '1800'))
_snapshot_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')


def _snapshot_path(timeframe: str) -> str:
  os.makedirs(_snapshot_dir, exist_ok=True)
  if timeframe == 'daily':
    return os.path.join(_snapshot_dir, 'snapshot_atr14.json')
  return os.path.join(_snapshot_dir, f'snapshot_atr14_{timeframe}.json')


def _build_payload(timeframe: str) -> Dict[str, Any]:
  rows, meta = compute_atr_rows(timeframe=timeframe)
  now = datetime.utcnow().isoformat() + 'Z'
  return {'rows': rows, 'count': len(rows), 'cachedAt': now, 'meta': meta, 'timeframe': timeframe}


def _with_marketcap(payload: Dict[str, Any]) -> Dict[str, Any]:
  return nse_mcap_svc.enrich_payload_marketcap_index(payload, row_keys=("rows",))


def _is_valid(payload: Dict[str, Any] | None, timeframe: str) -> bool:
  if not isinstance(payload, dict):
    return False
  meta = payload.get('meta') or {}
  base_months = meta.get('baseCutoffMonths', meta.get('cutoffMonths'))
  payload_tf = meta.get('timeframe') or payload.get('timeframe') or 'daily'
  return base_months == ATR_MONTHS and payload_tf == timeframe


@bp.get('/api/atr14')
def api_atr14():
  try:
    timeframe = normalize_timeframe(request.args.get('tf', 'daily'))
  except ValueError:
    return jsonify({'detail': 'Invalid timeframe'}), 400
  force_refresh = request.args.get('refresh') in ('1', 'true', 'yes')
  cache_key = f'atr14:{timeframe}'
  cached = _cache.get(cache_key)
  if cached is not None and not _is_valid(cached, timeframe):
    cached = None
  if cached is not None and not force_refresh:
    return jsonify(_with_marketcap({**cached, 'cached': True}))

  snapshot = load_json_snapshot(_snapshot_path(timeframe))
  if snapshot and not _is_valid(snapshot, timeframe):
    snapshot = None

  if cached is not None and force_refresh:
    background_refresh(_cache, cache_key, lambda: _build_payload(timeframe))
    return jsonify(_with_marketcap({**cached, 'cached': True, 'refreshing': True}))

  if snapshot and not force_refresh:
    background_refresh(_cache, cache_key, lambda: _build_payload(timeframe))
    return jsonify(_with_marketcap({**snapshot, 'cached': True, 'refreshing': True}))

  if snapshot and force_refresh:
    background_refresh(_cache, cache_key, lambda: _build_payload(timeframe))
    return jsonify(_with_marketcap({**snapshot, 'cached': True, 'refreshing': True}))

  try:
    payload = _build_payload(timeframe)
    _cache.set(cache_key, payload)
    save_json_snapshot(_snapshot_path(timeframe), payload)
    return jsonify(_with_marketcap(payload))
  except Exception:
    if snapshot:
      background_refresh(_cache, cache_key, lambda: _build_payload(timeframe))
      return jsonify(_with_marketcap({**snapshot, 'cached': True, 'fallback': True}))
    raise
