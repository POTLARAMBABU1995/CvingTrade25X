from __future__ import annotations

import os
import threading
import time
import uuid
from collections import deque
from typing import Any, Deque, Dict, List


_MAX_ITEMS = max(20, int(os.getenv("UI_NOTIFICATION_MAX_ITEMS", "200")))
_RETENTION_MS = max(60_000, int(os.getenv("UI_NOTIFICATION_RETENTION_MS", str(4 * 60 * 60 * 1000))))
_LOCK = threading.Lock()
_ITEMS: Deque[Dict[str, Any]] = deque(maxlen=_MAX_ITEMS)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _prune(now_ms: int | None = None) -> None:
    cutoff = int(now_ms or _now_ms()) - _RETENTION_MS
    while _ITEMS and int(_ITEMS[0].get("ts") or 0) < cutoff:
        _ITEMS.popleft()


def publish_notification(
    *,
    source: str,
    message: str,
    level: str = "success",
    category: str = "automation",
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    item = {
        "id": uuid.uuid4().hex,
        "ts": _now_ms(),
        "source": str(source or "").strip() or "system",
        "level": str(level or "success").strip().lower() or "success",
        "category": str(category or "automation").strip().lower() or "automation",
        "message": str(message or "").strip() or "Completed successfully.",
        "metadata": dict(metadata or {}),
    }
    with _LOCK:
        _prune(item["ts"])
        _ITEMS.append(item)
    return dict(item)


def list_notifications(*, since_ts: int = 0, limit: int = 20) -> List[Dict[str, Any]]:
    since = max(0, int(since_ts or 0))
    max_items = max(1, min(int(limit or 20), 100))
    with _LOCK:
        _prune()
        items = [dict(item) for item in _ITEMS if int(item.get("ts") or 0) > since]
    if len(items) <= max_items:
        return items
    return items[-max_items:]
