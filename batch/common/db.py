import os
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

import oracledb

from .env_bootstrap import load_default_env

load_default_env()

_pool: Optional[oracledb.ConnectionPool] = None


def init_pool() -> oracledb.ConnectionPool:
    global _pool
    if _pool:
        return _pool
    user = os.getenv('DB_USER') or os.getenv('ORACLE_USER')
    password = os.getenv('DB_PASSWORD') or os.getenv('ORACLE_PASSWORD')
    dsn = os.getenv('DB_DSN') or os.getenv('ORACLE_DSN')
    if not dsn:
        host = os.getenv('ORACLE_HOST', '127.0.0.1')
        port = os.getenv('ORACLE_PORT', '1521')
        service_name = os.getenv('ORACLE_SERVICE_NAME') or os.getenv('ORACLE_SERVICE')
        sid = os.getenv('ORACLE_SID')
        if host and port and (service_name or sid):
            dsn = f"{host}:{port}/{service_name or sid}"
    if not user or not password or not dsn:
        raise RuntimeError('DB_USER, DB_PASSWORD, and DB_DSN must be set')
    _pool = oracledb.create_pool(user=user, password=password, dsn=dsn, min=1, max=4, increment=1)
    return _pool


@contextmanager
def get_connection():
    pool = init_pool()
    conn = pool.acquire()
    try:
        yield conn
    finally:
        conn.close()


def fetch_all(sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params or {})
        columns = [d[0].lower() for d in cursor.description]
        rows = cursor.fetchall()
        return [{columns[i]: row[i] for i in range(len(columns))} for row in rows]


def execute_many(sql: str, params: List[Dict[str, Any]]) -> int:
    if not params:
        return 0
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.executemany(sql, params)
        conn.commit()
        return cursor.rowcount


def execute(sql: str, params: Optional[Dict[str, Any]] = None) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params or {})
        conn.commit()
        return cursor.rowcount
