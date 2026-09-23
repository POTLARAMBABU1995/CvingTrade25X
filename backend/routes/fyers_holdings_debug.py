from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

try:  # Support package and loose-module imports used by local tests.
    from ..services import fyers_holdings_service as fyers_holdings_svc
except ImportError:  # pragma: no cover
    from services import fyers_holdings_service as fyers_holdings_svc  # type: ignore


bp = Blueprint("fyers_holdings_debug", __name__, url_prefix="/api/fyers")
_logger = logging.getLogger(__name__)


def _json_error(message: str, status: int = 400):
    safe_message = "Internal server error." if int(status) >= 500 else str(message or "Invalid request parameter")
    return jsonify({"status": "error", "message": safe_message}), status


@bp.get("/holdings/reconcile")
def fyers_holdings_reconcile_endpoint():
    try:
        return jsonify(fyers_holdings_svc.reconcile_holdings(request.args.to_dict(flat=True)))
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception:
        _logger.exception("FYERS holdings reconciliation endpoint failed")
        return _json_error("Internal server error.", 500)
