from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable, Optional

try:
    from ..db_pool import fetchall_dict, pool
except ImportError:  # pragma: no cover
    from db_pool import fetchall_dict, pool  # type: ignore


_logger = logging.getLogger(__name__)

_VW_ASURA_V3_3_DASHBOARD_SUMMARY = "VW_ASURA_V3_3_DASHBOARD_SUMMARY"
_VW_ASURA_V3_3_LATEST_SIGNALS = "VW_ASURA_V3_3_LATEST_SIGNALS"
_VW_ASURA_V3_3_YEARLY_SUMMARY = "VW_ASURA_V3_3_YEARLY_SUMMARY"
_VW_ASURA_V3_3_COST_SUMMARY = "VW_ASURA_V3_3_COST_SUMMARY"
_VW_ASURA_V3_3_RISK_SUMMARY = "VW_ASURA_V3_3_RISK_SUMMARY"
_VW_ASURA_V3_2_SYMBOL_RATING = "VW_ASURA_V3_2_SYMBOL_RATING"

_DEFAULT_ELIGIBLE_RATINGS = ("PREMIUM", "STRONG", "NORMAL")
_ALL_RATINGS = ("PREMIUM", "STRONG", "NORMAL", "WEAK", "AVOID")
_RATING_SORT_ORDER = {"PREMIUM": 0, "STRONG": 1, "NORMAL": 2, "WEAK": 3, "AVOID": 4}

ASURA_V3_LATEST_SORT_COLUMNS = {
    "SYMBOL": "SYMBOL",
    "SIGNAL_DATE": "SIGNAL_DATE",
    "SYMBOL_RATING": "SYMBOL_RATING",
    "PRICE": "PRICE",
    "ENTRY_PRICE": "ENTRY_PRICE",
    "STOP_LOSS": "STOP_LOSS",
    "TARGET_1R": "TARGET_1R",
    "RRR": "RRR",
    "SIGNAL_SCORE": "SIGNAL_SCORE",
    "SIGNAL_GRADE": "SIGNAL_GRADE",
    "RSI14": "RSI14",
    "RSI_PREV_1D": "RSI_PREV_1D",
    "RSI_PREV_5D": "RSI_PREV_5D",
    "MACD_HIST": "MACD_HIST",
    "ADX14": "ADX14",
    "ATR_PERCENT": "ATR_PERCENT",
    "RISK_ATR": "RISK_ATR",
    "VOLUME_RATIO_20": "VOLUME_RATIO_20",
    "MOVE_1D_PCT": "MOVE_1D_PCT",
    "MOVE_1W_PCT": "MOVE_1W_PCT",
    "MOVE_1M_PCT": "MOVE_1M_PCT",
    "SUPPORT_GAP_PCT": "SUPPORT_GAP_PCT",
    "RESISTANCE_GAP_PCT": "RESISTANCE_GAP_PCT",
    "TREND_DIRECTION": "TREND_DIRECTION",
    "EMA_STACK": "EMA_STACK",
    "ATH_PRICE": "ATH_PRICE",
    "ATH_GAP_PCT": "ATH_GAP_PCT",
}


def _to_camel_case(key: str) -> str:
    token = str(key or "").strip().lower()
    if not token:
        return token
    parts = [part for part in token.split("_") if part]
    if not parts:
        return token
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def _to_json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        integral = value.to_integral_value()
        return int(value) if value == integral else float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {_to_camel_case(key): _to_json_value(value) for key, value in row.items()}


def _normalize_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_normalize_row(row) for row in rows]


def _coerce_signal_year(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return int(value.year)
    if isinstance(value, Decimal):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)

    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)

    year_token = text[:4]
    if year_token.isdigit() and (len(text) == 4 or text[4] in {"-", "/", "T", " "}):
        return int(year_token)
    return None


def _normalize_yearly_summary_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_rows = _normalize_rows(rows)
    for row in normalized_rows:
        row["signalYear"] = _coerce_signal_year(row.get("signalYear"))
    return normalized_rows


def _parse_csv_tokens(value: Optional[str]) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    return [token.strip().upper() for token in text.split(",") if token.strip()]


def _escape_like_fragment(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _bind_in_clause(bind_prefix: str, values: Iterable[str], binds: dict[str, Any]) -> str:
    placeholders: list[str] = []
    for index, value in enumerate(values):
        name = f"{bind_prefix}_{index}"
        placeholders.append(f":{name}")
        binds[name] = value
    return ", ".join(placeholders)


def _select_latest_signals_sql(where_clause: str, *, include_total_count: bool, order_clause: str = "") -> str:
    base_select = f"""
        SELECT
            SYMBOL,
            SIGNAL_DATE,
            SYMBOL_RATING,
            PRICE,
            ENTRY_PRICE,
            STOP_LOSS,
            TARGET_1R,
            CASE
                WHEN ENTRY_PRICE IS NULL OR STOP_LOSS IS NULL OR TARGET_1R IS NULL THEN NULL
                WHEN (ENTRY_PRICE - STOP_LOSS) = 0 THEN NULL
                ELSE ROUND((TARGET_1R - ENTRY_PRICE) / NULLIF((ENTRY_PRICE - STOP_LOSS), 0), 4)
            END AS RRR,
            SIGNAL_SCORE,
            SIGNAL_GRADE,
            RSI14,
            RSI_PREV_1D,
            RSI_PREV_5D,
            MACD_HIST,
            ADX14,
            ATR_PERCENT,
            RISK_ATR,
            VOLUME_RATIO_20,
            MOVE_1D_PCT,
            MOVE_1W_PCT,
            MOVE_1M_PCT,
            SUPPORT_GAP_PCT,
            RESISTANCE_GAP_PCT,
            TREND_DIRECTION,
            EMA_STACK,
            ATH_PRICE,
            ATH_GAP_PCT
        FROM {_VW_ASURA_V3_3_LATEST_SIGNALS}
        WHERE {where_clause}
    """
    if not include_total_count:
        return base_select
    return f"""
        SELECT
            base_rows.*,
            COUNT(1) OVER () AS TOTAL_COUNT
        FROM (
            {base_select}
        ) base_rows
        {order_clause}
    """


def _fetch_view_columns(conn, view_name: str) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT * FROM {view_name} WHERE ROWNUM = 0")
        return {str(desc[0]).upper() for desc in (cur.description or []) if desc and desc[0]}


def _query_max_value(conn, view_name: str, column_name: str) -> Any:
    with conn.cursor() as cur:
        cur.execute(f"SELECT MAX({column_name}) AS MAX_VALUE FROM {view_name}")
        rows = fetchall_dict(cur)
    if not rows:
        return None
    return rows[0].get("max_value")


def fetch_asura_v3_dashboard_summary() -> dict[str, Any]:
    with pool.acquire() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {_VW_ASURA_V3_3_DASHBOARD_SUMMARY} FETCH FIRST 1 ROWS ONLY")
            rows = fetchall_dict(cur)
    item = _normalize_row(rows[0]) if rows else {}
    return {"item": item}


def fetch_asura_v3_latest_signals(
    *,
    q: Optional[str],
    rating: Optional[str],
    grade: Optional[str],
    limit: int,
    offset: int,
    sort_by: str,
    sort_dir: str,
) -> dict[str, Any]:
    normalized_sort_by = str(sort_by or "SIGNAL_DATE").strip().upper()
    normalized_sort_dir = "ASC" if str(sort_dir or "DESC").strip().upper() == "ASC" else "DESC"
    sort_column = ASURA_V3_LATEST_SORT_COLUMNS.get(normalized_sort_by)
    if not sort_column:
        raise ValueError("Invalid request parameter: sort_by")

    where_parts = ["1 = 1"]
    binds: dict[str, Any] = {"limit": int(limit), "offset": int(offset)}
    count_binds: dict[str, Any] = {}

    search = str(q or "").strip().upper()
    if search:
        search_bind = f"%{_escape_like_fragment(search)}%"
        where_parts.append("UPPER(NVL(SYMBOL, '')) LIKE :q_like ESCAPE '\\'")
        binds["q_like"] = search_bind
        count_binds["q_like"] = search_bind

    rating_tokens = _parse_csv_tokens(rating)
    if rating_tokens:
        if "ALL" not in rating_tokens:
            filtered_ratings = [token for token in rating_tokens if token in _ALL_RATINGS]
            if not filtered_ratings:
                return {"items": [], "limit": int(limit), "offset": int(offset), "total": 0}
            rating_clause = _bind_in_clause("rating", filtered_ratings, binds)
            _bind_in_clause("rating", filtered_ratings, count_binds)
            where_parts.append(f"UPPER(NVL(SYMBOL_RATING, '')) IN ({rating_clause})")
    else:
        eligible_clause = _bind_in_clause("eligible_rating", _DEFAULT_ELIGIBLE_RATINGS, binds)
        _bind_in_clause("eligible_rating", _DEFAULT_ELIGIBLE_RATINGS, count_binds)
        where_parts.append(f"UPPER(NVL(SYMBOL_RATING, '')) IN ({eligible_clause})")

    grade_tokens = _parse_csv_tokens(grade)
    if grade_tokens:
        filtered_grades = [token for token in grade_tokens if token != "ALL"]
        if filtered_grades:
            grade_clause = _bind_in_clause("grade", filtered_grades, binds)
            _bind_in_clause("grade", filtered_grades, count_binds)
            where_parts.append(f"UPPER(NVL(SIGNAL_GRADE, '')) IN ({grade_clause})")

    where_clause = " AND ".join(where_parts)
    order_clause = f"ORDER BY {sort_column} {normalized_sort_dir} NULLS LAST, SYMBOL ASC"
    data_sql = _select_latest_signals_sql(where_clause, include_total_count=True, order_clause=order_clause)
    count_sql = f"SELECT COUNT(1) AS TOTAL_COUNT FROM ({_select_latest_signals_sql(where_clause, include_total_count=False)})"
    with pool.acquire() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT *
                FROM (
                    {data_sql}
                )
                OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY
                """,
                binds,
            )
            rows = fetchall_dict(cur)

            if rows:
                total = int(rows[0].get("total_count") or 0)
            else:
                cur.execute(count_sql, count_binds)
                count_rows = fetchall_dict(cur)
                total = int((count_rows[0].get("total_count") if count_rows else 0) or 0)

    items: list[dict[str, Any]] = []
    for row in rows:
        payload = {key: value for key, value in row.items() if key != "total_count"}
        items.append(_normalize_row(payload))
    return {
        "items": items,
        "limit": int(limit),
        "offset": int(offset),
        "total": max(total, 0),
    }


def fetch_asura_v3_yearly_summary() -> dict[str, Any]:
    with pool.acquire() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT *
                FROM {_VW_ASURA_V3_3_YEARLY_SUMMARY}
                ORDER BY SIGNAL_YEAR DESC NULLS LAST
                """
            )
            rows = fetchall_dict(cur)
    return {"items": _normalize_yearly_summary_rows(rows)}


def fetch_asura_v3_cost_summary() -> dict[str, Any]:
    with pool.acquire() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT *
                FROM {_VW_ASURA_V3_3_COST_SUMMARY}
                ORDER BY ROUND_TRIP_COST_PCT ASC NULLS LAST
                """
            )
            rows = fetchall_dict(cur)
    return {"items": _normalize_rows(rows)}


def fetch_asura_v3_risk_summary() -> dict[str, Any]:
    with pool.acquire() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {_VW_ASURA_V3_3_RISK_SUMMARY}")
            rows = fetchall_dict(cur)
    return {"items": _normalize_rows(rows)}


def fetch_asura_v3_symbol_ratings() -> dict[str, Any]:
    with pool.acquire() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    UPPER(NVL(SYMBOL_RATING, 'UNKNOWN')) AS SYMBOL_RATING,
                    COUNT(1) AS TOTAL_SYMBOLS
                FROM {_VW_ASURA_V3_2_SYMBOL_RATING}
                GROUP BY UPPER(NVL(SYMBOL_RATING, 'UNKNOWN'))
                """
            )
            rows = fetchall_dict(cur)

    normalized = _normalize_rows(rows)
    normalized.sort(key=lambda row: _RATING_SORT_ORDER.get(str(row.get("symbolRating") or "").upper(), 999))
    return {"items": normalized}


def fetch_asura_v3_health() -> dict[str, Any]:
    checked_at = datetime.utcnow().isoformat() + "Z"
    db_reachable = False
    latest_signal_date = None
    dashboard_refresh_timestamp = None

    try:
        with pool.acquire() as conn:
            db_reachable = True
            columns = _fetch_view_columns(conn, _VW_ASURA_V3_3_DASHBOARD_SUMMARY)
            latest_signal_date = _to_json_value(_query_max_value(conn, _VW_ASURA_V3_3_LATEST_SIGNALS, "SIGNAL_DATE"))
            for candidate in (
                "DASHBOARD_REFRESH_TIMESTAMP",
                "LAST_REFRESH_TS",
                "REFRESH_TS",
                "UPDATED_AT",
                "GENERATED_AT",
                "AS_OF_TS",
                "RUN_TS",
            ):
                if candidate not in columns:
                    continue
                dashboard_refresh_timestamp = _to_json_value(_query_max_value(conn, _VW_ASURA_V3_3_DASHBOARD_SUMMARY, candidate))
                if dashboard_refresh_timestamp is not None:
                    break
    except Exception:
        _logger.exception("asura_v3_health_failed")
        db_reachable = False

    return {
        "checkedAt": checked_at,
        "dashboardRefreshTimestamp": dashboard_refresh_timestamp,
        "dbReachable": db_reachable,
        "latestSignalDate": latest_signal_date,
    }


__all__ = [
    "ASURA_V3_LATEST_SORT_COLUMNS",
    "fetch_asura_v3_cost_summary",
    "fetch_asura_v3_dashboard_summary",
    "fetch_asura_v3_health",
    "fetch_asura_v3_latest_signals",
    "fetch_asura_v3_risk_summary",
    "fetch_asura_v3_symbol_ratings",
    "fetch_asura_v3_yearly_summary",
]
