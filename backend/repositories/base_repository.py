from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

try:
    from backend.db import get_oracle_connection
except Exception:  # pragma: no cover
    from db import get_oracle_connection  # type: ignore


class BaseRepository:
    """Small forward-standard base class for new repository modules."""

    @contextmanager
    def connection(self) -> Iterator[object]:
        conn = get_oracle_connection()
        try:
            yield conn
        finally:
            conn.close()
