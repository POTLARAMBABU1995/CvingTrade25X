from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal
from typing import Any, Dict, List, Literal

try:  # Support execution via package or direct script
    from ..config import settings
    from ..db_pool import pool
except ImportError:  # pragma: no cover
    from config import settings  # type: ignore
    from db_pool import pool  # type: ignore


VALID_TIMEFRAMES = ("daily", "weekly", "monthly", "yearly")
EMA_PERIODS: tuple[int, ...] = (20, 50, 100, 200)

# Use ONLY these views. Do not touch the raw table in application code.
TIMEFRAME_SQL: Dict[str, str] = {
    "daily": """
        SELECT
            SYMBOL,
            TRADING_DATE,
            PRICE_FOR_EMA,
            OPEN,
            HIGH,
            LOW,
            VOLUME
        FROM
            V_NSE500_EMA_DAILY
        WHERE
            SYMBOL = :symbol
        ORDER BY
            TRADING_DATE
    """,
    "weekly": """
        SELECT
            SYMBOL,
            WEEK_START,
            FIRST_TRADING_DATE,
            LAST_TRADING_DATE,
            PRICE_FOR_EMA,
            OPEN,
            HIGH,
            LOW,
            VOLUME
        FROM
            V_NSE500_EMA_WEEKLY
        WHERE
            SYMBOL = :symbol
        ORDER BY
            WEEK_START
    """,
    "monthly": """
        SELECT
            SYMBOL,
            MONTH_START,
            FIRST_TRADING_DATE,
            LAST_TRADING_DATE,
            PRICE_FOR_EMA,
            OPEN,
            HIGH,
            LOW,
            VOLUME
        FROM
            V_NSE500_EMA_MONTHLY
        WHERE
            SYMBOL = :symbol
        ORDER BY
            MONTH_START
    """,
    "yearly": """
        SELECT
            SYMBOL,
            YEAR_START,
            FIRST_TRADING_DATE,
            LAST_TRADING_DATE,
            PRICE_FOR_EMA,
            OPEN,
            HIGH,
            LOW,
            VOLUME
        FROM
            V_NSE500_EMA_YEARLY
        WHERE
            SYMBOL = :symbol
        ORDER BY
            YEAR_START
    """,
}

# Column used for ordering per timeframe (must match SQL above).
DATE_COL = {
    "daily": "trading_date",
    "weekly": "week_start",
    "monthly": "month_start",
    "yearly": "year_start",
}

_SYM_RE = re.compile(r"^[A-Z][A-Z0-9.&-]{0,24}$")


class InvalidParameterError(ValueError):
    """Raised when incoming query params are invalid."""


class SymbolNotFoundError(RuntimeError):
    """Raised when the requested symbol does not exist in the EMA views."""


def _normalize_symbol(symbol: str) -> str:
    sym = (symbol or "").strip().upper()
    if not sym:
        raise InvalidParameterError("symbol is required")
    if not _SYM_RE.match(sym):
        raise InvalidParameterError("symbol must start with a letter and may include A-Z, 0-9, ., -, &")
    return sym


def _normalize_timeframe(tf: str) -> Literal["daily", "weekly", "monthly", "yearly"]:
    val = (tf or "daily").strip().lower()
    if val not in VALID_TIMEFRAMES:
        raise InvalidParameterError("tf must be one of daily, weekly, monthly, yearly")
    return val  # type: ignore[return-value]


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except Exception:
        return None


def _to_date_str(value: Any) -> str | None:
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    return None


def _iter_rows(cursor) -> Iterable[tuple]:
    # Stream rows with tuned network/window sizes for faster fetch of long histories.
    cursor.arraysize = max(500, int(getattr(settings, "oracle_arraysize", 500)))
    cursor.prefetchrows = cursor.arraysize
    return cursor


def _next_ema(prev: float | None, price: float, period: int) -> float:
    k = 2 / (period + 1)
    return price if prev is None else (price - prev) * k + prev


def fetch_ema_series(symbol: str, timeframe: str) -> List[Dict[str, Any]]:
    """Return OHLC + PRICE_FOR_EMA + computed EMA20/50/100/200 for a symbol/timeframe."""
    sym = _normalize_symbol(symbol)
    tf = _normalize_timeframe(timeframe)
    sql = TIMEFRAME_SQL[tf]

    with pool.acquire() as con, con.cursor() as cur:
        cur.execute(sql, {"symbol": sym})
        cols = [c[0].lower() for c in cur.description]

        # Required column positions (fixed per view).
        date_idx = cols.index(DATE_COL[tf])
        price_idx = cols.index("price_for_ema")
        open_idx = cols.index("open")
        high_idx = cols.index("high")
        low_idx = cols.index("low")
        volume_idx = cols.index("volume")
        first_idx = cols.index("first_trading_date") if "first_trading_date" in cols else None
        last_idx = cols.index("last_trading_date") if "last_trading_date" in cols else None

        ema_state: Dict[int, float | None] = {p: None for p in EMA_PERIODS}
        results: List[Dict[str, Any]] = []

        for row in _iter_rows(cur):
            price_val = _to_float(row[price_idx])
            if price_val is None:  # Cannot compute EMA without a seed price.
                continue

            entry: Dict[str, Any] = {
                "symbol": sym,
                "timeframe": tf,
                DATE_COL[tf]: _to_date_str(row[date_idx]),
                "priceForEma": price_val,
                "open": _to_float(row[open_idx]),
                "high": _to_float(row[high_idx]),
                "low": _to_float(row[low_idx]),
                "volume": _to_float(row[volume_idx]),
            }
            if first_idx is not None:
                entry["firstTradingDate"] = _to_date_str(row[first_idx])
            if last_idx is not None:
                entry["lastTradingDate"] = _to_date_str(row[last_idx])

            for period in EMA_PERIODS:
                ema_state[period] = _next_ema(ema_state[period], price_val, period)
                entry[f"ema{period}"] = ema_state[period]

            results.append(entry)

    if not results:
        raise SymbolNotFoundError(f"{sym} not found in EMA {tf} view")
    results.sort(key=lambda r: r.get(DATE_COL[tf]) or "")
    return results
