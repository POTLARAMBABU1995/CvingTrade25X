from __future__ import annotations

import csv
import logging
import os
import re
import threading
import time
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from flask import Blueprint, jsonify, request

try:
    from ..db_pool import pool
except ImportError:  # pragma: no cover
    from db_pool import pool  # type: ignore

try:
    from ..services.strategy_agent_runtime_service import start_strategy_agent_execution
except ImportError:  # pragma: no cover
    from services.strategy_agent_runtime_service import start_strategy_agent_execution  # type: ignore
try:
    from ..services.dashboard_service import load_dashboard_payload
except ImportError:  # pragma: no cover
    from services.dashboard_service import load_dashboard_payload  # type: ignore

try:
    from ..services.volume_service import compute_volume_rows
except ImportError:  # pragma: no cover
    from services.volume_service import compute_volume_rows  # type: ignore

try:
    from ..services.ui_notification_service import publish_notification
except ImportError:  # pragma: no cover
    from services.ui_notification_service import publish_notification  # type: ignore


bp = Blueprint('yamuna', __name__)
_logger = logging.getLogger(__name__)

_IDENT_RE = re.compile(r'^[A-Za-z0-9_.$#]+$')
_DDL_LOCK = threading.Lock()
_DDL_READY = False

YAMUNA_SCHEMA = (os.getenv('YAMUNA_SCHEMA') or os.getenv('ORACLE_SCHEMA') or '').strip()
YAMUNA_GAINERS_TABLE = (os.getenv('YAMUNA_GAINERS_TABLE') or 'GAINERS_TOP25').strip()
YAMUNA_LOOSERS_TABLE = (os.getenv('YAMUNA_LOOSERS_TABLE') or 'LOOSERS_TOP25').strip()
YAMUNA_VOLUME_TABLE = (os.getenv('YAMUNA_VOLUME_TABLE') or 'VOLUME_MOVERS_TOP25').strip()
YAMUNA_CSV_OUTPUT_DIR = (os.getenv('YAMUNA_CSV_OUTPUT_DIR') or r'E:\YAMUNA automation').strip()
YAMUNA_TOP_LIMIT = max(1, int(os.getenv('YAMUNA_TOP_LIMIT', '25')))
YAMUNA_AUTO_INGEST_ENABLED = str(os.getenv('YAMUNA_AUTO_INGEST_ENABLED', '1')).strip().lower() not in {'0', 'false', 'no', 'off'}
YAMUNA_AUTO_INGEST_TIME = (os.getenv('YAMUNA_AUTO_INGEST_TIME') or '18:05').strip() or '18:05'
_yamuna_auto_ingest_started = False


def _safe_identifier(value: str) -> str:
    name = (value or '').strip()
    if not name or not _IDENT_RE.match(name):
        raise ValueError(f'Invalid identifier: {value!r}')
    return name


def _qualify_table(value: str) -> str:
    table = _safe_identifier(value)
    if '.' in table:
        return table
    if YAMUNA_SCHEMA:
        return f'{_safe_identifier(YAMUNA_SCHEMA)}.{table}'
    return table


GAINERS_TABLE = _qualify_table(YAMUNA_GAINERS_TABLE)
LOOSERS_TABLE = _qualify_table(YAMUNA_LOOSERS_TABLE)
VOLUME_TABLE = _qualify_table(YAMUNA_VOLUME_TABLE)


def _parse_date_value(value: Any) -> Optional[date]:
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
    for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%Y/%m/%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(token, fmt).date()
        except Exception:
            continue
    return None


def _date_to_iso(value: Optional[date]) -> Optional[str]:
    if not value:
        return None
    return value.strftime('%Y-%m-%d')


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(',', '')
    if text.endswith('%'):
        text = text[:-1]
    if text.lower().endswith('x'):
        text = text[:-1]
    try:
        return float(text)
    except Exception:
        return None


def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not (value == value):  # NaN
            return None
        return int(round(value))
    text = str(value).strip().replace(',', '')
    if not text:
        return None
    try:
        return int(round(float(text)))
    except Exception:
        return None


def _normalize_rows(
    rows: Any,
    *,
    fallback_date: Optional[date],
    include_volume: bool,
) -> Tuple[List[Dict[str, Any]], int, List[Dict[str, Any]]]:
    items = rows if isinstance(rows, list) else []
    normalized: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    skipped = 0
    seen: set[Tuple[str, date]] = set()

    for idx, raw in enumerate(items):
        if not isinstance(raw, dict):
            skipped += 1
            errors.append({'row': idx, 'error': 'invalid row type'})
            continue
        stock_raw = raw.get('stock') or raw.get('symbol') or raw.get('STOCK') or raw.get('SYMBOL')
        stock = str(stock_raw or '').strip().upper()
        ltc_date = _parse_date_value(raw.get('ltc_date') or raw.get('ltcDate') or raw.get('LTC_DATE')) or fallback_date
        if not stock or not ltc_date:
            skipped += 1
            errors.append({'row': idx, 'error': 'missing stock or ltc_date'})
            continue
        dedupe_key = (stock, ltc_date)
        if dedupe_key in seen:
            skipped += 1
            errors.append({'row': idx, 'error': 'duplicate stock+ltc_date in payload'})
            continue
        seen.add(dedupe_key)

        s_no = _to_int(raw.get('s_no') or raw.get('sNo') or raw.get('S_NO'))
        if s_no is None:
            s_no = len(normalized) + 1

        entry = {
            's_no': s_no,
            'stock': stock,
            'ltc_date': ltc_date,
            'price': _to_float(raw.get('price') or raw.get('PRICE')),
            'percentage': _to_float(raw.get('percentage') or raw.get('percentChange') or raw.get('PERCENTAGE')),
            'points': _to_float(raw.get('points') or raw.get('change') or raw.get('POINTS')),
        }
        if include_volume:
            entry['volume'] = _to_int(raw.get('volume') or raw.get('VOLUME'))
        normalized.append(entry)

    return normalized, skipped, errors


def _chunked(values: List[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(values), size):
        yield values[i:i + size]


def _existing_keys(conn, table: str, rows: List[Dict[str, Any]]) -> set[Tuple[str, date]]:
    if not rows:
        return set()
    by_date: Dict[date, set[str]] = {}
    for row in rows:
        ltc_date = row.get('ltc_date')
        stock = row.get('stock')
        if isinstance(ltc_date, date) and stock:
            by_date.setdefault(ltc_date, set()).add(str(stock))

    existing: set[Tuple[str, date]] = set()
    with conn.cursor() as cur:
        for ltc_date, stocks in by_date.items():
            sorted_stocks = sorted(stocks)
            for batch in _chunked(sorted_stocks, 900):
                bind: Dict[str, Any] = {'ltc_date': ltc_date}
                placeholders: List[str] = []
                for idx, stock in enumerate(batch):
                    key = f's{idx}'
                    bind[key] = stock
                    placeholders.append(f':{key}')
                sql = (
                    f"SELECT STOCK FROM {table} "
                    f"WHERE LTC_DATE = :ltc_date AND STOCK IN ({', '.join(placeholders)})"
                )
                cur.execute(sql, bind)
                for (stock_val,) in cur.fetchall() or []:
                    if stock_val:
                        existing.add((str(stock_val).strip().upper(), ltc_date))
    return existing


def _is_unique_violation(exc: Exception) -> bool:
    return 'ORA-00001' in str(exc)


def _merge_rows(conn, table: str, rows: List[Dict[str, Any]], *, include_volume: bool) -> Tuple[int, int]:
    if not rows:
        return 0, 0
    existing = _existing_keys(conn, table, rows)
    if include_volume:
        merge_sql = f"""
            MERGE INTO {table} t
            USING (
                SELECT :stock AS STOCK,
                       :ltc_date AS LTC_DATE,
                       :s_no AS S_NO,
                       :price AS PRICE,
                       :percentage AS PERCENTAGE,
                       :points AS POINTS,
                       :volume AS VOLUME
                FROM dual
            ) s
            ON (t.STOCK = s.STOCK AND t.LTC_DATE = s.LTC_DATE)
            WHEN MATCHED THEN
              UPDATE SET
                t.S_NO = s.S_NO,
                t.PRICE = s.PRICE,
                t.PERCENTAGE = s.PERCENTAGE,
                t.POINTS = s.POINTS,
                t.VOLUME = s.VOLUME
            WHEN NOT MATCHED THEN
              INSERT (S_NO, STOCK, LTC_DATE, PRICE, PERCENTAGE, POINTS, VOLUME)
              VALUES (s.S_NO, s.STOCK, s.LTC_DATE, s.PRICE, s.PERCENTAGE, s.POINTS, s.VOLUME)
        """
    else:
        merge_sql = f"""
            MERGE INTO {table} t
            USING (
                SELECT :stock AS STOCK,
                       :ltc_date AS LTC_DATE,
                       :s_no AS S_NO,
                       :price AS PRICE,
                       :percentage AS PERCENTAGE,
                       :points AS POINTS
                FROM dual
            ) s
            ON (t.STOCK = s.STOCK AND t.LTC_DATE = s.LTC_DATE)
            WHEN MATCHED THEN
              UPDATE SET
                t.S_NO = s.S_NO,
                t.PRICE = s.PRICE,
                t.PERCENTAGE = s.PERCENTAGE,
                t.POINTS = s.POINTS
            WHEN NOT MATCHED THEN
              INSERT (S_NO, STOCK, LTC_DATE, PRICE, PERCENTAGE, POINTS)
              VALUES (s.S_NO, s.STOCK, s.LTC_DATE, s.PRICE, s.PERCENTAGE, s.POINTS)
        """
    inserted = max(len(rows) - len(existing), 0)
    skipped_existing = len(existing)
    with conn.cursor() as cur:
        try:
            cur.executemany(merge_sql, rows)
        except Exception as exc:
            if not _is_unique_violation(exc):
                raise
            inserted = 0
            skipped_existing = len(existing)
            for row in rows:
                key = (str(row.get('stock') or '').strip().upper(), row.get('ltc_date'))
                try:
                    cur.execute(merge_sql, row)
                    if key[0] and key[1] and key not in existing:
                        inserted += 1
                except Exception as row_exc:
                    if not _is_unique_violation(row_exc):
                        raise
                    skipped_existing += 1
    return inserted, skipped_existing


def _csv_path(filename: str) -> str:
    os.makedirs(YAMUNA_CSV_OUTPUT_DIR, exist_ok=True)
    return os.path.join(YAMUNA_CSV_OUTPUT_DIR, filename)


def _write_csv(path: str, headers: List[str], rows: List[List[Any]]) -> None:
    with open(path, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def _export_csvs(ltc_date: date, gainers: List[Dict[str, Any]], loosers: List[Dict[str, Any]], volume: List[Dict[str, Any]]) -> Dict[str, str]:
    token = ltc_date.strftime('%Y%m%d')
    gainers_path = _csv_path(f'GAINERS_TOP25_{token}.csv')
    loosers_path = _csv_path(f'LOOSERS_TOP25_{token}.csv')
    volume_path = _csv_path(f'VOLUME_MOVERS_TOP25_{token}.csv')

    _write_csv(
        gainers_path,
        ['S.NO', 'STOCK', 'LTC_DATE', 'PRICE', 'PERCENTAGE', 'POINTS'],
        [[row.get('s_no'), row.get('stock'), _date_to_iso(row.get('ltc_date')), row.get('price'), row.get('percentage'), row.get('points')] for row in gainers],
    )
    _write_csv(
        loosers_path,
        ['S.NO', 'STOCK', 'LTC_DATE', 'PRICE', 'PERCENTAGE', 'POINTS'],
        [[row.get('s_no'), row.get('stock'), _date_to_iso(row.get('ltc_date')), row.get('price'), row.get('percentage'), row.get('points')] for row in loosers],
    )
    _write_csv(
        volume_path,
        ['S.NO', 'STOCK', 'LTC_DATE', 'PRICE', 'PERCENTAGE', 'POINTS', 'VOLUME'],
        [[row.get('s_no'), row.get('stock'), _date_to_iso(row.get('ltc_date')), row.get('price'), row.get('percentage'), row.get('points'), row.get('volume')] for row in volume],
    )
    return {
        'gainers': gainers_path,
        'loosers': loosers_path,
        'volumeMovers': volume_path,
    }


def _execute_ddl(conn, ddl: str) -> None:
    with conn.cursor() as cur:
        try:
            cur.execute(ddl)
        except Exception as exc:
            msg = str(exc)
            if 'ORA-00955' in msg:
                return
            raise


def _ensure_yamuna_objects(conn) -> None:
    global _DDL_READY
    if _DDL_READY:
        return
    with _DDL_LOCK:
        if _DDL_READY:
            return
        _logger.info('Ensuring Yamuna Oracle objects')
        _execute_ddl(conn, f"""
            CREATE TABLE {GAINERS_TABLE} (
              ID         NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
              S_NO       NUMBER NOT NULL,
              STOCK      VARCHAR2(50) NOT NULL,
              LTC_DATE   DATE NOT NULL,
              PRICE      NUMBER(18,4),
              PERCENTAGE NUMBER(9,4),
              POINTS     NUMBER(18,4),
              CREATED_AT TIMESTAMP DEFAULT SYSTIMESTAMP,
              CONSTRAINT UK_GAINERS_TOP25 UNIQUE (STOCK, LTC_DATE)
            )
        """)
        _execute_ddl(conn, f"""
            CREATE TABLE {LOOSERS_TABLE} (
              ID         NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
              S_NO       NUMBER NOT NULL,
              STOCK      VARCHAR2(50) NOT NULL,
              LTC_DATE   DATE NOT NULL,
              PRICE      NUMBER(18,4),
              PERCENTAGE NUMBER(9,4),
              POINTS     NUMBER(18,4),
              CREATED_AT TIMESTAMP DEFAULT SYSTIMESTAMP,
              CONSTRAINT UK_LOOSERS_TOP25 UNIQUE (STOCK, LTC_DATE)
            )
        """)
        _execute_ddl(conn, f"""
            CREATE TABLE {VOLUME_TABLE} (
              ID         NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
              S_NO       NUMBER NOT NULL,
              STOCK      VARCHAR2(50) NOT NULL,
              LTC_DATE   DATE NOT NULL,
              PRICE      NUMBER(18,4),
              PERCENTAGE NUMBER(9,4),
              POINTS     NUMBER(18,4),
              VOLUME     NUMBER(20),
              CREATED_AT TIMESTAMP DEFAULT SYSTIMESTAMP,
              CONSTRAINT UK_VOLUME_MOVERS_TOP25 UNIQUE (STOCK, LTC_DATE)
            )
        """)
        _execute_ddl(conn, f"CREATE INDEX IDX_GAINERS_DATE ON {GAINERS_TABLE} (LTC_DATE)")
        _execute_ddl(conn, f"CREATE INDEX IDX_LOOSERS_DATE ON {LOOSERS_TABLE} (LTC_DATE)")
        _execute_ddl(conn, f"CREATE INDEX IDX_VOLUME_DATE ON {VOLUME_TABLE} (LTC_DATE)")
        conn.commit()
        _DDL_READY = True


def _cmp_iso_date(left: Optional[str], right: Optional[str]) -> int:
    if not left and not right:
        return 0
    if not left:
        return -1
    if not right:
        return 1
    return 1 if left > right else (-1 if left < right else 0)


def _yamuna_symbol(value: Any) -> str:
    return str(value or '').strip().upper()


def _yamuna_numeric(value: Any) -> Optional[float]:
    return _to_float(value)


def _yamuna_iso(value: Any) -> Optional[str]:
    parsed = _parse_date_value(value)
    return _date_to_iso(parsed) if parsed else None


def _yamuna_build_payload_from_sources() -> Dict[str, Any]:
    movers_payload = load_dashboard_payload('nifty500', mover_limit=YAMUNA_TOP_LIMIT)
    volume_rows, _volume_meta = compute_volume_rows()

    gainers_source = list(movers_payload.get('gainers') or [])
    losers_source = list(movers_payload.get('losers') or [])
    volume_source = list(volume_rows or [])
    by_symbol = {
        _yamuna_symbol(row.get('symbol')): row
        for row in (gainers_source + losers_source)
        if _yamuna_symbol(row.get('symbol'))
    }

    def build_payload_row(*, index: int, stock: Any, ltc_date: Any, price: Any, percentage: Any, points: Any, volume: Any = None) -> Optional[Dict[str, Any]]:
        symbol = _yamuna_symbol(stock)
        iso_date = _yamuna_iso(ltc_date)
        if not symbol or not iso_date:
            return None
        row = {
            's_no': index + 1,
            'stock': symbol,
            'ltc_date': iso_date,
            'price': _yamuna_numeric(price),
            'percentage': _yamuna_numeric(percentage),
            'points': _yamuna_numeric(points),
        }
        if volume is not None:
            row['volume'] = _to_int(volume)
        return row

    gainers: List[Dict[str, Any]] = []
    for index, row in enumerate(gainers_source):
        percent = _yamuna_numeric(row.get('percentage') if row.get('percentage') is not None else row.get('percentChange'))
        if percent is None or percent < 4:
            continue
        payload_row = build_payload_row(
            index=len(gainers),
            stock=row.get('symbol') or row.get('stockName'),
            ltc_date=row.get('tradingDate') or row.get('tradeDate') or row.get('ltcDate'),
            price=row.get('price') if row.get('price') is not None else row.get('close'),
            percentage=percent,
            points=row.get('points') if row.get('points') is not None else row.get('change'),
        )
        if payload_row:
            gainers.append(payload_row)
        if len(gainers) >= YAMUNA_TOP_LIMIT:
            break

    loosers: List[Dict[str, Any]] = []
    for row in losers_source:
        percent = _yamuna_numeric(row.get('percentage') if row.get('percentage') is not None else row.get('percentChange'))
        if percent is None or abs(percent) < 4:
            continue
        payload_row = build_payload_row(
            index=len(loosers),
            stock=row.get('symbol') or row.get('stockName'),
            ltc_date=row.get('tradingDate') or row.get('tradeDate') or row.get('ltcDate'),
            price=row.get('price') if row.get('price') is not None else row.get('close'),
            percentage=percent,
            points=row.get('points') if row.get('points') is not None else row.get('change'),
        )
        if payload_row:
            loosers.append(payload_row)
        if len(loosers) >= YAMUNA_TOP_LIMIT:
            break

    volume_candidates = [
        row for row in volume_source
        if (_yamuna_numeric(row.get('volumeRatio') if row.get('volumeRatio') is not None else row.get('volumeRatioSort')) or 0) >= 3
    ]
    volume_candidates.sort(key=lambda row: _yamuna_numeric(row.get('volumeRatioSort') if row.get('volumeRatioSort') is not None else row.get('volumeRatio')) or 0, reverse=True)

    volume_movers: List[Dict[str, Any]] = []
    for row in volume_candidates:
        symbol = _yamuna_symbol(row.get('symbol'))
        mover_row = by_symbol.get(symbol) or {}
        payload_row = build_payload_row(
            index=len(volume_movers),
            stock=symbol,
            ltc_date=row.get('ltcDate') or mover_row.get('ltcDate') or row.get('tradingDate') or mover_row.get('tradingDate') or row.get('tradeDate') or mover_row.get('tradeDate'),
            price=row.get('price') if row.get('price') is not None else mover_row.get('price') if mover_row.get('price') is not None else mover_row.get('close'),
            percentage=row.get('percentage') if row.get('percentage') is not None else row.get('percentChange') if row.get('percentChange') is not None else mover_row.get('percentage') if mover_row.get('percentage') is not None else mover_row.get('percentChange'),
            points=row.get('points') if row.get('points') is not None else row.get('change') if row.get('change') is not None else mover_row.get('points') if mover_row.get('points') is not None else mover_row.get('change'),
            volume=row.get('volume'),
        )
        if payload_row:
            volume_movers.append(payload_row)
        if len(volume_movers) >= YAMUNA_TOP_LIMIT:
            break

    all_dates = [
        row.get('ltc_date')
        for row in (gainers + loosers + volume_movers)
        if row.get('ltc_date')
    ]
    page_date = max(all_dates) if all_dates else _date_to_iso(date.today())
    return {
        'ltc_date': page_date,
        'gainers': gainers,
        'loosers': loosers,
        'volumeMovers': volume_movers,
    }


def _get_yamuna_last_ltc_dates() -> Dict[str, Optional[str]]:
    with pool.acquire() as conn:
        _ensure_yamuna_objects(conn)
        with conn.cursor() as cur:
            cur.execute(f"SELECT TO_CHAR(MAX(LTC_DATE), 'YYYY-MM-DD') FROM {GAINERS_TABLE}")
            gainers_max = (cur.fetchone() or [None])[0]
            cur.execute(f"SELECT TO_CHAR(MAX(LTC_DATE), 'YYYY-MM-DD') FROM {LOOSERS_TABLE}")
            loosers_max = (cur.fetchone() or [None])[0]
            cur.execute(f"SELECT TO_CHAR(MAX(LTC_DATE), 'YYYY-MM-DD') FROM {VOLUME_TABLE}")
            volume_max = (cur.fetchone() or [None])[0]
    return {
        'gainers_max': _yamuna_iso(gainers_max),
        'loosers_max': _yamuna_iso(loosers_max),
        'volume_max': _yamuna_iso(volume_max),
    }


def _yamuna_should_auto_ingest(page_date: Optional[str], last_dates: Dict[str, Optional[str]]) -> bool:
    if not page_date:
        return False
    return (
        _cmp_iso_date(page_date, last_dates.get('gainers_max')) > 0
        or _cmp_iso_date(page_date, last_dates.get('loosers_max')) > 0
        or _cmp_iso_date(page_date, last_dates.get('volume_max')) > 0
    )


def run_yamuna_auto_ingest_once(reason: str = 'startup') -> Optional[Dict[str, Any]]:
    if not YAMUNA_AUTO_INGEST_ENABLED:
        return None
    correlation_id = str(uuid.uuid4())
    payload = _yamuna_build_payload_from_sources()
    page_date = payload.get('ltc_date')
    total_rows = len(payload.get('gainers') or []) + len(payload.get('loosers') or []) + len(payload.get('volumeMovers') or [])
    if not page_date or total_rows <= 0:
        _logger.info('Yamuna auto-ingest skipped correlationId=%s reason=%s rows=%s pageDate=%s', correlation_id, reason, total_rows, page_date)
        return None

    last_dates = _get_yamuna_last_ltc_dates()
    if not _yamuna_should_auto_ingest(page_date, last_dates):
        try:
            publish_notification(
                source='yamuna_auto_ingest',
                message=f"Yamuna auto ingestion already up to date for {page_date}.",
                metadata={
                    'reason': reason,
                    'ltcDate': page_date,
                    'insertedRows': 0,
                    'lastDates': last_dates,
                },
            )
        except Exception as exc:
            _logger.warning('Yamuna auto-ingest up-to-date notification failed correlationId=%s error=%s', correlation_id, exc)
        _logger.info('Yamuna auto-ingest up-to-date correlationId=%s reason=%s pageDate=%s lastDates=%s', correlation_id, reason, page_date, last_dates)
        return {
            'status': 'ok',
            'upToDate': True,
            'ltc_date': page_date,
            'inserted': {'gainers': 0, 'loosers': 0, 'volumeMovers': 0},
            'skipped': {},
        }

    payload_ltc_date = _parse_date_value(payload.get('ltc_date'))
    gainers_rows, gainers_skipped, gainers_errors = _normalize_rows(payload.get('gainers'), fallback_date=payload_ltc_date, include_volume=False)
    loosers_rows, loosers_skipped, loosers_errors = _normalize_rows(payload.get('loosers'), fallback_date=payload_ltc_date, include_volume=False)
    volume_rows, volume_skipped, volume_errors = _normalize_rows(payload.get('volumeMovers'), fallback_date=payload_ltc_date, include_volume=True)
    all_dates = [
        row.get('ltc_date')
        for row in (gainers_rows + loosers_rows + volume_rows)
        if isinstance(row.get('ltc_date'), date)
    ]
    ltc_date = payload_ltc_date or (max(all_dates) if all_dates else date.today())
    ltc_date_iso = _date_to_iso(ltc_date) or date.today().strftime('%Y-%m-%d')

    csv_paths = _export_csvs(ltc_date, gainers_rows, loosers_rows, volume_rows)
    with pool.acquire() as conn:
        _ensure_yamuna_objects(conn)
        inserted_gainers, existing_gainers = _merge_rows(conn, GAINERS_TABLE, gainers_rows, include_volume=False)
        inserted_loosers, existing_loosers = _merge_rows(conn, LOOSERS_TABLE, loosers_rows, include_volume=False)
        inserted_volume, existing_volume = _merge_rows(conn, VOLUME_TABLE, volume_rows, include_volume=True)
        conn.commit()

    inserted = {
        'gainers': inserted_gainers,
        'loosers': inserted_loosers,
        'volumeMovers': inserted_volume,
    }
    skipped = {
        'gainers': gainers_skipped + existing_gainers,
        'loosers': loosers_skipped + existing_loosers,
        'volumeMovers': volume_skipped + existing_volume,
    }
    inserted_total = (inserted_gainers or 0) + (inserted_loosers or 0) + (inserted_volume or 0)
    agent_result = None
    if inserted_total > 0:
        try:
            agent_result = start_strategy_agent_execution('yamuna', run_source='yamuna_auto_ingest')
        except Exception as exc:
            _logger.warning('Yamuna auto-ingest agent trigger failed correlationId=%s error=%s', correlation_id, exc)
    skipped_total = sum(int(value or 0) for value in skipped.values())
    if inserted_total > 0 or skipped_total > 0:
        try:
            publish_notification(
                source='yamuna_auto_ingest',
                message=(
                    f"Yamuna auto ingestion completed successfully for {inserted_total} rows."
                    if inserted_total > 0
                    else f"Yamuna auto ingestion completed successfully; existing rows already present for {ltc_date_iso}."
                ),
                metadata={
                    'reason': reason,
                    'ltcDate': ltc_date_iso,
                    'insertedRows': inserted_total,
                    'skippedRows': skipped_total,
                    'inserted': inserted,
                    'skipped': skipped,
                },
            )
        except Exception as exc:
            _logger.warning('Yamuna auto-ingest notification failed correlationId=%s error=%s', correlation_id, exc)

    if gainers_errors or loosers_errors or volume_errors:
        _logger.info('Yamuna auto-ingest validation notes correlationId=%s gainers=%s loosers=%s volume=%s', correlation_id, len(gainers_errors), len(loosers_errors), len(volume_errors))

    result = {
        'status': 'ok',
        'ltc_date': ltc_date_iso,
        'inserted': inserted,
        'skipped': skipped,
        'csv': csv_paths,
        'agent': agent_result,
    }
    _logger.info('Yamuna auto-ingest committed correlationId=%s reason=%s ltc_date=%s inserted=%s skipped=%s', correlation_id, reason, ltc_date_iso, inserted, skipped)
    return result


def start_yamuna_auto_ingest() -> None:
    global _yamuna_auto_ingest_started
    if _yamuna_auto_ingest_started or not YAMUNA_AUTO_INGEST_ENABLED:
        return
    _yamuna_auto_ingest_started = True

    def _loop() -> None:
        startup_delay = max(5, int(os.getenv('YAMUNA_AUTO_INGEST_STARTUP_DELAY_SEC', '30')))
        try:
            time.sleep(startup_delay)
            run_yamuna_auto_ingest_once(reason='startup')
        except Exception:
            _logger.exception('Yamuna startup auto-ingest failed')
        while True:
            try:
                now = datetime.now()
                parts = YAMUNA_AUTO_INGEST_TIME.split(':', 1)
                hour = int(parts[0]) if parts and parts[0].isdigit() else 18
                minute = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 5
                target = datetime(now.year, now.month, now.day, hour, minute)
                if target <= now:
                    target = target + timedelta(days=1)
                sleep_seconds = max(30, int((target - now).total_seconds()))
                time.sleep(sleep_seconds)
                run_yamuna_auto_ingest_once(reason='schedule')
            except Exception:
                _logger.exception('Yamuna auto-ingest scheduler error')
                time.sleep(300)

    threading.Thread(target=_loop, name='yamuna-auto-ingest', daemon=True).start()


@bp.get('/api/yamuna/last-ltc-date')
def api_yamuna_last_ltc_date():
    try:
        return jsonify(_get_yamuna_last_ltc_dates())
    except Exception as exc:
        _logger.exception('Yamuna last-ltc-date failed')
        return jsonify({'status': 'error', 'message': str(exc)}), 500


@bp.post('/api/yamuna/ingest')
def api_yamuna_ingest():
    correlation_id = request.headers.get('X-Correlation-Id') or str(uuid.uuid4())
    payload = request.get_json(silent=True) or {}

    payload_ltc_date = _parse_date_value(payload.get('ltc_date'))
    gainers_rows, gainers_skipped, gainers_errors = _normalize_rows(
        payload.get('gainers'),
        fallback_date=payload_ltc_date,
        include_volume=False,
    )
    loosers_rows, loosers_skipped, loosers_errors = _normalize_rows(
        payload.get('loosers'),
        fallback_date=payload_ltc_date,
        include_volume=False,
    )
    volume_rows, volume_skipped, volume_errors = _normalize_rows(
        payload.get('volumeMovers'),
        fallback_date=payload_ltc_date,
        include_volume=True,
    )

    all_dates = [
        row.get('ltc_date')
        for row in (gainers_rows + loosers_rows + volume_rows)
        if isinstance(row.get('ltc_date'), date)
    ]
    ltc_date = payload_ltc_date or (max(all_dates) if all_dates else date.today())
    ltc_date_iso = _date_to_iso(ltc_date) or date.today().strftime('%Y-%m-%d')

    _logger.info(
        'Yamuna ingest start correlationId=%s ltc_date=%s rows(g/l/v)=%s/%s/%s',
        correlation_id,
        ltc_date_iso,
        len(gainers_rows),
        len(loosers_rows),
        len(volume_rows),
    )

    try:
        csv_paths = _export_csvs(ltc_date, gainers_rows, loosers_rows, volume_rows)
        _logger.info(
            'Yamuna CSV export done correlationId=%s gainers=%s loosers=%s volume=%s',
            correlation_id,
            csv_paths['gainers'],
            csv_paths['loosers'],
            csv_paths['volumeMovers'],
        )
    except Exception as exc:
        _logger.exception('Yamuna CSV export failed correlationId=%s', correlation_id)
        return jsonify({'status': 'error', 'message': f'CSV export failed: {exc}'}), 500

    try:
        with pool.acquire() as conn:
            _ensure_yamuna_objects(conn)
            inserted_gainers, existing_gainers = _merge_rows(conn, GAINERS_TABLE, gainers_rows, include_volume=False)
            inserted_loosers, existing_loosers = _merge_rows(conn, LOOSERS_TABLE, loosers_rows, include_volume=False)
            inserted_volume, existing_volume = _merge_rows(conn, VOLUME_TABLE, volume_rows, include_volume=True)
            conn.commit()
    except Exception as exc:
        _logger.exception('Yamuna ingest DB failed correlationId=%s', correlation_id)
        return jsonify({
            'status': 'error',
            'ltc_date': ltc_date_iso,
            'message': str(exc),
            'csv': csv_paths,
        }), 500

    skipped = {
        'gainers': gainers_skipped + existing_gainers,
        'loosers': loosers_skipped + existing_loosers,
        'volumeMovers': volume_skipped + existing_volume,
    }
    inserted = {
        'gainers': inserted_gainers,
        'loosers': inserted_loosers,
        'volumeMovers': inserted_volume,
    }
    _logger.info(
        'Yamuna ingest committed correlationId=%s ltc_date=%s inserted=%s skipped=%s',
        correlation_id,
        ltc_date_iso,
        inserted,
        skipped,
    )
    if gainers_errors or loosers_errors or volume_errors:
        _logger.info(
            'Yamuna ingest validation notes correlationId=%s gainers=%s loosers=%s volume=%s',
            correlation_id,
            len(gainers_errors),
            len(loosers_errors),
            len(volume_errors),
        )

    agent_result = None
    inserted_total = (inserted_gainers or 0) + (inserted_loosers or 0) + (inserted_volume or 0)
    if inserted_total > 0:
        try:
            agent_result = start_strategy_agent_execution('yamuna', run_source='yamuna_ingest')
        except Exception as exc:
            _logger.warning('Yamuna agent trigger failed correlationId=%s error=%s', correlation_id, exc)

    return jsonify({
        'status': 'ok',
        'ltc_date': ltc_date_iso,
        'inserted': inserted,
        'skipped': skipped,
        'csv': csv_paths,
        'agent': agent_result,
    })


