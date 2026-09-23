from __future__ import annotations

import logging
import os
import re
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

from db import get_oracle_connection

logger = logging.getLogger(__name__)

def _load_dynamic_ui_sector_groups() -> list[tuple[str, str, list[str]]]:
    """Dynamically load sector groups from NSE_SECTOR_MASTER."""
    try:
        from db import get_oracle_connection
        conn = get_oracle_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute('SELECT SECTOR_CODE, SECTOR_NAME FROM NSE_SECTOR_MASTER ORDER BY DISPLAY_ORDER')
                rows = cursor.fetchall()
                if not rows:
                    logger.warning("No sectors found in NSE_SECTOR_MASTER.")
                    return []
                return [(row[0], row[1], [row[0]]) for row in rows]
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Failed to load sector groups dynamically: {e}")
        return []

_UI_SECTOR_GROUPS: list[tuple[str, str, list[str]]] = []
_SECTOR_GROUPS_LOADED = False

def get_ui_sector_groups() -> list[tuple[str, str, list[str]]]:
    global _UI_SECTOR_GROUPS, _SECTOR_GROUPS_LOADED
    if not _SECTOR_GROUPS_LOADED or not _UI_SECTOR_GROUPS:
        _UI_SECTOR_GROUPS = _load_dynamic_ui_sector_groups()
        _SECTOR_GROUPS_LOADED = True
    return _UI_SECTOR_GROUPS

def invalidate_sector_groups_cache() -> None:
    global _UI_SECTOR_GROUPS, _SECTOR_GROUPS_LOADED
    _UI_SECTOR_GROUPS = []
    _SECTOR_GROUPS_LOADED = False
    logger.info("Cleared dynamic UI sector groups cache.")

_INT_FIELDS = {'totalSymbols', 'rsi55Pct', 'rsi50Pct', 'sma20Pct', 'sma50Pct', 'sma100Pct', 'confirmedStocks', 'screenedStocks'}
_NUMERIC_FIELDS = (
    'totalSymbols', 'rsi55Pct', 'rsi50Pct', 'sma20Pct', 'sma50Pct', 'sma100Pct',
    'relativeMomentum', 'absoluteTrend', 'breadthComposite', 'mcapBreadth', 'ffmcBreadth',
    'countBreadth', 'riskAdjustment', 'rotationScore', 'finalRotation', 'stockConfirmationScoreAvg',
    'volumeRatio20', 'deliveryParticipationScore', 'obvSlopeScore',
    'accumulationScore', 'upDownVolumeScore', 'breadthVolumeScore',
)
_SQL_PATH = Path(__file__).resolve().parents[1] / 'sql' / 'sector_rotation_composite.sql'
_SAFE_SQL_NAME_RE = re.compile(r'^[A-Z][A-Z0-9_$#]*(?:\.[A-Z][A-Z0-9_$#]*)?$')
_FACT_SYNC_STATE: dict[str, Any] = {'checked_at': 0.0, 'fact_trade_date': None, 'raw_trade_date': None}
_REFERENCE_SYNC_STATE: dict[str, Any] = {'checked_at': 0.0, 'last_ok': False}
_SOURCE_COVERAGE_STATE: dict[str, Any] = {'checked_at': 0.0, 'raw_table': '', 'fact': None, 'raw': None}


def _env_float(name: str, default: float) -> float:
    raw = str(os.getenv(name, '')).strip()
    if not raw:
        return default
    try:
        return float(raw)
    except Exception:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, '')).strip().lower()
    if not raw:
        return default
    return raw in {'1', 'true', 'yes', 'y', 'on'}


def _env_int(name: str, default: int) -> int:
    raw = str(os.getenv(name, '')).strip()
    if not raw:
        return default
    try:
        return int(raw)
    except Exception:
        return default


def _normalize(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


@lru_cache(maxsize=1)
def _load_sql_template() -> str:
    return _SQL_PATH.read_text(encoding='utf-8')


def _coerce_date(value: Any) -> date | None:
    normalized = _normalize(value)
    if isinstance(normalized, date) and not isinstance(normalized, datetime):
        return normalized
    text = str(normalized or '').strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text[:10]).date()
    except Exception:
        return None


def _as_float(value: Any) -> float | None:
    normalized = _normalize(value)
    if normalized is None or normalized == '':
        return None
    try:
        return float(normalized)
    except Exception:
        return None


def _as_int(value: Any) -> int:
    normalized = _as_float(value)
    if normalized is None:
        return 0
    return int(round(normalized))


def _is_safe_sql_name(value: str, *, allow_dot: bool = False) -> bool:
    token = str(value or '').strip().upper()
    if not token:
        return False
    if not allow_dot and '.' in token:
        return False
    return bool(_SAFE_SQL_NAME_RE.fullmatch(token))


def _qualified_table_name(schema: str, table: str) -> str:
    normalized_table = str(table or '').strip().upper()
    normalized_schema = str(schema or '').strip().upper()
    qualified = f'{normalized_schema}.{normalized_table}' if normalized_schema else normalized_table
    if not _is_safe_sql_name(qualified, allow_dot=True):
        raise ValueError(f'Unsafe Oracle table name: {qualified}')
    return qualified


def _query_max_trade_date(table_name: str) -> date | None:
    if not _is_safe_sql_name(table_name, allow_dot=True):
        return None
    conn = get_oracle_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(f'SELECT MAX(trading_date) FROM {table_name}')
            row = cursor.fetchone()
            return _coerce_date(row[0] if row else None)
    except Exception:
        return None
    finally:
        conn.close()


def _query_symbol_coverage(table_name: str, trade_date: date | None) -> int:
    if trade_date is None or not _is_safe_sql_name(table_name, allow_dot=True):
        return 0
    conn = get_oracle_connection()
    try:
        with conn.cursor() as cursor:
            if table_name == 'FACT_OHLCV':
                cursor.execute(
                    """
                    SELECT COUNT(DISTINCT f.symbol_id)
                    FROM FACT_OHLCV f
                    JOIN dim_symbols ds
                      ON ds.symbol_id = f.symbol_id
                     AND NVL(ds.is_active, 'Y') = 'Y'
                    WHERE f.trading_date = :trade_date
                    """,
                    {'trade_date': trade_date},
                )
            else:
                cursor.execute(
                    f"""
                    SELECT COUNT(DISTINCT REPLACE(REPLACE(REPLACE(REPLACE(UPPER(TRIM(symbol)), 'NSE:', ''), 'BSE:', ''), '-EQ', ''), ' ', ''))
                    FROM {table_name}
                    WHERE trading_date = :trade_date
                    """,
                    {'trade_date': trade_date},
                )
            row = cursor.fetchone()
            return int(row[0] or 0) if row else 0
    except Exception:
        logger.exception('Failed symbol coverage query for %s @ %s', table_name, trade_date)
        return 0
    finally:
        conn.close()


def _procedure_exists(proc_name: str) -> bool:
    normalized = str(proc_name or '').strip().upper()
    if not _is_safe_sql_name(normalized, allow_dot=True):
        return False
    owner = None
    object_name = normalized
    if '.' in normalized:
        owner, object_name = normalized.split('.', 1)
    conn = get_oracle_connection()
    try:
        with conn.cursor() as cursor:
            if owner:
                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM all_objects
                    WHERE owner = :owner
                      AND object_name = :object_name
                      AND object_type = 'PROCEDURE'
                    """,
                    {'owner': owner, 'object_name': object_name},
                )
            else:
                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM user_objects
                    WHERE object_name = :object_name
                      AND object_type = 'PROCEDURE'
                    """,
                    {'object_name': object_name},
                )
            row = cursor.fetchone()
            return bool(row and int(row[0] or 0) > 0)
    except Exception:
        logger.exception('Failed to resolve procedure %s', normalized)
        return False
    finally:
        conn.close()


def _call_procedure(proc_name: str, args: list[Any] | tuple[Any, ...] | None = None, log_label: str | None = None) -> bool:
    conn = get_oracle_connection()
    try:
        with conn.cursor() as cursor:
            cursor.callproc(proc_name, list(args or []))
        conn.commit()
        return True
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        logger.exception('Failed %s via %s', log_label or 'Oracle procedure', proc_name)
        return False
    finally:
        conn.close()


def _call_fact_sync_procedure(proc_name: str, from_date: date | None, to_date: date | None) -> bool:
    return _call_procedure(proc_name, [from_date, to_date], 'FACT_OHLCV sync')


def ensure_sector_reference_data_synced(force: bool = False) -> bool:
    if not _env_bool('SECTOR_ROTATION_REFERENCE_SYNC_ENABLED', True):
        return False

    ttl_seconds = max(_env_int('SECTOR_ROTATION_REFERENCE_SYNC_TTL_SECONDS', 3600), 0)
    now = time.monotonic()
    last_checked = float(_REFERENCE_SYNC_STATE.get('checked_at') or 0.0)
    if not force and ttl_seconds and (now - last_checked) < ttl_seconds:
        return bool(_REFERENCE_SYNC_STATE.get('last_ok'))

    proc_name = str(os.getenv('SECTOR_ROTATION_REFERENCE_SYNC_PROC') or 'PR_SYNC_SECTOR_REFERENCE_DATA').strip().upper()
    if not _procedure_exists(proc_name):
        logger.warning('Sector reference sync procedure %s is missing', proc_name)
        _REFERENCE_SYNC_STATE.update({'checked_at': now, 'last_ok': False})
        return False

    ok = _call_procedure(proc_name, [], 'sector reference sync')
    _REFERENCE_SYNC_STATE.update({'checked_at': time.monotonic(), 'last_ok': ok})
    return ok


def _maybe_sync_fact_ohlcv(
    raw_table_name: str | None,
    fact_trade_date: date | None,
    raw_trade_date: date | None,
) -> tuple[date | None, date | None]:
    ttl_seconds = max(_env_int('SECTOR_ROTATION_FACT_SYNC_TTL_SECONDS', 900), 0)
    now = time.monotonic()
    last_checked = float(_FACT_SYNC_STATE.get('checked_at') or 0.0)
    cached_fact = _FACT_SYNC_STATE.get('fact_trade_date')
    cached_raw = _FACT_SYNC_STATE.get('raw_trade_date')
    if ttl_seconds and (now - last_checked) < ttl_seconds:
        if isinstance(cached_raw, date) and raw_trade_date == cached_raw:
            return cached_fact if isinstance(cached_fact, date) else fact_trade_date, raw_trade_date

    if raw_table_name is None or raw_trade_date is None or (fact_trade_date is not None and fact_trade_date >= raw_trade_date):
        _FACT_SYNC_STATE.update({'checked_at': now, 'fact_trade_date': fact_trade_date, 'raw_trade_date': raw_trade_date})
        return fact_trade_date, raw_trade_date

    if not _env_bool('SECTOR_ROTATION_FACT_SYNC_ENABLED', True):
        _FACT_SYNC_STATE.update({'checked_at': now, 'fact_trade_date': fact_trade_date, 'raw_trade_date': raw_trade_date})
        return fact_trade_date, raw_trade_date

    proc_name = str(os.getenv('SECTOR_ROTATION_FACT_SYNC_PROC') or 'PR_SYNC_FACT_OHLCV_FROM_DEV').strip().upper()
    if not _procedure_exists(proc_name):
        logger.warning('FACT_OHLCV sync procedure %s is missing; raw fallback remains active', proc_name)
        _FACT_SYNC_STATE.update({'checked_at': now, 'fact_trade_date': fact_trade_date, 'raw_trade_date': raw_trade_date})
        return fact_trade_date, raw_trade_date

    from_date = (fact_trade_date + timedelta(days=1)) if fact_trade_date is not None else None
    if _call_fact_sync_procedure(proc_name, from_date, raw_trade_date):
        fact_trade_date = _query_max_trade_date('FACT_OHLCV')

    _FACT_SYNC_STATE.update({'checked_at': time.monotonic(), 'fact_trade_date': fact_trade_date, 'raw_trade_date': raw_trade_date})
    return fact_trade_date, raw_trade_date


def _resolve_price_source() -> dict[str, Any]:
    raw_schema = str(os.getenv('ORACLE_SCHEMA') or '').strip().upper()
    raw_table = str(os.getenv('ORACLE_TABLE') or 'NSE_NIFTY500_DAILY_RAW_DATA_DEV').strip().upper()
    fact_candidate = {'key': 'FACT_OHLCV', 'kind': 'fact', 'table': 'FACT_OHLCV', 'maxTradeDate': _query_max_trade_date('FACT_OHLCV')}
    raw_candidate: dict[str, Any] | None = None
    if raw_table:
        qualified_raw = _qualified_table_name(raw_schema, raw_table)
        if qualified_raw != 'FACT_OHLCV':
            raw_candidate = {'key': 'RAW_DAILY', 'kind': 'raw', 'table': qualified_raw, 'maxTradeDate': _query_max_trade_date(qualified_raw)}
            fact_candidate['maxTradeDate'], raw_candidate['maxTradeDate'] = _maybe_sync_fact_ohlcv(
                qualified_raw,
                fact_candidate.get('maxTradeDate'),
                raw_candidate.get('maxTradeDate'),
            )
    if raw_candidate:
        now = time.monotonic()
        coverage_ttl = max(_env_int('SECTOR_ROTATION_SOURCE_COVERAGE_TTL_SECONDS', 300), 30)
        cached_raw_table = str(_SOURCE_COVERAGE_STATE.get('raw_table') or '')
        if (
            (now - float(_SOURCE_COVERAGE_STATE.get('checked_at') or 0.0)) >= coverage_ttl
            or cached_raw_table != str(raw_candidate['table'])
            or _SOURCE_COVERAGE_STATE.get('fact') is None
            or _SOURCE_COVERAGE_STATE.get('raw') is None
        ):
            fact_count = _query_symbol_coverage('FACT_OHLCV', fact_candidate.get('maxTradeDate'))
            raw_count = _query_symbol_coverage(str(raw_candidate['table']), raw_candidate.get('maxTradeDate'))
            _SOURCE_COVERAGE_STATE.update(
                {
                    'checked_at': now,
                    'raw_table': str(raw_candidate['table']),
                    'fact': fact_count,
                    'raw': raw_count,
                }
            )
        fact_count = int(_SOURCE_COVERAGE_STATE.get('fact') or 0)
        raw_count = int(_SOURCE_COVERAGE_STATE.get('raw') or 0)
        logger.info(
            '[SECTOR_BREADTH_SOURCE_CHECK] source=FACT_OHLCV latestDate=%s symbols=%s',
            fact_candidate.get('maxTradeDate'),
            fact_count,
        )
        logger.info(
            '[SECTOR_BREADTH_SOURCE_CHECK] source=RAW latestDate=%s symbols=%s',
            raw_candidate.get('maxTradeDate'),
            raw_count,
        )
        if raw_count > 0:
            ratio = fact_count / float(raw_count) if raw_count else 0.0
            threshold = _env_float('SECTOR_ROTATION_FACT_COVERAGE_MIN_RATIO', 0.70)
            if ratio < threshold:
                logger.warning(
                    '[SECTOR_BREADTH_SOURCE_SELECTED] source=RAW_DAILY reason=fact_coverage_below_threshold ratio=%.4f threshold=%.4f',
                    ratio,
                    threshold,
                )
                return raw_candidate

    candidates = [fact_candidate] + ([raw_candidate] if raw_candidate else [])
    preferred = str(os.getenv('SECTOR_ROTATION_PRICE_SOURCE') or 'AUTO').strip().upper()
    if preferred and preferred != 'AUTO':
        for candidate in candidates:
            if candidate and preferred in {candidate['key'], candidate['table']} and candidate.get('maxTradeDate') is not None:
                logger.info('[SECTOR_BREADTH_SOURCE_SELECTED] source=%s reason=preferred_source', candidate['key'])
                return candidate

    require_fact = _env_bool('SECTOR_ROTATION_REQUIRE_FACT_OHLCV', True)
    fact_trade_date = fact_candidate.get('maxTradeDate')
    raw_trade_date = raw_candidate.get('maxTradeDate') if raw_candidate else None
    if fact_trade_date is not None and (require_fact or raw_trade_date is None or fact_trade_date >= raw_trade_date):
        logger.info('[SECTOR_BREADTH_SOURCE_SELECTED] source=FACT_OHLCV reason=require_fact_or_not_behind_raw')
        return fact_candidate
    if raw_candidate and raw_trade_date is not None:
        logger.info('[SECTOR_BREADTH_SOURCE_SELECTED] source=RAW_DAILY reason=fact_missing_or_behind_raw')
        return raw_candidate
    if fact_trade_date is not None:
        logger.info('[SECTOR_BREADTH_SOURCE_SELECTED] source=FACT_OHLCV reason=raw_missing')
        return fact_candidate
    logger.info('[SECTOR_BREADTH_SOURCE_SELECTED] source=%s reason=fallback', (raw_candidate or fact_candidate).get('key'))
    return raw_candidate or fact_candidate


def _price_source_cte(source: dict[str, Any]) -> str:
    table_name = str(source['table'])
    normalize_fact_symbol = (
        "REPLACE(REPLACE(REPLACE(REPLACE(UPPER(TRIM(ds.symbol)), 'NSE:', ''), 'BSE:', ''), '-EQ', ''), ' ', '')"
    )
    normalize_raw_symbol = (
        "REPLACE(REPLACE(REPLACE(REPLACE(UPPER(TRIM(symbol)), 'NSE:', ''), 'BSE:', ''), '-EQ', ''), ' ', '')"
    )
    if source.get('kind') == 'fact':
        return f"""price_source AS (
    SELECT
        {normalize_fact_symbol} AS symbol,
        f.trading_date,
        CAST(f.previous_close AS NUMBER(18, 6)) AS close_price,
        CAST(f.high AS NUMBER(18, 6)) AS high_price,
        CAST(f.low AS NUMBER(18, 6)) AS low_price,
        CAST(f.volume AS NUMBER(18, 6)) AS volume
    FROM {table_name} f
    JOIN dim_symbols ds
      ON ds.symbol_id = f.symbol_id
     AND NVL(ds.is_active, 'Y') = 'Y'
    WHERE f.previous_close IS NOT NULL
)"""
    return f"""price_source AS (
    SELECT
        {normalize_raw_symbol} AS symbol,
        trading_date,
        CAST(previous_close AS NUMBER(18, 6)) AS close_price,
        CAST(high AS NUMBER(18, 6)) AS high_price,
        CAST(low AS NUMBER(18, 6)) AS low_price,
        CAST(volume AS NUMBER(18, 6)) AS volume
    FROM {table_name}
    WHERE previous_close IS NOT NULL
)"""


def _render_sql(source: dict[str, Any]) -> str:
    return _load_sql_template().replace('__PRICE_SOURCE_CTE__', _price_source_cte(source), 1)


def _weighted_average(rows: list[dict[str, Any]], field: str) -> float | None:
    total_weight = 0.0
    weighted_sum = 0.0
    for row in rows:
        value = _as_float(row.get(field))
        if value is None:
            continue
        weight = float(max(_as_int(row.get('totalSymbols')), 1))
        weighted_sum += value * weight
        total_weight += weight
    if total_weight <= 0:
        return None
    return round(weighted_sum / total_weight, 6)


def _confirmation_label(confirmed: int, screened: int) -> tuple[str, str]:
    if screened <= 0:
        return 'Neutral', 'Neutral / NA'
    ratio = confirmed / screened
    strong_ratio = _env_float('SECTOR_ROTATION_CONFIRMATION_STRONG_RATIO', 0.65)
    moderate_ratio = _env_float('SECTOR_ROTATION_CONFIRMATION_MODERATE_RATIO', 0.35)
    if ratio >= strong_ratio:
        label = 'Strong'
    elif ratio >= moderate_ratio:
        label = 'Moderate'
    else:
        label = 'Weak'
    return label, f'{label} ({confirmed}/{screened})'


def _sort_rows_by_rotation(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            row.get('finalRotation') is None,
            -(_as_float(row.get('finalRotation')) or 0.0),
            str(row.get('sectorName') or ''),
            str(row.get('sectorCode') or ''),
        ),
    )


def _assign_rank_scores(rows: list[dict[str, Any]]) -> None:
    total = len(rows)
    for idx, row in enumerate(rows):
        if total <= 1:
            row['rankScore'] = 100.0
        else:
            row['rankScore'] = round(((total - idx - 1) / (total - 1)) * 100, 2)


def _normalize_sector_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw_map: dict[str, dict[str, Any]] = {}
    for row in rows:
        code = str(row.get('sectorCode') or '').strip().upper()
        if code:
            raw_map[code] = row

    normalized_rows: list[dict[str, Any]] = []
    for sector_code, sector_name, source_codes in get_ui_sector_groups():
        matched = [raw_map[code] for code in source_codes if code in raw_map]
        if not matched:
            continue

        normalized_row: dict[str, Any] = {
            'sectorCode': sector_code,
            'sectorName': sector_name,
            'indexCode': matched[0].get('indexCode') if len(matched) == 1 else sector_code,
            'asOfDate': max((str(row.get('asOfDate') or '') for row in matched), default=''),
        }
        for field in _NUMERIC_FIELDS:
            value = _weighted_average(matched, field)
            if field in _INT_FIELDS and value is not None:
                normalized_row[field] = int(round(value))
            else:
                normalized_row[field] = value

        total_symbols = sum(_as_int(row.get('totalSymbols')) for row in matched)
        confirmed_stocks = sum(_as_int(row.get('confirmedStocks')) for row in matched)
        screened_stocks = sum(_as_int(row.get('screenedStocks')) for row in matched)
        label, screening = _confirmation_label(confirmed_stocks, screened_stocks)
        normalized_row['totalSymbols'] = total_symbols
        normalized_row['confirmedStocks'] = confirmed_stocks
        normalized_row['screenedStocks'] = screened_stocks
        normalized_row['stockConfirmationLabel'] = label
        normalized_row['stockConfirmationScreening'] = screening
        normalized_rows.append(normalized_row)

    normalized_rows = _sort_rows_by_rotation(normalized_rows)
    _assign_rank_scores(normalized_rows)
    return normalized_rows


def _query_rows(trade_date: date | None, source: dict[str, Any]) -> list[dict[str, Any]]:
    binds = {
        'requested_trade_date': trade_date,
        'delivery_pct_floor': _env_float('SECTOR_ROTATION_DELIVERY_PCT_FLOOR', 50.0),
        'delivery_qty_multiplier': _env_float('SECTOR_ROTATION_DELIVERY_QTY_MULTIPLIER', 1.0),
        'trade_qty_multiplier': _env_float('SECTOR_ROTATION_TRADE_QTY_MULTIPLIER', 1.0),
        'trade_count_multiplier': _env_float('SECTOR_ROTATION_TRADE_COUNT_MULTIPLIER', 1.0),
        'stock_confirmation_min_score': _env_float('SECTOR_ROTATION_STOCK_CONFIRMATION_MIN_SCORE', 0.70),
        'stock_confirmation_strong_ratio': _env_float('SECTOR_ROTATION_CONFIRMATION_STRONG_RATIO', 0.65),
        'stock_confirmation_moderate_ratio': _env_float('SECTOR_ROTATION_CONFIRMATION_MODERATE_RATIO', 0.35),
    }
    conn = get_oracle_connection()
    try:
        with conn.cursor() as cursor:
            import oracledb
            cursor.setinputsizes(requested_trade_date=oracledb.DB_TYPE_DATE)
            cursor.arraysize = 256
            cursor.execute(_render_sql(source), binds)
            columns = [col[0] for col in cursor.description or []]
            rows = cursor.fetchall()
    finally:
        conn.close()
    return [
        {columns[idx]: _normalize(row[idx]) for idx in range(len(columns))}
        for row in rows
    ]


def _recent_trade_dates(source: dict[str, Any], trade_date: date | None, limit: int) -> list[date]:
    table_name = str(source['table'])
    conn = get_oracle_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT trade_date
                FROM (
                    SELECT DISTINCT trading_date AS trade_date
                    FROM {table_name}
                    WHERE :requested_trade_date IS NULL OR trading_date <= :requested_trade_date
                    ORDER BY trading_date DESC
                )
                WHERE ROWNUM <= :limit_rows
                """,
                {'requested_trade_date': trade_date, 'limit_rows': int(limit)},
            )
            return [item for item in (_coerce_date(row[0]) for row in cursor.fetchall()) if item is not None]
    finally:
        conn.close()


def _rank_map(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {str(row.get('sectorCode') or '').strip().upper(): idx + 1 for idx, row in enumerate(_sort_rows_by_rotation(rows))}


def _attach_rotation_deltas(
    rows: list[dict[str, Any]],
    source: dict[str, Any],
    *,
    include_history: bool = False,
) -> list[dict[str, Any]]:
    if not rows:
        return rows
    anchor = max((_coerce_date(row.get('asOfDate')) for row in rows), default=None)
    for row in rows:
        row['finalRotationDelta5'] = None
        row['finalRotationDelta21'] = None
        row['rankChange5'] = None
        row['rankChange21'] = None
        row['priceSource'] = source['key']
        row['priceSourceTradeDate'] = anchor.isoformat() if anchor is not None else None

    if anchor is None or not include_history:
        return rows

    history = _recent_trade_dates(source, anchor, 22)
    prev5_date = history[5] if len(history) > 5 else None
    prev21_date = history[21] if len(history) > 21 else None

    prev5_rows = _normalize_sector_rows(_query_rows(prev5_date, source)) if prev5_date else []
    prev21_rows = _normalize_sector_rows(_query_rows(prev21_date, source)) if prev21_date else []
    prev5_map = {str(row.get('sectorCode') or '').strip().upper(): row for row in prev5_rows}
    prev21_map = {str(row.get('sectorCode') or '').strip().upper(): row for row in prev21_rows}
    current_rank = _rank_map(rows)
    prev5_rank = _rank_map(prev5_rows) if prev5_rows else {}
    prev21_rank = _rank_map(prev21_rows) if prev21_rows else {}

    for row in rows:
        code = str(row.get('sectorCode') or '').strip().upper()
        current_final = _as_float(row.get('finalRotation'))
        previous5_final = _as_float(prev5_map.get(code, {}).get('finalRotation'))
        previous21_final = _as_float(prev21_map.get(code, {}).get('finalRotation'))
        row['finalRotationDelta5'] = round(current_final - previous5_final, 6) if current_final is not None and previous5_final is not None else None
        row['finalRotationDelta21'] = round(current_final - previous21_final, 6) if current_final is not None and previous21_final is not None else None
        row['rankChange5'] = (prev5_rank.get(code) - current_rank.get(code)) if code in prev5_rank and code in current_rank else None
        row['rankChange21'] = (prev21_rank.get(code) - current_rank.get(code)) if code in prev21_rank and code in current_rank else None
    return rows


def fetch_sector_rotation_rows(
    trade_date: date | None = None,
    *,
    include_history: bool | None = None,
) -> list[dict[str, Any]]:
    if include_history is None:
        include_history = _env_bool('SECTOR_ROTATION_INCLUDE_HISTORY', False)
    source = _resolve_price_source()
    raw_rows = _query_rows(trade_date, source)
    normalized_rows = _normalize_sector_rows(raw_rows)
    return _attach_rotation_deltas(normalized_rows, source, include_history=include_history)
