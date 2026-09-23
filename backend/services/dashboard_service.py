from __future__ import annotations

import os
import re
import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from db import get_oracle_connection
try:
    from . import nse_mcap_service as nse_mcap_svc
except ImportError:  # pragma: no cover
    from services import nse_mcap_service as nse_mcap_svc  # type: ignore


@dataclass(frozen=True)
class SegmentConfig:
    view: str
    snapshot_view: str
    weekly_view: str
    monthly_view: str
    yearly_view: str
    symbol_table: str


SEGMENT_CONFIGS: Dict[str, SegmentConfig] = {
    'nifty50': SegmentConfig(
        view=os.getenv('NIFTY50_VIEW', 'V_NSE_NIFTY50_LARGECAP_OHLCV'),
        snapshot_view=os.getenv('NIFTY50_SNAPSHOT_VIEW', 'MV_NIFTY50_DAILY_SNAP'),
        weekly_view=os.getenv('NIFTY50_WEEKLY_VIEW', 'MV_NIFTY50_WEEKLY'),
        monthly_view=os.getenv('NIFTY50_MONTHLY_VIEW', 'MV_NIFTY50_MONTHLY'),
        yearly_view=os.getenv('NIFTY50_YEARLY_VIEW', 'MV_NIFTY50_YEARLY'),
        symbol_table=os.getenv('NIFTY50_SYMBOL_TABLE', 'NSE_NIFTY50_LARGECAP'),
    ),
    'next50': SegmentConfig(
        view=os.getenv('NEXT50_VIEW', 'V_NSE_NIFTY_NEXT50_MIDCAP_OHLCV'),
        snapshot_view=os.getenv('NEXT50_SNAPSHOT_VIEW', 'MV_NIFTY_NEXT50_DAILY_SNAP'),
        weekly_view=os.getenv('NEXT50_WEEKLY_VIEW', ''),
        monthly_view=os.getenv('NEXT50_MONTHLY_VIEW', ''),
        yearly_view=os.getenv('NEXT50_YEARLY_VIEW', ''),
        symbol_table=os.getenv('NEXT50_SYMBOL_TABLE', 'NIFTY_NEXT50_MIDCAP'),
    ),
    'midcap': SegmentConfig(
        view=os.getenv('MIDCAP_VIEW', 'V_NSE_NIFTY150_MIDCAP_OHLCV'),
        snapshot_view=os.getenv('MIDCAP_SNAPSHOT_VIEW', 'MV_NIFTY_MIDCAP150_DAILY_SNAP'),
        weekly_view=os.getenv('MIDCAP_WEEKLY_VIEW', 'MV_NIFTY150_WEEKLY'),
        monthly_view=os.getenv('MIDCAP_MONTHLY_VIEW', 'MV_NIFTY150_MONTHLY'),
        yearly_view=os.getenv('MIDCAP_YEARLY_VIEW', 'MV_NIFTY150_YEARLY'),
        symbol_table=os.getenv('MIDCAP_SYMBOL_TABLE', 'NSE_NIFTY150_MIDCAP'),
    ),
    'smallcap': SegmentConfig(
        view=os.getenv('SMALLCAP_VIEW', 'V_NSE_NIFTY250_SMALLCAP_OHLCV'),
        snapshot_view=os.getenv('SMALLCAP_SNAPSHOT_VIEW', 'MV_NIFTY_SMALLCAP250_DAILY_SNAP'),
        weekly_view=os.getenv('SMALLCAP_WEEKLY_VIEW', 'MV_NIFTY250_WEEKLY'),
        monthly_view=os.getenv('SMALLCAP_MONTHLY_VIEW', 'MV_NIFTY250_MONTHLY'),
        yearly_view=os.getenv('SMALLCAP_YEARLY_VIEW', 'MV_NIFTY250_YEARLY'),
        symbol_table=os.getenv('SMALLCAP_SYMBOL_TABLE', 'NSE_NIFTY250_SMALLCAP'),
    ),
    'nifty500': SegmentConfig(
        view=os.getenv(
            'NIFTY500_VIEW',
            os.getenv('ORACLE_TABLE', 'NSE_NIFTY500_DAILY_RAW_DATA_DEV'),
        ),
        snapshot_view=os.getenv('NIFTY500_SNAPSHOT_VIEW', ''),
        weekly_view=os.getenv('NIFTY500_WEEKLY_VIEW', ''),
        monthly_view=os.getenv('NIFTY500_MONTHLY_VIEW', ''),
        yearly_view=os.getenv('NIFTY500_YEARLY_VIEW', ''),
        symbol_table=os.getenv('NIFTY500_SYMBOL_TABLE', ''),
    ),
}

DEFAULT_SEGMENT = 'nifty50'
DEFAULT_MOVERS_LIMIT = 5
AVAILABLE_SEGMENTS = tuple(sorted(SEGMENT_CONFIGS.keys()))
INDEX_LABELS = {
    'nifty50': 'Nifty50',
    'next50': 'Next50',
    'midcap': 'Midcap150',
    'smallcap': 'Smallcap250',
    'nifty500': 'Nifty500',
    'niftytotal': 'NiftyTotal',
}
_BREADTH_ORDER = ('nifty50', 'next50', 'midcap', 'smallcap', 'nifty500', 'niftytotal')
CLOSE_CANDIDATES = (
    'close_price',
    'close',
    'price',
    'ltp',
    'last_price',
    'adj_close',
    'closing_price',
    'close_rate',
    'closevalue',
    'close_val',
    'closeprice',
    'closep',
    'previous_close',
)
VOLUME_CANDIDATES = (
    'volume',
    'tottrdqty',
    'tot_trdqty',
    'total_traded_qty',
    'qty',
)
_COLUMN_CACHE: Dict[str, List[str]] = {}
_CLOSE_COLUMN_CACHE: Dict[str, str] = {}
_SAFE_SQL_NAME_RE = re.compile(r'^[A-Z][A-Z0-9_$#]*(?:\.[A-Z][A-Z0-9_$#]*)?$')
_logger = logging.getLogger(__name__)


def _chunked_symbols(values: List[str], size: int = 900) -> List[List[str]]:
    cleaned = [str(item or '').strip().upper() for item in values if str(item or '').strip()]
    if not cleaned:
        return []
    return [cleaned[index:index + size] for index in range(0, len(cleaned), size)]


def _fmt_date(dt: datetime | None) -> str:
    if isinstance(dt, datetime):
        try:
            return dt.strftime('%d-%m-%Y')
        except Exception:
            return ''
    return ''


def _fmt_iso_date(dt: Any) -> str:
    if isinstance(dt, datetime):
        try:
            return dt.strftime('%Y-%m-%d')
        except Exception:
            return ''
    if isinstance(dt, date):
        try:
            return dt.strftime('%Y-%m-%d')
        except Exception:
            return ''
    return ''


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _get_segment_config(segment: str | None) -> SegmentConfig:
    key = (segment or DEFAULT_SEGMENT).strip().lower() or DEFAULT_SEGMENT
    config = SEGMENT_CONFIGS.get(key)
    if not config:
        raise ValueError(f'Unsupported dashboard segment: {segment}')
    return config


def _is_safe_sql_name(value: str) -> bool:
    token = str(value or '').strip().upper()
    if not token:
        return False
    return bool(_SAFE_SQL_NAME_RE.fullmatch(token))


def _qualified_table_name(name: str, schema: str | None = None) -> str:
    normalized = str(name or '').strip().upper()
    if not normalized:
        return ''
    if '.' in normalized:
        return normalized if _is_safe_sql_name(normalized) else ''
    normalized_schema = str(schema or '').strip().upper()
    candidate = f'{normalized_schema}.{normalized}' if normalized_schema else normalized
    return candidate if _is_safe_sql_name(candidate) else ''


def _raw_dev_table_name() -> str:
    return _qualified_table_name(
        os.getenv('ORACLE_TABLE', 'NSE_NIFTY500_DAILY_RAW_DATA_DEV'),
        os.getenv('ORACLE_SCHEMA', ''),
    )


def _segment_raw_join_view(config: SegmentConfig) -> str:
    raw_table = _raw_dev_table_name()
    symbol_table = _qualified_table_name(config.symbol_table, '')
    if not raw_table or not symbol_table:
        return ''
    return f"""(
        SELECT
            r.SYMBOL,
            r.OPEN,
            r.HIGH,
            r.LOW,
            r.PREVIOUS_CLOSE,
            r.VOLUME,
            r.TRADING_DATE
        FROM {raw_table} r
        INNER JOIN {symbol_table} u
            ON r.SYMBOL = u.SYMBOL
    )"""


def _nifty500_constituent_raw_view() -> str:
    constituent_views = [
        _segment_raw_join_view(SEGMENT_CONFIGS[key])
        for key in ('nifty50', 'next50', 'midcap', 'smallcap')
    ]
    constituent_views = [view for view in constituent_views if view]
    if not constituent_views:
        return ''
    union_sql = "\nUNION ALL\n".join(
        f"""
        SELECT
            v.SYMBOL,
            v.OPEN,
            v.HIGH,
            v.LOW,
            v.PREVIOUS_CLOSE,
            v.VOLUME,
            v.TRADING_DATE
        FROM {view} v
        """
        for view in constituent_views
    )
    return f"(\n{union_sql}\n)"


def _niftytotal_view_name() -> str:
    preferred = _qualified_table_name(
        os.getenv('NIFTYTOTAL_VIEW', 'NSE_NIFTY500_DAILY_RAW_DATA_VIEW'),
        os.getenv('ORACLE_SCHEMA', ''),
    )
    if preferred:
        return preferred
    fallback = _qualified_table_name(
        os.getenv('NIFTY500_VIEW', os.getenv('ORACLE_TABLE', 'NSE_NIFTY500_DAILY_RAW_DATA_DEV')),
        os.getenv('ORACLE_SCHEMA', ''),
    )
    return fallback


def _breadth_source_for_segment(segment_key: str, config: SegmentConfig, conn=None) -> str:
    raw_join_view = _segment_raw_join_view(config)
    if raw_join_view:
        return raw_join_view
    if segment_key == 'nifty500':
        constituent_raw_view = _nifty500_constituent_raw_view()
        if constituent_raw_view:
            return constituent_raw_view
    if segment_key == 'niftytotal':
        total_view = _niftytotal_view_name()
        if total_view:
            return total_view
    return _latest_view(config, conn)


def _latest_view(config: SegmentConfig, conn=None) -> str:
    candidates: List[str] = []
    for name in (config.snapshot_view, config.view):
        trimmed = (name or '').strip()
        if trimmed and trimmed not in candidates:
            candidates.append(trimmed)
    if conn is not None and candidates:
        freshest_view = None
        freshest_date: Optional[datetime] = None
        for view in candidates:
            try:
                trade_date = _fetch_latest_trading_date(conn, view)
            except Exception:
                trade_date = None
            if trade_date is None:
                continue
            if freshest_date is None or trade_date > freshest_date:
                freshest_date = trade_date
                freshest_view = view
        if freshest_view:
            return freshest_view
        raw_join_view = _segment_raw_join_view(config)
        if raw_join_view:
            return raw_join_view
    if config.view:
        return config.view
    return candidates[0] if candidates else ''


def _execute_query(conn, sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql, params or {})
        columns = [col[0].lower() for col in (cur.description or [])]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def _fetch_single_value(conn, sql: str, params: Optional[Dict[str, Any]] = None) -> Any:
    with conn.cursor() as cur:
        cur.execute(sql, params or {})
        row = cur.fetchone()
        if not row:
            return None
        return row[0]


def _fetch_latest_trading_date(conn, view: str) -> Optional[datetime]:
    sql = f"SELECT MAX(trading_date) FROM {view}"
    return _fetch_single_value(conn, sql)


def _fetch_trading_date_counts(conn, view: str) -> List[Dict[str, Any]]:
    sql = f"""
        SELECT
            trading_date,
            COUNT(*) AS row_count
        FROM {view}
        GROUP BY trading_date
        ORDER BY trading_date ASC
    """
    return _execute_query(conn, sql)


def _resolve_effective_trading_window(conn, view: str, *, min_rows: int = 25) -> Tuple[Optional[Any], Optional[Any], int]:
    date_rows = _fetch_trading_date_counts(conn, view)
    if not date_rows:
        return None, None, 0

    peak_count = max(int(row.get('row_count') or 0) for row in date_rows)
    effective_floor = max(int(min_rows or 0), int(peak_count * 0.9))

    selected_index = len(date_rows) - 1
    selected_row = date_rows[selected_index]
    selected_count = int(selected_row.get('row_count') or 0)
    for idx in range(len(date_rows) - 1, -1, -1):
        row = date_rows[idx]
        row_count = int(row.get('row_count') or 0)
        if row_count >= effective_floor:
            selected_index = idx
            selected_row = row
            selected_count = row_count
            break

    previous_row = date_rows[selected_index - 1] if selected_index > 0 else None
    return selected_row.get('trading_date'), (previous_row.get('trading_date') if previous_row else None), selected_count


def _get_view_columns(conn, view: str) -> List[str]:
    key = view.upper()
    cached = _COLUMN_CACHE.get(key)
    if cached is not None:
        return cached
    with conn.cursor() as cur:
        cur.execute(f"SELECT * FROM {view} WHERE ROWNUM = 0")
        columns = [col[0] for col in (cur.description or [])]
    _COLUMN_CACHE[key] = columns
    return columns


def _pick_column(columns: List[str], candidates: Tuple[str, ...]) -> Optional[str]:
    upper_map = {col.upper(): col for col in columns}
    for candidate in candidates:
        key = candidate.upper()
        if key in upper_map:
            return upper_map[key]
    return None


def _resolve_close_column(conn, view: str) -> str:
    key = view.upper()
    cached = _CLOSE_COLUMN_CACHE.get(key)
    if cached:
        return cached
    columns = _get_view_columns(conn, view)
    preferred_close = 'PREVIOUS_CLOSE'
    close_col = preferred_close if preferred_close in columns else _pick_column(columns, CLOSE_CANDIDATES)
    if not close_col:
        raise RuntimeError(f"Unable to resolve close column for view {view}")
    _CLOSE_COLUMN_CACHE[key] = close_col
    return close_col


def _resolve_volume_column(conn, view: str) -> Optional[str]:
    columns = _get_view_columns(conn, view)
    return _pick_column(columns, tuple(candidate.upper() for candidate in VOLUME_CANDIDATES))


def _fetch_latest_volume_map(conn, symbols: List[str], source_view: str) -> Dict[str, float | int]:
    symbol_keys = sorted({str(symbol or '').strip().upper() for symbol in symbols if str(symbol or '').strip()})
    if not symbol_keys:
        return {}

    candidates: List[tuple[str, str]] = []
    seen_sources: set[str] = set()

    def _add_source(source_name: str) -> None:
        source = str(source_name or '').strip()
        if not source or source in seen_sources:
            return
        try:
            volume_col = _resolve_volume_column(conn, source)
        except Exception:
            return
        if not volume_col:
            return
        seen_sources.add(source)
        candidates.append((source, volume_col))

    _add_source(source_view)
    fallback_raw = _qualified_table_name(
        os.getenv('ORACLE_TABLE', 'NSE_NIFTY500_DAILY_RAW_DATA_DEV'),
        os.getenv('ORACLE_SCHEMA', ''),
    )
    _add_source(fallback_raw)

    volume_by_symbol: Dict[str, float | int] = {}
    for source, volume_col in candidates:
        for batch in _chunked_symbols(symbol_keys):
            binds: Dict[str, Any] = {f'sym_{idx}': symbol for idx, symbol in enumerate(batch)}
            placeholders = ', '.join(f':sym_{idx}' for idx in range(len(batch)))
            sql = f"""
                WITH latest_date AS (
                    SELECT MAX(trading_date) AS latest_date
                    FROM {source}
                )
                SELECT UPPER(TRIM(symbol)) AS symbol_key,
                       {volume_col} AS volume_value
                FROM {source}
                WHERE trading_date = (SELECT latest_date FROM latest_date)
                  AND UPPER(TRIM(symbol)) IN ({placeholders})
            """
            with conn.cursor() as cur:
                cur.execute(sql, binds)
                for symbol_key, volume_value in cur.fetchall() or []:
                    key = str(symbol_key or '').strip().upper()
                    if not key or key in volume_by_symbol:
                        continue
                    numeric = _safe_float(volume_value)
                    if numeric is None:
                        continue
                    if float(numeric).is_integer():
                        volume_by_symbol[key] = int(numeric)
                    else:
                        volume_by_symbol[key] = round(numeric, 2)
        if all(symbol in volume_by_symbol for symbol in symbol_keys):
            break
    return volume_by_symbol


def _fill_missing_mover_volumes(conn, source_view: str, rows: List[Dict[str, Any]]) -> None:
    missing_symbols = [
        str(row.get('symbol') or row.get('stock') or row.get('stockName') or '').strip().upper()
        for row in rows
        if row.get('volume') in (None, '') and row.get('VOLUME') in (None, '')
    ]
    volume_lookup = _fetch_latest_volume_map(conn, missing_symbols, source_view)
    if not volume_lookup:
        return
    for row in rows:
        if row.get('volume') not in (None, '') or row.get('VOLUME') not in (None, ''):
            continue
        symbol = str(row.get('symbol') or row.get('stock') or row.get('stockName') or '').strip().upper()
        value = volume_lookup.get(symbol)
        if value is None:
            continue
        row['volume'] = value
        row['VOLUME'] = value


def _fetch_top_movers(conn, view: str, *, descending: bool, limit: int = 5) -> List[Dict[str, Any]]:
    close_col = _resolve_close_column(conn, view)
    order_clause = 'DESC NULLS LAST' if descending else 'ASC NULLS LAST'
    limit = max(int(limit or 5), 1)
    sql = f"""
        WITH series AS (
            SELECT
                v.symbol,
                v.trading_date,
                v.{close_col} AS close_value,
                LAG(v.{close_col}) OVER (PARTITION BY v.symbol ORDER BY v.trading_date) AS prev_day_close
            FROM {view} v
        ),
        base AS (
            SELECT
                s.symbol,
                s.trading_date,
                s.close_value,
                s.prev_day_close,
                (s.close_value - s.prev_day_close) AS points_change,
                CASE
                    WHEN s.prev_day_close IS NULL OR s.prev_day_close = 0 THEN NULL
                    ELSE (s.close_value - s.prev_day_close) / s.prev_day_close
                END AS change_ratio
            FROM series s
            WHERE s.trading_date = (SELECT MAX(trading_date) FROM series)
              AND s.prev_day_close IS NOT NULL
        )
        SELECT symbol, trading_date, close_value, prev_day_close, points_change, change_ratio
        FROM base
        ORDER BY change_ratio {order_clause}
        FETCH FIRST {limit} ROWS ONLY
    """
    return _execute_query(conn, sql)


def _fetch_breadth(conn, view: str) -> Dict[str, int]:
    close_col = _resolve_close_column(conn, view)
    latest_date, _, _ = _resolve_effective_trading_window(conn, view)
    if latest_date is None:
        return {'advances': 0, 'declines': 0, 'unchanged': 0}
    sql = f"""
        WITH series AS (
            SELECT
                v.symbol,
                v.trading_date,
                v.{close_col} AS close_value,
                LAG(v.{close_col}) OVER (PARTITION BY v.symbol ORDER BY v.trading_date) AS prev_day_close
            FROM {view} v
        )
        SELECT
            SUM(CASE WHEN close_value > prev_day_close THEN 1 ELSE 0 END) AS advances,
            SUM(CASE WHEN close_value < prev_day_close THEN 1 ELSE 0 END) AS declines,
            SUM(CASE WHEN close_value = prev_day_close THEN 1 ELSE 0 END) AS unchanged,
            COUNT(*) AS total_symbols
        FROM series
        WHERE trading_date = :latest_date
    """
    rows = _execute_query(conn, sql, {'latest_date': latest_date})
    if not rows:
        return {'advances': 0, 'declines': 0, 'unchanged': 0}
    row = rows[0]
    advances = int(row.get('advances') or 0)
    declines = int(row.get('declines') or 0)
    unchanged = int(row.get('unchanged') or 0)
    total_symbols = int(row.get('total_symbols') or 0)
    return {
        'advances': advances,
        'declines': declines,
        'unchanged': unchanged,
        'totalSymbols': total_symbols,
    }


def _fetch_combined_breadth(conn, universe_counts: Dict[str, int]) -> Dict[str, int]:
    totals = {'advances': 0, 'declines': 0, 'unchanged': 0, 'totalSymbols': 0}
    for segment_key in ('nifty50', 'next50', 'midcap', 'smallcap'):
        config = SEGMENT_CONFIGS.get(segment_key)
        if not config:
            continue
        stats = _fetch_breadth(conn, _breadth_source_for_segment(segment_key, config, conn))
        totals['advances'] += stats.get('advances', 0)
        totals['declines'] += stats.get('declines', 0)
        totals['unchanged'] += stats.get('unchanged', 0)
        totals['totalSymbols'] += stats.get('totalSymbols', 0)
    expected_total = sum(universe_counts.get(key, 0) for key in ('nifty50', 'next50', 'midcap', 'smallcap'))
    if expected_total <= 0:
        expected_total = universe_counts.get('nifty500') or 0
    totals['skip'] = max(totals['totalSymbols'] - (totals['advances'] + totals['declines'] + totals['unchanged']), 0)
    totals['expectedSymbols'] = expected_total
    totals['missingSymbols'] = max(expected_total - totals['totalSymbols'], 0)
    return totals


def _fetch_latest_counts(conn, view: str, symbol_table: str | None, universe_view: str | None = None) -> Dict[str, Any]:
    trading_date, _, _ = _resolve_effective_trading_window(conn, view)
    row = {}
    total_symbols = 0
    if trading_date is not None:
        sql = f"""
            SELECT
                COUNT(*) AS total_symbols
            FROM {view}
            WHERE trading_date = :trade_date
        """
        row = _execute_query(conn, sql, {'trade_date': trading_date})[0]
        total_symbols = int(row.get('total_symbols') or 0) if row else 0

    universe_symbols = 0
    if symbol_table:
        try:
            universe_symbols = int(_fetch_single_value(conn, f"SELECT COUNT(*) FROM {symbol_table}"))
        except Exception:
            universe_symbols = 0
    if universe_symbols == 0:
        universe_symbols = _count_universe_symbols(conn, universe_view or view)

    return {
        'trading_date': trading_date,
        'total_symbols': total_symbols,
        'universe_symbols': universe_symbols,
    }


def _fetch_top_movers_fast(conn, view: str, *, limit: int = 5) -> List[Dict[str, Any]]:
    close_col = _resolve_close_column(conn, view)
    volume_col = _resolve_volume_column(conn, view)
    volume_expr = f"v.{volume_col}" if volume_col else "NULL"
    limit = max(int(limit or 5), 1)
    latest_date, previous_market_date, _ = _resolve_effective_trading_window(conn, view)
    if latest_date is None:
        return []
    sql = f"""
        WITH current_rows AS (
            SELECT
                v.symbol,
                v.trading_date,
                v.{close_col} AS close_value,
                {volume_expr} AS volume_value
            FROM {view} v
            WHERE v.trading_date = :latest_date
        ),
        base AS (
            SELECT
                c.symbol,
                c.trading_date,
                c.close_value,
                c.volume_value,
                p.{close_col} AS prev_day_close,
                (c.close_value - p.{close_col}) AS points_change,
                CASE
                    WHEN p.{close_col} IS NULL OR p.{close_col} = 0 THEN NULL
                    ELSE (c.close_value - p.{close_col}) / p.{close_col}
                END AS change_ratio
            FROM current_rows c
            LEFT JOIN {view} p
                ON p.symbol = c.symbol
               AND p.trading_date = :previous_market_date
            WHERE p.{close_col} IS NOT NULL
        ),
        ranked_gainers AS (
            SELECT
                b.symbol,
                b.trading_date,
                b.close_value,
                b.volume_value,
                b.prev_day_close,
                b.points_change,
                b.change_ratio,
                ROW_NUMBER() OVER (ORDER BY b.change_ratio DESC NULLS LAST, b.symbol) AS rnk
            FROM base b
            WHERE b.change_ratio > 0
        ),
        ranked_losers AS (
            SELECT
                b.symbol,
                b.trading_date,
                b.close_value,
                b.volume_value,
                b.prev_day_close,
                b.points_change,
                b.change_ratio,
                ROW_NUMBER() OVER (ORDER BY b.change_ratio ASC NULLS LAST, b.symbol) AS rnk
            FROM base b
            WHERE b.change_ratio < 0
        )
        SELECT 'GAINER' AS bucket, symbol, trading_date, close_value, volume_value, prev_day_close, points_change, change_ratio, rnk
        FROM ranked_gainers
        WHERE rnk <= :limit
        UNION ALL
        SELECT 'LOSER' AS bucket, symbol, trading_date, close_value, volume_value, prev_day_close, points_change, change_ratio, rnk
        FROM ranked_losers
        WHERE rnk <= :limit
        ORDER BY bucket, rnk
    """
    rows = _execute_query(conn, sql, {'limit': limit, 'latest_date': latest_date, 'previous_market_date': previous_market_date})
    trading_date = rows[0].get('trading_date') if rows else None
    _logger.info(
        'Dashboard movers SQL view=%s trading_date=%s rows=%s percentage_columns=current:%s previous:lag(%s) volume_column=%s',
        view,
        _fmt_iso_date(trading_date),
        len(rows),
        close_col,
        close_col,
        volume_col or 'NONE',
    )
    return rows


def _fetch_breadth_rows(conn) -> List[Dict[str, Any]]:
    segments = (
        ('nifty50', SEGMENT_CONFIGS['nifty50']),
        ('next50', SEGMENT_CONFIGS['next50']),
        ('midcap', SEGMENT_CONFIGS['midcap']),
        ('smallcap', SEGMENT_CONFIGS['smallcap']),
        ('niftytotal', SEGMENT_CONFIGS['nifty500']),
    )
    rows: List[Dict[str, Any]] = []
    effective_windows: Dict[str, Tuple[Optional[Any], Optional[Any], int]] = {}

    for key, cfg in segments:
        source = _breadth_source_for_segment(key, cfg, conn)
        close_col = _resolve_close_column(conn, source)
        window = effective_windows.get(source)
        if window is None:
            window = _resolve_effective_trading_window(conn, source)
            effective_windows[source] = window
        latest_date, previous_date, _ = window
        if latest_date is None:
            continue
        sql = f"""
            WITH current_rows AS (
                SELECT
                    v.trading_date,
                    v.{close_col} AS close_value,
                    v.symbol
                FROM {source} v
                WHERE v.trading_date = :latest_date
            ),
            previous_rows AS (
                SELECT
                    v.symbol,
                    v.{close_col} AS prev_day_close
                FROM {source} v
                WHERE v.trading_date = :previous_date
            )
            SELECT
                :segment_key AS segment_key,
                MAX(trading_date) AS trading_date,
                SUM(CASE WHEN c.close_value > p.prev_day_close THEN 1 ELSE 0 END) AS advances,
                SUM(CASE WHEN c.close_value < p.prev_day_close THEN 1 ELSE 0 END) AS declines,
                SUM(CASE WHEN c.close_value = p.prev_day_close THEN 1 ELSE 0 END) AS unchanged,
                COUNT(*) AS total_symbols
            FROM current_rows c
            LEFT JOIN previous_rows p
              ON p.symbol = c.symbol
        """
        segment_rows = _execute_query(
            conn,
            sql,
            {'segment_key': key, 'latest_date': latest_date, 'previous_date': previous_date},
        )
        if segment_rows:
            rows.append(segment_rows[0])

    # Explicitly calculate Nifty500 as the exact sum of its 4 constituents
    constituent_keys = ('nifty50', 'next50', 'midcap', 'smallcap')
    nifty500_advances = sum(int(r.get('advances') or 0) for r in rows if r.get('segment_key') in constituent_keys)
    nifty500_declines = sum(int(r.get('declines') or 0) for r in rows if r.get('segment_key') in constituent_keys)
    nifty500_unchanged = sum(int(r.get('unchanged') or 0) for r in rows if r.get('segment_key') in constituent_keys)
    nifty500_total = sum(int(r.get('total_symbols') or 0) for r in rows if r.get('segment_key') in constituent_keys)
    
    trading_date = next((r.get('trading_date') for r in rows if r.get('segment_key') in constituent_keys and r.get('trading_date') is not None), None)

    if trading_date is not None:
        rows.append({
            'segment_key': 'nifty500',
            'trading_date': trading_date,
            'advances': nifty500_advances,
            'declines': nifty500_declines,
            'unchanged': nifty500_unchanged,
            'total_symbols': nifty500_total
        })

    rows.sort(key=lambda r: _BREADTH_ORDER.index((r.get('segment_key') or '').lower()) if (r.get('segment_key') or '').lower() in _BREADTH_ORDER else len(_BREADTH_ORDER))
    for idx, row in enumerate(rows, 1):
        row['sNo'] = idx
    return rows


def _count_symbols_for_date(conn, view: str, trade_date: datetime | None = None) -> int:
    if trade_date is None:
        latest_date, _, _ = _resolve_effective_trading_window(conn, view)
        if latest_date is None:
            return 0
        sql = f"""
            SELECT COUNT(*)
            FROM {view}
            WHERE trading_date = :trade_date
        """
        params = {'trade_date': latest_date}
    else:
        sql = f"SELECT COUNT(*) FROM {view} WHERE trading_date = :trade_date"
        params = {'trade_date': trade_date}
    value = _fetch_single_value(conn, sql, params)
    return int(value or 0)


def _count_universe_symbols(conn, view: str) -> int:
    sql = f"SELECT COUNT(DISTINCT symbol) FROM {view}"
    value = _fetch_single_value(conn, sql)
    return int(value or 0)


def _segment_universe_count(conn, cfg: SegmentConfig) -> int:
    if cfg.symbol_table:
        try:
            value = _fetch_single_value(conn, f"SELECT COUNT(*) FROM {cfg.symbol_table}")
            if value:
                return int(value)
        except Exception:
            pass
    return _count_universe_symbols(conn, cfg.view)


def _get_universe_counts(conn) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for key, cfg in SEGMENT_CONFIGS.items():
        counts[key] = _segment_universe_count(conn, cfg)
    constituent_total = sum(counts.get(key, 0) for key in ('nifty50', 'next50', 'midcap', 'smallcap'))
    counts['nifty500'] = constituent_total or counts.get('nifty500') or 0
    return counts


def _serialize_movers(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    serialized: List[Dict[str, Any]] = []
    for idx, row in enumerate(rows, 1):
        symbol = (row.get('symbol') or '').upper()
        close_val = _safe_float(
            row.get('close_value')
            or row.get('close_price')
            or row.get('previous_close_value')
            or row.get('previous_close')
        )
        prev_val = _safe_float(row.get('prev_day_close') or row.get('previous_close_value') or row.get('previous_close'))
        points_val = _safe_float(row.get('points_change'))
        change_ratio = _safe_float(row.get('change_ratio'))
        if points_val is None and close_val is not None and prev_val is not None:
            points_val = close_val - prev_val
        if change_ratio is None and close_val is not None and prev_val not in (None, 0):
            change_ratio = (close_val - prev_val) / prev_val
        prev_close = round(prev_val, 2) if prev_val is not None else None
        price = round(close_val, 2) if close_val is not None else None
        points = round(points_val, 2) if points_val is not None else None
        percent = round((change_ratio or 0) * 100, 2) if change_ratio is not None else None
        volume_val = _safe_float(row.get('volume_value') or row.get('volume'))
        if volume_val is None:
            volume: Optional[float | int] = None
        elif float(volume_val).is_integer():
            volume = int(volume_val)
        else:
            volume = round(volume_val, 2)
        serialized.append({
            'sNo': idx,
            'symbol': symbol,
            'stockName': symbol,
            'stock': symbol,
            'tradingDate': _fmt_date(row.get('trading_date')),
            'ltcDate': _fmt_date(row.get('trading_date')),
            'ltc_date': _fmt_date(row.get('trading_date')),
            'price': price,
            'close': price,
            'previousClose': prev_close,
            'points': points,
            'change': points,
            'changeFormatted': f"{points:+.2f}" if points is not None else None,
            'percentage': percent,
            'percentChange': percent,
            'percentageFormatted': f"{percent:+.2f}%" if percent is not None else None,
            'volume': volume,
            'VOLUME': volume,
        })
    return serialized


_NIFTY50_TOP_MOVERS_BASE_SQL = """
base AS (
  SELECT
    curr.trading_date,
    curr.symbol,
    curr.previous_close AS close_price,
    prev.previous_close AS prev_day_close,
    (curr.previous_close - prev.previous_close) AS chg,
    ROUND((curr.previous_close - prev.previous_close) / NULLIF(prev.previous_close, 0) * 100, 2) AS chg_pct,
    curr.volume
  FROM nse_nifty500_daily_raw_data_dev curr
  JOIN nse_nifty50_largecap lc
    ON lc.symbol = curr.symbol
  JOIN (
    SELECT
      MAX(trading_date) AS latest_date,
      MAX(CASE
            WHEN trading_date < (SELECT MAX(trading_date) FROM nse_nifty500_daily_raw_data_dev)
            THEN trading_date
          END) AS prev_market_date
    FROM nse_nifty500_daily_raw_data_dev
  ) d
    ON curr.trading_date = d.latest_date
  LEFT JOIN nse_nifty500_daily_raw_data_dev prev
    ON prev.symbol = curr.symbol
   AND prev.trading_date = d.prev_market_date
  WHERE prev.previous_close IS NOT NULL
)
"""


def _serialize_nifty50_top_mover_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    payload_rows: List[Dict[str, Any]] = []
    for row in rows:
        close_val = _safe_float(row.get('close_price'))
        chg_val = _safe_float(row.get('chg'))
        chg_pct_val = _safe_float(row.get('chg_pct'))
        volume_val = _safe_float(row.get('volume'))
        if volume_val is None:
            volume: Optional[float | int] = None
        elif float(volume_val).is_integer():
            volume = int(volume_val)
        else:
            volume = round(volume_val, 2)
        payload_rows.append({
            'symbol': str(row.get('symbol') or '').upper(),
            'close': round(close_val, 2) if close_val is not None else None,
            'chg': round(chg_val, 2) if chg_val is not None else None,
            'chg_pct': round(chg_pct_val, 2) if chg_pct_val is not None else None,
            'volume': volume,
        })
    return payload_rows


def _serialize_nifty50_dashboard_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    payload_rows: List[Dict[str, Any]] = []
    for idx, row in enumerate(rows, 1):
        symbol = str(row.get('symbol') or '').upper()
        close_val = _safe_float(row.get('close_price'))
        prev_day_close_val = _safe_float(row.get('prev_day_close'))
        chg_val = _safe_float(row.get('chg'))
        chg_pct_val = _safe_float(row.get('chg_pct'))
        volume_val = _safe_float(row.get('volume'))
        close_price = round(close_val, 2) if close_val is not None else None
        prev_day_close = round(prev_day_close_val, 2) if prev_day_close_val is not None else None
        points = round(chg_val, 2) if chg_val is not None else None
        percent = round(chg_pct_val, 2) if chg_pct_val is not None else None
        if volume_val is None:
            volume: Optional[float | int] = None
        elif float(volume_val).is_integer():
            volume = int(volume_val)
        else:
            volume = round(volume_val, 2)
        payload_rows.append({
            'sNo': idx,
            'symbol': symbol,
            'stockName': symbol,
            'stock': symbol,
            'tradingDate': _fmt_date(row.get('trading_date')),
            'ltcDate': _fmt_date(row.get('trading_date')),
            'ltc_date': _fmt_date(row.get('trading_date')),
            'price': close_price,
            'close': close_price,
            'previousClose': prev_day_close,
            'points': points,
            'change': points,
            'changeFormatted': f"{points:+.2f}" if points is not None else None,
            'percentage': percent,
            'percentChange': percent,
            'percentageFormatted': f"{percent:+.2f}%" if percent is not None else None,
            'volume': volume,
            'VOLUME': volume,
        })
    return payload_rows


def _normalize_mover_aliases(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    output_rows: List[Dict[str, Any]] = []
    for row in rows:
        output = dict(row)
        symbol = str(output.get('symbol') or output.get('stock') or output.get('stockName') or '').strip().upper()
        if symbol:
            output['symbol'] = symbol
            output.setdefault('SYMBOL', symbol)
            output.setdefault('stock', symbol)
            output.setdefault('STOCK', symbol)
            output.setdefault('stockName', symbol)
        ltc_date = str(output.get('ltcDate') or output.get('ltc_date') or output.get('LTC_DATE') or output.get('tradingDate') or '').strip()
        if ltc_date:
            output['ltcDate'] = ltc_date
            output['ltc_date'] = ltc_date
            output['LTC_DATE'] = ltc_date
        rank_value = output.get('mcapRank')
        if rank_value is None:
            rank_value = output.get('MCAP_RANK')
        if rank_value is not None:
            output['mcapRank'] = rank_value
            output['mcap_rank'] = rank_value
            output['MCAP_RANK'] = rank_value
        mcap_value = output.get('mcap')
        if mcap_value is None:
            mcap_value = output.get('MCAP')
        if mcap_value is not None:
            output['mcap'] = mcap_value
            output['MCAP'] = mcap_value
            output['market_cap'] = mcap_value
        index_value = output.get('index')
        if index_value in (None, ''):
            index_value = output.get('INDEX')
        if index_value not in (None, ''):
            output['index'] = index_value
            output['INDEX'] = index_value
        volume_value = output.get('volume')
        if volume_value is None:
            volume_value = output.get('VOLUME')
        if volume_value is not None:
            output['volume'] = volume_value
            output['VOLUME'] = volume_value
        output_rows.append(output)
    return output_rows


def _fetch_nifty50_top_movers_rows(conn, limit: int = 5) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Any]:
    limit = max(1, min(int(limit or 5), 50))
    trading_date, previous_market_date, _ = _resolve_effective_trading_window(conn, 'nse_nifty500_daily_raw_data_dev')
    if trading_date is None:
        return [], [], None

    gainers_sql = f"""
        WITH base AS (
            SELECT
                curr.trading_date,
                curr.symbol,
                curr.previous_close AS close_price,
                prev.previous_close AS prev_day_close,
                (curr.previous_close - prev.previous_close) AS chg,
                ROUND((curr.previous_close - prev.previous_close) / NULLIF(prev.previous_close, 0) * 100, 2) AS chg_pct,
                curr.volume
            FROM nse_nifty500_daily_raw_data_dev curr
            JOIN nse_nifty50_largecap lc
              ON lc.symbol = curr.symbol
            LEFT JOIN nse_nifty500_daily_raw_data_dev prev
              ON prev.symbol = curr.symbol
             AND prev.trading_date = :previous_market_date
            WHERE curr.trading_date = :trading_date
              AND prev.previous_close IS NOT NULL
        )
        SELECT * FROM base WHERE chg_pct > 0 ORDER BY chg_pct DESC FETCH FIRST {limit} ROWS ONLY
    """
    losers_sql = f"""
        WITH base AS (
            SELECT
                curr.trading_date,
                curr.symbol,
                curr.previous_close AS close_price,
                prev.previous_close AS prev_day_close,
                (curr.previous_close - prev.previous_close) AS chg,
                ROUND((curr.previous_close - prev.previous_close) / NULLIF(prev.previous_close, 0) * 100, 2) AS chg_pct,
                curr.volume
            FROM nse_nifty500_daily_raw_data_dev curr
            JOIN nse_nifty50_largecap lc
              ON lc.symbol = curr.symbol
            LEFT JOIN nse_nifty500_daily_raw_data_dev prev
              ON prev.symbol = curr.symbol
             AND prev.trading_date = :previous_market_date
            WHERE curr.trading_date = :trading_date
              AND prev.previous_close IS NOT NULL
        )
        SELECT * FROM base WHERE chg_pct < 0 ORDER BY chg_pct ASC FETCH FIRST {limit} ROWS ONLY
    """
    binds = {'trading_date': trading_date, 'previous_market_date': previous_market_date}
    gainers_rows = _execute_query(conn, gainers_sql, binds)
    losers_rows = _execute_query(conn, losers_sql, binds)
    _logger.info(
        'Nifty50 movers SQL trading_date=%s gainers_rows=%s losers_rows=%s percentage_columns=current:previous_close previous:lag(previous_close)',
        _fmt_iso_date(trading_date),
        len(gainers_rows),
        len(losers_rows),
    )
    return gainers_rows, losers_rows, trading_date


def load_nifty50_top_movers_payload(limit: int = 5) -> Dict[str, Any]:
    limit = max(1, min(int(limit or 5), 50))
    conn = get_oracle_connection()
    try:
        gainers_rows, losers_rows, trading_date = _fetch_nifty50_top_movers_rows(conn, limit=limit)
        return {
            'trading_date': _fmt_iso_date(trading_date),
            'gainers': _serialize_nifty50_top_mover_rows(gainers_rows),
            'losers': _serialize_nifty50_top_mover_rows(losers_rows),
        }
    finally:
        conn.close()


def get_dashboard_latest_trading_date(segment: str | None = None) -> str:
    config = _get_segment_config(segment)
    conn = get_oracle_connection()
    try:
        source_view = _latest_view(config, conn)
        latest, _, _ = _resolve_effective_trading_window(conn, source_view)
        return _fmt_date(latest)
    finally:
        conn.close()


def _empty_payload(segment: str | None = None) -> Dict[str, Any]:
    seg = (segment or DEFAULT_SEGMENT).strip().lower() or DEFAULT_SEGMENT
    return {
        'tradingDate': '',
        'totalSymbols': 0,
        'universeSymbols': 0,
        'gainers': [],
        'losers': [],
        'breadth': {'advances': 0, 'declines': 0, 'unchanged': 0, 'skip': 0, 'totalSymbols': 0},
        'breadthRows': [],
        'segment': seg,
    }


def _serialize_breadth_rows(rows: List[Dict[str, Any]], universe_counts: Dict[str, int]) -> List[Dict[str, Any]]:
    serialized: List[Dict[str, Any]] = []
    for row in rows:
        segment = (row.get('segment_key') or '').lower()
        index_label = INDEX_LABELS.get(segment, segment.upper())
        total_symbols = int(row.get('total_symbols') or 0)
        advances = int(row.get('advances') or 0)
        declines = int(row.get('declines') or 0)
        unchanged = int(row.get('unchanged') or 0)
        expected_symbols = universe_counts.get(segment)
        if expected_symbols is None and segment == 'nifty500':
            expected_symbols = sum(
                universe_counts.get(key, 0) for key in ('nifty50', 'next50', 'midcap', 'smallcap')
            ) or universe_counts.get('nifty500')
        if expected_symbols is None:
            expected_symbols = total_symbols
        row_total = advances + declines + unchanged
        skip = max(total_symbols - row_total, 0)
        missing_symbols = max(expected_symbols - total_symbols, 0)
        serialized.append({
            'segment': segment,
            'index': index_label,
            'tradingDate': _fmt_date(row.get('trading_date')),
            'advances': advances,
            'declines': declines,
            'unchanged': unchanged,
            'skip': skip,
            'totalSymbols': total_symbols,
            'expectedSymbols': expected_symbols,
            'missingSymbols': missing_symbols,
        })
    serialized.sort(key=lambda r: _BREADTH_ORDER.index(r['segment']) if r['segment'] in _BREADTH_ORDER else len(_BREADTH_ORDER))
    for idx, row in enumerate(serialized, 1):
        row['sNo'] = idx
    return serialized


def load_dashboard_payload(segment: str | None = None, mover_limit: int = DEFAULT_MOVERS_LIMIT) -> Dict[str, Any]:
    config = _get_segment_config(segment)
    segment_key = (segment or DEFAULT_SEGMENT).strip().lower() or DEFAULT_SEGMENT
    conn = get_oracle_connection()
    try:
        source_view = _latest_view(config, conn)
        mover_trading_date = None
        if segment_key == 'nifty50':
            # Keep dashboard movers in sync with /api/nifty50/top-movers SQL
            # (today close vs previous day close via LAG).
            gainers_rows, losers_rows, mover_trading_date = _fetch_nifty50_top_movers_rows(conn, limit=mover_limit)
            gainers = _serialize_nifty50_dashboard_rows(gainers_rows)
            losers = _serialize_nifty50_dashboard_rows(losers_rows)
        else:
            movers_raw = _fetch_top_movers_fast(conn, source_view, limit=mover_limit)
            gainers = _serialize_movers([row for row in movers_raw if (row.get('bucket') or '').upper() == 'GAINER'])
            losers = _serialize_movers([row for row in movers_raw if (row.get('bucket') or '').upper() == 'LOSER'])

        _fill_missing_mover_volumes(conn, source_view, gainers)
        _fill_missing_mover_volumes(conn, source_view, losers)
        gainers = nse_mcap_svc.enrich_rows_with_marketcap_index(gainers)
        losers = nse_mcap_svc.enrich_rows_with_marketcap_index(losers)
        gainers = _normalize_mover_aliases(gainers)
        losers = _normalize_mover_aliases(losers)

        meta = _fetch_latest_counts(conn, source_view, config.symbol_table, config.view)
        universe_counts = _get_universe_counts(conn)
        breadth_rows_raw = _fetch_breadth_rows(conn)
        breadth_rows = _serialize_breadth_rows(breadth_rows_raw, universe_counts)
        breadth_total = next((row for row in breadth_rows if row.get('segment') == 'nifty500'), None)
        breadth = {
            'advances': int(breadth_total['advances']) if breadth_total else 0,
            'declines': int(breadth_total['declines']) if breadth_total else 0,
            'unchanged': int(breadth_total['unchanged']) if breadth_total else 0,
            'skip': int(breadth_total.get('skip') or 0) if breadth_total else 0,
            'totalSymbols': int(breadth_total.get('totalSymbols') or 0) if breadth_total else 0,
            'expectedSymbols': int(breadth_total.get('expectedSymbols') or 0) if breadth_total else 0,
            'missingSymbols': int(breadth_total.get('missingSymbols') or 0) if breadth_total else 0,
        } if breadth_total else _fetch_combined_breadth(conn, universe_counts)

        trading_date_fmt = _fmt_date(mover_trading_date) or _fmt_date(meta.get('trading_date'))
        if not trading_date_fmt and gainers:
            trading_date_fmt = gainers[0].get('tradingDate') or ''

        required_keys = ('symbol', 'index', 'mcap', 'mcap_rank', 'volume', 'ltc_date')

        def _missing_counts(rows: List[Dict[str, Any]]) -> Dict[str, int]:
            counts: Dict[str, int] = {}
            for key in required_keys:
                counts[key] = sum(
                    1
                    for row in rows
                    if row.get(key) in (None, '') and row.get(key.upper()) in (None, '')
                )
            return counts

        _logger.info(
            'Dashboard movers payload segment=%s gainers=%s losers=%s gainers_row0_keys=%s losers_row0_keys=%s missing_gainers=%s missing_losers=%s',
            segment_key,
            len(gainers),
            len(losers),
            sorted((gainers[0] if gainers else {}).keys()),
            sorted((losers[0] if losers else {}).keys()),
            _missing_counts(gainers),
            _missing_counts(losers),
        )

        return {
            'tradingDate': trading_date_fmt,
            'totalSymbols': int(meta.get('total_symbols') or 0),
            'universeSymbols': int(meta.get('universe_symbols') or 0) or int(meta.get('total_symbols') or 0),
            'gainers': gainers,
            'losers': losers,
            'breadth': breadth,
            'breadthRows': breadth_rows,
            'segment': segment_key,
        }
    finally:
        conn.close()
