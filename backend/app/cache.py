import time
from collections import OrderedDict
from typing import Any, Optional


class SimpleCache:
    def __init__(self, max_items: int = 256, ttl_seconds: int = 30):
        self._max_items = max_items
        self._ttl = ttl_seconds
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        now = time.time()
        entry = self._data.get(key)
        if not entry:
            return None
        expires_at, value = entry
        if expires_at < now:
            self._data.pop(key, None)
            return None
        self._data.move_to_end(key)
        return value

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self._ttl
        expires_at = time.time() + ttl
        self._data[key] = (expires_at, value)
        self._data.move_to_end(key)
        while len(self._data) > self._max_items:
            self._data.popitem(last=False)

    def clear(self) -> None:
        self._data.clear()
