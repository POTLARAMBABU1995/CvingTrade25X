import os
import calendar
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

try:
    from .env_bootstrap import load_default_env  # type: ignore
except Exception:  # pragma: no cover
    from env_bootstrap import load_default_env  # type: ignore

try:
    import oracledb  # type: ignore
except Exception:  # pragma: no cover
    oracledb = None

try:
    from .db_pool import pool  # type: ignore
except Exception:  # pragma: no cover
    try:
        from db_pool import pool  # type: ignore
    except Exception:  # pragma: no cover
        pool = None  # type: ignore

load_default_env()


def _to_datetime(value):
    if isinstance(value, datetime):
        return value
    try:
        if hasattr(value, 'year') and hasattr(value, 'month') and hasattr(value, 'day'):
            return datetime(value.year, value.month, value.day)
    except Exception:
        return None
    return None


def _to_float(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except Exception:
        return None


def _to_date(value) -> Optional[date]:
    dt = _to_datetime(value)
    if dt is None:
        return None
    return dt.date()


def _resolve_available_columns(conn, schema: str, table: str) -> set[str]:
    qualified = f"{schema}.{table}" if schema else table
    try:
        with conn.cursor() as meta_cur:
            meta_cur.execute(f"SELECT * FROM {qualified} WHERE ROWNUM = 0")
            desc = meta_cur.description or []
            return {str(col[0]).upper() for col in desc if col and col[0]}
    except Exception:
        return set()


def _collect_candidates(available: set[str], candidates: List[str]) -> List[str]:
    out: List[str] = []
    for cand in candidates:
        name = cand.upper()
        if name in available and name not in out:
            out.append(name)
    return out


def _select_expr(columns: List[str], alias: str) -> str:
    if not columns:
        return f"NULL AS {alias}"
    if len(columns) == 1:
        return f"{columns[0]} AS {alias}"
    joined = ', '.join(columns)
    return f"COALESCE({joined}) AS {alias}"


def build_dsn():
    user = os.getenv('ORACLE_USER', 'CVING_APP')
    password = os.getenv('ORACLE_PASSWORD', '')
    direct_dsn = (os.getenv('ORACLE_DSN') or '').strip()
    if direct_dsn:
        return user, password, direct_dsn
    host = os.getenv('ORACLE_HOST', '127.0.0.1')
    port = int(os.getenv('ORACLE_PORT', '1521'))
    sid = os.getenv('ORACLE_SID')
    service_name = os.getenv('ORACLE_SERVICE_NAME') or os.getenv('ORACLE_SERVICE')
    if sid:
        dsn = oracledb.makedsn(host, port, sid=sid)
    else:
        dsn = oracledb.makedsn(host, port, service_name=(service_name or 'cvingpdb.local'))
    return user, password, dsn


def _acquire_connection():
    if pool is not None:
        return pool.acquire()
    if os.getenv("CVING_MCP_PROCESS_READONLY") == "1":
        raise RuntimeError("MCP read-only pool is unavailable; direct connection fallback is disabled")
    user, password, dsn = build_dsn()
    return oracledb.connect(user=user, password=password, dsn=dsn)


def _months_ago(base: date, months: int) -> date:
    year = base.year
    month = base.month - months
    while month <= 0:
        month += 12
        year -= 1
    day = min(base.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _resolve_anchor_date(conn, qualified_table: str, cutoff_anchor: str, date_column: str) -> date:
    if cutoff_anchor != "latest":
        return datetime.utcnow().date()

    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT MAX({date_column}) FROM {qualified_table}")
            row = cur.fetchone()
            latest_date = _to_date(row[0]) if row else None
            if latest_date is not None:
                return latest_date
    except Exception:
        pass
    return datetime.utcnow().date()


def fetch_ohlc_series_from_oracle(
    months: int | None = None,
    cutoff_anchor: str = "current",
    symbols: Optional[Iterable[Any]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Load rows from the source table, optionally enforcing a trailing-month cutoff.

    Returns dict: { SYMBOL: [ {date, open, high, low, close, volume}, ... ] }
    """
    if oracledb is None:
        raise RuntimeError('python-oracledb is not installed. Run: pip install oracledb')

    anchor_mode = str(cutoff_anchor or "current").strip().lower()
    if anchor_mode not in {"current", "latest"}:
        raise ValueError("Invalid cutoff_anchor. Expected one of: current, latest")

    conn = _acquire_connection()
    try:
        schema = os.getenv('ORACLE_SCHEMA', '')
        table = os.getenv('ORACLE_TABLE', 'NSE_NIFTY500_DAILY_RAW_DATA_DEV')
        qualified = f"{schema}.{table}" if schema else table

        available = _resolve_available_columns(conn, schema, table)
        date_cols = _collect_candidates(available, ['TRADING_DATE', 'TRADE_DATE', 'LTC_DATE', 'DATE'])
        if not date_cols:
            raise RuntimeError(f'No trading date column detected for table {qualified}')
        date_col = date_cols[0]

        open_cols = _collect_candidates(available, ['OPEN_PRICE', 'OPEN', 'O'])
        high_cols = _collect_candidates(available, ['HIGH_PRICE', 'HIGH', 'H'])
        low_cols = _collect_candidates(available, ['LOW_PRICE', 'LOW', 'L'])
        close_candidates = [
            'CLOSE_PRICE', 'CLOSE', 'ADJ_CLOSE', 'LTP',
            'LAST_PRICE', 'LAST_TRADED_PRICE', 'LASTTRADEPRICE',
            'CLOSING_PRICE', 'CLOSE_RATE', 'CLOSEVALUE', 'CLOSE_VAL',
            'CLOSEPRICE', 'CLOSEP'
        ]
        close_cols = _collect_candidates(available, close_candidates)
        if not close_cols and 'LTP' in available:
            close_cols = ['LTP']
        if not close_cols:
            fallback_close = [col for col in sorted(available) if any(key in col for key in ('CLOSE', 'LTP', 'LAST'))]
            if fallback_close:
                close_cols = fallback_close
        volume_cols = _collect_candidates(available, ['VOLUME', 'TOTTRDQTY', 'TOT_TRDQTY', 'QTY', 'DELIV_QTY'])

        if not close_cols:
            raise RuntimeError(f'No close/ltp column detected for table {qualified}')

        open_expr = _select_expr(open_cols, 'OPEN_VAL')
        high_expr = _select_expr(high_cols, 'HIGH_VAL')
        low_expr = _select_expr(low_cols, 'LOW_VAL')
        close_expr = _select_expr(close_cols, 'CLOSE_VAL')
        volume_expr = _select_expr(volume_cols, 'VOLUME_VAL')

        cutoff_clause = ""
        params: Dict[str, Any] = {}
        if months and months > 0:
            anchor_date = _resolve_anchor_date(conn, qualified, anchor_mode, date_col)
            cutoff_date = _months_ago(anchor_date, months)
            cutoff_clause = f" AND {date_col} >= :cutoff_date"
            params["cutoff_date"] = cutoff_date
        normalized_symbols = sorted({
            str(symbol).strip().upper()
            for symbol in (symbols or [])
            if str(symbol).strip()
        })
        symbol_clause = ""
        if normalized_symbols:
            bind_names: List[str] = []
            for index, symbol in enumerate(normalized_symbols):
                bind_name = f"symbol_{index}"
                bind_names.append(f":{bind_name}")
                params[bind_name] = symbol
            symbol_clause = f" AND UPPER(TRIM(SYMBOL)) IN ({', '.join(bind_names)})"

        sql = (
            f'SELECT SYMBOL, {date_col}, {open_expr}, {high_expr}, {low_expr}, {close_expr}, {volume_expr} '
            f'FROM {qualified} '
            f'WHERE SYMBOL IS NOT NULL'
            f'{symbol_clause}'
            f'{cutoff_clause} '
            f'ORDER BY SYMBOL, {date_col}'
        )

        series: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        with conn.cursor() as cur:
            cur.execute(sql, params)
            for row in cur:
                try:
                    symbol = str(row[0]) if row[0] is not None else None
                    if not symbol:
                        continue
                    dt = _to_datetime(row[1])
                    entry = {
                        'date': dt,
                        'open': _to_float(row[2]),
                        'high': _to_float(row[3]),
                        'low': _to_float(row[4]),
                        'close': _to_float(row[5]),
                        'volume': _to_float(row[6]) if len(row) > 6 else None,
                    }
                    series[symbol].append(entry)
                except Exception:
                    continue
        return series
    finally:
        conn.close()


def fetch_latest_trade_date_from_oracle() -> Optional[date]:
    """Return the latest source trading date without loading OHLC history."""
    if oracledb is None:
        raise RuntimeError('python-oracledb is not installed. Run: pip install oracledb')

    conn = _acquire_connection()
    try:
        schema = os.getenv('ORACLE_SCHEMA', '')
        table = os.getenv('ORACLE_TABLE', 'NSE_NIFTY500_DAILY_RAW_DATA_DEV')
        qualified = f"{schema}.{table}" if schema else table
        available = _resolve_available_columns(conn, schema, table)
        date_cols = _collect_candidates(available, ['TRADING_DATE', 'TRADE_DATE', 'LTC_DATE', 'DATE'])
        if not date_cols:
            raise RuntimeError(f'No trading date column detected for table {qualified}')
        date_col = date_cols[0]
        with conn.cursor() as cur:
            cur.execute(f"SELECT MAX({date_col}) FROM {qualified} WHERE {date_col} IS NOT NULL")
            row = cur.fetchone()
            return _to_date(row[0]) if row else None
    finally:
        conn.close()


def fetch_recent_ohlc_series_from_oracle(trading_days: int = 504) -> Dict[str, List[Dict[str, Any]]]:
    """Load a bounded recent OHLC window using the existing indexed date cutoff path."""
    bounded_days = max(60, min(int(trading_days or 504), 1000))
    months = max(3, min(48, (bounded_days + 20) // 21))
    return fetch_ohlc_series_from_oracle(months=months, cutoff_anchor="latest")


def get_oracle_connection():
    """Return a new oracledb connection using the configured DSN."""
    if oracledb is None:
        raise RuntimeError('python-oracledb is not installed. Run: pip install oracledb')
    return _acquire_connection()
