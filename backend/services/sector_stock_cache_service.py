from __future__ import annotations

import json
import os
import re
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any

try:
    from cache import estimate_size_bytes
except ImportError:  # pragma: no cover - package import path
    from backend.cache import estimate_size_bytes


_SAFE_NAME_RE = re.compile(r'^[A-Z0-9_]+$')


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, '')).strip().lower()
    if not raw:
        return default
    return raw in {'1', 'true', 'yes', 'y', 'on'}


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, str(default))).strip() or default)
    except (TypeError, ValueError):
        return default


class SectorStockCacheService:
    def __init__(self, *, max_items: int | None = None, max_bytes: int | None = None) -> None:
        self._memory: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._entry_sizes: dict[str, int] = {}
        self._estimated_bytes = 0
        self._max_items = max(1, int(max_items or _env_int('SECTOR_STOCK_CACHE_MAX_ITEMS', 24)))
        default_bytes = max(1, _env_int('SECTOR_STOCK_CACHE_MAX_MEMORY_MB', 128)) * 1024 * 1024
        self._max_bytes = max(1, int(max_bytes or default_bytes))
        self._expired_evictions = 0
        self._capacity_evictions = 0
        self._lock = Lock()
        self.cache_enabled = _env_bool('SECTOR_STOCK_CACHE_ENABLED', True)
        self.snapshot_enabled = _env_bool('SECTOR_STOCK_SNAPSHOT_ENABLED', True)
        self.snapshot_ttl_seconds = max(60, int(os.getenv('SECTOR_STOCK_SNAPSHOT_TTL_SECONDS', '3600')))
        self.cache_version = str(os.getenv('SECTOR_STOCK_CACHE_VERSION', 'v7')).strip() or 'v7'
        self.snapshot_dir = Path(__file__).resolve().parents[1] / 'cache' / 'sector_snapshots'

    def _remove_memory_locked(self, cache_key: str) -> None:
        self._memory.pop(cache_key, None)
        self._estimated_bytes = max(0, self._estimated_bytes - self._entry_sizes.pop(cache_key, 0))

    def _purge_expired_memory_locked(self, now: datetime) -> int:
        stale_keys = [
            key
            for key, entry in self._memory.items()
            if str(entry.get('cacheVersion') or '').strip() != self.cache_version
            or not isinstance(entry.get('expiresAt'), datetime)
            or now >= entry['expiresAt']
        ]
        for key in stale_keys:
            self._remove_memory_locked(key)
        self._expired_evictions += len(stale_keys)
        return len(stale_keys)

    def _enforce_memory_limits_locked(self) -> None:
        while self._memory and (
            len(self._memory) > self._max_items or self._estimated_bytes > self._max_bytes
        ):
            self._remove_memory_locked(next(iter(self._memory)))
            self._capacity_evictions += 1

    def _utc_now(self) -> datetime:
        return datetime.utcnow()

    def sanitize_snapshot_filename(self, table_name: str) -> str:
        token = str(table_name or '').strip().upper()
        if not token:
            raise ValueError('Empty table name')
        if not _SAFE_NAME_RE.fullmatch(token):
            raise ValueError('Unsafe table name for snapshot file')
        return f'{token}.json'

    def _snapshot_path(self, table_name: str) -> Path:
        return self.snapshot_dir / self.sanitize_snapshot_filename(table_name)

    def _load_snapshot_payload(self, table_name: str) -> dict[str, Any] | None:
        if not self.snapshot_enabled:
            return None
        try:
            snapshot_file = self._snapshot_path(table_name)
        except Exception:
            return None
        if not snapshot_file.exists():
            return None
        try:
            payload = json.loads(snapshot_file.read_text(encoding='utf-8'))
            if not isinstance(payload, dict):
                return None
            if str(payload.get('cacheVersion') or '').strip() != self.cache_version:
                return None
            expires_at_text = str(payload.get('expiresAt') or '').strip()
            if not expires_at_text:
                return None
            expires_at = datetime.fromisoformat(expires_at_text)
            rows = payload.get('rows')
            if not isinstance(rows, list):
                return None
            return {
                'cacheVersion': self.cache_version,
                'tableName': str(payload.get('tableName') or '').strip().upper(),
                'sectorName': str(payload.get('sectorName') or '').strip(),
                'rows': rows,
                'totalRows': int(payload.get('totalRows') or len(rows)),
                'loadedAt': str(payload.get('loadedAt') or '').strip(),
                'expiresAt': expires_at,
                'ttlSeconds': int(payload.get('ttlSeconds') or self.snapshot_ttl_seconds),
            }
        except Exception:
            return None

    def get_memory_cache(self, cache_key: str) -> dict[str, Any] | None:
        if not self.cache_enabled:
            return None
        now = self._utc_now()
        with self._lock:
            self._purge_expired_memory_locked(now)
            entry = self._memory.get(cache_key)
            if not entry:
                return None
            expires_at = entry['expiresAt']
            self._memory.move_to_end(cache_key)
            return {
                'cacheVersion': self.cache_version,
                'tableName': entry.get('tableName'),
                'sectorName': entry.get('sectorName'),
                'rows': entry.get('rows') or [],
                'totalRows': int(entry.get('totalRows') or 0),
                'loadedAt': entry.get('loadedAt'),
                'expiresAt': expires_at,
                'ttlSeconds': int(entry.get('ttlSeconds') or 0),
            }

    def set_memory_cache(
        self,
        cache_key: str,
        *,
        table_name: str,
        sector_name: str,
        rows: list[dict[str, Any]],
        ttl_seconds: int,
    ) -> dict[str, Any]:
        ttl = max(1, int(ttl_seconds))
        now = self._utc_now()
        payload = {
            'cacheVersion': self.cache_version,
            'tableName': str(table_name or '').strip().upper(),
            'sectorName': str(sector_name or '').strip(),
            'rows': list(rows or []),
            'totalRows': len(rows or []),
            'loadedAt': now,
            'expiresAt': now + timedelta(seconds=ttl),
            'ttlSeconds': ttl,
        }
        if not self.cache_enabled:
            return payload
        with self._lock:
            self._purge_expired_memory_locked(now)
            self._remove_memory_locked(cache_key)
            size_bytes = estimate_size_bytes(payload, stop_at=self._max_bytes + 1)
            if size_bytes > self._max_bytes:
                self._capacity_evictions += 1
                return payload
            self._memory[cache_key] = payload
            self._entry_sizes[cache_key] = size_bytes
            self._estimated_bytes += size_bytes
            self._memory.move_to_end(cache_key)
            self._enforce_memory_limits_locked()
        return payload

    def delete_memory_cache(self, cache_key: str) -> None:
        with self._lock:
            self._remove_memory_locked(cache_key)

    def clear_sector_memory_cache(self) -> None:
        with self._lock:
            self._memory.clear()
            self._entry_sizes.clear()
            self._estimated_bytes = 0

    def prune_memory_cache(self) -> int:
        with self._lock:
            return self._purge_expired_memory_locked(self._utc_now())

    def memory_stats(self) -> dict[str, int]:
        with self._lock:
            self._purge_expired_memory_locked(self._utc_now())
            return {
                'items': len(self._memory),
                'max_items': self._max_items,
                'estimated_bytes': self._estimated_bytes,
                'max_bytes': self._max_bytes,
                'expired_evictions': self._expired_evictions,
                'capacity_evictions': self._capacity_evictions,
            }

    def get_snapshot(self, table_name: str) -> dict[str, Any] | None:
        payload = self._load_snapshot_payload(table_name)
        if payload is None:
            return None
        if self._utc_now() >= payload.get('expiresAt'):
            return None
        return payload

    def peek_snapshot(self, table_name: str) -> dict[str, Any] | None:
        return self._load_snapshot_payload(table_name)

    def set_snapshot(
        self,
        table_name: str,
        *,
        sector_name: str,
        rows: list[dict[str, Any]],
        ttl_seconds: int | None = None,
    ) -> Path | None:
        if not self.snapshot_enabled:
            return None
        ttl = max(1, int(ttl_seconds or self.snapshot_ttl_seconds))
        now = self._utc_now()
        expires_at = now + timedelta(seconds=ttl)
        payload = {
            'cacheVersion': self.cache_version,
            'tableName': str(table_name or '').strip().upper(),
            'sectorName': str(sector_name or '').strip(),
            'rows': list(rows or []),
            'totalRows': len(rows or []),
            'loadedAt': now.isoformat(),
            'expiresAt': expires_at.isoformat(),
            'ttlSeconds': ttl,
        }
        try:
            file_path = self._snapshot_path(table_name)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(json.dumps(payload, ensure_ascii=True), encoding='utf-8')
            return file_path
        except Exception:
            return None

    def delete_snapshot(self, table_name: str) -> None:
        if not self.snapshot_enabled:
            return
        try:
            snapshot_file = self._snapshot_path(table_name)
            if snapshot_file.exists():
                snapshot_file.unlink()
        except Exception:
            return


sector_stock_cache_service = SectorStockCacheService()
