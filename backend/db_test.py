# backend/db_test.py
import os
import sys
import pprint

try:
    from .env_bootstrap import load_default_env  # type: ignore
except Exception:  # pragma: no cover
    from env_bootstrap import load_default_env  # type: ignore

try:
    import oracledb
except Exception as e:
    print("ERROR: Failed to import oracledb:", e)
    sys.exit(1)

load_default_env()

def _build_dsn():
    user = os.getenv("ORACLE_USER", "CVING_APP")
    pwd = os.getenv("ORACLE_PASSWORD", "")
    host = os.getenv("ORACLE_HOST", "127.0.0.1")
    port = os.getenv("ORACLE_PORT", "1521")
    service_name = os.getenv("ORACLE_SERVICE_NAME") or os.getenv("ORACLE_SERVICE") or "cvingpdb.local"
    dsn = f"{host}:{port}/{service_name}"
    return user, pwd, dsn

def try_connect(user, pwd, dsn):
    # If you have Oracle Instant Client and set ORACLE_LIB_DIR, initialize thick mode
    lib_dir = os.getenv("ORACLE_LIB_DIR")
    if lib_dir:
        try:
            oracledb.init_oracle_client(lib_dir=lib_dir)
            print("Initialized Oracle client from:", lib_dir)
        except Exception as e:
            print("Warning: init_oracle_client() failed:", e)

    # Try the connection using a couple of signatures to be compatible with different driver
    try:
        # some versions accept encoding/encoding errors; try it first
        conn = oracledb.connect(user=user, password=pwd, dsn=dsn, encoding="UTF-8")
        return conn
    except TypeError:
        # old/new driver refused encoding argument — try without
        try:
            conn = oracledb.connect(user=user, password=pwd, dsn=dsn)
            return conn
        except Exception as e:
            raise
    except Exception:
        # bubble up other errors
        raise

def test_db_fetch():
    user, pwd, dsn = _build_dsn()
    print("Trying DSN:", dsn, "user:", user)
    try:
        conn = try_connect(user, pwd, dsn)
        print("Connected OK. Server version:", getattr(conn, "version", "unknown"))
        cur = conn.cursor()
        # quick sanity query - change table name if different
        cur.execute("SELECT SYMBOL, TRADING_DATE, LTP FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV WHERE ROWNUM <= 5 ORDER BY TRADING_DATE DESC")
        rows = cur.fetchall()
        print("Sample rows (up to 5):")
        pp = pprint.PrettyPrinter(width=140)
        pp.pprint(rows)
        cur.close()
        conn.close()
    except Exception as ex:
        print("DB connection failed:", repr(ex))
        # helpful hints
        if "DPI-1047" in repr(ex) or "ORA-3136" in repr(ex) or "DLL" in repr(ex) or "client library" in repr(ex).lower():
            print("\nHINT: DPI-1047 or similar indicates Oracle Instant Client is needed.")
            print(" - Download Instant Client (basic) from Oracle and set ORACLE_LIB_DIR to its folder, or")
            print(" - Install python-oracledb and use thin mode (no instant client) if your environment allows it.")
        if "ORA-12541" in repr(ex) or "TNS:no listener" in repr(ex):
            print("\nHINT: Listener down or wrong host/port/SID. Check the DB is running and listener is up.")
        sys.exit(1)

if __name__ == "__main__":
    test_db_fetch()
