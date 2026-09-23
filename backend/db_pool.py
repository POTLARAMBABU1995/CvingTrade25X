# backend/db_pool.py
import os
import threading
import oracledb

try:
    from .env_bootstrap import load_default_env  # type: ignore
except Exception:  # pragma: no cover
    from env_bootstrap import load_default_env  # type: ignore

load_default_env()

def build_dsn() -> tuple[str, str, str]:
    user = os.getenv("ORACLE_USER", "CVING_APP")
    pwd  = os.getenv("ORACLE_PASSWORD", "")
    if os.getenv("CVING_MCP_PROCESS_READONLY") == "1":
        user = os.getenv("CVING_MCP_ORACLE_USER") or user
        pwd = os.getenv("CVING_MCP_ORACLE_PASSWORD") or pwd
    direct_dsn = (os.getenv("ORACLE_DSN") or "").strip()
    if direct_dsn:
        return user, pwd, direct_dsn
    host = os.getenv("ORACLE_HOST", "127.0.0.1")
    port = int(os.getenv("ORACLE_PORT", "1521"))
    sid = os.getenv("ORACLE_SID")
    service_name = os.getenv("ORACLE_SERVICE_NAME") or os.getenv("ORACLE_SERVICE")
    if sid:
        dsn = oracledb.makedsn(host, port, sid=sid)
    else:
        dsn = oracledb.makedsn(host, port, service_name=(service_name or "cvingpdb.local"))
    return user, pwd, dsn

USER, PWD, DSN = build_dsn()
_POOL_LOCK = threading.Lock()

def _create_pool():
    mcp_readonly = os.getenv("CVING_MCP_PROCESS_READONLY") == "1"
    options = dict(min=1, max=6)
    if mcp_readonly:
        from backend.mcp_server.database_guard import ReadOnlyPool, pool_options
        options = pool_options(oracledb)
    created = oracledb.create_pool(
        user=USER,
        password=PWD,
        dsn=DSN,
        **options,
        increment=1,
        stmtcachesize=100,
        homogeneous=True,
    )
    if mcp_readonly:
        return ReadOnlyPool(created, int(os.getenv("CVING_MCP_DB_QUERY_TIMEOUT_MS", "15000")),
                            int(os.getenv("CVING_MCP_MAX_ROWS", "5000")))
    return created

pool = _create_pool()

def recreate_pool():
    global USER, PWD, DSN, pool
    with _POOL_LOCK:
        previous_pool = pool
        USER, PWD, DSN = build_dsn()
        pool = _create_pool()
        try:
            previous_pool.close(force=True)
        except Exception:
            pass
        return pool

def fetchall_dict(cur):
    cols = [d[0].lower() for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]
