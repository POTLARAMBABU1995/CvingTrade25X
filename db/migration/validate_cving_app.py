from __future__ import annotations

import json
import os
from pathlib import Path

import oracledb


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_DIR = Path(__file__).resolve().parent
REPORT_PATH = MIGRATION_DIR / "validation_report.json"


def load_env() -> None:
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


load_env()


def get_connection():
    host = os.getenv("ORACLE_HOST", "127.0.0.1").strip()
    port = os.getenv("ORACLE_PORT", "1521").strip()
    service_name = (os.getenv("ORACLE_SERVICE_NAME") or os.getenv("ORACLE_SERVICE") or "cvingpdb.local").strip()
    dsn = (os.getenv("ORACLE_DSN") or f"{host}:{port}/{service_name}").strip()
    return oracledb.connect(
        user=os.getenv("ORACLE_USER", "CVING_APP").strip(),
        password=os.getenv("ORACLE_PASSWORD", "").strip(),
        dsn=dsn,
    )


REQUIRED_OBJECTS = {
    "TABLE": [
        "STOCK_EOD_HISTORY",
        "NSE_NIFTY500_DAILY_RAW_DATA_DEV",
        "NSE_NIFTY500_DAILY_RAW_DATA_ORACLE",
        "DIM_SYMBOLS",
        "FACT_OHLCV",
        "NSE_NIFTY50_LARGECAP",
        "NSE_NIFTY150_MIDCAP",
        "NSE_NIFTY250_SMALLCAP",
        "NSE_SECTOR_MASTER",
        "NSE_SYMBOL_SECTOR_MAP",
        "CVING_NSE_MARKET_CAP_HIST",
        "CVING_NSE_FFMC_HIST",
        "ASURA_BULLISH_TREND_STRATEGY_TESTING",
        "ASURA_SCAN_DAILY_FACT",
        "GAINERS_TOP25",
        "LOOSERS_TOP25",
        "VOLUME_MOVERS_TOP25",
        "CVING_STRATEGY_PARAMS",
        "CVING_STRATEGY_AGENT_RUNS",
        "CVING_STRATEGY_AGENT_BACKTESTS",
        "PRICE_ACTION_SR_LEVELS_MANUALLY",
        "REGISTRATIONS",
        "AUTH_SESSIONS",
        "AUTH_QUICK_MPIN",
        "LOGIN_ACTIVITY",
        "FYERS_HOLDINGS_IMPORTS",
        "FYERS_HOLDINGS_CURRENT",
        "FYERS_HOLDINGS_AUDIT",
    ],
    "VIEW": [
        "V_STOCK_EOD_HISTORY",
        "V_NSE500_EMA_DAILY",
        "V_NSE500_EMA_MONTHLY",
        "V_NSE500_EMA_YEARLY",
        "V_NSE_NIFTY50_LARGECAP_OHLCV",
        "V_NSE_NIFTY150_MIDCAP_OHLCV",
        "V_NSE_NIFTY250_SMALLCAP_OHLCV",
        "VW_SYMBOL_CAP_BUCKET",
        "VW_NSE_CANONICAL_SECTOR_STAGE",
        "V_ASURA_SCAN_LATEST",
    ],
    "PROCEDURE": [
        "PR_SYNC_DIM_SYMBOLS_FROM_DEV",
        "PR_MERGE_FACT_OHLCV_FROM_DEV",
        "PR_SYNC_FACT_OHLCV_FROM_DEV",
        "PR_SYNC_DIM_SYMBOLS_CAP_SEG_FROM_INDICES",
        "PR_SYNC_NSE_SYMBOL_SECTOR_MAP_FROM_STAGING",
        "PR_SYNC_SECTOR_REFERENCE_DATA",
    ],
    "PACKAGE": ["ST25X_ETL_PKG"],
    "FUNCTION": ["NORMALIZE_SYMBOL"],
    "TRIGGER": ["TRG_STOCK_EOD_HISTORY_NORM"],
    "MATERIALIZED VIEW": ["MV_NSE_SECTOR_UI_SNAPSHOT"],
    "SEQUENCE": ["ASURA_BTS_SEQ"],
}

ROW_COUNT_TABLES = [
    "NSE_NIFTY500_DAILY_RAW_DATA_DEV",
    "NSE_NIFTY500_DAILY_RAW_DATA_ORACLE",
    "STOCK_EOD_HISTORY",
    "FACT_OHLCV",
    "DIM_SYMBOLS",
    "GAINERS_TOP25",
    "LOOSERS_TOP25",
    "VOLUME_MOVERS_TOP25",
]


def fetch_scalar(cur, sql: str, binds: dict | None = None):
    cur.execute(sql, binds or {})
    row = cur.fetchone()
    return row[0] if row else None


def main() -> int:
    report: dict[str, object] = {
        "required_objects": {},
        "row_counts": {},
    }
    with get_connection() as conn:
        with conn.cursor() as cur:
            report["connection"] = {
                "user": fetch_scalar(cur, "SELECT USER FROM dual"),
                "db_name": fetch_scalar(cur, "SELECT SYS_CONTEXT('USERENV', 'DB_NAME') FROM dual"),
                "con_name": fetch_scalar(cur, "SELECT SYS_CONTEXT('USERENV', 'CON_NAME') FROM dual"),
                "default_tablespace": fetch_scalar(cur, "SELECT default_tablespace FROM user_users"),
                "temporary_tablespace": fetch_scalar(cur, "SELECT temporary_tablespace FROM user_users"),
            }

            required_summary: dict[str, list[dict[str, object]]] = {}
            for object_type, names in REQUIRED_OBJECTS.items():
                bucket: list[dict[str, object]] = []
                for name in names:
                    if object_type == "SEQUENCE":
                        exists = int(
                            fetch_scalar(
                                cur,
                                "SELECT COUNT(*) FROM user_sequences WHERE sequence_name = :name",
                                {"name": name},
                            )
                            or 0
                        ) > 0
                    else:
                        exists = int(
                            fetch_scalar(
                                cur,
                                "SELECT COUNT(*) FROM user_objects WHERE object_type = :object_type AND object_name = :name",
                                {"object_type": object_type, "name": name},
                            )
                            or 0
                        ) > 0
                    bucket.append({"name": name, "exists": exists})
                required_summary[object_type] = bucket
            report["required_objects"] = required_summary

            invalid_objects = []
            cur.execute(
                """
                SELECT object_type, object_name, status
                FROM user_objects
                WHERE status <> 'VALID'
                ORDER BY object_type, object_name
                """
            )
            for object_type, object_name, status in cur.fetchall() or []:
                invalid_objects.append(
                    {"object_type": object_type, "object_name": object_name, "status": status}
                )
            report["invalid_objects"] = invalid_objects

            row_counts: dict[str, int | None] = {}
            for table_name in ROW_COUNT_TABLES:
                try:
                    row_counts[table_name] = int(fetch_scalar(cur, f'SELECT COUNT(*) FROM "{table_name}"') or 0)
                except Exception:
                    row_counts[table_name] = None
            report["row_counts"] = row_counts

            cur.execute(
                """
                SELECT segment_type, segment_name, tablespace_name, bytes
                FROM user_segments
                WHERE tablespace_name IN ('SYSTEM', 'SYSAUX')
                ORDER BY segment_type, segment_name
                """
            )
            report["system_tablespace_segments"] = [
                {
                    "segment_type": segment_type,
                    "segment_name": segment_name,
                    "tablespace_name": tablespace_name,
                    "bytes": int(bytes_value or 0),
                }
                for segment_type, segment_name, tablespace_name, bytes_value in (cur.fetchall() or [])
            ]

    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Validation completed. Report: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

