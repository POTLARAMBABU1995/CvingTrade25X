from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any, Dict

from flask import Blueprint, jsonify, request, current_app

from cache import TTLCache, background_refresh, load_json_snapshot, save_json_snapshot
from services.volume_service import CUTOFF_MONTHS as VOLUME_MONTHS, compute_volume_rows
from services.technical_utils import normalize_timeframe
from services import nse_mcap_service as nse_mcap_svc


bp = Blueprint('volume', __name__)

_cache = TTLCache(ttl_seconds=int(os.getenv('VOLUME_CACHE_TTL') or '1800'))
_snapshot_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')


def _snapshot_path(timeframe: str) -> str:
  os.makedirs(_snapshot_dir, exist_ok=True)
  if timeframe == 'daily':
    return os.path.join(_snapshot_dir, 'snapshot_volume.json')
  return os.path.join(_snapshot_dir, f'snapshot_volume_{timeframe}.json')


def _build_payload(timeframe: str = 'daily') -> Dict[str, Any]:
  rows, meta = compute_volume_rows(timeframe=timeframe)
  rows = nse_mcap_svc.enrich_rows_with_marketcap_index(rows)
  now = datetime.utcnow().isoformat() + 'Z'
  return {'rows': rows, 'count': len(rows), 'cachedAt': now, 'meta': meta, 'timeframe': timeframe}


def _build_payload_and_persist(timeframe: str = 'daily') -> Dict[str, Any]:
  payload = _build_payload(timeframe)
  save_json_snapshot(_snapshot_path(timeframe), payload)
  return payload


def _is_valid(payload: Dict[str, Any] | None, timeframe: str) -> bool:
  if not isinstance(payload, dict):
    return False
  meta = payload.get('meta') or {}
  base_months = meta.get('baseCutoffMonths', meta.get('cutoffMonths'))
  payload_tf = meta.get('timeframe') or payload.get('timeframe') or 'daily'
  return base_months == VOLUME_MONTHS and payload_tf == timeframe


def _build_refreshing_placeholder(timeframe: str) -> Dict[str, Any]:
  now = datetime.utcnow().isoformat() + 'Z'
  return {
    'rows': [],
    'count': 0,
    'cachedAt': now,
    'meta': {
      'cutoffMonths': VOLUME_MONTHS,
      'baseCutoffMonths': VOLUME_MONTHS,
      'timeframe': timeframe,
      'startDate': None,
      'endDate': None,
    },
    'timeframe': timeframe,
  }


def _with_marketcap(payload: Dict[str, Any]) -> Dict[str, Any]:
  return nse_mcap_svc.enrich_payload_marketcap_index(payload, row_keys=('rows',))


def invalidate_volume_cache() -> None:
  _cache.clear()


def warm_volume_cache() -> None:
  background_refresh(_cache, 'volume:daily', lambda: _build_payload_and_persist('daily'))


@bp.get('/api/volume')
def api_volume():
  started = time.perf_counter()
  try:
    timeframe = normalize_timeframe(request.args.get('tf', 'daily'))
  except ValueError:
    return jsonify({'detail': 'Invalid timeframe'}), 400
  force_refresh = request.args.get('refresh') in ('1', 'true', 'yes')
  cache_key = f'volume:{timeframe}'
  cached = _cache.get(cache_key)
  if cached is not None and not _is_valid(cached, timeframe):
    cached = None
  if cached is not None and not force_refresh:
    current_app.logger.info(
      'api_volume rows=%s cutoff_months=%s start_date=%s end_date=%s percentage_columns=current:close previous:prior_close duration_ms=%s source=cache',
      len(cached.get('rows') or []),
      (cached.get('meta') or {}).get('cutoffMonths'),
      (cached.get('meta') or {}).get('startDate'),
      (cached.get('meta') or {}).get('endDate'),
      round((time.perf_counter() - started) * 1000, 2),
    )
    return jsonify({**_with_marketcap(cached), 'cached': True})
  if cached is not None and force_refresh:
    background_refresh(_cache, cache_key, lambda: _build_payload_and_persist(timeframe))
    current_app.logger.info(
      'api_volume rows=%s cutoff_months=%s start_date=%s end_date=%s percentage_columns=current:close previous:prior_close duration_ms=%s source=cache_refreshing',
      len(cached.get('rows') or []),
      (cached.get('meta') or {}).get('cutoffMonths'),
      (cached.get('meta') or {}).get('startDate'),
      (cached.get('meta') or {}).get('endDate'),
      round((time.perf_counter() - started) * 1000, 2),
    )
    return jsonify({**_with_marketcap(cached), 'cached': True, 'refreshing': True})

  snapshot = load_json_snapshot(_snapshot_path(timeframe))
  if snapshot and not _is_valid(snapshot, timeframe):
    snapshot = None
  if snapshot and not force_refresh:
    background_refresh(_cache, cache_key, lambda: _build_payload_and_persist(timeframe))
    current_app.logger.info(
      'api_volume rows=%s cutoff_months=%s start_date=%s end_date=%s percentage_columns=current:close previous:prior_close duration_ms=%s source=snapshot',
      len(snapshot.get('rows') or []),
      (snapshot.get('meta') or {}).get('cutoffMonths'),
      (snapshot.get('meta') or {}).get('startDate'),
      (snapshot.get('meta') or {}).get('endDate'),
      round((time.perf_counter() - started) * 1000, 2),
    )
    return jsonify({**_with_marketcap(snapshot), 'cached': True, 'stale': True})
  if snapshot and force_refresh:
    background_refresh(_cache, cache_key, lambda: _build_payload_and_persist(timeframe))
    current_app.logger.info(
      'api_volume rows=%s cutoff_months=%s start_date=%s end_date=%s percentage_columns=current:close previous:prior_close duration_ms=%s source=snapshot_refreshing',
      len(snapshot.get('rows') or []),
      (snapshot.get('meta') or {}).get('cutoffMonths'),
      (snapshot.get('meta') or {}).get('startDate'),
      (snapshot.get('meta') or {}).get('endDate'),
      round((time.perf_counter() - started) * 1000, 2),
    )
    return jsonify({**_with_marketcap(snapshot), 'cached': True, 'refreshing': True, 'stale': True})

  # Cold-start path: avoid long blocking response; compute in background.
  background_refresh(_cache, cache_key, lambda: _build_payload_and_persist(timeframe))
  placeholder = _build_refreshing_placeholder(timeframe)
  current_app.logger.info(
    'api_volume rows=0 cutoff_months=%s start_date=%s end_date=%s percentage_columns=current:close previous:prior_close duration_ms=%s source=cold_start_placeholder',
    (placeholder.get('meta') or {}).get('cutoffMonths'),
    (placeholder.get('meta') or {}).get('startDate'),
    (placeholder.get('meta') or {}).get('endDate'),
    round((time.perf_counter() - started) * 1000, 2),
  )
  return jsonify({**placeholder, 'cached': False, 'refreshing': True, 'stale': True})

