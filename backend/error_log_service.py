from __future__ import annotations

import json
import logging
import os
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional


logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_LOG_DIR = Path(os.getenv("CVING_ERROR_LOG_DIR") or (_PROJECT_ROOT / "logs" / "api-errors"))
_RETENTION_DAYS = max(1, int(str(os.getenv("CVING_ERROR_LOG_RETENTION_DAYS", "31")).strip() or "31"))
_CLEANUP_INTERVAL_SEC = 3600
_LOCK = threading.Lock()
_last_cleanup_ts = 0.0


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_log_dir() -> Path:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    return _LOG_DIR


def _log_file_path(ts: datetime) -> Path:
    return _ensure_log_dir() / f"{ts:%Y-%m-%d}.log"


def _isoformat_utc(ts: datetime) -> str:
    return ts.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _cleanup_old_logs(now_ts: float) -> None:
    global _last_cleanup_ts
    if now_ts - _last_cleanup_ts < _CLEANUP_INTERVAL_SEC:
        return
    _last_cleanup_ts = now_ts
    cutoff_ts = now_ts - (_RETENTION_DAYS * 86400)
    log_dir = _ensure_log_dir()
    for path in log_dir.glob("*.log"):
        try:
            if path.is_file() and path.stat().st_mtime < cutoff_ts:
                path.unlink()
        except FileNotFoundError:
            continue
        except Exception:
            logger.exception("Failed to delete expired API error log: %s", path)


def _request_context(request: Any) -> dict[str, Any]:
    if request is None:
        return {}
    query_string = ""
    try:
        raw_query = getattr(request, "query_string", b"")
        if isinstance(raw_query, bytes):
            query_string = raw_query.decode("utf-8", errors="replace")
        elif raw_query:
            query_string = str(raw_query)
    except Exception:
        query_string = ""
    return {
        "method": getattr(request, "method", None),
        "path": getattr(request, "path", None),
        "query_string": query_string or None,
        "endpoint": getattr(request, "endpoint", None),
        "remote_addr": getattr(request, "remote_addr", None),
        "user_agent": getattr(getattr(request, "user_agent", None), "string", None),
    }


def capture_api_error(
    *,
    request: Any,
    status: int,
    message: str,
    extra: Optional[Mapping[str, Any]] = None,
    exc: Optional[BaseException] = None,
) -> dict[str, str]:
    now = _utc_now()
    log_path = _log_file_path(now)
    metadata = {
        "errorId": uuid.uuid4().hex[:12],
        "timestamp": _isoformat_utc(now),
        "logPath": str(log_path),
    }
    entry: dict[str, Any] = {
        "error_id": metadata["errorId"],
        "timestamp": metadata["timestamp"],
        "status": int(status),
        "message": str(message or "").strip() or f"HTTP {status}",
    }
    entry.update(_request_context(request))
    if extra:
        entry["extra"] = dict(extra)
    if exc is not None:
        entry["exception_type"] = type(exc).__name__
        entry["traceback"] = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    with _LOCK:
        _cleanup_old_logs(time.time())
        try:
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=True, default=str))
                handle.write("\n")
        except Exception:
            logger.exception("Failed to persist API error log entry")
    return metadata
