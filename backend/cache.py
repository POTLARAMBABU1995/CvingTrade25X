from __future__ import annotations

import json
import sys
import threading
import time
from collections import OrderedDict
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable, Hashable, Optional


def estimate_size_bytes(value: Any, *, stop_at: int | None = None) -> int:
    """Estimate retained bytes for JSON-like cache payloads without double-counting."""
    total = 0
    pending = [value]
    seen: set[int] = set()
    limit = max(0, int(stop_at or 0))

    while pending:
        current = pending.pop()
        object_id = id(current)
        if object_id in seen:
            continue
        seen.add(object_id)
        try:
            total += sys.getsizeof(current)
        except TypeError:  # pragma: no cover - uncommon extension objects
            continue
        if limit and total > limit:
            return total
        if isinstance(current, Mapping):
            pending.extend(current.keys())
            pending.extend(current.values())
        elif isinstance(current, (list, tuple, set, frozenset, OrderedDict)):
            pending.extend(current)
    return total


class TTLCache:
    """Thread-safe, LRU, item- and byte-bounded TTL cache."""

    __slots__ = (
        "_store",
        "_ttl",
        "_max_items",
        "_max_bytes",
        "_estimated_bytes",
        "_expired_evictions",
        "_capacity_evictions",
        "_next_sweep",
        "_lock",
    )

    def __init__(self, ttl_seconds: int, max_items: int = 256, max_bytes: int | None = None) -> None:
        self._store: OrderedDict[Hashable, tuple[float, Any, int]] = OrderedDict()
        self._ttl = max(0, int(ttl_seconds))
        self._max_items = max(1, int(max_items))
        self._max_bytes = max(0, int(max_bytes or 0))
        self._estimated_bytes = 0
        self._expired_evictions = 0
        self._capacity_evictions = 0
        self._next_sweep = 0.0
        self._lock = threading.Lock()

    def _remove_locked(self, key: Hashable) -> Optional[Any]:
        payload = self._store.pop(key, None)
        if payload is None:
            return None
        _, value, size_bytes = payload
        self._estimated_bytes = max(0, self._estimated_bytes - size_bytes)
        return value

    def _evict_expired_locked(self, key: Hashable, now: float) -> Optional[Any]:
        payload = self._store.get(key)
        if not payload:
            return None
        ts, value, _ = payload
        if now - ts > self._ttl:
            self._remove_locked(key)
            self._expired_evictions += 1
            return None
        return value

    def _purge_expired_locked(self, now: float) -> int:
        stale_keys = [key for key, (ts, _, _) in self._store.items() if now - ts > self._ttl]
        for key in stale_keys:
            self._remove_locked(key)
        self._expired_evictions += len(stale_keys)
        self._next_sweep = now + max(1.0, min(float(self._ttl or 1), 30.0))
        return len(stale_keys)

    def _maybe_purge_expired_locked(self, now: float) -> int:
        if now < self._next_sweep:
            return 0
        return self._purge_expired_locked(now)

    def _enforce_limits_locked(self) -> None:
        while self._store and (
            len(self._store) > self._max_items
            or (self._max_bytes > 0 and self._estimated_bytes > self._max_bytes)
        ):
            key = next(iter(self._store))
            self._remove_locked(key)
            self._capacity_evictions += 1

    def get(self, key: Hashable) -> Optional[Any]:
        with self._lock:
            value = self._evict_expired_locked(key, time.monotonic())
            if value is None:
                return None
            self._store.move_to_end(key)
            return value

    def set(self, key: Hashable, value: Any) -> None:
        with self._lock:
            now = time.monotonic()
            self._maybe_purge_expired_locked(now)
            self._remove_locked(key)
            size_bytes = (
                estimate_size_bytes(value, stop_at=self._max_bytes + 1)
                if self._max_bytes
                else 0
            )
            if self._max_bytes > 0 and size_bytes > self._max_bytes:
                self._capacity_evictions += 1
                return
            self._store[key] = (now, value, size_bytes)
            self._estimated_bytes += size_bytes
            self._store.move_to_end(key)
            self._enforce_limits_locked()

    def delete(self, key: Hashable) -> None:
        with self._lock:
            self._remove_locked(key)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._estimated_bytes = 0
            self._next_sweep = 0.0

    def prune(self) -> int:
        """Release every expired entry and return the number removed."""
        with self._lock:
            return self._purge_expired_locked(time.monotonic())

    def stats(self) -> dict[str, int]:
        """Return safe cache diagnostics without exposing keys or values."""
        with self._lock:
            self._purge_expired_locked(time.monotonic())
            return {
                "items": len(self._store),
                "max_items": self._max_items,
                "estimated_bytes": self._estimated_bytes,
                "max_bytes": self._max_bytes,
                "expired_evictions": self._expired_evictions,
                "capacity_evictions": self._capacity_evictions,
            }


_refresh_guard = threading.Lock()
_refresh_inflight: set[tuple[int, str]] = set()


def background_refresh(cache: TTLCache, key: str, compute: Callable[[], Any]) -> None:
    """Populate the cache entry on a background daemon thread."""
    token = (id(cache), key)

    with _refresh_guard:
        if token in _refresh_inflight:
            return
        _refresh_inflight.add(token)

    def _runner() -> None:
        try:
            payload = compute()
            cache.set(key, payload)
        except Exception:  # pragma: no cover - defensive logging
            import logging

            logging.exception("Background cache refresh failed for key %s", key)
        finally:
            with _refresh_guard:
                _refresh_inflight.discard(token)

    threading.Thread(target=_runner, name=f"cache-refresh-{key}", daemon=True).start()


def load_json_snapshot(path: str) -> Optional[dict[str, Any]]:
    file_path = Path(path)
    if not file_path.exists():
        return None
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:  # pragma: no cover
        return None


def save_json_snapshot(path: str, payload: dict[str, Any]) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

