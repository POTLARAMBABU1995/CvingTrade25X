from __future__ import annotations

import logging
import os
import re
import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, Optional

from db import get_oracle_connection


_logger = logging.getLogger(__name__)

_IDENT_RE = re.compile(r"^[A-Za-z0-9_.$#]+$")
_SOURCE_META_CACHE: dict[str, str] | None = None
_ATH_SOURCE_TABLE = str(os.getenv("ATH_SOURCE_TABLE") or "NSE_NIFTY500_DAILY_RAW_DATA_DEV").strip().upper()
_ATH_SAMPLE_SYMBOLS = ("ABB", "AADHARHFC", "AARTIIND")


def _safe_identifier(value: str, *, allow_dot: bool = False) -> str:
    token = str(value or "").strip()
    if not token:
        raise ValueError("Identifier is empty")
    if allow_dot:
        parts = token.split(".")
        if not parts or any((not _IDENT_RE.fullmatch(part)) for part in parts):
            raise ValueError(f"Unsafe identifier: {token}")
    else:
        if not _IDENT_RE.fullmatch(token):
            raise ValueError(f"Unsafe identifier: {token}")
    return token


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except Exception:
        return None


def _to_iso_date(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return None


def _normalize_symbols(symbols: Iterable[str]) -> list[str]:
    out: set[str] = set()
    for symbol in symbols:
        token = str(symbol or "").strip().upper()
        if not token:
            continue
        if ":" in token:
            token = token.split(":", 1)[1]
        token = token.replace(".NS", "")
        if token.endswith("-EQ"):
            token = token[:-3]
        token = token.strip()
        if token:
            out.add(token)
    return sorted(out)


def _pick_first(columns: set[str], candidates: list[str]) -> Optional[str]:
    for candidate in candidates:
        token = candidate.upper()
        if token in columns:
            return token
    return None


def _normalized_symbol_sql_expr(table_alias: str, symbol_col: str) -> str:
    # Keep Oracle-side symbol normalization aligned with Python normalization:
    # strip prefix before ":", strip ".NS" suffix, strip "-EQ" suffix.
    base = f"UPPER(TRIM({table_alias}.{symbol_col}))"
    without_prefix = f"CASE WHEN INSTR({base}, ':') > 0 THEN SUBSTR({base}, INSTR({base}, ':') + 1) ELSE {base} END"
    without_ns = f"REGEXP_REPLACE({without_prefix}, '\\\\.NS$', '')"
    return f"REGEXP_REPLACE({without_ns}, '-EQ$', '')"


def _normalize_symbol_token(value: Any) -> str:
    normalized = _normalize_symbols([str(value or "")])
    return normalized[0] if normalized else ""


def _symbol_query_variants(symbol: str) -> list[str]:
    token = str(symbol or "").strip().upper()
    if not token:
        return []
    candidates = {
        token,
        f"{token}.NS",
        f"{token}-EQ",
        f"NSE:{token}",
        f"NSE:{token}-EQ",
    }
    return sorted(candidate for candidate in candidates if candidate)


def _symbol_variant_chunks(symbols: list[str], *, max_binds: int = 900) -> list[list[str]]:
    chunks: list[list[str]] = []
    current: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        for variant in _symbol_query_variants(symbol):
            if variant in seen:
                continue
            if len(current) >= max_binds:
                chunks.append(current)
                current = []
            seen.add(variant)
            current.append(variant)
    if current:
        chunks.append(current)
    return chunks


def _merge_ath_record(
    result: dict[str, dict[str, Any]],
    *,
    symbol: Any,
    ath_val: Any,
    ath_date_val: Any,
) -> None:
    symbol_key = _normalize_symbol_token(symbol)
    if not symbol_key:
        return
    ath = _to_float(ath_val)
    ath_date = _to_iso_date(ath_date_val)
    existing = result.get(symbol_key) or {}
    existing_ath = _to_float(existing.get("ath"))
    existing_date = str(existing.get("ath_date") or "")
    if existing_ath is None or (ath is not None and ath > existing_ath) or (
        ath is not None and existing_ath is not None and ath == existing_ath and ath_date and ath_date > existing_date
    ):
        result[symbol_key] = _row_record(ath=ath, ath_date=ath_date)


def _resolve_source_meta() -> dict[str, str]:
    global _SOURCE_META_CACHE
    if _SOURCE_META_CACHE is not None:
        return dict(_SOURCE_META_CACHE)

    schema = str(os.getenv("ORACLE_SCHEMA") or "").strip().upper()
    table = _ATH_SOURCE_TABLE
    qualified_table = f"{schema}.{table}" if schema else table
    qualified_table = _safe_identifier(qualified_table, allow_dot=True)

    conn = get_oracle_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {qualified_table} WHERE ROWNUM = 0")
            columns = {
                str(col[0]).strip().upper()
                for col in (cur.description or [])
                if col and col[0]
            }
    finally:
        conn.close()

    symbol_col = _pick_first(columns, ["SYMBOL", "STOCK", "TRADING_SYMBOL", "TICKER"])
    trade_col = _pick_first(columns, ["TRADING_DATE", "TRADE_DATE", "DATE"])
    high_col = _pick_first(columns, ["HIGH_PRICE", "HIGH", "H", "DAY_HIGH"])
    if not symbol_col or not trade_col or not high_col:
        raise RuntimeError(
            "Unable to resolve ATH source columns. "
            f"symbol={symbol_col}, trade_date={trade_col}, high={high_col}, table={qualified_table}"
        )

    _SOURCE_META_CACHE = {
        "table": qualified_table,
        "source_table": table,
        "symbol_col": _safe_identifier(symbol_col),
        "trade_col": _safe_identifier(trade_col),
        "high_col": _safe_identifier(high_col),
    }
    return dict(_SOURCE_META_CACHE)


def _row_record(ath: Optional[float], ath_date: Optional[str] = None) -> dict[str, Any]:
    return {
        "ath": ath,
        "ath_date": ath_date,
    }


def _query_chunk(
    conn,
    *,
    meta: dict[str, str],
    chunk: list[str],
    as_of_date: Optional[date],
    include_date: bool,
) -> dict[str, dict[str, Any]]:
    binds: dict[str, Any] = {}
    placeholders: list[str] = []
    for index, symbol in enumerate(chunk):
        key = f"sym_{index}"
        placeholders.append(f":{key}")
        binds[key] = symbol

    symbol_expr = f"UPPER(TRIM(t.{meta['symbol_col']}))"
    where_as_of = ""
    if as_of_date is not None:
        binds["as_of_date"] = as_of_date
        where_as_of = f" AND t.{meta['trade_col']} <= :as_of_date"

    if include_date:
        sql = f"""
SELECT
    ranked.symbol,
    ranked.ath,
    ranked.ath_date
FROM (
    SELECT
        {symbol_expr} AS symbol,
        t.{meta['high_col']} AS ath,
        t.{meta['trade_col']} AS ath_date,
        ROW_NUMBER() OVER (
            PARTITION BY {symbol_expr}
            ORDER BY t.{meta['high_col']} DESC, t.{meta['trade_col']} DESC
        ) AS rn
    FROM {meta['table']} t
    WHERE {symbol_expr} IN ({', '.join(placeholders)})
      AND t.{meta['high_col']} IS NOT NULL
      {where_as_of}
) ranked
WHERE ranked.rn = 1
"""
    else:
        sql = f"""
SELECT
    {symbol_expr} AS symbol,
    MAX(t.{meta['high_col']}) AS ath
FROM {meta['table']} t
WHERE {symbol_expr} IN ({', '.join(placeholders)})
  AND t.{meta['high_col']} IS NOT NULL
  {where_as_of}
GROUP BY {symbol_expr}
"""

    result: dict[str, dict[str, Any]] = {}
    with conn.cursor() as cur:
        cur.execute(sql, binds)
        for row in cur.fetchall() or []:
            if include_date:
                symbol, ath_val, ath_date_val = row
            else:
                symbol, ath_val = row
                ath_date_val = None
            _merge_ath_record(
                result,
                symbol=symbol,
                ath_val=ath_val,
                ath_date_val=ath_date_val,
            )
    return result


def _query_all(
    conn,
    *,
    meta: dict[str, str],
    as_of_date: Optional[date],
    include_date: bool,
) -> dict[str, dict[str, Any]]:
    symbol_expr = f"UPPER(TRIM(t.{meta['symbol_col']}))"
    binds: dict[str, Any] = {}
    where_as_of = ""
    if as_of_date is not None:
        binds["as_of_date"] = as_of_date
        where_as_of = f" AND t.{meta['trade_col']} <= :as_of_date"

    if include_date:
        sql = f"""
SELECT
    ranked.symbol,
    ranked.ath,
    ranked.ath_date
FROM (
    SELECT
        {symbol_expr} AS symbol,
        t.{meta['high_col']} AS ath,
        t.{meta['trade_col']} AS ath_date,
        ROW_NUMBER() OVER (
            PARTITION BY {symbol_expr}
            ORDER BY t.{meta['high_col']} DESC, t.{meta['trade_col']} DESC
        ) AS rn
    FROM {meta['table']} t
    WHERE {symbol_expr} IS NOT NULL
      AND t.{meta['high_col']} IS NOT NULL
      {where_as_of}
) ranked
WHERE ranked.rn = 1
"""
    else:
        sql = f"""
SELECT
    {symbol_expr} AS symbol,
    MAX(t.{meta['high_col']}) AS ath
FROM {meta['table']} t
WHERE {symbol_expr} IS NOT NULL
  AND t.{meta['high_col']} IS NOT NULL
  {where_as_of}
GROUP BY {symbol_expr}
"""

    result: dict[str, dict[str, Any]] = {}
    with conn.cursor() as cur:
        cur.execute(sql, binds)
        for row in cur.fetchall() or []:
            if include_date:
                symbol, ath_val, ath_date_val = row
            else:
                symbol, ath_val = row
                ath_date_val = None
            _merge_ath_record(
                result,
                symbol=symbol,
                ath_val=ath_val,
                ath_date_val=ath_date_val,
            )
    return result


def get_all_time_high_for_symbols(
    symbols: Optional[Iterable[str]] = None,
    *,
    as_of_date: Optional[date] = None,
    include_date: bool = False,
    endpoint: str = "unknown",
) -> dict[str, dict[str, Any]]:
    normalized_symbols = _normalize_symbols(symbols or []) if symbols is not None else []
    is_all_symbols_query = symbols is None
    if (not is_all_symbols_query) and (not normalized_symbols):
        return {}

    meta = _resolve_source_meta()
    started = time.perf_counter()
    records: dict[str, dict[str, Any]] = {}

    conn = get_oracle_connection()
    try:
        if is_all_symbols_query:
            records = _query_all(
                conn,
                meta=meta,
                as_of_date=as_of_date,
                include_date=include_date,
            )
        else:
            for chunk in _symbol_variant_chunks(normalized_symbols, max_binds=150):
                records.update(
                    _query_chunk(
                        conn,
                        meta=meta,
                        chunk=chunk,
                        as_of_date=as_of_date,
                        include_date=include_date,
                    )
                )
    finally:
        conn.close()

    if not is_all_symbols_query:
        for symbol in normalized_symbols:
            records.setdefault(symbol, _row_record(ath=None, ath_date=None))

    query_ms = round((time.perf_counter() - started) * 1000.0, 2)
    sample_pairs: list[str] = []
    for symbol in _ATH_SAMPLE_SYMBOLS:
        ath_value = records.get(symbol, {}).get("ath")
        if ath_value is None:
            continue
        sample_pairs.append(f"{symbol}={ath_value:.2f}")
    if not sample_pairs:
        for symbol in sorted(records.keys()):
            ath_value = records.get(symbol, {}).get("ath")
            if ath_value is None:
                continue
            sample_pairs.append(f"{symbol}={ath_value:.2f}")
            if len(sample_pairs) >= 5:
                break

    if is_all_symbols_query:
        missing_symbols = [
            symbol for symbol, payload in records.items()
            if payload.get("ath") is None
        ]
        symbols_count = len(records)
    else:
        missing_symbols = [
            symbol for symbol in normalized_symbols
            if records.get(symbol, {}).get("ath") is None
        ]
        symbols_count = len(normalized_symbols)

    _logger.info("[ATH] source=%s", meta.get("source_table") or meta["table"])
    _logger.info("[ATH] symbols_count=%s", symbols_count)
    _logger.info("[ATH] query_time_ms=%s", query_ms)
    _logger.info(
        "[ATH] endpoint=%s table=%s highColumn=%s includeDate=%s",
        endpoint,
        meta["table"],
        meta["high_col"],
        str(include_date).lower(),
    )
    if sample_pairs:
        _logger.info("[ATH] sample: %s", ", ".join(sample_pairs))
    if missing_symbols:
        for symbol in missing_symbols[:25]:
            _logger.warning("[ATH][WARN] ath missing for symbol=%s", symbol)
        if len(missing_symbols) > 25:
            _logger.warning(
                "[ATH][WARN] endpoint=%s missingAthCount=%s loggedFirst=%s",
                endpoint,
                len(missing_symbols),
                25,
            )

    high_token = meta["high_col"].upper()
    if "HIGH" not in high_token and high_token not in {"H", "DAY_HIGH"}:
        _logger.warning(
            "[ATH][WARN] endpoint=%s non_high_column_detected=%s",
            endpoint,
            meta["high_col"],
        )

    return records


def get_ath_map(
    symbols: Optional[Iterable[str]] = None,
    *,
    as_of_date: Optional[date] = None,
    endpoint: str = "unknown",
) -> dict[str, Optional[float]]:
    records = get_all_time_high_for_symbols(
        symbols,
        as_of_date=as_of_date,
        include_date=False,
        endpoint=endpoint,
    )
    return {symbol: _to_float(record.get("ath")) for symbol, record in records.items()}


def log_stale_snapshot_warning(*, endpoint: str, source: str) -> None:
    _logger.warning(
        "[ATH][WARN] stale snapshot/cache detected endpoint=%s source=%s",
        endpoint,
        source,
    )


def get_all_time_high_by_symbol(
    symbol: str,
    *,
    as_of_date: Optional[date] = None,
    include_date: bool = False,
    endpoint: str = "unknown",
) -> dict[str, Any]:
    symbol_key = str(symbol or "").strip().upper()
    if not symbol_key:
        return _row_record(ath=None, ath_date=None)
    records = get_all_time_high_for_symbols(
        [symbol_key],
        as_of_date=as_of_date,
        include_date=include_date,
        endpoint=endpoint,
    )
    return records.get(symbol_key, _row_record(ath=None, ath_date=None))


def compute_distance_from_ath_percent(current_price: Optional[float], ath: Optional[float]) -> Optional[float]:
    if current_price is None or ath is None or ath == 0:
        return None
    try:
        return round(((float(ath) - float(current_price)) / float(ath)) * 100.0, 2)
    except Exception:
        return None


def warn_if_ath_below_current(
    ath_map: dict[str, Optional[float]],
    current_price_map: dict[str, Optional[float]],
    *,
    endpoint: str,
) -> None:
    for symbol, ath_value in ath_map.items():
        current_price = current_price_map.get(symbol)
        if ath_value is None or current_price is None:
            continue
        try:
            if float(ath_value) < float(current_price):
                _logger.warning(
                    "[ATH][WARN] endpoint=%s ATH < current_price for symbol=%s ath=%s current_price=%s",
                    endpoint,
                    symbol,
                    round(float(ath_value), 4),
                    round(float(current_price), 4),
                )
        except Exception:
            continue
