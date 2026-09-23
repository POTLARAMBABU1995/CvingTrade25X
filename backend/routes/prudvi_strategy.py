from __future__ import annotations

import logging
import time

from flask import Blueprint, g, jsonify, request

from services import nse_mcap_service as nse_mcap_svc
from services.prudvi_strategy_service import fetch_prudvi_strategy_scan


bp = Blueprint("prudvi_strategy", __name__)
_logger = logging.getLogger(__name__)
_REQUIRED_Y_FLAGS = ("EMA_GT_20", "EMA_GT_50", "RSI_GT_50", "ADX_GT_25", "MACD_GT_0", "VOLUME_GT_20")


def _refresh_requested() -> bool:
    raw = request.args.get("refresh")
    if raw is None:
        return False
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def _with_marketcap(payload):
    rows = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(rows, list) and rows:
        if all(
            isinstance(row, dict) and {"INDEX", "MCAP", "MCAP_RANK"}.issubset(row.keys())
            for row in rows
        ):
            return payload
    return nse_mcap_svc.enrich_payload_marketcap_index(payload, row_keys=("data",), symbol_keys=("SYMBOL", "symbol"))


def _is_required_y_row(row):
    if not isinstance(row, dict):
        return False
    return all(str(row.get(key, "")).strip().upper() == "Y" for key in _REQUIRED_Y_FLAGS)


def _filter_required_flag_rows(payload):
    if not isinstance(payload, dict):
        return payload
    rows = payload.get("data")
    if not isinstance(rows, list):
        return payload
    filtered_rows = [row for row in rows if _is_required_y_row(row)]
    payload["data"] = filtered_rows
    meta = payload.get("meta")
    if isinstance(meta, dict):
        meta["rows"] = len(filtered_rows)
    return payload


@bp.get("/api/strategy/prudvi")
def api_prudvi_strategy():
    started = time.perf_counter()
    request_id = str(getattr(g, "request_id", "") or "")
    try:
        service_started = time.perf_counter()
        payload = _with_marketcap(fetch_prudvi_strategy_scan(refresh=_refresh_requested()))
        payload = _filter_required_flag_rows(payload)
        if isinstance(payload, dict):
            payload["status"] = "success"
        service_ms = int((time.perf_counter() - service_started) * 1000)
        response = jsonify(payload)
        response.headers["Content-Type"] = "application/json"
        meta = payload.get("meta") if isinstance(payload, dict) else {}
        data = payload.get("data") if isinstance(payload, dict) else []
        row_count = len(data) if isinstance(data, list) else 0
        _logger.info(
            "prudvi_strategy_api request_id=%s route=%s status=success rows=%s cache=%s service_ms=%s total_ms=%s",
            request_id,
            request.path,
            row_count,
            meta.get("cacheState") if isinstance(meta, dict) else None,
            service_ms,
            int((time.perf_counter() - started) * 1000),
        )
        return response
    except Exception:
        _logger.exception(
            "prudvi_strategy_api request_id=%s route=%s status=error total_ms=%s",
            request_id,
            request.path,
            int((time.perf_counter() - started) * 1000),
        )
        response = jsonify({
            "data": [],
            "error": "Failed to load Prudvi strategy scanner.",
            "message": "Failed to load Prudvi strategy scanner.",
            "request_id": request_id,
            "status": "error",
        })
        response.headers["Content-Type"] = "application/json"
        return response, 500
