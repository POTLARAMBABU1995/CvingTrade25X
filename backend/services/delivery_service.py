from __future__ import annotations

import logging
import os
import re
import hashlib
import json
import time
from copy import deepcopy
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple

try:
    from ..db_pool import pool, fetchall_dict
except ImportError:  # pragma: no cover
    from db_pool import pool, fetchall_dict  # type: ignore

try:
    from ..cache import TTLCache
except ImportError:  # pragma: no cover
    from cache import TTLCache  # type: ignore


_logger = logging.getLogger(__name__)

_IDENT_RE = re.compile(r"^[A-Za-z0-9_.$#]+$")

_DELIVERY_TABLE = (os.getenv("NSE_DELIVERY_TABLE") or "CVING_NSE_DELIVERY_HIST").strip()
_OHLC_TABLE = (os.getenv("ORACLE_TABLE") or "NSE_NIFTY500_DAILY_RAW_DATA_DEV").strip()
_ORACLE_SCHEMA = (os.getenv("ORACLE_SCHEMA") or "").strip()
_FORCE_PRICE_FALLBACK = str(os.getenv("DELIVERY_FORCE_PRICE_FALLBACK", "0")).strip().lower() in {"1", "true", "yes", "on"}

_DEFAULT_PAGE_SIZE = 25
_MAX_PAGE_SIZE = 25

_DEFAULT_SORT = "delivery_score"
_DEFAULT_SORT_DIR = "desc"

_METADATA_TTL_SEC = 600
_metadata_cache: Dict[str, Any] = {
    "expires_at": 0.0,
    "projection": None,
    "price_source": None,
}

_SNAPSHOT_LOOKBACK_DAYS = max(30, int(str(os.getenv("DELIVERY_SNAPSHOT_LOOKBACK_DAYS", "45")).strip() or "45"))
_SNAPSHOT_TTL_SEC = max(30, int(str(os.getenv("DELIVERY_PERIOD_SNAPSHOT_TTL_SEC", "900")).strip() or "900"))
_SNAPSHOT_MAX_ITEMS = max(8, int(str(os.getenv("DELIVERY_PERIOD_SNAPSHOT_MAX_ITEMS", "64")).strip() or "64"))
_period_snapshot_cache = TTLCache(ttl_seconds=_SNAPSHOT_TTL_SEC, max_items=_SNAPSHOT_MAX_ITEMS)
_DELIVERY_CACHE_TTL_SEC = max(30, int(str(os.getenv("DELIVERY_CACHE_TTL_SECONDS", "300")).strip() or "300"))
_DELIVERY_CACHE_MAX_ITEMS = max(32, int(str(os.getenv("DELIVERY_CACHE_MAX_ITEMS", "500")).strip() or "500"))
_delivery_response_cache = TTLCache(ttl_seconds=_DELIVERY_CACHE_TTL_SEC, max_items=_DELIVERY_CACHE_MAX_ITEMS)
_DELIVERY_SUMMARY_SCHEMA_VERSION = 4

_SORT_MAP: Dict[str, str] = {
    "symbol": "f.symbol",
    "price": "f.price",
    "trading_date": "f.trading_date",
    "ltc_date": "f.ltc_date",
    "t_d": "f.t_d",
    "delivery_qty": "f.delivery_qty",
    "delivery_pct": "f.delivery_pct",
    "delivery_score": "f.delivery_score",
    "delivery_status": "f.delivery_status",
}


def _safe_identifier(value: str) -> str:
    text = str(value or "").strip()
    if not text or not _IDENT_RE.match(text):
        raise ValueError(f"Invalid SQL identifier: {value!r}")
    return text


def _qualify_table(table_name: str) -> str:
    raw = _safe_identifier(table_name)
    if "." in raw:
        return raw
    if _ORACLE_SCHEMA:
        return f"{_safe_identifier(_ORACLE_SCHEMA)}.{raw}"
    return raw


def _normalize_key(value: str) -> str:
    return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum() or ch == "_")


def normalize_delivery_symbol(value: Any) -> str:
    token = str(value or "").strip().upper()
    if not token:
        return ""
    for prefix in ("NSE:", "BSE:"):
        if token.startswith(prefix):
            token = token[len(prefix):].strip()
            break
    for suffix in (":EQ", "-EQ"):
        if token.endswith(suffix):
            token = token[:-len(suffix)].strip()
            break
    return token


def _normalized_delivery_symbol_expr(expr: str) -> str:
    return (
        "UPPER(TRIM(REGEXP_REPLACE("
        "REGEXP_REPLACE("
        "REGEXP_REPLACE(TRIM("
        f"{expr}"
        "), '^(NSE|BSE):', '', 1, 0, 'i'), "
        "'(:EQ|-EQ)$', '', 1, 0, 'i'), "
        "'[[:space:]]+', '')))"
    )


def _pick_column(columns: Iterable[str], candidates: Sequence[str]) -> Optional[str]:
    col_map = {str(col).upper(): str(col) for col in columns}
    for candidate in candidates:
        key = str(candidate).upper()
        if key in col_map:
            return col_map[key]
    return None


def _to_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "").strip())
    except Exception:
        return None


def _to_int(value: Any, default: int = 0) -> int:
    num = _to_number(value)
    if num is None:
        return default
    try:
        return int(round(num))
    except Exception:
        return default


def _to_int_optional(value: Any) -> Optional[int]:
    num = _to_number(value)
    if num is None:
        return None
    try:
        return int(round(num))
    except Exception:
        return None


def _to_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    token = text[:10]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(token, fmt).date()
        except Exception:
            continue
    return None


def _date_to_iso(value: Any) -> Optional[str]:
    parsed = _to_date(value)
    return parsed.strftime("%Y-%m-%d") if parsed else None


def _resolve_ltc_date_iso(row: Dict[str, Any]) -> Optional[str]:
    if not isinstance(row, dict):
        return None
    return _date_to_iso(row.get("ltc_date")) or _date_to_iso(row.get("trading_date"))


def _resolve_columns(conn, table_sql: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT * FROM {table_sql} WHERE ROWNUM = 0")
        desc = cur.description or []
    return [str(item[0]).upper() for item in desc if item and item[0]]


def _resolve_price_source(conn, delivery_table_sql: str) -> Optional[Dict[str, str]]:
    source_table_sql = _qualify_table(_OHLC_TABLE)
    if source_table_sql.upper() == delivery_table_sql.upper():
        return None
    try:
        columns = _resolve_columns(conn, source_table_sql)
    except Exception:
        _logger.warning("Delivery price fallback table not readable: %s", source_table_sql, exc_info=True)
        return None

    symbol_col = _pick_column(columns, ("SYMBOL", "STOCK", "TICKER", "SECURITY"))
    date_col = _pick_column(columns, ("TRADING_DATE", "TRADE_DATE", "DATE"))
    close_col = _pick_column(
        columns,
        (
            "CLOSE_PRICE",
            "CLOSE",
            "ADJ_CLOSE",
            "LTP",
            "LAST_PRICE",
            "LAST_TRADED_PRICE",
            "CLOSING_PRICE",
            "BUYING_PRICE",
            "PRICE",
        ),
    )
    if not symbol_col or not date_col or not close_col:
        return None
    return {
        "table": source_table_sql,
        "symbol_col": symbol_col,
        "date_col": date_col,
        "close_col": close_col,
    }


def _resolve_delivery_projection(conn) -> Dict[str, Any]:
    table_sql = _qualify_table(_DELIVERY_TABLE)
    columns = _resolve_columns(conn, table_sql)
    symbol_col = _pick_column(columns, ("SYMBOL", "STOCK", "TICKER", "SECURITY", "SC_NAME"))
    date_col = _pick_column(columns, ("TRADING_DATE", "TRADE_DATE", "DATE"))
    qty_col = _pick_column(columns, ("DELIVERY_QTY", "DELIVERABLE_QTY", "DELIV_QTY", "DELIVQTY"))
    pct_col = _pick_column(
        columns,
        (
            "DELIVERY_PERCENT",
            "DELIVERY_PERCENTAGE",
            "DELIVERY_PCT",
            "DELIVERY%",
            "DELIV_PERCENT",
            "DELIV_PER",
            "DELIVPERCENT",
            "DELIVPER",
        ),
    )
    price_col = _pick_column(
        columns,
        (
            "PRICE",
            "CLOSE_PRICE",
            "CLOSE",
            "LTP",
            "LAST_PRICE",
            "LAST_TRADED_PRICE",
            "BUYING_PRICE",
        ),
    )
    status_col = _pick_column(columns, ("FETCH_STATUS", "STATUS"))
    fetch_ts_col = _pick_column(columns, ("FETCH_TS", "UPDATED_TS", "UPDATED_AT", "FETCHED_AT", "CREATED_AT"))
    updated_ts_col = _pick_column(columns, ("UPDATED_TS", "UPDATED_AT", "MODIFIED_AT", "LAST_UPDATED_AT"))
    id_col = _pick_column(columns, ("ID", "ROW_ID"))

    if not symbol_col or not date_col or not qty_col or not pct_col:
        missing = []
        if not symbol_col:
            missing.append("SYMBOL")
        if not date_col:
            missing.append("TRADING_DATE/TRADE_DATE")
        if not qty_col:
            missing.append("DELIVERY_QTY/DELIVERABLE_QTY/DELIV_QTY")
        if not pct_col:
            missing.append("DELIVERY_PERCENT/DELIVERY_PCT/DELIV_PER")
        raise RuntimeError(f"Delivery table schema is missing required columns: {', '.join(missing)}")

    return {
        "table_sql": table_sql,
        "columns": columns,
        "symbol_col": symbol_col,
        "date_col": date_col,
        "qty_col": qty_col,
        "pct_col": pct_col,
        "price_col": price_col,
        "status_col": status_col,
        "fetch_ts_col": fetch_ts_col,
        "updated_ts_col": updated_ts_col,
        "id_col": id_col,
    }


def _resolve_runtime_metadata(conn) -> Tuple[Dict[str, Any], Optional[Dict[str, str]]]:
    now = time.time()
    expires_at = float(_metadata_cache.get("expires_at") or 0.0)
    cached_projection = _metadata_cache.get("projection")
    cached_price_source = _metadata_cache.get("price_source")
    if now < expires_at and isinstance(cached_projection, dict):
        return cached_projection, cached_price_source if isinstance(cached_price_source, dict) else None

    projection = _resolve_delivery_projection(conn)
    price_source = _resolve_price_source(conn, projection["table_sql"])
    _metadata_cache["projection"] = projection
    _metadata_cache["price_source"] = price_source
    _metadata_cache["expires_at"] = now + _METADATA_TTL_SEC
    return projection, price_source


def _fetch_latest_ltc_date(conn, *, projection: Dict[str, Any]) -> Optional[str]:
    table_sql = projection["table_sql"]
    date_col = projection["date_col"]
    sql = f"""
SELECT
    CAST(MAX(src.{date_col}) AS DATE) AS latest_ltc_date
FROM {table_sql} src
WHERE src.{date_col} IS NOT NULL
"""
    with conn.cursor() as cur:
        cur.execute(sql)
        rows = fetchall_dict(cur)
    if not rows:
        return None
    return _date_to_iso(rows[0].get("latest_ltc_date"))


def _derive_recent_td_limit(
    *,
    trading_date: Optional[date],
    start_date: Optional[date],
    end_date: Optional[date],
    td: Optional[int],
    latest_only: bool,
) -> Optional[int]:
    if trading_date is not None or start_date is not None or end_date is not None:
        return None
    if td is not None:
        return max(20, int(td) + 25)
    if latest_only:
        return 25
    return 180


def _fill_missing_prices(conn, rows: list[Dict[str, Any]], price_source: Dict[str, str]) -> None:
    missing_pairs = []
    symbols = set()
    for row in rows:
        if row.get("price") is not None:
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        trading_date = _to_date(row.get("trading_date"))
        if not symbol:
            continue
        symbols.add(symbol)
        if trading_date is not None:
            missing_pairs.append((symbol, trading_date))
    if not symbols:
        return

    exact_map: Dict[Tuple[str, str], float] = {}
    latest_map: Dict[str, float] = {}

    if missing_pairs:
        clauses = []
        binds: Dict[str, Any] = {}
        for idx, (symbol, trading_day) in enumerate(missing_pairs):
            sym_key = f"esym_{idx}"
            day_key = f"eday_{idx}"
            clauses.append(
                f"(UPPER(TRIM(ps.{price_source['symbol_col']})) = :{sym_key} AND CAST(ps.{price_source['date_col']} AS DATE) = :{day_key})"
            )
            binds[sym_key] = symbol
            binds[day_key] = trading_day
        exact_sql = f"""
SELECT
    UPPER(TRIM(ps.{price_source['symbol_col']})) AS symbol,
    CAST(ps.{price_source['date_col']} AS DATE) AS trading_date,
    CAST(ps.{price_source['close_col']} AS NUMBER(24,6)) AS close_price
FROM {price_source['table']} ps
WHERE {" OR ".join(clauses)}
"""
        with conn.cursor() as cur:
            cur.execute(exact_sql, binds)
            for rec in fetchall_dict(cur):
                sym = str(rec.get("symbol") or "").strip().upper()
                dt = _date_to_iso(rec.get("trading_date"))
                close = _to_number(rec.get("close_price"))
                if sym and dt and close is not None:
                    exact_map[(sym, dt)] = close

    symbol_binds = {}
    symbol_placeholders = []
    for idx, symbol in enumerate(sorted(symbols)):
        bind_key = f"lsym_{idx}"
        symbol_binds[bind_key] = symbol
        symbol_placeholders.append(f":{bind_key}")
    latest_sql = f"""
SELECT
    x.symbol,
    x.close_price
FROM (
    SELECT
        UPPER(TRIM(ps.{price_source['symbol_col']})) AS symbol,
        CAST(ps.{price_source['close_col']} AS NUMBER(24,6)) AS close_price,
        ROW_NUMBER() OVER (
            PARTITION BY UPPER(TRIM(ps.{price_source['symbol_col']}))
            ORDER BY CAST(ps.{price_source['date_col']} AS DATE) DESC
        ) AS rn
    FROM {price_source['table']} ps
    WHERE UPPER(TRIM(ps.{price_source['symbol_col']})) IN ({", ".join(symbol_placeholders)})
      AND ps.{price_source['close_col']} IS NOT NULL
) x
WHERE x.rn = 1
"""
    with conn.cursor() as cur:
        cur.execute(latest_sql, symbol_binds)
        for rec in fetchall_dict(cur):
            sym = str(rec.get("symbol") or "").strip().upper()
            close = _to_number(rec.get("close_price"))
            if sym and close is not None:
                latest_map[sym] = close

    for row in rows:
        if row.get("price") is not None:
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        row_iso = _date_to_iso(row.get("trading_date"))
        matched = exact_map.get((symbol, row_iso or ""))
        if matched is None:
            matched = latest_map.get(symbol)
        if matched is not None:
            row["price"] = matched


def _resolve_sort(sort_by: Optional[str], sort_dir: Optional[str]) -> str:
    normalized_by = _normalize_key(sort_by or _DEFAULT_SORT)
    primary_expr = _SORT_MAP.get(normalized_by, _SORT_MAP[_DEFAULT_SORT])
    normalized_dir = str(sort_dir or _DEFAULT_SORT_DIR).strip().lower()
    primary_dir = "ASC" if normalized_dir == "asc" else "DESC"

    if primary_expr == _SORT_MAP[_DEFAULT_SORT] and primary_dir == "DESC":
        return "f.delivery_score DESC, f.delivery_pct DESC, f.delivery_qty DESC, f.symbol ASC"

    tie_breakers = [
        ("f.delivery_score", "DESC"),
        ("f.delivery_pct", "DESC"),
        ("f.delivery_qty", "DESC"),
        ("f.symbol", "ASC"),
    ]
    parts = [f"{primary_expr} {primary_dir}"]
    existing = {primary_expr}
    for expr, direction in tie_breakers:
        if expr in existing:
            continue
        parts.append(f"{expr} {direction}")
        existing.add(expr)
    return ", ".join(parts)


def _build_cte_sql(
    *,
    projection: Dict[str, Any],
    price_source: Optional[Dict[str, str]],
    filter_sql: str,
    source_filter_sql: str,
    recent_td_limit: Optional[int],
    use_filtered_date_rank: bool = False,
) -> str:
    symbol_col = projection["symbol_col"]
    date_col = projection["date_col"]
    qty_col = projection["qty_col"]
    pct_col = projection["pct_col"]
    price_col = projection["price_col"]
    status_col = projection["status_col"]
    fetch_ts_col = projection["fetch_ts_col"]
    updated_ts_col = projection["updated_ts_col"]
    id_col = projection["id_col"]
    table_sql = projection["table_sql"]

    status_priority_sql = (
        f"CASE WHEN UPPER(NVL(src.{status_col}, 'SUCCESS')) = 'SUCCESS' THEN 0 ELSE 1 END"
        if status_col
        else "0"
    )
    ts_priority_sql = f"src.{fetch_ts_col} DESC" if fetch_ts_col else f"src.{date_col} DESC"
    updated_priority_sql = f", src.{updated_ts_col} DESC" if updated_ts_col else ""
    id_priority_sql = f", src.{id_col} DESC" if id_col else ""
    delivery_price_expr = f"CAST(src.{price_col} AS NUMBER(24,6))" if price_col else "CAST(NULL AS NUMBER(24,6))"

    rank_limit_clause = ""
    if recent_td_limit is not None:
        rank_limit_clause = "    WHERE drf.t_d <= :recent_td_limit"

    if use_filtered_date_rank:
        date_rank_source_sql = """
        SELECT DISTINCT db_dates.trading_date AS trading_date
        FROM delivery_base db_dates
"""
    else:
        date_rank_source_sql = f"""
        SELECT DISTINCT CAST(src_date.{date_col} AS DATE) AS trading_date
        FROM {table_sql} src_date
        WHERE src_date.{date_col} IS NOT NULL
"""

    recent_source_filter_sql = ""
    if recent_td_limit is not None and not use_filtered_date_rank:
        recent_source_filter_sql = f"""
      AND CAST(src.{date_col} AS DATE) >= (
          SELECT MIN(recent_dates.trading_date)
          FROM (
              SELECT
                  d.trading_date,
                  DENSE_RANK() OVER (ORDER BY d.trading_date DESC) - 1 AS t_d
              FROM (
                  SELECT DISTINCT CAST(src_recent.{date_col} AS DATE) AS trading_date
                  FROM {table_sql} src_recent
                  WHERE src_recent.{date_col} IS NOT NULL
              ) d
          ) recent_dates
          WHERE recent_dates.t_d <= :recent_td_limit
      )"""

    if price_source:
        price_source_cte = f"""
delivery_symbols AS (
    SELECT DISTINCT symbol
    FROM delivery_base
),
delivery_date_window AS (
    SELECT
        MIN(trading_date) AS min_trading_date,
        MAX(trading_date) AS max_trading_date
    FROM delivery_base
),
price_source AS (
    SELECT
        UPPER(TRIM(ps.{price_source['symbol_col']})) AS symbol,
        CAST(ps.{price_source['date_col']} AS DATE) AS trading_date,
        CAST(ps.{price_source['close_col']} AS NUMBER(24,6)) AS close_price
    FROM {price_source['table']} ps
    INNER JOIN delivery_symbols ds
      ON ds.symbol = UPPER(TRIM(ps.{price_source['symbol_col']}))
    CROSS JOIN delivery_date_window dw
    WHERE ps.{price_source['symbol_col']} IS NOT NULL
      AND ps.{price_source['date_col']} IS NOT NULL
      AND ps.{price_source['close_col']} IS NOT NULL
      AND CAST(ps.{price_source['date_col']} AS DATE) BETWEEN (dw.min_trading_date - 30) AND dw.max_trading_date
),
price_day AS (
    SELECT symbol, trading_date, close_price FROM price_source
),
price_latest AS (
    SELECT x.symbol, x.close_price
    FROM (
        SELECT
            UPPER(TRIM(ps.{price_source['symbol_col']})) AS symbol,
            CAST(ps.{price_source['close_col']} AS NUMBER(24,6)) AS close_price,
            ROW_NUMBER() OVER (
                PARTITION BY UPPER(TRIM(ps.{price_source['symbol_col']}))
                ORDER BY CAST(ps.{price_source['date_col']} AS DATE) DESC
            ) AS rn
        FROM {price_source['table']} ps
        INNER JOIN delivery_symbols ds
          ON ds.symbol = UPPER(TRIM(ps.{price_source['symbol_col']}))
        WHERE ps.{price_source['symbol_col']} IS NOT NULL
          AND ps.{price_source['date_col']} IS NOT NULL
          AND ps.{price_source['close_col']} IS NOT NULL
    ) x
    WHERE x.rn = 1
),
"""
        price_join_sql = """
    LEFT JOIN price_day pd
      ON pd.symbol = db.symbol
     AND pd.trading_date = db.trading_date
    LEFT JOIN price_latest pl
      ON pl.symbol = db.symbol
"""
        price_value_sql = "COALESCE(db.delivery_price, pd.close_price, pl.close_price)"
    else:
        price_source_cte = ""
        price_join_sql = ""
        price_value_sql = "db.delivery_price"

    return f"""
WITH delivery_raw AS (
    SELECT
        UPPER(TRIM(src.{symbol_col})) AS symbol,
        CAST(src.{date_col} AS DATE) AS trading_date,
        CAST(src.{qty_col} AS NUMBER(24,6)) AS delivery_qty,
        CAST(src.{pct_col} AS NUMBER(12,6)) AS delivery_pct,
        {delivery_price_expr} AS delivery_price,
        ROW_NUMBER() OVER (
            PARTITION BY UPPER(TRIM(src.{symbol_col})), CAST(src.{date_col} AS DATE)
            ORDER BY {status_priority_sql}, {ts_priority_sql}{updated_priority_sql}{id_priority_sql}
        ) AS rn
    FROM {table_sql} src
    WHERE src.{symbol_col} IS NOT NULL
      AND src.{date_col} IS NOT NULL
{source_filter_sql}
{recent_source_filter_sql}
),
delivery_base AS (
    SELECT
        symbol,
        trading_date,
        delivery_qty,
        delivery_pct,
        delivery_price
    FROM delivery_raw
    WHERE rn = 1
),
date_ranked_full AS (
    SELECT
        d.trading_date,
        DENSE_RANK() OVER (ORDER BY d.trading_date DESC) - 1 AS t_d
    FROM (
{date_rank_source_sql}
    ) d
),
date_ranked AS (
    SELECT
        drf.trading_date,
        drf.t_d
    FROM date_ranked_full drf
{rank_limit_clause}
),
{price_source_cte}
enriched AS (
    SELECT
        db.symbol,
        db.trading_date,
        db.trading_date AS ltc_date,
        dr.t_d,
        db.delivery_qty,
        db.delivery_pct,
        {price_value_sql} AS price
    FROM delivery_base db
    INNER JOIN date_ranked dr
      ON dr.trading_date = db.trading_date
{price_join_sql}
),
metrics AS (
    SELECT
        e.*,
        AVG(e.delivery_pct) OVER (
            PARTITION BY e.symbol
            ORDER BY e.trading_date
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ) AS pct_avg_3,
        AVG(e.delivery_pct) OVER (
            PARTITION BY e.symbol
            ORDER BY e.trading_date
            ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
        ) AS pct_avg_5,
        AVG(e.delivery_pct) OVER (
            PARTITION BY e.symbol
            ORDER BY e.trading_date
            ROWS BETWEEN 9 PRECEDING AND 5 PRECEDING
        ) AS pct_avg_prev_5,
        AVG(e.delivery_qty) OVER (
            PARTITION BY e.symbol
            ORDER BY e.trading_date
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ) AS qty_avg_3,
        AVG(e.delivery_qty) OVER (
            PARTITION BY e.symbol
            ORDER BY e.trading_date
            ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
        ) AS qty_avg_5,
        AVG(e.delivery_qty) OVER (
            PARTITION BY e.symbol
            ORDER BY e.trading_date
            ROWS BETWEEN 9 PRECEDING AND 5 PRECEDING
        ) AS qty_avg_prev_5,
        AVG(e.delivery_qty) OVER (
            PARTITION BY e.symbol
            ORDER BY e.trading_date
            ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
        ) AS qty_avg_20,
        LAG(e.price) OVER (
            PARTITION BY e.symbol
            ORDER BY e.trading_date
        ) AS prev_price,
        MAX(e.price) OVER (
            PARTITION BY e.symbol
            ORDER BY e.trading_date
            ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
        ) AS price_high_20,
        COUNT(1) OVER (
            PARTITION BY e.symbol
            ORDER BY e.trading_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS history_days
    FROM enriched e
),
component_scores AS (
    SELECT
        m.*,
        CASE
            WHEN m.delivery_pct IS NULL THEN 0
            WHEN m.delivery_pct < 30 THEN GREATEST(0, LEAST(5, (m.delivery_pct / 30) * 5))
            WHEN m.delivery_pct < 40 THEN 5 + ((m.delivery_pct - 30) / 10) * 7
            WHEN m.delivery_pct < 50 THEN 12 + ((m.delivery_pct - 40) / 10) * 8
            WHEN m.delivery_pct < 60 THEN 20 + ((m.delivery_pct - 50) / 10) * 6
            ELSE LEAST(30, 26 + LEAST(m.delivery_pct - 60, 20) * 0.2)
        END AS score_pct_level,
        LEAST(
            25,
            GREATEST(
                0,
                (CASE
                    WHEN m.delivery_pct IS NOT NULL AND m.pct_avg_3 IS NOT NULL AND m.delivery_pct > m.pct_avg_3
                    THEN LEAST(8, 4 + (m.delivery_pct - m.pct_avg_3) / 2)
                    ELSE 0
                END)
                + (CASE
                    WHEN m.pct_avg_3 IS NOT NULL AND m.pct_avg_5 IS NOT NULL AND m.pct_avg_3 > m.pct_avg_5
                    THEN LEAST(8, 3 + (m.pct_avg_3 - m.pct_avg_5) * 2)
                    ELSE 0
                END)
                + (CASE
                    WHEN m.pct_avg_5 IS NOT NULL AND m.pct_avg_prev_5 IS NOT NULL AND m.pct_avg_5 > m.pct_avg_prev_5
                    THEN LEAST(9, 3 + (m.pct_avg_5 - m.pct_avg_prev_5) * 1.5)
                    ELSE 0
                END)
            )
        ) AS score_pct_trend,
        LEAST(
            25,
            GREATEST(
                0,
                (
                    (CASE WHEN m.delivery_qty IS NOT NULL AND m.qty_avg_3 IS NOT NULL AND m.delivery_qty > m.qty_avg_3 THEN 6 ELSE 0 END)
                    + (CASE WHEN m.qty_avg_3 IS NOT NULL AND m.qty_avg_5 IS NOT NULL AND m.qty_avg_3 > m.qty_avg_5 THEN 6 ELSE 0 END)
                    + (CASE WHEN m.qty_avg_5 IS NOT NULL AND m.qty_avg_prev_5 IS NOT NULL AND m.qty_avg_5 > m.qty_avg_prev_5 THEN 5 ELSE 0 END)
                    + (CASE WHEN m.delivery_qty IS NOT NULL AND m.qty_avg_20 IS NOT NULL AND m.delivery_qty > m.qty_avg_20 THEN 8 ELSE 0 END)
                    - (CASE
                        WHEN m.delivery_pct >= 40
                         AND m.delivery_qty IS NOT NULL
                         AND m.qty_avg_20 IS NOT NULL
                         AND m.delivery_qty < m.qty_avg_20
                        THEN 5
                        ELSE 0
                    END)
                )
            )
        ) AS score_qty_trend,
        LEAST(
            10,
            GREATEST(
                0,
                CASE
                    WHEN m.price IS NULL THEN 5
                    ELSE
                        (CASE
                            WHEN m.prev_price IS NULL THEN 2.5
                            WHEN m.price > m.prev_price THEN 5
                            ELSE 0
                        END)
                        + (CASE
                            WHEN m.price_high_20 IS NULL OR m.price_high_20 = 0 THEN 2.5
                            WHEN m.price >= m.price_high_20 * 0.98 THEN 5
                            ELSE 0
                        END)
                END
            )
        ) AS score_price_confirm,
        GREATEST(
            0,
            10
            - (CASE
                WHEN m.delivery_pct IS NOT NULL
                 AND m.pct_avg_3 IS NOT NULL
                 AND m.delivery_pct > m.pct_avg_3 * 1.40
                 AND (m.pct_avg_5 IS NULL OR m.pct_avg_prev_5 IS NULL OR m.pct_avg_3 <= m.pct_avg_5 OR m.pct_avg_5 <= m.pct_avg_prev_5)
                THEN 4
                ELSE 0
            END)
            - (CASE
                WHEN m.delivery_qty IS NOT NULL
                 AND m.qty_avg_20 IS NOT NULL
                 AND m.qty_avg_20 > 0
                 AND m.delivery_qty < (m.qty_avg_20 * 0.30)
                THEN 3
                WHEN m.delivery_qty IS NOT NULL
                 AND m.qty_avg_20 IS NULL
                 AND m.delivery_qty < 10000
                THEN 2
                ELSE 0
            END)
            - (CASE
                WHEN m.delivery_pct >= 45
                 AND m.price IS NOT NULL
                 AND m.prev_price IS NOT NULL
                 AND m.price < m.prev_price
                 AND m.delivery_qty IS NOT NULL
                 AND m.qty_avg_3 IS NOT NULL
                 AND m.delivery_qty < m.qty_avg_3
                THEN 3
                ELSE 0
            END)
            - (CASE
                WHEN m.history_days < 5 THEN 2
                ELSE 0
            END)
        ) AS score_stability
    FROM metrics m
),
scored AS (
    SELECT
        c.symbol,
        c.price,
        c.trading_date,
        c.ltc_date,
        c.t_d,
        c.delivery_qty,
        c.delivery_pct,
        c.history_days,
        CASE WHEN c.history_days < 5 THEN 'LIMITED_HISTORY' ELSE 'FULL_HISTORY' END AS history_status,
        CASE
            WHEN c.delivery_pct IS NULL OR c.delivery_qty IS NULL THEN 0
            ELSE ROUND(
                LEAST(
                    100,
                    GREATEST(
                        0,
                        c.score_pct_level
                        + c.score_pct_trend
                        + c.score_qty_trend
                        + c.score_price_confirm
                        + c.score_stability
                    )
                )
            )
        END AS delivery_score,
        CASE
            WHEN c.delivery_qty IS NOT NULL AND c.qty_avg_3 IS NOT NULL AND c.delivery_qty > c.qty_avg_3 THEN 1
            ELSE 0
        END AS delivery_qty_rising
    FROM component_scores c
),
classified AS (
    SELECT
        s.symbol,
        s.price,
        s.trading_date,
        s.ltc_date,
        s.t_d,
        s.delivery_qty,
        s.delivery_pct,
        s.delivery_score,
        s.history_status,
        s.delivery_qty_rising,
        CASE
            WHEN s.delivery_score <= 30 THEN 'Weak Delivery'
            WHEN s.delivery_score <= 50 THEN 'Watchlist'
            WHEN s.delivery_score <= 70 THEN 'Positive Delivery Build-up'
            WHEN s.delivery_score <= 85 THEN 'Strong Accumulation'
            ELSE 'Very Strong Accumulation'
        END AS delivery_status
    FROM scored s
),
filtered AS (
    SELECT
        c.symbol,
        c.price,
        c.trading_date,
        c.ltc_date,
        c.t_d,
        c.delivery_qty,
        c.delivery_pct,
        c.delivery_score,
        c.delivery_status,
        c.history_status,
        c.delivery_qty_rising
    FROM classified c
    WHERE 1 = 1
{filter_sql}
)
"""


def _build_filter_sql(
    *,
    symbol: Optional[str],
    trading_date: Optional[date],
    start_date: Optional[date],
    end_date: Optional[date],
    td: Optional[int],
    min_delivery_pct: Optional[float],
    delivery_pct_eq_100: bool,
    min_delivery_score: Optional[float],
    latest_only: bool,
    strong_only: bool,
    delivery_status: Optional[str],
) -> Tuple[str, Dict[str, Any]]:
    clauses: list[str] = []
    binds: Dict[str, Any] = {}

    symbol_text = str(symbol or "").strip().upper()
    if symbol_text:
        clauses.append("  AND c.symbol LIKE :symbol_like")
        binds["symbol_like"] = f"%{symbol_text}%"

    if latest_only:
        clauses.append("  AND c.t_d = 0")
    else:
        if trading_date:
            clauses.append("  AND c.trading_date = :trading_date")
            binds["trading_date"] = trading_date
        else:
            resolved_start_date = start_date or end_date
            resolved_end_date = end_date or start_date
            if resolved_start_date and resolved_end_date:
                clauses.append("  AND c.trading_date BETWEEN :start_date AND :end_date")
                binds["start_date"] = resolved_start_date
                binds["end_date"] = resolved_end_date

        if td is not None:
            clauses.append("  AND c.t_d = :td")
            binds["td"] = td

    if min_delivery_pct is not None:
        clauses.append("  AND c.delivery_pct >= :min_delivery_pct")
        binds["min_delivery_pct"] = float(min_delivery_pct)

    if delivery_pct_eq_100:
        clauses.append("  AND ROUND(NVL(c.delivery_pct, 0), 2) = 100")

    if min_delivery_score is not None:
        clauses.append("  AND c.delivery_score >= :min_delivery_score")
        binds["min_delivery_score"] = float(min_delivery_score)

    if strong_only:
        clauses.append("  AND c.delivery_status = 'Strong Accumulation'")

    status_text = str(delivery_status or "").strip()
    if status_text:
        clauses.append("  AND c.delivery_status = :delivery_status")
        binds["delivery_status"] = status_text

    sql = ""
    if clauses:
        sql = "\n" + "\n".join(clauses)
    return sql, binds


def _build_source_filter_sql(
    *,
    symbol_col: str,
    date_col: str,
    symbol: Optional[str],
    trading_date: Optional[date],
    start_date: Optional[date],
    end_date: Optional[date],
    latest_only: bool,
) -> Tuple[str, Dict[str, Any]]:
    clauses: list[str] = []
    binds: Dict[str, Any] = {}

    symbol_text = str(symbol or "").strip().upper()
    if symbol_text:
        clauses.append(f"  AND UPPER(TRIM(src.{symbol_col})) LIKE :src_symbol_like")
        binds["src_symbol_like"] = f"%{symbol_text}%"

    resolved_start_date: Optional[date] = None
    resolved_end_date: Optional[date] = None
    if not latest_only:
        if trading_date:
            resolved_start_date = trading_date
            resolved_end_date = trading_date
        elif start_date or end_date:
            resolved_start_date = start_date or end_date
            resolved_end_date = end_date or start_date

    if resolved_start_date and resolved_end_date:
        lookback_start = resolved_start_date - timedelta(days=_SNAPSHOT_LOOKBACK_DAYS)
        clauses.append(f"  AND CAST(src.{date_col} AS DATE) BETWEEN :src_start_date AND :src_end_date")
        binds["src_start_date"] = lookback_start
        binds["src_end_date"] = resolved_end_date

    sql = ""
    if clauses:
        sql = "\n" + "\n".join(clauses)
    return sql, binds


def _build_period_snapshot_key(
    *,
    symbol: Optional[str],
    trading_date: Optional[date],
    start_date: Optional[date],
    end_date: Optional[date],
    td: Optional[int],
    min_delivery_pct: Optional[float],
    delivery_pct_eq_100: bool,
    min_delivery_score: Optional[float],
    latest_only: bool,
    strong_only: bool,
    delivery_status: Optional[str],
    sort_by: Optional[str],
    sort_dir: Optional[str],
    latest_ltc_date: Optional[str],
) -> str:
    payload = {
        "v": _DELIVERY_SUMMARY_SCHEMA_VERSION,
        "table": _DELIVERY_TABLE,
        "price_table": _OHLC_TABLE,
        "force_price_fallback": bool(_FORCE_PRICE_FALLBACK),
        "symbol": str(symbol or "").strip().upper(),
        "trading_date": trading_date.isoformat() if isinstance(trading_date, date) else "",
        "start_date": start_date.isoformat() if isinstance(start_date, date) else "",
        "end_date": end_date.isoformat() if isinstance(end_date, date) else "",
        "td": int(td) if td is not None else None,
        "min_delivery_pct": float(min_delivery_pct) if min_delivery_pct is not None else None,
        "delivery_pct_eq_100": bool(delivery_pct_eq_100),
        "min_delivery_score": float(min_delivery_score) if min_delivery_score is not None else None,
        "latest_only": bool(latest_only),
        "strong_only": bool(strong_only),
        "delivery_status": str(delivery_status or "").strip(),
        "sort_by": _normalize_key(sort_by or _DEFAULT_SORT),
        "sort_dir": "asc" if str(sort_dir or _DEFAULT_SORT_DIR).strip().lower() == "asc" else "desc",
        "latest_ltc_date": str(latest_ltc_date or "").strip(),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return f"delivery-period:{digest}"


def _build_delivery_request_cache_key(
    *,
    symbol: Optional[str],
    trading_date: Optional[date],
    start_date: Optional[date],
    end_date: Optional[date],
    latest_only: bool,
    min_delivery_pct: Optional[float],
    delivery_pct_eq_100: bool,
    min_delivery_score: Optional[float],
    strong_only: bool,
    page: int,
    page_size: int,
    sort_by: Optional[str],
    sort_dir: Optional[str],
    latest_ltc_date: Optional[str],
) -> str:
    payload = {
        "v": _DELIVERY_SUMMARY_SCHEMA_VERSION,
        "table": _DELIVERY_TABLE,
        "price_table": _OHLC_TABLE,
        "force_price_fallback": bool(_FORCE_PRICE_FALLBACK),
        "symbol": str(symbol or "").strip().upper(),
        "trading_date": trading_date.isoformat() if isinstance(trading_date, date) else "",
        "start_date": start_date.isoformat() if isinstance(start_date, date) else "",
        "end_date": end_date.isoformat() if isinstance(end_date, date) else "",
        "latest_only": bool(latest_only),
        "min_delivery_pct": float(min_delivery_pct) if min_delivery_pct is not None else None,
        "delivery_pct_eq_100": bool(delivery_pct_eq_100),
        "min_delivery_score": float(min_delivery_score) if min_delivery_score is not None else None,
        "strong_only": bool(strong_only),
        "page": int(page),
        "page_size": int(page_size),
        "sort_by": _normalize_key(sort_by or _DEFAULT_SORT),
        "sort_dir": "asc" if str(sort_dir or _DEFAULT_SORT_DIR).strip().lower() == "asc" else "desc",
        "latest_ltc_date": str(latest_ltc_date or "").strip(),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return f"delivery-response:{digest}"


def _should_inline_latest_summary(
    *,
    snapshot_enabled: bool,
    latest_only: bool,
    symbol: Optional[str],
    min_delivery_pct: Optional[float],
    delivery_pct_eq_100: bool,
    min_delivery_score: Optional[float],
    strong_only: bool,
    delivery_status: Optional[str],
) -> bool:
    return (
        not snapshot_enabled
        and latest_only
        and not str(symbol or "").strip()
        and min_delivery_pct is None
        and not delivery_pct_eq_100
        and min_delivery_score is None
        and not strong_only
        and not str(delivery_status or "").strip()
    )


def _fetch_latest_delivery_summary(
    conn,
    *,
    projection: Dict[str, Any],
    price_source: Optional[Dict[str, str]],
    latest_ltc_date: Optional[str],
) -> Dict[str, Any]:
    latest_ltc_date_obj = _to_date(latest_ltc_date)
    if latest_ltc_date_obj is None:
        return {
            "ltc_date": None,
            "total_stocks": 0,
            "delivery_pct_eq_100_count": 0,
            "delivery_pct_gt_90_count": 0,
            "delivery_pct_gt_80_count": 0,
            "delivery_pct_gt_70_count": 0,
            "delivery_pct_gt_60_count": 0,
            "delivery_pct_gt_50_count": 0,
            "delivery_pct_gt_40_count": 0,
            "delivery_score_gt_100_count": 0,
            "delivery_score_gt_90_count": 0,
            "delivery_score_gt_80_count": 0,
            "delivery_score_gt_70_count": 0,
            "delivery_score_gt_60_count": 0,
            "delivery_score_gt_50_count": 0,
            "strong_accumulation_count": 0,
        }

    summary_recent_td_limit = _derive_recent_td_limit(
        trading_date=None,
        start_date=None,
        end_date=None,
        td=None,
        latest_only=True,
    )
    summary_cte_sql = _build_cte_sql(
        projection=projection,
        price_source=price_source,
        filter_sql="",
        source_filter_sql="",
        recent_td_limit=summary_recent_td_limit,
        use_filtered_date_rank=False,
    )
    symbol_key_expr = _normalized_delivery_symbol_expr("c.symbol")
    summary_sql = f"""
{summary_cte_sql}
SELECT
    MAX(x.latest_ltc_date) AS latest_ltc_date,
    COUNT(DISTINCT x.symbol_key) AS total_stocks,
    COUNT(DISTINCT CASE WHEN ROUND(NVL(x.delivery_pct, 0), 2) = 100 THEN x.symbol_key END) AS delivery_pct_eq_100_count,
    COUNT(DISTINCT CASE WHEN NVL(x.delivery_pct, 0) > 90 THEN x.symbol_key END) AS delivery_pct_gt_90_count,
    COUNT(DISTINCT CASE WHEN NVL(x.delivery_pct, 0) > 80 THEN x.symbol_key END) AS delivery_pct_gt_80_count,
    COUNT(DISTINCT CASE WHEN NVL(x.delivery_pct, 0) > 70 THEN x.symbol_key END) AS delivery_pct_gt_70_count,
    COUNT(DISTINCT CASE WHEN NVL(x.delivery_pct, 0) > 60 THEN x.symbol_key END) AS delivery_pct_gt_60_count,
    COUNT(DISTINCT CASE WHEN NVL(x.delivery_pct, 0) > 50 THEN x.symbol_key END) AS delivery_pct_gt_50_count,
    COUNT(DISTINCT CASE WHEN NVL(x.delivery_pct, 0) > 40 THEN x.symbol_key END) AS delivery_pct_gt_40_count,
    COUNT(DISTINCT CASE WHEN NVL(x.delivery_score, 0) > 100 THEN x.symbol_key END) AS delivery_score_gt_100_count,
    COUNT(DISTINCT CASE WHEN NVL(x.delivery_score, 0) > 90 THEN x.symbol_key END) AS delivery_score_gt_90_count,
    COUNT(DISTINCT CASE WHEN NVL(x.delivery_score, 0) > 80 THEN x.symbol_key END) AS delivery_score_gt_80_count,
    COUNT(DISTINCT CASE WHEN NVL(x.delivery_score, 0) > 70 THEN x.symbol_key END) AS delivery_score_gt_70_count,
    COUNT(DISTINCT CASE WHEN NVL(x.delivery_score, 0) > 60 THEN x.symbol_key END) AS delivery_score_gt_60_count,
    COUNT(DISTINCT CASE WHEN NVL(x.delivery_score, 0) > 50 THEN x.symbol_key END) AS delivery_score_gt_50_count,
    COUNT(DISTINCT CASE WHEN x.delivery_status = 'Strong Accumulation' THEN x.symbol_key END) AS strong_accumulation_count
FROM (
    SELECT
        {symbol_key_expr} AS symbol_key,
        c.ltc_date AS latest_ltc_date,
        c.delivery_pct,
        c.delivery_score,
        c.delivery_status
    FROM classified c
    WHERE c.ltc_date = :summary_latest_ltc_date
) x
"""
    summary_binds: Dict[str, Any] = {
        "summary_latest_ltc_date": latest_ltc_date_obj,
    }
    if summary_recent_td_limit is not None:
        summary_binds["recent_td_limit"] = int(summary_recent_td_limit)

    with conn.cursor() as cur:
        cur.execute(summary_sql, summary_binds)
        rows = fetchall_dict(cur)

    if not rows:
        return {
            "ltc_date": latest_ltc_date_obj.isoformat(),
            "total_stocks": 0,
            "delivery_pct_eq_100_count": 0,
            "delivery_pct_gt_90_count": 0,
            "delivery_pct_gt_80_count": 0,
            "delivery_pct_gt_70_count": 0,
            "delivery_pct_gt_60_count": 0,
            "delivery_pct_gt_50_count": 0,
            "delivery_pct_gt_40_count": 0,
            "delivery_score_gt_100_count": 0,
            "delivery_score_gt_90_count": 0,
            "delivery_score_gt_80_count": 0,
            "delivery_score_gt_70_count": 0,
            "delivery_score_gt_60_count": 0,
            "delivery_score_gt_50_count": 0,
            "strong_accumulation_count": 0,
        }

    result = rows[0]
    return {
        "ltc_date": _date_to_iso(result.get("latest_ltc_date")) or latest_ltc_date_obj.isoformat(),
        "total_stocks": max(0, _to_int(result.get("total_stocks"), 0)),
        "delivery_pct_eq_100_count": max(0, _to_int(result.get("delivery_pct_eq_100_count"), 0)),
        "delivery_pct_gt_90_count": max(0, _to_int(result.get("delivery_pct_gt_90_count"), 0)),
        "delivery_pct_gt_80_count": max(0, _to_int(result.get("delivery_pct_gt_80_count"), 0)),
        "delivery_pct_gt_70_count": max(0, _to_int(result.get("delivery_pct_gt_70_count"), 0)),
        "delivery_pct_gt_60_count": max(0, _to_int(result.get("delivery_pct_gt_60_count"), 0)),
        "delivery_pct_gt_50_count": max(0, _to_int(result.get("delivery_pct_gt_50_count"), 0)),
        "delivery_pct_gt_40_count": max(0, _to_int(result.get("delivery_pct_gt_40_count"), 0)),
        "delivery_score_gt_100_count": max(0, _to_int(result.get("delivery_score_gt_100_count"), 0)),
        "delivery_score_gt_90_count": max(0, _to_int(result.get("delivery_score_gt_90_count"), 0)),
        "delivery_score_gt_80_count": max(0, _to_int(result.get("delivery_score_gt_80_count"), 0)),
        "delivery_score_gt_70_count": max(0, _to_int(result.get("delivery_score_gt_70_count"), 0)),
        "delivery_score_gt_60_count": max(0, _to_int(result.get("delivery_score_gt_60_count"), 0)),
        "delivery_score_gt_50_count": max(0, _to_int(result.get("delivery_score_gt_50_count"), 0)),
        "strong_accumulation_count": max(0, _to_int(result.get("strong_accumulation_count"), 0)),
    }


def fetch_latest_delivery_scores_for_symbols(symbols: Iterable[Any]) -> Dict[str, Dict[str, Any]]:
    requested_symbols = {
        normalized
        for normalized in (normalize_delivery_symbol(symbol) for symbol in symbols)
        if normalized
    }
    if not requested_symbols:
        return {}

    latest_scores: Dict[str, Dict[str, Any]] = {}
    with pool.acquire() as conn:
        projection, runtime_price_source = _resolve_runtime_metadata(conn)
        query_price_source = runtime_price_source if (_FORCE_PRICE_FALLBACK and runtime_price_source) else None
        filtered_symbol_expr = _normalized_delivery_symbol_expr("f.symbol")
        recent_td_limit = _derive_recent_td_limit(
            trading_date=None,
            start_date=None,
            end_date=None,
            td=None,
            latest_only=True,
        )

        binds: Dict[str, Any] = {}
        if recent_td_limit is not None:
            binds["recent_td_limit"] = int(recent_td_limit)
        cte_sql = _build_cte_sql(
            projection=projection,
            price_source=query_price_source,
            filter_sql="",
            source_filter_sql="",
            recent_td_limit=recent_td_limit,
            use_filtered_date_rank=False,
        )
        sql = f"""
{cte_sql}
SELECT
    ranked.symbol_key,
    ranked.symbol,
    ranked.ltc_date,
    ranked.delivery_score,
    ranked.delivery_status
FROM (
    SELECT
        {filtered_symbol_expr} AS symbol_key,
        f.symbol,
        f.ltc_date,
        f.delivery_score,
        f.delivery_status,
        ROW_NUMBER() OVER (
            PARTITION BY {filtered_symbol_expr}
            ORDER BY f.ltc_date DESC NULLS LAST, f.delivery_score DESC NULLS LAST, f.symbol ASC
        ) AS rn
    FROM filtered f
) ranked
WHERE ranked.rn = 1
"""
        with conn.cursor() as cur:
            cur.execute(sql, binds)
            for row in fetchall_dict(cur):
                symbol_key = normalize_delivery_symbol(row.get("symbol_key"))
                if not symbol_key or symbol_key not in requested_symbols:
                    continue
                latest_scores[symbol_key] = {
                    "symbol": (row.get("symbol") or "").strip(),
                    "ltc_date": _date_to_iso(row.get("ltc_date")),
                    "delivery_score": _to_int(row.get("delivery_score"), 0),
                    "delivery_status": row.get("delivery_status"),
                }

    return latest_scores


def _parse_page(page: Any) -> int:
    value = _to_int(page, 1)
    return max(1, value)


def _parse_page_size(page_size: Any) -> int:
    value = _to_int(page_size, _DEFAULT_PAGE_SIZE)
    if value < 1:
        value = _DEFAULT_PAGE_SIZE
    return min(_MAX_PAGE_SIZE, value)


def fetch_delivery_page(
    *,
    symbol: Optional[str] = None,
    trading_date: Optional[date] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    td: Optional[int] = None,
    min_delivery_pct: Optional[float] = None,
    delivery_pct_eq_100: bool = False,
    min_delivery_score: Optional[float] = None,
    latest_only: bool = True,
    strong_only: bool = False,
    delivery_status: Optional[str] = None,
    page: int = 1,
    page_size: int = _DEFAULT_PAGE_SIZE,
    sort_by: Optional[str] = None,
    sort_dir: Optional[str] = None,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    started = time.perf_counter()
    resolved_page = _parse_page(page)
    resolved_page_size = _parse_page_size(page_size)
    resolved_sort_sql = _resolve_sort(sort_by, sort_dir)
    has_explicit_date_scope = any(
        (
            trading_date is not None,
            start_date is not None,
            end_date is not None,
            td is not None,
        )
    )
    effective_latest_only = bool(latest_only) or not has_explicit_date_scope
    effective_trading_date = None if effective_latest_only else trading_date
    effective_start_date = None if effective_latest_only else start_date
    effective_end_date = None if effective_latest_only else end_date
    symbol_text = str(symbol or "").strip().upper()
    snapshot_enabled = bool(symbol_text) and (effective_start_date is not None or effective_end_date is not None)
    snapshot_key = ""
    snapshot_hit = False
    cached_flag = False
    snapshot_flag = False
    db_elapsed_ms = 0
    latest_ltc_date_token: Optional[str] = None
    inline_latest_summary = _should_inline_latest_summary(
        snapshot_enabled=snapshot_enabled,
        latest_only=effective_latest_only,
        symbol=symbol,
        min_delivery_pct=min_delivery_pct,
        delivery_pct_eq_100=delivery_pct_eq_100,
        min_delivery_score=min_delivery_score,
        strong_only=bool(strong_only),
        delivery_status=delivery_status,
    )

    try:
        with pool.acquire() as cache_conn:
            projection_for_cache, _ = _resolve_runtime_metadata(cache_conn)
            latest_ltc_date_token = _fetch_latest_ltc_date(cache_conn, projection=projection_for_cache)
    except Exception:
        _logger.warning("Unable to resolve delivery latest_ltc_date token for cache key.", exc_info=True)

    normalized_sort_by = _normalize_key(sort_by or _DEFAULT_SORT)
    normalized_sort_dir = "asc" if str(sort_dir or _DEFAULT_SORT_DIR).strip().lower() == "asc" else "desc"
    request_cache_key = _build_delivery_request_cache_key(
        symbol=symbol,
        trading_date=effective_trading_date,
        start_date=effective_start_date,
        end_date=effective_end_date,
        latest_only=effective_latest_only,
        min_delivery_pct=min_delivery_pct,
        delivery_pct_eq_100=delivery_pct_eq_100,
        min_delivery_score=min_delivery_score,
        strong_only=bool(strong_only),
        page=resolved_page,
        page_size=resolved_page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
        latest_ltc_date=latest_ltc_date_token,
    )

    cached_response = _delivery_response_cache.get(request_cache_key)
    if isinstance(cached_response, dict):
        response = deepcopy(cached_response)
        meta = response.setdefault("meta", {})
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        meta["elapsed_ms"] = elapsed_ms
        meta["cache_hit"] = True
        meta["cache_key"] = request_cache_key
        meta["ttl_seconds"] = _DELIVERY_CACHE_TTL_SEC
        meta["latest_ltc_date"] = latest_ltc_date_token
        if "cached_at" not in meta:
            meta["cached_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        _logger.info(
            "delivery_query request_id=%s cache=hit cache_key=%s page=%s page_size=%s rows=%s total=%s db_ms=%s total_ms=%s",
            request_id or "",
            request_cache_key,
            resolved_page,
            resolved_page_size,
            len(response.get("data") or []),
            _to_int(response.get("total_records"), 0),
            0,
            elapsed_ms,
        )
        return response

    if snapshot_enabled:
        snapshot_key = _build_period_snapshot_key(
            symbol=symbol,
            trading_date=effective_trading_date,
            start_date=effective_start_date,
            end_date=effective_end_date,
            td=td,
            min_delivery_pct=min_delivery_pct,
            delivery_pct_eq_100=delivery_pct_eq_100,
            min_delivery_score=min_delivery_score,
            latest_only=effective_latest_only,
            strong_only=bool(strong_only),
            delivery_status=delivery_status,
            sort_by=sort_by,
            sort_dir=sort_dir,
            latest_ltc_date=latest_ltc_date_token,
        )
        cached_snapshot = _period_snapshot_cache.get(snapshot_key)
        if isinstance(cached_snapshot, dict):
            snapshot_rows = cached_snapshot.get("rows") or []
            total_records = max(0, _to_int(cached_snapshot.get("total_records"), len(snapshot_rows)))
            summary_total_stocks = max(0, _to_int(cached_snapshot.get("summary_total_stocks"), total_records))
            pct_eq_100_count = max(
                0,
                _to_int(
                    cached_snapshot.get("summary_delivery_pct_eq_100_count"),
                    _to_int(cached_snapshot.get("delivery_pct_eq_100_count"), 0),
                ),
            )
            pct_gt_90_count = max(
                0,
                _to_int(
                    cached_snapshot.get("summary_delivery_pct_gt_90_count"),
                    _to_int(cached_snapshot.get("delivery_pct_gt_90_count"), 0),
                ),
            )
            pct_gt_80_count = max(
                0,
                _to_int(
                    cached_snapshot.get("summary_delivery_pct_gt_80_count"),
                    _to_int(cached_snapshot.get("delivery_pct_gt_80_count"), 0),
                ),
            )
            pct_gt_70_count = max(
                0,
                _to_int(
                    cached_snapshot.get("summary_delivery_pct_gt_70_count"),
                    _to_int(cached_snapshot.get("delivery_pct_gt_70_count"), 0),
                ),
            )
            pct_gt_60_count = max(
                0,
                _to_int(
                    cached_snapshot.get("summary_delivery_pct_gt_60_count"),
                    _to_int(cached_snapshot.get("delivery_pct_gt_60_count"), 0),
                ),
            )
            pct_gt_50_count = max(
                0,
                _to_int(
                    cached_snapshot.get("summary_delivery_pct_gt_50_count"),
                    _to_int(cached_snapshot.get("delivery_pct_gt_50_count"), 0),
                ),
            )
            pct_gt_40_count = max(
                0,
                _to_int(
                    cached_snapshot.get("summary_delivery_pct_gt_40_count"),
                    _to_int(cached_snapshot.get("delivery_pct_gt_40_count"), 0),
                ),
            )
            score_gt_100_count = max(0, _to_int(cached_snapshot.get("summary_delivery_score_gt_100_count"), _to_int(cached_snapshot.get("delivery_score_gt_100_count"), 0)))
            score_gt_90_count = max(0, _to_int(cached_snapshot.get("summary_delivery_score_gt_90_count"), _to_int(cached_snapshot.get("delivery_score_gt_90_count"), 0)))
            score_gt_80_count = max(0, _to_int(cached_snapshot.get("summary_delivery_score_gt_80_count"), _to_int(cached_snapshot.get("delivery_score_gt_80_count"), 0)))
            score_gt_70_count = max(0, _to_int(cached_snapshot.get("summary_delivery_score_gt_70_count"), _to_int(cached_snapshot.get("delivery_score_gt_70_count"), 0)))
            score_gt_60_count = max(0, _to_int(cached_snapshot.get("summary_delivery_score_gt_60_count"), _to_int(cached_snapshot.get("delivery_score_gt_60_count"), 0)))
            score_gt_50_count = max(0, _to_int(cached_snapshot.get("summary_delivery_score_gt_50_count"), _to_int(cached_snapshot.get("delivery_score_gt_50_count"), 0)))
            strong_count = max(
                0,
                _to_int(
                    cached_snapshot.get("summary_strong_accumulation_count"),
                    _to_int(cached_snapshot.get("strong_accumulation_count"), 0),
                ),
            )
            ltc_date_global = (
                _date_to_iso(cached_snapshot.get("summary_ltc_date"))
                or _date_to_iso(cached_snapshot.get("ltc_date_global"))
                or latest_ltc_date_token
            )
            offset_rows = (resolved_page - 1) * resolved_page_size
            paged_rows = snapshot_rows[offset_rows : offset_rows + resolved_page_size]
            output_rows: list[Dict[str, Any]] = []
            for index, row in enumerate(paged_rows, start=offset_rows + 1):
                item = dict(row)
                item["s_no"] = index
                output_rows.append(item)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            response_payload = {
                "status": "success",
                "ltc_date": ltc_date_global,
                "page": resolved_page,
                "page_size": resolved_page_size,
                "total_records": total_records,
                "summary": {
                    "total_stocks": summary_total_stocks,
                    "delivery_pct_eq_100_count": pct_eq_100_count,
                    "delivery_pct_gt_90_count": pct_gt_90_count,
                    "delivery_pct_gt_80_count": pct_gt_80_count,
                    "delivery_pct_gt_70_count": pct_gt_70_count,
                    "delivery_pct_gt_60_count": pct_gt_60_count,
                    "delivery_pct_gt_50_count": pct_gt_50_count,
                    "delivery_pct_gt_40_count": pct_gt_40_count,
                    "delivery_score_gt_100_count": score_gt_100_count,
                    "delivery_score_gt_90_count": score_gt_90_count,
                    "delivery_score_gt_80_count": score_gt_80_count,
                    "delivery_score_gt_70_count": score_gt_70_count,
                    "delivery_score_gt_60_count": score_gt_60_count,
                    "delivery_score_gt_50_count": score_gt_50_count,
                    "strong_accumulation_count": strong_count,
                },
                "data": output_rows,
                "cached": True,
                "snapshot": True,
                "meta": {
                    "elapsed_ms": elapsed_ms,
                    "sort_by": normalized_sort_by,
                    "sort_dir": normalized_sort_dir,
                    "snapshot_hit": True,
                    "cache_hit": False,
                    "cache_key": request_cache_key,
                    "latest_ltc_date": latest_ltc_date_token,
                    "cached_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "ttl_seconds": _DELIVERY_CACHE_TTL_SEC,
                    "db_elapsed_ms": 0,
                },
            }
            _delivery_response_cache.set(request_cache_key, deepcopy(response_payload))
            _logger.info(
                "delivery_query request_id=%s cache=miss cache_key=%s page=%s page_size=%s rows=%s total=%s db_ms=%s total_ms=%s snapshot=%s snapshot_hit=%s",
                request_id or "",
                request_cache_key,
                resolved_page,
                resolved_page_size,
                len(output_rows),
                total_records,
                0,
                elapsed_ms,
                True,
                True,
            )
            return response_payload

    with pool.acquire() as conn:
        db_started = time.perf_counter()
        projection, runtime_price_source = _resolve_runtime_metadata(conn)
        query_price_source = runtime_price_source if (_FORCE_PRICE_FALLBACK and runtime_price_source) else None
        latest_summary: Dict[str, Any] = {
            "ltc_date": latest_ltc_date_token,
            "total_stocks": 0,
            "delivery_pct_eq_100_count": 0,
            "delivery_pct_gt_90_count": 0,
            "delivery_pct_gt_80_count": 0,
            "delivery_pct_gt_70_count": 0,
            "delivery_pct_gt_60_count": 0,
            "delivery_pct_gt_50_count": 0,
            "delivery_pct_gt_40_count": 0,
            "delivery_score_gt_100_count": 0,
            "delivery_score_gt_90_count": 0,
            "delivery_score_gt_80_count": 0,
            "delivery_score_gt_70_count": 0,
            "delivery_score_gt_60_count": 0,
            "delivery_score_gt_50_count": 0,
            "strong_accumulation_count": 0,
        }
        if not inline_latest_summary:
            latest_summary = _fetch_latest_delivery_summary(
                conn,
                projection=projection,
                price_source=query_price_source,
                latest_ltc_date=latest_ltc_date_token,
            )

        source_filter_sql, bind_source_filters = _build_source_filter_sql(
            symbol_col=projection["symbol_col"],
            date_col=projection["date_col"],
            symbol=symbol,
            trading_date=effective_trading_date,
            start_date=effective_start_date,
            end_date=effective_end_date,
            latest_only=bool(latest_only),
        )
        filter_sql, bind_filters = _build_filter_sql(
            symbol=symbol,
            trading_date=effective_trading_date,
            start_date=effective_start_date,
            end_date=effective_end_date,
            td=td,
            min_delivery_pct=min_delivery_pct,
            delivery_pct_eq_100=delivery_pct_eq_100,
            min_delivery_score=min_delivery_score,
            latest_only=effective_latest_only,
            strong_only=bool(strong_only),
            delivery_status=delivery_status,
        )
        recent_td_limit = _derive_recent_td_limit(
            trading_date=effective_trading_date,
            start_date=effective_start_date,
            end_date=effective_end_date,
            td=td,
            latest_only=effective_latest_only,
        )
        cte_sql = _build_cte_sql(
            projection=projection,
            price_source=query_price_source,
            filter_sql=filter_sql,
            source_filter_sql=source_filter_sql,
            recent_td_limit=recent_td_limit,
            use_filtered_date_rank=bool(snapshot_enabled),
        )

        query_binds = dict(bind_source_filters)
        query_binds.update(bind_filters)
        if recent_td_limit is not None:
            query_binds["recent_td_limit"] = int(recent_td_limit)

        total_records = 0
        summary_total_stocks = max(0, _to_int(latest_summary.get("total_stocks"), 0))
        pct_eq_100_count = max(0, _to_int(latest_summary.get("delivery_pct_eq_100_count"), 0))
        pct_gt_90_count = max(0, _to_int(latest_summary.get("delivery_pct_gt_90_count"), 0))
        pct_gt_80_count = max(0, _to_int(latest_summary.get("delivery_pct_gt_80_count"), 0))
        pct_gt_70_count = max(0, _to_int(latest_summary.get("delivery_pct_gt_70_count"), 0))
        pct_gt_60_count = max(0, _to_int(latest_summary.get("delivery_pct_gt_60_count"), 0))
        pct_gt_50_count = max(0, _to_int(latest_summary.get("delivery_pct_gt_50_count"), 0))
        pct_gt_40_count = max(0, _to_int(latest_summary.get("delivery_pct_gt_40_count"), 0))
        score_gt_100_count = max(0, _to_int(latest_summary.get("delivery_score_gt_100_count"), 0))
        score_gt_90_count = max(0, _to_int(latest_summary.get("delivery_score_gt_90_count"), 0))
        score_gt_80_count = max(0, _to_int(latest_summary.get("delivery_score_gt_80_count"), 0))
        score_gt_70_count = max(0, _to_int(latest_summary.get("delivery_score_gt_70_count"), 0))
        score_gt_60_count = max(0, _to_int(latest_summary.get("delivery_score_gt_60_count"), 0))
        score_gt_50_count = max(0, _to_int(latest_summary.get("delivery_score_gt_50_count"), 0))
        strong_count = max(0, _to_int(latest_summary.get("strong_accumulation_count"), 0))
        ltc_date_global: Optional[str] = _date_to_iso(latest_summary.get("ltc_date")) or latest_ltc_date_token

        if snapshot_enabled:
            snapshot_sql = f"""
{cte_sql}
SELECT
    f.symbol,
    f.price,
    f.trading_date,
    f.ltc_date,
    f.t_d,
    f.delivery_qty,
    f.delivery_pct,
    f.delivery_score,
    f.delivery_status,
    f.history_status,
    f.delivery_qty_rising
FROM filtered f
ORDER BY {resolved_sort_sql}
"""
            raw_rows: list[Dict[str, Any]]
            with conn.cursor() as cur:
                cur.execute(snapshot_sql, query_binds)
                raw_rows = fetchall_dict(cur)

            snapshot_rows: list[Dict[str, Any]] = []
            for row in raw_rows:
                ltc_iso = _resolve_ltc_date_iso(row)
                snapshot_rows.append(
                    {
                        "symbol": (row.get("symbol") or "").strip(),
                        "price": _to_number(row.get("price")),
                        "trading_date": _date_to_iso(row.get("trading_date")),
                        "ltc_date": ltc_iso,
                        "t_d": _to_int_optional(row.get("t_d")),
                        "delivery_qty": _to_number(row.get("delivery_qty")),
                        "delivery_pct": _to_number(row.get("delivery_pct")),
                        "delivery_score": _to_int(row.get("delivery_score"), 0),
                        "delivery_status": row.get("delivery_status"),
                        "history_status": row.get("history_status"),
                        "delivery_qty_rising": _to_int(row.get("delivery_qty_rising"), 0) == 1,
                    }
                )

            if snapshot_rows and runtime_price_source and not _FORCE_PRICE_FALLBACK:
                _fill_missing_prices(conn, snapshot_rows, runtime_price_source)

            total_records = len(snapshot_rows)

            if snapshot_key:
                _period_snapshot_cache.set(
                    snapshot_key,
                    {
                        "rows": snapshot_rows,
                        "total_records": total_records,
                        "summary_total_stocks": summary_total_stocks,
                        "summary_delivery_pct_eq_100_count": pct_eq_100_count,
                        "summary_delivery_pct_gt_90_count": pct_gt_90_count,
                        "summary_delivery_pct_gt_80_count": pct_gt_80_count,
                        "summary_delivery_pct_gt_70_count": pct_gt_70_count,
                        "summary_delivery_pct_gt_60_count": pct_gt_60_count,
                        "summary_delivery_pct_gt_50_count": pct_gt_50_count,
                        "summary_delivery_pct_gt_40_count": pct_gt_40_count,
                        "summary_delivery_score_gt_100_count": score_gt_100_count,
                        "summary_delivery_score_gt_90_count": score_gt_90_count,
                        "summary_delivery_score_gt_80_count": score_gt_80_count,
                        "summary_delivery_score_gt_70_count": score_gt_70_count,
                        "summary_delivery_score_gt_60_count": score_gt_60_count,
                        "summary_delivery_score_gt_50_count": score_gt_50_count,
                        "summary_strong_accumulation_count": strong_count,
                        "summary_ltc_date": ltc_date_global,
                    },
                )

            offset_rows = (resolved_page - 1) * resolved_page_size
            paged_rows = snapshot_rows[offset_rows : offset_rows + resolved_page_size]
            output_rows = []
            for index, row in enumerate(paged_rows, start=offset_rows + 1):
                item = dict(row)
                item["s_no"] = index
                output_rows.append(item)
            snapshot_flag = True
            cached_flag = False
            snapshot_hit = False
        else:
            offset_rows = (resolved_page - 1) * resolved_page_size
            page_binds = dict(query_binds)
            page_binds.update(
                {
                    "offset_rows": offset_rows,
                    "page_size_rows": resolved_page_size,
                }
            )

            cte_for_page_sql = cte_sql
            summary_columns_sql = ""
            summary_join_sql = ""
            if inline_latest_summary:
                summary_symbol_expr = _normalized_delivery_symbol_expr("c.symbol")
                cte_for_page_sql = f"""
{cte_sql},
summary_stats AS (
    SELECT
        MAX(c.ltc_date) AS summary_ltc_date,
        COUNT(DISTINCT {summary_symbol_expr}) AS summary_total_stocks,
        COUNT(DISTINCT CASE WHEN ROUND(NVL(c.delivery_pct, 0), 2) = 100 THEN {summary_symbol_expr} END) AS summary_delivery_pct_eq_100_count,
        COUNT(DISTINCT CASE WHEN NVL(c.delivery_pct, 0) > 90 THEN {summary_symbol_expr} END) AS summary_delivery_pct_gt_90_count,
        COUNT(DISTINCT CASE WHEN NVL(c.delivery_pct, 0) > 80 THEN {summary_symbol_expr} END) AS summary_delivery_pct_gt_80_count,
        COUNT(DISTINCT CASE WHEN NVL(c.delivery_pct, 0) > 70 THEN {summary_symbol_expr} END) AS summary_delivery_pct_gt_70_count,
        COUNT(DISTINCT CASE WHEN NVL(c.delivery_pct, 0) > 60 THEN {summary_symbol_expr} END) AS summary_delivery_pct_gt_60_count,
        COUNT(DISTINCT CASE WHEN NVL(c.delivery_pct, 0) > 50 THEN {summary_symbol_expr} END) AS summary_delivery_pct_gt_50_count,
        COUNT(DISTINCT CASE WHEN NVL(c.delivery_pct, 0) > 40 THEN {summary_symbol_expr} END) AS summary_delivery_pct_gt_40_count,
        COUNT(DISTINCT CASE WHEN NVL(c.delivery_score, 0) > 100 THEN {summary_symbol_expr} END) AS summary_delivery_score_gt_100_count,
        COUNT(DISTINCT CASE WHEN NVL(c.delivery_score, 0) > 90 THEN {summary_symbol_expr} END) AS summary_delivery_score_gt_90_count,
        COUNT(DISTINCT CASE WHEN NVL(c.delivery_score, 0) > 80 THEN {summary_symbol_expr} END) AS summary_delivery_score_gt_80_count,
        COUNT(DISTINCT CASE WHEN NVL(c.delivery_score, 0) > 70 THEN {summary_symbol_expr} END) AS summary_delivery_score_gt_70_count,
        COUNT(DISTINCT CASE WHEN NVL(c.delivery_score, 0) > 60 THEN {summary_symbol_expr} END) AS summary_delivery_score_gt_60_count,
        COUNT(DISTINCT CASE WHEN NVL(c.delivery_score, 0) > 50 THEN {summary_symbol_expr} END) AS summary_delivery_score_gt_50_count,
        COUNT(DISTINCT CASE WHEN c.delivery_status = 'Strong Accumulation' THEN {summary_symbol_expr} END) AS summary_strong_accumulation_count
    FROM classified c
    WHERE c.t_d = 0
)
"""
                summary_columns_sql = """,
    ss.summary_ltc_date,
    ss.summary_total_stocks,
    ss.summary_delivery_pct_eq_100_count,
    ss.summary_delivery_pct_gt_90_count,
    ss.summary_delivery_pct_gt_80_count,
    ss.summary_delivery_pct_gt_70_count,
    ss.summary_delivery_pct_gt_60_count,
    ss.summary_delivery_pct_gt_50_count,
    ss.summary_delivery_pct_gt_40_count,
    ss.summary_delivery_score_gt_100_count,
    ss.summary_delivery_score_gt_90_count,
    ss.summary_delivery_score_gt_80_count,
    ss.summary_delivery_score_gt_70_count,
    ss.summary_delivery_score_gt_60_count,
    ss.summary_delivery_score_gt_50_count,
    ss.summary_strong_accumulation_count"""
                summary_join_sql = "CROSS JOIN summary_stats ss"

            page_sql = f"""
{cte_for_page_sql}
SELECT
    f.symbol,
    f.price,
    f.trading_date,
    f.ltc_date,
    f.t_d,
    f.delivery_qty,
    f.delivery_pct,
    f.delivery_score,
    f.delivery_status,
    f.history_status,
    f.delivery_qty_rising,
    COUNT(1) OVER () AS total_records
{summary_columns_sql}
FROM filtered f
{summary_join_sql}
ORDER BY {resolved_sort_sql}
OFFSET :offset_rows ROWS FETCH NEXT :page_size_rows ROWS ONLY
"""

            rows: list[Dict[str, Any]]
            with conn.cursor() as cur:
                cur.execute(page_sql, page_binds)
                rows = fetchall_dict(cur)

            if rows:
                first = rows[0]
                total_records = _to_int(first.get("total_records"), 0)
                if inline_latest_summary:
                    summary_total_stocks = max(0, _to_int(first.get("summary_total_stocks"), 0))
                    pct_eq_100_count = max(0, _to_int(first.get("summary_delivery_pct_eq_100_count"), 0))
                    pct_gt_90_count = max(0, _to_int(first.get("summary_delivery_pct_gt_90_count"), 0))
                    pct_gt_80_count = max(0, _to_int(first.get("summary_delivery_pct_gt_80_count"), 0))
                    pct_gt_70_count = max(0, _to_int(first.get("summary_delivery_pct_gt_70_count"), 0))
                    pct_gt_60_count = max(0, _to_int(first.get("summary_delivery_pct_gt_60_count"), 0))
                    pct_gt_50_count = max(0, _to_int(first.get("summary_delivery_pct_gt_50_count"), 0))
                    pct_gt_40_count = max(0, _to_int(first.get("summary_delivery_pct_gt_40_count"), 0))
                    score_gt_100_count = max(0, _to_int(first.get("summary_delivery_score_gt_100_count"), 0))
                    score_gt_90_count = max(0, _to_int(first.get("summary_delivery_score_gt_90_count"), 0))
                    score_gt_80_count = max(0, _to_int(first.get("summary_delivery_score_gt_80_count"), 0))
                    score_gt_70_count = max(0, _to_int(first.get("summary_delivery_score_gt_70_count"), 0))
                    score_gt_60_count = max(0, _to_int(first.get("summary_delivery_score_gt_60_count"), 0))
                    score_gt_50_count = max(0, _to_int(first.get("summary_delivery_score_gt_50_count"), 0))
                    strong_count = max(0, _to_int(first.get("summary_strong_accumulation_count"), 0))
                    ltc_date_global = _date_to_iso(first.get("summary_ltc_date")) or ltc_date_global
            else:
                if inline_latest_summary:
                    summary_sql = f"""
{cte_for_page_sql}
SELECT
    (SELECT COUNT(1) FROM filtered) AS total_records
{summary_columns_sql}
FROM summary_stats ss
"""
                else:
                    summary_sql = f"""
{cte_sql}
SELECT
    COUNT(1) AS total_records
FROM filtered f
"""
                with conn.cursor() as cur:
                    cur.execute(summary_sql, query_binds)
                    summary_row = fetchall_dict(cur)
                if summary_row:
                    aggregate = summary_row[0]
                    total_records = _to_int(aggregate.get("total_records"), 0)
                    if inline_latest_summary:
                        summary_total_stocks = max(0, _to_int(aggregate.get("summary_total_stocks"), 0))
                        pct_eq_100_count = max(0, _to_int(aggregate.get("summary_delivery_pct_eq_100_count"), 0))
                        pct_gt_90_count = max(0, _to_int(aggregate.get("summary_delivery_pct_gt_90_count"), 0))
                        pct_gt_80_count = max(0, _to_int(aggregate.get("summary_delivery_pct_gt_80_count"), 0))
                        pct_gt_70_count = max(0, _to_int(aggregate.get("summary_delivery_pct_gt_70_count"), 0))
                        pct_gt_60_count = max(0, _to_int(aggregate.get("summary_delivery_pct_gt_60_count"), 0))
                        pct_gt_50_count = max(0, _to_int(aggregate.get("summary_delivery_pct_gt_50_count"), 0))
                        pct_gt_40_count = max(0, _to_int(aggregate.get("summary_delivery_pct_gt_40_count"), 0))
                        score_gt_100_count = max(0, _to_int(aggregate.get("summary_delivery_score_gt_100_count"), 0))
                        score_gt_90_count = max(0, _to_int(aggregate.get("summary_delivery_score_gt_90_count"), 0))
                        score_gt_80_count = max(0, _to_int(aggregate.get("summary_delivery_score_gt_80_count"), 0))
                        score_gt_70_count = max(0, _to_int(aggregate.get("summary_delivery_score_gt_70_count"), 0))
                        score_gt_60_count = max(0, _to_int(aggregate.get("summary_delivery_score_gt_60_count"), 0))
                        score_gt_50_count = max(0, _to_int(aggregate.get("summary_delivery_score_gt_50_count"), 0))
                        strong_count = max(0, _to_int(aggregate.get("summary_strong_accumulation_count"), 0))
                        ltc_date_global = _date_to_iso(aggregate.get("summary_ltc_date")) or ltc_date_global

            output_rows = []
            for index, row in enumerate(rows, start=offset_rows + 1):
                row_ltc_date = _resolve_ltc_date_iso(row)
                output_rows.append(
                    {
                        "s_no": index,
                        "symbol": (row.get("symbol") or "").strip(),
                        "price": _to_number(row.get("price")),
                        "trading_date": _date_to_iso(row.get("trading_date")),
                        "ltc_date": row_ltc_date or ltc_date_global,
                        "t_d": _to_int_optional(row.get("t_d")),
                        "delivery_qty": _to_number(row.get("delivery_qty")),
                        "delivery_pct": _to_number(row.get("delivery_pct")),
                        "delivery_score": _to_int(row.get("delivery_score"), 0),
                        "delivery_status": row.get("delivery_status"),
                        "history_status": row.get("history_status"),
                        "delivery_qty_rising": _to_int(row.get("delivery_qty_rising"), 0) == 1,
                    }
                )

            if output_rows and runtime_price_source and not _FORCE_PRICE_FALLBACK:
                _fill_missing_prices(conn, output_rows, runtime_price_source)
            snapshot_flag = False
            cached_flag = False
            snapshot_hit = False
        db_elapsed_ms = int((time.perf_counter() - db_started) * 1000)

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    response_payload = {
        "status": "success",
        "ltc_date": ltc_date_global,
        "page": resolved_page,
        "page_size": resolved_page_size,
        "total_records": total_records,
        "summary": {
            "total_stocks": summary_total_stocks,
            "delivery_pct_eq_100_count": pct_eq_100_count,
            "delivery_pct_gt_90_count": pct_gt_90_count,
            "delivery_pct_gt_80_count": pct_gt_80_count,
            "delivery_pct_gt_70_count": pct_gt_70_count,
            "delivery_pct_gt_60_count": pct_gt_60_count,
            "delivery_pct_gt_50_count": pct_gt_50_count,
            "delivery_pct_gt_40_count": pct_gt_40_count,
            "delivery_score_gt_100_count": score_gt_100_count,
            "delivery_score_gt_90_count": score_gt_90_count,
            "delivery_score_gt_80_count": score_gt_80_count,
            "delivery_score_gt_70_count": score_gt_70_count,
            "delivery_score_gt_60_count": score_gt_60_count,
            "delivery_score_gt_50_count": score_gt_50_count,
            "strong_accumulation_count": strong_count,
        },
        "data": output_rows,
        "cached": cached_flag,
        "snapshot": snapshot_flag,
        "meta": {
            "elapsed_ms": elapsed_ms,
            "sort_by": normalized_sort_by,
            "sort_dir": normalized_sort_dir,
            "snapshot_hit": snapshot_hit,
            "cache_hit": False,
            "summary_source": "inline" if inline_latest_summary else "prequery",
            "cache_key": request_cache_key,
            "latest_ltc_date": latest_ltc_date_token,
            "cached_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "ttl_seconds": _DELIVERY_CACHE_TTL_SEC,
            "db_elapsed_ms": db_elapsed_ms,
        },
    }
    _delivery_response_cache.set(request_cache_key, deepcopy(response_payload))

    _logger.info(
        "delivery_query request_id=%s cache=miss cache_key=%s symbol=%s trading_date=%s start_date=%s end_date=%s td=%s min_pct=%s min_score=%s latest_only=%s strong_only=%s page=%s page_size=%s sort=%s/%s total=%s db_ms=%s total_ms=%s snapshot=%s snapshot_hit=%s",
        request_id or "",
        request_cache_key,
        symbol,
        effective_trading_date.isoformat() if isinstance(effective_trading_date, date) else None,
        effective_start_date.isoformat() if isinstance(effective_start_date, date) else None,
        effective_end_date.isoformat() if isinstance(effective_end_date, date) else None,
        td,
        min_delivery_pct,
        min_delivery_score,
        effective_latest_only,
        strong_only,
        resolved_page,
        resolved_page_size,
        sort_by or _DEFAULT_SORT,
        sort_dir or _DEFAULT_SORT_DIR,
        total_records,
        db_elapsed_ms,
        elapsed_ms,
        snapshot_flag,
        snapshot_hit,
    )
    return response_payload


__all__ = [
    "fetch_delivery_page",
]
