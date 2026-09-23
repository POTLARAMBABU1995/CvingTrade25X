from __future__ import annotations

import os
from collections import OrderedDict
from datetime import datetime, timedelta
from threading import Lock
from typing import Any

try:
    from cache import estimate_size_bytes
except ImportError:  # pragma: no cover - package import path
    from backend.cache import estimate_size_bytes


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, str(default))).strip() or default)
    except (TypeError, ValueError):
        return default


class SectorCacheService:
    def __init__(self, *, max_items: int | None = None, max_bytes: int | None = None) -> None:
        self._cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._entry_sizes: dict[str, int] = {}
        self._estimated_bytes = 0
        self._max_items = max(1, int(max_items or _env_int('SECTOR_CACHE_MAX_ITEMS', 48)))
        default_bytes = max(1, _env_int('SECTOR_CACHE_MAX_MEMORY_MB', 96)) * 1024 * 1024
        self._max_bytes = max(1, int(max_bytes or default_bytes))
        self._expired_evictions = 0
        self._capacity_evictions = 0
        self._lock = Lock()

    def _remove_locked(self, key: str) -> None:
        self._cache.pop(key, None)
        self._estimated_bytes = max(0, self._estimated_bytes - self._entry_sizes.pop(key, 0))

    def _purge_expired_locked(self, now: datetime) -> int:
        stale_keys = [
            key
            for key, entry in self._cache.items()
            if not isinstance(entry.get('expires_at'), datetime) or now >= entry['expires_at']
        ]
        for key in stale_keys:
            self._remove_locked(key)
        self._expired_evictions += len(stale_keys)
        return len(stale_keys)

    def _enforce_limits_locked(self) -> None:
        while self._cache and (
            len(self._cache) > self._max_items or self._estimated_bytes > self._max_bytes
        ):
            self._remove_locked(next(iter(self._cache)))
            self._capacity_evictions += 1

    def get_cache(self, key: str) -> dict[str, Any] | None:
        now = datetime.utcnow()
        with self._lock:
            self._purge_expired_locked(now)
            entry = self._cache.get(key)
            if not entry:
                return None
            expires_at = entry['expires_at']
            self._cache.move_to_end(key)
            return {
                'data': entry.get('data'),
                'loaded_at': entry.get('loaded_at'),
                'expires_at': expires_at,
                'ttl_seconds': entry.get('ttl_seconds'),
            }

    def set_cache(self, key: str, data: Any, ttl_seconds: int) -> dict[str, Any]:
        ttl = max(1, int(ttl_seconds))
        now = datetime.utcnow()
        payload = {
            'data': data,
            'loaded_at': now,
            'expires_at': now + timedelta(seconds=ttl),
            'ttl_seconds': ttl,
        }
        with self._lock:
            self._purge_expired_locked(now)
            self._remove_locked(key)
            size_bytes = estimate_size_bytes(payload, stop_at=self._max_bytes + 1)
            if size_bytes > self._max_bytes:
                self._capacity_evictions += 1
                return payload
            self._cache[key] = payload
            self._entry_sizes[key] = size_bytes
            self._estimated_bytes += size_bytes
            self._cache.move_to_end(key)
            self._enforce_limits_locked()
        return payload

    def delete_cache(self, key: str) -> None:
        with self._lock:
            self._remove_locked(key)

    def clear_sector_cache(self) -> None:
        with self._lock:
            self._cache.clear()
            self._entry_sizes.clear()
            self._estimated_bytes = 0

    def prune(self) -> int:
        with self._lock:
            return self._purge_expired_locked(datetime.utcnow())

    def stats(self) -> dict[str, int]:
        with self._lock:
            self._purge_expired_locked(datetime.utcnow())
            return {
                'items': len(self._cache),
                'max_items': self._max_items,
                'estimated_bytes': self._estimated_bytes,
                'max_bytes': self._max_bytes,
                'expired_evictions': self._expired_evictions,
                'capacity_evictions': self._capacity_evictions,
            }


sector_cache_service = SectorCacheService()
