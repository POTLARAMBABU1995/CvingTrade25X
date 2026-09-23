from __future__ import annotations

import asyncio
import logging
from typing import Any

import oracledb

from .config import settings

logger = logging.getLogger(__name__)


class OraclePool:
    """Async Oracle connection pool wrapper."""

    __slots__ = ("_pool", "_lock")

    def __init__(self) -> None:
        self._pool: oracledb.AsyncConnectionPool | None = None
        self._lock = asyncio.Lock()

    async def init(self) -> None:
        async with self._lock:
            if self._pool is not None:
                return
            logger.info("Creating Oracle connection pool")
            self._pool = await oracledb.create_pool(
                user=settings.oracle_user,
                password=settings.oracle_password,
                dsn=settings.oracle_dsn,
                min=settings.oracle_min_pool,
                max=settings.oracle_max_pool,
                increment=settings.oracle_pool_increment,
                stmtcachesize=settings.oracle_stmt_cache_size,
                getmode=oracledb.SPOOL_ATTRVAL_WAIT,
            )

    async def close(self) -> None:
        if self._pool is None:
            return
        await self._pool.close()
        self._pool = None

    async def acquire(self) -> oracledb.AsyncConnection:
        if self._pool is None:
            await self.init()
        assert self._pool is not None
        return await self._pool.acquire()

    async def release(self, conn: oracledb.AsyncConnection) -> None:
        if self._pool is None:
            return
        await self._pool.release(conn)

    def stats(self) -> dict[str, Any]:
        pool = self._pool
        if pool is None:
            return {}
        return {
            "open": pool.opened,
            "busy": pool.busy,
            "timeout": pool.timeout,
        }


oracle_pool = OraclePool()
