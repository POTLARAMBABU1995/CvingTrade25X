from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

try:  # Support running as package or loose module
    from ..services import ema_service as svc
    from ..services.ema_service import InvalidParameterError, SymbolNotFoundError
except ImportError:  # pragma: no cover
    from services import ema_service as svc  # type: ignore
    from services.ema_service import InvalidParameterError, SymbolNotFoundError  # type: ignore

bp = Blueprint("ema", __name__)
_logger = logging.getLogger(__name__)


@bp.get("/api/ema")
def ema_endpoint():
    """Return EMA-ready OHLC rows for a symbol and timeframe."""
    symbol = request.args.get("symbol", "", type=str)
    timeframe = request.args.get("tf", "daily", type=str)
    try:
        rows = svc.fetch_ema_series(symbol, timeframe)
        # Return array (sorted by view ORDER BY) to keep response tiny and fast.
        return jsonify(rows)
    except InvalidParameterError as exc:
        return jsonify({"detail": str(exc)}), 400
    except SymbolNotFoundError as exc:
        return jsonify({"detail": str(exc)}), 404
    except Exception as exc:  # pragma: no cover
        _logger.exception("EMA fetch failed: symbol=%s tf=%s", symbol, timeframe, exc_info=exc)
        return jsonify({"detail": "Unable to fetch EMA series"}), 500
