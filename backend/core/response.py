from __future__ import annotations

from typing import Any


def success_response(data: Any = None, *, message: str = "OK", request_id: str = "") -> dict[str, Any]:
    return {
        "status": "success",
        "message": message,
        "data": data,
        "request_id": request_id,
    }


def error_response(message: str, *, request_id: str = "", error_code: str = "ERROR") -> dict[str, Any]:
    return {
        "status": "error",
        "message": message,
        "error_code": error_code,
        "request_id": request_id,
    }
