from __future__ import annotations

import base64
import copy
import datetime as dt
import csv
import hashlib
import json
import logging
import math
import os
import re
import subprocess
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Callable, Literal, Optional
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import oracledb
import pandas as pd

try:  # Support execution via package or direct script
    from ..db_pool import fetchall_dict, pool
    from .job_memory_policy import prune_finished_jobs
except ImportError:  # pragma: no cover
    from db_pool import fetchall_dict, pool  # type: ignore
    from services.job_memory_policy import prune_finished_jobs  # type: ignore

MAX_LIMIT = 5000
DEFAULT_LIMIT = 200
VALID_TIMEFRAMES = ("daily", "weekly", "monthly", "yearly")
SYNC_PROC = os.getenv("STOCK_SYNC_PROC", "PR_SYNC_STOCK_NEW_ROWS")
SYNC_TARGET = os.getenv("STOCK_SYNC_TARGET", "DEV_ORACLE")
DBMS_OUTPUT_MAX_LINES = 2000
SOURCE_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_$#\.]*$")
_MD_ORACLE_SCHEMA = str(os.getenv("ORACLE_SCHEMA", "")).strip().upper()
_MD_ORACLE_TABLE = str(os.getenv("ORACLE_TABLE", "NSE_NIFTY500_DAILY_RAW_DATA_DEV")).strip().upper()
_MD_ORACLE_QUALIFIED = f"{_MD_ORACLE_SCHEMA}.{_MD_ORACLE_TABLE}" if _MD_ORACLE_SCHEMA else _MD_ORACLE_TABLE
DEFAULT_SUMMARY_SOURCES = ",".join(
    item
    for item in (
        _MD_ORACLE_QUALIFIED,
        _MD_ORACLE_TABLE,
        "V_STOCK_EOD_HISTORY",
        "STOCK_EOD_HISTORY",
    )
    if item
)
SUMMARY_SOURCES_ENV = os.getenv("MARKETDATA_SUMMARY_SOURCES", DEFAULT_SUMMARY_SOURCES)
_summary_sources_seen: set[str] = set()
_summary_sources_list: list[str] = []
for _candidate in SUMMARY_SOURCES_ENV.split(","):
    _token = _candidate.strip().upper()
    if not _token or _token in _summary_sources_seen:
        continue
    _summary_sources_seen.add(_token)
    _summary_sources_list.append(_token)
SUMMARY_SOURCES: tuple[str, ...] = tuple(_summary_sources_list)
_SUMMARY_SOURCE_CACHE: Optional[str] = None
_SUMMARY_SOURCE_META_CACHE: dict[str, dict[str, str]] = {}
STOCK_EOD_TABLE_ENV = "MARKETDATA_STOCK_EOD_TABLE"
DEFAULT_STOCK_EOD_TABLE = "STOCK_EOD_HISTORY"
MARKETDATA_ORACLE_SYNC_TABLE_ENV = "MARKETDATA_ORACLE_SYNC_TABLE"
DEFAULT_MARKETDATA_ORACLE_SYNC_TABLE = "NSE_NIFTY500_DAILY_RAW_DATA_ORACLE"
_logger = logging.getLogger(__name__)
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, str(default))).strip())
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(str(os.getenv(name, str(default))).strip())
    except (TypeError, ValueError):
        return default


def _env_str(name: str, default: str = "") -> str:
    return str(os.getenv(name, default)).strip()


STOCK_EOD_MERGED_RETENTION_DAYS = max(1, _env_int("STOCK_EOD_MERGED_RETENTION_DAYS", 7))
STOCK_EOD_CURRENT_DAY_ELIGIBLE_HOUR = min(
    23,
    max(0, _env_int("STOCK_EOD_CURRENT_DAY_ELIGIBLE_HOUR", 17)),
)
DEFAULT_FYERS_PROJECT_DIR = r"D:\fyers_api_integration"
FYERS_PROJECT_DIR = os.getenv("FYERS_PROJECT_DIR", DEFAULT_FYERS_PROJECT_DIR).strip() or DEFAULT_FYERS_PROJECT_DIR
FYERS_PYTHON_EXE = os.getenv("FYERS_PYTHON_EXE", "").strip()
FYERS_LOG_TAIL_LINES = _env_int("FYERS_LOG_TAIL_LINES", 80)
FYERS_AUTH_TIMEOUT_SEC = _env_int("FYERS_AUTH_TIMEOUT_SEC", 600)
FYERS_SINGLE_TIMEOUT_SEC = _env_int("FYERS_SINGLE_TIMEOUT_SEC", 3600)
FYERS_BATCH_TIMEOUT_SEC = _env_int("FYERS_BATCH_TIMEOUT_SEC", 21600)
FYERS_JOB_TTL_SEC = _env_int("FYERS_JOB_TTL_SEC", 43200)
FYERS_JOB_MAX_LINES = _env_int("FYERS_JOB_MAX_LINES", 4000)
FYERS_JOB_MAX_RETAINED = max(1, _env_int("FYERS_JOB_MAX_RETAINED", 6))
FYERS_JOB_DEFAULT_TAIL = _env_int("FYERS_JOB_DEFAULT_TAIL", 220)
FYERS_JOB_LOCK_TIMEOUT_SEC = max(0.2, _env_float("FYERS_JOB_LOCK_TIMEOUT_SEC", 1.5))
FYERS_FAILED_SYMBOLS_CACHE_TTL_SEC = max(0.0, _env_float("FYERS_FAILED_SYMBOLS_CACHE_TTL_SEC", 10.0))
FYERS_FAILED_SYMBOLS_CACHE_MAX_ITEMS = max(1, _env_int("FYERS_FAILED_SYMBOLS_CACHE_MAX_ITEMS", 128))
FYERS_AUTH_RETRY_COUNT = max(1, _env_int("FYERS_AUTH_RETRY_COUNT", 2))
FYERS_AUTH_STATE_TTL_SEC = max(30, _env_int("FYERS_AUTH_STATE_TTL_SEC", 120))
FYERS_AUTH_VALIDITY_SEC = max(3600, _env_int("FYERS_AUTH_VALIDITY_SEC", 24 * 60 * 60))
FYERS_AUTH_COMPLETION_GRACE_SEC = max(1, _env_int("FYERS_AUTH_COMPLETION_GRACE_SEC", 10))
FYERS_AUTH_PROFILE_VALIDATION_MAX_AGE_SEC = max(
    0,
    _env_int("FYERS_AUTH_PROFILE_VALIDATION_MAX_AGE_SEC", 20),
)
FYERS_AUTH_STATE_FILE = os.getenv("FYERS_AUTH_STATE_FILE", ".fyers_auth_state.json").strip() or ".fyers_auth_state.json"
FYERS_AUTH_STATUS_CACHE_FILE = _env_str("FYERS_AUTH_STATUS_CACHE_FILE", "runtime/cache/fyers_auth_status.json") or "runtime/cache/fyers_auth_status.json"
FYERS_AUTH_STATUS_CACHE_TTL_SEC = max(0.0, _env_float("FYERS_AUTH_STATUS_CACHE_TTL_SEC", 60.0))
FYERS_AUTH_STATUS_FAST_WAIT_SEC = max(0.0, _env_float("FYERS_AUTH_STATUS_FAST_WAIT_SEC", 5.0))
FYERS_ACTIVE_JOB_STALE_SEC = max(300, _env_int("FYERS_ACTIVE_JOB_STALE_SEC", 15 * 60))
FYERS_MAX_RETRIES = max(0, _env_int("FYERS_MAX_RETRIES", 5))
FYERS_RETRY_BASE_SLEEP_SECONDS = max(0.1, _env_float("FYERS_RETRY_BASE_SLEEP_SECONDS", 2.0))
FYERS_REQUEST_SLEEP_SECONDS = max(0.0, _env_float("FYERS_REQUEST_SLEEP_SECONDS", 0.4))
FYERS_BATCH_INSERT_SIZE = max(1, _env_int("FYERS_BATCH_INSERT_SIZE", 500))
FYERS_SYMBOL_MASTER_URL = (
    _env_str("FYERS_SYMBOL_MASTER_URL", "https://public.fyers.in/sym_details/NSE_CM.csv")
    or "https://public.fyers.in/sym_details/NSE_CM.csv"
)
FYERS_SYMBOL_MASTER_CACHE_TTL_SEC = max(60, _env_int("FYERS_SYMBOL_MASTER_CACHE_TTL_SEC", 6 * 60 * 60))
FYERS_DEFAULT_START_DATE = _env_str("FYERS_DEFAULT_START_DATE", "1998-01-01") or "1998-01-01"
FYERS_FIXED_RESOLUTION = "1D"
FYERS_SOURCE = _env_str("FYERS_SOURCE", "FYERS_SINGLE_STOCK") or "FYERS_SINGLE_STOCK"
FYERS_AUTH_PROBE_SYMBOL = _env_str("FYERS_AUTH_PROBE_SYMBOL", "NSE:RELIANCE-EQ") or "NSE:RELIANCE-EQ"
FYERS_AUTH_PROBE_TIMEOUT_SEC = max(10, _env_int("FYERS_AUTH_PROBE_TIMEOUT_SEC", 90))
FYERS_DATA_DIR = _env_str("FYERS_DATA_DIR")
FYERS_DATA_RETENTION_DAYS = max(1, _env_int("FYERS_DATA_RETENTION_DAYS", 30))
FYERS_CLEANUP_INTERVAL_DAYS = max(7, _env_int("FYERS_CLEANUP_INTERVAL_DAYS", 7))
FYERS_CLEANUP_LOOP_SECONDS = max(3600, _env_int("FYERS_CLEANUP_LOOP_SECONDS", 6 * 60 * 60))
FYERS_CLEANUP_STATE_FILE = os.getenv("FYERS_CLEANUP_STATE_FILE", ".fyers_cleanup_state.json").strip() or ".fyers_cleanup_state.json"
FYERS_PROXY_MODE = (_env_str("FYERS_PROXY_MODE", "direct").lower() or "direct")
FYERS_HTTP_PROXY = _env_str("FYERS_HTTP_PROXY")
FYERS_HTTPS_PROXY = _env_str("FYERS_HTTPS_PROXY")
FYERS_ALL_PROXY = _env_str("FYERS_ALL_PROXY")
FYERS_NO_PROXY = _env_str("FYERS_NO_PROXY")
FYERS_AUTH_EXPIRED_UI_MESSAGE = "Authentication Expired Please authenticate"
FYERS_BATCH_AUTH_ERROR_MESSAGE = "FYERS authentication failed. Please click Authorize FYERS and rerun the batch."
FYERS_BATCH_AUTH_UI_MESSAGE = FYERS_AUTH_EXPIRED_UI_MESSAGE
FYERS_AUTH_REQUIRED_MESSAGE = "Authentication Expired. Please authenticate FYERS before extracting symbols."
FYERS_AUTH_STATUS_EXPIRED_MESSAGE = "Authentication Expired. Please do the authentication."
FYERS_STALE_CALLBACK_MESSAGE = "Stale FYERS callback detected. Close old callback tabs and click Authorize once again."
FYERS_INVALID_REFRESH_MESSAGE = "FYERS refresh token failed. Fresh login required."
FYERS_AUTH_VALIDATION_FAILED_MESSAGE = "Unable to validate FYERS authentication. Please authenticate FYERS before extracting symbols."
FYERS_IST = ZoneInfo("Asia/Kolkata")
_SINGLE_FETCH_ROWS_RE = re.compile(r"Fetched\s+(\d+)\s+rows\b", re.IGNORECASE)
_SINGLE_UPSERT_ROWS_RE = re.compile(r"Upserted\s+(\d+)\s+rows\b", re.IGNORECASE)
_FUTURE_DATE_ERROR = "endDate cannot be greater than today."
_FYERS_NO_DATA_RE = re.compile(r"no candles returned|no data fetched|no trading days|bad request|no data", re.IGNORECASE)
_FYERS_INVALID_SYMBOL_RE = re.compile(r"invalid symbol|rejected symbol|code['\"]?\s*[:=]\s*-?300|code['\"]?\s*[:=]\s*-?310", re.IGNORECASE)
_FYERS_RATE_LIMIT_RE = re.compile(r"\b429\b|rate limit|request limit|throttle|too many requests", re.IGNORECASE)
_FYERS_DIRECT_BATCH_STARTED_RE = re.compile(r"FYERS direct batch started\.\s*symbols=(\d+)\b", re.IGNORECASE)
_FYERS_PROCESSING_SYMBOL_RE = re.compile(r"Processing\s+(\d+)\s*/\s*(\d+)\s*:\s*([^\s]+)", re.IGNORECASE)
_FYERS_INSERTED_SYMBOL_RE = re.compile(
    r"Inserted\s+(\d+)\s+rows,\s*Updated\s+(\d+)\s+rows\s+for\s+([^\s]+)\s+into\s+Oracle\s+DB",
    re.IGNORECASE,
)
_FYERS_SYMBOL_FAILED_RE = re.compile(r"^\[ERROR\]\s+([^\s]+)\s+failed\s*:", re.IGNORECASE)
_FYERS_SYMBOL_SKIPPED_RE = re.compile(r"^\[WARN\]\s+([^\s]+)\s+skipped\s*:", re.IGNORECASE)
_FYERS_SINGLE_SYNC_COVERAGE_RE = re.compile(
    r"\[SINGLE_STOCK_SYNC\]\s+symbol=([^\s]+)\s+status=COVERAGE_CHECK\s+.*?"
    r"existing_rows=(\d+)\s+missing_ranges=(\d+)\s+missing_estimated_days=(\d+)",
    re.IGNORECASE,
)
_FYERS_SINGLE_SYNC_FETCHED_RE = re.compile(
    r"\[SINGLE_STOCK_SYNC\]\s+symbol=([^\s]+)\s+fetched_rows=(\d+)\s+range=",
    re.IGNORECASE,
)
_FYERS_SINGLE_SYNC_DB_MERGE_RE = re.compile(
    r"\[SINGLE_STOCK_SYNC\]\s+db_merge\s+symbol=([^\s]+)\s+.*?"
    r"inserted=(\d+)\s+updated=(\d+)\s+skipped=(\d+)\s+failed_ranges=(\d+)",
    re.IGNORECASE,
)
_FYERS_SINGLE_SYNC_FAILED_RANGE_RE = re.compile(
    r"\[SINGLE_STOCK_SYNC\]\s+symbol=([^\s]+)\s+failed_range=([0-9-]+)\.\.([0-9-]+)",
    re.IGNORECASE,
)
_FYERS_AUTH_FAILURE_RE = re.compile(
    r"code['\"]?\s*[:=]\s*-?16\b|could not authenticate the user|invalid access token|token expired",
    re.IGNORECASE,
)
_BATCH_DONE_RE = re.compile(r"Done\.\s*Loaded=(\d+),\s*Remaining quota=(\d+)", re.IGNORECASE)
_BATCH_SUMMARY_RE = re.compile(
    r"Summary:\s*processed\s*(\d+)\s*/\s*(\d+)\s*symbols\s*"
    r"\|\s*with data=(\d+)\s*\|\s*no data=(\d+)\s*\|\s*failed=(\d+)\s*"
    r"\|\s*skipped=(\d+)\s*\|\s*incidents=(\d+)\s*\|\s*NIFTY500_total=(\d+)",
    re.IGNORECASE,
)
_BATCH_SKIP_REASONS_RE = re.compile(r"Skip reasons:\s*(.+)$", re.IGNORECASE)
_BATCH_SUMMARY_CSV_RE = re.compile(r"Symbol summary CSV:\s*(.+)$", re.IGNORECASE)
_BATCH_FAILED_SYMBOL_LINE_RE = re.compile(
    r"(?im)^\[(?:WARN|ERROR)\]\s*([A-Z0-9:_&\.\-]+)\s*:\s*(?:fetch failed|.*invalid.*symbol|.*rejected symbol|.*skipping symbol)"
)
_FYERS_LOGIN_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_FYERS_PROXY_FAILURE_RE = re.compile(
    r"ProxyError|Unable to connect to proxy|Failed to establish a new connection|WinError\s*10061",
    re.IGNORECASE,
)
_FYERS_INVALID_AUTH_RE = re.compile(
    r"invalid auth code|invalid[_\s-]*grant|state mismatch|Did not receive auth_code",
    re.IGNORECASE,
)
_FYERS_INVALID_REFRESH_RE = re.compile(
    r"refresh token.*invalid[_\s-]*grant|invalid[_\s-]*grant.*refresh token|refresh token failed",
    re.IGNORECASE,
)
_FYERS_MASTER_ALLOWED_SUFFIXES = ("EQ", "BE", "SM", "ST", "BZ")
_FYERS_MASTER_ALLOWED_SUFFIXES_SET = set(_FYERS_MASTER_ALLOWED_SUFFIXES)
_FYERS_INPUT_SERIES_RE = re.compile(r"-(EQ|BE|SM|ST|BZ)$", re.IGNORECASE)
_FYERS_EXACT_SYMBOL_RE = re.compile(r"^NSE:([A-Z0-9&._-]+)-((?:EQ|BE|SM|ST|BZ))$")
_FYERS_LOOKUP_KEY_RE = re.compile(r"[^A-Z0-9]+")
_FYERS_MANUAL_SYMBOL_CORRECTIONS = {
    "BOSCHHCIL": "BOSCH-HCIL",
    "CHOLAINV": "CHOLAFIN",
    "RBL": "RBLBANK",
    "SYSTEMATIX": "SYSTMTXC",
}
_FYERS_SYMBOL_MASTER_LOCK = threading.Lock()
_FYERS_SYMBOL_MASTER_CACHE: dict[str, Any] = {
    "loaded_at": 0.0,
    "lookup": {},
}
_FYERS_UI_HIDDEN_LOG_PATTERNS = (
    re.compile(r"^\[FYERS_SYMBOL_RESOLVE\]\s+", re.IGNORECASE),
    re.compile(r"^\[SINGLE_STOCK_SYNC\]\s+", re.IGNORECASE),
    re.compile(r"^\[INFO\]\s+Raw Fyers symbol:", re.IGNORECASE),
    re.compile(r"^\[INFO\]\s+Normalized DB symbol:", re.IGNORECASE),
    re.compile(r"^\[INFO\]\s+Input symbols:", re.IGNORECASE),
    re.compile(r"^\[INFO\]\s+Normalized symbols:", re.IGNORECASE),
    re.compile(r"^\[INFO\]\s+cache_coverage\s+", re.IGNORECASE),
    re.compile(r"^\[INFO\]\s+No XLSX produced for API gap\s+", re.IGNORECASE),
    re.compile(r"^\[INFO\]\s+Loading cache segment from XLSX:", re.IGNORECASE),
    re.compile(r"^\[INFO\]\s+merge_summary\s+", re.IGNORECASE),
    re.compile(r"^\[INFO\]\s+direct_api_fetch\s+", re.IGNORECASE),
)
_FYERS_PROXY_BASE_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")
_FYERS_PROXY_GIT_KEYS = ("GIT_HTTP_PROXY", "GIT_HTTPS_PROXY")
_FYERS_DIRECT_NO_PROXY_REQUIRED = ("localhost", "127.0.0.1", "::1", "api-t1.fyers.in", "api.fyers.in")
_FYERS_PROXY_REMOVAL_KEYS = tuple(
    key for item in (_FYERS_PROXY_BASE_KEYS + _FYERS_PROXY_GIT_KEYS) for key in (item, item.lower())
)
_FYERS_FAILED_SYMBOL_TABLE = "FYERS_API_SKIPED_REJECTED_SYMBOLS"
_FYERS_FAILED_SYMBOL_ALLOWED_EXTENSIONS = (".csv", ".json", ".xlsx", ".xls", ".txt", ".log")
_FYERS_STOP_REQUEST_REASON = "FYERS_STOP_REQUESTED"
_FYERS_TERMINAL_JOB_STATUSES = {"succeeded", "failed", "cancelled"}
_FYERS_PERSISTED_TERMINAL_JOB_STATUSES = {
    "COMPLETED",
    "FAILED",
    "PARTIAL",
    "STOPPED",
    "SUCCESS",
    "SUCCEEDED",
    "CANCELLED",
}
_FYERS_ACTIONABLE_SKIPPED_STATUSES = {
    "SKIPPED_ALREADY_INSERTED",
    "SKIPPED_AFTER_INSERTED",
    "FAILED",
    "INVALID",
    "ERROR",
}
_FYERS_FAILED_STATUS_GROUP = {"FAILED", "AUTH_FAILED", "NO_DATA", "API_ERROR"}
_FYERS_EXPECTED_SYMBOL_SKIP_STATUSES = {"FAILED_INVALID_SYMBOL", "FAILED_NO_DATA"}

_FYERS_JOBS: dict[str, dict[str, Any]] = {}
_FYERS_JOBS_LOCK = threading.Lock()
_FYERS_AUTH_STATE_LOCK = threading.Lock()
_FYERS_AUTH_STATUS_CACHE_LOCK = threading.Lock()
_FYERS_AUTH_STATUS_REFRESH_LOCK = threading.Lock()
_FYERS_CLEANUP_STATE_LOCK = threading.Lock()
_FYERS_CLEANUP_SCHEDULER_LOCK = threading.Lock()
_FYERS_CLEANUP_SCHEDULER_STARTED = False
_FYERS_AUTH_STATUS_REFRESH_ACTIVE = False
_FYERS_TRACKING_SCHEMA_READY = False
_FYERS_TRACKING_SCHEMA_LOCK = threading.Lock()
_FYERS_FAILED_SYMBOLS_CACHE_LOCK = threading.Lock()
_FYERS_FAILED_SYMBOLS_CACHE: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}
_FYERS_SINGLE_FLIGHT_STAGES = {
    "batch",
    "single",
    "resume",
    "rerun-failed",
    "rerun-remaining",
}


class SymbolNotFoundError(Exception):
    """Raised when no rows exist for a requested symbol."""


class StockEodDeleteError(RuntimeError):
    """Raised when STOCK_EOD_HISTORY delete verification fails."""


class FyersStopRequestedError(RuntimeError):
    """Raised when the active FYERS job is asked to stop immediately."""


def _is_valid_source_name(name: str) -> bool:
    return bool(SOURCE_NAME_PATTERN.match(name or ""))


def _is_missing_source_error(error: Exception) -> bool:
    message = str(error or "").upper()
    return ("ORA-00942" in message) or ("TABLE OR VIEW DOES NOT EXIST" in message)


def _resolve_marketdata_oracle_sync_table() -> str:
    table_name = str(
        os.getenv(MARKETDATA_ORACLE_SYNC_TABLE_ENV, DEFAULT_MARKETDATA_ORACLE_SYNC_TABLE)
        or DEFAULT_MARKETDATA_ORACLE_SYNC_TABLE
    ).strip().upper()
    if not _is_valid_source_name(table_name):
        raise RuntimeError(f"Invalid Oracle sync table configured in {MARKETDATA_ORACLE_SYNC_TABLE_ENV}.")
    return table_name


def _detect_date_column(cur, table_name: str) -> str | None:
    cur.execute(f"SELECT * FROM {table_name} WHERE ROWNUM = 0")
    description = getattr(cur, "description", None) or []
    cols = {str(d[0]).upper() for d in description if d and d[0]}
    return next(
        (name for name in ("TRADING_DATE", "TRADE_DATE", "LTC_DATE", "DATE") if name in cols),
        None,
    )


def _safe_latest_date(cur, table_name: str, date_column: str) -> str | None:
    cur.execute(f"SELECT TO_CHAR(MAX({date_column}), 'YYYY-MM-DD') FROM {table_name}")
    row = cur.fetchone() or [None]
    value = row[0] if row else None
    text = str(value or "").strip()
    return text or None


def _stock_eod_eligible_date_predicate(date_expr: str) -> str:
    cutoff_hour = int(STOCK_EOD_CURRENT_DAY_ELIGIBLE_HOUR)
    return (
        f"(TRUNC({date_expr}) < TRUNC(SYSDATE) "
        f"OR (TRUNC({date_expr}) = TRUNC(SYSDATE) "
        f"AND TO_NUMBER(TO_CHAR(SYSDATE, 'HH24')) >= {cutoff_hour}))"
    )


def _stock_eod_latest_date_subquery(table_name: str, date_column: str) -> str:
    return (
        f"(SELECT MAX({date_column}) FROM {table_name} "
        f"WHERE {_stock_eod_eligible_date_predicate(date_column)})"
    )


def _safe_latest_stock_eod_date(cur, table_name: str, date_column: str) -> str | None:
    cur.execute(
        f"""
        SELECT TO_CHAR(MAX({date_column}), 'YYYY-MM-DD')
        FROM {table_name}
        WHERE {_stock_eod_eligible_date_predicate(date_column)}
        """
    )
    row = cur.fetchone() or [None]
    value = row[0] if row else None
    text = str(value or "").strip()
    return text or None


def _safe_latest_pending_rows(
    cur,
    *,
    source_table: str,
    source_date_column: str,
    target_table: str,
    target_date_column: str,
) -> int:
    cur.execute(
        f"""
        SELECT COUNT(*)
        FROM {source_table} h
        LEFT JOIN {target_table} t
          ON t.symbol = UPPER(TRIM(h.symbol))
         AND t.{target_date_column} = TRUNC(h.{source_date_column})
        WHERE TRUNC(h.{source_date_column}) = TRUNC({_stock_eod_latest_date_subquery(source_table, source_date_column)})
          AND {_stock_eod_eligible_date_predicate(f'h.{source_date_column}')}
          AND t.symbol IS NULL
        """
    )
    row = cur.fetchone() or [0]
    return int((row[0] if row else 0) or 0)


def _auto_merge_availability(cur) -> dict[str, object]:
    source_table = _resolve_stock_eod_table_name()
    source_date_column = "TRADE_DATE"

    source_latest_date = _safe_latest_stock_eod_date(cur, source_table, source_date_column)
    source_latest_rows = 0
    if source_latest_date:
        cur.execute(
            f"""
            SELECT COUNT(*)
            FROM {source_table}
            WHERE TRUNC({source_date_column}) = TRUNC({_stock_eod_latest_date_subquery(source_table, source_date_column)})
              AND {_stock_eod_eligible_date_predicate(source_date_column)}
            """
        )
        row = cur.fetchone() or [0]
        source_latest_rows = int((row[0] if row else 0) or 0)

    dev_table = _MD_ORACLE_QUALIFIED
    dev_date_column = _detect_date_column(cur, dev_table)
    if not dev_date_column:
        raise RuntimeError(f"No supported date column found in {dev_table}.")
    dev_latest_date = _safe_latest_date(cur, dev_table, dev_date_column)
    pending_dev_rows = (
        _safe_latest_pending_rows(
            cur,
            source_table=source_table,
            source_date_column=source_date_column,
            target_table=dev_table,
            target_date_column=dev_date_column,
        )
        if source_latest_date else 0
    )

    oracle_table = _resolve_marketdata_oracle_sync_table()
    oracle_date_column: str | None = None
    oracle_latest_date: str | None = None
    pending_oracle_rows = 0
    oracle_available = True
    oracle_error = ""
    try:
        oracle_date_column = _detect_date_column(cur, oracle_table)
        if not oracle_date_column:
            raise RuntimeError(f"No supported date column found in {oracle_table}.")
        oracle_latest_date = _safe_latest_date(cur, oracle_table, oracle_date_column)
        pending_oracle_rows = (
            _safe_latest_pending_rows(
                cur,
                source_table=source_table,
                source_date_column=source_date_column,
                target_table=oracle_table,
                target_date_column=oracle_date_column,
            )
            if source_latest_date else 0
        )
    except Exception as exc:
        oracle_available = False
        oracle_error = str(exc or "").strip()

    validation = _collect_stock_history_sync_validation(cur) if oracle_available else {}
    pending_dev_rows = int(validation.get("dev_source_missing_count") or 0)
    pending_dev_rows += int(validation.get("dev_source_changed_count") or 0)
    pending_dev_rows += int(validation.get("oracle_missing_in_dev_count") or 0)
    pending_oracle_rows = int(validation.get("oracle_source_missing_count") or 0)
    pending_oracle_rows += int(validation.get("oracle_source_changed_count") or 0)
    pending_oracle_rows += int(validation.get("dev_missing_in_oracle_count") or 0)
    merge_required = bool(source_latest_date) and (
        pending_dev_rows > 0
        or (oracle_available and pending_oracle_rows > 0)
        or (oracle_available and not bool(validation.get("dev_oracle_row_count_match", True)))
    )
    return {
        "source_table": source_table,
        "source_date_column": source_date_column,
        "source_latest_trade_date": source_latest_date,
        "source_latest_row_count": source_latest_rows,
        "dev_table": dev_table,
        "dev_date_column": dev_date_column,
        "dev_latest_trade_date": dev_latest_date,
        "pending_dev_rows": pending_dev_rows,
        "oracle_table": oracle_table,
        "oracle_date_column": oracle_date_column,
        "oracle_latest_trade_date": oracle_latest_date,
        "oracle_available": oracle_available,
        "oracle_error": oracle_error,
        "pending_oracle_rows": pending_oracle_rows if oracle_available else None,
        "merge_required": merge_required,
        **validation,
    }


def get_auto_merge_availability() -> dict[str, object]:
    with pool.acquire() as con, con.cursor() as cur:
        return _auto_merge_availability(cur)


def _resolve_summary_source(con) -> str:
    global _SUMMARY_SOURCE_CACHE
    if _SUMMARY_SOURCE_CACHE:
        return _SUMMARY_SOURCE_CACHE

    candidates = SUMMARY_SOURCES or ("V_STOCK_EOD_HISTORY", "STOCK_EOD_HISTORY")
    last_error: Optional[Exception] = None
    for source in candidates:
        if not _is_valid_source_name(source):
            continue
        with con.cursor() as cur:
            try:
                cur.execute(f"SELECT 1 FROM {source} WHERE ROWNUM <= 1")
                cur.fetchone()
                _SUMMARY_SOURCE_CACHE = source
                return source
            except Exception as exc:
                last_error = exc
                if _is_missing_source_error(exc):
                    continue
                raise

    if last_error:
        raise RuntimeError(
            f"Unable to resolve marketdata source from candidates: {', '.join(candidates)}"
        ) from last_error
    raise RuntimeError("No valid marketdata summary sources configured")


def _is_stock_eod_source(value: object) -> bool:
    token = str(value or "").strip().upper()
    return token in {"STOCK_EOD", "STOCK_EOD_HISTORY", "EOD_HISTORY"}


def _resolve_marketdata_source(con, source: object = None) -> str:
    if _is_stock_eod_source(source):
        return _resolve_stock_eod_table_name()
    return _resolve_summary_source(con)


def _resolve_summary_source_meta(con, source: object = None) -> dict[str, str]:
    source = _resolve_marketdata_source(con, source)
    cached = _SUMMARY_SOURCE_META_CACHE.get(source)
    if cached:
        return cached
    with con.cursor() as cur:
        cur.execute(f"SELECT * FROM {source} WHERE ROWNUM = 0")
        cols = {str(d[0]).upper() for d in (cur.description or []) if d and d[0]}
    date_column = next(
        (name for name in ("TRADING_DATE", "TRADE_DATE", "LTC_DATE", "DATE") if name in cols),
        None,
    )
    if not date_column:
        raise RuntimeError(
            f"No supported date column found in {source}. Expected one of TRADING_DATE/TRADE_DATE/LTC_DATE/DATE."
        )
    meta = {"source": source, "date_column": date_column}
    _SUMMARY_SOURCE_META_CACHE[source] = meta
    return meta


def _normalize_fyers_proxy_mode(value: object) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in {"direct", "system", "explicit"} else "direct"


def _sanitize_proxy_value(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        if "://" not in raw:
            return re.sub(r"^([^:@/]+):([^@/]+)@", "***:***@", raw)
        parsed = urlsplit(raw)
        if parsed.username is None and parsed.password is None:
            return raw
        host = parsed.hostname or ""
        if parsed.port:
            host = f"{host}:{parsed.port}"
        netloc = f"***:***@{host}" if host else "***:***@"
        return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
    except Exception:
        return re.sub(r"//([^:@/]+):([^@/]+)@", "//***:***@", raw)


def _split_csv_values(value: object) -> list[str]:
    parts: list[str] = []
    for chunk in str(value or "").split(","):
        token = chunk.strip()
        if token:
            parts.append(token)
    return parts


def _merge_no_proxy(existing: object, required: tuple[str, ...]) -> str:
    merged: list[str] = []
    seen: set[str] = set()
    for token in [*_split_csv_values(existing), *required]:
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(token)
    return ",".join(merged)


def _set_proxy_key(env: dict[str, str], key: str, value: str) -> None:
    env[key] = value
    env[key.lower()] = value


def _extract_proxy_snapshot(env: dict[str, str]) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for key in (_FYERS_PROXY_BASE_KEYS + _FYERS_PROXY_GIT_KEYS):
        value = str(env.get(key) or env.get(key.lower()) or "").strip()
        if value:
            snapshot[key] = _sanitize_proxy_value(value)
    return snapshot


def _apply_fyers_proxy_policy(env: dict[str, str]) -> tuple[dict[str, str], dict[str, Any]]:
    resolved = dict(env)
    mode = _normalize_fyers_proxy_mode(FYERS_PROXY_MODE)

    if mode != "system":
        existing_no_proxy = str(resolved.get("NO_PROXY") or resolved.get("no_proxy") or "").strip()
        for key in _FYERS_PROXY_REMOVAL_KEYS:
            resolved.pop(key, None)
        direct_no_proxy = _merge_no_proxy(existing_no_proxy, _FYERS_DIRECT_NO_PROXY_REQUIRED)
        _set_proxy_key(resolved, "NO_PROXY", direct_no_proxy)

    if mode == "explicit":
        if FYERS_HTTP_PROXY:
            _set_proxy_key(resolved, "HTTP_PROXY", FYERS_HTTP_PROXY)
        if FYERS_HTTPS_PROXY:
            _set_proxy_key(resolved, "HTTPS_PROXY", FYERS_HTTPS_PROXY)
        if FYERS_ALL_PROXY:
            _set_proxy_key(resolved, "ALL_PROXY", FYERS_ALL_PROXY)
        if FYERS_NO_PROXY:
            _set_proxy_key(resolved, "NO_PROXY", FYERS_NO_PROXY)

    diagnostics = {
        "mode": mode,
        "proxy": _extract_proxy_snapshot(resolved),
    }
    return resolved, diagnostics


def _is_proxy_connect_failure(text: object) -> bool:
    return bool(_FYERS_PROXY_FAILURE_RE.search(str(text or "")))


def _is_invalid_auth_code_failure(text: object) -> bool:
    return bool(_FYERS_INVALID_AUTH_RE.search(str(text or "")))


def _is_invalid_refresh_token_failure(text: object) -> bool:
    return bool(_FYERS_INVALID_REFRESH_RE.search(str(text or "")))


def _is_fyers_auth_failure(text: object) -> bool:
    return bool(_FYERS_AUTH_FAILURE_RE.search(str(text or "")))


def _fresh_fyers_state() -> str:
    return f"swingtrade-login-{uuid.uuid4().hex[:10]}"


def _summary_metrics_sql(source: str, date_column: str, include_where_symbol: bool = False) -> str:
    where_symbol = "WHERE symbol = :sym" if include_where_symbol else ""
    return f"""
        SELECT
          symbol                                       AS stock,
          MAX({date_column})                           AS latest_trade_date,
          CAST(1 AS NUMBER)                            AS daily,
          COUNT(DISTINCT TRUNC({date_column}, 'IW'))   AS weekly,
          COUNT(DISTINCT TRUNC({date_column}, 'MM'))   AS monthly,
          COUNT(DISTINCT TRUNC({date_column}, 'YYYY')) AS yearly,
          COUNT(DISTINCT TRUNC({date_column}))         AS total_no_of_trading_days
        FROM {source}
        {where_symbol}
        GROUP BY symbol
    """


def _coerce_limit(value: Optional[int]) -> int:
    try:
        num = int(value or DEFAULT_LIMIT)
    except (TypeError, ValueError):
        num = DEFAULT_LIMIT
    return max(1, min(MAX_LIMIT, num))


def list_symbols(prefix: Optional[str] = None, limit: Optional[int] = None, source: object = None):
    lim = _coerce_limit(limit)
    binds = {"lim": lim}
    prefix_clause = ""
    if prefix:
        binds["q"] = f"{prefix.upper()}%"
        prefix_clause = "AND symbol LIKE :q"
    with pool.acquire() as con, con.cursor() as cur:
        source_meta = _resolve_summary_source_meta(con, source)
        source = source_meta["source"]
        date_column = source_meta["date_column"]
        sql = f"""
            SELECT symbol,
                   latest_trade_date
            FROM (
              SELECT
                symbol,
                MAX({date_column}) AS latest_trade_date,
                ROW_NUMBER() OVER (ORDER BY symbol) AS rn
              FROM {source}
              WHERE 1=1
              {prefix_clause}
              GROUP BY symbol
            )
            WHERE rn <= :lim
            ORDER BY symbol
        """
        cur.execute(sql, binds)
        return fetchall_dict(cur)


def stock_summary(symbol: str, source: object = None):
    sym = (symbol or "").strip().upper()
    if not sym:
        raise ValueError("Symbol is required")

    with pool.acquire() as con, con.cursor() as cur:
        source_meta = _resolve_summary_source_meta(con, source)
        sql = _summary_metrics_sql(source_meta["source"], source_meta["date_column"], include_where_symbol=True)
        cur.execute(sql, {"sym": sym})
        row = cur.fetchone()
        if not row:
            raise SymbolNotFoundError(f"{sym} not found in stock_eod_history")
        cols = [d[0].lower() for d in cur.description]
        return dict(zip(cols, row))


def summary_table(
    timeframe: Literal["daily", "weekly", "monthly", "yearly"],
    symbol: Optional[str] = None,
    source: object = None,
):
    tf = (timeframe or "daily").lower()
    if tf not in VALID_TIMEFRAMES:
        raise ValueError("Invalid timeframe")
    sym = (symbol or "").strip().upper()
    requested_source = source

    cols_for = {
        "daily":   "s_no, stock, latest_trade_date, daily, weekly, monthly, yearly, total_no_of_trading_days",
        "weekly":  "s_no, stock, latest_trade_date, weekly, monthly, yearly, total_no_of_trading_days",
        "monthly": "s_no, stock, latest_trade_date, monthly, yearly, total_no_of_trading_days",
        "yearly":  "s_no, stock, latest_trade_date, yearly, total_no_of_trading_days",
    }
    with pool.acquire() as con, con.cursor() as cur:
        source_meta = _resolve_summary_source_meta(con, source)
        source = source_meta["source"]
        date_column = source_meta["date_column"]
        source_upper = str(source or "").strip().upper()
        stock_eod_table = _resolve_stock_eod_table_name()
        if tf == "daily" and (_is_stock_eod_source(requested_source) or source_upper == stock_eod_table):
            sql = f"""
                SELECT
                  ROW_NUMBER() OVER (ORDER BY trade_date DESC) AS s_no,
                  stocks,
                  trade_date AS latest_trade_date,
                  CAST(1 AS NUMBER) AS total_no_of_trading_days
                FROM (
                  SELECT trade_date, stocks
                  FROM (
                    SELECT
                      TRUNC({date_column}) AS trade_date,
                      COUNT(DISTINCT symbol) AS stocks
                    FROM {source}
                    WHERE {_stock_eod_eligible_date_predicate(date_column)}
                    GROUP BY TRUNC({date_column})
                    )
                  ORDER BY trade_date DESC
                  FETCH FIRST 5 ROWS ONLY
                )
                ORDER BY trade_date DESC
            """
            cur.execute(sql)
            return fetchall_dict(cur)
        binds: dict[str, object] = {}
        if sym:
            base = _summary_metrics_sql(source, date_column, include_where_symbol=True)
            binds["sym"] = sym
        else:
            base = _summary_metrics_sql(source, date_column, include_where_symbol=False)
        sql = f"""
            SELECT {cols_for[tf]}
            FROM (
              SELECT
                ROW_NUMBER() OVER (ORDER BY stock) AS s_no,
                stock,
                latest_trade_date,
                daily,
                weekly,
                monthly,
                yearly,
                total_no_of_trading_days
              FROM ({base})
            )
        """
        cur.execute(sql, binds)
        rows = fetchall_dict(cur)
        if sym and not rows:
            raise SymbolNotFoundError(f"{sym} not found in stock summary view")
        return rows


def market_stats(source: object = None):
    with pool.acquire() as con, con.cursor() as cur:
        source_name = _resolve_marketdata_source(con, source)
        cur.execute(
            f"""
            SELECT
              COUNT(*) AS record_count,
              COUNT(DISTINCT symbol) AS stock_count
            FROM {source_name}
            """
        )
        rows = fetchall_dict(cur)
        row = rows[0] if rows else {}
        record_count = int(row.get("record_count") or 0)
        stock_count = int(row.get("stock_count") or 0)
        payload = {
            "record_count": record_count,
            "stock_count": stock_count,
            "source": source_name,
        }
        stock_eod_table = _resolve_stock_eod_table_name()
        payload["stock_eod_table"] = stock_eod_table
        if str(source_name).upper() == stock_eod_table:
            stock_eod_date_column = _detect_date_column(cur, stock_eod_table)
            trading_day_count = 0
            if stock_eod_date_column:
                cur.execute(
                    f"""
                    SELECT COUNT(DISTINCT CASE
                      WHEN {_stock_eod_eligible_date_predicate(stock_eod_date_column)}
                      THEN TRUNC({stock_eod_date_column})
                    END) AS trading_day_count
                    FROM {stock_eod_table}
                    """
                )
                trading_day_rows = fetchall_dict(cur)
                trading_day_row = trading_day_rows[0] if trading_day_rows else {}
                trading_day_count = int(trading_day_row.get("trading_day_count") or 0)
            payload.update({
                "stock_eod_record_count": record_count,
                "stock_eod_stock_count": stock_count,
                "stock_eod_total_trading_days": trading_day_count,
                "totalTradingDays": trading_day_count,
                "TOTAL_TRADING_DAYS": trading_day_count,
            })
        else:
            try:
                stock_eod_date_column = _detect_date_column(cur, stock_eod_table)
                trading_days_sql = (
                    f"""COUNT(DISTINCT CASE
                      WHEN {_stock_eod_eligible_date_predicate(stock_eod_date_column)}
                      THEN TRUNC({stock_eod_date_column})
                    END) AS trading_day_count"""
                    if stock_eod_date_column
                    else "CAST(0 AS NUMBER) AS trading_day_count"
                )
                cur.execute(
                    f"""
                    SELECT
                      COUNT(*) AS record_count,
                      COUNT(DISTINCT symbol) AS stock_count,
                      {trading_days_sql}
                    FROM {stock_eod_table}
                    """
                )
                stock_eod_rows = fetchall_dict(cur)
                stock_eod_row = stock_eod_rows[0] if stock_eod_rows else {}
                payload.update({
                    "stock_eod_record_count": int(stock_eod_row.get("record_count") or 0),
                    "stock_eod_stock_count": int(stock_eod_row.get("stock_count") or 0),
                    "stock_eod_total_trading_days": int(stock_eod_row.get("trading_day_count") or 0),
                    "totalTradingDays": int(stock_eod_row.get("trading_day_count") or 0),
                    "TOTAL_TRADING_DAYS": int(stock_eod_row.get("trading_day_count") or 0),
                })
            except Exception as exc:
                _logger.warning(
                    "[MARKETDATA][STATS] stock_eod_count_failed table=%s error=%s",
                    stock_eod_table,
                    exc,
                )
                payload.update({
                    "stock_eod_record_count": None,
                    "stock_eod_stock_count": None,
                    "stock_eod_total_trading_days": None,
                    "totalTradingDays": None,
                    "TOTAL_TRADING_DAYS": None,
                })
        try:
            payload.update(_stock_eod_pending_dev_summary(cur))
        except Exception as exc:
            _logger.warning(
                "[MARKETDATA][STATS] stock_eod_pending_count_failed table=%s error=%s",
                stock_eod_table,
                exc,
            )
            payload.update({
                "stock_eod_latest_trade_date": None,
                "stock_eod_latest_source_rows": None,
                "stock_eod_pending_dev_count": None,
                "stock_eod_latest_pending_dev_count": None,
            })
        try:
            payload.update(_stock_eod_sync_card_summary(cur))
        except Exception as exc:
            _logger.warning(
                "[MARKETDATA][STATS] stock_eod_sync_card_count_failed table=%s error=%s",
                stock_eod_table,
                exc,
            )
            payload.update({
                "stock_eod_synced_rows": None,
                "stock_eod_synched_rows": None,
                "stock_eod_unsynced_rows": None,
                "stock_eod_unsynched_rows": None,
                "stock_eod_pending_sync_count": None,
                "stockEodSyncedRows": None,
                "stockEodUnsyncedRows": None,
            })
        return payload


def _parse_date(value: Optional[str]) -> Optional[dt.date]:
    if not value:
        return None
    try:
        return dt.datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Dates must be supplied as YYYY-MM-DD")


def stock_ohlcv(
    symbol: str,
    granularity: Literal["daily", "weekly", "monthly", "yearly"] = "daily",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    sym = (symbol or "").strip().upper()
    if not sym:
        raise ValueError("Symbol is required")

    gran = (granularity or "daily").lower()
    if gran not in VALID_TIMEFRAMES:
        raise ValueError("Invalid granularity")

    d_from = _parse_date(date_from) if date_from else None
    d_to = _parse_date(date_to) if date_to else None

    where = ["symbol = :sym"]
    binds: dict[str, object] = {"sym": sym}
    if d_from:
        where.append("trade_date >= :dfrom")
        binds["dfrom"] = d_from
    if d_to:
        where.append("trade_date <= :dto")
        binds["dto"] = d_to

    if gran == "daily":
        sql = f"""
            SELECT
              TRUNC(trade_date) AS bucket,
              MIN(open_price) KEEP (DENSE_RANK FIRST ORDER BY trade_date) AS open_price,
              MAX(high_price)  AS high_price,
              MIN(low_price)   AS low_price,
              MAX(close_price) KEEP (DENSE_RANK LAST  ORDER BY trade_date) AS close_price,
              SUM(volume)      AS volume
            FROM stock_eod_history
            WHERE {' AND '.join(where)}
            GROUP BY TRUNC(trade_date)
            ORDER BY bucket
        """
    else:
        view_for = {
            "weekly": "v_stock_weekly_ohlcv",
            "monthly": "v_stock_monthly_ohlcv",
            "yearly": "v_stock_yearly_ohlcv",
        }
        view_name = view_for[gran]
        filters = ["symbol = :sym"]
        if d_from:
            filters.append("bucket >= :dfrom")
            binds["dfrom"] = d_from
        if d_to:
            filters.append("bucket <= :dto")
            binds["dto"] = d_to
        sql = f"""
            SELECT
              bucket,
              open_price,
              high_price,
              low_price,
              close_price,
              volume
            FROM {view_name}
            WHERE {' AND '.join(filters)}
            ORDER BY bucket
        """

    with pool.acquire() as con, con.cursor() as cur:
        cur.execute(sql, binds)
        rows = fetchall_dict(cur)
        if not rows and gran != "daily":
            raise SymbolNotFoundError(f"{sym} not found in {view_name}")
        return rows


def _format_ts(value: object | None) -> str | None:
    if value is None:
        return None
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def _read_dbms_output(cur, limit: int = DBMS_OUTPUT_MAX_LINES):
    lines: list[str] = []
    try:
        status = cur.var(oracledb.NUMBER)
        line = cur.var(oracledb.STRING)
        for _ in range(limit):
            cur.callproc("dbms_output.get_line", (line, status))
            if int(status.getvalue() or 0) != 0:
                break
            value = line.getvalue()
            if value is not None:
                lines.append(str(value))
    except Exception:
        return []
    return lines


def _parse_sync_output(lines: list[str]):
    summary: dict[str, object] = {}
    dev_re = re.compile(r"DEV\s+inserted\s*:\s*(\d+)", re.IGNORECASE)
    orc_re = re.compile(r"ORACLE\s+inserted\s*:\s*(\d+)", re.IGNORECASE)
    rows_re = re.compile(r"Rows\s+in\s+STOCK_EOD_HISTORY\s+window\s*:\s*(\d+)", re.IGNORECASE)
    high_re = re.compile(r"High-watermark\s*:\s*(.+)$", re.IGNORECASE)
    for line in lines:
        if not line:
            continue
        dev_match = dev_re.search(line)
        if dev_match:
            summary["inserted_dev"] = int(dev_match.group(1))
        orc_match = orc_re.search(line)
        if orc_match:
            summary["inserted_oracle"] = int(orc_match.group(1))
        rows_match = rows_re.search(line)
        if rows_match:
            summary["window_rows"] = int(rows_match.group(1))
        high_match = high_re.search(line)
        if high_match:
            summary["last_load_ts"] = high_match.group(1).strip()
    if any("no new rows" in (line or "").lower() for line in lines):
        summary.setdefault("message", "No new rows to merge.")
    return summary


def _stock_history_source_sql(source_table: str) -> str:
    return f"""
        SELECT
          src.symbol,
          src.trade_date,
          src.open_price,
          src.high_price,
          src.low_price,
          src.close_price,
          src.volume
        FROM (
          SELECT
            UPPER(TRIM(h.symbol)) AS symbol,
            TRUNC(h.trade_date) AS trade_date,
            h.open_price,
            h.high_price,
            h.low_price,
            h.close_price,
            h.volume,
            ROW_NUMBER() OVER (
              PARTITION BY UPPER(TRIM(h.symbol)), TRUNC(h.trade_date)
              ORDER BY h.load_ts DESC NULLS LAST, h.ROWID DESC
            ) AS rn
          FROM {source_table} h
        ) src
        WHERE src.rn = 1
    """


def _stock_history_value_difference_sql(*, target_alias: str, source_alias: str) -> str:
    return (
        f"NVL({target_alias}.open, -1e125) <> NVL({source_alias}.open_price, -1e125) "
        f"OR NVL({target_alias}.high, -1e125) <> NVL({source_alias}.high_price, -1e125) "
        f"OR NVL({target_alias}.low, -1e125) <> NVL({source_alias}.low_price, -1e125) "
        f"OR NVL({target_alias}.previous_close, -1e125) <> NVL({source_alias}.close_price, -1e125) "
        f"OR NVL({target_alias}.volume, -1) <> NVL({source_alias}.volume, -1)"
    )


def _count_rows(cur, table_name: str) -> int:
    cur.execute(f"SELECT COUNT(*) FROM {table_name}")
    row = cur.fetchone() or [0]
    return int((row[0] if row else 0) or 0)


def _count_source_rows(cur, *, source_table: str) -> int:
    cur.execute(f"SELECT COUNT(*) FROM ({_stock_history_source_sql(source_table)}) src")
    row = cur.fetchone() or [0]
    return int((row[0] if row else 0) or 0)


def _count_source_missing_rows(cur, *, source_table: str, target_table: str) -> int:
    cur.execute(
        f"""
        SELECT COUNT(*)
        FROM ({_stock_history_source_sql(source_table)}) src
        LEFT JOIN {target_table} tgt
          ON tgt.symbol = src.symbol
         AND tgt.trading_date = src.trade_date
        WHERE tgt.symbol IS NULL
        """
    )
    row = cur.fetchone() or [0]
    return int((row[0] if row else 0) or 0)


def _count_source_changed_rows(cur, *, source_table: str, target_table: str) -> int:
    cur.execute(
        f"""
        SELECT COUNT(*)
        FROM ({_stock_history_source_sql(source_table)}) src
        JOIN {target_table} tgt
          ON tgt.symbol = src.symbol
         AND tgt.trading_date = src.trade_date
        WHERE {_stock_history_value_difference_sql(target_alias='tgt', source_alias='src')}
        """
    )
    row = cur.fetchone() or [0]
    return int((row[0] if row else 0) or 0)


def _count_target_missing_rows(cur, *, source_table: str, target_table: str) -> int:
    cur.execute(
        f"""
        SELECT COUNT(*)
        FROM {source_table} src
        LEFT JOIN {target_table} tgt
          ON UPPER(TRIM(tgt.symbol)) = UPPER(TRIM(src.symbol))
         AND TRUNC(tgt.trading_date) = TRUNC(src.trading_date)
        WHERE tgt.symbol IS NULL
          AND TRUNC(src.trading_date) >= TRUNC(SYSDATE) - 14
        """
    )
    row = cur.fetchone() or [0]
    return int((row[0] if row else 0) or 0)


def _stock_eod_pending_dev_summary(cur) -> dict[str, object]:
    source_table = _resolve_stock_eod_table_name()
    source_date_column = "TRADE_DATE"
    latest_trade_date = _safe_latest_stock_eod_date(cur, source_table, source_date_column)
    latest_source_rows = 0
    latest_pending_dev_rows = 0
    if latest_trade_date:
        cur.execute(
            f"""
            SELECT COUNT(*)
            FROM {source_table}
            WHERE TRUNC({source_date_column}) = TRUNC({_stock_eod_latest_date_subquery(source_table, source_date_column)})
              AND {_stock_eod_eligible_date_predicate(source_date_column)}
            """
        )
        row = cur.fetchone() or [0]
        latest_source_rows = int((row[0] if row else 0) or 0)

        dev_table = _MD_ORACLE_QUALIFIED
        dev_date_column = _detect_date_column(cur, dev_table)
        if not dev_date_column:
            raise RuntimeError(f"No supported date column found in {dev_table}.")
        latest_pending_dev_rows = _safe_latest_pending_rows(
            cur,
            source_table=source_table,
            source_date_column=source_date_column,
            target_table=dev_table,
            target_date_column=dev_date_column,
        )
    return {
        "stock_eod_latest_trade_date": latest_trade_date,
        "stock_eod_latest_source_rows": latest_source_rows,
        "stock_eod_pending_dev_count": latest_pending_dev_rows,
        "stock_eod_latest_pending_dev_count": latest_pending_dev_rows,
    }


def _stock_eod_sync_card_summary(cur) -> dict[str, object]:
    source_table = _resolve_stock_eod_table_name()
    dev_table = _MD_ORACLE_QUALIFIED
    oracle_table = _resolve_marketdata_oracle_sync_table()
    cur.execute(
        f"""
        SELECT
          SUM(CASE
            WHEN d.symbol IS NOT NULL
             AND o.symbol IS NOT NULL
             AND NOT ({_stock_history_value_difference_sql(target_alias='d', source_alias='src')})
             AND NOT ({_stock_history_value_difference_sql(target_alias='o', source_alias='src')})
            THEN 1 ELSE 0 END) AS synced_rows,
          SUM(CASE
            WHEN d.symbol IS NULL
              OR o.symbol IS NULL
              OR ({_stock_history_value_difference_sql(target_alias='d', source_alias='src')})
              OR ({_stock_history_value_difference_sql(target_alias='o', source_alias='src')})
            THEN 1 ELSE 0 END) AS unsynced_rows
        FROM ({_stock_history_source_sql(source_table)}) src
        LEFT JOIN {dev_table} d
          ON d.symbol = src.symbol
         AND d.trading_date = src.trade_date
        LEFT JOIN {oracle_table} o
          ON o.symbol = src.symbol
         AND o.trading_date = src.trade_date
        """
    )
    row = cur.fetchone() or [0, 0]
    synced_rows = int((row[0] if row else 0) or 0)
    unsynced_rows = int((row[1] if len(row) > 1 else 0) or 0)
    return {
        "stock_eod_synced_rows": synced_rows,
        "stock_eod_synched_rows": synced_rows,
        "stock_eod_unsynced_rows": unsynced_rows,
        "stock_eod_unsynched_rows": unsynced_rows,
        "stock_eod_pending_sync_count": unsynced_rows,
        "stockEodSyncedRows": synced_rows,
        "stockEodUnsyncedRows": unsynced_rows,
    }


def _collect_stock_history_sync_validation(cur) -> dict[str, object]:
    source_table = _resolve_stock_eod_table_name()
    dev_table = _MD_ORACLE_QUALIFIED
    oracle_table = _resolve_marketdata_oracle_sync_table()

    source_unique_keys = _count_source_rows(cur, source_table=source_table)
    dev_total_rows = _count_rows(cur, dev_table)
    oracle_total_rows = _count_rows(cur, oracle_table)
    dev_source_missing = _count_source_missing_rows(cur, source_table=source_table, target_table=dev_table)
    oracle_source_missing = _count_source_missing_rows(cur, source_table=source_table, target_table=oracle_table)
    dev_source_changed = _count_source_changed_rows(cur, source_table=source_table, target_table=dev_table)
    oracle_source_changed = _count_source_changed_rows(cur, source_table=source_table, target_table=oracle_table)
    oracle_missing_in_dev = _count_target_missing_rows(cur, source_table=oracle_table, target_table=dev_table)
    dev_missing_in_oracle = _count_target_missing_rows(cur, source_table=dev_table, target_table=oracle_table)
    counts_match = dev_total_rows == oracle_total_rows
    targets_fully_synced = (
        counts_match
        and dev_source_missing == 0
        and oracle_source_missing == 0
        and dev_source_changed == 0
        and oracle_source_changed == 0
        and oracle_missing_in_dev == 0
        and dev_missing_in_oracle == 0
    )
    return {
        "stock_history_unique_key_count": source_unique_keys,
        "dev_total_row_count": dev_total_rows,
        "oracle_total_row_count": oracle_total_rows,
        "dev_source_missing_count": dev_source_missing,
        "oracle_source_missing_count": oracle_source_missing,
        "dev_source_changed_count": dev_source_changed,
        "oracle_source_changed_count": oracle_source_changed,
        "oracle_missing_in_dev_count": oracle_missing_in_dev,
        "dev_missing_in_oracle_count": dev_missing_in_oracle,
        "dev_oracle_row_count_match": counts_match,
        "targets_fully_synced": targets_fully_synced,
    }


def _reconcile_stock_history_target(cur, *, source_table: str, target_table: str, target_label: str) -> dict[str, object]:
    total_source_keys = _count_source_rows(cur, source_table=source_table)
    missing_before = _count_source_missing_rows(cur, source_table=source_table, target_table=target_table)
    changed_before = _count_source_changed_rows(cur, source_table=source_table, target_table=target_table)
    skipped_before = max(0, total_source_keys - missing_before - changed_before)
    if missing_before <= 0 and changed_before <= 0:
        return {
            f"{target_label}_inserted": 0,
            f"{target_label}_updated": 0,
            f"{target_label}_skipped": skipped_before,
            f"{target_label}_source_keys": total_source_keys,
        }

    _logger.info(
        "[MARKETDATA][STOCK_HISTORY_SYNC] target=%s total_source_keys=%s missing_before=%s changed_before=%s skipped_before=%s",
        target_table,
        total_source_keys,
        missing_before,
        changed_before,
        skipped_before,
    )
    cur.execute(
        f"""
        MERGE INTO {target_table} tgt
        USING ({_stock_history_source_sql(source_table)}) src
           ON (
                tgt.symbol = src.symbol
            AND tgt.trading_date = src.trade_date
           )
        WHEN MATCHED THEN UPDATE SET
          tgt.open = src.open_price,
          tgt.high = src.high_price,
          tgt.low = src.low_price,
          tgt.previous_close = src.close_price,
          tgt.volume = src.volume
        WHERE {_stock_history_value_difference_sql(target_alias='tgt', source_alias='src')}
        WHEN NOT MATCHED THEN INSERT (
          symbol,
          open,
          high,
          low,
          previous_close,
          volume,
          trading_date
        ) VALUES (
          src.symbol,
          src.open_price,
          src.high_price,
          src.low_price,
          src.close_price,
          src.volume,
          src.trade_date
        )
        """
    )
    merged_rows = int(cur.rowcount or 0)
    missing_after = _count_source_missing_rows(cur, source_table=source_table, target_table=target_table)
    changed_after = _count_source_changed_rows(cur, source_table=source_table, target_table=target_table)
    if missing_after > 0 or changed_after > 0:
        raise RuntimeError(
            f"Stock history sync validation failed for {target_table}: "
            f"missing_after={missing_after}, changed_after={changed_after}."
        )
    expected_affected = missing_before + changed_before
    if merged_rows and expected_affected and merged_rows != expected_affected:
        _logger.warning(
            "[MARKETDATA][STOCK_HISTORY_SYNC] target=%s merged_rows=%s expected_affected=%s",
            target_table,
            merged_rows,
            expected_affected,
        )
    _logger.info(
        "[MARKETDATA][STOCK_HISTORY_SYNC] completed target=%s inserted=%s updated=%s skipped=%s",
        target_table,
        missing_before,
        changed_before,
        skipped_before,
    )
    return {
        f"{target_label}_inserted": missing_before,
        f"{target_label}_updated": changed_before,
        f"{target_label}_skipped": skipped_before,
        f"{target_label}_source_keys": total_source_keys,
        f"{target_label}_affected_rows": expected_affected,
    }


def _reconcile_target_pair_missing_rows(
    cur,
    *,
    source_table: str,
    target_table: str,
    source_label: str,
    target_label: str,
) -> dict[str, object]:
    missing_before = _count_target_missing_rows(cur, source_table=source_table, target_table=target_table)
    if missing_before <= 0:
        return {f"{target_label}_inserted_from_{source_label}": 0}

    _logger.info(
        "[MARKETDATA][TARGET_PARITY_SYNC] source=%s target=%s missing_before=%s",
        source_table,
        target_table,
        missing_before,
    )
    cur.execute(
        f"""
        INSERT INTO {target_table} (
          symbol,
          open,
          high,
          low,
          previous_close,
          volume,
          trading_date
        )
        SELECT
          UPPER(TRIM(src.symbol)),
          src.open,
          src.high,
          src.low,
          src.previous_close,
          src.volume,
          TRUNC(src.trading_date)
        FROM {source_table} src
        WHERE TRUNC(src.trading_date) >= TRUNC(SYSDATE) - 14
          AND NOT EXISTS (
            SELECT 1
            FROM {target_table} tgt
            WHERE UPPER(TRIM(tgt.symbol)) = UPPER(TRIM(src.symbol))
              AND TRUNC(tgt.trading_date) = TRUNC(src.trading_date)
          )
        """
    )
    inserted = int(cur.rowcount or 0)
    missing_after = _count_target_missing_rows(cur, source_table=source_table, target_table=target_table)
    if missing_after > 0:
        raise RuntimeError(
            f"Target parity sync validation failed for {target_table}: missing_after={missing_after}."
        )
    return {f"{target_label}_inserted_from_{source_label}": inserted}


def _reconcile_stock_history_targets(cur) -> dict[str, object]:
    source_table = _resolve_stock_eod_table_name()
    dev_table = _MD_ORACLE_QUALIFIED
    oracle_table = _resolve_marketdata_oracle_sync_table()
    if not _is_valid_source_name(dev_table):
        raise RuntimeError("Invalid DEV table configured in ORACLE_TABLE/ORACLE_SCHEMA.")
    if not _is_valid_source_name(oracle_table):
        raise RuntimeError(f"Invalid Oracle sync table configured in {MARKETDATA_ORACLE_SYNC_TABLE_ENV}.")

    dev_sync = _reconcile_stock_history_target(
        cur,
        source_table=source_table,
        target_table=dev_table,
        target_label="dev",
    )
    oracle_sync = _reconcile_stock_history_target(
        cur,
        source_table=source_table,
        target_table=oracle_table,
        target_label="oracle",
    )
    dev_from_oracle = _reconcile_target_pair_missing_rows(
        cur,
        source_table=oracle_table,
        target_table=dev_table,
        source_label="oracle",
        target_label="dev",
    )
    oracle_from_dev = _reconcile_target_pair_missing_rows(
        cur,
        source_table=dev_table,
        target_table=oracle_table,
        source_label="dev",
        target_label="oracle",
    )
    validation = _collect_stock_history_sync_validation(cur)
    if not bool(validation.get("targets_fully_synced")):
        raise RuntimeError(
            "Stock history validation failed after reconciliation: "
            f"dev_source_missing={validation.get('dev_source_missing_count')}, "
            f"oracle_source_missing={validation.get('oracle_source_missing_count')}, "
            f"dev_source_changed={validation.get('dev_source_changed_count')}, "
            f"oracle_source_changed={validation.get('oracle_source_changed_count')}, "
            f"oracle_missing_in_dev={validation.get('oracle_missing_in_dev_count')}, "
            f"dev_missing_in_oracle={validation.get('dev_missing_in_oracle_count')}."
        )
    return {
        **dev_sync,
        **oracle_sync,
        **dev_from_oracle,
        **oracle_from_dev,
        **validation,
    }


def _cleanup_merged_stock_eod_history(cur, *, retention_days: int) -> dict[str, object]:
    source_table = _resolve_stock_eod_table_name()
    source_date_column = "TRADE_DATE"
    dev_table = _MD_ORACLE_QUALIFIED
    dev_date_column = _detect_date_column(cur, dev_table)
    if not dev_date_column:
        raise RuntimeError(f"No supported date column found in {dev_table}.")

    retention = max(1, int(retention_days or STOCK_EOD_MERGED_RETENTION_DAYS))
    predicates = [
        f"TRUNC(h.{source_date_column}) <= TRUNC(SYSDATE) - :retention_days",
        f"""EXISTS (
            SELECT 1
            FROM {dev_table} d
            WHERE d.symbol = h.symbol
              AND TRUNC(d.{dev_date_column}) = TRUNC(h.{source_date_column})
        )""",
    ]
    oracle_table = _resolve_marketdata_oracle_sync_table()
    oracle_date_column = None
    oracle_available = True
    oracle_error = ""
    try:
        oracle_date_column = _detect_date_column(cur, oracle_table)
        if not oracle_date_column:
            raise RuntimeError(f"No supported date column found in {oracle_table}.")
        predicates.append(
            f"""EXISTS (
                SELECT 1
                FROM {oracle_table} o
                WHERE o.symbol = h.symbol
                  AND TRUNC(o.{oracle_date_column}) = TRUNC(h.{source_date_column})
            )"""
        )
    except Exception as exc:
        oracle_available = False
        oracle_error = str(exc or "").strip()
        if not _is_missing_source_error(exc):
            raise

    where_clause = "\n              AND ".join(predicates)
    count_sql = f"""
        SELECT COUNT(*)
        FROM {source_table} h
        WHERE {where_clause}
    """
    delete_sql = f"""
        DELETE FROM {source_table} h
        WHERE {where_clause}
    """
    binds = {"retention_days": retention}

    cur.execute(count_sql, binds)
    row = cur.fetchone() or [0]
    eligible_rows = int((row[0] if row else 0) or 0)
    deleted_rows = 0
    if eligible_rows > 0:
        cur.execute(delete_sql, binds)
        deleted_rows = int(cur.rowcount or 0)

    _logger.info(
        "[MARKETDATA][STOCK_EOD_CLEANUP] table=%s retention_days=%s eligible_rows=%s deleted_rows=%s oracle_available=%s",
        source_table,
        retention,
        eligible_rows,
        deleted_rows,
        oracle_available,
    )
    return {
        "cleanup_retention_days": retention,
        "cleanup_eligible_source_rows": eligible_rows,
        "cleanup_deleted_source_rows": deleted_rows,
        "cleanup_oracle_validation_required": oracle_available,
        "cleanup_oracle_validation_error": oracle_error,
    }


def merge_latest():
    with pool.acquire() as con, con.cursor() as cur:
        try:
            cur.callproc("dbms_output.enable")
        except Exception:
            pass
        try:
            cur.callproc(SYNC_PROC)
            output = _read_dbms_output(cur)
            summary = _parse_sync_output(output)
            try:
                cur.execute(
                    "SELECT last_load_ts FROM STOCK_SYNC_CTRL WHERE target = :target",
                    {"target": SYNC_TARGET},
                )
                row = cur.fetchone()
                if row:
                    summary.setdefault("last_load_ts", _format_ts(row[0]))
            except Exception:
                pass
            summary.update(_reconcile_stock_history_targets(cur))
            summary["inserted_dev"] = int(summary.get("dev_inserted") or 0)
            summary["updated_dev"] = int(summary.get("dev_updated") or 0)
            summary["inserted_oracle"] = int(summary.get("oracle_inserted") or 0)
            summary["updated_oracle"] = int(summary.get("oracle_updated") or 0)
            summary["message"] = (
                "Stock history synchronization completed. "
                f"DEV inserted={summary['inserted_dev']}, updated={summary['updated_dev']}; "
                f"ORACLE inserted={summary['inserted_oracle']}, updated={summary['updated_oracle']}."
            )
            try:
                cur.execute("SAVEPOINT stock_eod_cleanup")
                summary.update(_cleanup_merged_stock_eod_history(cur, retention_days=STOCK_EOD_MERGED_RETENTION_DAYS))
            except Exception as cleanup_exc:
                cur.execute("ROLLBACK TO SAVEPOINT stock_eod_cleanup")
                _logger.exception("[MARKETDATA][STOCK_EOD_CLEANUP] automatic cleanup failed")
                summary.update({
                    "cleanup_retention_days": STOCK_EOD_MERGED_RETENTION_DAYS,
                    "cleanup_eligible_source_rows": 0,
                    "cleanup_deleted_source_rows": 0,
                    "cleanup_error": str(cleanup_exc or "").strip() or "Automatic source cleanup failed.",
                })
            con.commit()
        except Exception:
            try:
                con.rollback()
            except Exception:
                _logger.exception("[MARKETDATA][MERGE] rollback_failed")
            raise
        payload: dict[str, object] = {"ok": True, **summary}
        if output:
            payload["output"] = output
        return payload


def _resolve_stock_eod_table_name() -> str:
    table_name = str(os.getenv(STOCK_EOD_TABLE_ENV, DEFAULT_STOCK_EOD_TABLE) or DEFAULT_STOCK_EOD_TABLE).strip().upper()
    if not _is_valid_source_name(table_name):
        raise RuntimeError(f"Invalid stock EOD table configured in {STOCK_EOD_TABLE_ENV}.")
    return table_name


def clear_stock_eod_history(confirm_text: object) -> dict[str, Any]:
    confirmation = str(confirm_text or "").strip().upper()
    if confirmation != "DELETE":
        raise ValueError("Delete confirmation failed. Type DELETE to confirm.")

    table_name = _resolve_stock_eod_table_name()
    _logger.info("[MARKETDATA][DELETE_ALL] request_received table=%s", table_name)
    with pool.acquire() as con, con.cursor() as cur:
        try:
            _logger.info("[MARKETDATA][DELETE_ALL] begin_transaction table=%s", table_name)
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            row = cur.fetchone()
            previous_record_count = int((row[0] if row else 0) or 0)
            _logger.info(
                "[MARKETDATA][DELETE_ALL] before_count table=%s count=%s",
                table_name,
                previous_record_count,
            )
            cur.execute(f"DELETE FROM {table_name}")
            deleted_rows = int(cur.rowcount or 0)
            _logger.info(
                "[MARKETDATA][DELETE_ALL] delete_executed table=%s deleted_rows=%s",
                table_name,
                deleted_rows,
            )

            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            row = cur.fetchone()
            remaining_rows = int((row[0] if row else 0) or 0)
            _logger.info(
                "[MARKETDATA][DELETE_ALL] after_count table=%s count=%s",
                table_name,
                remaining_rows,
            )

            if previous_record_count > 0:
                if deleted_rows <= 0:
                    raise StockEodDeleteError(
                        f"Delete verification failed for {table_name}: before_count={previous_record_count}, deleted_rows={deleted_rows}."
                    )
                if remaining_rows != 0:
                    raise StockEodDeleteError(
                        f"Delete verification failed for {table_name}: remaining_rows={remaining_rows} after delete."
                    )
            con.commit()
            _logger.info(
                "[MARKETDATA][DELETE_ALL] commit_success table=%s before_count=%s deleted_rows=%s remaining_rows=%s",
                table_name,
                previous_record_count,
                deleted_rows,
                remaining_rows,
            )
        except Exception as exc:
            try:
                con.rollback()
                _logger.info("[MARKETDATA][DELETE_ALL] rollback_success table=%s", table_name)
            except Exception:
                _logger.exception("[MARKETDATA][DELETE_ALL] rollback_failed table=%s", table_name)
            _logger.exception("[MARKETDATA][DELETE_ALL] failed table=%s error=%s", table_name, exc)
            raise

    global _SUMMARY_SOURCE_CACHE
    _SUMMARY_SOURCE_CACHE = None
    _SUMMARY_SOURCE_META_CACHE.clear()
    _logger.info(
        "[MARKETDATA][DELETE_ALL] table=%s previous_record_count=%s deleted_rows=%s",
        table_name,
        previous_record_count,
        deleted_rows,
    )
    return {
        "ok": True,
        "success": True,
        "table_name": table_name,
        "previous_record_count": previous_record_count,
        "before_count": previous_record_count,
        "deleted_rows": deleted_rows,
        "remaining_rows": remaining_rows,
        "message": "Delete completed successfully.",
    }


def _tail_non_empty_lines(text: str, limit: int = FYERS_LOG_TAIL_LINES) -> list[str]:
    lines = [line.rstrip() for line in str(text or "").splitlines() if str(line).strip()]
    return lines[-max(1, int(limit or 1)):]


def _resolve_fyers_project_dir() -> Path:
    project_dir = Path(FYERS_PROJECT_DIR).expanduser()
    if not str(project_dir).strip():
        raise ValueError("FYERS_PROJECT_DIR is not configured.")
    if not project_dir.exists():
        raise ValueError(f"FYERS project directory not found: {project_dir}")
    if not (project_dir / "src").exists():
        raise ValueError(f"Invalid FYERS project directory (missing src): {project_dir}")
    return project_dir


def _resolve_fyers_data_dir(project_dir: Path | None = None) -> Path:
    resolved_project_dir = project_dir or _resolve_fyers_project_dir()
    if FYERS_DATA_DIR:
        data_dir = Path(FYERS_DATA_DIR).expanduser()
        if not data_dir.is_absolute():
            data_dir = resolved_project_dir / data_dir
    else:
        data_dir = resolved_project_dir / "data"
    return data_dir.resolve()


def _fyers_failed_symbols_source_signature() -> tuple[Any, ...]:
    return ("oracle", _FYERS_FAILED_SYMBOL_TABLE)


def _fyers_failed_symbols_cache_key(
    params: dict[str, Any],
    *,
    limit: int,
    offset: int,
) -> tuple[Any, ...]:
    filter_keys = (
        "status",
        "symbol",
        "from_date",
        "fromDate",
        "to_date",
        "toDate",
        "source_mode",
        "sourceMode",
    )
    normalized_filters = tuple(
        (key, str(params.get(key) or "").strip())
        for key in filter_keys
    )
    return (
        _fyers_failed_symbols_source_signature(),
        max(1, int(limit)),
        max(0, int(offset)),
        normalized_filters,
    )


def _get_cached_fyers_failed_symbols_payload(cache_key: tuple[Any, ...]) -> dict[str, Any] | None:
    if FYERS_FAILED_SYMBOLS_CACHE_TTL_SEC <= 0:
        return None
    now_ts = time.monotonic()
    with _FYERS_FAILED_SYMBOLS_CACHE_LOCK:
        entry = _FYERS_FAILED_SYMBOLS_CACHE.get(cache_key)
        if not entry:
            return None
        expires_at, payload = entry
        if expires_at <= now_ts:
            _FYERS_FAILED_SYMBOLS_CACHE.pop(cache_key, None)
            return None
        return copy.deepcopy(payload)


def _store_fyers_failed_symbols_payload(cache_key: tuple[Any, ...], payload: dict[str, Any]) -> None:
    if FYERS_FAILED_SYMBOLS_CACHE_TTL_SEC <= 0:
        return
    expires_at = time.monotonic() + FYERS_FAILED_SYMBOLS_CACHE_TTL_SEC
    with _FYERS_FAILED_SYMBOLS_CACHE_LOCK:
        while (
            len(_FYERS_FAILED_SYMBOLS_CACHE) >= FYERS_FAILED_SYMBOLS_CACHE_MAX_ITEMS
            and cache_key not in _FYERS_FAILED_SYMBOLS_CACHE
        ):
            _FYERS_FAILED_SYMBOLS_CACHE.pop(next(iter(_FYERS_FAILED_SYMBOLS_CACHE)), None)
        _FYERS_FAILED_SYMBOLS_CACHE[cache_key] = (expires_at, copy.deepcopy(payload))


def invalidate_fyers_failed_symbols_cache(reason: str = "") -> None:
    with _FYERS_FAILED_SYMBOLS_CACHE_LOCK:
        cleared = len(_FYERS_FAILED_SYMBOLS_CACHE)
        _FYERS_FAILED_SYMBOLS_CACHE.clear()
    if cleared:
        _logger.debug("[FYERS][FAILED_SYMBOLS][CACHE_INVALIDATED] reason=%s cleared=%s", reason, cleared)


def _resolve_fyers_python_executable(project_dir: Path) -> str:
    candidates: list[Path] = []
    if FYERS_PYTHON_EXE:
        candidates.append(Path(FYERS_PYTHON_EXE).expanduser())
    candidates.append(project_dir / ".venv" / "Scripts" / "python.exe")
    if sys.executable:
        candidates.append(Path(sys.executable))

    for candidate in candidates:
        if candidate and candidate.exists():
            return str(candidate)
    return "python"


def _load_external_fyers_modules(project_dir: Path) -> tuple[Any, Any, Any]:
    project_token = str(project_dir.resolve())
    if project_token not in sys.path:
        sys.path.insert(0, project_token)
    try:
        from src.config import load_config as external_load_config  # type: ignore
        from src.fyers_client import FyersHistoryClient as external_history_client  # type: ignore
        from src import db as external_db  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"Unable to load FYERS direct API modules from {project_dir}: {exc}") from exc
    return external_load_config, external_history_client, external_db


def _load_fyers_direct_config(project_dir: Path) -> dict[str, Any]:
    external_load_config, _history_client, _external_db = _load_external_fyers_modules(project_dir)
    current_cwd = Path.cwd()
    try:
        os.chdir(project_dir)
        cfg = dict(external_load_config())
    finally:
        os.chdir(current_cwd)
    cfg["RESOLUTION"] = FYERS_FIXED_RESOLUTION
    cfg["FYERS_MAX_RETRIES"] = str(FYERS_MAX_RETRIES)
    cfg["FYERS_RETRY_BASE_SLEEP_SECONDS"] = str(FYERS_RETRY_BASE_SLEEP_SECONDS)
    cfg["FYERS_REQUEST_SLEEP_SECONDS"] = str(FYERS_REQUEST_SLEEP_SECONDS)
    cfg["FYERS_BATCH_INSERT_SIZE"] = str(FYERS_BATCH_INSERT_SIZE)
    return cfg


def _direct_fetch_fyers_rows(
    *,
    project_dir: Path,
    symbol: str,
    start_date: dt.date,
    end_date: dt.date,
    resolution: str,
    should_stop: Optional[Callable[[], bool]] = None,
) -> tuple[list[tuple[Any, ...]], int, dict[str, Any]]:
    _raise_if_fyers_stop_requested(should_stop)
    cfg = _load_fyers_direct_config(project_dir)
    _external_load_config, external_history_client, external_db = _load_external_fyers_modules(project_dir)
    client = external_history_client(cfg.get("FYERS_ACCESS_TOKEN"), cfg.get("FYERS_APP_ID"))
    chunk_days = max(1, _parse_int(cfg.get("CHUNK_DAYS"), 100))
    candles, meta = client.fetch_history_range(
        symbol,
        start_date.isoformat(),
        end_date.isoformat(),
        resolution,
        chunk_days=chunk_days,
        max_retries=FYERS_MAX_RETRIES,
        retry_base_sleep_seconds=FYERS_RETRY_BASE_SLEEP_SECONDS,
        request_sleep_seconds=FYERS_REQUEST_SLEEP_SECONDS,
    )
    _raise_if_fyers_stop_requested(should_stop)
    rows = external_db.transform_candles(symbol, candles or [])
    return rows, len(candles or []), dict(meta or {})


def _coerce_fyers_trade_date(value: Any) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    for candidate in (text[:10], text):
        try:
            return dt.datetime.strptime(candidate, "%Y-%m-%d").date()
        except ValueError:
            continue
    return None


def _coerce_fyers_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _coerce_fyers_volume(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _normalize_fyers_upsert_row(row: tuple[Any, ...]) -> tuple[str, dt.date, float | None, float | None, float | None, float | None, int | None] | None:
    if len(row) < 7:
        return None
    symbol = str(row[0] or "").strip().upper()
    trade_date = _coerce_fyers_trade_date(row[1])
    if not symbol or trade_date is None:
        return None
    return (
        symbol,
        trade_date,
        _coerce_fyers_number(row[2]),
        _coerce_fyers_number(row[3]),
        _coerce_fyers_number(row[4]),
        _coerce_fyers_number(row[5]),
        _coerce_fyers_volume(row[6]),
    )


def _fyers_values_changed(
    current: tuple[Any, Any, Any, Any, Any] | None,
    incoming: tuple[str, dt.date, float | None, float | None, float | None, float | None, int | None],
) -> bool:
    if current is None:
        return True
    for existing_value, incoming_value in zip(current[:4], incoming[2:6]):
        existing_number = _coerce_fyers_number(existing_value)
        if existing_number is None and incoming_value is None:
            continue
        if existing_number is None or incoming_value is None:
            return True
        if abs(existing_number - incoming_value) > 0.000001:
            return True
    existing_volume = _coerce_fyers_volume(current[4])
    incoming_volume = incoming[6]
    return existing_volume != incoming_volume


def _fetch_existing_fyers_ohlcv_by_range(
    conn,
    symbol: str,
    start_date: dt.date,
    end_date: dt.date,
) -> dict[dt.date, tuple[Any, Any, Any, Any, Any]]:
    sql = """
SELECT TRUNC(TRADE_DATE) AS TRADE_DATE,
       OPEN_PRICE,
       HIGH_PRICE,
       LOW_PRICE,
       CLOSE_PRICE,
       VOLUME
FROM STOCK_EOD_HISTORY
WHERE SYMBOL = normalize_symbol(:symbol)
  AND TRUNC(TRADE_DATE) BETWEEN TRUNC(:start_date) AND TRUNC(:end_date)
    """
    existing: dict[dt.date, tuple[Any, Any, Any, Any, Any]] = {}
    with conn.cursor() as cur:
        cur.execute(sql, {"symbol": symbol, "start_date": start_date, "end_date": end_date})
        for row in cur:
            trade_date = _coerce_fyers_trade_date(row[0])
            if trade_date is None:
                continue
            existing[trade_date] = (row[1], row[2], row[3], row[4], row[5])
    return existing


def _upsert_fyers_rows_direct(conn, rows: list[tuple[Any, ...]]) -> dict[str, Any]:
    if not rows:
        return {
            "inserted": 0,
            "updated": 0,
            "skipped": 0,
            "merged": 0,
            "input_rows": 0,
            "inserted_dates": set(),
            "duplicate_dates": set(),
        }

    deduped: dict[tuple[str, dt.date], tuple[str, dt.date, float | None, float | None, float | None, float | None, int | None]] = {}
    for row in rows:
        normalized = _normalize_fyers_upsert_row(row)
        if normalized is None:
            continue
        deduped[(normalized[0], normalized[1])] = normalized
    if not deduped:
        return {
            "inserted": 0,
            "updated": 0,
            "skipped": 0,
            "merged": 0,
            "input_rows": len(rows),
            "inserted_dates": set(),
            "duplicate_dates": set(),
        }

    # FYERS has already been called before this function. Read only the fetched
    # symbol/date window here so the UI can report exact insert/update/unchanged
    # counts while the keyed MERGE remains the authoritative write operation.
    existing_by_key: dict[tuple[str, dt.date], tuple[Any, Any, Any, Any, Any]] = {}
    rows_by_symbol: dict[str, list[dt.date]] = {}
    for symbol, trade_date in deduped:
        rows_by_symbol.setdefault(symbol, []).append(trade_date)
    for symbol, trading_dates in rows_by_symbol.items():
        existing_rows = _fetch_existing_fyers_ohlcv_by_range(
            conn,
            symbol,
            min(trading_dates),
            max(trading_dates),
        )
        existing_by_key.update({(symbol, trade_date): values for trade_date, values in existing_rows.items()})

    inserted_keys = {key for key in deduped if key not in existing_by_key}
    updated_keys = {
        key
        for key, incoming in deduped.items()
        if key in existing_by_key and _fyers_values_changed(existing_by_key[key], incoming)
    }
    skipped_keys = set(deduped) - inserted_keys - updated_keys

    bind_rows = [
        {
            "symbol": row[0],
            "trade_date": row[1],
            "open_price": row[2],
            "high_price": row[3],
            "low_price": row[4],
            "close_price": row[5],
            "volume": row[6],
        }
        for row in deduped.values()
    ]
    inserted_dates = {trade_date for _symbol, trade_date in inserted_keys}
    duplicate_dates = {trade_date for _symbol, trade_date in (updated_keys | skipped_keys)}

    if bind_rows:
        sql = """
MERGE INTO STOCK_EOD_HISTORY d
USING (
  SELECT
    normalize_symbol(:symbol) SYMBOL,
    :trade_date TRADE_DATE,
    :open_price OPEN_PRICE,
    :high_price HIGH_PRICE,
    :low_price LOW_PRICE,
    :close_price CLOSE_PRICE,
    :volume VOLUME
  FROM dual
) s
ON (d.SYMBOL = s.SYMBOL AND TRUNC(d.TRADE_DATE) = TRUNC(s.TRADE_DATE))
WHEN MATCHED THEN UPDATE SET
    d.OPEN_PRICE = s.OPEN_PRICE,
    d.HIGH_PRICE = s.HIGH_PRICE,
    d.LOW_PRICE = s.LOW_PRICE,
    d.CLOSE_PRICE = s.CLOSE_PRICE,
    d.VOLUME = s.VOLUME
WHERE
    NVL(d.OPEN_PRICE, -1) <> NVL(s.OPEN_PRICE, -1)
    OR NVL(d.HIGH_PRICE, -1) <> NVL(s.HIGH_PRICE, -1)
    OR NVL(d.LOW_PRICE, -1) <> NVL(s.LOW_PRICE, -1)
    OR NVL(d.CLOSE_PRICE, -1) <> NVL(s.CLOSE_PRICE, -1)
    OR NVL(d.VOLUME, -1) <> NVL(s.VOLUME, -1)
WHEN NOT MATCHED THEN INSERT (
    SYMBOL,
    TRADE_DATE,
    OPEN_PRICE,
    HIGH_PRICE,
    LOW_PRICE,
    CLOSE_PRICE,
    VOLUME
) VALUES (
    s.SYMBOL,
    s.TRADE_DATE,
    s.OPEN_PRICE,
    s.HIGH_PRICE,
    s.LOW_PRICE,
    s.CLOSE_PRICE,
    s.VOLUME
)
        """
        with conn.cursor() as cur:
            cur.executemany(sql, bind_rows)
        conn.commit()

    return {
        "inserted": len(inserted_keys),
        "updated": len(updated_keys),
        "skipped": len(skipped_keys),
        "merged": len(bind_rows),
        "input_rows": len(rows),
        "inserted_dates": inserted_dates,
        "duplicate_dates": duplicate_dates,
    }


def _load_fyers_batch_symbols(project_dir: Path) -> list[str]:
    cfg = _load_fyers_direct_config(project_dir)
    symbols_csv = str(cfg.get("SYMBOLS_CSV") or "").strip()
    if not symbols_csv:
        raise ValueError("SYMBOLS_CSV is not configured in the FYERS project.")
    symbols_path = Path(symbols_csv)
    if not symbols_path.is_absolute():
        symbols_path = project_dir / symbols_path
    if not symbols_path.exists():
        csv_candidate = symbols_path.with_suffix(".csv") if not symbols_path.suffix else None
        if csv_candidate is not None and csv_candidate.exists():
            symbols_path = csv_candidate
        else:
            raise ValueError(f"FYERS symbols CSV not found: {symbols_path}")
    df = pd.read_csv(symbols_path, dtype=str)
    if df.empty:
        return []
    symbol_column = next((col for col in df.columns if str(col).strip().lower() == "symbol"), df.columns[0])
    symbols: list[str] = []
    seen: set[str] = set()
    for value in df[symbol_column].tolist():
        token = str(value or "").strip().upper()
        if not token or token in seen:
            continue
        seen.add(token)
        symbols.append(token)
    return symbols


def _date_range_has_weekday(start_date: dt.date, end_date: dt.date) -> bool:
    total_days = (end_date - start_date).days + 1
    if total_days >= 7:
        return True
    for offset in range(max(0, total_days)):
        if (start_date + dt.timedelta(days=offset)).weekday() < 5:
            return True
    return False


def _coerce_date_value(value: object) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    for candidate in (text[:10], text):
        try:
            return dt.datetime.strptime(candidate, "%Y-%m-%d").date()
        except ValueError:
            continue
    return None


def _raise_if_fyers_stop_requested(should_stop: Optional[Callable[[], bool]], message: str = "FYERS stop requested.") -> None:
    if not should_stop:
        return
    try:
        stop_requested = bool(should_stop())
    except Exception:
        stop_requested = False
    if stop_requested:
        raise FyersStopRequestedError(message)


def _run_fyers_module(
    module_name: str,
    args: list[str],
    *,
    timeout_sec: int,
    env_overrides: Optional[dict[str, str]] = None,
    on_stdout_line: Optional[Callable[[str], None]] = None,
    on_stderr_line: Optional[Callable[[str], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
    abort_on_output: Optional[Callable[[str], bool]] = None,
    abort_message: str = "",
) -> dict[str, Any]:
    project_dir = _resolve_fyers_project_dir()
    python_exe = _resolve_fyers_python_executable(project_dir)
    command = [python_exe, "-u", "-m", module_name, *args]

    env = os.environ.copy()
    env_file = project_dir / ".env"
    if env_file.exists():
        try:
            for raw_line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if not key:
                    continue
                parsed = value.strip()
                if len(parsed) >= 2 and parsed[0] == parsed[-1] and parsed[0] in {"'", '"'}:
                    parsed = parsed[1:-1]
                env[key] = parsed
        except Exception:
            pass
    if env_overrides:
        for key, value in env_overrides.items():
            if value is None:
                continue
            env[str(key)] = str(value)
    env, proxy_policy = _apply_fyers_proxy_policy(env)

    started = time.monotonic()
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    timed_out = False
    aborted_by_output = False
    aborted_by_stop = False
    abort_reason = ""

    def _consume_lines(stream, sink: list[str], callback: Optional[Callable[[str], None]]) -> None:
        nonlocal aborted_by_output, aborted_by_stop, abort_reason
        try:
            for raw in iter(stream.readline, ""):
                if raw is None:
                    continue
                line = str(raw).rstrip("\r\n")
                sink.append(line)
                if callback and line:
                    try:
                        callback(line)
                    except Exception:
                        pass
                if abort_on_output and line:
                    try:
                        should_abort = bool(abort_on_output(line))
                    except Exception:
                        should_abort = False
                if should_abort and not aborted_by_output:
                    aborted_by_output = True
                    abort_reason = abort_message or line
                    try:
                            proc.kill()
                    except Exception:
                            pass
                if should_stop and not aborted_by_output:
                    try:
                        stop_requested = bool(should_stop())
                    except Exception:
                        stop_requested = False
                    if stop_requested:
                        aborted_by_output = True
                        aborted_by_stop = True
                        abort_reason = _FYERS_STOP_REQUEST_REASON
                        try:
                            proc.kill()
                        except Exception:
                            pass
        finally:
            try:
                stream.close()
            except Exception:
                pass

    try:
        proc = subprocess.Popen(
            command,
            cwd=str(project_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )
    except Exception as exc:
        elapsed = round(time.monotonic() - started, 3)
        return {
            "ok": False,
            "returncode": 1,
            "timed_out": False,
            "duration_seconds": elapsed,
            "stdout": "",
            "stderr": str(exc),
            "stdout_tail": [],
            "stderr_tail": [str(exc)],
            "command": command,
            "cwd": str(project_dir),
            "proxy_policy": proxy_policy.get("mode"),
            "proxy_env": proxy_policy.get("proxy"),
        }

    out_thread = threading.Thread(
        target=_consume_lines,
        args=(proc.stdout, stdout_lines, on_stdout_line),  # type: ignore[arg-type]
        daemon=True,
    )
    err_thread = threading.Thread(
        target=_consume_lines,
        args=(proc.stderr, stderr_lines, on_stderr_line),  # type: ignore[arg-type]
        daemon=True,
    )
    out_thread.start()
    err_thread.start()

    try:
        proc.wait(timeout=max(1, int(timeout_sec or 1)))
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            proc.kill()
        except Exception:
            pass
    if aborted_by_output and proc.returncode is None:
        try:
            proc.kill()
        except Exception:
            pass

    out_thread.join(timeout=2)
    err_thread.join(timeout=2)

    elapsed = round(time.monotonic() - started, 3)
    returncode = int(proc.returncode) if proc.returncode is not None else (124 if timed_out else 1)
    stdout_text = "\n".join(stdout_lines)
    stderr_text = "\n".join(stderr_lines)
    if timed_out and on_stderr_line:
        try:
            on_stderr_line(f"Process timed out after {max(1, int(timeout_sec or 1))} seconds.")
        except Exception:
            pass

    return {
        "ok": (returncode == 0) and (not timed_out),
        "returncode": returncode,
        "timed_out": timed_out,
        "duration_seconds": elapsed,
        "stdout": stdout_text,
        "stderr": stderr_text,
        "stdout_tail": _tail_non_empty_lines(stdout_text),
        "stderr_tail": _tail_non_empty_lines(stderr_text),
        "command": command,
        "cwd": str(project_dir),
        "proxy_policy": proxy_policy.get("mode"),
        "proxy_env": proxy_policy.get("proxy"),
        "aborted_by_output": aborted_by_output,
        "aborted_by_stop": aborted_by_stop,
        "abort_reason": abort_reason,
    }


def _parse_iso_date(value: object, field_name: str) -> dt.date:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required (YYYY-MM-DD).")
    try:
        return dt.datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{field_name} must be YYYY-MM-DD.") from exc


def _split_symbol_input_tokens(symbol_input: object) -> list[str]:
    tokens: list[str] = []
    values = symbol_input if isinstance(symbol_input, (list, tuple, set)) else [symbol_input]
    for value in values:
        tokens.extend(token.strip() for token in str(value or "").replace("\n", ",").split(","))
    return [token for token in tokens if token]


def _extract_exact_fyers_symbol(value: object) -> str | None:
    text = "".join(str(value or "").upper().split())
    if not text:
        return None
    match = _FYERS_EXACT_SYMBOL_RE.match(text)
    if not match:
        return None
    suffix = str(match.group(2) or "").upper()
    if suffix not in _FYERS_MASTER_ALLOWED_SUFFIXES_SET:
        return None
    return text


def _canonical_fyers_lookup_key(value: object) -> str:
    text = "".join(str(value or "").upper().split())
    if not text:
        return ""
    if ":" in text:
        text = text.split(":", 1)[1]
    if text.endswith(".NS"):
        text = text[:-3]
    text = _FYERS_INPUT_SERIES_RE.sub("", text)
    return _FYERS_LOOKUP_KEY_RE.sub("", text)


def _clean_fyers_lookup_symbol(value: object) -> str:
    text = "".join(str(value or "").upper().split())
    if not text:
        return ""
    if ":" in text:
        text = text.split(":", 1)[1]
    if text.endswith(".NS"):
        text = text[:-3]
    text = _FYERS_INPUT_SERIES_RE.sub("", text)
    corrected = _FYERS_MANUAL_SYMBOL_CORRECTIONS.get(_canonical_fyers_lookup_key(text), text)
    return str(corrected or "").strip("-")


def _build_fyers_symbol_lookup(master_df: pd.DataFrame) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for row in master_df.itertuples(index=False, name=None):
        exact_symbol = next(
            (candidate for candidate in (_extract_exact_fyers_symbol(value) for value in row) if candidate),
            None,
        )
        if not exact_symbol:
            continue
        symbol_body = exact_symbol.split(":", 1)[1]
        base_symbol, _series = symbol_body.rsplit("-", 1)
        for key in {base_symbol, _canonical_fyers_lookup_key(base_symbol)}:
            if key and key not in lookup:
                lookup[key] = exact_symbol

    for alias_key, target_symbol in _FYERS_MANUAL_SYMBOL_CORRECTIONS.items():
        resolved_symbol = lookup.get(target_symbol) or lookup.get(_canonical_fyers_lookup_key(target_symbol))
        if resolved_symbol:
            lookup[alias_key] = resolved_symbol

    return lookup


def _get_fyers_symbol_lookup(*, force_refresh: bool = False) -> dict[str, str]:
    now_ts = time.time()
    with _FYERS_SYMBOL_MASTER_LOCK:
        cached_lookup = dict(_FYERS_SYMBOL_MASTER_CACHE.get("lookup") or {})
        loaded_at = float(_FYERS_SYMBOL_MASTER_CACHE.get("loaded_at") or 0.0)
        cache_is_fresh = cached_lookup and (now_ts - loaded_at) < FYERS_SYMBOL_MASTER_CACHE_TTL_SEC
        if not force_refresh and cache_is_fresh:
            return cached_lookup

    try:
        master_df = pd.read_csv(
            FYERS_SYMBOL_MASTER_URL,
            header=None,
            dtype=str,
            keep_default_na=False,
            na_filter=False,
        )
        lookup = _build_fyers_symbol_lookup(master_df)
        if not lookup:
            raise ValueError("No NSE CM symbols were parsed from the FYERS master CSV.")
    except Exception as exc:
        if cached_lookup:
            _logger.warning(
                "[FYERS_SYMBOL_MASTER] refresh failed url=%s entries=%s error=%s using_stale_cache=1",
                FYERS_SYMBOL_MASTER_URL,
                len(cached_lookup),
                exc,
            )
            return cached_lookup
        raise RuntimeError(f"Unable to load FYERS symbol master from {FYERS_SYMBOL_MASTER_URL}: {exc}") from exc

    with _FYERS_SYMBOL_MASTER_LOCK:
        _FYERS_SYMBOL_MASTER_CACHE["loaded_at"] = now_ts
        _FYERS_SYMBOL_MASTER_CACHE["lookup"] = dict(lookup)
    _logger.info(
        "[FYERS_SYMBOL_MASTER] loaded url=%s entries=%s",
        FYERS_SYMBOL_MASTER_URL,
        len(lookup),
    )
    return dict(lookup)


def resolve_fyers_symbol(raw_input_symbol: str, fyers_lookup: dict[str, str]) -> str | None:
    clean_symbol = _clean_fyers_lookup_symbol(raw_input_symbol)
    if not clean_symbol:
        return None
    for lookup_key in (clean_symbol, _canonical_fyers_lookup_key(clean_symbol)):
        resolved_symbol = _extract_exact_fyers_symbol(fyers_lookup.get(lookup_key))
        if resolved_symbol:
            return resolved_symbol
    return None


def _build_fyers_symbol_resolution_row(raw_input_symbol: object, fyers_lookup: dict[str, str]) -> dict[str, Any]:
    input_symbol = "".join(str(raw_input_symbol or "").upper().split())
    clean_symbol = _clean_fyers_lookup_symbol(raw_input_symbol)
    attempted_symbol = _normalize_fyers_symbol(clean_symbol) if clean_symbol else ""
    resolved_symbol = resolve_fyers_symbol(str(raw_input_symbol or ""), fyers_lookup) if clean_symbol else None
    status = "OK" if resolved_symbol else "MISSING"
    return {
        "input_symbol": input_symbol,
        "clean_symbol": clean_symbol,
        "resolved_symbol": resolved_symbol,
        "normalized_symbol": resolved_symbol or attempted_symbol,
        "resolved": bool(resolved_symbol),
        "resolution_status": status,
    }


def _log_fyers_symbol_resolution(row: dict[str, Any], line_logger: Optional[Callable[[str], None]] = None) -> None:
    message = (
        "[FYERS_SYMBOL_RESOLVE] "
        f"Input={row.get('input_symbol') or 'UNKNOWN'} "
        f"Clean={row.get('clean_symbol') or 'UNKNOWN'} "
        f"Resolved={row.get('resolved_symbol') or 'None'} "
        f"Status={row.get('resolution_status') or 'UNKNOWN'}"
    )
    _logger.info(message)
    if line_logger:
        try:
            line_logger(message)
        except Exception:
            pass


def _resolve_fyers_symbol_rows(
    input_symbols: list[str],
    *,
    line_logger: Optional[Callable[[str], None]] = None,
) -> list[dict[str, Any]]:
    if not input_symbols:
        return []
    fyers_lookup = _get_fyers_symbol_lookup()
    rows: list[dict[str, Any]] = []
    seen_symbols: set[str] = set()
    for raw_input_symbol in input_symbols:
        row = _build_fyers_symbol_resolution_row(raw_input_symbol, fyers_lookup)
        normalized_symbol = str(row.get("normalized_symbol") or "").strip()
        if not normalized_symbol or normalized_symbol in seen_symbols:
            continue
        seen_symbols.add(normalized_symbol)
        _log_fyers_symbol_resolution(row, line_logger=line_logger)
        rows.append(row)
    return rows


def resolve_fyers_symbols(
    input_symbols: list[str],
    *,
    line_logger: Optional[Callable[[str], None]] = None,
) -> tuple[list[str], list[dict[str, str]]]:
    resolved_symbols: list[str] = []
    missing_symbols: list[dict[str, str]] = []
    for row in _resolve_fyers_symbol_rows(input_symbols, line_logger=line_logger):
        normalized_symbol = str(row.get("normalized_symbol") or "").strip()
        if row.get("resolved"):
            resolved_symbols.append(normalized_symbol)
            continue
        missing_symbols.append({
            "input_symbol": str(row.get("input_symbol") or ""),
            "clean_symbol": str(row.get("clean_symbol") or ""),
            "normalized_symbol": normalized_symbol,
            "error_message": "Symbol not found in FYERS symbol master.",
        })
    return resolved_symbols, missing_symbols


def _normalize_fyers_symbol(symbol: object) -> str:
    text = "".join(str(symbol or "").upper().split())
    if not text:
        raise ValueError("symbol is required.")
    if text.endswith(".NS"):
        text = text[:-3]
    if ":" in text:
        return text
    if not _FYERS_INPUT_SERIES_RE.search(text):
        text = f"{text}-EQ"
    return f"NSE:{text}"


def _normalize_fyers_display_symbol(symbol: object) -> str:
    text = "".join(str(symbol or "").upper().split())
    if not text:
        return ""
    if ":" in text:
        text = text.split(":", 1)[1]
    if text.endswith(".NS"):
        text = text[:-3]
    text = _FYERS_INPUT_SERIES_RE.sub("", text)
    return text.strip()


def _normalize_resolution(value: object) -> str:
    text = "".join(str(value or "1D").upper().split()) or "1D"
    if not re.match(r"^[A-Z0-9]+$", text):
        raise ValueError("resolution should contain only letters/numbers (examples: 1D, D, W, 60).")
    return text


def _parse_iso_date_with_default(value: object, field_name: str, default_value: dt.date) -> dt.date:
    text = str(value or "").strip()
    if not text:
        return default_value
    return _parse_iso_date(text, field_name)


def _normalize_symbols_payload(
    symbol_input: object,
    *,
    line_logger: Optional[Callable[[str], None]] = None,
) -> list[dict[str, Any]]:
    tokens = _split_symbol_input_tokens(symbol_input)
    normalized_rows = _resolve_fyers_symbol_rows(tokens, line_logger=line_logger)
    if not normalized_rows:
        raise ValueError("Stock name is required.")
    return normalized_rows


def _extract_last_non_empty_line(text: str) -> str:
    for line in reversed(str(text or "").splitlines()):
        candidate = str(line).strip()
        if candidate:
            return candidate
    return ""


def _classify_symbol_failure(text: str, *, stage: str) -> tuple[str, str, str]:
    message = _extract_last_non_empty_line(text) or "Request failed."
    if _is_fyers_auth_failure(text):
        return ("FAILED_AUTH", "FYERS_AUTH_FAILED", "FYERS authentication failed. Authorize FYERS and retry.")
    if _FYERS_INVALID_SYMBOL_RE.search(text):
        return ("FAILED_INVALID_SYMBOL", "INVALID_SYMBOL", "FYERS rejected symbol")
    if _FYERS_RATE_LIMIT_RE.search(text):
        return ("FAILED_RATE_LIMIT", "RATE_LIMIT", "FYERS request limit exceeded")
    if _FYERS_NO_DATA_RE.search(text):
        return ("FAILED_NO_DATA", "NO_DATA", "No candle data returned by FYERS")
    if stage == "load":
        return ("FAILED_DB_ERROR", "DB_ERROR", message)
    return ("FAILED_API_ERROR", "API_ERROR", message)


def _contains_db_error_signature(text: str) -> bool:
    raw = str(text or "")
    return (
        ("ORA-" in raw.upper())
        or ("DPI-" in raw.upper())
        or ("DPY-" in raw.upper())
        or bool(re.search(r"\bDatabase error\b", raw, flags=re.IGNORECASE))
    )


def _db_error_code(error: Exception) -> int | None:
    obj = None
    if getattr(error, "args", None):
        obj = error.args[0]
    return getattr(obj, "code", None)


def _execute_ddl_ignore_exists(conn, ddl: str) -> None:
    with conn.cursor() as cur:
        try:
            cur.execute(ddl)
        except Exception as exc:
            code = _db_error_code(exc)
            if code in {955, 1408}:  # ORA-00955 name is already used; ORA-01408 column list already indexed
                return
            raise


def _load_table_columns(conn, table_name: str) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COLUMN_NAME
            FROM USER_TAB_COLUMNS
            WHERE TABLE_NAME = :table_name
            """,
            {"table_name": str(table_name or "").strip().upper()},
        )
        return {str(row[0]).strip().upper() for row in cur.fetchall() if row and row[0]}


def _ensure_table_columns(conn, table_name: str, definitions: dict[str, str]) -> set[str]:
    table_token = str(table_name or "").strip().upper()
    current_columns = _load_table_columns(conn, table_token)
    for column_name, ddl in definitions.items():
        normalized_name = str(column_name or "").strip().upper()
        if normalized_name in current_columns:
            continue
        _execute_ddl_ignore_exists(conn, f"ALTER TABLE {table_token} ADD ({normalized_name} {ddl})")
        current_columns.add(normalized_name)
    return current_columns


def _normalize_failed_symbol_status(
    status: object = None,
    reason: object = None,
    error_code: object = None,
) -> str:
    token = str(status or "").strip().upper()
    if token in {"FAILED", "SKIPPED", "REJECTED", "AUTH_FAILED", "NO_DATA", "API_ERROR"}:
        return token
    reason_token = str(reason or error_code or "").strip().upper()
    if reason_token in {"FAILED_INVALID_SYMBOL", "INVALID_SYMBOL", "REJECTED_SYMBOL"}:
        return "REJECTED"
    if reason_token in {"FAILED_NO_DATA", "NO_DATA", "NO_TRADING_DATA_IN_WINDOW", "TRANSFORM_EMPTY_ROWS"}:
        return "NO_DATA"
    if reason_token in {"FAILED_AUTH", "FYERS_AUTH_FAILED"}:
        return "AUTH_FAILED"
    if reason_token in {"FETCH_FAILED", "FAILED_API_ERROR", "FAILED_RATE_LIMIT", "API_ERROR", "RATE_LIMIT"}:
        return "API_ERROR"
    if reason_token.startswith("SKIP"):
        return "SKIPPED"
    return "FAILED"


def _normalize_failed_symbol_source_mode(value: object = None) -> str:
    token = str(value or "").strip().upper()
    if token in {"CSV_BATCH", "SINGLE_STOCK", "AUTO_BATCH", "SINGLE_STOCK_RERUN"}:
        return token
    return "CSV_BATCH"


def _normalize_failed_symbol_rerun_status(value: object = None) -> str:
    token = str(value or "").strip().upper()
    if token in {"PENDING", "RUNNING", "SUCCESS", "FAILED", "SKIPPED"}:
        return token
    return "PENDING"


def _normalize_failed_symbol_text(value: object, max_length: int) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text[:max(1, int(max_length))]


def _ensure_fyers_failed_symbols_columns(conn) -> set[str]:
    return _ensure_table_columns(
        conn,
        _FYERS_FAILED_SYMBOL_TABLE,
        {
            "RUN_ID": "VARCHAR2(120)",
            "FYERS_SYMBOL": "VARCHAR2(100)",
            "FROM_DATE": "DATE",
            "TO_DATE": "DATE",
            "STATUS": "VARCHAR2(30)",
            "REASON": "VARCHAR2(500)",
            "ERROR_CODE": "VARCHAR2(120)",
            "ERROR_MESSAGE": "VARCHAR2(4000)",
            "SOURCE_MODE": "VARCHAR2(40)",
            "RERUN_STATUS": "VARCHAR2(30)",
            "RERUN_COUNT": "NUMBER DEFAULT 0",
            "LAST_RERUN_TS": "TIMESTAMP",
            "CREATED_AT": "TIMESTAMP DEFAULT SYSTIMESTAMP",
            "UPDATED_AT": "TIMESTAMP",
        },
    )


def _ensure_fyers_extraction_columns(conn) -> None:
    _ensure_table_columns(
        conn,
        "FYERS_EXTRACTION_RUNS",
        {
            "JOB_TYPE": "VARCHAR2(40) DEFAULT 'batch'",
            "INSERTED_COUNT": "NUMBER DEFAULT 0",
            "REMAINING_COUNT": "NUMBER DEFAULT 0",
            "INSERTED_SKIPPED_COUNT": "NUMBER DEFAULT 0",
            "INVALID_COUNT": "NUMBER DEFAULT 0",
            "ERROR_COUNT": "NUMBER DEFAULT 0",
            "REQUESTED_STOP_FLAG": "CHAR(1) DEFAULT 'N'",
        },
    )
    _ensure_table_columns(
        conn,
        "FYERS_EXTRACTION_SYMBOL_STATUS",
        {
            "STATUS_REASON": "VARCHAR2(500)",
            "RETRY_COUNT": "NUMBER DEFAULT 0",
        },
    )


def _ensure_fyers_tracking_tables(conn) -> None:
    global _FYERS_TRACKING_SCHEMA_READY
    if _FYERS_TRACKING_SCHEMA_READY:
        return
    with _FYERS_TRACKING_SCHEMA_LOCK:
        if _FYERS_TRACKING_SCHEMA_READY:
            return
        _execute_ddl_ignore_exists(
            conn,
            """
CREATE TABLE FYERS_REUSE_SYMBOLS (
    ID NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    INPUT_SYMBOL VARCHAR2(100),
    NORMALIZED_SYMBOL VARCHAR2(100),
    STATUS VARCHAR2(50),
    ERROR_CODE VARCHAR2(100),
    ERROR_MESSAGE VARCHAR2(4000),
    START_DATE DATE,
    END_DATE DATE,
    RESOLUTION VARCHAR2(10) DEFAULT '1D',
    RETRY_COUNT NUMBER DEFAULT 0,
    SOURCE VARCHAR2(50) DEFAULT 'FYERS_SINGLE_STOCK',
    CREATED_AT TIMESTAMP DEFAULT SYSTIMESTAMP,
    UPDATED_AT TIMESTAMP,
    CONSTRAINT CK_FYERS_REUSE_RESOLUTION CHECK (RESOLUTION = '1D')
)
            """.strip(),
        )
        _execute_ddl_ignore_exists(
            conn,
            """
CREATE TABLE FYERS_SUCCESS_SYMBOLS (
    ID NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    SYMBOL VARCHAR2(100) NOT NULL,
    TRADING_DATE DATE NOT NULL,
    RESOLUTION VARCHAR2(10) DEFAULT '1D',
    INSERTED_ROWS NUMBER DEFAULT 0,
    DUPLICATE_ROWS_SKIPPED NUMBER DEFAULT 0,
    STATUS VARCHAR2(30) DEFAULT 'SUCCESS',
    SOURCE VARCHAR2(50) DEFAULT 'FYERS_SINGLE_STOCK',
    CREATED_AT TIMESTAMP DEFAULT SYSTIMESTAMP,
    UPDATED_AT TIMESTAMP,
    CONSTRAINT UK_FYERS_SUCCESS_SYMBOLS UNIQUE (SYMBOL, TRADING_DATE),
    CONSTRAINT CK_FYERS_SUCCESS_RESOLUTION CHECK (RESOLUTION = '1D')
)
            """.strip(),
        )
        _execute_ddl_ignore_exists(
            conn,
            """
CREATE TABLE FYERS_API_SKIPED_REJECTED_SYMBOLS (
    S_NO NUMBER GENERATED BY DEFAULT AS IDENTITY,
    RUN_ID VARCHAR2(120),
    SYMBOL VARCHAR2(100),
    FYERS_SYMBOL VARCHAR2(100),
    TRADING_DATE DATE,
    FROM_DATE DATE,
    TO_DATE DATE,
    STATUS VARCHAR2(30),
    REASON VARCHAR2(500),
    ERROR_CODE VARCHAR2(120),
    ERROR_MESSAGE VARCHAR2(4000),
    SOURCE_MODE VARCHAR2(40),
    RERUN_STATUS VARCHAR2(30),
    RERUN_COUNT NUMBER DEFAULT 0,
    LAST_RERUN_TS TIMESTAMP,
    CREATED_AT TIMESTAMP DEFAULT SYSTIMESTAMP,
    UPDATED_AT TIMESTAMP
)
            """.strip(),
        )
        _execute_ddl_ignore_exists(
            conn,
            """
CREATE TABLE FYERS_EXTRACTION_RUNS (
    JOB_ID VARCHAR2(100) PRIMARY KEY,
    JOB_TYPE VARCHAR2(40) DEFAULT 'batch',
    TRADING_DATE DATE,
    STATUS VARCHAR2(30),
    TOTAL_SYMBOLS NUMBER,
    COMPLETED_COUNT NUMBER,
    INSERTED_COUNT NUMBER DEFAULT 0,
    REMAINING_COUNT NUMBER DEFAULT 0,
    FAILED_COUNT NUMBER,
    SKIPPED_COUNT NUMBER,
    INSERTED_SKIPPED_COUNT NUMBER DEFAULT 0,
    INVALID_COUNT NUMBER DEFAULT 0,
    ERROR_COUNT NUMBER DEFAULT 0,
    STARTED_AT TIMESTAMP DEFAULT SYSTIMESTAMP,
    UPDATED_AT TIMESTAMP,
    COMPLETED_AT TIMESTAMP,
    REQUESTED_STOP_FLAG CHAR(1) DEFAULT 'N',
    ERROR_MESSAGE VARCHAR2(4000)
)
            """.strip(),
        )
        _execute_ddl_ignore_exists(
            conn,
            """
CREATE TABLE FYERS_EXTRACTION_SYMBOL_STATUS (
    JOB_ID VARCHAR2(100) NOT NULL,
    TRADING_DATE DATE NOT NULL,
    SYMBOL VARCHAR2(100) NOT NULL,
    STATUS VARCHAR2(30),
    STATUS_REASON VARCHAR2(500),
    ATTEMPT_COUNT NUMBER DEFAULT 0,
    RETRY_COUNT NUMBER DEFAULT 0,
    ERROR_MESSAGE VARCHAR2(4000),
    STARTED_AT TIMESTAMP DEFAULT SYSTIMESTAMP,
    UPDATED_AT TIMESTAMP,
    COMPLETED_AT TIMESTAMP,
    CONSTRAINT PK_FYERS_EXT_SYM_STATUS PRIMARY KEY (JOB_ID, TRADING_DATE, SYMBOL)
)
            """.strip(),
        )
        _execute_ddl_ignore_exists(
            conn,
            "CREATE INDEX IDX_FYERS_EXT_RUNS_01 ON FYERS_EXTRACTION_RUNS (TRADING_DATE, STATUS)",
        )
        _execute_ddl_ignore_exists(
            conn,
            "CREATE INDEX IDX_FYERS_EXT_SYM_01 ON FYERS_EXTRACTION_SYMBOL_STATUS (TRADING_DATE, SYMBOL, STATUS)",
        )
        _ensure_fyers_failed_symbols_columns(conn)
        _ensure_fyers_extraction_columns(conn)
        _execute_ddl_ignore_exists(
            conn,
            "CREATE INDEX IDX_FYERS_REUSE_SYMBOLS_01 ON FYERS_REUSE_SYMBOLS (NORMALIZED_SYMBOL, STATUS)",
        )
        _execute_ddl_ignore_exists(
            conn,
            "CREATE INDEX IDX_FYERS_REUSE_SYMBOLS_02 ON FYERS_REUSE_SYMBOLS (CREATED_AT)",
        )
        _execute_ddl_ignore_exists(
            conn,
            "CREATE INDEX IDX_FYERS_REUSE_SYMBOLS_03 ON FYERS_REUSE_SYMBOLS (START_DATE, END_DATE)",
        )
        _execute_ddl_ignore_exists(
            conn,
            "CREATE INDEX IDX_FYERS_SUCCESS_SYMBOLS_01 ON FYERS_SUCCESS_SYMBOLS (SYMBOL, TRADING_DATE)",
        )
        _execute_ddl_ignore_exists(
            conn,
            "CREATE INDEX IDX_FYERS_SUCCESS_SYMBOLS_02 ON FYERS_SUCCESS_SYMBOLS (TRADING_DATE, STATUS)",
        )
        _execute_ddl_ignore_exists(
            conn,
            "CREATE INDEX IDX_FYERS_SKIP_REJECTED_01 ON FYERS_API_SKIPED_REJECTED_SYMBOLS (STATUS, RERUN_STATUS)",
        )
        _execute_ddl_ignore_exists(
            conn,
            "CREATE INDEX IDX_FYERS_SKIP_REJECTED_02 ON FYERS_API_SKIPED_REJECTED_SYMBOLS (SYMBOL, TRADING_DATE)",
        )
        conn.commit()
        _FYERS_TRACKING_SCHEMA_READY = True


def _db_init_extraction_run(
    conn,
    job_id: str,
    trading_date: dt.date,
    total_symbols: int,
    *,
    job_type: str = "batch",
) -> None:
    sql = """
    MERGE INTO FYERS_EXTRACTION_RUNS target
    USING (
        SELECT :job_id AS JOB_ID,
               :job_type AS JOB_TYPE,
               :trading_date AS TRADING_DATE,
               :total_symbols AS TOTAL_SYMBOLS
        FROM DUAL
    ) source
    ON (target.JOB_ID = source.JOB_ID)
    WHEN MATCHED THEN UPDATE SET
        target.JOB_TYPE = source.JOB_TYPE,
        target.TRADING_DATE = source.TRADING_DATE,
        target.STATUS = 'RUNNING',
        target.TOTAL_SYMBOLS = source.TOTAL_SYMBOLS,
        target.REMAINING_COUNT = source.TOTAL_SYMBOLS,
        target.UPDATED_AT = SYSTIMESTAMP,
        target.COMPLETED_AT = NULL,
        target.REQUESTED_STOP_FLAG = 'N',
        target.ERROR_MESSAGE = NULL
    WHEN NOT MATCHED THEN INSERT (
        JOB_ID, JOB_TYPE, TRADING_DATE, STATUS, TOTAL_SYMBOLS, COMPLETED_COUNT,
        INSERTED_COUNT, REMAINING_COUNT, FAILED_COUNT, SKIPPED_COUNT,
        INSERTED_SKIPPED_COUNT, INVALID_COUNT, ERROR_COUNT, STARTED_AT,
        UPDATED_AT, REQUESTED_STOP_FLAG
    ) VALUES (
        source.JOB_ID, source.JOB_TYPE, source.TRADING_DATE, 'RUNNING',
        source.TOTAL_SYMBOLS, 0, 0, source.TOTAL_SYMBOLS, 0, 0, 0, 0, 0,
        SYSTIMESTAMP, SYSTIMESTAMP, 'N'
    )
    """
    with conn.cursor() as cur:
        cur.execute(sql, {
            "job_id": job_id,
            "job_type": str(job_type or "batch")[:40],
            "trading_date": trading_date,
            "total_symbols": max(int(total_symbols or 0), 0),
        })
    conn.commit()


def _db_init_extraction_symbols(conn, job_id: str, trading_date: dt.date, symbols: list[str]) -> None:
    sql = """
    MERGE INTO FYERS_EXTRACTION_SYMBOL_STATUS target
    USING (
        SELECT :job_id AS JOB_ID, :trading_date AS TRADING_DATE, :symbol AS SYMBOL
        FROM DUAL
    ) source
    ON (
        target.JOB_ID = source.JOB_ID
        AND target.TRADING_DATE = source.TRADING_DATE
        AND target.SYMBOL = source.SYMBOL
    )
    WHEN NOT MATCHED THEN INSERT (
        JOB_ID, TRADING_DATE, SYMBOL, STATUS, ATTEMPT_COUNT, RETRY_COUNT, STARTED_AT
    ) VALUES (
        source.JOB_ID, source.TRADING_DATE, source.SYMBOL, 'PENDING', 0, 0, SYSTIMESTAMP
    )
    """
    binds = [{"job_id": job_id, "trading_date": trading_date, "symbol": sym} for sym in symbols]
    with conn.cursor() as cur:
        cur.executemany(sql, binds)
    conn.commit()


def _canonical_fyers_symbol_status(
    status: object,
    reason: object = None,
    error_message: object = None,
) -> str:
    token = str(status or "").strip().upper()
    reason_text = " ".join(
        part for part in (
            str(reason or "").strip(),
            str(error_message or "").strip(),
        )
        if part
    ).upper()
    if token in {
        "PENDING",
        "RUNNING",
        "INSERTED",
        "SKIPPED_ALREADY_INSERTED",
        "SKIPPED_AFTER_INSERTED",
        "INVALID",
        "ERROR",
        "STOPPED",
    }:
        return token
    if token in {"SUCCESS", "SUCCEEDED", "COMPLETED"}:
        return "INSERTED"
    if token in {"FAILED_INVALID_SYMBOL", "REJECTED"} or "INVALID_SYMBOL" in reason_text or "INVALID SYMBOL" in reason_text:
        return "INVALID"
    if (
        token in {"FAILED_DB_ERROR", "FAILED_API_ERROR", "FAILED_AUTH", "FAILED_RATE_LIMIT", "API_ERROR", "AUTH_FAILED"}
        or "DB_ERROR" in reason_text
        or "API_ERROR" in reason_text
        or "ORA-" in reason_text
    ):
        return "ERROR"
    if token in {"FAILED_NO_DATA", "NO_DATA"}:
        return "FAILED"
    if token == "SKIPPED":
        if "ALREADY INSERTED" in reason_text:
            return "SKIPPED_ALREADY_INSERTED"
        if "PREVIOUSLY FAILED" in reason_text or "NO DATA" in reason_text:
            return "FAILED"
        return "SKIPPED_AFTER_INSERTED"
    if token == "FAILED":
        return "FAILED"
    if token.startswith("FAILED"):
        return "FAILED"
    if token in {"CANCELLED", "CANCELED"}:
        return "STOPPED"
    return token or "PENDING"


def _db_update_extraction_symbol(
    conn,
    job_id: str,
    trading_date: dt.date,
    symbol: str,
    status: str,
    error_message: str | None = None,
) -> None:
    canonical_status = _canonical_fyers_symbol_status(status, error_message, error_message)
    status_reason = str(error_message or "").strip()[:500] or None
    sql = """
    UPDATE FYERS_EXTRACTION_SYMBOL_STATUS
    SET STATUS = :status,
        STATUS_REASON = :status_reason,
        ATTEMPT_COUNT = ATTEMPT_COUNT + CASE WHEN :status = 'RUNNING' THEN 1 ELSE 0 END,
        RETRY_COUNT = RETRY_COUNT + CASE WHEN :status = 'RUNNING' THEN 1 ELSE 0 END,
        ERROR_MESSAGE = :error_message,
        UPDATED_AT = SYSTIMESTAMP,
        COMPLETED_AT = CASE
            WHEN :status IN (
                'INSERTED', 'SKIPPED_ALREADY_INSERTED', 'SKIPPED_AFTER_INSERTED',
                'FAILED', 'INVALID', 'ERROR', 'STOPPED'
            ) THEN SYSTIMESTAMP
            ELSE COMPLETED_AT
        END
    WHERE JOB_ID = :job_id AND TRADING_DATE = :trading_date AND SYMBOL = :symbol
    """
    with conn.cursor() as cur:
        cur.execute(sql, {
            "status": canonical_status,
            "status_reason": status_reason,
            "error_message": str(error_message or "")[:4000] if error_message else None,
            "job_id": job_id,
            "trading_date": trading_date,
            "symbol": symbol
        })
    conn.commit()


def _db_update_extraction_run_counts(conn, job_id: str, status: str | None = None, error_message: str | None = None) -> None:
    sql_counts = """
    SELECT
        COUNT(*) AS TOTAL,
        SUM(CASE WHEN STATUS IN ('SUCCESS', 'INSERTED') THEN 1 ELSE 0 END) AS INSERTED,
        SUM(CASE WHEN STATUS = 'FAILED' THEN 1 ELSE 0 END) AS FAILED,
        SUM(CASE WHEN STATUS IN ('SKIPPED', 'SKIPPED_ALREADY_INSERTED', 'SKIPPED_AFTER_INSERTED') THEN 1 ELSE 0 END) AS SKIPPED,
        SUM(CASE WHEN STATUS IN ('SKIPPED_ALREADY_INSERTED', 'SKIPPED_AFTER_INSERTED') THEN 1 ELSE 0 END) AS INSERTED_SKIPPED,
        SUM(CASE WHEN STATUS = 'INVALID' THEN 1 ELSE 0 END) AS INVALID,
        SUM(CASE WHEN STATUS = 'ERROR' THEN 1 ELSE 0 END) AS ERRORS,
        SUM(CASE WHEN STATUS IN ('PENDING', 'RUNNING', 'STOPPED') THEN 1 ELSE 0 END) AS REMAINING
    FROM FYERS_EXTRACTION_SYMBOL_STATUS
    WHERE JOB_ID = :job_id
    """
    sql_update = """
    UPDATE FYERS_EXTRACTION_RUNS
    SET COMPLETED_COUNT = :completed,
        INSERTED_COUNT = :inserted,
        REMAINING_COUNT = :remaining,
        FAILED_COUNT = :failed,
        SKIPPED_COUNT = :skipped,
        INSERTED_SKIPPED_COUNT = :inserted_skipped,
        INVALID_COUNT = :invalid,
        ERROR_COUNT = :errors,
        UPDATED_AT = SYSTIMESTAMP,
        STATUS = COALESCE(:status, STATUS),
        ERROR_MESSAGE = COALESCE(:error_message, ERROR_MESSAGE),
        COMPLETED_AT = CASE WHEN :status IN ('COMPLETED', 'FAILED', 'PARTIAL', 'STOPPED', 'SUCCESS') THEN SYSTIMESTAMP ELSE COMPLETED_AT END
    WHERE JOB_ID = :job_id
    """
    with conn.cursor() as cur:
        cur.execute(sql_counts, {"job_id": job_id})
        row = cur.fetchone()
        if row:
            total = int(row[0] or 0)
            inserted = int(row[1] or 0)
            failed = int(row[2] or 0)
            skipped = int(row[3] or 0)
            inserted_skipped = int(row[4] or 0)
            invalid = int(row[5] or 0)
            errors = int(row[6] or 0)
            remaining = int(row[7] or 0)
            completed = max(total - remaining, 0)
            cur.execute(sql_update, {
                "completed": completed,
                "inserted": inserted,
                "remaining": remaining,
                "failed": failed,
                "skipped": skipped,
                "inserted_skipped": inserted_skipped,
                "invalid": invalid,
                "errors": errors,
                "status": status,
                "error_message": str(error_message or "")[:4000] if error_message else None,
                "job_id": job_id
            })
    conn.commit()


def _insert_skipped_rejected_symbol(
    conn,
    *,
    symbol: str,
    trading_date: dt.date | None,
    skip_reason: str,
    run_id: str | None = None,
    fyers_symbol: str | None = None,
    from_date: dt.date | None = None,
    to_date: dt.date | None = None,
    status: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    source_mode: str | None = None,
    rerun_status: str | None = None,
) -> bool:
    normalized_symbol = _normalize_failed_symbol_text(_normalize_fyers_display_symbol(symbol), 100)
    normalized_fyers_symbol = _normalize_failed_symbol_text(
        fyers_symbol or (
            _normalize_fyers_symbol(symbol) if symbol else ""
        ),
        100,
    )
    normalized_trading_date = _coerce_date_value(trading_date)
    normalized_from_date = _coerce_date_value(from_date) or normalized_trading_date
    normalized_to_date = _coerce_date_value(to_date) or normalized_trading_date
    normalized_status = _normalize_failed_symbol_status(status, skip_reason, error_code)
    normalized_source_mode = _normalize_failed_symbol_source_mode(source_mode)
    normalized_rerun_status = _normalize_failed_symbol_rerun_status(rerun_status)
    normalized_reason = _normalize_failed_symbol_text(skip_reason, 500)
    normalized_error_code = _normalize_failed_symbol_text(error_code, 120)
    normalized_error_message = _normalize_failed_symbol_text(error_message, 4000)
    normalized_run_id = _normalize_failed_symbol_text(run_id, 120)

    sql = """
MERGE INTO FYERS_API_SKIPED_REJECTED_SYMBOLS tgt
USING (
    SELECT
        :run_id AS RUN_ID,
        :symbol AS SYMBOL,
        :fyers_symbol AS FYERS_SYMBOL,
        :trading_date AS TRADING_DATE,
        :from_date AS FROM_DATE,
        :to_date AS TO_DATE,
        :status AS STATUS,
        :reason AS REASON,
        :error_code AS ERROR_CODE,
        :error_message AS ERROR_MESSAGE,
        :source_mode AS SOURCE_MODE,
        :rerun_status AS RERUN_STATUS
    FROM dual
) src
ON (
    NVL(tgt.SYMBOL, '~') = NVL(src.SYMBOL, '~')
    AND NVL(TRUNC(tgt.TRADING_DATE), DATE '1900-01-01') = NVL(TRUNC(src.TRADING_DATE), DATE '1900-01-01')
    AND NVL(TRUNC(tgt.FROM_DATE), DATE '1900-01-01') = NVL(TRUNC(src.FROM_DATE), DATE '1900-01-01')
    AND NVL(TRUNC(tgt.TO_DATE), DATE '1900-01-01') = NVL(TRUNC(src.TO_DATE), DATE '1900-01-01')
    AND NVL(tgt.STATUS, '~') = NVL(src.STATUS, '~')
    AND NVL(tgt.SOURCE_MODE, '~') = NVL(src.SOURCE_MODE, '~')
)
WHEN MATCHED THEN
    UPDATE SET
        tgt.RUN_ID = COALESCE(src.RUN_ID, tgt.RUN_ID),
        tgt.TRADING_DATE = COALESCE(src.TRADING_DATE, tgt.TRADING_DATE),
        tgt.FROM_DATE = COALESCE(src.FROM_DATE, tgt.FROM_DATE),
        tgt.TO_DATE = COALESCE(src.TO_DATE, tgt.TO_DATE),
        tgt.STATUS = COALESCE(src.STATUS, tgt.STATUS),
        tgt.FYERS_SYMBOL = COALESCE(src.FYERS_SYMBOL, tgt.FYERS_SYMBOL),
        tgt.REASON = COALESCE(src.REASON, tgt.REASON),
        tgt.ERROR_CODE = COALESCE(src.ERROR_CODE, tgt.ERROR_CODE),
        tgt.ERROR_MESSAGE = COALESCE(src.ERROR_MESSAGE, tgt.ERROR_MESSAGE),
        tgt.SOURCE_MODE = COALESCE(src.SOURCE_MODE, tgt.SOURCE_MODE),
        tgt.RERUN_STATUS = COALESCE(src.RERUN_STATUS, tgt.RERUN_STATUS),
        tgt.UPDATED_AT = SYSTIMESTAMP
WHEN NOT MATCHED THEN
    INSERT (
        RUN_ID,
        SYMBOL,
        FYERS_SYMBOL,
        TRADING_DATE,
        FROM_DATE,
        TO_DATE,
        STATUS,
        REASON,
        ERROR_CODE,
        ERROR_MESSAGE,
        SOURCE_MODE,
        RERUN_STATUS,
        RERUN_COUNT,
        CREATED_AT,
        UPDATED_AT
    )
    VALUES (
        src.RUN_ID,
        src.SYMBOL,
        src.FYERS_SYMBOL,
        src.TRADING_DATE,
        src.FROM_DATE,
        src.TO_DATE,
        src.STATUS,
        src.REASON,
        src.ERROR_CODE,
        src.ERROR_MESSAGE,
        src.SOURCE_MODE,
        src.RERUN_STATUS,
        0,
        SYSTIMESTAMP,
        SYSTIMESTAMP
    )
    """
    try:
        _ensure_fyers_failed_symbols_columns(conn)
        with conn.cursor() as cur:
            cur.execute(
                sql,
                {
                    "run_id": normalized_run_id,
                    "symbol": normalized_symbol,
                    "fyers_symbol": normalized_fyers_symbol,
                    "trading_date": normalized_trading_date,
                    "from_date": normalized_from_date,
                    "to_date": normalized_to_date,
                    "status": normalized_status,
                    "reason": normalized_reason,
                    "error_code": normalized_error_code,
                    "error_message": normalized_error_message,
                    "source_mode": normalized_source_mode,
                    "rerun_status": normalized_rerun_status,
                },
            )
        conn.commit()
        invalidate_fyers_failed_symbols_cache("skip_rejected_upsert")
        _logger.info(
            "[FYERS][SKIP_REJECTED][UPSERTED] symbol=%s fyers_symbol=%s trading_date=%s status=%s source_mode=%s reason=%s insert_status=success",
            normalized_symbol,
            normalized_fyers_symbol,
            normalized_trading_date.isoformat() if isinstance(normalized_trading_date, dt.date) else None,
            normalized_status,
            normalized_source_mode,
            normalized_reason,
        )
        return True
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        _logger.warning(
            "[FYERS][SKIP_REJECTED][FAILED] symbol=%s trading_date=%s status=%s source_mode=%s reason=%s insert_status=failed error=%s",
            normalized_symbol,
            normalized_trading_date.isoformat() if isinstance(normalized_trading_date, dt.date) else None,
            normalized_status,
            normalized_source_mode,
            normalized_reason,
            exc,
        )
        return False


def _extract_batch_failed_symbols(text: str) -> list[str]:
    symbols: list[str] = []
    seen: set[str] = set()
    for match in _BATCH_FAILED_SYMBOL_LINE_RE.finditer(str(text or "")):
        symbol = str(match.group(1) or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        symbols.append(symbol)
    return symbols


def _merge_failed_symbol(
    conn,
    *,
    input_symbol: str,
    normalized_symbol: str,
    status: str,
    error_code: str,
    error_message: str,
    start_date: dt.date,
    end_date: dt.date,
    retry_count: int,
) -> None:
    sql = """
MERGE INTO FYERS_REUSE_SYMBOLS tgt
USING (
    SELECT
        :input_symbol AS INPUT_SYMBOL,
        :normalized_symbol AS NORMALIZED_SYMBOL,
        :status AS STATUS,
        :error_code AS ERROR_CODE,
        :error_message AS ERROR_MESSAGE,
        :start_date AS START_DATE,
        :end_date AS END_DATE,
        :retry_count AS RETRY_COUNT
    FROM dual
) src
ON (
    tgt.NORMALIZED_SYMBOL = src.NORMALIZED_SYMBOL
    AND tgt.START_DATE = src.START_DATE
    AND tgt.END_DATE = src.END_DATE
    AND tgt.STATUS = src.STATUS
)
WHEN MATCHED THEN
    UPDATE SET
        tgt.ERROR_CODE = src.ERROR_CODE,
        tgt.ERROR_MESSAGE = src.ERROR_MESSAGE,
        tgt.RETRY_COUNT = src.RETRY_COUNT,
        tgt.RESOLUTION = '1D',
        tgt.UPDATED_AT = SYSTIMESTAMP
WHEN NOT MATCHED THEN
    INSERT (
        INPUT_SYMBOL,
        NORMALIZED_SYMBOL,
        STATUS,
        ERROR_CODE,
        ERROR_MESSAGE,
        START_DATE,
        END_DATE,
        RESOLUTION,
        RETRY_COUNT,
        SOURCE,
        CREATED_AT
    )
    VALUES (
        src.INPUT_SYMBOL,
        src.NORMALIZED_SYMBOL,
        src.STATUS,
        src.ERROR_CODE,
        src.ERROR_MESSAGE,
        src.START_DATE,
        src.END_DATE,
        '1D',
        src.RETRY_COUNT,
        :source,
        SYSTIMESTAMP
    )
    """
    with conn.cursor() as cur:
        cur.execute(
            sql,
            {
                "input_symbol": input_symbol,
                "normalized_symbol": normalized_symbol,
                "status": status,
                "error_code": error_code,
                "error_message": str(error_message or "")[:4000],
                "start_date": start_date,
                "end_date": end_date,
                "retry_count": max(0, int(retry_count or 0)),
                "source": FYERS_SOURCE,
            },
        )
    conn.commit()


def _merge_success_symbol_dates(
    conn,
    *,
    symbol: str,
    inserted_dates: set[dt.date],
    duplicate_dates: set[dt.date],
) -> None:
    sql = """
MERGE INTO FYERS_SUCCESS_SYMBOLS tgt
USING (
    SELECT
        :symbol AS SYMBOL,
        :trading_date AS TRADING_DATE,
        :inserted_rows AS INSERTED_ROWS,
        :duplicate_rows_skipped AS DUPLICATE_ROWS_SKIPPED
    FROM dual
) src
ON (
    tgt.SYMBOL = src.SYMBOL
    AND tgt.TRADING_DATE = src.TRADING_DATE
)
WHEN MATCHED THEN
    UPDATE SET
        tgt.INSERTED_ROWS = NVL(tgt.INSERTED_ROWS, 0) + src.INSERTED_ROWS,
        tgt.DUPLICATE_ROWS_SKIPPED = NVL(tgt.DUPLICATE_ROWS_SKIPPED, 0) + src.DUPLICATE_ROWS_SKIPPED,
        tgt.STATUS = 'SUCCESS',
        tgt.RESOLUTION = '1D',
        tgt.UPDATED_AT = SYSTIMESTAMP
WHEN NOT MATCHED THEN
    INSERT (
        SYMBOL,
        TRADING_DATE,
        RESOLUTION,
        INSERTED_ROWS,
        DUPLICATE_ROWS_SKIPPED,
        STATUS,
        SOURCE,
        CREATED_AT
    )
    VALUES (
        src.SYMBOL,
        src.TRADING_DATE,
        '1D',
        src.INSERTED_ROWS,
        src.DUPLICATE_ROWS_SKIPPED,
        'SUCCESS',
        :source,
        SYSTIMESTAMP
    )
    """
    bind_rows: list[dict[str, Any]] = []
    for trading_date in sorted(inserted_dates | duplicate_dates):
        bind_rows.append(
            {
                "symbol": symbol,
                "trading_date": trading_date,
                "inserted_rows": 1 if trading_date in inserted_dates else 0,
                "duplicate_rows_skipped": 1 if trading_date in duplicate_dates else 0,
                "source": FYERS_SOURCE,
            }
        )
    if not bind_rows:
        return
    with conn.cursor() as cur:
        cur.executemany(sql, bind_rows)
    conn.commit()


def _fetch_existing_symbol_dates(conn, symbol: str, trading_dates: list[dt.date]) -> set[dt.date]:
    if not trading_dates:
        return set()
    start_date = min(trading_dates)
    end_date = max(trading_dates)
    sql = """
SELECT TRADE_DATE
FROM STOCK_EOD_HISTORY
WHERE SYMBOL = normalize_symbol(:symbol)
  AND TRUNC(TRADE_DATE) BETWEEN TRUNC(:start_date) AND TRUNC(:end_date)
    """
    existing: set[dt.date] = set()
    with conn.cursor() as cur:
        cur.execute(
            sql,
            {
                "symbol": symbol,
                "start_date": start_date,
                "end_date": end_date,
            },
        )
        for row in cur:
            raw = row[0]
            if isinstance(raw, dt.datetime):
                existing.add(raw.date())
            elif isinstance(raw, dt.date):
                existing.add(raw)
    return existing


def _fetch_existing_symbol_dates_by_range(conn, symbol: str, start_date: dt.date, end_date: dt.date) -> set[dt.date]:
    sql = """
SELECT TRUNC(TRADE_DATE) AS TRADE_DATE
FROM STOCK_EOD_HISTORY
WHERE SYMBOL = normalize_symbol(:symbol)
  AND TRUNC(TRADE_DATE) BETWEEN TRUNC(:start_date) AND TRUNC(:end_date)
    """
    existing: set[dt.date] = set()
    with conn.cursor() as cur:
        cur.execute(
            sql,
            {
                "symbol": symbol,
                "start_date": start_date,
                "end_date": end_date,
            },
        )
        for row in cur:
            raw = row[0]
            if isinstance(raw, dt.datetime):
                existing.add(raw.date())
            elif isinstance(raw, dt.date):
                existing.add(raw)
    return existing


def _fetch_previously_failed_permanent_symbols(conn, trading_date: dt.date) -> set[str]:
    sql = """
    SELECT DISTINCT FYERS_SYMBOL
    FROM FYERS_API_SKIPED_REJECTED_SYMBOLS
    WHERE TRADING_DATE = :trading_date
      AND ERROR_CODE IN ('NO_DATA', 'INVALID_SYMBOL')
    """
    syms: set[str] = set()
    with conn.cursor() as cur:
        cur.execute(sql, {"trading_date": trading_date})
        for row in cur:
            if row[0]:
                syms.add(str(row[0]).strip().upper())
    return syms


def _fetch_actual_trading_dates(conn, start_date: dt.date, end_date: dt.date) -> set[dt.date]:
    sql = """
    SELECT DISTINCT TRUNC(TRADE_DATE) AS TRADE_DATE
    FROM STOCK_EOD_HISTORY
    WHERE TRUNC(TRADE_DATE) BETWEEN TRUNC(:start_date) AND TRUNC(:end_date)
    """
    dates: set[dt.date] = set()
    with conn.cursor() as cur:
        cur.execute(sql, {"start_date": start_date, "end_date": end_date})
        for row in cur:
            raw = row[0]
            if isinstance(raw, dt.datetime):
                dates.add(raw.date())
            elif isinstance(raw, dt.date):
                dates.add(raw)
    return dates


def _build_fyers_fetch_ranges(
    *,
    start_date: dt.date,
    end_date: dt.date,
    actual_trading_dates: set[dt.date],
    existing_dates: set[dt.date],
    force_refresh: bool,
) -> list[tuple[dt.date, dt.date]]:
    if force_refresh or not existing_dates or not actual_trading_dates:
        return [(start_date, end_date)]

    known_dates = sorted(
        value
        for value in actual_trading_dates
        if start_date <= value <= end_date
    )
    if not known_dates:
        return [(start_date, end_date)]

    ranges: list[tuple[dt.date, dt.date]] = []
    missing_run_start: dt.date | None = None
    missing_run_end: dt.date | None = None

    for trading_date in known_dates:
        if trading_date not in existing_dates:
            if missing_run_start is None:
                missing_run_start = trading_date
            missing_run_end = trading_date
        elif missing_run_start is not None and missing_run_end is not None:
            ranges.append((missing_run_start, missing_run_end))
            missing_run_start = None
            missing_run_end = None

    if missing_run_start is not None and missing_run_end is not None:
        ranges.append((missing_run_start, missing_run_end))

    latest_known_date = known_dates[-1]
    if latest_known_date < end_date:
        tail_start = latest_known_date + dt.timedelta(days=1)
        if ranges and ranges[-1][1] == latest_known_date:
            ranges[-1] = (ranges[-1][0], end_date)
        else:
            ranges.append((tail_start, end_date))

    return ranges


def _fyers_range_payload(start_date: dt.date, end_date: dt.date, error_message: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "from": start_date.isoformat(),
        "to": end_date.isoformat(),
    }
    if error_message:
        payload["error_message"] = error_message
    return payload


def _estimate_fyers_missing_days(ranges: list[tuple[dt.date, dt.date]]) -> int:
    return sum(max(0, (end_date - start_date).days + 1) for start_date, end_date in ranges)


def _fetch_fyers_ohlcv_for_missing_ranges(
    *,
    project_dir: Path,
    symbol: str,
    fetch_ranges: list[tuple[dt.date, dt.date]],
    resolution: str,
    line_logger: Optional[Callable[[str], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> dict[str, Any]:
    rows_by_date: dict[dt.date, tuple[Any, ...]] = {}
    failed_ranges: list[dict[str, Any]] = []
    api_records_count_total = 0
    fetch_chunk_count = 0
    rate_limit_retries = 0
    api_started_at = time.monotonic()

    for range_index, (fetch_start_date, fetch_end_date) in enumerate(fetch_ranges, start=1):
        _raise_if_fyers_stop_requested(should_stop)
        if line_logger:
            try:
                line_logger(
                    "[SINGLE_STOCK_SYNC] "
                    f"symbol={symbol} "
                    f"fetching_range={fetch_start_date.isoformat()}..{fetch_end_date.isoformat()} "
                    f"range_index={range_index}/{len(fetch_ranges)}"
                )
            except Exception:
                pass
        try:
            range_rows, range_record_count, fetch_meta = _direct_fetch_fyers_rows(
                project_dir=project_dir,
                symbol=symbol,
                start_date=fetch_start_date,
                end_date=fetch_end_date,
                resolution=resolution,
                should_stop=should_stop,
            )
            _raise_if_fyers_stop_requested(should_stop)
        except Exception as exc:
            error_message = str(exc)
            classified_status, _classified_code, _classified_message = _classify_symbol_failure(
                error_message,
                stage="fetch",
            )
            if (
                _is_fyers_auth_failure(error_message)
                or _contains_db_error_signature(error_message)
                or classified_status in _FYERS_EXPECTED_SYMBOL_SKIP_STATUSES
            ):
                raise
            failed_ranges.append(_fyers_range_payload(fetch_start_date, fetch_end_date, error_message))
            if line_logger:
                try:
                    line_logger(
                        "[SINGLE_STOCK_SYNC] "
                        f"symbol={symbol} "
                        f"failed_range={fetch_start_date.isoformat()}..{fetch_end_date.isoformat()} "
                        f"error={error_message}"
                    )
                except Exception:
                    pass
            _logger.warning(
                "[SINGLE_STOCK_SYNC] symbol=%s failed_range=%s..%s error=%s",
                symbol,
                fetch_start_date.isoformat(),
                fetch_end_date.isoformat(),
                error_message,
            )
            continue

        api_records_count_total += int(range_record_count or 0)
        fetch_chunk_count += _parse_int(fetch_meta.get("chunks"), 0)
        rate_limit_retries += _parse_int(fetch_meta.get("rate_limit_retries"), 0)
        for direct_row in range_rows:
            if len(direct_row) <= 1:
                continue
            trade_date = _coerce_fyers_trade_date(direct_row[1])
            if trade_date is not None:
                rows_by_date[trade_date] = direct_row
        if line_logger:
            try:
                line_logger(
                    "[SINGLE_STOCK_SYNC] "
                    f"symbol={symbol} "
                    f"fetched_rows={range_record_count} "
                    f"range={fetch_start_date.isoformat()}..{fetch_end_date.isoformat()}"
                )
            except Exception:
                pass

    return {
        "rows": list(rows_by_date.values()),
        "fetched_rows": api_records_count_total,
        "failed_ranges": failed_ranges,
        "meta": {
            "ranges": len(fetch_ranges),
            "chunks": fetch_chunk_count,
            "rate_limit_retries": rate_limit_retries,
            "api_time_seconds": round(time.monotonic() - api_started_at, 3),
        },
    }


def _default_output_prefix(symbol: str) -> str:
    clean = re.sub(r"[^A-Z0-9]+", "_", symbol.upper()).strip("_") or "FYERS"
    stamp = dt.datetime.now().strftime("%d%m%Y_%H%M%S")
    return f"{clean}_{stamp}"


def _count_error_lines(text: str) -> int:
    return sum(1 for line in str(text or "").splitlines() if re.search(r"\berror\b|\bfailed\b|exception", line, re.IGNORECASE))


def _parse_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _parse_optional_iso_date(value: object, field_name: str) -> dt.date | None:
    text = str(value or "").strip()
    if not text:
        return None
    return _parse_iso_date(text, field_name)


def _build_in_bind_clause(prefix: str, values: list[Any]) -> tuple[str, dict[str, Any]]:
    placeholders: list[str] = []
    binds: dict[str, Any] = {}
    for index, value in enumerate(values):
        bind_name = f"{prefix}_{index}"
        placeholders.append(f":{bind_name}")
        binds[bind_name] = value
    return ", ".join(placeholders), binds


def _build_fyers_failed_symbols_where_clause(params: dict[str, Any], *, alias: str = "t") -> tuple[str, dict[str, Any]]:
    conditions = ["1 = 1"]
    binds: dict[str, Any] = {}

    status = str(params.get("status") or "").strip().upper()
    if status:
        conditions.append(f"UPPER(COALESCE({alias}.STATUS, 'FAILED')) = :status")
        binds["status"] = status

    source_mode = str(params.get("source_mode") or params.get("sourceMode") or "").strip().upper()
    if source_mode:
        conditions.append(f"UPPER(COALESCE({alias}.SOURCE_MODE, 'CSV_BATCH')) = :source_mode")
        binds["source_mode"] = source_mode

    symbol_token = str(params.get("symbol") or "").strip().upper()
    if symbol_token:
        escaped = symbol_token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        binds["symbol_like"] = f"%{escaped}%"
        normalized_symbol_token = _normalize_fyers_display_symbol(symbol_token)
        normalized_escaped = normalized_symbol_token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        binds["symbol_key_like"] = f"%{normalized_escaped}%"
        symbol_key_expr = _fyers_failed_symbol_key_expr(f"NVL({alias}.SYMBOL, {alias}.FYERS_SYMBOL)")
        conditions.append(
            f"(UPPER(NVL({alias}.SYMBOL, '')) LIKE :symbol_like ESCAPE '\\' "
            f"OR UPPER(NVL({alias}.FYERS_SYMBOL, '')) LIKE :symbol_like ESCAPE '\\' "
            f"OR {symbol_key_expr} LIKE :symbol_key_like ESCAPE '\\')"
        )

    from_date = _parse_optional_iso_date(params.get("from_date") or params.get("fromDate"), "from_date")
    if from_date is not None:
        conditions.append(f"TRUNC(COALESCE({alias}.TRADING_DATE, {alias}.FROM_DATE, {alias}.TO_DATE)) >= :from_date")
        binds["from_date"] = from_date

    to_date = _parse_optional_iso_date(params.get("to_date") or params.get("toDate"), "to_date")
    if to_date is not None:
        conditions.append(f"TRUNC(COALESCE({alias}.TRADING_DATE, {alias}.TO_DATE, {alias}.FROM_DATE)) <= :to_date")
        binds["to_date"] = to_date

    return " AND ".join(conditions), binds


def _fyers_failed_symbol_key_expr(column_sql: str) -> str:
    return (
        "REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE("
        f"UPPER(TRIM({column_sql}))"
        ", 'NSE:', ''), 'BSE:', ''), ':EQ', ''), '-EQ', ''), ' ', ''), CHR(9), '')"
    )


def _fyers_failed_symbols_missing_cte(where_sql: str) -> str:
    uniform_symbol_key = _fyers_failed_symbol_key_expr("NVL(t.SYMBOL, t.FYERS_SYMBOL)")
    dev_symbol_key = _fyers_failed_symbol_key_expr("d.SYMBOL")
    uniform_trading_date = "TRUNC(COALESCE(t.TRADING_DATE, t.FROM_DATE, t.TO_DATE))"
    return f"""
WITH uniform_base AS (
    SELECT
        t.S_NO AS row_id,
        {uniform_symbol_key} AS symbol,
        t.FYERS_SYMBOL AS fyers_symbol,
        {uniform_trading_date} AS trading_date,
        TRUNC(COALESCE(t.FROM_DATE, t.TRADING_DATE, t.TO_DATE)) AS from_date,
        TRUNC(COALESCE(t.TO_DATE, t.TRADING_DATE, t.FROM_DATE)) AS to_date,
        UPPER(COALESCE(t.STATUS, 'FAILED')) AS status,
        t.REASON AS reason,
        t.ERROR_MESSAGE AS error_message,
        UPPER(COALESCE(t.RERUN_STATUS, 'PENDING')) AS rerun_status,
        t.LAST_RERUN_TS AS last_rerun_ts,
        t.CREATED_AT AS created_at,
        t.UPDATED_AT AS updated_at
    FROM {_FYERS_FAILED_SYMBOL_TABLE} t
    WHERE {where_sql}
      AND {uniform_symbol_key} IS NOT NULL
      AND {uniform_trading_date} IS NOT NULL
),
missing_only AS (
    SELECT ub.*
    FROM uniform_base ub
    WHERE NOT EXISTS (
        SELECT 1
        FROM {_MD_ORACLE_QUALIFIED} d
        WHERE d.SYMBOL IS NOT NULL
          AND d.TRADING_DATE >= ub.trading_date
          AND d.TRADING_DATE < ub.trading_date + 1
          AND {dev_symbol_key} = ub.symbol
    )
),
deduped AS (
    SELECT
        m.*,
        ROW_NUMBER() OVER (
            PARTITION BY m.symbol, m.trading_date
            ORDER BY COALESCE(m.updated_at, m.last_rerun_ts, m.created_at, CAST(m.trading_date AS TIMESTAMP)) DESC,
                     NVL(m.row_id, 0) DESC
        ) AS rn
    FROM missing_only m
),
symbol_failed_counts AS (
    SELECT
        symbol,
        COUNT(DISTINCT trading_date) AS td_count
    FROM deduped
    WHERE rn = 1
    GROUP BY symbol
),
monthly_dev_counts AS (
    SELECT
        month_key,
        MAX(symbol_month_td_count) AS month_max_td_count
    FROM (
        SELECT
            months.month_key AS month_key,
            {dev_symbol_key} AS symbol,
            COUNT(DISTINCT TRUNC(d.TRADING_DATE)) AS symbol_month_td_count
        FROM {_MD_ORACLE_QUALIFIED} d
        JOIN (
            SELECT DISTINCT TRUNC(trading_date, 'MM') AS month_key
            FROM deduped
            WHERE rn = 1
        ) months
          ON d.TRADING_DATE >= months.month_key
         AND d.TRADING_DATE < ADD_MONTHS(months.month_key, 1)
        WHERE d.SYMBOL IS NOT NULL
          AND d.TRADING_DATE IS NOT NULL
        GROUP BY
            months.month_key,
            {dev_symbol_key}
    )
    GROUP BY month_key
),
monthly_symbol_failed_counts AS (
    SELECT
        symbol,
        TRUNC(trading_date, 'MM') AS month_key,
        COUNT(DISTINCT trading_date) AS symbol_month_failed_td_count
    FROM deduped
    WHERE rn = 1
    GROUP BY
        symbol,
        TRUNC(trading_date, 'MM')
),
final_rows AS (
    SELECT
        d.row_id,
        d.symbol,
        d.fyers_symbol,
        d.trading_date,
        d.from_date,
        d.to_date,
        d.status,
        d.rerun_status,
        d.last_rerun_ts,
        d.created_at,
        d.updated_at,
        CASE
            WHEN d.reason IS NOT NULL AND d.error_message IS NOT NULL
                THEN d.reason || ' - ' || d.error_message
            WHEN d.reason IS NOT NULL
                THEN d.reason
            WHEN d.error_message IS NOT NULL
                THEN d.error_message
            ELSE '-'
        END AS reason_error_message,
        sfc.td_count,
        msfc.symbol_month_failed_td_count,
        mdc.month_max_td_count,
        CASE
            WHEN mdc.month_max_td_count IS NOT NULL
             AND msfc.symbol_month_failed_td_count >= mdc.month_max_td_count
                THEN 'FULL_MONTH_FAILED'
            WHEN mdc.month_max_td_count IS NOT NULL
             AND msfc.symbol_month_failed_td_count >= CEIL(mdc.month_max_td_count * 0.8)
                THEN 'HIGH_FAILED_DATES'
            WHEN msfc.symbol_month_failed_td_count > 20
                THEN 'HIGH_FAILED_DATES'
            ELSE 'NORMAL'
        END AS td_flag
    FROM deduped d
    LEFT JOIN symbol_failed_counts sfc
      ON sfc.symbol = d.symbol
    LEFT JOIN monthly_symbol_failed_counts msfc
      ON msfc.symbol = d.symbol
     AND msfc.month_key = TRUNC(d.trading_date, 'MM')
    LEFT JOIN monthly_dev_counts mdc
      ON mdc.month_key = TRUNC(d.trading_date, 'MM')
    WHERE d.rn = 1
)
"""


def _format_fyers_failed_symbol_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    formatted: list[dict[str, Any]] = []
    for row in rows:
        formatted.append(
            {
                "rowId": _parse_int(row.get("row_id"), 0),
                "symbol": str(row.get("symbol") or "").strip(),
                "tradingDate": str(row.get("trading_date") or "").strip(),
                "reasonErrorMessage": str(row.get("reason_error_message") or "-").strip() or "-",
                "tdCount": _parse_int(row.get("td_count"), 0),
                "symbolMonthFailedTdCount": _parse_int(row.get("symbol_month_failed_td_count"), 0),
                "monthMaxTdCount": _parse_int(row.get("month_max_td_count"), 0),
                "tdFlag": str(row.get("td_flag") or "NORMAL").strip().upper() or "NORMAL",
            }
        )
    return formatted


def _coerce_boolean(value: object) -> bool:
    if isinstance(value, bool):
        return value
    token = str(value or "").strip().lower()
    return token in {"1", "true", "yes", "y", "on"}


def _month_start(value: dt.date) -> dt.date:
    return dt.date(value.year, value.month, 1)


def _sort_timestamp(value: object) -> float:
    if isinstance(value, dt.datetime):
        return value.timestamp()
    if isinstance(value, dt.date):
        return float(value.toordinal())
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        parsed = _coerce_date_value(text)
        return float(parsed.toordinal()) if parsed else 0.0


def _build_oracle_date_windows(
    column_sql: str,
    dates: set[dt.date],
    prefix: str,
    *,
    month_windows: bool = False,
) -> tuple[str, dict[str, Any]]:
    parts: list[str] = []
    binds: dict[str, Any] = {}
    for index, date_value in enumerate(sorted(dates)):
        bind_name = f"{prefix}_{index}"
        if month_windows:
            parts.append(f"({column_sql} >= :{bind_name} AND {column_sql} < ADD_MONTHS(:{bind_name}, 1))")
        else:
            parts.append(f"({column_sql} >= :{bind_name} AND {column_sql} < :{bind_name} + 1)")
        binds[bind_name] = date_value
    return " OR ".join(parts), binds


def _query_fyers_failed_symbol_source_rows(conn, filters: dict[str, Any]) -> list[dict[str, Any]]:
    where_sql, where_binds = _build_fyers_failed_symbols_where_clause(filters)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
                t.S_NO AS row_id,
                NVL(t.SYMBOL, t.FYERS_SYMBOL) AS symbol,
                t.FYERS_SYMBOL AS fyers_symbol,
                t.TRADING_DATE AS trading_date,
                COALESCE(t.FROM_DATE, t.TRADING_DATE) AS from_date,
                COALESCE(t.TO_DATE, t.TRADING_DATE) AS to_date,
                UPPER(COALESCE(t.STATUS, 'FAILED')) AS status,
                t.REASON AS reason,
                t.ERROR_MESSAGE AS error_message,
                UPPER(COALESCE(t.RERUN_STATUS, 'PENDING')) AS rerun_status,
                t.LAST_RERUN_TS AS last_rerun_ts,
                t.CREATED_AT AS created_at,
                t.UPDATED_AT AS updated_at
            FROM {_FYERS_FAILED_SYMBOL_TABLE} t
            WHERE {where_sql}
            """,
            where_binds,
        )
        return fetchall_dict(cur)


def _fetch_dev_existing_symbol_dates(conn, trading_dates: set[dt.date]) -> set[tuple[str, dt.date]]:
    if not trading_dates:
        return set()
    date_sql, binds = _build_oracle_date_windows("d.TRADING_DATE", trading_dates, "dev_dt")
    symbol_expr = _fyers_failed_symbol_key_expr("d.SYMBOL")
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
                {symbol_expr} AS symbol,
                TRUNC(d.TRADING_DATE) AS trading_date
            FROM {_MD_ORACLE_QUALIFIED} d
            WHERE d.SYMBOL IS NOT NULL
              AND d.TRADING_DATE IS NOT NULL
              AND ({date_sql})
            GROUP BY
                {symbol_expr},
                TRUNC(d.TRADING_DATE)
            """,
            binds,
        )
        rows = fetchall_dict(cur)
    existing: set[tuple[str, dt.date]] = set()
    for row in rows:
        symbol = str(row.get("symbol") or "").strip().upper()
        trading_date = _coerce_date_value(row.get("trading_date"))
        if symbol and trading_date:
            existing.add((symbol, trading_date))
    return existing


def _fetch_monthly_dev_max_counts(conn, month_keys: set[dt.date]) -> dict[dt.date, int]:
    if not month_keys:
        return {}
    month_sql, binds = _build_oracle_date_windows("d.TRADING_DATE", month_keys, "dev_month", month_windows=True)
    symbol_expr = _fyers_failed_symbol_key_expr("d.SYMBOL")
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
                month_rows.month_key AS month_key,
                MAX(month_rows.symbol_month_td_count) AS month_max_td_count
            FROM (
                SELECT
                    TRUNC(d.TRADING_DATE, 'MM') AS month_key,
                    {symbol_expr} AS symbol,
                    COUNT(DISTINCT TRUNC(d.TRADING_DATE)) AS symbol_month_td_count
                FROM {_MD_ORACLE_QUALIFIED} d
                WHERE d.SYMBOL IS NOT NULL
                  AND d.TRADING_DATE IS NOT NULL
                  AND ({month_sql})
                GROUP BY
                    TRUNC(d.TRADING_DATE, 'MM'),
                    {symbol_expr}
            ) month_rows
            GROUP BY month_rows.month_key
            """,
            binds,
        )
        rows = fetchall_dict(cur)
    result: dict[dt.date, int] = {}
    for row in rows:
        month_key = _coerce_date_value(row.get("month_key"))
        if month_key:
            result[_month_start(month_key)] = _parse_int(row.get("month_max_td_count"), 0)
    return result


def _reason_error_message(reason: object, error_message: object) -> str:
    reason_text = str(reason or "").strip()
    error_text = str(error_message or "").strip()
    if reason_text and error_text:
        return f"{reason_text} - {error_text}"
    return reason_text or error_text or "-"


def _summary_for_fyers_failed_symbol_rows(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "totalFailed": sum(1 for row in rows if row.get("status") in {"FAILED", "AUTH_FAILED", "NO_DATA", "API_ERROR"}),
        "totalSkipped": sum(1 for row in rows if row.get("status") == "SKIPPED"),
        "totalRejected": sum(1 for row in rows if row.get("status") == "REJECTED"),
        "pendingRerun": sum(1 for row in rows if row.get("rerun_status") == "PENDING"),
        "rerunSuccess": sum(1 for row in rows if row.get("rerun_status") == "SUCCESS"),
        "rerunFailed": sum(1 for row in rows if row.get("rerun_status") == "FAILED"),
    }


def _build_fyers_failed_symbols_read_rows(
    conn,
    filters: dict[str, Any],
    *,
    missing_in_dev_only: bool = True,
) -> list[dict[str, Any]]:
    source_rows = _query_fyers_failed_symbol_source_rows(conn, filters)
    normalized_rows: list[dict[str, Any]] = []
    trading_dates: set[dt.date] = set()
    for row in source_rows:
        symbol = _normalize_fyers_display_symbol(row.get("symbol") or row.get("fyers_symbol"))
        trading_date = _coerce_date_value(row.get("trading_date") or row.get("from_date") or row.get("to_date"))
        if not symbol or trading_date is None:
            continue
        normalized = {
            **row,
            "symbol": symbol,
            "trading_date": trading_date,
            "from_date": _coerce_date_value(row.get("from_date")) or trading_date,
            "to_date": _coerce_date_value(row.get("to_date")) or trading_date,
            "status": str(row.get("status") or "FAILED").strip().upper() or "FAILED",
            "rerun_status": str(row.get("rerun_status") or "PENDING").strip().upper() or "PENDING",
            "reason_error_message": _reason_error_message(row.get("reason"), row.get("error_message")),
        }
        normalized_rows.append(normalized)
        trading_dates.add(trading_date)

    if missing_in_dev_only:
        existing_dev_pairs = _fetch_dev_existing_symbol_dates(conn, trading_dates)
        candidate_rows = [
            row for row in normalized_rows
            if (str(row.get("symbol") or "").strip().upper(), row["trading_date"]) not in existing_dev_pairs
        ]
    else:
        candidate_rows = normalized_rows

    deduped: dict[tuple[str, dt.date], dict[str, Any]] = {}
    for row in candidate_rows:
        key = (str(row.get("symbol") or "").strip().upper(), row["trading_date"])
        current = deduped.get(key)
        next_sort = (
            _sort_timestamp(row.get("updated_at"))
            or _sort_timestamp(row.get("last_rerun_ts"))
            or _sort_timestamp(row.get("created_at"))
            or _sort_timestamp(row.get("trading_date")),
            _parse_int(row.get("row_id"), 0),
        )
        current_sort = (
            _sort_timestamp(current.get("updated_at")) if current else 0.0,
            _parse_int(current.get("row_id"), 0) if current else 0,
        )
        if current is None or next_sort >= current_sort:
            deduped[key] = row

    rows = list(deduped.values())
    symbol_counts: dict[str, int] = {}
    symbol_month_counts: dict[tuple[str, dt.date], int] = {}
    month_keys: set[dt.date] = set()
    for row in rows:
        symbol = str(row.get("symbol") or "").strip().upper()
        trading_date = row["trading_date"]
        month_key = _month_start(trading_date)
        symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1
        symbol_month_key = (symbol, month_key)
        symbol_month_counts[symbol_month_key] = symbol_month_counts.get(symbol_month_key, 0) + 1
        month_keys.add(month_key)

    month_max_counts = _fetch_monthly_dev_max_counts(conn, month_keys)
    for row in rows:
        symbol = str(row.get("symbol") or "").strip().upper()
        month_key = _month_start(row["trading_date"])
        month_failed_count = symbol_month_counts.get((symbol, month_key), 0)
        month_max_count = month_max_counts.get(month_key, 0)
        if month_max_count and month_failed_count >= month_max_count:
            td_flag = "FULL_MONTH_FAILED"
        elif month_max_count and month_failed_count >= math.ceil(month_max_count * 0.8):
            td_flag = "HIGH_FAILED_DATES"
        elif month_failed_count > 20:
            td_flag = "HIGH_FAILED_DATES"
        else:
            td_flag = "NORMAL"
        row["td_count"] = symbol_counts.get(symbol, 0)
        row["symbol_month_failed_td_count"] = month_failed_count
        row["month_max_td_count"] = month_max_count
        row["td_flag"] = td_flag

    rows.sort(key=lambda item: (str(item.get("symbol") or ""), item.get("trading_date") or dt.date.min), reverse=False)
    rows.sort(key=lambda item: (str(item.get("symbol") or ""), -(item.get("trading_date") or dt.date.min).toordinal()))
    return rows


def _load_failed_symbol_rows_by_filters(conn, filters: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        _build_fyers_failed_symbols_read_rows(conn, filters, missing_in_dev_only=True),
        key=lambda row: _parse_int(row.get("row_id"), 0),
    )


def _list_repeating_failed_symbols_from_rows(rows: list[dict[str, Any]], *, limit: int = 100) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "").strip()
        if symbol:
            grouped.setdefault(symbol, []).append(row)
    repeating: list[dict[str, Any]] = []
    for symbol, rows in grouped.items():
        if len(rows) <= 1:
            continue
        failed_dates = sorted({
            (row.get("trading_date").isoformat() if isinstance(row.get("trading_date"), dt.date) else str(row.get("trading_date") or ""))
            for row in rows
            if row.get("trading_date")
        })
        repeating.append(
            {
                "symbol": symbol,
                "occurrences": len(rows),
                "from_date": failed_dates[0] if failed_dates else "",
                "to_date": failed_dates[-1] if failed_dates else "",
                "failed_dates": ", ".join(failed_dates),
            }
        )
    repeating.sort(key=lambda row: (-_parse_int(row.get("occurrences"), 0), str(row.get("symbol") or "")))
    return repeating[:max(1, min(500, int(limit)))]


def list_fyers_failed_symbols(params: dict[str, Any]) -> dict[str, Any]:
    limit = max(1, min(500, _parse_int(params.get("limit"), 25)))
    offset = max(0, _parse_int(params.get("offset"), 0))
    cache_key = _fyers_failed_symbols_cache_key(params, limit=limit, offset=offset)
    cached_payload = _get_cached_fyers_failed_symbols_payload(cache_key)
    if cached_payload is not None:
        return cached_payload

    started_at = time.perf_counter()

    with pool.acquire() as conn:
        _ensure_fyers_tracking_tables(conn)
        all_rows = _build_fyers_failed_symbols_read_rows(conn, params, missing_in_dev_only=False)
        page_rows = all_rows[offset:offset + limit]
        rows = _format_fyers_failed_symbol_rows(page_rows)
        repeating_symbols = _list_repeating_failed_symbols_from_rows(all_rows, limit=100)

    payload = {
        "ok": True,
        "rows": rows,
        "repeatingSymbols": repeating_symbols,
        "limit": limit,
        "offset": offset,
        "totalCount": len(all_rows),
        "summary": _summary_for_fyers_failed_symbol_rows(all_rows),
    }
    _store_fyers_failed_symbols_payload(cache_key, payload)
    _logger.info(
        "[FYERS][FAILED_SYMBOLS][DB_DISPLAY] rows=%s page_rows=%s offset=%s limit=%s duration_ms=%.1f",
        len(all_rows),
        len(rows),
        offset,
        limit,
        (time.perf_counter() - started_at) * 1000.0,
    )
    return payload


def _update_failed_symbol_rerun_rows(
    conn,
    row_ids: list[int],
    *,
    rerun_status: str,
    increment_count: bool = False,
) -> None:
    if not row_ids:
        return
    placeholders, placeholder_binds = _build_in_bind_clause("row_id", [int(row_id) for row_id in row_ids])
    update_sql = f"""
        UPDATE {_FYERS_FAILED_SYMBOL_TABLE}
        SET
            RERUN_STATUS = :rerun_status,
            LAST_RERUN_TS = SYSTIMESTAMP,
            UPDATED_AT = SYSTIMESTAMP,
            RERUN_COUNT = CASE
                WHEN :increment_count = 1 THEN NVL(RERUN_COUNT, 0) + 1
                ELSE NVL(RERUN_COUNT, 0)
            END
        WHERE S_NO IN ({placeholders})
    """
    with conn.cursor() as cur:
        cur.execute(
            update_sql,
            {
                "rerun_status": _normalize_failed_symbol_rerun_status(rerun_status),
                "increment_count": 1 if increment_count else 0,
                **placeholder_binds,
            },
        )
    invalidate_fyers_failed_symbols_cache("rerun_status_update")


def _update_failed_symbol_rerun_row_outcome(
    conn,
    *,
    row_id: int,
    rerun_status: str,
    status: str | None = None,
    reason: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    current_row_id = _parse_int(row_id, 0)
    if current_row_id <= 0:
        return
    normalized_reason = _normalize_failed_symbol_text(reason, 500)
    normalized_error_code = _normalize_failed_symbol_text(error_code, 120)
    normalized_error_message = _normalize_failed_symbol_text(error_message, 4000)
    normalized_status = _normalize_failed_symbol_status(status, normalized_reason, normalized_error_code)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE {_FYERS_FAILED_SYMBOL_TABLE}
            SET
                RERUN_STATUS = :rerun_status,
                STATUS = :status,
                REASON = :reason,
                ERROR_CODE = :error_code,
                ERROR_MESSAGE = :error_message,
                LAST_RERUN_TS = SYSTIMESTAMP,
                UPDATED_AT = SYSTIMESTAMP
            WHERE S_NO = :row_id
            """,
            {
                "rerun_status": _normalize_failed_symbol_rerun_status(rerun_status),
                "status": normalized_status,
                "reason": normalized_reason,
                "error_code": normalized_error_code,
                "error_message": normalized_error_message,
                "row_id": current_row_id,
            },
        )
    invalidate_fyers_failed_symbols_cache("rerun_row_outcome_update")


def _delete_failed_symbol_rows(conn, row_ids: list[int]) -> int:
    normalized_row_ids = sorted({_parse_int(item, 0) for item in row_ids if _parse_int(item, 0) > 0})
    if not normalized_row_ids:
        return 0
    placeholders, placeholder_binds = _build_in_bind_clause("delete_row_id", normalized_row_ids)
    with conn.cursor() as cur:
        cur.execute(
            f"DELETE FROM {_FYERS_FAILED_SYMBOL_TABLE} WHERE S_NO IN ({placeholders})",
            placeholder_binds,
        )
        invalidate_fyers_failed_symbols_cache("rerun_success_delete")
        return int(cur.rowcount or 0)


def _delete_failed_symbol_rows_by_locators(conn, locators: list[dict[str, Any]]) -> int:
    normalized_locators: list[tuple[str, dt.date]] = []
    seen: set[tuple[str, dt.date]] = set()
    for locator in locators:
        if not isinstance(locator, dict):
            continue
        symbol = _normalize_fyers_display_symbol(locator.get("symbol"))
        trading_date = _coerce_date_value(locator.get("tradingDate") or locator.get("trading_date"))
        if not symbol or trading_date is None:
            continue
        key = (symbol, trading_date)
        if key in seen:
            continue
        seen.add(key)
        normalized_locators.append(key)
    if not normalized_locators:
        return 0

    conditions: list[str] = []
    binds: dict[str, Any] = {}
    symbol_expr = _fyers_failed_symbol_key_expr("NVL(SYMBOL, FYERS_SYMBOL)")
    trading_date_expr = "TRUNC(COALESCE(TRADING_DATE, FROM_DATE, TO_DATE))"
    for index, (symbol, trading_date) in enumerate(normalized_locators):
        symbol_bind = f"delete_symbol_{index}"
        date_bind = f"delete_date_{index}"
        conditions.append(f"({symbol_expr} = :{symbol_bind} AND {trading_date_expr} = :{date_bind})")
        binds[symbol_bind] = symbol
        binds[date_bind] = trading_date

    where_clause = ' OR '.join(conditions)
    with conn.cursor() as cur:
        cur.execute(
            f"DELETE FROM {_FYERS_FAILED_SYMBOL_TABLE} WHERE {where_clause}",
            binds,
        )
        invalidate_fyers_failed_symbols_cache("manual_delete_locator")
        return int(cur.rowcount or 0)


def delete_fyers_failed_symbols(payload: dict[str, Any]) -> dict[str, Any]:
    raw_row_ids = payload.get("rowIds") or payload.get("row_ids") or []
    row_ids = sorted({
        _parse_int(item, 0)
        for item in (raw_row_ids if isinstance(raw_row_ids, list) else [])
        if _parse_int(item, 0) > 0
    })
    raw_locators = payload.get("rowLocators") or payload.get("row_locators") or []
    row_locators = raw_locators if isinstance(raw_locators, list) else []
    if not row_ids and not row_locators:
        raise ValueError("At least one valid failed-symbol row is required for delete.")

    with pool.acquire() as conn:
        _ensure_fyers_tracking_tables(conn)
        deleted_count = 0
        if row_ids:
            deleted_count += _delete_failed_symbol_rows(conn, row_ids)
        if row_locators:
            deleted_count += _delete_failed_symbol_rows_by_locators(conn, row_locators)
        conn.commit()

    return {
        "ok": True,
        "stage": "failed-symbol-delete",
        "message": (
            "Failed symbol deleted."
            if deleted_count == 1
            else f"{deleted_count} failed symbols deleted."
        ),
        "deletedCount": deleted_count,
        "request": {
            "rowIds": row_ids,
            "rowLocators": row_locators,
        },
    }


def _map_rerun_result_outcome(result_row: dict[str, Any]) -> dict[str, str]:
    status_token = str((result_row or {}).get("status") or "").strip().upper()
    message = str((result_row or {}).get("error_message") or "").strip()
    if status_token == "SUCCESS":
        return {
            "rerun_status": "SUCCESS",
            "status": "SUCCESS",
            "reason": "RERUN_SUCCESS",
            "error_code": "",
            "error_message": "",
        }
    if status_token in {"FAILED_NO_DATA", "FAILED_INVALID_SYMBOL"}:
        reason = status_token
        error_code = "NO_DATA" if status_token == "FAILED_NO_DATA" else "INVALID_SYMBOL"
        return {
            "rerun_status": "SKIPPED",
            "status": _normalize_failed_symbol_status(status_token, reason, error_code),
            "reason": reason,
            "error_code": error_code,
            "error_message": message or ("No candle data returned by FYERS" if error_code == "NO_DATA" else "FYERS rejected symbol"),
        }
    reason = status_token or "FAILED_API_ERROR"
    error_code = "API_ERROR"
    if reason == "FAILED_DB_ERROR":
        error_code = "DB_ERROR"
    elif reason == "FAILED_RATE_LIMIT":
        error_code = "RATE_LIMIT"
    elif reason == "FAILED_AUTH":
        error_code = "FYERS_AUTH_FAILED"
    return {
        "rerun_status": "FAILED",
        "status": _normalize_failed_symbol_status("FAILED", reason, error_code),
        "reason": reason,
        "error_code": error_code,
        "error_message": message or "Re-run failed while fetching/inserting symbol history.",
    }


def _load_failed_symbol_rows_for_rerun(
    conn,
    *,
    row_ids: list[int],
    symbols: list[str],
    from_date: dt.date | None,
    to_date: dt.date | None,
) -> list[dict[str, Any]]:
    conditions = ["1 = 1"]
    binds: dict[str, Any] = {}

    if row_ids:
        placeholders, placeholder_binds = _build_in_bind_clause("row_id", [int(item) for item in row_ids])
        conditions.append(f"t.S_NO IN ({placeholders})")
        binds.update(placeholder_binds)
    else:
        display_symbols = sorted({_normalize_fyers_display_symbol(item) for item in symbols if _normalize_fyers_display_symbol(item)})
        fyers_symbols = sorted({_normalize_fyers_symbol(item) for item in symbols if str(item or "").strip()})
        if display_symbols:
            symbol_placeholders, symbol_binds = _build_in_bind_clause("display_symbol", display_symbols)
            binds.update(symbol_binds)
        else:
            symbol_placeholders = ""
        if fyers_symbols:
            fyers_placeholders, fyers_binds = _build_in_bind_clause("fyers_symbol", fyers_symbols)
            binds.update(fyers_binds)
        else:
            fyers_placeholders = ""
        symbol_predicates: list[str] = []
        if symbol_placeholders:
            symbol_predicates.append(f"UPPER(NVL(t.SYMBOL, '')) IN ({symbol_placeholders})")
        if fyers_placeholders:
            symbol_predicates.append(f"UPPER(NVL(t.FYERS_SYMBOL, '')) IN ({fyers_placeholders})")
        if symbol_predicates:
            symbol_or_clause = ' OR '.join(symbol_predicates)
            conditions.append(f"({symbol_or_clause})")

    if from_date is not None:
        conditions.append("TRUNC(COALESCE(t.FROM_DATE, t.TRADING_DATE, t.TO_DATE)) >= :rerun_from_date")
        binds["rerun_from_date"] = from_date
    if to_date is not None:
        conditions.append("TRUNC(COALESCE(t.TO_DATE, t.TRADING_DATE, t.FROM_DATE)) <= :rerun_to_date")
        binds["rerun_to_date"] = to_date

    with conn.cursor() as cur:
        where_clause = ' AND '.join(conditions)
        cur.execute(
            f"""
            SELECT
                t.S_NO AS row_id,
                NVL(t.SYMBOL, t.FYERS_SYMBOL) AS symbol,
                t.FYERS_SYMBOL AS fyers_symbol,
                TO_CHAR(t.TRADING_DATE, 'YYYY-MM-DD') AS trading_date,
                TO_CHAR(COALESCE(t.FROM_DATE, t.TRADING_DATE), 'YYYY-MM-DD') AS from_date,
                TO_CHAR(COALESCE(t.TO_DATE, t.TRADING_DATE), 'YYYY-MM-DD') AS to_date,
                UPPER(COALESCE(t.STATUS, 'FAILED')) AS status,
                UPPER(COALESCE(t.RERUN_STATUS, 'PENDING')) AS rerun_status,
                NVL(t.RERUN_COUNT, 0) AS rerun_count
            FROM {_FYERS_FAILED_SYMBOL_TABLE} t
            WHERE {where_clause}
            ORDER BY NVL(t.S_NO, 0) ASC
            """,
            binds,
        )
        return fetchall_dict(cur)


def rerun_fyers_failed_symbols(
    payload: dict[str, Any],
    line_logger: Optional[Callable[[str], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> dict[str, Any]:
    def _log(message: str) -> None:
        if not line_logger:
            return
        try:
            line_logger(message)
        except Exception:
            return

    rerun_all = _coerce_boolean(payload.get("rerun_all") if "rerun_all" in payload else payload.get("rerunAll"))
    filter_payload = payload.get("filters")
    rerun_filters = filter_payload if isinstance(filter_payload, dict) else {}
    _log(
        f"[INFO] Failed-symbol rerun requested mode={'ALL_FILTERED' if rerun_all else 'SELECTED'} "
        f"payload_keys={sorted(payload.keys())}"
    )
    raw_symbols = payload.get("symbols")
    if isinstance(raw_symbols, list):
        symbols = [str(item or "").strip() for item in raw_symbols if str(item or "").strip()]
    else:
        symbols = [token.strip() for token in str(raw_symbols or "").split(",") if token.strip()]
    raw_row_ids = payload.get("rowIds") or payload.get("row_ids") or []
    row_ids = [
        _parse_int(item, 0)
        for item in (raw_row_ids if isinstance(raw_row_ids, list) else [])
        if _parse_int(item, 0) > 0
    ]
    if not rerun_all and not row_ids and not symbols:
        raise ValueError("At least one symbol is required for rerun.")

    from_date = _parse_optional_iso_date(payload.get("from_date") or payload.get("fromDate"), "from_date")
    to_date = _parse_optional_iso_date(payload.get("to_date") or payload.get("toDate"), "to_date")
    if from_date and to_date and to_date < from_date:
        raise ValueError("to_date cannot be earlier than from_date.")

    with pool.acquire() as conn:
        _ensure_fyers_tracking_tables(conn)
        if rerun_all:
            rows = _load_failed_symbol_rows_by_filters(conn, rerun_filters)
        else:
            rows = _load_failed_symbol_rows_for_rerun(
                conn,
                row_ids=row_ids,
                symbols=symbols,
                from_date=from_date,
                to_date=to_date,
            )

        if not rows:
            raise ValueError("No failed/skipped/rejected symbol rows found for rerun.")
        _log(f"[INFO] Failed-symbol rows selected for rerun: {len(rows)}")

        row_start_dates = [
            _coerce_date_value(row.get("from_date")) or _coerce_date_value(row.get("trading_date"))
            for row in rows
        ]
        row_end_dates = [
            _coerce_date_value(row.get("to_date")) or _coerce_date_value(row.get("trading_date"))
            for row in rows
        ]
        resolved_start = min([item for item in row_start_dates if isinstance(item, dt.date)], default=from_date)
        resolved_end = max([item for item in row_end_dates if isinstance(item, dt.date)], default=to_date)
        if resolved_start and resolved_end and not _date_range_has_weekday(resolved_start, resolved_end):
            raise ValueError("Weekend selected. Saturday and Sunday are market holidays.")

        if resolved_start and resolved_end:
            auth_failed, auth_run_result = _run_fyers_history_auth_probe(
                start_date=resolved_start,
                end_date=resolved_end,
                resolution=FYERS_FIXED_RESOLUTION,
                line_logger=line_logger,
            )
            if auth_failed:
                row_id_values = [int(row.get("row_id") or 0) for row in rows if _parse_int(row.get("row_id"), 0) > 0]
                _update_failed_symbol_rerun_rows(conn, row_id_values, rerun_status="FAILED", increment_count=True)
                conn.commit()
                _log("[ERROR] FYERS authentication failed while validating failed-symbol rerun.")
                return _build_fyers_auth_failure_payload(
                    "failed-symbol-rerun",
                    FYERS_AUTH_EXPIRED_UI_MESSAGE,
                    ui_message=FYERS_AUTH_EXPIRED_UI_MESSAGE,
                    run_result=auth_run_result,
                )

        rows_by_window: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in rows:
            row_start = str(row.get("from_date") or row.get("trading_date") or "").strip()
            row_end = str(row.get("to_date") or row.get("trading_date") or "").strip()
            fallback_start = resolved_start.isoformat() if isinstance(resolved_start, dt.date) else ""
            fallback_end = resolved_end.isoformat() if isinstance(resolved_end, dt.date) else ""
            key = (row_start or fallback_start, row_end or fallback_end)
            rows_by_window.setdefault(key, []).append(row)

        rerun_inserted = 0
        rerun_skipped = 0
        rerun_failed = 0
        processed_rows = 0
        updated_row_ids: list[int] = []
        batch_results: list[dict[str, Any]] = []
        deleted_success_rows = 0
        stop_requested = False
        window_items = list(rows_by_window.items())

        for window_index, ((group_start, group_end), group_rows) in enumerate(window_items, start=1):
            if should_stop and should_stop():
                stop_requested = True
                _log("[INFO] Stop request detected before starting next rerun window.")
                break
            group_row_ids = [int(row.get("row_id") or 0) for row in group_rows if _parse_int(row.get("row_id"), 0) > 0]
            _update_failed_symbol_rerun_rows(conn, group_row_ids, rerun_status="RUNNING", increment_count=True)
            conn.commit()

            group_symbols = sorted(
                {
                    _normalize_fyers_display_symbol(row.get("fyers_symbol") or row.get("symbol"))
                    for row in group_rows
                    if _normalize_fyers_display_symbol(row.get("fyers_symbol") or row.get("symbol"))
                }
            )
            _log(
                f"[INFO] Re-run window {window_index}/{len(window_items)} "
                f"start={group_start} end={group_end} symbols={len(group_symbols)} rows={len(group_rows)} "
                f"tracked_rows={len(group_row_ids)}"
            )
            result = fyers_run_single(
                {
                    "authorize": False,
                    "startDate": group_start,
                    "endDate": group_end,
                    "resolution": FYERS_FIXED_RESOLUTION,
                    "symbol": ",".join(group_symbols),
                    "sourceMode": "SINGLE_STOCK_RERUN",
                    "runId": f"rerun_{uuid.uuid4().hex[:12]}",
                },
                line_logger=line_logger,
                should_stop=should_stop,
            )
            batch_results.append(result)
            if bool(result.get("cancelled")):
                stop_requested = True
                _log("[INFO] Re-run window stopped safely after current symbol completed.")

            result_rows = result.get("results") if isinstance(result.get("results"), list) else []
            if not result_rows:
                next_status = "FAILED" if not result.get("ok") else "SKIPPED"
                fallback_reason = "FAILED_API_ERROR" if next_status == "FAILED" else "FAILED_NO_DATA"
                fallback_error_code = "API_ERROR" if next_status == "FAILED" else "NO_DATA"
                fallback_message = str(result.get("message") or "").strip() or (
                    "Re-run failed while processing the symbol window."
                    if next_status == "FAILED"
                    else "No candle data returned by FYERS."
                )
                for row_id in group_row_ids:
                    _update_failed_symbol_rerun_row_outcome(
                        conn,
                        row_id=row_id,
                        rerun_status=next_status,
                        status=next_status,
                        reason=fallback_reason,
                        error_code=fallback_error_code,
                        error_message=fallback_message,
                    )
                conn.commit()
                if next_status == "FAILED":
                    rerun_failed += len(group_rows)
                else:
                    rerun_skipped += len(group_rows)
                processed_rows += len(group_rows)
                updated_row_ids.extend(group_row_ids)
                _log(
                    f"[WARN] Re-run window {window_index}/{len(window_items)} returned no row-level results "
                    f"status={next_status} affected_rows={len(group_rows)} tracked_rows={len(group_row_ids)}"
                )
                continue

            rerun_result_by_symbol: dict[str, dict[str, str]] = {}
            for item in result_rows:
                result_status = str((item or {}).get("status") or "").strip().upper()
                symbol_key = _normalize_fyers_display_symbol(
                    (item or {}).get("normalized_symbol") or (item or {}).get("input_symbol")
                )
                if not symbol_key:
                    continue
                outcome = _map_rerun_result_outcome(item or {})
                rerun_result_by_symbol[symbol_key] = outcome
                if outcome.get("rerun_status") == "SUCCESS":
                    rerun_inserted += 1
                elif outcome.get("rerun_status") == "SKIPPED":
                    rerun_skipped += 1
                else:
                    rerun_failed += 1

            success_row_ids: list[int] = []
            for row in group_rows:
                current_row_id = _parse_int(row.get("row_id"), 0)
                if current_row_id <= 0:
                    continue
                current_symbol = _normalize_fyers_display_symbol(row.get("fyers_symbol") or row.get("symbol"))
                outcome = rerun_result_by_symbol.get(current_symbol) or {
                    "rerun_status": "FAILED",
                    "status": "FAILED",
                    "reason": "FAILED_API_ERROR",
                    "error_code": "API_ERROR",
                    "error_message": "Re-run result missing for symbol.",
                }
                rerun_status = str(outcome.get("rerun_status") or "FAILED").strip().upper()
                if rerun_status == "SUCCESS":
                    success_row_ids.append(current_row_id)
                else:
                    _update_failed_symbol_rerun_row_outcome(
                        conn,
                        row_id=current_row_id,
                        rerun_status=rerun_status,
                        status=outcome.get("status") or "FAILED",
                        reason=outcome.get("reason") or "FAILED_API_ERROR",
                        error_code=outcome.get("error_code") or "API_ERROR",
                        error_message=outcome.get("error_message") or "Re-run failed while processing symbol.",
                    )
                updated_row_ids.append(current_row_id)
            deleted_success_rows += _delete_failed_symbol_rows(conn, success_row_ids)
            conn.commit()
            processed_rows += len(group_rows)
            _log(
                f"[INFO] Re-run window {window_index}/{len(window_items)} complete "
                f"success_rows_deleted={len(success_row_ids)} processed_rows={len(group_rows)} "
                f"tracked_rows={len(group_row_ids)}"
            )

    rerun_summary = {
        "processed": processed_rows,
        "inserted": rerun_inserted,
        "skipped": rerun_skipped,
        "failed": rerun_failed,
        "deletedSuccessRows": deleted_success_rows,
        "cancelled": bool(stop_requested),
    }
    rerun_message = "Re-run completed."
    if stop_requested:
        rerun_message = "Re-run stopped safely after current symbol completed."
    elif rerun_failed and (rerun_inserted or rerun_skipped):
        rerun_message = "Re-run completed with partial success."
    elif rerun_failed:
        rerun_message = "Re-run failed."
    _log(
        f"[INFO] Re-run summary processed={rerun_summary['processed']} inserted={rerun_inserted} "
        f"skipped={rerun_skipped} failed={rerun_failed} deleted={deleted_success_rows} cancelled={stop_requested}"
    )

    return {
        "ok": rerun_failed == 0 and not stop_requested,
        "stage": "failed-symbol-rerun",
        "status": "CANCELLED" if stop_requested else ("FAILED" if rerun_failed > 0 else "SUCCESS"),
        "cancelled": bool(stop_requested),
        "message": rerun_message,
        "stats": rerun_summary,
        "details": {
            "row_ids": updated_row_ids,
            "results": batch_results,
            "deletedSuccessRows": deleted_success_rows,
            "rerunAll": rerun_all,
        },
        "request": {
            "symbols": symbols,
            "rowIds": row_ids,
            "fromDate": from_date.isoformat() if isinstance(from_date, dt.date) else None,
            "toDate": to_date.isoformat() if isinstance(to_date, dt.date) else None,
            "mode": str(payload.get("mode") or "SINGLE_STOCK_RERUN").strip() or "SINGLE_STOCK_RERUN",
            "rerunAll": rerun_all,
            "filters": rerun_filters if rerun_all else {},
        },
    }


def _resolve_summary_csv_path(project_dir: Path, raw_path: str | None) -> str | None:
    path_text = str(raw_path or "").strip()
    if not path_text:
        return None
    parsed = Path(path_text)
    candidate = parsed if parsed.is_absolute() else project_dir / parsed
    return str(candidate.resolve()) if candidate.exists() else str(candidate)


def _read_summary_totals(summary_csv_path: str | None) -> dict[str, int]:
    if not summary_csv_path:
        return {}
    path = Path(summary_csv_path)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if str(row.get("Symbol") or "").strip().upper() != "__TOTALS__":
                    continue
                return {
                    "inserted": _parse_int(row.get("Inserted"), 0),
                    "skipped": _parse_int(row.get("Skipped"), 0),
                    "invalid": _parse_int(row.get("Invalid"), 0),
                    "previously_skipped": _parse_int(row.get("Previously_Skipped"), 0),
                    "inserted_days": _parse_int(row.get("Inserted_Days"), 0),
                    "skipped_days": _parse_int(row.get("Skipped_Days"), 0),
                    "total_days": _parse_int(row.get("Total"), 0),
                }
    except Exception:
        return {}
    return {}


def _parse_skip_reason_counts(text: str) -> dict[str, int]:
    match = _BATCH_SKIP_REASONS_RE.search(text or "")
    if not match:
        return {}
    counts: dict[str, int] = {}
    for chunk in str(match.group(1) or "").split(","):
        token = chunk.strip()
        if not token or "=" not in token:
            continue
        key, value = token.split("=", 1)
        key = key.strip()
        if not key:
            continue
        counts[key] = _parse_int(value.strip(), 0)
    return counts


def _build_logs_payload(run_result: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "command": run_result.get("command") or [],
        "cwd": run_result.get("cwd") or "",
        "durationSeconds": run_result.get("duration_seconds"),
        "timedOut": bool(run_result.get("timed_out")),
        "stdoutTail": run_result.get("stdout_tail") or [],
        "stderrTail": run_result.get("stderr_tail") or [],
    }
    proxy_mode = str(run_result.get("proxy_policy") or "").strip()
    if proxy_mode:
        payload["proxyMode"] = proxy_mode
    proxy_map = run_result.get("proxy_env")
    if isinstance(proxy_map, dict) and proxy_map:
        payload["proxy"] = proxy_map
    return payload


def _build_fyers_failure(stage: str, message: str, run_result: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "stage": stage,
        "message": message,
        "stats": {
            "inserted": 0,
            "skipped": 0,
            "failed": 1,
            "errors": 1,
        },
    }
    if run_result is not None:
        payload["logs"] = _build_logs_payload(run_result)
    return payload


def _build_fyers_auth_failure_payload(
    stage: str,
    message: str,
    *,
    ui_message: str,
    run_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = _build_fyers_failure(stage, message, run_result=run_result)
    payload.update({
        "authStatus": "FAILED",
        "errorCode": "FYERS_AUTH_FAILED",
        "shouldRetry": False,
        "requiresAuthorization": True,
        "uiMessage": ui_message,
    })
    details = payload.get("details")
    if not isinstance(details, dict):
        details = {}
    details.update({
        "auth_failed": True,
        "error_code": "FYERS_AUTH_FAILED",
        "ui_message": ui_message,
    })
    payload["details"] = details
    return payload


def _build_fyers_auth_required_payload(
    *,
    status: str = "AUTH_REQUIRED",
    code: str = "FYERS_AUTH_REQUIRED",
    message: str = FYERS_AUTH_REQUIRED_MESSAGE,
    expires_at: object = None,
) -> dict[str, Any]:
    return {
        "ok": False,
        "stage": "authorize",
        "status": status,
        "code": code,
        "errorCode": code,
        "message": message,
        "authenticated": False,
        "canExtract": False,
        "requiresAuthorization": True,
        "shouldRetry": False,
        "expiresAt": expires_at,
    }


def _as_authorization_failure(
    payload: dict[str, Any],
    *,
    status: str,
    code: str,
    message: str,
) -> dict[str, Any]:
    payload.update({
        "status": status,
        "code": code,
        "errorCode": code,
        "message": message,
        "authenticated": False,
        "canExtract": False,
        "requiresAuthorization": True,
        "shouldRetry": False,
        "auth_url": None,
        "loginUrl": None,
    })
    stats = payload.get("stats")
    if isinstance(stats, dict):
        stats["failed"] = 0
        stats["errors"] = max(1, _parse_int(stats.get("errors"), 1))
    return payload


def _with_fyers_auth_success_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    payload["authStatus"] = "VALID"
    payload["errorCode"] = None
    payload["shouldRetry"] = False
    payload["requiresAuthorization"] = False
    return payload


def _utc_now_iso() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _local_now_iso() -> str:
    return dt.datetime.now(FYERS_IST).replace(microsecond=0).isoformat()


def _today_local_iso() -> str:
    return dt.datetime.now(FYERS_IST).date().isoformat()


def _parse_iso_datetime(value: object) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = dt.datetime.fromisoformat(candidate)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def _estimate_fyers_eta_datetime(
    *,
    started_at_ts: float,
    completed_symbols: int,
    total_symbols: int,
    now_ts: float | None = None,
) -> dt.datetime | None:
    if completed_symbols <= 0 or total_symbols <= completed_symbols:
        return None
    effective_now_ts = now_ts if now_ts is not None else time.time()
    elapsed_seconds = max(0.0, effective_now_ts - float(started_at_ts))
    if elapsed_seconds <= 0:
        return None
    avg_seconds_per_symbol = elapsed_seconds / max(1, completed_symbols)
    remaining_symbols = max(0, total_symbols - completed_symbols)
    if remaining_symbols <= 0:
        return None
    return dt.datetime.fromtimestamp(
        effective_now_ts + (avg_seconds_per_symbol * remaining_symbols),
        tz=dt.timezone.utc,
    ).replace(microsecond=0)


def _format_fyers_eta_display(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone().strftime("%d-%m-%Y %I:%M:%S %p %Z")


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    raw = str(token or "").strip()
    if not raw:
        return {}
    if ":" in raw and raw.count(".") < 2:
        raw = raw.split(":", 1)[1]
    parts = raw.split(".")
    if len(parts) < 2:
        return {}
    payload_segment = parts[1].strip()
    if not payload_segment:
        return {}
    padding = "=" * ((4 - (len(payload_segment) % 4)) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload_segment + padding)
        payload = json.loads(decoded.decode("utf-8", errors="ignore"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_fyers_token_metadata(project_dir: Path) -> dict[str, Any]:
    token_path = project_dir / "src" / "token.json"
    metadata: dict[str, Any] = {
        "tokenPath": str(token_path),
        "tokenExists": token_path.exists(),
        "expiryAvailable": False,
        "authenticated": False,
        "authExpired": False,
        "expiresAt": None,
        "expiresAtUtc": None,
        "expiresAtEpoch": None,
        "issuedAt": None,
        "issuedAtUtc": None,
    }
    if not token_path.exists():
        return metadata
    try:
        payload = json.loads(token_path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return metadata
    if not isinstance(payload, dict):
        return metadata
    token_text = str(payload.get("raw_access_token") or payload.get("access_token") or "").strip()
    claims = _decode_jwt_payload(token_text)
    exp_value = _parse_int(claims.get("exp"), 0)
    iat_value = _parse_int(claims.get("iat"), 0)
    metadata["tokenExists"] = bool(token_text)
    if iat_value > 0:
        issued_at_utc = dt.datetime.fromtimestamp(iat_value, tz=dt.timezone.utc).replace(microsecond=0)
        metadata["issuedAtUtc"] = issued_at_utc.isoformat().replace("+00:00", "Z")
        metadata["issuedAt"] = issued_at_utc.astimezone().replace(microsecond=0).isoformat()
    if exp_value <= 0:
        return metadata
    expires_at_utc = dt.datetime.fromtimestamp(exp_value, tz=dt.timezone.utc).replace(microsecond=0)
    expires_at_local = expires_at_utc.astimezone(FYERS_IST).replace(microsecond=0)
    now_utc = dt.datetime.now(dt.timezone.utc)
    metadata.update({
        "expiryAvailable": True,
        "authenticated": bool(token_text) and expires_at_utc > now_utc,
        "authExpired": expires_at_utc <= now_utc,
        "expiresAt": expires_at_local.isoformat(),
        "expiresAtUtc": expires_at_utc.isoformat().replace("+00:00", "Z"),
        "expiresAtEpoch": exp_value,
    })
    return metadata


def _coerce_datetime_value(value: object) -> dt.datetime | None:
    if isinstance(value, dt.datetime):
        return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)
    return _parse_iso_datetime(_fyers_json_value(value))


def _resolve_fyers_auth_valid_until_epoch(
    state: dict[str, Any] | None = None,
    token_metadata: dict[str, Any] | None = None,
) -> int:
    metadata = token_metadata or {}
    auth_state = state or {}
    token_expiry_epoch = _parse_int(metadata.get("expiresAtEpoch"), 0)
    state_valid_until_epoch = _parse_int(auth_state.get("valid_until_epoch"), 0)
    if token_expiry_epoch > 0:
        return token_expiry_epoch
    if state_valid_until_epoch > 0:
        return state_valid_until_epoch
    return 0


def _format_fyers_auth_expiry(expiry_value: object) -> str:
    parsed = _coerce_datetime_value(expiry_value)
    if parsed is None:
        return ""
    local = parsed.astimezone(FYERS_IST)
    return local.strftime("%d-%m-%Y %I:%M %p")


def _build_fyers_authenticated_message(expiry_value: object) -> str:
    expiry_display = _format_fyers_auth_expiry(expiry_value)
    if expiry_display:
        return f"FYERS access token already authenticated and valid until {expiry_display}."
    return "FYERS access token already authenticated and valid."


def _is_fyers_auth_state_valid(
    state: dict[str, Any] | None,
    *,
    token_metadata: dict[str, Any] | None = None,
) -> bool:
    auth_state = state or {}
    metadata = token_metadata or {}
    valid_until_epoch = _resolve_fyers_auth_valid_until_epoch(auth_state, metadata)
    if valid_until_epoch <= int(time.time()):
        return False
    if metadata:
        if not bool(metadata.get("tokenExists")):
            return False
        if bool(metadata.get("expiryAvailable")) and bool(metadata.get("authExpired")):
            return False
    return True


def _resolve_fyers_auth_status_cache_path() -> Path:
    candidate = Path(FYERS_AUTH_STATUS_CACHE_FILE).expanduser()
    if not candidate.is_absolute():
        candidate = _REPO_ROOT / candidate
    return candidate


def _normalize_cached_fyers_auth_status(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    today = _today_local_iso()
    last_auth_date = str(normalized.get("lastAuthorizedDate") or normalized.get("authDate") or "").strip()
    verified_at = str(
        normalized.get("verifiedAt")
        or normalized.get("verified_at")
        or normalized.get("lastAuthorizedAt")
        or ""
    ).strip()
    verified_at_utc = str(normalized.get("verifiedAtUtc") or normalized.get("verified_at_utc") or "").strip()
    expires_at = str(normalized.get("expiresAt") or normalized.get("expires_at") or "").strip()
    expires_at_utc = str(normalized.get("expiresAtUtc") or normalized.get("expires_at_utc") or "").strip()
    expires_at_epoch = _parse_int(
        normalized.get("expiresAtEpoch")
        or normalized.get("expires_at_epoch")
        or normalized.get("validUntilEpoch")
        or normalized.get("valid_until_epoch"),
        0,
    )
    now_epoch = int(dt.datetime.now(dt.timezone.utc).timestamp())
    expiry_available = expires_at_epoch > 0
    auth_expired = expiry_available and expires_at_epoch <= now_epoch
    remaining_validity_minutes = max(0, math.ceil((expires_at_epoch - now_epoch) / 60)) if expiry_available else 0
    normalized["today"] = today
    normalized["lastAuthorizedDate"] = last_auth_date or None
    authenticated_today = bool(last_auth_date) and last_auth_date == today
    normalized["authenticatedToday"] = authenticated_today
    normalized["expiryAvailable"] = expiry_available
    normalized["authExpired"] = auth_expired
    normalized["verifiedAt"] = verified_at or None
    normalized["verifiedAtUtc"] = verified_at_utc or None
    normalized["verified_at"] = verified_at or None
    normalized["verified_at_utc"] = verified_at_utc or None
    normalized["expiresAt"] = expires_at or (str(normalized.get("validUntil") or "").strip() or None)
    normalized["expiresAtUtc"] = expires_at_utc or (str(normalized.get("validUntilUtc") or "").strip() or None)
    normalized["expires_at"] = normalized.get("expiresAt")
    normalized["expires_at_utc"] = normalized.get("expiresAtUtc")
    normalized["expiresAtEpoch"] = expires_at_epoch or None
    normalized["expires_at_epoch"] = expires_at_epoch or None
    normalized["remainingValidityMinutes"] = remaining_validity_minutes
    normalized["remaining_validity_minutes"] = remaining_validity_minutes
    normalized["source"] = str(normalized.get("source") or normalized.get("statusSource") or "cache").strip() or "cache"
    normalized["statusSource"] = normalized["source"]

    is_authenticated = bool(
        normalized.get("tokenExists")
        and expiry_available
        and not auth_expired
    )
    normalized["authenticated"] = is_authenticated
    normalized["canExtract"] = is_authenticated

    invalidated_reason = str(normalized.get("invalidatedReason") or "").strip().upper()
    pending_expires_at = _parse_iso_datetime(normalized.get("pendingExpiresAt"))
    pending_active = bool(
        normalized.get("pendingStateHash")
        and pending_expires_at is not None
        and pending_expires_at > dt.datetime.now(dt.timezone.utc)
    )

    if is_authenticated:
        normalized["status"] = "AUTHENTICATED"
        normalized["message"] = _build_fyers_authenticated_message(normalized.get("expiresAt"))
    elif pending_active:
        normalized["status"] = "AUTHORIZING"
        normalized["message"] = "FYERS authorization is in progress. Complete the current login before starting extraction."
    elif invalidated_reason == "STALE_CALLBACK":
        normalized["status"] = "STALE_CALLBACK"
        normalized["message"] = FYERS_STALE_CALLBACK_MESSAGE
    elif invalidated_reason == "INVALID_REFRESH_TOKEN":
        normalized["status"] = "INVALID_REFRESH_TOKEN"
        normalized["message"] = FYERS_INVALID_REFRESH_MESSAGE
    else:
        normalized["status"] = "EXPIRED" if (auth_expired or bool(normalized.get("tokenExists"))) else "NOT_AUTHENTICATED"
        normalized["message"] = FYERS_AUTH_STATUS_EXPIRED_MESSAGE

    normalized["token_date"] = last_auth_date or today
    if not normalized.get("expires_at"):
        normalized["expires_at"] = f"{today}T23:59:59+05:30"

    return normalized


def _read_cached_fyers_auth_status() -> dict[str, Any] | None:
    path = _resolve_fyers_auth_status_cache_path()
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore").strip()
        if not raw:
            return None
        payload = json.loads(raw)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    normalized = _normalize_cached_fyers_auth_status(payload)
    if normalized.get("ok") is None:
        normalized["ok"] = True
    return normalized


def _write_cached_fyers_auth_status(payload: dict[str, Any]) -> None:
    path = _resolve_fyers_auth_status_cache_path()
    to_store = dict(_normalize_cached_fyers_auth_status(payload))
    to_store["cachedAtUtc"] = _utc_now_iso()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(to_store, ensure_ascii=True, indent=2), encoding="utf-8")
    except Exception:
        return


def _build_fyers_auth_status_payload(
    *,
    today: str,
    is_today: bool,
    state: dict[str, Any],
    token_metadata: dict[str, Any],
    message: str,
    source: str,
    degraded: bool = False,
) -> dict[str, Any]:
    resolved_expiry_epoch = _resolve_fyers_auth_valid_until_epoch(state, token_metadata)
    resolved_expiry_local = (
        token_metadata.get("expiresAt")
        or str(state.get("valid_until") or "").strip()
        or None
    )
    resolved_expiry_utc = (
        token_metadata.get("expiresAtUtc")
        or str(state.get("valid_until_utc") or "").strip()
        or None
    )
    payload = {
        "ok": True,
        "stage": "authorize",
        "today": today,
        "message": message,
        "source": source,
        "statusSource": source,
        "degraded": bool(degraded),
        "authenticatedToday": bool(is_today),
        "authenticated": bool(token_metadata.get("authenticated")),
        "canExtract": bool(token_metadata.get("authenticated")) and bool(is_today),
        "authExpired": bool(token_metadata.get("authExpired")),
        "lastAuthorizedDate": str(state.get("last_auth_date") or "").strip() or None,
        "lastAuthorizedAt": str(state.get("last_auth_at") or "").strip() or None,
        "verifiedAt": str(state.get("verified_at") or state.get("last_auth_at") or "").strip() or None,
        "verifiedAtUtc": str(state.get("verified_at_utc") or "").strip() or None,
        "invalidatedReason": str(state.get("invalidated_reason") or "").strip() or None,
        "pendingStateHash": str(state.get("pending_state_hash") or "").strip() or None,
        "pendingCreatedAt": str(state.get("pending_created_at") or "").strip() or None,
        "pendingExpiresAt": str(state.get("pending_expires_at") or "").strip() or None,
        "validUntil": str(state.get("valid_until") or "").strip() or None,
        "validUntilUtc": str(state.get("valid_until_utc") or "").strip() or None,
        "validUntilEpoch": _parse_int(state.get("valid_until_epoch"), 0) or None,
        "expiresAt": resolved_expiry_local,
        "expiresAtUtc": resolved_expiry_utc,
        "expiryAvailable": bool(token_metadata.get("expiryAvailable")) or resolved_expiry_epoch > 0,
        "expiresAtEpoch": resolved_expiry_epoch or None,
        "tokenExists": bool(token_metadata.get("tokenExists")),
        "tokenPath": token_metadata.get("tokenPath"),
        "issuedAt": token_metadata.get("issuedAt"),
        "issuedAtUtc": token_metadata.get("issuedAtUtc"),
    }
    return _normalize_cached_fyers_auth_status(payload)


def _build_fyers_auth_status_unavailable_payload(
    *,
    cached_payload: dict[str, Any] | None = None,
    error_message: str = "",
) -> dict[str, Any]:
    today = _today_local_iso()
    if cached_payload:
        payload = _normalize_cached_fyers_auth_status(cached_payload)
        payload["ok"] = True
        payload["source"] = "cache"
        payload["statusSource"] = "cache"
        payload["degraded"] = True
        if payload.get("authenticated") or str(payload.get("status") or "").upper() in {
            "AUTHORIZING",
            "INVALID_REFRESH_TOKEN",
            "STALE_CALLBACK",
        }:
            pass
        else:
            payload["message"] = FYERS_AUTH_STATUS_EXPIRED_MESSAGE
        if error_message:
            payload["details"] = {"warning": error_message}
            if not payload.get("authenticated"):
                payload["message"] = f"{payload['message']} Using last cached snapshot; {error_message}"
        return payload
    return {
        "ok": True,
        "stage": "authorize",
        "today": today,
        "message": FYERS_AUTH_STATUS_EXPIRED_MESSAGE,
        "source": "fallback",
        "statusSource": "fallback",
        "degraded": True,
        "authenticatedToday": False,
        "authenticated": False,
        "canExtract": False,
        "authExpired": False,
        "status": "NOT_AUTHENTICATED",
        "token_date": today,
        "expires_at": f"{today}T23:59:59+05:30",
        "lastAuthorizedDate": None,
        "lastAuthorizedAt": None,
        "expiresAt": None,
        "expiresAtUtc": None,
        "expiryAvailable": False,
        "expiresAtEpoch": None,
        "tokenExists": False,
        "tokenPath": None,
        "issuedAt": None,
        "issuedAtUtc": None,
        "details": {"warning": error_message} if error_message else {},
    }


def _fyers_auth_status_cache_is_fresh(payload: dict[str, Any] | None) -> bool:
    if not payload:
        return False
    normalized = _normalize_cached_fyers_auth_status(payload)
    if normalized.get("authenticated") is True and normalized.get("authExpired") is False:
        return True
    cached_at = _parse_iso_datetime(payload.get("cachedAtUtc"))
    if cached_at is None:
        return False
    age = (dt.datetime.now(dt.timezone.utc) - cached_at.astimezone(dt.timezone.utc)).total_seconds()
    return age <= FYERS_AUTH_STATUS_CACHE_TTL_SEC


def _refresh_fyers_auth_status_live() -> dict[str, Any]:
    project_dir = _resolve_fyers_project_dir()
    today = _today_local_iso()
    is_today, state = _is_fyers_authenticated_today(project_dir)
    token_metadata = _read_fyers_token_metadata(project_dir)
    if not is_today and str(state.get("invalidated_reason") or "").strip().upper() == "STALE_CALLBACK":
        recovered, recovered_state, recovered_metadata = _try_reconcile_fyers_auth_completion(
            project_dir,
            state=state,
            token_metadata=token_metadata,
        )
        if recovered:
            is_today = True
            state = recovered_state
            token_metadata = recovered_metadata
    payload = _build_fyers_auth_status_payload(
        today=today,
        is_today=is_today,
        state=state,
        token_metadata=token_metadata,
        message="Authorization status loaded.",
        source="live",
    )
    with _FYERS_AUTH_STATUS_CACHE_LOCK:
        _write_cached_fyers_auth_status(payload)
    return payload


def _start_fyers_auth_status_refresh() -> tuple[threading.Event, dict[str, Any]]:
    done = threading.Event()
    result: dict[str, Any] = {}

    def _worker() -> None:
        global _FYERS_AUTH_STATUS_REFRESH_ACTIVE
        try:
            result["payload"] = _refresh_fyers_auth_status_live()
        except Exception as exc:
            _logger.warning("[FYERS][AUTH_STATUS][REFRESH_SLOW_OR_FAILED] %s", exc)
            result["error"] = str(exc)
        finally:
            with _FYERS_AUTH_STATUS_REFRESH_LOCK:
                _FYERS_AUTH_STATUS_REFRESH_ACTIVE = False
            done.set()

    with _FYERS_AUTH_STATUS_REFRESH_LOCK:
        global _FYERS_AUTH_STATUS_REFRESH_ACTIVE
        if _FYERS_AUTH_STATUS_REFRESH_ACTIVE:
            result["error"] = "Live FYERS auth status refresh already in progress."
            done.set()
            return done, result
        _FYERS_AUTH_STATUS_REFRESH_ACTIVE = True
        threading.Thread(target=_worker, name="fyers-auth-status-refresh", daemon=True).start()
    return done, result


def _resolve_fyers_auth_state_path(project_dir: Path) -> Path:
    candidate = Path(FYERS_AUTH_STATE_FILE).expanduser()
    if not candidate.is_absolute():
        candidate = project_dir / candidate
    return candidate


def _read_fyers_auth_state(project_dir: Path) -> dict[str, Any]:
    path = _resolve_fyers_auth_state_path(project_dir)
    if not path.exists():
        return {}
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore").strip()
        if not raw:
            return {}
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _write_fyers_auth_state(project_dir: Path, payload: dict[str, Any]) -> None:
    path = _resolve_fyers_auth_state_path(project_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    except Exception:
        # Non-fatal: auth can still work without persisted cache.
        return


def _mark_fyers_auth_success(project_dir: Path) -> dict[str, Any]:
    global _IN_MEMORY_AUTH_STATUS, _IN_MEMORY_AUTH_STATUS_TS
    token_metadata = _read_fyers_token_metadata(project_dir)
    verified_at_utc_dt = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    verified_at_local_dt = verified_at_utc_dt.astimezone(FYERS_IST).replace(microsecond=0)
    expires_at_epoch = _parse_int(token_metadata.get("expiresAtEpoch"), 0)
    if expires_at_epoch > 0:
        valid_until_utc_dt = dt.datetime.fromtimestamp(expires_at_epoch, tz=dt.timezone.utc).replace(microsecond=0)
    else:
        valid_until_utc_dt = verified_at_utc_dt + dt.timedelta(seconds=FYERS_AUTH_VALIDITY_SEC)
    valid_until_local_dt = valid_until_utc_dt.astimezone(FYERS_IST).replace(microsecond=0)
    today = verified_at_local_dt.date().isoformat()
    state = {
        "last_auth_date": today,
        "last_auth_at": verified_at_local_dt.isoformat(),
        "verified_at": verified_at_local_dt.isoformat(),
        "verified_at_utc": verified_at_utc_dt.isoformat().replace("+00:00", "Z"),
        "valid_until": valid_until_local_dt.isoformat(),
        "valid_until_utc": valid_until_utc_dt.isoformat().replace("+00:00", "Z"),
        "valid_until_epoch": int(valid_until_utc_dt.timestamp()),
        "updated_at_utc": _utc_now_iso(),
    }
    with _FYERS_AUTH_STATE_LOCK:
        _write_fyers_auth_state(project_dir, state)
    _IN_MEMORY_AUTH_STATUS = None
    _IN_MEMORY_AUTH_STATUS_TS = 0.0
    return state


def _mark_fyers_auth_pending(project_dir: Path, state_value: str) -> dict[str, Any]:
    global _IN_MEMORY_AUTH_STATUS, _IN_MEMORY_AUTH_STATUS_TS
    created_at = dt.datetime.now(FYERS_IST).replace(microsecond=0)
    expires_at = created_at + dt.timedelta(seconds=FYERS_AUTH_STATE_TTL_SEC)
    state = {
        "last_auth_date": "",
        "last_auth_at": "",
        "verified_at": "",
        "verified_at_utc": "",
        "valid_until": "",
        "valid_until_utc": "",
        "valid_until_epoch": 0,
        "pending_state_hash": hashlib.sha256(state_value.encode("utf-8")).hexdigest(),
        "pending_created_at": created_at.isoformat(),
        "pending_expires_at": expires_at.isoformat(),
        "pending_used": False,
        "updated_at_utc": _utc_now_iso(),
    }
    with _FYERS_AUTH_STATE_LOCK:
        _write_fyers_auth_state(project_dir, state)
    _IN_MEMORY_AUTH_STATUS = None
    _IN_MEMORY_AUTH_STATUS_TS = 0.0
    _write_cached_fyers_auth_status(_build_fyers_auth_status_payload(
        today=_today_local_iso(),
        is_today=False,
        state=state,
        token_metadata=_read_fyers_token_metadata(project_dir),
        message="FYERS authorization is in progress.",
        source="authorize",
    ))
    return state


def _mark_fyers_auth_failure(project_dir: Path, reason: str = "fyers_auth_failure") -> dict[str, Any]:
    global _IN_MEMORY_AUTH_STATUS, _IN_MEMORY_AUTH_STATUS_TS
    state = {
        "last_auth_date": "",
        "last_auth_at": "",
        "verified_at": "",
        "verified_at_utc": "",
        "valid_until": "",
        "valid_until_utc": "",
        "valid_until_epoch": 0,
        "invalidated_at": _local_now_iso(),
        "invalidated_reason": str(reason or "fyers_auth_failure"),
        "updated_at_utc": _utc_now_iso(),
    }
    with _FYERS_AUTH_STATE_LOCK:
        _write_fyers_auth_state(project_dir, state)
    _IN_MEMORY_AUTH_STATUS = None
    _IN_MEMORY_AUTH_STATUS_TS = 0.0
    _write_cached_fyers_auth_status(_build_fyers_auth_status_payload(
        today=_today_local_iso(),
        is_today=False,
        state=state,
        token_metadata={
            "authenticated": False,
            "authExpired": True,
            "expiresAt": None,
            "expiresAtUtc": None,
            "expiryAvailable": False,
            "expiresAtEpoch": None,
            "tokenExists": False,
            "tokenPath": str(project_dir / "src" / "token.json"),
            "issuedAt": None,
            "issuedAtUtc": None,
        },
        message="FYERS authentication requires renewal.",
        source="failure",
        degraded=True,
    ))
    return state


def _try_reconcile_fyers_auth_completion(
    project_dir: Path,
    *,
    state: dict[str, Any],
    token_metadata: dict[str, Any] | None = None,
) -> tuple[bool, dict[str, Any], dict[str, Any]]:
    metadata = dict(token_metadata or _read_fyers_token_metadata(project_dir))
    token_valid = bool(
        metadata.get("tokenExists")
        and metadata.get("expiryAvailable")
        and metadata.get("authenticated")
        and not metadata.get("authExpired")
        and _parse_int(metadata.get("expiresAtEpoch"), 0) > int(time.time())
    )
    if not token_valid:
        return False, state, metadata

    issued_at = _parse_iso_datetime(metadata.get("issuedAtUtc") or metadata.get("issuedAt"))
    if issued_at is None:
        return False, state, metadata
    issued_utc = issued_at.astimezone(dt.timezone.utc)
    grace = dt.timedelta(seconds=FYERS_AUTH_COMPLETION_GRACE_SEC)
    pending_created_at = _parse_iso_datetime(state.get("pending_created_at"))
    pending_expires_at = _parse_iso_datetime(state.get("pending_expires_at"))
    invalidated_at = _parse_iso_datetime(state.get("invalidated_at"))
    issued_during_attempt = bool(
        pending_created_at
        and pending_expires_at
        and issued_utc >= pending_created_at.astimezone(dt.timezone.utc) - grace
        and issued_utc <= pending_expires_at.astimezone(dt.timezone.utc) + grace
    )
    issued_at_invalidation_boundary = bool(
        invalidated_at
        and abs((issued_utc - invalidated_at.astimezone(dt.timezone.utc)).total_seconds())
        <= FYERS_AUTH_COMPLETION_GRACE_SEC
    )
    if not issued_during_attempt and not issued_at_invalidation_boundary:
        return False, state, metadata

    profile_valid, _profile_details = _probe_fyers_profile_auth(project_dir)
    if not profile_valid:
        return False, state, metadata

    success_state = _mark_fyers_auth_success(project_dir)
    _write_cached_fyers_auth_status(_build_fyers_auth_status_payload(
        today=_today_local_iso(),
        is_today=True,
        state=success_state,
        token_metadata=metadata,
        message="FYERS access token updated.",
        source="authorize-reconciled",
    ))
    return True, success_state, metadata


def _resolve_fyers_cleanup_state_path(project_dir: Path) -> Path:
    candidate = Path(FYERS_CLEANUP_STATE_FILE).expanduser()
    if not candidate.is_absolute():
        candidate = project_dir / candidate
    return candidate


def _read_fyers_cleanup_state(project_dir: Path) -> dict[str, Any]:
    path = _resolve_fyers_cleanup_state_path(project_dir)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_fyers_cleanup_state(project_dir: Path, payload: dict[str, Any]) -> None:
    path = _resolve_fyers_cleanup_state_path(project_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    except Exception:
        return


def _is_allowed_cleanup_file(data_dir: Path, candidate: Path) -> bool:
    try:
        resolved_root = data_dir.resolve(strict=False)
        resolved_candidate = candidate.resolve(strict=False)
        resolved_candidate.relative_to(resolved_root)
    except Exception:
        return False
    if resolved_candidate.parent != resolved_root:
        return False
    if not resolved_candidate.is_file():
        return False
    return resolved_candidate.suffix.lower() in _FYERS_FAILED_SYMBOL_ALLOWED_EXTENSIONS


def cleanup_fyers_data_files(
    *,
    data_dir: str | Path | None = None,
    retention_days: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    project_dir = _resolve_fyers_project_dir()
    expected_dir = _resolve_fyers_data_dir(project_dir).resolve(strict=False)
    candidate_dir = Path(data_dir).expanduser() if data_dir else expected_dir
    resolved_dir = candidate_dir.resolve(strict=False)
    if resolved_dir != expected_dir:
        raise ValueError(f"Cleanup is restricted to {expected_dir}.")
    if not resolved_dir.exists():
        return {
            "ok": True,
            "deleted_count": 0,
            "skipped_count": 0,
            "dry_run": bool(dry_run),
            "path": str(resolved_dir),
            "retention_days": max(1, int(retention_days or FYERS_DATA_RETENTION_DAYS)),
            "deleted_files": [],
            "skipped_files": [],
        }
    if not resolved_dir.is_dir():
        raise ValueError(f"FYERS data directory is not a folder: {resolved_dir}")

    retention = max(1, int(retention_days or FYERS_DATA_RETENTION_DAYS))
    cutoff_ts = time.time() - (retention * 86400)
    deleted_files: list[str] = []
    skipped_files: list[str] = []
    deleted_count = 0
    skipped_count = 0

    for item in sorted(resolved_dir.iterdir(), key=lambda path: path.name.lower()):
        if not _is_allowed_cleanup_file(resolved_dir, item):
            skipped_count += 1
            skipped_files.append(item.name)
            continue
        try:
            modified_ts = item.stat().st_mtime
        except Exception:
            skipped_count += 1
            skipped_files.append(item.name)
            continue
        if modified_ts > cutoff_ts:
            skipped_count += 1
            skipped_files.append(item.name)
            continue
        if not dry_run:
            item.unlink(missing_ok=False)
        deleted_count += 1
        deleted_files.append(item.name)

    _logger.info(
        "[FYERS][DATA_CLEANUP] dry_run=%s retention_days=%s path=%s deleted_count=%s skipped_count=%s deleted_files=%s",
        bool(dry_run),
        retention,
        str(resolved_dir),
        deleted_count,
        skipped_count,
        deleted_files,
    )
    return {
        "ok": True,
        "deleted_count": deleted_count,
        "skipped_count": skipped_count,
        "dry_run": bool(dry_run),
        "path": str(resolved_dir),
        "retention_days": retention,
        "deleted_files": deleted_files,
        "skipped_files": skipped_files,
    }


def _run_fyers_data_cleanup_cycle(*, allow_bootstrap_only: bool) -> dict[str, Any]:
    project_dir = _resolve_fyers_project_dir()
    now_utc = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    with _FYERS_CLEANUP_STATE_LOCK:
        state = _read_fyers_cleanup_state(project_dir)
        last_run = _parse_iso_datetime(state.get("last_run_at"))
        if allow_bootstrap_only and not last_run:
            bootstrap_state = {
                "last_run_at": now_utc.isoformat().replace("+00:00", "Z"),
                "last_checked_at": now_utc.isoformat().replace("+00:00", "Z"),
                "bootstrap_only": True,
                "retention_days": FYERS_DATA_RETENTION_DAYS,
                "data_dir": str(_resolve_fyers_data_dir(project_dir)),
            }
            _write_fyers_cleanup_state(project_dir, bootstrap_state)
            _logger.info(
                "[FYERS][DATA_CLEANUP][BOOTSTRAP] path=%s retention_days=%s next_due_in_days=%s",
                bootstrap_state["data_dir"],
                FYERS_DATA_RETENTION_DAYS,
                FYERS_CLEANUP_INTERVAL_DAYS,
            )
            return {
                "ok": True,
                "bootstrapped": True,
                "message": "FYERS cleanup scheduler initialized. First automatic cleanup will run next week.",
            }

        due = last_run is None or (now_utc - last_run) >= dt.timedelta(days=FYERS_CLEANUP_INTERVAL_DAYS)
        if not due:
            state["last_checked_at"] = now_utc.isoformat().replace("+00:00", "Z")
            _write_fyers_cleanup_state(project_dir, state)
            return {
                "ok": True,
                "due": False,
                "message": "FYERS cleanup scheduler checked. Weekly cleanup is not due yet.",
            }

        result = cleanup_fyers_data_files(retention_days=FYERS_DATA_RETENTION_DAYS, dry_run=False)
        state.update({
            "last_run_at": now_utc.isoformat().replace("+00:00", "Z"),
            "last_checked_at": now_utc.isoformat().replace("+00:00", "Z"),
            "bootstrap_only": False,
            "retention_days": FYERS_DATA_RETENTION_DAYS,
            "data_dir": result.get("path"),
            "deleted_count": result.get("deleted_count"),
            "skipped_count": result.get("skipped_count"),
            "deleted_files": result.get("deleted_files"),
        })
        _write_fyers_cleanup_state(project_dir, state)
        return result


def start_fyers_data_cleanup_scheduler(*, initial_delay_seconds: int = 30) -> None:
    global _FYERS_CLEANUP_SCHEDULER_STARTED
    with _FYERS_CLEANUP_SCHEDULER_LOCK:
        if _FYERS_CLEANUP_SCHEDULER_STARTED:
            return
        _FYERS_CLEANUP_SCHEDULER_STARTED = True

    def _loop() -> None:
        if initial_delay_seconds > 0:
            time.sleep(initial_delay_seconds)
        while True:
            try:
                _run_fyers_data_cleanup_cycle(allow_bootstrap_only=True)
            except Exception as exc:
                _logger.warning("[FYERS][DATA_CLEANUP][SCHEDULER_ERROR] %s", exc)
            time.sleep(FYERS_CLEANUP_LOOP_SECONDS)

    threading.Thread(target=_loop, name="fyers-data-cleanup-scheduler", daemon=True).start()


def _run_fyers_history_auth_probe(
    *,
    start_date: dt.date,
    end_date: dt.date,
    resolution: str,
    line_logger: Optional[Callable[[str], None]] = None,
) -> tuple[bool, dict[str, Any]]:
    project_dir = _resolve_fyers_project_dir()
    probe_symbol = _normalize_fyers_symbol(FYERS_AUTH_PROBE_SYMBOL)
    started = time.monotonic()
    try:
        rows, fetched_count, _meta = _direct_fetch_fyers_rows(
            project_dir=project_dir,
            symbol=probe_symbol,
            start_date=start_date,
            end_date=end_date,
            resolution=resolution,
        )
        message = f"FYERS auth probe fetched {fetched_count} rows for {probe_symbol}; file_storage=disabled."
        if line_logger:
            try:
                line_logger(f"[INFO] {message}")
            except Exception:
                pass
        run_result = {
            "ok": True,
            "returncode": 0,
            "timed_out": False,
            "duration_seconds": round(time.monotonic() - started, 3),
            "stdout": message,
            "stderr": "",
            "stdout_tail": [message],
            "stderr_tail": [],
            "command": ["direct-fyers-auth-probe"],
            "cwd": str(project_dir),
            "rows": len(rows),
        }
        combined = message
    except Exception as exc:
        message = str(exc)
        if line_logger:
            try:
                line_logger(f"[stderr] {message}")
            except Exception:
                pass
        run_result = {
            "ok": False,
            "returncode": 1,
            "timed_out": False,
            "duration_seconds": round(time.monotonic() - started, 3),
            "stdout": "",
            "stderr": message,
            "stdout_tail": [],
            "stderr_tail": [message],
            "command": ["direct-fyers-auth-probe"],
            "cwd": str(project_dir),
        }
        combined = message
    return _is_fyers_auth_failure(combined), run_result


def _probe_fyers_profile_auth(project_dir: Path) -> tuple[bool, dict[str, Any]]:
    done = threading.Event()
    result: dict[str, Any] = {}

    def _worker() -> None:
        try:
            cfg = _load_fyers_direct_config(project_dir)
            _external_load_config, external_history_client, _external_db = _load_external_fyers_modules(project_dir)
            client = external_history_client(cfg.get("FYERS_ACCESS_TOKEN"), cfg.get("FYERS_APP_ID"))
            response = client.fyers.get_profile()
            if not isinstance(response, dict):
                result["details"] = {
                    "status": "error",
                    "code": None,
                    "message": "FYERS profile validation returned an invalid response.",
                    "authFailure": False,
                }
                return
            status = str(response.get("s") or response.get("status") or "").strip().lower()
            code = response.get("code")
            message = str(response.get("message") or "").strip()
            valid = status == "ok" and not _is_fyers_auth_failure(message)
            result["valid"] = valid
            result["details"] = {
                "status": status or ("ok" if valid else "error"),
                "code": code,
                "message": "FYERS profile validation succeeded." if valid else (message or "FYERS profile validation failed."),
                "authFailure": _is_fyers_auth_failure(f"{code} {message}"),
            }
        except Exception as exc:
            message = str(exc)
            result["details"] = {
                "status": "error",
                "code": None,
                "message": "FYERS profile validation failed.",
                "authFailure": _is_fyers_auth_failure(message),
            }
        finally:
            done.set()

    threading.Thread(target=_worker, name="fyers-auth-profile-probe", daemon=True).start()
    if not done.wait(FYERS_AUTH_PROBE_TIMEOUT_SEC):
        return False, {
            "status": "timeout",
            "code": None,
            "message": "FYERS profile validation timed out.",
            "authFailure": False,
        }
    details = result.get("details")
    return bool(result.get("valid")), details if isinstance(details, dict) else {
        "status": "error",
        "code": None,
        "message": "FYERS profile validation failed.",
        "authFailure": False,
    }


def ensure_valid_fyers_auth(*, profile_validated_at: object = None) -> dict[str, Any]:
    project_dir = _resolve_fyers_project_dir()
    token_metadata = _read_fyers_token_metadata(project_dir)
    state = _get_fyers_auth_state(project_dir)
    is_valid = _is_fyers_auth_state_valid(state, token_metadata=token_metadata)
    token_valid = bool(
        is_valid
        and token_metadata.get("tokenExists")
        and token_metadata.get("authenticated")
        and _resolve_fyers_auth_valid_until_epoch(state, token_metadata) > int(time.time())
    )
    if not token_valid:
        return _build_fyers_auth_required_payload(expires_at=token_metadata.get("expiresAt"))

    recently_validated = False
    try:
        validated_at = float(profile_validated_at or 0)
        recently_validated = (
            validated_at > 0
            and (time.time() - validated_at) <= FYERS_AUTH_PROFILE_VALIDATION_MAX_AGE_SEC
        )
    except (TypeError, ValueError):
        recently_validated = False

    if not recently_validated:
        profile_valid, profile_details = _probe_fyers_profile_auth(project_dir)
        if not profile_valid:
            if bool(profile_details.get("authFailure")):
                _mark_fyers_auth_failure(project_dir, "AUTH_REQUIRED")
            return _build_fyers_auth_required_payload(
                status="AUTH_VALIDATION_FAILED",
                code="FYERS_AUTH_VALIDATION_FAILED",
                message=FYERS_AUTH_VALIDATION_FAILED_MESSAGE,
                expires_at=token_metadata.get("expiresAt"),
            )

    return {
        "ok": True,
        "stage": "authorize",
        "status": "AUTHENTICATED",
        "message": _build_fyers_authenticated_message(token_metadata.get("expiresAt")),
        "authenticated": True,
        "canExtract": True,
        "requiresAuthorization": False,
        "shouldRetry": False,
        "expiresAt": token_metadata.get("expiresAt"),
        "expiresAtUtc": token_metadata.get("expiresAtUtc"),
        "verifiedAt": str(state.get("verified_at") or state.get("last_auth_at") or "").strip() or None,
        "remainingValidityMinutes": max(
            0,
            math.ceil((_resolve_fyers_auth_valid_until_epoch(state, token_metadata) - int(time.time())) / 60),
        ),
        "cached": True,
    }


def _get_fyers_auth_state(project_dir: Path) -> dict[str, Any]:
    with _FYERS_AUTH_STATE_LOCK:
        return _read_fyers_auth_state(project_dir)


def _is_fyers_authenticated_today(project_dir: Path) -> tuple[bool, dict[str, Any]]:
    state = _get_fyers_auth_state(project_dir)
    token_metadata = _read_fyers_token_metadata(project_dir)
    return (_is_fyers_auth_state_valid(state, token_metadata=token_metadata), state)


_IN_MEMORY_AUTH_STATUS: dict[str, Any] | None = None
_IN_MEMORY_AUTH_STATUS_TS: float = 0.0
_IN_MEMORY_AUTH_STATUS_TTL = 10.0


def fyers_auth_status() -> dict[str, Any]:
    global _IN_MEMORY_AUTH_STATUS, _IN_MEMORY_AUTH_STATUS_TS
    now = time.monotonic()
    if _IN_MEMORY_AUTH_STATUS is not None and (now - _IN_MEMORY_AUTH_STATUS_TS) <= _IN_MEMORY_AUTH_STATUS_TTL:
        return _IN_MEMORY_AUTH_STATUS

    cached_payload = _read_cached_fyers_auth_status()
    if _fyers_auth_status_cache_is_fresh(cached_payload):
        payload = cached_payload or _build_fyers_auth_status_unavailable_payload()
        _IN_MEMORY_AUTH_STATUS = payload
        _IN_MEMORY_AUTH_STATUS_TS = now
        return payload

    done, result = _start_fyers_auth_status_refresh()
    if done.wait(FYERS_AUTH_STATUS_FAST_WAIT_SEC):
        live_payload = result.get("payload")
        if isinstance(live_payload, dict):
            _IN_MEMORY_AUTH_STATUS = live_payload
            _IN_MEMORY_AUTH_STATUS_TS = now
            return live_payload
        fallback = _build_fyers_auth_status_unavailable_payload(
            cached_payload=cached_payload,
            error_message=str(result.get("error") or ""),
        )
        _IN_MEMORY_AUTH_STATUS = fallback
        _IN_MEMORY_AUTH_STATUS_TS = now
        return fallback

    fallback = _build_fyers_auth_status_unavailable_payload(
        cached_payload=cached_payload,
        error_message="Live FYERS auth status refresh exceeded the page-load budget.",
    )
    _IN_MEMORY_AUTH_STATUS = fallback
    _IN_MEMORY_AUTH_STATUS_TS = now
    return fallback


def _cleanup_fyers_jobs_locked(now_ts: float) -> None:
    job_metadata = {
        job_id: {
            "status": job.get("status"),
            "started_at": job.get("started_at"),
            "updated_at": job.get("updated_at"),
            "finished_at": job.get("finished_at"),
        }
        for job_id, job in _FYERS_JOBS.items()
        if float(job.get("finished_ts") or 0) > 0
    }
    removed = prune_finished_jobs(
        _FYERS_JOBS,
        now_ts=now_ts,
        ttl_seconds=FYERS_JOB_TTL_SEC,
        max_finished_items=FYERS_JOB_MAX_RETAINED,
    )
    for job_id, reason in removed:
        stale_job = job_metadata.get(job_id, {})
        if reason == "ttl_expired":
            _logger.info(
                "[FYERS][JOB_CLEANUP] job_id=%s status=%s created_at=%s updated_at=%s finished_at=%s reason=ttl_expired ttl_sec=%s registry_size=%s",
                job_id,
                stale_job.get("status"),
                stale_job.get("started_at"),
                stale_job.get("updated_at"),
                stale_job.get("finished_at"),
                max(60, FYERS_JOB_TTL_SEC),
                len(_FYERS_JOBS),
            )
        else:
            _logger.info(
                "[FYERS][JOB_CLEANUP] job_id=%s reason=retention_limit max_finished_jobs=%s registry_size=%s",
                job_id,
                FYERS_JOB_MAX_RETAINED,
                len(_FYERS_JOBS),
            )


def _append_job_log(job: dict[str, Any], line: str) -> None:
    text = str(line or "").rstrip()
    if not text:
        return
    if any(pattern.search(text) for pattern in _FYERS_UI_HIDDEN_LOG_PATTERNS):
        job["updated_at"] = _utc_now_iso()
        return
    logs = job.setdefault("logs", [])
    logs.append(text)
    if len(logs) > max(200, FYERS_JOB_MAX_LINES):
        trim_to = max(100, int(FYERS_JOB_MAX_LINES * 0.75))
        del logs[: max(0, len(logs) - trim_to)]
    login_match = _FYERS_LOGIN_URL_RE.search(text)
    if login_match and "fyers.in" in login_match.group(0).lower():
        job["login_url"] = login_match.group(0).strip()
    job["updated_at"] = _utc_now_iso()


def _update_fyers_job_progress_from_log(job: dict[str, Any], line: str) -> None:
    text = str(line or "").strip()
    if not text:
        return

    stats = job.setdefault("stats", {})
    if not isinstance(stats, dict):
        stats = {}
        job["stats"] = stats

    def record_first_completion(previous_completed: int) -> None:
        if previous_completed <= 0 and not job.get("first_completed_at"):
            job["first_completed_at"] = _utc_now_iso()

    coverage = _FYERS_SINGLE_SYNC_COVERAGE_RE.search(text)
    if coverage:
        symbol = str(coverage.group(1) or "").strip()
        stats["existing_rows"] = _parse_int(stats.get("existing_rows"), 0) + _parse_int(coverage.group(2), 0)
        stats["missing_ranges_count"] = _parse_int(stats.get("missing_ranges_count"), 0) + _parse_int(coverage.group(3), 0)
        stats["missing_estimated_days"] = _parse_int(stats.get("missing_estimated_days"), 0) + _parse_int(coverage.group(4), 0)
        stats["remaining_ranges"] = _parse_int(stats.get("missing_ranges_count"), 0)
        if symbol:
            job["currentSymbol"] = symbol
            job["current_symbol"] = symbol
            job["message"] = f"Checking DB coverage: {symbol}"
        job["updated_at"] = _utc_now_iso()
        return

    fetched = _FYERS_SINGLE_SYNC_FETCHED_RE.search(text)
    if fetched:
        symbol = str(fetched.group(1) or "").strip()
        stats["fetched_rows"] = _parse_int(stats.get("fetched_rows"), 0) + _parse_int(fetched.group(2), 0)
        if symbol:
            job["currentSymbol"] = symbol
            job["current_symbol"] = symbol
            job["message"] = f"Fetched missing FYERS rows: {symbol}"
        job["updated_at"] = _utc_now_iso()
        return

    db_merge = _FYERS_SINGLE_SYNC_DB_MERGE_RE.search(text)
    if db_merge:
        symbol = str(db_merge.group(1) or "").strip()
        stats["inserted_rows"] = _parse_int(stats.get("inserted_rows"), 0) + _parse_int(db_merge.group(2), 0)
        stats["updated_rows"] = _parse_int(stats.get("updated_rows"), 0) + _parse_int(db_merge.group(3), 0)
        stats["skipped_existing_rows"] = _parse_int(stats.get("skipped_existing_rows"), 0) + _parse_int(db_merge.group(4), 0)
        stats["failed_ranges_count"] = max(
            _parse_int(stats.get("failed_ranges_count"), 0),
            _parse_int(db_merge.group(5), 0),
        )
        stats["remaining_ranges"] = _parse_int(stats.get("failed_ranges_count"), 0)
        if symbol:
            job["currentSymbol"] = symbol
            job["current_symbol"] = symbol
            job["message"] = f"Merged FYERS rows: {symbol}"
        job["updated_at"] = _utc_now_iso()
        return

    failed_range = _FYERS_SINGLE_SYNC_FAILED_RANGE_RE.search(text)
    if failed_range:
        symbol = str(failed_range.group(1) or "").strip()
        stats["failed_ranges_count"] = _parse_int(stats.get("failed_ranges_count"), 0) + 1
        stats["remaining_ranges"] = _parse_int(stats.get("failed_ranges_count"), 0)
        if symbol:
            job["currentSymbol"] = symbol
            job["current_symbol"] = symbol
            job["message"] = f"FYERS range failed: {symbol}"
        job["updated_at"] = _utc_now_iso()
        return

    batch_started = _FYERS_DIRECT_BATCH_STARTED_RE.search(text)
    if batch_started:
        total = _parse_int(batch_started.group(1), 0)
        if total > 0:
            stats["total"] = max(_parse_int(stats.get("total"), 0), total)
            stats["nifty500_total"] = max(_parse_int(stats.get("nifty500_total"), 0), total)
            stats.setdefault("completed", 0)
            stats.setdefault("processed", 0)
            job["message"] = f"FYERS direct batch running. 0/{total} symbols processed."
        job["updated_at"] = _utc_now_iso()
        return

    processing = _FYERS_PROCESSING_SYMBOL_RE.search(text)
    if processing:
        processed = _parse_int(processing.group(1), 0)
        total = _parse_int(processing.group(2), 0)
        symbol = str(processing.group(3) or "").strip()
        if total > 0:
            stats["total"] = max(_parse_int(stats.get("total"), 0), total)
            stats["nifty500_total"] = max(_parse_int(stats.get("nifty500_total"), 0), total)
        if processed > 0:
            stats["processed"] = max(_parse_int(stats.get("processed"), 0), processed)
            stats["current_index"] = max(_parse_int(stats.get("current_index"), 0), processed)
            stats["completed"] = max(_parse_int(stats.get("completed"), 0), processed - 1)
        if symbol:
            job["currentSymbol"] = symbol
            job["current_symbol"] = symbol
            job["message"] = (
                f"Processing {stats.get('processed', processed)}/{stats.get('total', total)}: {symbol}"
            )
        job["updated_at"] = _utc_now_iso()
        return

    inserted = _FYERS_INSERTED_SYMBOL_RE.search(text)
    if inserted:
        previous_completed = _parse_int(stats.get("completed"), 0)
        inserted_rows = max(_parse_int(inserted.group(1), 0), 0)
        updated_rows = max(_parse_int(inserted.group(2), 0), 0)
        symbol = str(inserted.group(3) or "").strip()
        stats["inserted"] = _parse_int(stats.get("inserted"), 0) + 1
        stats["rows_loaded"] = _parse_int(stats.get("rows_loaded"), 0) + inserted_rows
        stats["inserted_rows"] = _parse_int(stats.get("inserted_rows"), 0) + inserted_rows
        stats["duplicate_rows_skipped"] = _parse_int(stats.get("duplicate_rows_skipped"), 0) + updated_rows
        stats["completed"] = max(
            previous_completed + 1,
            _parse_int(stats.get("current_index"), 0),
        )
        record_first_completion(previous_completed)
        stats.setdefault("skipped", 0)
        stats.setdefault("failed", 0)
        stats.setdefault("errors", 0)
        if symbol:
            job["currentSymbol"] = symbol
            job["current_symbol"] = symbol
            job["message"] = (
                f"Inserted {symbol}. {stats.get('processed', stats.get('inserted', 0))}/"
                f"{stats.get('total', 0)} symbols processed."
            )
        job["updated_at"] = _utc_now_iso()
        return

    failed = _FYERS_SYMBOL_FAILED_RE.search(text)
    if failed:
        previous_completed = _parse_int(stats.get("completed"), 0)
        symbol = str(failed.group(1) or "").strip()
        stats["failed"] = _parse_int(stats.get("failed"), 0) + 1
        stats["errors"] = _parse_int(stats.get("errors"), 0) + 1
        stats["completed"] = max(
            previous_completed + 1,
            _parse_int(stats.get("current_index"), 0),
        )
        record_first_completion(previous_completed)
        failed_list = job.setdefault("failed_symbols", [])
        if symbol and symbol not in failed_list:
            failed_list.append(symbol)
        if symbol:
            job["currentSymbol"] = symbol
            job["current_symbol"] = symbol
            job["message"] = f"FYERS symbol failed: {symbol}"
        job["updated_at"] = _utc_now_iso()
        return

    skipped = _FYERS_SYMBOL_SKIPPED_RE.search(text)
    if skipped:
        previous_completed = _parse_int(stats.get("completed"), 0)
        symbol = str(skipped.group(1) or "").strip()
        stats["skipped"] = _parse_int(stats.get("skipped"), 0) + 1
        stats["completed"] = max(
            previous_completed + 1,
            _parse_int(stats.get("current_index"), 0),
        )
        record_first_completion(previous_completed)
        skipped_list = job.setdefault("skipped_symbols", [])
        if symbol and symbol not in skipped_list:
            skipped_list.append(symbol)
        if symbol:
            job["currentSymbol"] = symbol
            job["current_symbol"] = symbol
            job["message"] = f"FYERS symbol skipped: {symbol}"
        job["updated_at"] = _utc_now_iso()


def _estimate_fyers_job_eta(job: dict[str, Any], *, now_ts: float | None = None) -> str | None:
    stats = job.get("stats")
    if not isinstance(stats, dict):
        return None
    completed_symbols = _parse_int(stats.get("completed"), 0)
    total_symbols = _parse_int(stats.get("total"), 0)
    started_at = _parse_iso_datetime(job.get("started_at"))
    if started_at is None:
        return None
    estimate_started_at = started_at
    estimate_completed_symbols = completed_symbols
    first_completed_at = _parse_iso_datetime(job.get("first_completed_at"))
    if first_completed_at is not None and completed_symbols > 1:
        estimate_started_at = first_completed_at
        estimate_completed_symbols = completed_symbols - 1
    eta_dt = _estimate_fyers_eta_datetime(
        started_at_ts=estimate_started_at.timestamp(),
        completed_symbols=estimate_completed_symbols,
        total_symbols=max(total_symbols - (completed_symbols - estimate_completed_symbols), 0),
        now_ts=now_ts,
    )
    if eta_dt is None:
        return None
    return eta_dt.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _build_fyers_job_timing_payload(job: dict[str, Any], *, now_ts: float | None = None) -> dict[str, Any]:
    stats = job.get("stats")
    if not isinstance(stats, dict):
        stats = {}
    started_at = job.get("started_at")
    updated_at = job.get("updated_at")
    finished_at = job.get("finished_at")
    started_dt = _parse_iso_datetime(started_at)
    end_dt = _parse_iso_datetime(finished_at or updated_at)
    elapsed_seconds = None
    if started_dt is not None and end_dt is not None:
        elapsed_seconds = max(0, int((end_dt - started_dt).total_seconds()))
    return {
        "startedAt": started_at,
        "updatedAt": updated_at,
        "finishedAt": finished_at,
        "lastHeartbeatAt": updated_at,
        "etaTimestamp": _estimate_fyers_job_eta(job, now_ts=now_ts),
        "completedSymbols": _parse_int(stats.get("completed"), 0),
        "totalSymbols": _parse_int(stats.get("total"), 0),
        "elapsedSeconds": elapsed_seconds,
    }


def _normalize_fyers_client_session_id(value: object) -> str:
    token = str(value or "").strip()
    if not token:
        return ""
    return token[:120]


def _job_should_stop(job_id: str) -> bool:
    with _FYERS_JOBS_LOCK:
        current = _FYERS_JOBS.get(job_id)
        if not current:
            return False
        return bool(current.get("stop_requested"))


def _normalize_fyers_job_tail(tail_lines: int | None = None) -> int:
    tail = tail_lines if tail_lines is not None else FYERS_JOB_DEFAULT_TAIL
    return max(20, min(int(tail), max(200, FYERS_JOB_MAX_LINES)))


def _format_fyers_summary_date(value: object = None) -> str:
    trade_date = _coerce_date_value(value) or _coerce_date_value(_today_local_iso()) or dt.date.today()
    return trade_date.strftime("%d-%m-%Y")


def _extract_fyers_terminal_failed_symbols(result: dict[str, Any] | None) -> list[str]:
    if not isinstance(result, dict):
        return []

    symbols: list[str] = []
    seen: set[str] = set()

    def _add_symbol(value: object) -> None:
        symbol = _normalize_fyers_display_symbol(value)
        if not symbol or symbol in seen:
            return
        seen.add(symbol)
        symbols.append(symbol)

    explicit = result.get("failedSymbols") or result.get("failed_symbols")
    if isinstance(explicit, str):
        for token in explicit.split(","):
            _add_symbol(token)
    elif isinstance(explicit, list):
        for item in explicit:
            _add_symbol(item)

    rows = result.get("results")
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            status = str(row.get("status") or "").strip().upper()
            if not status or status == "SUCCESS":
                continue
            _add_symbol(
                row.get("normalized_symbol")
                or row.get("fyers_symbol")
                or row.get("symbol")
                or row.get("input_symbol")
            )
    return symbols


def _build_fyers_terminal_summary_lines(result: dict[str, Any] | None) -> list[str]:
    if not isinstance(result, dict):
        return []
    stats = dict(result.get("stats") or {})
    request_payload = dict(result.get("request") or {})
    trade_date = _format_fyers_summary_date(
        request_payload.get("endDate")
        or request_payload.get("end_date")
        or result.get("endDate")
        or result.get("end_date")
    )
    symbols_total = _parse_int(stats.get("total"), _parse_int(result.get("total_symbols"), 0))
    inserted_total = _parse_int(stats.get("inserted"), _parse_int(result.get("success_count"), 0))
    skipped_total = _parse_int(stats.get("skipped"), _parse_int(result.get("skipped_count"), 0))
    failed_total = _parse_int(stats.get("failed"), _parse_int(result.get("failed_count"), 0))
    failed_symbols = ",".join(_extract_fyers_terminal_failed_symbols(result))
    return [
        f"<===>Summary Details Date:{trade_date}<====>",
        f"symbols={symbols_total} ->total",
        f"inserted={inserted_total} ->total",
        f"skipped={skipped_total} ->total",
        f"failed={failed_total} ->total",
        f"failed symbols=[{failed_symbols}]",
    ]


def _append_fyers_terminal_summary(job: dict[str, Any], result: dict[str, Any] | None) -> None:
    if job.get("_terminal_summary_appended"):
        return
    if str(job.get("stage") or "").strip().lower() == "authorize":
        return
    if isinstance(result, dict) and (
        result.get("canExtract") is False
        or result.get("requiresAuthorization") is True
        or str(result.get("status") or "").strip().upper() in {
            "AUTH_EXPIRED",
            "AUTH_REQUIRED",
            "AUTH_VALIDATION_FAILED",
            "INVALID_REFRESH_TOKEN",
            "STALE_CALLBACK",
        }
    ):
        return
    lines = _build_fyers_terminal_summary_lines(result)
    if not lines:
        return
    for line in lines:
        _append_job_log(job, line)
    job["_terminal_summary_appended"] = True


def _fyers_json_value(value: Any) -> Any:
    if isinstance(value, dt.datetime):
        normalized = value
        if normalized.tzinfo is None:
            normalized = normalized.replace(tzinfo=dt.timezone.utc)
        return normalized.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, dt.date):
        return value.isoformat()
    return value


def _build_fyers_symbol_payload(row: dict[str, Any], *, trading_date: Any = None) -> dict[str, Any]:
    raw_status = str(row.get("status") or "").strip().upper()
    reason = row.get("status_reason") or row.get("reason")
    error_message = row.get("error_message") or row.get("last_error")
    canonical_status = _canonical_fyers_symbol_status(raw_status, reason, error_message)
    retry_count = max(
        _parse_int(row.get("retry_count"), _parse_int(row.get("attempt_count"), 0)),
        0,
    )
    symbol = str(row.get("symbol") or "").strip()
    trade_date = _fyers_json_value(row.get("trading_date") or trading_date)
    reason_text = str(reason or error_message or "").strip()
    error_text = str(error_message or "").strip()
    return {
        "Symbol": symbol,
        "Status": canonical_status,
        "Reason": reason_text,
        "Trading Date": trade_date,
        "Retry Count": retry_count,
        "Last Error": error_text,
        "symbol": symbol,
        "status": canonical_status,
        "rawStatus": raw_status,
        "reason": reason_text,
        "tradingDate": trade_date,
        "retryCount": retry_count,
        "lastError": error_text,
    }


def _build_fyers_persisted_job_payload(
    run: dict[str, Any],
    symbol_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    job_id = str(run.get("job_id") or run.get("jobId") or "").strip()
    trading_date = _fyers_json_value(run.get("trading_date") or run.get("tradingDate"))
    symbols = [
        _build_fyers_symbol_payload(row, trading_date=trading_date)
        for row in symbol_rows
    ]
    status_counts: dict[str, int] = {}
    for row in symbols:
        token = str(row.get("Status") or "PENDING")
        status_counts[token] = status_counts.get(token, 0) + 1

    total = max(
        _parse_int(run.get("total_symbols"), _parse_int(run.get("total"), len(symbols))),
        len(symbols),
    )
    inserted = status_counts.get("INSERTED", 0)
    skipped = (
        status_counts.get("SKIPPED_ALREADY_INSERTED", 0)
        + status_counts.get("SKIPPED_AFTER_INSERTED", 0)
    )
    inserted_skipped = skipped
    failed = status_counts.get("FAILED", 0)
    invalid = status_counts.get("INVALID", 0)
    errors = status_counts.get("ERROR", 0)
    remaining = max(total - inserted - skipped - failed - invalid - errors, 0)
    persisted_status = str(run.get("status") or "RUNNING").strip().upper() or "RUNNING"
    done = persisted_status in _FYERS_PERSISTED_TERMINAL_JOB_STATUSES
    stop_requested = str(run.get("requested_stop_flag") or "N").strip().upper() in {"Y", "1", "TRUE"}
    message = str(run.get("error_message") or "").strip()
    if not message:
        message = "FYERS extraction recovered from persisted Oracle job state."
    stats = {
        "total": total,
        "tradingDate": trading_date,
        "inserted": inserted,
        "remaining": remaining,
        "failed": failed,
        "skipped": skipped,
        "insertedSkipped": inserted_skipped,
        "invalid": invalid,
        "errors": errors,
    }
    return {
        "ok": persisted_status not in {"FAILED"},
        "jobId": job_id,
        "job_id": job_id,
        "runId": job_id,
        "run_id": job_id,
        "stage": str(run.get("job_type") or run.get("stage") or "batch").strip().lower(),
        "status": persisted_status,
        "done": done,
        "message": message,
        "tradingDate": trading_date,
        "trading_date": trading_date,
        "startedAt": _fyers_json_value(run.get("started_at")),
        "updatedAt": _fyers_json_value(run.get("updated_at")),
        "finishedAt": _fyers_json_value(run.get("completed_at")),
        "stopRequested": stop_requested,
        "stopRequestedAt": None,
        "stats": stats,
        "counts": dict(stats),
        "symbols": symbols,
        "logs": {"tail": [], "totalLines": 0},
        "persisted": True,
    }


def _load_fyers_symbol_rows(
    job_id: str,
    statuses: set[str] | tuple[str, ...] | list[str] | None = None,
    limit: int = 2000,
) -> list[dict[str, Any]]:
    jid = str(job_id or "").strip()
    if not jid:
        raise ValueError("jobId is required.")
    bounded_limit = max(1, min(int(limit or 2000), 5000))
    sql = """
    SELECT JOB_ID, TRADING_DATE, SYMBOL, STATUS, STATUS_REASON,
           RETRY_COUNT, ATTEMPT_COUNT, ERROR_MESSAGE, STARTED_AT,
           UPDATED_AT, COMPLETED_AT
    FROM FYERS_EXTRACTION_SYMBOL_STATUS
    WHERE JOB_ID = :job_id
      AND ROWNUM <= :row_limit
    ORDER BY SYMBOL
    """
    legacy_sql = """
    SELECT JOB_ID, TRADING_DATE, SYMBOL, STATUS, NULL AS STATUS_REASON,
           ATTEMPT_COUNT AS RETRY_COUNT, ATTEMPT_COUNT, ERROR_MESSAGE,
           STARTED_AT, UPDATED_AT, COMPLETED_AT
    FROM FYERS_EXTRACTION_SYMBOL_STATUS
    WHERE JOB_ID = :job_id
      AND ROWNUM <= :row_limit
    ORDER BY SYMBOL
    """
    with pool.acquire() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(sql, {"job_id": jid, "row_limit": bounded_limit})
            except Exception:
                cur.execute(legacy_sql, {"job_id": jid, "row_limit": bounded_limit})
            columns = [str(item[0]).strip().lower() for item in cur.description]
            rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    if not statuses:
        return rows
    allowed = {str(item or "").strip().upper() for item in statuses if str(item or "").strip()}
    return [
        row for row in rows
        if _canonical_fyers_symbol_status(
            row.get("status"),
            row.get("status_reason"),
            row.get("error_message"),
        ) in allowed
    ]


def _load_fyers_job_snapshot(
    job_id: str,
    include_symbols: bool = True,
) -> dict[str, Any] | None:
    jid = str(job_id or "").strip()
    if not jid:
        raise ValueError("jobId is required.")
    sql = """
    SELECT JOB_ID, JOB_TYPE, TRADING_DATE, STATUS, TOTAL_SYMBOLS,
           INSERTED_COUNT, REMAINING_COUNT, FAILED_COUNT, SKIPPED_COUNT,
           INSERTED_SKIPPED_COUNT, INVALID_COUNT, ERROR_COUNT,
           STARTED_AT, UPDATED_AT, COMPLETED_AT, REQUESTED_STOP_FLAG,
           ERROR_MESSAGE
    FROM FYERS_EXTRACTION_RUNS
    WHERE JOB_ID = :job_id
    """
    legacy_sql = """
    SELECT JOB_ID, 'batch' AS JOB_TYPE, TRADING_DATE, STATUS, TOTAL_SYMBOLS,
           COMPLETED_COUNT AS INSERTED_COUNT, NULL AS REMAINING_COUNT,
           FAILED_COUNT, SKIPPED_COUNT, SKIPPED_COUNT AS INSERTED_SKIPPED_COUNT,
           0 AS INVALID_COUNT, 0 AS ERROR_COUNT, STARTED_AT, UPDATED_AT,
           COMPLETED_AT, 'N' AS REQUESTED_STOP_FLAG, ERROR_MESSAGE
    FROM FYERS_EXTRACTION_RUNS
    WHERE JOB_ID = :job_id
    """
    try:
        _cleanup_stale_persisted_fyers_jobs()
        with pool.acquire() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(sql, {"job_id": jid})
                except Exception:
                    cur.execute(legacy_sql, {"job_id": jid})
                row = cur.fetchone()
                if not row:
                    return None
                columns = [str(item[0]).strip().lower() for item in cur.description]
                run = dict(zip(columns, row))
        symbol_rows = _load_fyers_symbol_rows(jid, limit=2000) if include_symbols else []
        return _build_fyers_persisted_job_payload(run, symbol_rows)
    except Exception as exc:
        _logger.warning("[FYERS][PERSISTED_JOB_READ_FAILED] job_id=%s error=%s", jid, exc)
        return None


def _persist_fyers_job_start(job_id: str, stage: str, payload: dict[str, Any]) -> None:
    if str(stage or "").strip().lower() == "authorize":
        return
    try:
        raw_trading_date = payload.get("endDate") or payload.get("end_date") or dt.date.today().isoformat()
        trading_date = _parse_iso_date(raw_trading_date, "endDate")
        with pool.acquire() as conn:
            _ensure_fyers_tracking_tables(conn)
            _db_init_extraction_run(conn, job_id, trading_date, 0, job_type=stage)
    except Exception as exc:
        _logger.warning("[FYERS][PERSIST_JOB_START_FAILED] job_id=%s stage=%s error=%s", job_id, stage, exc)


def _persist_fyers_stop_request(job_id: str) -> bool:
    sql = """
    UPDATE FYERS_EXTRACTION_RUNS
    SET REQUESTED_STOP_FLAG = 'Y',
        STATUS = CASE
            WHEN STATUS IN ('RUNNING', 'STARTED', 'PENDING') THEN 'STOP_REQUESTED'
            ELSE STATUS
        END,
        UPDATED_AT = SYSTIMESTAMP
    WHERE JOB_ID = :job_id
    """
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {"job_id": job_id})
                updated = int(cur.rowcount or 0)
            conn.commit()
        return updated > 0
    except Exception as exc:
        _logger.warning("[FYERS][PERSIST_STOP_FAILED] job_id=%s error=%s", job_id, exc)
        return False


def _persist_fyers_orphaned_stop(job_id: str) -> bool:
    """Finalize a stop when no local worker exists to observe the stop flag."""
    sql = """
    UPDATE FYERS_EXTRACTION_RUNS
    SET REQUESTED_STOP_FLAG = 'Y',
        STATUS = 'STOPPED',
        UPDATED_AT = SYSTIMESTAMP,
        COMPLETED_AT = NVL(COMPLETED_AT, SYSTIMESTAMP),
        ERROR_MESSAGE = CASE
            WHEN ERROR_MESSAGE IS NULL OR TRIM(ERROR_MESSAGE) IS NULL
                THEN 'Stopped by user after the FYERS worker session was no longer active.'
            ELSE ERROR_MESSAGE
        END
    WHERE JOB_ID = :job_id
      AND STATUS IN ('RUNNING', 'STARTED', 'PENDING', 'STOP_REQUESTED')
    """
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {"job_id": job_id})
                updated = int(cur.rowcount or 0)
            conn.commit()
        return updated > 0
    except Exception as exc:
        _logger.warning("[FYERS][PERSIST_ORPHANED_STOP_FAILED] job_id=%s error=%s", job_id, exc)
        return False


def _persist_fyers_job_terminal(job_id: str, result: dict[str, Any]) -> None:
    if str(result.get("stage") or "").strip().lower() == "authorize":
        return
    final_status = "SUCCESS" if bool(result.get("ok")) else "FAILED"
    if result.get("canExtract") is False or result.get("requiresAuthorization") is True:
        final_status = "AUTH_EXPIRED"
    elif bool(result.get("cancelled")):
        final_status = "STOPPED"
    elif bool(result.get("ok")) and _parse_int((result.get("stats") or {}).get("failed"), 0) > 0:
        final_status = "PARTIAL"
    try:
        with pool.acquire() as conn:
            _db_update_extraction_run_counts(
                conn,
                job_id,
                status=final_status,
                error_message=str(result.get("message") or "")[:4000] or None,
            )
    except Exception as exc:
        _logger.warning("[FYERS][PERSIST_JOB_TERMINAL_FAILED] job_id=%s status=%s error=%s", job_id, final_status, exc)


def _enrich_fyers_job_stats(job: dict[str, Any]) -> dict[str, Any]:
    raw_stats = dict(job.get("stats") or {})
    result = job.get("result")
    if isinstance(result, dict):
        result_stats = result.get("stats")
        if isinstance(result_stats, dict):
            raw_stats = {**raw_stats, **result_stats}
    total = max(
        _parse_int(raw_stats.get("total"), _parse_int(raw_stats.get("nifty500_total"), 0)),
        0,
    )
    inserted = max(_parse_int(raw_stats.get("inserted"), 0), 0)
    skipped = max(_parse_int(raw_stats.get("skipped"), 0), 0)
    failed = max(_parse_int(raw_stats.get("failed"), 0), 0)
    invalid = max(_parse_int(raw_stats.get("invalid"), 0), 0)
    errors = max(_parse_int(raw_stats.get("errors"), failed), 0)
    completed = max(_parse_int(raw_stats.get("completed"), inserted + skipped + failed + invalid), 0)
    remaining = max(total - completed, 0)
    trading_date = job.get("trading_date")
    raw_stats.update({
        "total": total,
        "tradingDate": trading_date,
        "inserted": inserted,
        "remaining": remaining,
        "failed": failed,
        "skipped": skipped,
        "insertedSkipped": max(_parse_int(raw_stats.get("insertedSkipped"), skipped), 0),
        "invalid": invalid,
        "errors": errors,
    })
    return raw_stats


def _serialize_fyers_job(job: dict[str, Any], tail_lines: int | None = None) -> dict[str, Any]:
    tail = _normalize_fyers_job_tail(tail_lines)
    logs = list(job.get("logs") or [])
    total_lines = max(_parse_int(job.get("_logs_total"), len(logs)), len(logs))
    status = str(job.get("status") or "running")
    done = status in _FYERS_TERMINAL_JOB_STATUSES
    current_symbol = job.get("currentSymbol") or job.get("current_symbol")
    payload: dict[str, Any] = {
        "jobId": job.get("id"),
        "stage": job.get("stage"),
        "status": status,
        "done": done,
        "message": job.get("message") or "",
        "startedAt": job.get("started_at"),
        "updatedAt": job.get("updated_at"),
        "finishedAt": job.get("finished_at"),
        "stats": _enrich_fyers_job_stats(job),
        "tradingDate": job.get("trading_date"),
        "trading_date": job.get("trading_date"),
        "currentSymbol": current_symbol,
        "current_symbol": current_symbol,
        "clientSessionId": job.get("client_session_id"),
        "failedSymbols": job.get("failed_symbols") or [],
        "failed_symbols": job.get("failed_symbols") or [],
        "skippedSymbols": job.get("skipped_symbols") or [],
        "skipped_symbols": job.get("skipped_symbols") or [],
        "timing": _build_fyers_job_timing_payload(job),
        "loginUrl": job.get("login_url"),
        "auth_url": job.get("login_url"),
        "stopRequested": bool(job.get("stop_requested")),
        "stopRequestedAt": job.get("stop_requested_at"),
        "logs": {
            "tail": logs[-tail:],
            "totalLines": total_lines,
        },
    }
    result_rows = (job.get("result") or {}).get("results") if isinstance(job.get("result"), dict) else None
    if isinstance(result_rows, list):
        payload["symbols"] = [
            _build_fyers_symbol_payload(
                {
                    "symbol": row.get("normalized_symbol") or row.get("symbol") or row.get("input_symbol"),
                    "status": row.get("status"),
                    "status_reason": row.get("error_code"),
                    "retry_count": row.get("retry_count"),
                    "error_message": row.get("error_message"),
                },
                trading_date=job.get("trading_date"),
            )
            for row in result_rows
            if isinstance(row, dict)
        ]
    if done and isinstance(job.get("result"), dict):
        payload["result"] = job.get("result")
        payload["ok"] = bool((job.get("result") or {}).get("ok"))
    else:
        payload["ok"] = status != "failed"
    return payload


def _fyers_busy_job_payload(job_id: str) -> dict[str, Any]:
    now_iso = _utc_now_iso()
    return {
        "jobId": job_id,
        "stage": None,
        "status": "running",
        "done": False,
        "message": "FYERS job status is busy. Retrying...",
        "startedAt": None,
        "updatedAt": now_iso,
        "finishedAt": None,
        "stats": {"inserted": 0, "skipped": 0, "failed": 0, "errors": 0},
        "currentSymbol": None,
        "current_symbol": None,
        "timing": {
            "startedAt": None,
            "updatedAt": now_iso,
            "finishedAt": None,
            "lastHeartbeatAt": now_iso,
            "etaTimestamp": None,
            "completedSymbols": 0,
            "totalSymbols": 0,
            "elapsedSeconds": None,
        },
        "loginUrl": None,
        "stopRequested": False,
        "stopRequestedAt": None,
        "logs": {
            "tail": [],
            "totalLines": 0,
        },
        "ok": True,
        "busy": True,
    }


def _find_active_fyers_job_locked(*, stages: set[str] | None = None) -> dict[str, Any] | None:
    return _find_active_fyers_job_locked_for_session(stages=stages, client_session_id="")


def _persist_fyers_stale_job(job_id: str, reason: str) -> bool:
    sql = """
    UPDATE FYERS_EXTRACTION_RUNS
    SET STATUS = 'CANCELLED',
        REQUESTED_STOP_FLAG = 'Y',
        UPDATED_AT = SYSTIMESTAMP,
        COMPLETED_AT = NVL(COMPLETED_AT, SYSTIMESTAMP),
        ERROR_MESSAGE = :reason
    WHERE JOB_ID = :job_id
      AND STATUS IN ('RUNNING', 'STARTED', 'PENDING', 'STOP_REQUESTED')
    """
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {"job_id": job_id, "reason": reason[:4000]})
                updated = int(cur.rowcount or 0)
            conn.commit()
        return updated > 0
    except Exception as exc:
        _logger.warning("[FYERS][STALE_PERSIST_FAILED] job_id=%s error=%s", job_id, exc)
        return False


def _cleanup_stale_persisted_fyers_jobs() -> None:
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=FYERS_ACTIVE_JOB_STALE_SEC)
    sql = """
    SELECT JOB_ID, STATUS, UPDATED_AT, STARTED_AT
    FROM FYERS_EXTRACTION_RUNS
    WHERE STATUS IN ('RUNNING', 'STARTED', 'PENDING', 'STOP_REQUESTED')
    """
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall()
                columns = [str(item[0]).strip().lower() for item in cur.description]
        for row in rows:
            record = dict(zip(columns, row))
            heartbeat = _coerce_datetime_value(record.get("updated_at")) or _coerce_datetime_value(record.get("started_at"))
            if heartbeat is None:
                continue
            if heartbeat.astimezone(dt.timezone.utc) >= cutoff:
                continue
            job_id = str(record.get("job_id") or "").strip()
            if not job_id:
                continue
            _persist_fyers_stale_job(
                job_id,
                f"FYERS stale job was closed automatically after {FYERS_ACTIVE_JOB_STALE_SEC} seconds without a heartbeat.",
            )
    except Exception as exc:
        _logger.warning("[FYERS][STALE_PERSIST_SCAN_FAILED] error=%s", exc)


def _find_active_fyers_job_locked_for_session(
    *,
    stages: set[str] | None = None,
    client_session_id: str = "",
) -> dict[str, Any] | None:
    for job in _FYERS_JOBS.values():
        status = str(job.get("status") or "").strip().lower()
        if status in _FYERS_TERMINAL_JOB_STATUSES:
            continue
        stage = str(job.get("stage") or "").strip().lower()
        if stages and stage not in stages:
            continue
        if client_session_id:
            if _normalize_fyers_client_session_id(job.get("client_session_id")) != client_session_id:
                continue
        return job
    return None


def _fyers_running_job_payload(job: dict[str, Any], *, requested_stage: str) -> dict[str, Any]:
    payload = _serialize_fyers_job(job)
    existing_job_id = str(payload.get("jobId") or job.get("id") or "").strip()
    existing_stage = str(job.get("stage") or requested_stage).strip().lower() or requested_stage
    return {
        "ok": False,
        "jobId": existing_job_id,
        "job_id": existing_job_id,
        "runId": existing_job_id,
        "run_id": existing_job_id,
        "stage": existing_stage,
        "requestedStage": requested_stage,
        "status": "RUNNING",
        "done": False,
        "message": f"FYERS automation insertion is already running ({existing_stage}).",
        "job": payload,
    }


def _run_fyers_job_async(
    stage: str,
    payload: dict[str, Any],
    runner: Callable[[dict[str, Any], Optional[Callable[[str], None]], Optional[Callable[[], bool]]], dict[str, Any]],
) -> dict[str, Any]:
    now_ts = time.time()
    job_id = uuid.uuid4().hex
    runner_payload = dict(payload or {})
    client_session_id = _normalize_fyers_client_session_id(
        runner_payload.get("clientSessionId") or runner_payload.get("client_session_id")
    )
    if client_session_id:
        runner_payload["clientSessionId"] = client_session_id
        runner_payload["client_session_id"] = client_session_id
    runner_payload["runId"] = job_id
    runner_payload["run_id"] = job_id
    runner_payload["jobType"] = stage
    trading_date = str(
        runner_payload.get("endDate")
        or runner_payload.get("end_date")
        or dt.date.today().isoformat()
    ).strip()
    job: dict[str, Any] = {
        "id": job_id,
        "stage": stage,
        "status": "running",
        "message": f"{stage.capitalize()} job started.",
        "started_at": _utc_now_iso(),
        "updated_at": _utc_now_iso(),
        "finished_at": None,
        "finished_ts": 0.0,
        "stats": {"inserted": 0, "skipped": 0, "failed": 0, "errors": 0},
        "logs": [],
        "result": None,
        "login_url": None,
        "client_session_id": client_session_id,
        "stop_requested": False,
        "stop_requested_at": None,
        "trading_date": trading_date,
    }

    def _worker() -> None:
        def _log(line: str) -> None:
            with _FYERS_JOBS_LOCK:
                current = _FYERS_JOBS.get(job_id)
                if not current:
                    return
                _append_job_log(current, line)
                _update_fyers_job_progress_from_log(current, line)

        try:
            _persist_fyers_job_start(job_id, stage, runner_payload)
            _log(f"[INFO] Running FYERS {stage} job.")
            result = runner(runner_payload, _log, lambda: _job_should_stop(job_id))
        except Exception as exc:
            result = {
                "ok": False,
                "stage": stage,
                "message": str(exc),
                "stats": {"inserted": 0, "skipped": 0, "failed": 1, "errors": 1},
            }
            _log(f"[ERROR] {exc}")
            _log(traceback.format_exc())

        _persist_fyers_job_terminal(job_id, result)
        with _FYERS_JOBS_LOCK:
            current = _FYERS_JOBS.get(job_id)
            if not current:
                return
            _append_fyers_terminal_summary(current, result)
            current["result"] = result
            current["stats"] = (result or {}).get("stats") or current.get("stats")
            current["message"] = (result or {}).get("message") or current.get("message")
            current["status"] = (
                "cancelled"
                if bool((result or {}).get("cancelled"))
                else ("succeeded" if bool((result or {}).get("ok")) else "failed")
            )
            current["finished_at"] = _utc_now_iso()
            current["finished_ts"] = time.time()
            current["updated_at"] = current["finished_at"]

    with _FYERS_JOBS_LOCK:
        _cleanup_fyers_jobs_locked(now_ts)
        if stage in _FYERS_SINGLE_FLIGHT_STAGES:
            active_job = _find_active_fyers_job_locked_for_session(
                stages=_FYERS_SINGLE_FLIGHT_STAGES,
                client_session_id=client_session_id,
            )
            if active_job:
                return _fyers_running_job_payload(active_job, requested_stage=stage)
        _FYERS_JOBS[job_id] = job

    thread = threading.Thread(target=_worker, daemon=True, name=f"fyers-{stage}-{job_id[:8]}")
    thread.start()
    return {
        "ok": True,
        "jobId": job_id,
        "job_id": job_id,
        "runId": job_id,
        "run_id": job_id,
        "stage": stage,
        "status": "STARTED",
        "jobStatus": "running",
        "message": (
            "FYERS authorization started in background."
            if stage == "authorize"
            else (
            "FYERS extraction started in background"
            if stage == "batch"
            else f"{stage.capitalize()} job started in background."
        )),
    }


def fyers_get_latest_job() -> dict[str, Any]:
    if not _FYERS_JOBS_LOCK.acquire(timeout=FYERS_JOB_LOCK_TIMEOUT_SEC):
        return {"ok": True, "job": None}
    try:
        _cleanup_fyers_jobs_locked(time.time())
        if not _FYERS_JOBS:
            return {"ok": True, "job": None}
        latest_job = max(_FYERS_JOBS.values(), key=lambda j: j.get("started_at", ""))
        return {"ok": True, "job": _serialize_fyers_job(latest_job)}
    finally:
        _FYERS_JOBS_LOCK.release()


def fyers_get_latest_active_job() -> dict[str, Any]:
    if _FYERS_JOBS_LOCK.acquire(timeout=FYERS_JOB_LOCK_TIMEOUT_SEC):
        try:
            _cleanup_fyers_jobs_locked(time.time())
            active = _find_active_fyers_job_locked()
            if active:
                return {"ok": True, "job": _serialize_fyers_job(active)}
        finally:
            _FYERS_JOBS_LOCK.release()
    _cleanup_stale_persisted_fyers_jobs()
    sql = """
    SELECT JOB_ID
    FROM (
        SELECT JOB_ID
        FROM FYERS_EXTRACTION_RUNS
        WHERE STATUS IN ('RUNNING', 'STARTED', 'PENDING', 'STOP_REQUESTED')
        ORDER BY NVL(UPDATED_AT, STARTED_AT) DESC
    )
    WHERE ROWNUM = 1
    """
    try:
        with pool.acquire() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                row = cur.fetchone()
        if not row:
            return {"ok": True, "job": None}
        return {"ok": True, "job": _load_fyers_job_snapshot(str(row[0]), include_symbols=False)}
    except Exception as exc:
        _logger.warning("[FYERS][LATEST_ACTIVE_READ_FAILED] error=%s", exc)
        return {"ok": True, "job": None, "degraded": True}


def fyers_get_job(
    job_id: str,
    tail_lines: int | None = None,
    *,
    include_symbols: bool = True,
) -> dict[str, Any]:
    jid = str(job_id or "").strip()
    if not jid:
        raise ValueError("jobId is required.")
    tail = _normalize_fyers_job_tail(tail_lines)
    if not _FYERS_JOBS_LOCK.acquire(timeout=FYERS_JOB_LOCK_TIMEOUT_SEC):
        _logger.warning(
            "[FYERS][JOB_LOOKUP_BUSY] job_id=%s lock_timeout_sec=%s",
            jid,
            FYERS_JOB_LOCK_TIMEOUT_SEC,
        )
        return _fyers_busy_job_payload(jid)

    job_snapshot: dict[str, Any] | None = None
    registry_size = 0
    known_job_ids: list[str] = []
    try:
        _cleanup_fyers_jobs_locked(time.time())
        job = _FYERS_JOBS.get(jid)
        registry_size = len(_FYERS_JOBS)
        if not job:
            known_job_ids = list(_FYERS_JOBS.keys())[-5:]
        else:
            job_snapshot = dict(job)
            job_logs = job.get("logs") or []
            if isinstance(job_logs, list):
                job_snapshot["logs"] = list(job_logs[-tail:])
                job_snapshot["_logs_total"] = len(job_logs)
            else:
                copied_logs = list(job_logs)
                job_snapshot["logs"] = copied_logs[-tail:]
                job_snapshot["_logs_total"] = len(copied_logs)
            result_payload = job.get("result")
            if isinstance(result_payload, dict):
                job_snapshot["result"] = dict(result_payload)
    finally:
        _FYERS_JOBS_LOCK.release()

    if job_snapshot is None:
        _logger.warning(
            "[FYERS][JOB_LOOKUP_MISS] job_id=%s registry_size=%s known_job_ids=%s",
            jid,
            registry_size,
            known_job_ids,
        )
        persisted = _load_fyers_job_snapshot(jid, include_symbols=include_symbols)
        if persisted is not None:
            return persisted
        raise ValueError(f"FYERS job not found: {jid}")

    _logger.debug(
        "[FYERS][JOB_LOOKUP_HIT] job_id=%s status=%s created_at=%s updated_at=%s finished_at=%s registry_size=%s",
        jid,
        job_snapshot.get("status"),
        job_snapshot.get("started_at"),
        job_snapshot.get("updated_at"),
        job_snapshot.get("finished_at"),
        registry_size,
    )
    return _serialize_fyers_job(job_snapshot, tail_lines=tail_lines)


def fyers_request_stop(job_id: str) -> dict[str, Any]:
    jid = str(job_id or "").strip()
    if not jid:
        raise ValueError("jobId is required.")
    in_memory_payload: dict[str, Any] | None = None
    with _FYERS_JOBS_LOCK:
        _cleanup_fyers_jobs_locked(time.time())
        job = _FYERS_JOBS.get(jid)
        if job is not None:
            current_status = str(job.get("status") or "running")
            if current_status in _FYERS_TERMINAL_JOB_STATUSES:
                in_memory_payload = _serialize_fyers_job(job)
                in_memory_payload["message"] = "FYERS job has already completed."
                in_memory_payload["stopAccepted"] = False
            else:
                if not job.get("stop_requested"):
                    job["stop_requested"] = True
                    job["stop_requested_at"] = _utc_now_iso()
                    job["message"] = "Fyers automation stop requested. Stopping immediately."
                    _append_job_log(job, "[INFO] Stop requested. Stopping FYERS job immediately.")
                in_memory_payload = _serialize_fyers_job(job)
                in_memory_payload["message"] = "Fyers automation stop requested. Stopping immediately."
                in_memory_payload["stopAccepted"] = True
    if in_memory_payload is not None:
        if bool(in_memory_payload.get("stopAccepted")):
            _persist_fyers_stop_request(jid)
        return in_memory_payload
    # A recovered persisted job has no entry in this process's worker registry.
    # Mark it terminal immediately: otherwise STOP_REQUESTED remains visible until
    # the stale-heartbeat timeout even though no worker can consume that flag.
    persisted_updated = _persist_fyers_orphaned_stop(jid)
    persisted = _load_fyers_job_snapshot(jid, include_symbols=True)
    if persisted is None:
        raise ValueError(f"FYERS job not found: {jid}")
    persisted["stopAccepted"] = bool(persisted_updated)
    persisted["stopRequested"] = True
    persisted["message"] = "Fyers automation stop requested. Stopping immediately."
    return persisted


def fyers_authorize(
    line_logger: Optional[Callable[[str], None]] = None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    project_dir = _resolve_fyers_project_dir()
    today = _today_local_iso()
    login_url_emitted = False

    def _forward_auth_stdout(line: str) -> None:
        nonlocal login_url_emitted
        text = str(line or "").strip()
        if text:
            login_match = _FYERS_LOGIN_URL_RE.search(text)
            if login_match and "fyers.in" in login_match.group(0).lower():
                login_url_emitted = True
        if line_logger:
            line_logger(line)

    if not force:
        auth_valid, _state = _is_fyers_authenticated_today(project_dir)
        token_metadata = _read_fyers_token_metadata(project_dir)
        if auth_valid and bool(token_metadata.get("authenticated")):
            message = _build_fyers_authenticated_message(token_metadata.get("expiresAt"))
            if line_logger:
                try:
                    line_logger(f"[INFO] {message}")
                except Exception:
                    pass
            return {
                "ok": True,
                "stage": "authorize",
                "status": "ALREADY_AUTHENTICATED",
                "message": message,
                "cached": True,
                "authDate": str(_state.get("last_auth_date") or "").strip() or today,
                "requiresAuthorization": False,
                "auth_url": None,
                "loginUrl": None,
                "expires_at": token_metadata.get("expiresAt"),
                "expiresAt": token_metadata.get("expiresAt"),
                "expiresAtUtc": token_metadata.get("expiresAtUtc"),
                "verifiedAt": str(_state.get("verified_at") or _state.get("last_auth_at") or "").strip() or None,
                "remainingValidityMinutes": max(
                    0,
                    math.ceil((_resolve_fyers_auth_valid_until_epoch(_state, token_metadata) - int(time.time())) / 60),
                ),
                "stats": {
                    "inserted": 0,
                    "skipped": 0,
                    "failed": 0,
                    "errors": 0,
                },
                "logs": {
                    "command": [],
                    "cwd": str(project_dir),
                    "durationSeconds": 0,
                    "timedOut": False,
                    "stdoutTail": [message],
                    "stderrTail": [],
                },
            }

    run_result: dict[str, Any] | None = None
    pending_state: dict[str, Any] = {}
    for attempt in range(1, FYERS_AUTH_RETRY_COUNT + 1):
        if line_logger and FYERS_AUTH_RETRY_COUNT > 1:
            try:
                line_logger(f"[INFO] FYERS authorization attempt {attempt}/{FYERS_AUTH_RETRY_COUNT}.")
            except Exception:
                pass
        fresh_state = _fresh_fyers_state()
        pending_state = _mark_fyers_auth_pending(project_dir, fresh_state)
        run_result = _run_fyers_module(
            "src.token_helper",
            [],
            timeout_sec=min(FYERS_AUTH_TIMEOUT_SEC, FYERS_AUTH_STATE_TTL_SEC),
            env_overrides={"FYERS_STATE": fresh_state},
            on_stdout_line=_forward_auth_stdout,
            on_stderr_line=(lambda line: line_logger(f"[stderr] {line}") if line_logger else None),
        )
        if run_result.get("timed_out") or run_result.get("ok"):
            break
        combined_error_text = "\n".join([
            str(run_result.get("stderr") or ""),
            str(run_result.get("stdout") or ""),
            "\n".join(run_result.get("stderr_tail") or []),
        ])
        should_retry = (
            attempt < FYERS_AUTH_RETRY_COUNT
            and _is_invalid_auth_code_failure(combined_error_text)
            and not _is_invalid_refresh_token_failure(combined_error_text)
            and not login_url_emitted
        )
        if not should_retry:
            if line_logger and login_url_emitted and _is_invalid_auth_code_failure(combined_error_text):
                try:
                    line_logger(
                        "[WARN] Authorization returned an invalid/stale auth code after a live login URL was opened. "
                        "Skipping automatic retry to avoid creating duplicate callback tabs."
                    )
                except Exception:
                    pass
            break
        if line_logger:
            try:
                line_logger(
                    "[WARN] Authorization returned an invalid/stale auth code. "
                    "Retrying with a fresh state."
                )
            except Exception:
                pass
    if run_result is None:
        run_result = {
            "ok": False,
            "returncode": 1,
            "timed_out": False,
            "duration_seconds": 0,
            "stdout": "",
            "stderr": "Authorization command failed.",
            "stdout_tail": [],
            "stderr_tail": ["Authorization command failed."],
            "command": [],
            "cwd": str(project_dir),
        }
    logs = _build_logs_payload(run_result)
    stdout_text = str(run_result.get("stdout") or "")
    message = "FYERS authorization completed."
    if "refreshed" in stdout_text.lower():
        message = "FYERS access token refreshed."
    elif "saved" in stdout_text.lower():
        message = "FYERS access token updated."
    if run_result.get("timed_out") or not run_result.get("ok"):
        recovered, recovered_state, recovered_metadata = _try_reconcile_fyers_auth_completion(
            project_dir,
            state=pending_state,
        )
        if recovered:
            return {
                "ok": True,
                "stage": "authorize",
                "status": "AUTHORIZED",
                "message": "FYERS access token updated.",
                "cached": False,
                "authDate": recovered_state.get("last_auth_date") or today,
                "authenticated": True,
                "canExtract": True,
                "requiresAuthorization": False,
                "auth_url": None,
                "loginUrl": None,
                "expires_at": recovered_metadata.get("expiresAt"),
                "expiresAt": recovered_metadata.get("expiresAt"),
                "expiresAtUtc": recovered_metadata.get("expiresAtUtc"),
                "stats": {
                    "inserted": 0,
                    "skipped": 0,
                    "failed": 0,
                    "errors": 0,
                },
                "logs": logs,
            }
    if run_result.get("timed_out"):
        _mark_fyers_auth_failure(project_dir, "STALE_CALLBACK")
        payload = _build_fyers_failure("authorize", FYERS_STALE_CALLBACK_MESSAGE, run_result)
        return _as_authorization_failure(
            payload,
            status="STALE_CALLBACK",
            code="FYERS_STALE_CALLBACK",
            message=FYERS_STALE_CALLBACK_MESSAGE,
        )
    if not run_result.get("ok"):
        stderr_tail = run_result.get("stderr_tail") or []
        detail = stderr_tail[-1] if stderr_tail else "Authorization command failed."
        stderr_text = str(run_result.get("stderr") or "")
        combined_failure = "\n".join([stderr_text, detail])
        status = "AUTH_REQUIRED"
        code = "FYERS_AUTH_REQUIRED"
        reason = "AUTH_REQUIRED"
        if _is_proxy_connect_failure(combined_failure):
            detail = (
                "FYERS authorization failed due to proxy connectivity. Effective proxy is unreachable. "
                "Use FYERS_PROXY_MODE=direct (default) or configure valid proxy settings."
            )
        elif _is_invalid_refresh_token_failure(combined_failure) and not login_url_emitted:
            detail = FYERS_INVALID_REFRESH_MESSAGE
            status = "INVALID_REFRESH_TOKEN"
            code = "FYERS_INVALID_REFRESH_TOKEN"
            reason = "INVALID_REFRESH_TOKEN"
        elif _is_invalid_auth_code_failure(combined_failure):
            detail = FYERS_STALE_CALLBACK_MESSAGE
            status = "STALE_CALLBACK"
            code = "FYERS_STALE_CALLBACK"
            reason = "STALE_CALLBACK"
        _mark_fyers_auth_failure(project_dir, reason)
        payload = _build_fyers_failure("authorize", detail, run_result)
        payload["stats"]["errors"] = max(1, len(stderr_tail))  # type: ignore[index]
        return _as_authorization_failure(payload, status=status, code=code, message=detail)

    state = _mark_fyers_auth_success(project_dir)
    token_metadata = _read_fyers_token_metadata(project_dir)
    _write_cached_fyers_auth_status(_build_fyers_auth_status_payload(
        today=today,
        is_today=True,
        state=state,
        token_metadata=token_metadata,
        message=message,
        source="authorize",
    ))
    return {
        "ok": True,
        "stage": "authorize",
        "status": "AUTHORIZED",
        "message": message,
        "cached": False,
        "authDate": state.get("last_auth_date") or today,
        "requiresAuthorization": False,
        "auth_url": None,
        "loginUrl": None,
        "expires_at": token_metadata.get("expiresAt"),
        "expiresAt": token_metadata.get("expiresAt"),
        "expiresAtUtc": token_metadata.get("expiresAtUtc"),
        "stats": {
            "inserted": 0,
            "skipped": 0,
            "failed": 0,
            "errors": 0,
        },
        "logs": logs,
    }


def _build_fyers_already_authenticated_payload(
    *,
    today: str,
    state: dict[str, Any],
    token_metadata: dict[str, Any],
) -> dict[str, Any]:
    expires_at = token_metadata.get("expiresAt")
    remaining_validity_minutes = max(
        0,
        math.ceil((_resolve_fyers_auth_valid_until_epoch(state, token_metadata) - int(time.time())) / 60),
    )
    return {
        "ok": True,
        "stage": "authorize",
        "status": "ALREADY_AUTHENTICATED",
        "message": _build_fyers_authenticated_message(expires_at),
        "cached": True,
        "authDate": str(state.get("last_auth_date") or "").strip() or today,
        "authenticatedToday": True,
        "authenticated": True,
        "requiresAuthorization": False,
        "auth_url": None,
        "loginUrl": None,
        "expires_at": expires_at,
        "expiresAt": expires_at,
        "expiresAtUtc": token_metadata.get("expiresAtUtc"),
        "verifiedAt": str(state.get("verified_at") or state.get("last_auth_at") or "").strip() or None,
        "remainingValidityMinutes": remaining_validity_minutes,
        "stats": {
            "inserted": 0,
            "skipped": 0,
            "failed": 0,
            "errors": 0,
        },
        "logs": {
            "command": [],
            "cwd": str(_resolve_fyers_project_dir()),
            "durationSeconds": 0,
            "timedOut": False,
            "stdoutTail": [_build_fyers_authenticated_message(expires_at)],
            "stderrTail": [],
        },
    }


def fyers_run_authorize_job(
    payload: dict[str, Any],
    line_logger: Optional[Callable[[str], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> dict[str, Any]:
    del should_stop
    return fyers_authorize(
        line_logger=line_logger,
        force=bool(payload.get("force")),
    )


def fyers_run_single(
    payload: dict[str, Any],
    line_logger: Optional[Callable[[str], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> dict[str, Any]:
    today = dt.date.today()
    try:
        default_start = _parse_iso_date(FYERS_DEFAULT_START_DATE, "FYERS_DEFAULT_START_DATE")
    except ValueError as exc:
        raise ValueError(str(exc)) from exc

    start_date = _parse_iso_date_with_default(payload.get("startDate") or payload.get("start_date"), "startDate", default_start)
    end_date = _parse_iso_date_with_default(payload.get("endDate") or payload.get("end_date"), "endDate", today)
    if end_date > today:
        raise ValueError(_FUTURE_DATE_ERROR)
    if end_date < start_date:
        raise ValueError("endDate cannot be earlier than startDate.")
    if not _date_range_has_weekday(start_date, end_date):
        raise ValueError("Weekend selected. Saturday and Sunday are market holidays.")

    resolution = FYERS_FIXED_RESOLUTION
    authorize_first = bool(payload.get("authorize", True))
    auth_payload = ensure_valid_fyers_auth(
        profile_validated_at=payload.get("_auth_prevalidated_at"),
    )
    if not auth_payload.get("ok"):
        auth_payload["stage"] = "single"
        return auth_payload
    symbol_rows = _normalize_symbols_payload(payload.get("symbol"), line_logger=line_logger)
    run_id = str(payload.get("runId") or payload.get("run_id") or uuid.uuid4().hex).strip() or uuid.uuid4().hex
    source_mode = _normalize_failed_symbol_source_mode(payload.get("sourceMode") or payload.get("source_mode") or "SINGLE_STOCK")

    if line_logger:
        try:
            input_symbols = ", ".join(item["input_symbol"] for item in symbol_rows)
            normalized_symbols = ", ".join(item["normalized_symbol"] for item in symbol_rows)
            line_logger("[INFO] FYERS single-stock request started.")
            line_logger(f"[INFO] Input symbols: {input_symbols}")
            line_logger(f"[INFO] Normalized symbols: {normalized_symbols}")
            line_logger(f"[INFO] Start date: {start_date.isoformat()} End date: {end_date.isoformat()} Resolution: {resolution}")
        except Exception:
            pass

    project_dir = _resolve_fyers_project_dir()

    total_symbols = len(symbol_rows)
    success_count = 0
    failed_count = 0
    skipped_count = 0
    inserted_rows_total = 0
    updated_rows_total = 0
    duplicate_rows_total = 0
    existing_rows_total = 0
    missing_ranges_total = 0
    missing_estimated_days_total = 0
    fetched_rows_total = 0
    failed_ranges_total: list[dict[str, Any]] = []
    api_time_seconds_total = 0.0
    db_time_seconds_total = 0.0
    success_trading_dates_total = 0
    results: list[dict[str, Any]] = []
    stop_requested = False
    auth_failed_detected = False
    run_started_at_ts = time.time()

    with pool.acquire() as conn:
        _ensure_fyers_tracking_tables(conn)
        _db_init_extraction_run(
            conn,
            run_id,
            end_date,
            total_symbols,
            job_type=str(payload.get("jobType") or payload.get("job_type") or source_mode).lower(),
        )
        _db_init_extraction_symbols(conn, run_id, end_date, [r["normalized_symbol"] for r in symbol_rows])
        previously_failed_permanent = _fetch_previously_failed_permanent_symbols(conn, end_date)

    for index, row in enumerate(symbol_rows):
        if should_stop and should_stop():
            stop_requested = True
            if line_logger:
                try:
                    line_logger("[INFO] Stop request detected. Ending FYERS single run immediately.")
                except Exception:
                    pass
            break
        input_symbol = row["input_symbol"]
        normalized_symbol = row["normalized_symbol"]
        clean_symbol = str(row.get("clean_symbol") or "").strip()
        symbol_result: dict[str, Any] = {
            "input_symbol": input_symbol,
            "normalized_symbol": normalized_symbol,
            "status": "FAILED_API_ERROR",
            "resolution": resolution,
            "fetched_count": 0,
            "xlsx_written": False,
            "db_insert_attempted": False,
            "inserted_rows": 0,
            "updated_rows": 0,
            "duplicate_rows_skipped": 0,
            "existing_rows": 0,
            "missing_ranges_count": 0,
            "missing_estimated_days": 0,
            "fetched_rows": 0,
            "skipped_existing_rows": 0,
            "failed_ranges": [],
            "remaining_ranges": 0,
            "api_time_seconds": 0.0,
            "db_time_seconds": 0.0,
            "success_trading_dates": 0,
            "error_message": None,
        }
        if line_logger:
            try:
                line_logger(
                    f"[INFO] Processing {index + 1}/{total_symbols}: {normalized_symbol} "
                    f"(resolution={resolution})"
                )
                eta_dt = _estimate_fyers_eta_datetime(
                    started_at_ts=run_started_at_ts,
                    completed_symbols=index,
                    total_symbols=total_symbols,
                )
                eta_display = _format_fyers_eta_display(eta_dt)
                if eta_display:
                    line_logger(f"[INFO] ETA Timestamp: {eta_display}")
                else:
                    line_logger("[INFO] ETA Timestamp: Calculating after first completed symbol.")
            except Exception:
                pass
        if not bool(row.get("resolved")):
            status = "FAILED_INVALID_SYMBOL"
            error_code = "INVALID_SYMBOL"
            error_message = (
                f"Symbol not found in FYERS symbol master."
                if not clean_symbol
                else f"Symbol {clean_symbol} not found in FYERS symbol master."
            )
            with pool.acquire() as conn:
                _merge_failed_symbol(
                    conn,
                    input_symbol=input_symbol,
                    normalized_symbol=normalized_symbol,
                    status=status,
                    error_code=error_code,
                    error_message=error_message,
                    start_date=start_date,
                    end_date=end_date,
                    retry_count=0,
                )
                _insert_skipped_rejected_symbol(
                    conn,
                    symbol=input_symbol,
                    fyers_symbol=normalized_symbol,
                    trading_date=end_date,
                    from_date=start_date,
                    to_date=end_date,
                    skip_reason=error_code,
                    run_id=run_id,
                    status=status,
                    error_code=error_code,
                    error_message=error_message,
                    source_mode=source_mode,
                    rerun_status="PENDING",
                )
                _db_update_extraction_symbol(conn, run_id, end_date, normalized_symbol, status, error_message)
                _db_update_extraction_run_counts(conn, run_id)
            symbol_result.update({
                "status": status,
                "error_message": error_message,
            })
            results.append(symbol_result)
            skipped_count += 1
            if line_logger:
                try:
                    line_logger(f"[WARN] {normalized_symbol} skipped: {error_message}")
                except Exception:
                    pass
            continue
        if index > 0 and FYERS_REQUEST_SLEEP_SECONDS > 0:
            sleep_started_at = time.monotonic()
            while (time.monotonic() - sleep_started_at) < FYERS_REQUEST_SLEEP_SECONDS:
                _raise_if_fyers_stop_requested(should_stop)
                time.sleep(min(0.1, max(0.01, FYERS_REQUEST_SLEEP_SECONDS)))
        retry_count = 0
        existing_before: set[dt.date] = set()
        fetch_ranges: list[tuple[dt.date, dt.date]] = []
        force_refresh = bool(payload.get("forceRefresh") or payload.get("force_refresh") or payload.get("force", False))

        with pool.acquire() as conn:
            _db_update_extraction_symbol(conn, run_id, end_date, normalized_symbol, "RUNNING")

            if normalized_symbol in previously_failed_permanent:
                if line_logger:
                    try:
                        line_logger(f"[WARN] {normalized_symbol} skipped: Previously failed with permanent error for this date.")
                    except Exception:
                        pass
                _db_update_extraction_symbol(conn, run_id, end_date, normalized_symbol, "SKIPPED", "Previously failed permanently.")
                symbol_result.update({
                    "status": "SKIPPED",
                    "error_message": "Previously failed permanently.",
                })
                results.append(symbol_result)
                skipped_count += 1
                _db_update_extraction_run_counts(conn, run_id)
                continue

            # Always request the selected range from FYERS. Existing rows are
            # reconciled only during the keyed upsert after the API response,
            # so the fetch path does not pre-check STOCK_EOD_HISTORY coverage.
            coverage_started_at = time.monotonic()
            existing_before = set()
            fetch_ranges = [(start_date, end_date)]
            existing_rows = 0
            missing_ranges_count = len(fetch_ranges)
            missing_estimated_days = _estimate_fyers_missing_days(fetch_ranges)
            db_time_seconds_total += time.monotonic() - coverage_started_at
            existing_rows_total += existing_rows
            missing_ranges_total += missing_ranges_count
            missing_estimated_days_total += missing_estimated_days
            symbol_result.update({
                "existing_rows": existing_rows,
                "missing_ranges_count": missing_ranges_count,
                "missing_estimated_days": missing_estimated_days,
                "remaining_ranges": missing_ranges_count,
            })

            if line_logger:
                try:
                    line_logger(
                        "[SINGLE_STOCK_SYNC] "
                        f"symbol={normalized_symbol} status=COVERAGE_CHECK "
                        f"from={start_date.isoformat()} to={end_date.isoformat()} "
                        f"existing_rows={existing_rows} missing_ranges={missing_ranges_count} "
                        f"missing_estimated_days={missing_estimated_days}"
                    )
                except Exception:
                    pass
            _logger.info(
                "[SINGLE_STOCK_SYNC] symbol=%s status=COVERAGE_CHECK from=%s to=%s existing_rows=%s missing_ranges=%s missing_estimated_days=%s",
                normalized_symbol,
                start_date.isoformat(),
                end_date.isoformat(),
                existing_rows,
                missing_ranges_count,
                missing_estimated_days,
            )

        if line_logger:
            try:
                line_logger(
                    "[INFO] direct_api_fetch "
                    f"symbol={normalized_symbol} "
                    f"start_date={start_date.isoformat()} "
                    f"end_date={end_date.isoformat()} "
                    f"resolution={resolution} "
                    "file_storage=disabled"
                )
            except Exception:
                pass

        try:
            fetch_payload = _fetch_fyers_ohlcv_for_missing_ranges(
                project_dir=project_dir,
                symbol=normalized_symbol,
                fetch_ranges=fetch_ranges,
                resolution=resolution,
                line_logger=line_logger,
                should_stop=should_stop,
            )
            direct_rows = list(fetch_payload.get("rows") or [])
            api_records_count_total = _parse_int(fetch_payload.get("fetched_rows"), 0)
            failed_ranges = list(fetch_payload.get("failed_ranges") or [])
            _fetch_meta = dict(fetch_payload.get("meta") or {})
            api_time_seconds_total += float(_fetch_meta.get("api_time_seconds") or 0.0)
            failed_ranges_total.extend(failed_ranges)
            fetched_rows_total += api_records_count_total
            symbol_result["fetched_count"] = api_records_count_total
            symbol_result["fetched_rows"] = api_records_count_total
            symbol_result["failed_ranges"] = failed_ranges
            symbol_result["remaining_ranges"] = len(failed_ranges)
            symbol_result["api_time_seconds"] = float(_fetch_meta.get("api_time_seconds") or 0.0)
            symbol_result["db_insert_attempted"] = True
            symbol_result["xlsx_written"] = False
            if not direct_rows:
                if failed_ranges:
                    status = "FAILED_API_ERROR"
                    error_code = "API_ERROR"
                    error_message = "All missing FYERS ranges failed."
                else:
                    status = "FAILED_NO_DATA"
                    error_code = "NO_DATA"
                    error_message = "No candle data returned by FYERS"
                with pool.acquire() as conn:
                    _merge_failed_symbol(
                        conn,
                        input_symbol=input_symbol,
                        normalized_symbol=normalized_symbol,
                        status=status,
                        error_code=error_code,
                        error_message=error_message,
                        start_date=start_date,
                        end_date=end_date,
                        retry_count=retry_count,
                    )
                    _insert_skipped_rejected_symbol(
                        conn,
                        symbol=input_symbol,
                        fyers_symbol=normalized_symbol,
                        trading_date=end_date,
                        from_date=start_date,
                        to_date=end_date,
                        skip_reason=error_code,
                        run_id=run_id,
                        status=status,
                        error_code=error_code,
                        error_message=error_message,
                        source_mode=source_mode,
                        rerun_status="PENDING",
                    )
                    _db_update_extraction_symbol(conn, run_id, end_date, normalized_symbol, status, error_message)
                    _db_update_extraction_run_counts(conn, run_id)
                symbol_result.update({
                    "status": status,
                    "error_message": error_message,
                })
                results.append(symbol_result)
                if failed_ranges:
                    failed_count += 1
                else:
                    skipped_count += 1
                continue

            with pool.acquire() as conn:
                _raise_if_fyers_stop_requested(should_stop)
                db_started_at = time.monotonic()
                raw_upsert_counts = _upsert_fyers_rows_direct(conn, direct_rows)
                upsert_counts = raw_upsert_counts if isinstance(raw_upsert_counts, dict) else {
                    "inserted": raw_upsert_counts,
                    "updated": 0,
                    "skipped": 0,
                }
                db_elapsed = time.monotonic() - db_started_at
                db_time_seconds_total += db_elapsed
                if "inserted_dates" in upsert_counts or "duplicate_dates" in upsert_counts:
                    inserted_dates = set(upsert_counts.get("inserted_dates") or set())
                    duplicate_dates = set(upsert_counts.get("duplicate_dates") or set())
                else:
                    inserted_dates = {
                        normalized_row[1]
                        for row in direct_rows
                        if (normalized_row := _normalize_fyers_upsert_row(row)) is not None
                    }
                    duplicate_dates = set()
                loaded_dates = inserted_dates | duplicate_dates
                inserted_rows = _parse_int(upsert_counts.get("inserted"), len(inserted_dates))
                updated_rows = _parse_int(upsert_counts.get("updated"), 0)
                skipped_unchanged_rows = _parse_int(upsert_counts.get("skipped"), 0)
                skipped_existing_rows = skipped_unchanged_rows if force_refresh else len(existing_before) + skipped_unchanged_rows
                if line_logger:
                    try:
                        line_logger(
                            "[SINGLE_STOCK_SYNC] db_merge "
                            f"symbol={normalized_symbol} "
                            f"selected_start_date={start_date.isoformat()} "
                            f"selected_end_date={end_date.isoformat()} "
                            "file_storage=disabled "
                            f"api_records_count={api_records_count_total} "
                            f"final_records_count={len(loaded_dates)} "
                            f"inserted={inserted_rows} "
                            f"updated={updated_rows} "
                            f"skipped={skipped_existing_rows} "
                            f"failed_ranges={len(failed_ranges)}"
                        )
                    except Exception:
                        pass
                _logger.info(
                    "[SINGLE_STOCK_SYNC] symbol=%s db_merge inserted=%s updated=%s skipped=%s failed_ranges=%s db_time=%.3fs",
                    normalized_symbol,
                    inserted_rows,
                    updated_rows,
                    skipped_existing_rows,
                    len(failed_ranges),
                    db_elapsed,
                )

                _merge_success_symbol_dates(
                    conn,
                    symbol=normalized_symbol,
                    inserted_dates=inserted_dates,
                    duplicate_dates=duplicate_dates,
                )

                duplicate_rows = skipped_existing_rows
                success_trading_dates = len(loaded_dates)

                symbol_result.update({
                    "status": "PARTIAL_SUCCESS" if failed_ranges else "SUCCESS",
                    "inserted_rows": inserted_rows,
                    "updated_rows": updated_rows,
                    "duplicate_rows_skipped": duplicate_rows,
                    "skipped_existing_rows": skipped_existing_rows,
                    "success_trading_dates": success_trading_dates,
                    "db_time_seconds": round(db_elapsed, 3),
                    "error_message": None,
                })
                results.append(symbol_result)
                _db_update_extraction_symbol(conn, run_id, end_date, normalized_symbol, "SUCCESS")

                success_count += 1
                inserted_rows_total += inserted_rows
                updated_rows_total += updated_rows
                duplicate_rows_total += duplicate_rows
                success_trading_dates_total += success_trading_dates

                if line_logger:
                    try:
                        line_logger(
                            f"Inserted {inserted_rows} rows, Updated {updated_rows} rows for {normalized_symbol} into Oracle DB"
                        )
                    except Exception:
                        pass
                _db_update_extraction_run_counts(conn, run_id)

        except Exception as exc:
            if isinstance(exc, FyersStopRequestedError):
                stop_requested = True
                if line_logger:
                    try:
                        line_logger("[INFO] Stop request detected. Aborting FYERS single run immediately.")
                    except Exception:
                        pass
                break
            error_message = str(exc)
            if _contains_db_error_signature(error_message):
                status = "FAILED_DB_ERROR"
                error_code = "DB_ERROR"
            else:
                status, error_code, _classified_message = _classify_symbol_failure(
                    error_message,
                    stage="fetch",
                )
            if status == "FAILED_AUTH":
                auth_failed_detected = True
                try:
                    _mark_fyers_auth_failure(project_dir, "AUTH_EXPIRED")
                except Exception:
                    pass
                with pool.acquire() as conn:
                    _db_update_extraction_symbol(
                        conn,
                        run_id,
                        end_date,
                        normalized_symbol,
                        "AUTH_EXPIRED",
                        FYERS_AUTH_REQUIRED_MESSAGE,
                    )
                    _db_update_extraction_run_counts(conn, run_id)
                if line_logger:
                    try:
                        line_logger("[FYERS_AUTH_FAILED] authentication expired. Aborting before failed-symbol tracking.")
                    except Exception:
                        pass
                break
            expected_symbol_skip = status in _FYERS_EXPECTED_SYMBOL_SKIP_STATUSES
            with pool.acquire() as conn:
                try:
                    _merge_failed_symbol(
                        conn,
                        input_symbol=input_symbol,
                        normalized_symbol=normalized_symbol,
                        status=status,
                        error_code=error_code,
                        error_message=error_message,
                        start_date=start_date,
                        end_date=end_date,
                        retry_count=retry_count,
                    )
                except Exception:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                try:
                    _insert_skipped_rejected_symbol(
                        conn,
                        symbol=input_symbol,
                        fyers_symbol=normalized_symbol,
                        trading_date=end_date,
                        from_date=start_date,
                        to_date=end_date,
                        skip_reason=error_code or status,
                        run_id=run_id,
                        status=status,
                        error_code=error_code,
                        error_message=error_message,
                        source_mode=source_mode,
                        rerun_status="PENDING",
                    )
                except Exception:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                _db_update_extraction_symbol(conn, run_id, end_date, normalized_symbol, status, error_message)
                _db_update_extraction_run_counts(conn, run_id)
            symbol_result.update({
                "status": status,
                "error_message": error_message,
            })
            results.append(symbol_result)
            if expected_symbol_skip:
                skipped_count += 1
            else:
                failed_count += 1
            if line_logger:
                try:
                    if expected_symbol_skip:
                        line_logger(f"[WARN] {normalized_symbol} skipped: {error_message}")
                    else:
                        line_logger(f"[ERROR] {normalized_symbol} failed: {error_message}")
                        line_logger(traceback.format_exc())
                except Exception:
                    pass
        if auth_failed_detected:
            break

    status = "FAILED"
    if success_count == total_symbols:
        status = "SUCCESS"
    elif success_count > 0:
        status = "PARTIAL_SUCCESS"
    elif skipped_count == total_symbols and failed_count == 0:
        status = "ALREADY_UP_TO_DATE"
    if failed_ranges_total and success_count > 0:
        status = "PARTIAL_SUCCESS"
    if stop_requested:
        status = "CANCELLED"
    if auth_failed_detected:
        status = "AUTH_EXPIRED"

    message = "Single stock run completed."
    if status == "PARTIAL_SUCCESS":
        message = "Single stock run completed with partial success."
    elif status == "ALREADY_UP_TO_DATE":
        message = "Single stock run already up to date."
    elif status == "FAILED":
        message = "Single stock run failed."
    elif status == "CANCELLED":
        message = "Single stock run stopped immediately."
    if auth_failed_detected:
        message = FYERS_AUTH_REQUIRED_MESSAGE
    elif status == "PARTIAL_SUCCESS" and failed_ranges_total:
        message = "Single stock run completed with failed FYERS ranges."

    if line_logger:
        try:
            line_logger(
                "[SINGLE_STOCK_SYNC] "
                f"status={status} inserted={inserted_rows_total} updated={updated_rows_total} "
                f"skipped={duplicate_rows_total} failed_ranges={len(failed_ranges_total)} "
                f"runtime={round(time.time() - run_started_at_ts, 3)}s"
            )
        except Exception:
            pass

    try:
        with pool.acquire() as conn:
            final_db_status = "COMPLETED"
            if status == "SUCCESS":
                final_db_status = "SUCCESS"
            elif status == "FAILED":
                final_db_status = "FAILED"
            elif status == "CANCELLED":
                final_db_status = "STOPPED"
            elif status == "AUTH_EXPIRED":
                final_db_status = "AUTH_EXPIRED"
            elif status == "PARTIAL_SUCCESS":
                final_db_status = "PARTIAL"
            _db_update_extraction_run_counts(conn, run_id, status=final_db_status, error_message=message)
    except Exception as exc:
        _logger.warning("[FYERS][FINAL_RUN_STATUS_UPDATE_FAILED] run_id=%s message=%s error=%s", run_id, message, exc)


    processed_symbols = len(results)

    response: dict[str, Any] = {
        "ok": status not in {"FAILED"} and not auth_failed_detected,
        "stage": "single",
        "status": status,
        "cancelled": bool(stop_requested),
        "message": message,
        "resolution": resolution,
        "total_symbols": total_symbols,
        "success_count": success_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
        "success_trading_dates_count": success_trading_dates_total,
        "inserted_rows": inserted_rows_total,
        "updated_rows": updated_rows_total,
        "duplicate_rows_skipped": duplicate_rows_total,
        "existing_rows": existing_rows_total,
        "missing_ranges_count": missing_ranges_total,
        "missing_estimated_days": missing_estimated_days_total,
        "fetched_rows": fetched_rows_total,
        "skipped_existing_rows": duplicate_rows_total,
        "failed_ranges": failed_ranges_total,
        "remaining_ranges": len(failed_ranges_total),
        "api_time_seconds": round(api_time_seconds_total, 3),
        "db_time_seconds": round(db_time_seconds_total, 3),
        "results": results,
        "request": {
            "symbols": [item["normalized_symbol"] for item in symbol_rows],
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "resolution": resolution,
            "authorize": authorize_first,
        },
        "stats": {
            "total": total_symbols,
            "processed": processed_symbols,
            "inserted": success_count,
            "skipped": skipped_count,
            "failed": failed_count,
            "errors": failed_count,
            "inserted_rows": inserted_rows_total,
            "updated_rows": updated_rows_total,
            "duplicate_rows_skipped": duplicate_rows_total,
            "existing_rows": existing_rows_total,
            "missing_ranges_count": missing_ranges_total,
            "missing_estimated_days": missing_estimated_days_total,
            "fetched_rows": fetched_rows_total,
            "skipped_existing_rows": duplicate_rows_total,
            "failed_ranges": failed_ranges_total,
            "failed_ranges_count": len(failed_ranges_total),
            "remaining_ranges": len(failed_ranges_total),
            "api_time_seconds": round(api_time_seconds_total, 3),
            "db_time_seconds": round(db_time_seconds_total, 3),
            "success_trading_dates": success_trading_dates_total,
        },
        "details": {
            "fixed_resolution": resolution,
            "default_start_date": default_start.isoformat(),
            "source": FYERS_SOURCE,
            "source_mode": source_mode,
            "run_id": run_id,
            "stop_requested": bool(stop_requested),
            "existing_rows": existing_rows_total,
            "missing_ranges_count": missing_ranges_total,
            "missing_estimated_days": missing_estimated_days_total,
            "fetched_rows": fetched_rows_total,
            "inserted_rows": inserted_rows_total,
            "updated_rows": updated_rows_total,
            "skipped_existing_rows": duplicate_rows_total,
            "failed_ranges": failed_ranges_total,
            "remaining_ranges": len(failed_ranges_total),
            "api_time_seconds": round(api_time_seconds_total, 3),
            "db_time_seconds": round(db_time_seconds_total, 3),
            "auth_failed": bool(auth_failed_detected),
        },
    }
    if auth_payload is not None:
        response["authorization"] = {
            "ok": bool(auth_payload.get("ok")),
            "message": auth_payload.get("message"),
            "cached": bool(auth_payload.get("cached", False)),
            "authDate": auth_payload.get("authDate"),
        }
    if auth_failed_detected:
        response["authStatus"] = "EXPIRED"
        response["errorCode"] = "FYERS_AUTH_EXPIRED"
        response["shouldRetry"] = False
        response["requiresAuthorization"] = True
        response["authenticated"] = False
        response["canExtract"] = False
        response["uiMessage"] = FYERS_AUTH_REQUIRED_MESSAGE
        response["details"]["error_code"] = "FYERS_AUTH_EXPIRED"
        response["details"]["ui_message"] = FYERS_AUTH_REQUIRED_MESSAGE
        return response
    return _with_fyers_auth_success_metadata(response)


def fyers_run_batch(
    payload: dict[str, Any],
    line_logger: Optional[Callable[[str], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> dict[str, Any]:
    start_date = _parse_iso_date(payload.get("startDate") or payload.get("start_date"), "startDate")
    end_date = _parse_iso_date(payload.get("endDate") or payload.get("end_date"), "endDate")
    if end_date < start_date:
        raise ValueError("endDate cannot be earlier than startDate.")
    if not _date_range_has_weekday(start_date, end_date):
        raise ValueError("Weekend selected. Saturday and Sunday are market holidays.")

    resolution_raw = payload.get("resolution") or ""
    resolution = _normalize_resolution(resolution_raw) if str(resolution_raw or "").strip() else ""
    authorize_first = bool(payload.get("authorize", True))
    auth_payload = ensure_valid_fyers_auth(
        profile_validated_at=payload.get("_auth_prevalidated_at"),
    )
    if not auth_payload.get("ok"):
        auth_payload["stage"] = "batch"
        return auth_payload

    precheck_auth_failed, precheck_run_result = _run_fyers_history_auth_probe(
        start_date=start_date,
        end_date=end_date,
        resolution=resolution or FYERS_FIXED_RESOLUTION,
        line_logger=line_logger,
    )
    if precheck_auth_failed:
        project_dir = _resolve_fyers_project_dir()
        try:
            _mark_fyers_auth_failure(project_dir, "fyers_history_auth_probe_failed")
        except Exception:
            pass
        if line_logger:
            try:
                line_logger("[FYERS_AUTH_FAILED] token invalid/expired. Aborting batch before symbol loop.")
            except Exception:
                pass
        _logger.error("[FYERS_AUTH_FAILED] token invalid/expired. Aborting batch before symbol loop.")
        return _build_fyers_auth_failure_payload(
            "batch",
            FYERS_BATCH_AUTH_ERROR_MESSAGE,
            ui_message=FYERS_BATCH_AUTH_UI_MESSAGE,
            run_result=precheck_run_result,
        )

    project_dir = _resolve_fyers_project_dir()
    symbols = _load_fyers_batch_symbols(project_dir)
    if not symbols:
        raise ValueError("No symbols found in FYERS SYMBOLS_CSV.")
    if line_logger:
        try:
            line_logger(
                f"[INFO] FYERS direct batch started. symbols={len(symbols)} "
                f"start={start_date.isoformat()} end={end_date.isoformat()} file_storage=disabled"
            )
        except Exception:
            pass

    single_payload = {
        "symbol": ",".join(symbols),
        "startDate": start_date.isoformat(),
        "endDate": end_date.isoformat(),
        "resolution": resolution or FYERS_FIXED_RESOLUTION,
        "authorize": False,
        "sourceMode": "CSV_BATCH",
        "runId": str(payload.get("runId") or payload.get("run_id") or uuid.uuid4().hex),
    }
    single_result = fyers_run_single(single_payload, line_logger=line_logger, should_stop=should_stop)
    stats_payload = dict(single_result.get("stats") or {})
    details_payload = dict(single_result.get("details") or {})
    auth_failed = bool(details_payload.get("auth_failed")) or str(single_result.get("errorCode") or "") == "FYERS_AUTH_FAILED"
    stop_requested = bool(single_result.get("cancelled"))
    if auth_failed:
        try:
            _mark_fyers_auth_failure(project_dir, "fyers_history_auth_failure")
        except Exception:
            pass
        if line_logger:
            try:
                line_logger("[FYERS_AUTH_FAILED] authentication failed during fetch. Aborting remaining symbols.")
            except Exception:
                pass
        _logger.error("[FYERS_AUTH_FAILED] authentication failed during fetch. Aborting remaining symbols.")

    command_failed = auth_failed or bool(single_result.get("ok") is False and not stop_requested)
    inserted_count = max(_parse_int(stats_payload.get("inserted"), _parse_int(single_result.get("success_count"), 0)), 0)
    skipped_count = max(_parse_int(stats_payload.get("skipped"), _parse_int(single_result.get("skipped_count"), 0)), 0)
    failed_count = max(_parse_int(stats_payload.get("failed"), _parse_int(single_result.get("failed_count"), 0)), 0)
    errors_count = max(_parse_int(stats_payload.get("errors"), failed_count), 0)
    rows_loaded = max(_parse_int(stats_payload.get("inserted_rows"), _parse_int(single_result.get("inserted_rows"), 0)), 0)
    updated_rows = max(_parse_int(stats_payload.get("updated_rows"), _parse_int(single_result.get("updated_rows"), 0)), 0)
    existing_rows = max(_parse_int(stats_payload.get("existing_rows"), _parse_int(single_result.get("existing_rows"), 0)), 0)
    missing_ranges_count = max(_parse_int(stats_payload.get("missing_ranges_count"), _parse_int(single_result.get("missing_ranges_count"), 0)), 0)
    missing_estimated_days = max(_parse_int(stats_payload.get("missing_estimated_days"), _parse_int(single_result.get("missing_estimated_days"), 0)), 0)
    fetched_rows = max(_parse_int(stats_payload.get("fetched_rows"), _parse_int(single_result.get("fetched_rows"), 0)), 0)
    skipped_existing_rows = max(_parse_int(stats_payload.get("skipped_existing_rows"), _parse_int(single_result.get("skipped_existing_rows"), 0)), 0)
    remaining_ranges = max(_parse_int(stats_payload.get("remaining_ranges"), _parse_int(single_result.get("remaining_ranges"), 0)), 0)
    api_time_seconds = float(stats_payload.get("api_time_seconds") or single_result.get("api_time_seconds") or 0.0)
    db_time_seconds = float(stats_payload.get("db_time_seconds") or single_result.get("db_time_seconds") or 0.0)
    no_data = skipped_count
    incidents = failed_count
    remaining_quota = 0
    skipped_rejected_inserted = failed_count + skipped_count
    failed_symbols = _extract_fyers_terminal_failed_symbols(single_result)
    failed_ranges = list(stats_payload.get("failed_ranges") or details_payload.get("failed_ranges") or single_result.get("failed_ranges") or [])
    logs = {
        "command": ["direct-fyers-api"],
        "cwd": str(project_dir),
        "durationSeconds": 0,
        "timedOut": False,
        "stdoutTail": [
            f"Direct FYERS API batch completed. symbols={len(symbols)} inserted={inserted_count} skipped={skipped_count} failed={failed_count}",
        ],
        "stderrTail": [],
    }

    message = "Direct FYERS API batch run completed."
    if auth_failed:
        message = FYERS_BATCH_AUTH_ERROR_MESSAGE
    elif stop_requested:
        message = "Direct FYERS API batch run stopped safely after current symbol completed."
    elif command_failed:
        message = "Direct FYERS API batch run failed."
    elif failed_count > 0:
        message = "Direct FYERS API batch run completed with failed symbols."

    response: dict[str, Any] = {
        "ok": not command_failed,
        "stage": "batch",
        "status": "CANCELLED" if stop_requested else ("FAILED" if command_failed else "SUCCESS"),
        "cancelled": bool(stop_requested),
        "message": message,
        "uiMessage": FYERS_BATCH_AUTH_UI_MESSAGE if auth_failed else None,
        "failedSymbols": failed_symbols,
        "failed_symbols": failed_symbols,
        "request": {
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "resolution": resolution or None,
            "authorize": authorize_first,
        },
        "stats": {
            "total": len(symbols),
            "processed": _parse_int(stats_payload.get("processed"), len(symbols)),
            "inserted": inserted_count,
            "skipped": skipped_count,
            "failed": failed_count,
            "errors": errors_count,
            "rows_loaded": rows_loaded,
            "updated_rows": updated_rows,
            "existing_rows": existing_rows,
            "missing_ranges_count": missing_ranges_count,
            "missing_estimated_days": missing_estimated_days,
            "fetched_rows": fetched_rows,
            "skipped_existing_rows": skipped_existing_rows,
            "failed_ranges": failed_ranges,
            "failed_ranges_count": len(failed_ranges),
            "remaining_ranges": remaining_ranges,
            "api_time_seconds": round(api_time_seconds, 3),
            "db_time_seconds": round(db_time_seconds, 3),
            "no_data": no_data,
            "incidents": incidents,
            "remaining_quota": remaining_quota,
            "nifty500_total": len(symbols),
        },
        "details": {
            "returnCode": 0 if not command_failed else 1,
            "timedOut": False,
            "skip_reasons": {},
            "summary_csv": None,
            "summary_totals": {},
            "skipped_rejected_symbols_logged": skipped_rejected_inserted,
            "skipped_rejected_candidates": skipped_rejected_inserted,
            "file_storage": "disabled",
            "direct_api": True,
            "error_code": "FYERS_AUTH_FAILED" if auth_failed else None,
            "auth_failed": bool(auth_failed),
            "failed_symbols": failed_symbols,
            "failed_ranges": failed_ranges,
            "existing_rows": existing_rows,
            "missing_ranges_count": missing_ranges_count,
            "missing_estimated_days": missing_estimated_days,
            "fetched_rows": fetched_rows,
            "inserted_rows": rows_loaded,
            "updated_rows": updated_rows,
            "skipped_existing_rows": skipped_existing_rows,
            "remaining_ranges": remaining_ranges,
            "api_time_seconds": round(api_time_seconds, 3),
            "db_time_seconds": round(db_time_seconds, 3),
            "stop_requested": bool(stop_requested),
            "abort_reason": "FYERS_AUTH_REQUIRED" if auth_failed else (_FYERS_STOP_REQUEST_REASON if stop_requested else None),
            "ui_message": FYERS_BATCH_AUTH_UI_MESSAGE if auth_failed else None,
        },
        "logs": logs,
    }
    response["authStatus"] = "FAILED" if auth_failed else "VALID"
    response["errorCode"] = "FYERS_AUTH_FAILED" if auth_failed else None
    response["shouldRetry"] = False if auth_failed else False
    response["requiresAuthorization"] = bool(auth_failed)
    if auth_payload is not None:
        response["authorization"] = {
            "ok": bool(auth_payload.get("ok")),
            "message": auth_payload.get("message"),
            "cached": bool(auth_payload.get("cached", False)),
            "authDate": auth_payload.get("authDate"),
        }
    return _with_fyers_auth_success_metadata(response) if not auth_failed else response


def _existing_fyers_extraction_job_payload(stage: str, *, client_session_id: str = "") -> dict[str, Any] | None:
    if not _FYERS_JOBS_LOCK.acquire(timeout=FYERS_JOB_LOCK_TIMEOUT_SEC):
        return None
    try:
        _cleanup_fyers_jobs_locked(time.time())
        active_job = _find_active_fyers_job_locked_for_session(
            stages=_FYERS_SINGLE_FLIGHT_STAGES,
            client_session_id=client_session_id,
        )
        return _fyers_running_job_payload(active_job, requested_stage=stage) if active_job else None
    finally:
        _FYERS_JOBS_LOCK.release()


def _start_fyers_guarded_job(
    stage: str,
    payload: dict[str, Any],
    runner: Callable[[dict[str, Any], Optional[Callable[[str], None]], Optional[Callable[[], bool]]], dict[str, Any]],
) -> dict[str, Any]:
    client_session_id = _normalize_fyers_client_session_id(
        payload.get("clientSessionId") or payload.get("client_session_id")
    )
    if stage in _FYERS_SINGLE_FLIGHT_STAGES:
        existing = _existing_fyers_extraction_job_payload(stage, client_session_id=client_session_id)
        if existing:
            return existing
    auth_payload = ensure_valid_fyers_auth()
    if not auth_payload.get("ok"):
        return auth_payload
    runner_payload = dict(payload or {})
    runner_payload["_auth_prevalidated_at"] = time.time()
    return _run_fyers_job_async(stage, runner_payload, runner)


def fyers_start_single_job(payload: dict[str, Any]) -> dict[str, Any]:
    return _start_fyers_guarded_job("single", payload, fyers_run_single)


def fyers_start_batch_job(payload: dict[str, Any]) -> dict[str, Any]:
    return _start_fyers_guarded_job("batch", payload, fyers_run_batch)


def fyers_start_authorize_job(payload: dict[str, Any]) -> dict[str, Any]:
    force = bool(payload.get("force"))
    project_dir = _resolve_fyers_project_dir()
    today = _today_local_iso()
    if not force:
        auth_valid, state = _is_fyers_authenticated_today(project_dir)
        token_metadata = _read_fyers_token_metadata(project_dir)
        if auth_valid and bool(token_metadata.get("authenticated")):
            quick_payload = _build_fyers_already_authenticated_payload(
                today=today,
                state=state,
                token_metadata=token_metadata,
            )
            _write_cached_fyers_auth_status(_build_fyers_auth_status_payload(
                today=today,
                is_today=True,
                state=state,
                token_metadata=token_metadata,
                message=quick_payload["message"],
                source="authorize",
            ))
            return quick_payload
    if not _FYERS_JOBS_LOCK.acquire(timeout=FYERS_JOB_LOCK_TIMEOUT_SEC):
        return {
            "ok": False,
            "stage": "authorize",
            "status": "BUSY",
            "message": "FYERS authorization is busy. Please retry.",
        }
    try:
        _cleanup_fyers_jobs_locked(time.time())
        active_authorize_job = _find_active_fyers_job_locked(stages={"authorize"})
        if active_authorize_job:
            payload = _serialize_fyers_job(active_authorize_job)
            existing_job_id = str(payload.get("jobId") or "").strip()
            return {
                "ok": False,
                "jobId": existing_job_id,
                "job_id": existing_job_id,
                "runId": existing_job_id,
                "run_id": existing_job_id,
                "stage": "authorize",
                "status": "RUNNING",
                "done": False,
                "message": "FYERS authorization is already running. Reconnecting to the active authorization job.",
                "job": payload,
            }
    finally:
        _FYERS_JOBS_LOCK.release()
    started = _run_fyers_job_async("authorize", {"force": force}, fyers_run_authorize_job)
    started["status"] = "AUTH_URL_CREATED"
    started["message"] = "FYERS authorization started in background. Open the login URL from the Active Job panel when it appears."
    started["requiresAuthorization"] = True
    started["auth_url"] = None
    started["loginUrl"] = None
    return started


def fyers_start_failed_symbols_rerun_job(payload: dict[str, Any]) -> dict[str, Any]:
    return _start_fyers_guarded_job("failed-symbol-rerun", payload, rerun_fyers_failed_symbols)


def _in_memory_fyers_symbol_rows(job_id: str) -> tuple[str | None, list[dict[str, Any]]]:
    if not _FYERS_JOBS_LOCK.acquire(timeout=FYERS_JOB_LOCK_TIMEOUT_SEC):
        return None, []
    try:
        job = _FYERS_JOBS.get(job_id)
        if not job:
            return None, []
        trading_date = str(job.get("trading_date") or "").strip() or None
        result = job.get("result")
        result_rows = result.get("results") if isinstance(result, dict) else None
        if not isinstance(result_rows, list):
            return trading_date, []
        rows = []
        for item in result_rows:
            if not isinstance(item, dict):
                continue
            rows.append({
                "symbol": item.get("normalized_symbol") or item.get("symbol") or item.get("input_symbol"),
                "status": item.get("status"),
                "status_reason": item.get("error_code"),
                "retry_count": item.get("retry_count"),
                "error_message": item.get("error_message"),
                "trading_date": trading_date,
            })
        return trading_date, rows
    finally:
        _FYERS_JOBS_LOCK.release()


def _start_fyers_persisted_selection_job(
    payload: dict[str, Any],
    *,
    statuses: tuple[str, ...] | list[str] | set[str],
    stage: str,
) -> dict[str, Any]:
    client_session_id = _normalize_fyers_client_session_id(
        payload.get("clientSessionId") or payload.get("client_session_id")
    )
    source_job_id = str(
        payload.get("jobId")
        or payload.get("job_id")
        or payload.get("sourceJobId")
        or payload.get("source_job_id")
        or ""
    ).strip()
    if not source_job_id:
        raise ValueError("jobId is required.")
    existing = _existing_fyers_extraction_job_payload(stage, client_session_id=client_session_id)
    if existing:
        return existing
    auth_payload = ensure_valid_fyers_auth()
    if not auth_payload.get("ok"):
        return auth_payload
    allowed = {str(item or "").strip().upper() for item in statuses if str(item or "").strip()}
    trading_date: str | None = None
    rows: list[dict[str, Any]] = []
    try:
        rows = _load_fyers_symbol_rows(source_job_id, limit=2000)
        snapshot = _load_fyers_job_snapshot(source_job_id, include_symbols=False)
        if snapshot:
            trading_date = str(snapshot.get("tradingDate") or "").strip() or None
    except Exception as exc:
        _logger.warning("[FYERS][PERSISTED_SELECTION_READ_FAILED] job_id=%s stage=%s error=%s", source_job_id, stage, exc)
    if not rows:
        memory_date, rows = _in_memory_fyers_symbol_rows(source_job_id)
        trading_date = trading_date or memory_date
    selected_symbols: list[str] = []
    seen: set[str] = set()
    for row in rows:
        canonical = _canonical_fyers_symbol_status(
            row.get("status"),
            row.get("status_reason"),
            row.get("error_message"),
        )
        symbol = str(row.get("symbol") or "").strip()
        if canonical not in allowed or not symbol or symbol in seen:
            continue
        seen.add(symbol)
        selected_symbols.append(symbol)
        trading_date = trading_date or str(_fyers_json_value(row.get("trading_date")) or "").strip() or None
    if not selected_symbols:
        raise ValueError(f"No eligible FYERS symbols found for {stage}.")
    selected_date = str(
        payload.get("tradingDate")
        or payload.get("trading_date")
        or payload.get("endDate")
        or payload.get("end_date")
        or trading_date
        or ""
    ).strip()
    if not selected_date:
        raise ValueError("tradingDate is required.")
    runner_payload = {
        "symbol": ",".join(selected_symbols),
        "startDate": selected_date,
        "endDate": selected_date,
        "authorize": bool(payload.get("authorize", True)),
        "sourceMode": "SINGLE_STOCK_RERUN",
        "sourceJobId": source_job_id,
        "_auth_prevalidated_at": time.time(),
        "clientSessionId": client_session_id or None,
    }
    return _run_fyers_job_async(stage, runner_payload, fyers_run_single)


def fyers_resume_job(payload: dict[str, Any]) -> dict[str, Any]:
    return _start_fyers_persisted_selection_job(
        payload,
        statuses=("PENDING", "RUNNING", "STOPPED", "FAILED", "INVALID", "ERROR"),
        stage="resume",
    )


def fyers_rerun_failed_job(payload: dict[str, Any]) -> dict[str, Any]:
    return _start_fyers_persisted_selection_job(
        payload,
        statuses=("FAILED", "INVALID", "ERROR"),
        stage="rerun-failed",
    )


def fyers_rerun_remaining_job(payload: dict[str, Any]) -> dict[str, Any]:
    return _start_fyers_persisted_selection_job(
        payload,
        statuses=("PENDING", "RUNNING", "STOPPED"),
        stage="rerun-remaining",
    )


def fyers_get_skipped_symbols(job_id: str) -> dict[str, Any]:
    jid = str(job_id or "").strip()
    if not jid:
        raise ValueError("jobId is required.")
    trading_date: str | None = None
    try:
        rows = _load_fyers_symbol_rows(jid, limit=2000)
        snapshot = _load_fyers_job_snapshot(jid, include_symbols=False)
        if snapshot:
            trading_date = str(snapshot.get("tradingDate") or "").strip() or None
    except Exception as exc:
        _logger.warning("[FYERS][SKIPPED_SYMBOL_READ_FAILED] job_id=%s error=%s", jid, exc)
        trading_date, rows = _in_memory_fyers_symbol_rows(jid)
    symbols = [
        _build_fyers_symbol_payload(row, trading_date=trading_date)
        for row in rows
        if _canonical_fyers_symbol_status(
            row.get("status"),
            row.get("status_reason"),
            row.get("error_message"),
        ) in _FYERS_ACTIONABLE_SKIPPED_STATUSES
    ]
    return {
        "ok": True,
        "jobId": jid,
        "job_id": jid,
        "tradingDate": trading_date,
        "total": len(symbols),
        "symbols": symbols,
    }


def fyers_rerun_failed_symbols_compat(
    payload: dict[str, Any],
    *,
    max_wait_seconds: int = 105,
    poll_interval_seconds: float = 1.5,
) -> dict[str, Any]:
    started = fyers_start_failed_symbols_rerun_job(payload)
    job_id = str(started.get("jobId") or "").strip()
    if not job_id:
        return started

    wait_budget = max(0, min(int(max_wait_seconds), 115))
    poll_interval = max(0.25, min(float(poll_interval_seconds), 5.0))
    deadline = time.time() + wait_budget
    last_snapshot: dict[str, Any] = {
        "jobId": job_id,
        "status": "running",
        "done": False,
        "message": "Re-run is running in background.",
        "stats": {"inserted": 0, "skipped": 0, "failed": 0, "errors": 0},
        "logs": {"tail": [], "totalLines": 0},
    }

    while time.time() < deadline:
        snapshot = fyers_get_job(job_id, tail_lines=260)
        last_snapshot = snapshot if isinstance(snapshot, dict) else last_snapshot
        status_token = str(last_snapshot.get("status") or "").strip().lower()
        done = bool(last_snapshot.get("done")) or status_token in _FYERS_TERMINAL_JOB_STATUSES
        if done:
            result_payload = last_snapshot.get("result")
            if isinstance(result_payload, dict):
                return result_payload
            return {
                "ok": bool(last_snapshot.get("ok")),
                "stage": "failed-symbol-rerun",
                "status": str(last_snapshot.get("status") or "").upper() or "UNKNOWN",
                "message": str(last_snapshot.get("message") or "Re-run completed."),
                "stats": last_snapshot.get("stats") or {"inserted": 0, "skipped": 0, "failed": 0, "errors": 0},
                "details": {
                    "jobId": job_id,
                },
                "logs": last_snapshot.get("logs") or {"tail": [], "totalLines": 0},
            }
        time.sleep(poll_interval)

    running_stats = last_snapshot.get("stats")
    if not isinstance(running_stats, dict):
        running_stats = {}
    running_logs = last_snapshot.get("logs")
    if not isinstance(running_logs, dict):
        running_logs = {"tail": [], "totalLines": 0}
    return {
        "ok": True,
        "stage": "failed-symbol-rerun",
        "status": "RUNNING",
        "message": "Re-run is still running in background. Please refresh logs.",
        "stats": {
            "processed": _parse_int(running_stats.get("processed"), 0),
            "inserted": _parse_int(running_stats.get("inserted"), 0),
            "skipped": _parse_int(running_stats.get("skipped"), 0),
            "failed": _parse_int(running_stats.get("failed"), 0),
            "deletedSuccessRows": _parse_int(running_stats.get("deletedSuccessRows"), 0),
        },
        "details": {
            "jobId": job_id,
            "deferred": True,
        },
        "logs": running_logs,
    }
