from __future__ import annotations

import datetime as dt
import csv
import io
import json
import logging
import math
import os
import re
import time
import zipfile
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Sequence

try:
    from ..cache import TTLCache
    from ..db_pool import fetchall_dict, pool
except ImportError:  # pragma: no cover
    from cache import TTLCache  # type: ignore
    from db_pool import fetchall_dict, pool  # type: ignore

_logger = logging.getLogger(__name__)

ALLOWED_TABLES: tuple[str, ...] = (
    "NSE_NIFTY500_DAILY_RAW_DATA_DEV",
    "NSE_NIFTY500_DAILY_RAW_DATA_ORACLE",
)
DEFAULT_TABLE = ALLOWED_TABLES[0]
PAGE_SIZE_OPTIONS: tuple[int, ...] = (25, 50, 100, 250, 500)
DEFAULT_PAGE_SIZE = 50
SUMMARY_PAGE_SIZE = 25
DETAIL_PAGE_SIZE = 25
CSV_HEADERS: tuple[str, ...] = ("s.no", "symbol", "trade_date", "open", "high", "low", "close", "volume")
SUMMARY_CACHE_TTL_SECONDS = max(1, int(os.getenv("HISTORICAL_SUMMARY_CACHE_TTL_SECONDS", "1800")))
SUMMARY_CACHE_MAX_ITEMS = max(1, int(os.getenv("HISTORICAL_SUMMARY_CACHE_MAX_ITEMS", "128")))
SUMMARY_CACHE_MAX_MEMORY_MB = max(1, int(os.getenv("HISTORICAL_SUMMARY_CACHE_MAX_MEMORY_MB", "64")))
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_.$#]+$")
_SUMMARY_CACHE = TTLCache(
    ttl_seconds=SUMMARY_CACHE_TTL_SECONDS,
    max_items=SUMMARY_CACHE_MAX_ITEMS,
    max_bytes=SUMMARY_CACHE_MAX_MEMORY_MB * 1024 * 1024,
)

TABLE_METADATA: dict[str, dict[str, Any]] = {
    "NSE_NIFTY500_DAILY_RAW_DATA_DEV": {
        "view_name": "VW_HISTORICAL_DATA_DEV",
        "delete_table": "NSE_NIFTY500_DAILY_RAW_DATA_DEV",
        "delete_symbol_col": "SYMBOL",
        "detail_columns": [
            {"key": "symbol", "label": "Symbol"},
            {"key": "trading_date", "label": "Trading Date"},
            {"key": "open", "label": "Open"},
            {"key": "high", "label": "High"},
            {"key": "low", "label": "Low"},
            {"key": "close_price", "label": "Close Price"},
            {"key": "volume", "label": "Volume"},
        ],
    },
    "NSE_NIFTY500_DAILY_RAW_DATA_ORACLE": {
        "view_name": "VW_HISTORICAL_DATA_ORACLE",
        "delete_table": "NSE_NIFTY500_DAILY_RAW_DATA_ORACLE",
        "delete_symbol_col": "SYMBOL",
        "detail_columns": [
            {"key": "symbol", "label": "Symbol"},
            {"key": "trading_date", "label": "Trading Date"},
            {"key": "open", "label": "Open"},
            {"key": "high", "label": "High"},
            {"key": "low", "label": "Low"},
            {"key": "close_price", "label": "Close Price"},
            {"key": "volume", "label": "Volume"},
        ],
    },
}

SUMMARY_SELECT_COLUMNS = (
    "s.SYMBOL AS SYMBOL",
    "s.TRADING_DAYS AS TRADING_DAYS",
    "s.IPO_DATE AS IPO_DATE",
    "s.IPO_PRICE AS IPO_PRICE",
    "s.PRICE AS PRICE",
    "s.LATEST_TRADING_DATE AS TRADE_DATE",
    "s.ATH AS ATH",
    "s.ATH_DATE AS ATH_DATE",
    "s.EXISTING AS EXISTING",
)


def list_allowed_tables() -> list[str]:
    return list(ALLOWED_TABLES)


def _safe_identifier(value: str) -> str:
    token = str(value or "").strip()
    if not token or not _IDENTIFIER_RE.match(token):
        raise ValueError(f"Invalid SQL identifier: {value!r}")
    return token


def _table_sql(table_name: str) -> str:
    table_token = _safe_identifier(table_name)
    schema = str(os.getenv("ORACLE_SCHEMA") or "").strip()
    if not schema:
        return table_token
    return f"{_safe_identifier(schema)}.{table_token}"


def _view_sql(table_name: str) -> str:
    metadata = TABLE_METADATA[table_name]
    return _table_sql(str(metadata["view_name"]))


def _to_json_value(value: Any) -> Any:
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _to_export_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    return _to_json_value(value)


def _to_json_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for row in rows:
        payload.append({key: _to_json_value(value) for key, value in dict(row).items()})
    return payload


def _parse_date(value: Any, field_name: str) -> dt.date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return dt.datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{field_name} must be in YYYY-MM-DD format.") from exc


def _parse_int(value: Any, field_name: str, *, minimum: int | None = None) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = int(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an integer.") from exc
    if minimum is not None and parsed < minimum:
        raise ValueError(f"{field_name} must be greater than or equal to {minimum}.")
    return parsed


def _parse_float(value: Any, field_name: str) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid number.") from exc


def _normalize_page(value: Any) -> int:
    parsed = _parse_int(value, "page", minimum=1)
    return parsed or 1


def _normalize_page_size(value: Any) -> int:
    parsed = _parse_int(value, "page_size", minimum=1)
    if parsed is None:
        return DEFAULT_PAGE_SIZE
    if parsed in PAGE_SIZE_OPTIONS:
        return parsed
    return DEFAULT_PAGE_SIZE


def _normalize_sort_order(value: Any) -> str:
    token = str(value or "DESC").strip().upper()
    return "ASC" if token == "ASC" else "DESC"


def _validate_table_name(raw_table_name: Any) -> str:
    token = str(raw_table_name or DEFAULT_TABLE).strip().upper()
    if token not in TABLE_METADATA:
        _logger.warning("[HISTORICAL_DATA][WARN] invalid table rejected=%s", raw_table_name)
        raise ValueError("Invalid table selected")
    return token


def _normalize_symbols(values: Sequence[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw in values:
        symbol = str(raw or "").strip().upper()
        if not symbol:
            continue
        if symbol in seen:
            continue
        seen.add(symbol)
        output.append(symbol)
    return output


def _normalize_dates(values: Sequence[Any], *, field_name: str) -> list[dt.date]:
    output: list[dt.date] = []
    seen: set[dt.date] = set()
    for raw in values:
        parsed = _parse_date(raw, field_name)
        if parsed is None:
            continue
        if parsed in seen:
            continue
        seen.add(parsed)
        output.append(parsed)
    return sorted(output)


def _build_summary_base_sql(table_name: str) -> str:
    source_view_sql = _view_sql(table_name)
    return f"""
SELECT
    s.SYMBOL AS SYMBOL,
    s.TRADING_DAYS AS TRADING_DAYS,
    s.IPO_DATE AS IPO_DATE,
    s.IPO_PRICE AS IPO_PRICE,
    s.PRICE AS PRICE,
    s.ATH AS ATH,
    s.ATH_DATE AS ATH_DATE,
    s.EXISTING AS EXISTING,
    s.LATEST_TRADING_DATE AS LATEST_TRADING_DATE
FROM (
    SELECT
        STOCK AS SYMBOL,
        COUNT(*) AS TRADING_DAYS,
        MIN(TRADING_DATE) AS IPO_DATE,
        MIN(CLOSE_PRICE) KEEP (DENSE_RANK FIRST ORDER BY TRADING_DATE ASC) AS IPO_PRICE,
        MAX(CLOSE_PRICE) KEEP (DENSE_RANK LAST ORDER BY TRADING_DATE ASC) AS PRICE,
        MAX(HIGH) AS ATH,
        MAX(TRADING_DATE) KEEP (DENSE_RANK LAST ORDER BY HIGH, TRADING_DATE) AS ATH_DATE,
        ROUND(MONTHS_BETWEEN(MAX(TRADING_DATE), MIN(TRADING_DATE)) / 12, 2) AS EXISTING,
        MAX(TRADING_DATE) AS LATEST_TRADING_DATE
    FROM {source_view_sql}
    GROUP BY STOCK
) s
"""


def _summary_filters(params: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
    symbol = str(params.get("symbol") or "").strip().upper()
    min_records = _parse_int(params.get("min_records"), "min_records", minimum=0)
    listed_from = _parse_date(params.get("listed_from"), "listed_from")
    listed_to = _parse_date(params.get("listed_to"), "listed_to")
    ath_min = _parse_float(params.get("ath_min"), "ath_min")
    ath_max = _parse_float(params.get("ath_max"), "ath_max")
    latest_from = _parse_date(params.get("latest_from"), "latest_from")
    latest_to = _parse_date(params.get("latest_to"), "latest_to")

    if listed_from and listed_to and listed_from > listed_to:
        raise ValueError("listed_from cannot be greater than listed_to.")
    if latest_from and latest_to and latest_from > latest_to:
        raise ValueError("latest_from cannot be greater than latest_to.")
    if ath_min is not None and ath_max is not None and ath_min > ath_max:
        raise ValueError("ath_min cannot be greater than ath_max.")

    clauses: list[str] = ["WHERE 1=1"]
    binds: dict[str, Any] = {}
    if symbol:
        clauses.append("  AND UPPER(s.SYMBOL) LIKE :symbol_like")
        binds["symbol_like"] = f"%{symbol}%"
    if min_records is not None:
        clauses.append("  AND s.TRADING_DAYS >= :min_records")
        binds["min_records"] = min_records
    if listed_from:
        clauses.append("  AND s.IPO_DATE >= :listed_from")
        binds["listed_from"] = listed_from
    if listed_to:
        clauses.append("  AND s.IPO_DATE <= :listed_to")
        binds["listed_to"] = listed_to
    if ath_min is not None:
        clauses.append("  AND s.ATH >= :ath_min")
        binds["ath_min"] = ath_min
    if ath_max is not None:
        clauses.append("  AND s.ATH <= :ath_max")
        binds["ath_max"] = ath_max
    if latest_from:
        clauses.append("  AND s.LATEST_TRADING_DATE >= :latest_from")
        binds["latest_from"] = latest_from
    if latest_to:
        clauses.append("  AND s.LATEST_TRADING_DATE <= :latest_to")
        binds["latest_to"] = latest_to

    normalized_filters = {
        "symbol": symbol,
        "min_records": min_records,
        "listed_from": listed_from.isoformat() if listed_from else "",
        "listed_to": listed_to.isoformat() if listed_to else "",
        "ath_min": ath_min,
        "ath_max": ath_max,
        "latest_from": latest_from.isoformat() if latest_from else "",
        "latest_to": latest_to.isoformat() if latest_to else "",
    }
    return "\n".join(clauses), binds, normalized_filters


def _summary_cache_key(table_name: str, normalized_filters: dict[str, Any]) -> str:
    return "|".join([
        table_name,
        str(normalized_filters.get("symbol") or ""),
        str(normalized_filters.get("min_records") or ""),
        str(normalized_filters.get("listed_from") or ""),
        str(normalized_filters.get("listed_to") or ""),
        str(normalized_filters.get("ath_min") if normalized_filters.get("ath_min") is not None else ""),
        str(normalized_filters.get("ath_max") if normalized_filters.get("ath_max") is not None else ""),
        str(normalized_filters.get("latest_from") or ""),
        str(normalized_filters.get("latest_to") or ""),
    ])


def _master_cache_key(table_name: str) -> str:
    return f"MASTER_TABLE_SUMMARY|{table_name}"


def _summary_cache_get(cache_key: str) -> dict[str, Any] | None:
    cached = _SUMMARY_CACHE.get(cache_key)
    return cached if isinstance(cached, dict) else None


def _summary_cache_set(cache_key: str, payload: dict[str, Any]) -> None:
    _SUMMARY_CACHE.set(cache_key, payload)


def _summary_cache_clear() -> None:
    _SUMMARY_CACHE.clear()


def _get_master_table_summary(table_name: str, force_refresh: bool = False) -> dict[str, Any]:
    cache_key = _master_cache_key(table_name)
    if not force_refresh:
        cached = _summary_cache_get(cache_key)
        if cached is not None:
            return cached

    started_at = time.perf_counter()
    base_sql = _build_summary_base_sql(table_name)
    all_rows_sql = f"""
SELECT
    {", ".join(SUMMARY_SELECT_COLUMNS)},
    s.LATEST_TRADING_DATE AS LATEST_TRADING_DATE
FROM ({base_sql}) s
ORDER BY s.SYMBOL
"""
    with pool.acquire() as con, con.cursor() as cur:
        cur.execute(all_rows_sql, {})
        all_rows_raw = _to_json_rows(fetchall_dict(cur))

    normalized_rows: list[dict[str, Any]] = []
    latest_data_date_value: Any = None
    total_records_value = 0
    for row in all_rows_raw:
        trading_days = int(row.get("trading_days") or 0)
        total_records_value += trading_days
        row_latest = row.get("latest_trading_date")
        if row_latest is not None:
            if latest_data_date_value is None or str(row_latest) > str(latest_data_date_value):
                latest_data_date_value = row_latest
        trade_date_value = row.get("trade_date") or row.get("latest_trading_date")
        normalized_rows.append({
            "symbol": row.get("symbol"),
            "trading_days": trading_days,
            "ipo_date": row.get("ipo_date"),
            "ipo_price": row.get("ipo_price"),
            "price": row.get("price"),
            "trade_date": trade_date_value,
            "latest_trading_date": trade_date_value,
            "ath": row.get("ath"),
            "ath_date": row.get("ath_date"),
            "existing": row.get("existing"),
        })

    payload = {
        "rows": normalized_rows,
        "total_count": len(normalized_rows),
        "total_records": total_records_value,
        "latest_data_date": _to_json_value(latest_data_date_value) or "",
    }
    _summary_cache_set(cache_key, payload)
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    _logger.info(
        "[HISTORICAL_DATA] master summary loaded table=%s rows=%s total_records=%s duration_ms=%s",
        table_name,
        len(normalized_rows),
        total_records_value,
        elapsed_ms,
    )
    return payload


def get_summary(params: dict[str, Any]) -> dict[str, Any]:
    table_name = _validate_table_name(params.get("table_name"))
    page = _normalize_page(params.get("page"))
    requested_page_size = _normalize_page_size(params.get("page_size"))
    page_size = SUMMARY_PAGE_SIZE if requested_page_size != SUMMARY_PAGE_SIZE else requested_page_size
    _where_sql, _binds, normalized_filters = _summary_filters(params)
    started_at = time.perf_counter()

    force_refresh = str(params.get("refresh") or "").strip().lower() in ("true", "1", "yes")

    master_payload = _get_master_table_summary(table_name, force_refresh=force_refresh)
    master_rows = list(master_payload.get("rows") or [])

    symbol = normalized_filters.get("symbol")
    min_records = normalized_filters.get("min_records")
    listed_from = normalized_filters.get("listed_from")
    listed_to = normalized_filters.get("listed_to")
    ath_min = normalized_filters.get("ath_min")
    ath_max = normalized_filters.get("ath_max")
    latest_from = normalized_filters.get("latest_from")
    latest_to = normalized_filters.get("latest_to")

    filtered_rows = master_rows
    if symbol:
        symbol_upper = str(symbol).strip().upper()
        filtered_rows = [r for r in filtered_rows if symbol_upper in str(r.get("symbol") or "").upper()]
    if min_records is not None:
        filtered_rows = [r for r in filtered_rows if int(r.get("trading_days") or 0) >= min_records]
    if listed_from:
        filtered_rows = [r for r in filtered_rows if r.get("ipo_date") and str(r.get("ipo_date"))[:10] >= listed_from]
    if listed_to:
        filtered_rows = [r for r in filtered_rows if r.get("ipo_date") and str(r.get("ipo_date"))[:10] <= listed_to]
    if ath_min is not None:
        filtered_rows = [r for r in filtered_rows if r.get("ath") is not None and float(r.get("ath")) >= ath_min]
    if ath_max is not None:
        filtered_rows = [r for r in filtered_rows if r.get("ath") is not None and float(r.get("ath")) <= ath_max]
    if latest_from:
        filtered_rows = [
            r for r in filtered_rows
            if (r.get("trade_date") or r.get("latest_trading_date")) and str(r.get("trade_date") or r.get("latest_trading_date"))[:10] >= latest_from
        ]
    if latest_to:
        filtered_rows = [
            r for r in filtered_rows
            if (r.get("trade_date") or r.get("latest_trading_date")) and str(r.get("trade_date") or r.get("latest_trading_date"))[:10] <= latest_to
        ]

    total_count = len(filtered_rows)
    total_pages = max(1, int(math.ceil(total_count / float(page_size)))) if total_count else 1

    offset_rows = (page - 1) * page_size
    rows = filtered_rows[offset_rows: offset_rows + page_size]

    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    _logger.info(
        "[HISTORICAL_DATA] summary completed table=%s page=%s rows=%s total_count=%s duration_ms=%s",
        table_name,
        page,
        len(rows),
        total_count,
        elapsed_ms,
    )
    return {
        "ok": True,
        "table_name": table_name,
        "page": page,
        "page_size": page_size,
        "total_count": total_count,
        "total_pages": total_pages,
        "filters": normalized_filters,
        "cards": {
            "selected_table": table_name,
            "total_symbols": int(master_payload.get("total_count") or total_count),
            "total_records": int(master_payload.get("total_records") or 0),
            "latest_data_date": _to_json_value(master_payload.get("latest_data_date")) or "",
        },
        "rows": rows,
        "data": rows,
    }


def _build_detail_base_sql(table_name: str, symbol: str, from_date: dt.date | None, to_date: dt.date | None) -> tuple[str, dict[str, Any]]:
    source_view_sql = _view_sql(table_name)
    where_clauses = ["UPPER(TRIM(src.STOCK)) = :symbol"]
    binds: dict[str, Any] = {"symbol": symbol}
    if from_date:
        where_clauses.append("src.TRADING_DATE >= :from_date")
        binds["from_date"] = from_date
    if to_date:
        where_clauses.append("src.TRADING_DATE <= :to_date")
        binds["to_date"] = to_date
    where_sql = " AND ".join(where_clauses)

    base_sql = f"""
SELECT
    src.STOCK AS SYMBOL,
    src.TRADING_DATE AS TRADING_DATE,
    src.OPEN AS OPEN,
    src.HIGH AS HIGH,
    src.LOW AS LOW,
    src.CLOSE_PRICE AS CLOSE_PRICE,
    src.VOLUME AS VOLUME
FROM {source_view_sql} src
WHERE {where_sql}
"""
    return base_sql, binds


def get_symbol_rows(symbol: str, params: dict[str, Any]) -> dict[str, Any]:
    table_name = _validate_table_name(params.get("table_name"))
    normalized_symbol = str(symbol or "").strip().upper()
    if not normalized_symbol:
        raise ValueError("symbol is required.")

    from_date = _parse_date(params.get("from_date"), "from_date")
    to_date = _parse_date(params.get("to_date"), "to_date")
    if from_date and to_date and from_date > to_date:
        raise ValueError("from_date cannot be greater than to_date.")

    page = _normalize_page(params.get("page"))
    requested_page_size = _normalize_page_size(params.get("page_size"))
    page_size = DETAIL_PAGE_SIZE if requested_page_size != DETAIL_PAGE_SIZE else requested_page_size
    sort_order = _normalize_sort_order(params.get("sort_order"))
    base_sql, binds = _build_detail_base_sql(table_name, normalized_symbol, from_date, to_date)
    count_sql = f"SELECT COUNT(*) AS TOTAL_COUNT FROM ({base_sql}) d"
    page_sql = f"""
SELECT *
FROM ({base_sql}) d
ORDER BY d.TRADING_DATE {sort_order}
OFFSET :offset_rows ROWS FETCH NEXT :page_size_rows ROWS ONLY
"""
    page_binds = dict(binds)
    page_binds.update({
        "offset_rows": (page - 1) * page_size,
        "page_size_rows": page_size,
    })

    _logger.info(
        "[HISTORICAL_DATA] symbol drilldown table=%s symbol=%s",
        table_name,
        normalized_symbol,
    )

    with pool.acquire() as con, con.cursor() as cur:
        cur.execute(count_sql, binds)
        total_count = int((cur.fetchone() or [0])[0] or 0)
        cur.execute(page_sql, page_binds)
        rows = _to_json_rows(fetchall_dict(cur))

    total_pages = max(1, int(math.ceil(total_count / float(page_size)))) if total_count else 1
    return {
        "ok": True,
        "table_name": table_name,
        "symbol": normalized_symbol,
        "page": page,
        "page_size": page_size,
        "total_count": total_count,
        "total_pages": total_pages,
        "sort_order": sort_order,
        "columns": TABLE_METADATA[table_name]["detail_columns"],
        "rows": rows,
        "data": rows,
    }


def _format_date_dd_mm_yyyy(value: Any) -> str:
    if isinstance(value, (dt.date, dt.datetime)):
        return value.strftime("%d-%m-%Y")
    if value:
        text = str(value).split("T")[0].strip()
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", text)
        if m:
            return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        m2 = re.match(r"^(\d{2})-(\d{2})-(\d{4})", text)
        if m2:
            return text
    return dt.date.today().strftime("%d-%m-%Y")


def _get_export_file_stem(normalized_symbol: str, latest_date: Any, timestamp: dt.datetime | None = None) -> str:
    date_str = _format_date_dd_mm_yyyy(latest_date)
    ts = (timestamp or dt.datetime.now()).strftime("%H%M%S")
    return f"{normalized_symbol}_{date_str}_{ts}"


def _get_symbol_export_rows(symbol: str, params: dict[str, Any]) -> tuple[str, str, list[dict[str, Any]], str]:
    table_name = _validate_table_name(params.get("table_name"))
    normalized_symbol = str(symbol or "").strip().upper()
    if not normalized_symbol:
        raise ValueError("symbol is required.")

    from_date = _parse_date(params.get("from_date"), "from_date")
    to_date = _parse_date(params.get("to_date"), "to_date")
    if from_date and to_date and from_date > to_date:
        raise ValueError("from_date cannot be greater than to_date.")

    base_sql, binds = _build_detail_base_sql(table_name, normalized_symbol, from_date, to_date)
    csv_sql = f"""
SELECT *
FROM ({base_sql}) d
ORDER BY d.TRADING_DATE ASC
"""
    with pool.acquire() as con, con.cursor() as cur:
        cur.execute(csv_sql, binds)
        rows = fetchall_dict(cur)

    latest_date_val: Any = None
    normalized_rows: list[dict[str, Any]] = []
    for serial_no, row in enumerate(rows, start=1):
        trade_date = row.get("trading_date")
        if trade_date:
            latest_date_val = trade_date
        if isinstance(trade_date, (dt.date, dt.datetime)):
            trade_date = trade_date.strftime("%Y-%m-%d")
        normalized_rows.append({
            "s.no": serial_no,
            "symbol": row.get("symbol") or normalized_symbol,
            "trade_date": trade_date or "",
            "open": _to_export_value(row.get("open")) if row.get("open") is not None else "",
            "high": _to_export_value(row.get("high")) if row.get("high") is not None else "",
            "low": _to_export_value(row.get("low")) if row.get("low") is not None else "",
            "close": _to_export_value(row.get("close_price")) if row.get("close_price") is not None else "",
            "volume": _to_export_value(row.get("volume")) if row.get("volume") is not None else "",
        })
    return table_name, normalized_symbol, normalized_rows, _format_date_dd_mm_yyyy(latest_date_val)


def _render_symbol_csv(rows: Sequence[dict[str, Any]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_HEADERS, lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def get_symbol_csv(symbol: str, params: dict[str, Any]) -> tuple[str, str]:
    table_name, normalized_symbol, rows, latest_date_str = _get_symbol_export_rows(symbol, params)
    file_stem = _get_export_file_stem(normalized_symbol, latest_date_str)
    csv_content = _render_symbol_csv(rows)

    _logger.info(
        "[HISTORICAL_DATA][CSV] generated table=%s symbol=%s rows=%s file_stem=%s",
        table_name,
        normalized_symbol,
        len(rows),
        file_stem,
    )
    return f"{file_stem}.csv", csv_content


def get_symbol_export_bundle(symbol: str, params: dict[str, Any]) -> tuple[str, bytes]:
    table_name, normalized_symbol, rows, latest_date_str = _get_symbol_export_rows(symbol, params)
    file_stem = _get_export_file_stem(normalized_symbol, latest_date_str)
    csv_content = _render_symbol_csv(rows)
    json_content = json.dumps(rows, ensure_ascii=False, indent=2) + "\n"
    txt_lines = ["\t".join(CSV_HEADERS)]
    txt_lines.extend("\t".join(str(row.get(header, "")) for header in CSV_HEADERS) for row in rows)
    txt_content = "\r\n".join(txt_lines) + "\r\n"

    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{file_stem}.csv", csv_content.encode("utf-8"))
        archive.writestr(f"{file_stem}.json", json_content.encode("utf-8"))
        archive.writestr(f"{file_stem}.txt", txt_content.encode("utf-8"))

    _logger.info(
        "[HISTORICAL_DATA][EXPORT] generated table=%s symbol=%s rows=%s formats=csv,json,txt file_stem=%s",
        table_name,
        normalized_symbol,
        len(rows),
        file_stem,
    )
    return f"{file_stem}.zip", output.getvalue()


def _in_clause(prefix: str, values: Sequence[Any]) -> tuple[str, dict[str, Any]]:
    placeholders: list[str] = []
    binds: dict[str, Any] = {}
    for idx, value in enumerate(values):
        key = f"{prefix}_{idx}"
        placeholders.append(f":{key}")
        binds[key] = value
    return ", ".join(placeholders), binds


def _delete_symbol_rows_for_table(cur: Any, table_name: str, symbols: Sequence[str]) -> tuple[int, int]:
    metadata = TABLE_METADATA[table_name]
    symbol_col = str(metadata["delete_symbol_col"])
    table_sql = _table_sql(str(metadata["delete_table"]))
    in_sql, in_binds = _in_clause("sym", symbols)
    where_sql = f"UPPER(TRIM({symbol_col})) IN ({in_sql})"
    count_sql = f"SELECT COUNT(*) AS MATCHED_ROWS FROM {table_sql} WHERE {where_sql}"
    delete_sql = f"DELETE FROM {table_sql} WHERE {where_sql}"

    cur.execute(count_sql, in_binds)
    matched_rows = int((cur.fetchone() or [0])[0] or 0)
    deleted_rows = 0
    if matched_rows > 0:
        cur.execute(delete_sql, in_binds)
        deleted_rows = int(cur.rowcount or 0)
    return matched_rows, deleted_rows


def delete_symbols(payload: dict[str, Any]) -> dict[str, Any]:
    table_name = _validate_table_name(payload.get("table_name"))
    confirm_text = str(payload.get("confirm_text") or "").strip()
    if confirm_text != "DELETE":
        raise ValueError("Delete confirmation failed")

    symbols = _normalize_symbols(payload.get("symbols") or [])
    if not symbols:
        raise ValueError("symbols is required.")

    dev_table_name = "NSE_NIFTY500_DAILY_RAW_DATA_DEV"
    oracle_table_name = "NSE_NIFTY500_DAILY_RAW_DATA_ORACLE"
    con = None
    try:
        with pool.acquire() as con, con.cursor() as cur:
            dev_matched_rows, dev_deleted_rows = _delete_symbol_rows_for_table(cur, dev_table_name, symbols)
            oracle_matched_rows, oracle_deleted_rows = _delete_symbol_rows_for_table(cur, oracle_table_name, symbols)
            con.commit()
        matched_rows = dev_matched_rows + oracle_matched_rows
        deleted_rows = dev_deleted_rows + oracle_deleted_rows
        _logger.info(
            "[HISTORICAL_DATA][DELETE] request_table=%s symbols=%s dev_deleted_rows=%s oracle_deleted_rows=%s total_deleted_rows=%s",
            table_name,
            ",".join(symbols),
            dev_deleted_rows,
            oracle_deleted_rows,
            deleted_rows,
        )
        _summary_cache_clear()
        return {
            "ok": True,
            "success": True,
            "table_name": table_name,
            "symbols": symbols,
            "deleted_symbols": len(symbols),
            "deletedSymbols": len(symbols),
            "dev_matched_rows": dev_matched_rows,
            "devMatchedRows": dev_matched_rows,
            "dev_deleted_rows": dev_deleted_rows,
            "devDeletedRows": dev_deleted_rows,
            "oracle_matched_rows": oracle_matched_rows,
            "oracleMatchedRows": oracle_matched_rows,
            "oracle_deleted_rows": oracle_deleted_rows,
            "oracleDeletedRows": oracle_deleted_rows,
            "matched_rows": matched_rows,
            "deleted_rows": deleted_rows,
            "message": "Delete completed successfully",
        }
    except Exception as exc:
        if con is not None and hasattr(con, "rollback"):
            try:
                con.rollback()
            except Exception:
                _logger.exception(
                    "[HISTORICAL_DATA][ERROR] rollback failed request_table=%s symbols=%s",
                    table_name,
                    ",".join(symbols),
                )
        _logger.exception(
            "[HISTORICAL_DATA][ERROR] delete failed request_table=%s symbols=%s",
            table_name,
            ",".join(symbols),
        )
        raise RuntimeError("Backend error while deleting data") from exc


def delete_rows(payload: dict[str, Any]) -> dict[str, Any]:
    table_name = _validate_table_name(payload.get("table_name"))
    confirm_text = str(payload.get("confirm_text") or "").strip()
    if confirm_text != "DELETE":
        raise ValueError("Delete confirmation failed")

    symbol = str(payload.get("symbol") or "").strip().upper()
    if not symbol:
        raise ValueError("symbol is required.")

    trading_dates = _normalize_dates(payload.get("trading_dates") or [], field_name="trading_dates")
    if not trading_dates:
        raise ValueError("trading_dates is required.")

    metadata = TABLE_METADATA[table_name]
    symbol_col = metadata["delete_symbol_col"]
    table_sql = _table_sql(str(metadata["delete_table"]))
    in_sql, date_binds = _in_clause("dt", trading_dates)
    binds = {"symbol": symbol}
    binds.update(date_binds)
    where_sql = f"UPPER(TRIM({symbol_col})) = :symbol AND TRADING_DATE IN ({in_sql})"
    count_sql = f"SELECT COUNT(*) AS MATCHED_ROWS FROM {table_sql} WHERE {where_sql}"
    delete_sql = f"DELETE FROM {table_sql} WHERE {where_sql}"

    try:
        with pool.acquire() as con, con.cursor() as cur:
            cur.execute(count_sql, binds)
            matched_rows = int((cur.fetchone() or [0])[0] or 0)
            deleted_rows = 0
            if matched_rows > 0:
                cur.execute(delete_sql, binds)
                deleted_rows = int(cur.rowcount or 0)
            con.commit()
        _logger.info(
            "[HISTORICAL_DATA][DELETE_ROWS] table=%s symbol=%s dates=%s deleted_rows=%s",
            table_name,
            symbol,
            ",".join(day.isoformat() for day in trading_dates),
            deleted_rows,
        )
        _summary_cache_clear()
        return {
            "ok": True,
            "table_name": table_name,
            "symbol": symbol,
            "trading_dates": [day.isoformat() for day in trading_dates],
            "matched_rows": matched_rows,
            "deleted_rows": deleted_rows,
            "message": "Delete completed successfully",
        }
    except Exception as exc:
        _logger.exception(
            "[HISTORICAL_DATA][ERROR] delete failed table=%s symbols=%s",
            table_name,
            symbol,
        )
        raise RuntimeError("Backend error while deleting data") from exc


__all__ = [
    "ALLOWED_TABLES",
    "DEFAULT_TABLE",
    "PAGE_SIZE_OPTIONS",
    "TABLE_METADATA",
    "delete_rows",
    "delete_symbols",
    "get_summary",
    "get_symbol_csv",
    "get_symbol_export_bundle",
    "get_symbol_rows",
    "list_allowed_tables",
]
