from __future__ import annotations

import datetime as dt
import logging
import os
import re
import time
from decimal import Decimal
from typing import Any, Iterable, Literal

try:
    from ..config import settings
    from ..db_pool import pool
except ImportError:  # pragma: no cover
    from config import settings  # type: ignore
    from db_pool import pool  # type: ignore


_logger = logging.getLogger(__name__)

SOURCE_TABLE = "NSE_NIFTY500_DAILY_RAW_DATA_DEV"
VALID_TIMEFRAMES = ("daily", "weekly", "monthly")

_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]*(?:\.[A-Za-z][A-Za-z0-9_$#]*)?$")
_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9.&_-]{0,49}$")
_GREEN_VOLUME = "rgba(34,197,94,0.45)"
_RED_VOLUME = "rgba(239,68,68,0.45)"
_WATCHLIST_CACHE: dict[str, Any] = {"expires_at": 0.0, "payload": None}


def _watchlist_cache_ttl_seconds() -> int:
    try:
        return max(0, int(str(os.getenv("CHART_WATCHLIST_CACHE_TTL_SECONDS", "300")).strip()))
    except Exception:
        return 300


def _clone_watchlist_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "total_symbols": payload.get("total_symbols", 0),
        "latest_trade_date": payload.get("latest_trade_date"),
        "rows": [dict(item) for item in payload.get("rows", []) if isinstance(item, dict)],
    }


class InvalidChartParameter(ValueError):
    """Raised when chart request parameters are invalid."""


def _safe_identifier(value: str) -> str:
    token = str(value or "").strip()
    if not token or not _IDENTIFIER_RE.fullmatch(token):
        raise RuntimeError(f"Invalid SQL identifier configured: {value!r}")
    return token


def _table_sql() -> str:
    schema = str(os.getenv("ORACLE_SCHEMA") or "").strip()
    table = _safe_identifier(SOURCE_TABLE)
    if not schema:
        return table
    return f"{_safe_identifier(schema)}.{table}"


def normalize_chart_symbol(value: Any) -> str:
    token = re.sub(r"\s+", "", str(value or "").strip().upper())
    if not token:
        raise InvalidChartParameter("symbol is required")
    token = re.sub(r"^(NSE|BSE):", "", token, flags=re.IGNORECASE)
    token = re.sub(r"(:EQ|-EQ)$", "", token, flags=re.IGNORECASE)
    if not token or not _SYMBOL_RE.fullmatch(token):
        raise InvalidChartParameter("symbol must be a valid NSE symbol")
    return token


def normalize_timeframe(value: Any) -> Literal["daily", "weekly", "monthly"]:
    token = str(value or "daily").strip().lower()
    if token not in VALID_TIMEFRAMES:
        raise InvalidChartParameter("timeframe must be one of daily, weekly, monthly")
    return token  # type: ignore[return-value]


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(str(value).replace(",", "").strip())
    except Exception:
        return None


def _to_int(value: Any) -> int:
    num = _to_float(value)
    if num is None:
        return 0
    try:
        return int(round(num))
    except Exception:
        return 0


def _to_optional_int(value: Any) -> int | None:
    num = _to_float(value)
    if num is None:
        return None
    try:
        return int(round(num))
    except Exception:
        return None


def _round_optional(value: Any, digits: int = 2) -> float | None:
    num = _to_float(value)
    if num is None:
        return None
    return round(num, digits)


def _date_to_iso(value: Any) -> str | None:
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", text)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return text[:10]


def _pick_column(columns: Iterable[str], candidates: tuple[str, ...]) -> str | None:
    lookup = {str(col).upper(): str(col).upper() for col in columns}
    for candidate in candidates:
        key = candidate.upper()
        if key in lookup:
            return lookup[key]
    return None


def _normalized_symbol_expr(column: str) -> str:
    return (
        "UPPER(TRIM(REGEXP_REPLACE("
        "REGEXP_REPLACE("
        "REGEXP_REPLACE(TRIM("
        f"{column}"
        "), '^(NSE|BSE):', '', 1, 0, 'i'), "
        "'(:EQ|-EQ)$', '', 1, 0, 'i'), "
        "'[[:space:]]+', '')))"
    )


def _fast_normalized_symbol_expr(column: str) -> str:
    return (
        "REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE("
        f"UPPER(TRIM({column}))"
        ", 'NSE:', ''), 'BSE:', ''), ':EQ', ''), '-EQ', ''), ' ', ''), CHR(9), '')"
    )


def _resolve_columns(conn, table_sql: str) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT * FROM {table_sql} WHERE ROWNUM = 0")
        return {str(col[0]).upper() for col in (cur.description or []) if col and col[0]}


def _resolve_projection(conn) -> dict[str, str | None]:
    table = _table_sql()
    columns = _resolve_columns(conn, table)
    symbol_col = _pick_column(columns, ("SYMBOL", "STOCK", "TICKER", "SECURITY"))
    date_col = _pick_column(columns, ("TRADING_DATE", "TRADE_DATE", "LTC_DATE", "DATE"))
    open_col = _pick_column(columns, ("OPEN", "OPEN_PRICE", "O"))
    high_col = _pick_column(columns, ("HIGH", "HIGH_PRICE", "H", "DAY_HIGH"))
    low_col = _pick_column(columns, ("LOW", "LOW_PRICE", "L", "DAY_LOW"))
    close_col = _pick_column(
        columns,
        (
            "PREVIOUS_CLOSE",
            "CLOSE_PRICE",
            "CLOSE",
            "ADJ_CLOSE",
            "LTP",
            "LAST_PRICE",
            "CLOSING_PRICE",
            "CLOSEVALUE",
        ),
    )
    volume_col = _pick_column(columns, ("VOLUME", "TOTTRDQTY", "TOT_TRDQTY", "TOTAL_TRADED_QTY", "QTY"))
    week_bucket_col = _pick_column(columns, ("WEEK_BUCKET",))
    month_bucket_col = _pick_column(columns, ("MONTH_BUCKET",))

    missing = []
    if not symbol_col:
        missing.append("SYMBOL")
    if not date_col:
        missing.append("TRADING_DATE")
    if not open_col:
        missing.append("OPEN")
    if not high_col:
        missing.append("HIGH")
    if not low_col:
        missing.append("LOW")
    if not close_col:
        missing.append("PREVIOUS_CLOSE/CLOSE_PRICE")
    if missing:
        raise RuntimeError(f"Chart source table is missing required columns: {', '.join(missing)}")

    return {
        "table": table,
        "symbol_col": symbol_col,
        "date_col": date_col,
        "open_col": open_col,
        "high_col": high_col,
        "low_col": low_col,
        "close_col": close_col,
        "volume_col": volume_col,
        "week_bucket_col": week_bucket_col,
        "month_bucket_col": month_bucket_col,
    }


def _build_daily_sql(projection: dict[str, str | None], symbol_predicate: str) -> str:
    table = projection["table"]
    symbol_col = projection["symbol_col"]
    date_col = projection["date_col"]
    open_col = projection["open_col"]
    high_col = projection["high_col"]
    low_col = projection["low_col"]
    close_col = projection["close_col"]
    volume_col = projection["volume_col"] or "NULL"
    return f"""
SELECT
    TO_CHAR({date_col}, 'YYYY-MM-DD') AS TIME,
    {open_col} AS OPEN_VAL,
    {high_col} AS HIGH_VAL,
    {low_col} AS LOW_VAL,
    {close_col} AS CLOSE_VAL,
    {volume_col} AS VOLUME_VAL
FROM {table}
WHERE {symbol_predicate}
  AND {date_col} IS NOT NULL
  AND {open_col} IS NOT NULL
  AND {high_col} IS NOT NULL
  AND {low_col} IS NOT NULL
  AND {close_col} IS NOT NULL
ORDER BY {date_col} ASC
"""


def _bucket_expr(projection: dict[str, str | None], timeframe: str) -> str:
    date_col = projection["date_col"]
    if timeframe == "weekly":
        return projection["week_bucket_col"] or f"TRUNC({date_col}, 'IW')"
    return projection["month_bucket_col"] or f"TRUNC({date_col}, 'MM')"


def _build_aggregate_sql(projection: dict[str, str | None], timeframe: str, symbol_predicate: str) -> str:
    table = projection["table"]
    symbol_col = projection["symbol_col"]
    date_col = projection["date_col"]
    open_col = projection["open_col"]
    high_col = projection["high_col"]
    low_col = projection["low_col"]
    close_col = projection["close_col"]
    volume_col = projection["volume_col"]
    volume_expr = f"SUM(NVL({volume_col}, 0))" if volume_col else "CAST(0 AS NUMBER)"
    bucket = _bucket_expr(projection, timeframe)
    return f"""
SELECT
    TO_CHAR(PERIOD_START, 'YYYY-MM-DD') AS TIME,
    OPEN_VAL,
    HIGH_VAL,
    LOW_VAL,
    CLOSE_VAL,
    VOLUME_VAL
FROM (
    SELECT
        {bucket} AS PERIOD_START,
        MAX({open_col}) KEEP (DENSE_RANK FIRST ORDER BY {date_col} ASC) AS OPEN_VAL,
        MAX({high_col}) AS HIGH_VAL,
        MIN({low_col}) AS LOW_VAL,
        MAX({close_col}) KEEP (DENSE_RANK LAST ORDER BY {date_col} ASC) AS CLOSE_VAL,
        {volume_expr} AS VOLUME_VAL
    FROM {table}
    WHERE {symbol_predicate}
      AND {date_col} IS NOT NULL
      AND {open_col} IS NOT NULL
      AND {high_col} IS NOT NULL
      AND {low_col} IS NOT NULL
      AND {close_col} IS NOT NULL
    GROUP BY {bucket}
)
ORDER BY PERIOD_START ASC
"""


def _watchlist_symbol_expr(symbol_col: str) -> str:
    return f"NULLIF(UPPER(TRIM({symbol_col})), '')"


def _build_watchlist_symbols_sql(projection: dict[str, str | None]) -> str:
    table = projection["table"]
    symbol_col = str(projection["symbol_col"])
    close_col = projection["close_col"]
    normalized_symbol = _watchlist_symbol_expr(symbol_col)
    return f"""
SELECT DISTINCT
    {normalized_symbol} AS SYMBOL_VAL
FROM {table}
WHERE {symbol_col} IS NOT NULL
  AND {close_col} IS NOT NULL
  AND {normalized_symbol} IS NOT NULL
ORDER BY SYMBOL_VAL
"""


def _build_watchlist_current_sql(projection: dict[str, str | None]) -> str:
    table = projection["table"]
    symbol_col = str(projection["symbol_col"])
    date_col = projection["date_col"]
    close_col = projection["close_col"]
    volume_col = projection["volume_col"]
    normalized_symbol = _watchlist_symbol_expr(symbol_col)
    volume_expr = volume_col or "CAST(NULL AS NUMBER)"
    return f"""
WITH market_dates AS (
    SELECT
        MAX({date_col}) AS LATEST_DATE,
        MAX(CASE
            WHEN {date_col} < (
                SELECT MAX({date_col})
                FROM {table}
                WHERE {date_col} IS NOT NULL
                  AND {close_col} IS NOT NULL
            )
            THEN {date_col}
            ELSE NULL
        END) AS PREVIOUS_DATE
    FROM {table}
    WHERE {date_col} IS NOT NULL
      AND {close_col} IS NOT NULL
),
latest AS (
    SELECT
        {normalized_symbol} AS SYMBOL_VAL,
        {date_col} AS TRADING_DATE,
        {close_col} AS LAST_PRICE,
        {volume_expr} AS VOLUME_VAL
    FROM {table}, market_dates
    WHERE {symbol_col} IS NOT NULL
      AND {date_col} = market_dates.LATEST_DATE
      AND {close_col} IS NOT NULL
),
prev_rows AS (
    SELECT
        {normalized_symbol} AS SYMBOL_VAL,
        {close_col} AS PREV_CLOSE
    FROM {table}, market_dates
    WHERE {symbol_col} IS NOT NULL
      AND {date_col} = market_dates.PREVIOUS_DATE
      AND {close_col} IS NOT NULL
)
SELECT
    latest.SYMBOL_VAL AS SYMBOL,
    TO_CHAR(latest.TRADING_DATE, 'YYYY-MM-DD') AS TRADING_DATE,
    latest.LAST_PRICE AS LAST_PRICE,
    prev_rows.PREV_CLOSE AS PREV_CLOSE,
    CASE
        WHEN latest.LAST_PRICE IS NOT NULL AND prev_rows.PREV_CLOSE IS NOT NULL
        THEN latest.LAST_PRICE - prev_rows.PREV_CLOSE
        ELSE NULL
    END AS CHANGE_VAL,
    CASE
        WHEN latest.LAST_PRICE IS NOT NULL
         AND prev_rows.PREV_CLOSE IS NOT NULL
         AND prev_rows.PREV_CLOSE <> 0
        THEN ROUND(((latest.LAST_PRICE - prev_rows.PREV_CLOSE) / prev_rows.PREV_CLOSE) * 100, 2)
        ELSE NULL
    END AS CHANGE_PERCENT,
    latest.VOLUME_VAL AS VOLUME_VAL,
    TO_CHAR((SELECT LATEST_DATE FROM market_dates), 'YYYY-MM-DD') AS LATEST_TRADE_DATE
FROM latest
LEFT JOIN prev_rows
    ON prev_rows.SYMBOL_VAL = latest.SYMBOL_VAL
WHERE latest.SYMBOL_VAL IS NOT NULL
ORDER BY latest.SYMBOL_VAL
"""


def _build_watchlist_symbol_history_sql(projection: dict[str, str | None]) -> str:
    table = projection["table"]
    symbol_col = str(projection["symbol_col"])
    date_col = projection["date_col"]
    close_col = projection["close_col"]
    volume_col = projection["volume_col"]
    normalized_symbol = _watchlist_symbol_expr(symbol_col)
    volume_expr = volume_col or "CAST(NULL AS NUMBER)"
    return f"""
SELECT
    SYMBOL_VAL AS SYMBOL,
    TO_CHAR(TRADING_DATE, 'YYYY-MM-DD') AS TRADING_DATE,
    LAST_PRICE AS LAST_PRICE,
    PREV_CLOSE AS PREV_CLOSE,
    CASE
        WHEN LAST_PRICE IS NOT NULL AND PREV_CLOSE IS NOT NULL
        THEN LAST_PRICE - PREV_CLOSE
        ELSE NULL
    END AS CHANGE_VAL,
    CASE
        WHEN LAST_PRICE IS NOT NULL
         AND PREV_CLOSE IS NOT NULL
         AND PREV_CLOSE <> 0
        THEN ROUND(((LAST_PRICE - PREV_CLOSE) / PREV_CLOSE) * 100, 2)
        ELSE NULL
    END AS CHANGE_PERCENT,
    VOLUME_VAL AS VOLUME_VAL,
    TO_CHAR(TRADING_DATE, 'YYYY-MM-DD') AS LATEST_TRADE_DATE
FROM (
    SELECT
        {normalized_symbol} AS SYMBOL_VAL,
        {date_col} AS TRADING_DATE,
        {close_col} AS LAST_PRICE,
        {volume_expr} AS VOLUME_VAL,
        LAG({close_col}) OVER (ORDER BY {date_col} ASC) AS PREV_CLOSE,
        ROW_NUMBER() OVER (ORDER BY {date_col} DESC) AS RN
    FROM {table}
    WHERE {symbol_col} = :symbol
      AND {date_col} IS NOT NULL
      AND {close_col} IS NOT NULL
)
WHERE RN = 1
"""


def _iter_rows(cursor) -> Iterable[tuple]:
    cursor.arraysize = max(500, int(getattr(settings, "oracle_arraysize", 500)))
    cursor.prefetchrows = cursor.arraysize
    return cursor


def _append_payload_row(candles: list[dict[str, Any]], volumes: list[dict[str, Any]], row: tuple[Any, ...]) -> None:
    row_time = _date_to_iso(row[0])
    open_val = _to_float(row[1])
    high_val = _to_float(row[2])
    low_val = _to_float(row[3])
    close_val = _to_float(row[4])
    if not row_time or open_val is None or high_val is None or low_val is None or close_val is None:
        return
    candles.append({
        "time": row_time,
        "open": open_val,
        "high": high_val,
        "low": low_val,
        "close": close_val,
    })
    volumes.append({
        "time": row_time,
        "value": _to_int(row[5] if len(row) > 5 else None),
        "color": _GREEN_VOLUME if close_val >= open_val else _RED_VOLUME,
    })


def _query_series(
    conn,
    projection: dict[str, str | None],
    timeframe: str,
    symbol_predicate: str,
    normalized_symbol: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sql = _build_daily_sql(projection, symbol_predicate) if timeframe == "daily" else _build_aggregate_sql(projection, timeframe, symbol_predicate)
    with conn.cursor() as cur:
        cur.execute(sql, {"symbol": normalized_symbol})
        candles: list[dict[str, Any]] = []
        volume: list[dict[str, Any]] = []
        for row in _iter_rows(cur):
            _append_payload_row(candles, volume, row)
    return candles, volume


def fetch_ohlcv_payload(symbol: Any, timeframe: Any = "daily") -> dict[str, Any]:
    normalized_symbol = normalize_chart_symbol(symbol)
    normalized_timeframe = normalize_timeframe(timeframe)
    started = time.perf_counter()

    with pool.acquire() as conn:
        projection = _resolve_projection(conn)
        strict_predicate = f"{projection['symbol_col']} = :symbol"
        candles, volume = _query_series(conn, projection, normalized_timeframe, strict_predicate, normalized_symbol)
        symbol_match_mode = "strict"
        if not candles:
            normalized_predicate = f"{_normalized_symbol_expr(str(projection['symbol_col']))} = :symbol"
            candles, volume = _query_series(conn, projection, normalized_timeframe, normalized_predicate, normalized_symbol)
            symbol_match_mode = "normalized"

    latest_date = candles[-1]["time"] if candles else None
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    _logger.info(
        "[CHART_OHLCV] status=ok symbol=%s timeframe=%s total_candles=%s latest_date=%s duration_ms=%s source_table=%s symbol_match=%s",
        normalized_symbol,
        normalized_timeframe,
        len(candles),
        latest_date,
        elapsed_ms,
        SOURCE_TABLE,
        symbol_match_mode,
    )
    return {
        "symbol": normalized_symbol,
        "timeframe": normalized_timeframe,
        "latest_date": latest_date,
        "total_candles": len(candles),
        "candles": candles,
        "volume": volume,
    }


def _watchlist_row_to_payload(row: tuple[Any, ...]) -> tuple[dict[str, Any] | None, str | None]:
    symbol = str(row[0] or "").strip().upper()
    if not symbol:
        return None, None
    item = {
        "symbol": symbol,
        "last": _round_optional(row[2]),
        "change": _round_optional(row[4]),
        "change_percent": _round_optional(row[5]),
        "volume": _to_optional_int(row[6] if len(row) > 6 else None),
        "trading_date": _date_to_iso(row[1]),
    }
    return item, _date_to_iso(row[7] if len(row) > 7 else None)


def fetch_watchlist_payload() -> dict[str, Any]:
    started = time.perf_counter()
    cache_ttl_seconds = _watchlist_cache_ttl_seconds()
    cached_payload = _WATCHLIST_CACHE.get("payload")
    if cache_ttl_seconds > 0 and isinstance(cached_payload, dict) and time.time() < float(_WATCHLIST_CACHE.get("expires_at") or 0):
        _logger.info(
            "[CHART_WATCHLIST] status=cache_hit total_symbols=%s latest_trade_date=%s source_table=%s",
            cached_payload.get("total_symbols", 0),
            cached_payload.get("latest_trade_date"),
            SOURCE_TABLE,
        )
        return _clone_watchlist_payload(cached_payload)

    rows: list[dict[str, Any]] = []
    latest_trade_date: str | None = None
    all_symbols: list[str] = []
    missing_symbols: list[str] = []

    with pool.acquire() as conn:
        projection = _resolve_projection(conn)
        symbols_sql = _build_watchlist_symbols_sql(projection)
        current_sql = _build_watchlist_current_sql(projection)
        fallback_sql = _build_watchlist_symbol_history_sql(projection)
        with conn.cursor() as cur:
            cur.execute(symbols_sql)
            all_symbols = [str(row[0] or "").strip().upper() for row in _iter_rows(cur) if row and row[0]]

            cur.execute(current_sql)
            for row in _iter_rows(cur):
                item, query_latest_date = _watchlist_row_to_payload(row)
                if not item:
                    continue
                if not latest_trade_date and query_latest_date:
                    latest_trade_date = query_latest_date
                rows.append(item)

            row_symbols = {item["symbol"] for item in rows}
            missing_symbols = [symbol for symbol in all_symbols if symbol and symbol not in row_symbols]
            for symbol in missing_symbols:
                cur.execute(fallback_sql, {"symbol": symbol})
                for row in _iter_rows(cur):
                    item, query_latest_date = _watchlist_row_to_payload(row)
                    if not item:
                        continue
                    if not latest_trade_date and query_latest_date:
                        latest_trade_date = query_latest_date
                    rows.append(item)
                    break

    rows.sort(key=lambda item: str(item.get("symbol") or ""))

    if not latest_trade_date:
        dated_rows = [item["trading_date"] for item in rows if item.get("trading_date")]
        latest_trade_date = max(dated_rows) if dated_rows else None

    missing_latest = [item["symbol"] for item in rows if item.get("last") is None]
    missing_previous = [item["symbol"] for item in rows if item.get("last") is not None and item.get("change") is None]
    missing_volume = [item["symbol"] for item in rows if item.get("volume") is None]
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    _logger.info(
        "[CHART_WATCHLIST] status=ok total_symbols=%s latest_trade_date=%s rows_returned=%s "
        "fallback_symbols=%s missing_latest=%s missing_previous=%s missing_volume=%s duration_ms=%s source_table=%s",
        len(all_symbols) or len(rows),
        latest_trade_date,
        len(rows),
        len(missing_symbols),
        len(missing_latest),
        len(missing_previous),
        len(missing_volume),
        elapsed_ms,
        SOURCE_TABLE,
    )
    if missing_latest or missing_previous:
        _logger.warning(
            "[CHART_WATCHLIST] missing_data missing_latest_sample=%s missing_previous_sample=%s",
            ",".join(missing_latest[:25]) or "-",
            ",".join(missing_previous[:25]) or "-",
        )

    payload = {
        "total_symbols": len(all_symbols) or len(rows),
        "latest_trade_date": latest_trade_date,
        "rows": rows,
    }
    if cache_ttl_seconds > 0:
        _WATCHLIST_CACHE["payload"] = _clone_watchlist_payload(payload)
        _WATCHLIST_CACHE["expires_at"] = time.time() + cache_ttl_seconds
    return payload
