from __future__ import annotations

import sys

from flask import Blueprint, g, jsonify, request

from error_log_service import capture_api_error

try:
    from ..services import chart_service as svc
except ImportError:  # pragma: no cover
    from services import chart_service as svc  # type: ignore


bp = Blueprint("chart", __name__, url_prefix="/api/chart")


def _json_error(message: str, status: int = 400):
    safe_message = "Internal server error." if int(status) >= 500 else str(message or "Invalid request parameter")
    payload = {"status": "error", "message": safe_message, "request_id": getattr(g, "request_id", "")}
    if status >= 500:
        exc = sys.exc_info()[1]
        payload.update(capture_api_error(
            request=request,
            status=status,
            message=safe_message,
            extra={"blueprint": bp.name},
            exc=exc if isinstance(exc, BaseException) else None,
        ))
    return jsonify(payload), int(status)


@bp.get("/ohlcv")
def chart_ohlcv_endpoint():
    symbol = request.args.get("symbol", "", type=str)
    timeframe = request.args.get("timeframe", "daily", type=str)
    try:
        return jsonify(svc.fetch_ohlcv_payload(symbol, timeframe))
    except svc.InvalidChartParameter as exc:
        return _json_error(str(exc), 400)
    except Exception:
        return _json_error("Unable to fetch chart OHLCV data.", 500)


@bp.get("/watchlist")
def chart_watchlist_endpoint():
    try:
        return jsonify(svc.fetch_watchlist_payload())
    except Exception:
        return _json_error("Unable to fetch chart watchlist data.", 500)
