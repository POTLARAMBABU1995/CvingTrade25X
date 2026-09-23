import logging
from typing import Any, Dict, Iterable, List, Optional

import oracledb

from .config import get_settings

logger = logging.getLogger(__name__)
_pool: Optional[oracledb.ConnectionPool] = None


def init_pool() -> oracledb.ConnectionPool:
    global _pool
    if _pool:
        return _pool
    settings = get_settings()
    if not settings.db_user or not settings.db_password or not settings.db_dsn:
        raise RuntimeError('DB_USER, DB_PASSWORD, and DB_DSN must be set')
    _pool = oracledb.create_pool(
        user=settings.db_user,
        password=settings.db_password,
        dsn=settings.db_dsn,
        min=settings.db_pool_min,
        max=settings.db_pool_max,
        increment=settings.db_pool_increment,
        timeout=settings.db_pool_timeout,
        getmode=oracledb.POOL_GETMODE_WAIT,
    )
    logger.info('db.pool.ready', extra={'min': settings.db_pool_min, 'max': settings.db_pool_max})
    return _pool


def close_pool() -> None:
    global _pool
    if _pool:
        _pool.close()
        _pool = None


def _row_to_dict(columns: Iterable[str], row: Iterable[Any]) -> Dict[str, Any]:
    return {col: row[idx] for idx, col in enumerate(columns)}


def fetch_all(sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    pool = init_pool()
    with pool.acquire() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params or {})
        columns = [d[0].lower() for d in cursor.description]
        rows = cursor.fetchall()
        return [_row_to_dict(columns, row) for row in rows]


def fetch_one(sql: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    pool = init_pool()
    with pool.acquire() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params or {})
        row = cursor.fetchone()
        if not row:
            return None
        columns = [d[0].lower() for d in cursor.description]
        return _row_to_dict(columns, row)


def execute(sql: str, params: Optional[Dict[str, Any]] = None) -> int:
    pool = init_pool()
    with pool.acquire() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params or {})
        conn.commit()
        return cursor.rowcount
