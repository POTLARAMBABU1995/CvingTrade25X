from __future__ import annotations

import logging
import time

from flask import Blueprint, g, jsonify, request

from services.asura_v3_service import (
    ASURA_V3_LATEST_SORT_COLUMNS,
    fetch_asura_v3_cost_summary,
    fetch_asura_v3_dashboard_summary,
    fetch_asura_v3_health,
    fetch_asura_v3_latest_signals,
    fetch_asura_v3_risk_summary,
    fetch_asura_v3_symbol_ratings,
    fetch_asura_v3_yearly_summary,
)
from .request_validators import parse_int, parse_sort_dir, parse_sort_key


bp = Blueprint("asura_v3", __name__)
_logger = logging.getLogger(__name__)


def _request_id() -> str:
    return str(getattr(g, "request_id", "") or "")


def _success(payload: dict, *, request_id: str) -> tuple:
    response_payload = {"request_id": request_id, "status": "success", **payload}
    response = jsonify(response_payload)
    response.headers["Content-Type"] = "application/json"
    return response, 200


def _error_response(message: str, status_code: int, *, request_id: str) -> tuple:
    payload = {
        "message": message,
        "request_id": request_id,
        "status": "error",
    }
    response = jsonify(payload)
    response.headers["Content-Type"] = "application/json"
    return response, status_code


@bp.get("/api/strategy/asura-v3/dashboard-summary")
def api_asura_v3_dashboard_summary():
    started = time.perf_counter()
    request_id = _request_id()
    try:
        payload = fetch_asura_v3_dashboard_summary()
        payload["durationMs"] = int((time.perf_counter() - started) * 1000)
        _logger.info(
            "asura_v3_dashboard_summary_api request_id=%s route=%s status=success duration_ms=%s",
            request_id,
            request.path,
            payload["durationMs"],
        )
        return _success(payload, request_id=request_id)
    except Exception:
        _logger.exception(
            "asura_v3_dashboard_summary_api request_id=%s route=%s status=error",
            request_id,
            request.path,
        )
        return _error_response("Failed to load Asura V3 dashboard summary.", 500, request_id=request_id)


@bp.get("/api/strategy/asura-v3/latest-signals")
def api_asura_v3_latest_signals():
    started = time.perf_counter()
    request_id = _request_id()
    try:
        limit = parse_int(request.args.get("limit"), 25, min_value=1, max_value=500, field="limit")
        offset = parse_int(request.args.get("offset"), 0, min_value=0, max_value=2_000_000, field="offset")
        sort_by = parse_sort_key(
            request.args.get("sort_by"),
            default="SIGNAL_DATE",
            allowed=ASURA_V3_LATEST_SORT_COLUMNS.keys(),
            field="sort_by",
        )
        sort_dir = parse_sort_dir(request.args.get("sort_dir"), default="DESC", field="sort_dir")

        payload = fetch_asura_v3_latest_signals(
            q=request.args.get("q"),
            rating=request.args.get("rating"),
            grade=request.args.get("grade"),
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
        payload["durationMs"] = int((time.perf_counter() - started) * 1000)
        _logger.info(
            "asura_v3_latest_signals_api request_id=%s route=%s status=success total=%s rows=%s limit=%s offset=%s sort_by=%s sort_dir=%s duration_ms=%s",
            request_id,
            request.path,
            payload.get("total", 0),
            len(payload.get("items") or []),
            limit,
            offset,
            sort_by,
            sort_dir,
            payload["durationMs"],
        )
        return _success(payload, request_id=request_id)
    except ValueError as exc:
        return _error_response(str(exc), 400, request_id=request_id)
    except Exception:
        _logger.exception(
            "asura_v3_latest_signals_api request_id=%s route=%s status=error",
            request_id,
            request.path,
        )
        return _error_response("Failed to load Asura V3 latest signals.", 500, request_id=request_id)


@bp.get("/api/strategy/asura-v3/yearly-summary")
def api_asura_v3_yearly_summary():
    started = time.perf_counter()
    request_id = _request_id()
    try:
        payload = fetch_asura_v3_yearly_summary()
        payload["durationMs"] = int((time.perf_counter() - started) * 1000)
        _logger.info(
            "asura_v3_yearly_summary_api request_id=%s route=%s status=success rows=%s duration_ms=%s",
            request_id,
            request.path,
            len(payload.get("items") or []),
            payload["durationMs"],
        )
        return _success(payload, request_id=request_id)
    except Exception:
        _logger.exception(
            "asura_v3_yearly_summary_api request_id=%s route=%s status=error",
            request_id,
            request.path,
        )
        return _error_response("Failed to load Asura V3 yearly summary.", 500, request_id=request_id)


@bp.get("/api/strategy/asura-v3/cost-summary")
def api_asura_v3_cost_summary():
    started = time.perf_counter()
    request_id = _request_id()
    try:
        payload = fetch_asura_v3_cost_summary()
        payload["durationMs"] = int((time.perf_counter() - started) * 1000)
        _logger.info(
            "asura_v3_cost_summary_api request_id=%s route=%s status=success rows=%s duration_ms=%s",
            request_id,
            request.path,
            len(payload.get("items") or []),
            payload["durationMs"],
        )
        return _success(payload, request_id=request_id)
    except Exception:
        _logger.exception(
            "asura_v3_cost_summary_api request_id=%s route=%s status=error",
            request_id,
            request.path,
        )
        return _error_response("Failed to load Asura V3 cost summary.", 500, request_id=request_id)


@bp.get("/api/strategy/asura-v3/risk-summary")
def api_asura_v3_risk_summary():
    started = time.perf_counter()
    request_id = _request_id()
    try:
        payload = fetch_asura_v3_risk_summary()
        payload["durationMs"] = int((time.perf_counter() - started) * 1000)
        _logger.info(
            "asura_v3_risk_summary_api request_id=%s route=%s status=success rows=%s duration_ms=%s",
            request_id,
            request.path,
            len(payload.get("items") or []),
            payload["durationMs"],
        )
        return _success(payload, request_id=request_id)
    except Exception:
        _logger.exception(
            "asura_v3_risk_summary_api request_id=%s route=%s status=error",
            request_id,
            request.path,
        )
        return _error_response("Failed to load Asura V3 risk summary.", 500, request_id=request_id)


@bp.get("/api/strategy/asura-v3/symbol-ratings")
def api_asura_v3_symbol_ratings():
    started = time.perf_counter()
    request_id = _request_id()
    try:
        payload = fetch_asura_v3_symbol_ratings()
        payload["durationMs"] = int((time.perf_counter() - started) * 1000)
        _logger.info(
            "asura_v3_symbol_ratings_api request_id=%s route=%s status=success rows=%s duration_ms=%s",
            request_id,
            request.path,
            len(payload.get("items") or []),
            payload["durationMs"],
        )
        return _success(payload, request_id=request_id)
    except Exception:
        _logger.exception(
            "asura_v3_symbol_ratings_api request_id=%s route=%s status=error",
            request_id,
            request.path,
        )
        return _error_response("Failed to load Asura V3 symbol ratings.", 500, request_id=request_id)


@bp.get("/api/strategy/asura-v3/health")
def api_asura_v3_health():
    started = time.perf_counter()
    request_id = _request_id()
    try:
        payload = fetch_asura_v3_health()
        payload["durationMs"] = int((time.perf_counter() - started) * 1000)
        _logger.info(
            "asura_v3_health_api request_id=%s route=%s status=success db_reachable=%s duration_ms=%s",
            request_id,
            request.path,
            payload.get("dbReachable"),
            payload["durationMs"],
        )
        return _success(payload, request_id=request_id)
    except Exception:
        _logger.exception(
            "asura_v3_health_api request_id=%s route=%s status=error",
            request_id,
            request.path,
        )
        return _error_response("Failed to load Asura V3 health status.", 500, request_id=request_id)
