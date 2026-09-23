from __future__ import annotations

import sys

from flask import Blueprint, Response, jsonify, request, g
from error_log_service import capture_api_error

try:  # Support package and loose-module execution
    from ..services import historical_data_service as svc
except ImportError:  # pragma: no cover
    from services import historical_data_service as svc  # type: ignore


bp = Blueprint("historical_data", __name__, url_prefix="/api/historical-data")


def _json_error(message: str, status: int = 400):
    safe_message = "Internal server error." if int(status) >= 500 else str(message or "Invalid request parameter")
    payload = {
        "status": "error",
        "message": safe_message,
        "detail": safe_message,
        "request_id": getattr(g, "request_id", ""),
    }
    if status >= 500:
        exc = sys.exc_info()[1]
        payload.update(capture_api_error(
            request=request,
            status=status,
            message=safe_message,
            extra={"blueprint": bp.name},
            exc=exc if isinstance(exc, BaseException) else None,
        ))
    return jsonify(payload), status


@bp.get("/tables")
def historical_tables_endpoint():
    return jsonify({
        "ok": True,
        "default_table": svc.DEFAULT_TABLE,
        "tables": svc.list_allowed_tables(),
    })


@bp.get("/summary")
def historical_summary_endpoint():
    try:
        payload = svc.get_summary(request.args.to_dict(flat=True))
        return jsonify(payload)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.get("/symbol/<symbol>")
def historical_symbol_endpoint(symbol: str):
    try:
        payload = svc.get_symbol_rows(symbol, request.args.to_dict(flat=True))
        return jsonify(payload)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.get("/symbol/<symbol>/csv")
def historical_symbol_csv_endpoint(symbol: str):
    try:
        filename, csv_content = svc.get_symbol_csv(symbol, request.args.to_dict(flat=True))
        return Response(
            csv_content,
            content_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.get("/symbol/<symbol>/download")
def historical_symbol_download_endpoint(symbol: str):
    try:
        filename, archive_content = svc.get_symbol_export_bundle(symbol, request.args.to_dict(flat=True))
        return Response(
            archive_content,
            content_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.post("/delete-symbols")
def historical_delete_symbols_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        result = svc.delete_symbols(payload)
        return jsonify(result)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.post("/delete-rows")
def historical_delete_rows_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        result = svc.delete_rows(payload)
        return jsonify(result)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)
