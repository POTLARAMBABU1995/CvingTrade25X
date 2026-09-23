from __future__ import annotations

import logging
import time

from flask import Blueprint, jsonify, request

from services import nse_mcap_service as nse_mcap_svc
from services.strong_uptrend_reversal_service import fetch_strong_uptrend_reversal_scan


bp = Blueprint('strong_uptrend_reversal', __name__)
_logger = logging.getLogger(__name__)


def _refresh_requested() -> bool:
    raw = request.args.get('refresh')
    if raw is None:
        return False
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}


def _with_marketcap(payload):
    return nse_mcap_svc.enrich_payload_marketcap_index(payload, row_keys=('data',))


@bp.get('/api/strategy/strong-uptrend-reversal')
def api_strong_uptrend_reversal():
    started = time.perf_counter()
    try:
        service_started = time.perf_counter()
        payload = _with_marketcap(fetch_strong_uptrend_reversal_scan(refresh=_refresh_requested()))
        service_ms = int((time.perf_counter() - service_started) * 1000)
        serialization_started = time.perf_counter()
        response = jsonify(payload)
        serialization_ms = int((time.perf_counter() - serialization_started) * 1000)
        response.headers['Content-Type'] = 'application/json'
        meta = payload.get('meta') if isinstance(payload, dict) else {}
        data = payload.get('data') if isinstance(payload, dict) else []
        row_count = len(data) if isinstance(data, list) else meta.get('rows', 0) if isinstance(meta, dict) else 0
        _logger.info(
            'strong_uptrend_reversal_api route=%s status=SUCCESS rows=%s cache=%s service_ms=%s json_ms=%s total_ms=%s',
            request.path,
            row_count,
            meta.get('cacheState') if isinstance(meta, dict) else None,
            service_ms,
            serialization_ms,
            int((time.perf_counter() - started) * 1000),
        )
        return response
    except Exception:
        _logger.exception(
            'Failed to build strong uptrend reversal payload route=%s total_ms=%s',
            request.path,
            int((time.perf_counter() - started) * 1000),
        )
        response = jsonify({
            'data': [],
            'error': 'Failed to load strong uptrend reversal scanner.',
            'status': 'FAILED',
        })
        response.headers['Content-Type'] = 'application/json'
        return response, 500
