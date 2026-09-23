
from __future__ import annotations

import csv
import datetime as dt
import json
import logging
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

try:
  from . import nse_mcap_service as mcap
  from . import nse_existing_csv_symbol_service as existing_csv_svc
  from . import nse_data_overview_service as data_overview_svc
except ImportError:  # pragma: no cover
  from services import nse_mcap_service as mcap  # type: ignore
  from services import nse_existing_csv_symbol_service as existing_csv_svc  # type: ignore
  from services import nse_data_overview_service as data_overview_svc  # type: ignore

logger = logging.getLogger(__name__)

_TABLE = (mcap.os.getenv('NSE_DELIVERY_TABLE') or 'CVING_NSE_DELIVERY_HIST').strip()
_LATEST_VIEW = (mcap.os.getenv('NSE_DELIVERY_LATEST_VIEW') or 'VW_CVING_NSE_DELIVERY_LATEST').strip()
_FILE_SOURCE = (mcap.os.getenv('NSE_DELIVERY_SOURCE_NAME') or 'NSE_DELIVERY_FILE').strip().upper()
_CREATED_BY = (mcap.os.getenv('NSE_DELIVERY_CREATED_BY') or 'CVING_NSE_DELIVERY_UI').strip() or 'CVING_NSE_DELIVERY_UI'
_EQ_ONLY_DEFAULT = mcap._EQ_ONLY_DEFAULT
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DOWNLOAD_DIR = Path(
  mcap.os.getenv('DELIVERY_DOWNLOAD_DIR')
  or mcap.os.getenv('NSE_DELIVERY_DOWNLOAD_DIR')
  or (_PROJECT_ROOT / 'batch' / 'nse_delivery_data' / 'downloads')
)
_JOB_TTL_SEC = mcap._JOB_TTL_SEC
_MAX_ROWS = mcap._MAX_ROWS
_RUN_TYPE = 'DELIVERY'
_LOCAL_DELIVERY_CSV_RE = mcap.re.compile(r'(?i)^sec_bhavdata_full_(?P<date>\d{8})\.csv$')

_TABLE_SQL = mcap._safe_ident(_TABLE)
_LATEST_VIEW_SQL = mcap._safe_ident(_LATEST_VIEW)

_SYMBOL_COLUMNS = mcap._SYMBOL_COLUMNS
_SERIES_COLUMNS = mcap._SERIES_COLUMNS
_NAME_COLUMNS = mcap._NAME_COLUMNS
_PREV_CLOSE_COLUMNS = ('PREVCLOSE', 'PREV_CLOSE', 'PREVIOUSCLOSE', 'PREVCLOSEPRICE')
_CLOSE_COLUMNS = ('CLOSEPRICE', 'CLOSE_PRICE', 'CLOSE', 'CLOSEPRICEPAIDUPVALUE')
_TOTAL_QTY_COLUMNS = ('TTLTRDQNTY', 'TOTALTRDQTY', 'TTL_TRD_QNTY', 'TOTTRDQTY')
_TURNOVER_COLUMNS = ('TURNOVERLACS', 'TURNOVER_LACS', 'TURNOVER')
_TRADE_COUNT_COLUMNS = ('NOOFTRADES', 'NO_OF_TRADES', 'TRADES', 'TOTALTRADES')
_DELIVERY_QTY_COLUMNS = ('DELIVQTY', 'DELIV_QTY', 'DELIVERYQTY', 'DELIVERY_QTY')
_DELIVERY_PCT_COLUMNS = ('DELIVPER', 'DELIV_PER', 'DELIVERYPERCENTAGE', 'DELIVERY_PCT', 'DELIVPERCENT')

_RUNTIME_READY = False
_RUNTIME_LOCK = threading.Lock()
_JOBS: Dict[str, Dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()


def _download_dir() -> Path:
  _DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
  return _DOWNLOAD_DIR


def _expected_csv_path(trade_date: dt.date) -> Path:
  return _download_dir() / f'sec_bhavdata_full_{trade_date.strftime("%d%m%Y")}.csv'


def _expected_zip_path(trade_date: dt.date) -> Path:
  return _download_dir() / f'sec_bhavdata_full_{trade_date.strftime("%d%m%Y")}.zip'


def _trade_date_from_delivery_csv(csv_path: Path) -> Optional[dt.date]:
  match = _LOCAL_DELIVERY_CSV_RE.match(csv_path.name or '')
  if not match:
    return None
  try:
    return dt.datetime.strptime(match.group('date'), '%d%m%Y').date()
  except ValueError:
    return None


def _reuse_local_download(trade_date: dt.date, line_logger: Optional[Callable[[str], None]] = None) -> Optional[Path]:
  csv_path = _expected_csv_path(trade_date)
  if csv_path.exists() and csv_path.is_file() and csv_path.stat().st_size > 0:
    if line_logger:
      line_logger(f'[INFO] Reusing local delivery CSV {csv_path}')
    return csv_path
  zip_path = _expected_zip_path(trade_date)
  if zip_path.exists() and zip_path.is_file() and zip_path.stat().st_size > 0:
    if line_logger:
      line_logger(f'[INFO] Reusing local delivery ZIP {zip_path}')
    return _extract_zip(zip_path, trade_date)
  return None


def _candidate_specs(trade_date: dt.date) -> List[Tuple[str, str]]:
  month = trade_date.strftime('%b').upper()
  year = trade_date.strftime('%Y')
  ddmmyyyy = trade_date.strftime('%d%m%Y')
  lower = f'sec_bhavdata_full_{ddmmyyyy}.csv'
  lower_zip = f'sec_bhavdata_full_{ddmmyyyy}.zip'
  lower_csv_zip = f'sec_bhavdata_full_{ddmmyyyy}.csv.zip'
  legacy_archive_base = 'https://archives.nseindia.com'
  return [
    ('products_delivery_csv', f'{mcap._ARCHIVE_BASE}/products/content/{lower}'),
    ('products_delivery_zip', f'{mcap._ARCHIVE_BASE}/products/content/{lower_zip}'),
    ('products_delivery_csv_zip', f'{mcap._ARCHIVE_BASE}/products/content/{lower_csv_zip}'),
    ('legacy_products_delivery_csv', f'{legacy_archive_base}/products/content/{lower}'),
    ('legacy_products_delivery_zip', f'{legacy_archive_base}/products/content/{lower_zip}'),
    ('legacy_products_delivery_csv_zip', f'{legacy_archive_base}/products/content/{lower_csv_zip}'),
    ('historical_delivery_csv', f'{mcap._ARCHIVE_BASE}/content/historical/EQUITIES/{year}/{month}/{lower}'),
    ('historical_delivery_zip', f'{mcap._ARCHIVE_BASE}/content/historical/EQUITIES/{year}/{month}/{lower_zip}'),
    ('historical_delivery_csv_zip', f'{mcap._ARCHIVE_BASE}/content/historical/EQUITIES/{year}/{month}/{lower_csv_zip}'),
  ]


def _discover_urls(client: Any, trade_date: dt.date, line_logger: Optional[Callable[[str], None]] = None) -> List[str]:
  ddmmyyyy = trade_date.strftime('%d%m%Y')
  targets = {
    f'sec_bhavdata_full_{ddmmyyyy}.csv',
    f'sec_bhavdata_full_{ddmmyyyy}.zip',
    f'sec_bhavdata_full_{ddmmyyyy}.csv.zip',
  }
  urls: List[str] = []
  if line_logger:
    line_logger('[INFO] Discovering delivery file URLs from official NSE pages...')
  for page_url in (
    f'{mcap._ARCHIVE_BASE}/content/historical/EQUITIES/{trade_date.strftime("%Y")}/{trade_date.strftime("%b").upper()}/',
    f'{mcap._NSE_BASE}/all-reports',
    f'{mcap._NSE_BASE}/report-detail/eq_security',
  ):
    try:
      html = client.read_text(page_url)
    except Exception as exc:
      logger.warning('NSE delivery discovery page failed url=%s error=%s', page_url, exc)
      continue
    matches = mcap._extract_discovered_urls(page_url, html, targets)
    if matches:
      urls.extend(matches)
      if line_logger:
        line_logger(f'[INFO] Delivery discovery matched {len(matches)} candidate url(s) via {page_url}')
  return list(dict.fromkeys(urls))


def _extract_zip(zip_path: Path, trade_date: dt.date) -> Path:
  out_path = _expected_csv_path(trade_date)
  with zipfile.ZipFile(zip_path, 'r') as archive:
    chosen = None
    for member in archive.namelist():
      lower = member.lower()
      if lower.endswith('.csv') and 'sec_bhavdata_full' in lower:
        chosen = member
        break
    if chosen is None:
      raise RuntimeError(f'Delivery CSV not found inside archive: {zip_path.name}')
    with archive.open(chosen) as source, out_path.open('wb') as target:
      target.write(source.read())
  return out_path

def ensure_runtime(conn=None) -> Dict[str, Any]:
  global _RUNTIME_READY
  owns_conn = conn is None
  if owns_conn:
    conn = mcap.pool.acquire()
  try:
    with _RUNTIME_LOCK:
      if not mcap._table_exists(conn, _TABLE_SQL):
        mcap._exec_ddl(conn, f'''
          CREATE TABLE {_TABLE_SQL} (
            ID NUMBER GENERATED BY DEFAULT ON NULL AS IDENTITY PRIMARY KEY,
            TRADE_DATE DATE NOT NULL,
            SYMBOL VARCHAR2(50) NOT NULL,
            SOURCE_NAME VARCHAR2(50) NOT NULL,
            SERIES VARCHAR2(10),
            SECURITY_NAME VARCHAR2(300),
            PREV_CLOSE NUMBER(24,6),
            CLOSE_PRICE NUMBER(24,6),
            TOTAL_TRADED_QTY NUMBER(24,6),
            TURNOVER_LACS NUMBER(24,6),
            NO_OF_TRADES NUMBER(24,6),
            DELIVERY_QTY NUMBER(24,6),
            DELIVERY_PCT NUMBER(12,6),
            RESPONSE_PAYLOAD CLOB,
            FETCH_STATUS VARCHAR2(30) DEFAULT 'SUCCESS' NOT NULL,
            ERROR_MESSAGE VARCHAR2(2000),
            FETCH_TS TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
            CREATED_BY VARCHAR2(128) DEFAULT USER NOT NULL,
            UPDATED_TS TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
            CONSTRAINT UQ_{mcap._split_ident(_TABLE_SQL)[1][-20:]} UNIQUE (TRADE_DATE, SYMBOL, SOURCE_NAME),
            CONSTRAINT {mcap._ck_name(_TABLE_SQL, 'STATUS')} CHECK (FETCH_STATUS IN ('SUCCESS', 'FAILED', 'PARTIAL', 'SKIPPED', 'PARSE_ERROR')),
            CONSTRAINT {mcap._ck_name(_TABLE_SQL, 'PAYLOAD')} CHECK (RESPONSE_PAYLOAD IS JSON OR RESPONSE_PAYLOAD IS NULL)
          )
        ''')
      for idx_sql in (
        f'CREATE INDEX {mcap._idx_name(_TABLE_SQL, "TRDDATE")} ON {_TABLE_SQL} (TRADE_DATE, FETCH_STATUS)',
        f'CREATE INDEX {mcap._idx_name(_TABLE_SQL, "SYMDATE")} ON {_TABLE_SQL} (SYMBOL, TRADE_DATE DESC)',
      ):
        idx_name = idx_sql.split()[2]
        if not mcap._index_exists(conn, idx_name):
          mcap._exec_ddl(conn, idx_sql)
      if not mcap._view_exists(conn, _LATEST_VIEW_SQL):
        with conn.cursor() as cur:
          cur.execute(f'''
            CREATE OR REPLACE FORCE NONEDITIONABLE VIEW {_LATEST_VIEW_SQL} AS
            SELECT id, trade_date, symbol, source_name, series, security_name,
                   prev_close, close_price, total_traded_qty, turnover_lacs,
                   no_of_trades, delivery_qty, delivery_pct, response_payload,
                   fetch_status, error_message, fetch_ts, created_by, updated_ts
            FROM (
              SELECT t.*, ROW_NUMBER() OVER (
                PARTITION BY t.symbol, t.source_name
                ORDER BY t.trade_date DESC, t.fetch_ts DESC, t.updated_ts DESC
              ) rn
              FROM {_TABLE_SQL} t
            )
            WHERE rn = 1
          ''')
      conn.commit()
      _download_dir()
      _RUNTIME_READY = True
      return {'ok': True, 'table': _TABLE_SQL, 'runsTable': mcap._RUNS_TABLE_SQL, 'view': _LATEST_VIEW_SQL, 'downloadDir': str(_download_dir())}
  finally:
    if owns_conn and conn is not None:
      conn.close()


def download_delivery_csv(trade_date: dt.date, line_logger: Optional[Callable[[str], None]] = None) -> Path:
  ensure_runtime()
  local_path = _reuse_local_download(trade_date, line_logger=line_logger)
  if local_path is not None:
    return local_path
  download_client = mcap._HttpClient(
    warmup=False,
    timeout_sec=mcap._DOWNLOAD_TIMEOUT_SEC,
    retry_count=mcap._DOWNLOAD_RETRY_COUNT,
    min_sleep=mcap._DOWNLOAD_MIN_SLEEP,
    max_sleep=mcap._DOWNLOAD_MAX_SLEEP,
  )
  discovery_client = mcap._HttpClient(
    warmup=False,
    timeout_sec=mcap._DISCOVERY_TIMEOUT_SEC,
    retry_count=mcap._DISCOVERY_RETRY_COUNT,
    min_sleep=mcap._DOWNLOAD_MIN_SLEEP,
    max_sleep=mcap._DOWNLOAD_MAX_SLEEP,
  )
  last_error: Optional[Exception] = None
  attempted: set[str] = set()

  def _download_from_url(url: str, client: Optional[Any] = None) -> Optional[Path]:
    nonlocal last_error
    try:
      if line_logger:
        line_logger(f'[INFO] Downloading {url}')
      payload, headers = (client or download_client).read(url, '*/*')
      ctype = str(headers.get('Content-Type') or headers.get('content-type') or '').lower()
      if url.lower().endswith('.zip') or 'zip' in ctype or payload[:2] == b'PK':
        zip_path = _expected_zip_path(trade_date)
        zip_path.write_bytes(payload)
        return _extract_zip(zip_path, trade_date)
      if url.lower().endswith('.csv') or 'csv' in ctype or (b',' in payload[:200] and b'\n' in payload[:500]):
        csv_path = _expected_csv_path(trade_date)
        csv_path.write_bytes(payload)
        return csv_path
      raise RuntimeError(f'Unexpected response type for {url}')
    except Exception as exc:
      last_error = exc
      logger.warning('NSE delivery download failed url=%s error=%s', url, exc)
      if line_logger:
        line_logger(f'[WARN] Download candidate failed: {url} :: {exc}')
      return None

  for _key, url in _candidate_specs(trade_date):
    attempted.add(url)
    downloaded = _download_from_url(url)
    if downloaded is not None:
      return downloaded
  for url in _discover_urls(discovery_client, trade_date, line_logger=line_logger):
    if url in attempted:
      continue
    attempted.add(url)
    downloaded = _download_from_url(url, client=download_client)
    if downloaded is not None:
      return downloaded
  raise RuntimeError(f'Unable to download NSE delivery CSV for {trade_date.isoformat()}: {last_error}')


def _record(symbol: str, trade_date: dt.date, **kwargs: Any) -> Dict[str, Any]:
  return {
    'id': kwargs.get('id'),
    'trade_date': trade_date,
    'symbol': str(symbol).strip().upper(),
    'source_name': _FILE_SOURCE,
    'series': (kwargs.get('series') or None),
    'security_name': (kwargs.get('security_name') or None),
    'prev_close': mcap._parse_decimal(kwargs.get('prev_close')),
    'close_price': mcap._parse_decimal(kwargs.get('close_price')),
    'total_traded_qty': mcap._parse_decimal(kwargs.get('total_traded_qty')),
    'turnover_lacs': mcap._parse_decimal(kwargs.get('turnover_lacs')),
    'no_of_trades': mcap._parse_decimal(kwargs.get('no_of_trades')),
    'delivery_qty': mcap._parse_decimal(kwargs.get('delivery_qty')),
    'delivery_pct': mcap._parse_decimal(kwargs.get('delivery_pct')),
    'response_payload': kwargs.get('response_payload'),
    'fetch_status': str(kwargs.get('fetch_status') or 'SUCCESS').upper(),
    'error_message': (str(kwargs.get('error_message') or '')[:2000] or None),
    'created_by': kwargs.get('created_by') or _CREATED_BY,
  }


def _merge_sql() -> str:
  return f"""
    SELECT CAST(:trade_date AS DATE) trade_date,
           CAST(:symbol AS VARCHAR2(50)) symbol,
           CAST(:source_name AS VARCHAR2(50)) source_name,
           CAST(:series AS VARCHAR2(10)) series,
           CAST(:security_name AS VARCHAR2(300)) security_name,
           CAST(:prev_close AS NUMBER(24,6)) prev_close,
           CAST(:close_price AS NUMBER(24,6)) close_price,
           CAST(:total_traded_qty AS NUMBER(24,6)) total_traded_qty,
           CAST(:turnover_lacs AS NUMBER(24,6)) turnover_lacs,
           CAST(:no_of_trades AS NUMBER(24,6)) no_of_trades,
           CAST(:delivery_qty AS NUMBER(24,6)) delivery_qty,
           CAST(:delivery_pct AS NUMBER(12,6)) delivery_pct,
           TO_CLOB(:response_payload) response_payload,
           CAST(:fetch_status AS VARCHAR2(30)) fetch_status,
           CAST(:error_message AS VARCHAR2(2000)) error_message,
           CAST(:created_by AS VARCHAR2(128)) created_by
    FROM dual
  """


def _upsert_records(records: List[Dict[str, Any]]) -> Tuple[int, int, int]:
  import oracledb
  if not records:
    return 0, 0, 0
  conn = mcap.pool.acquire()
  success_count = 0
  failure_count = 0
  skipped_count = 0
  update_sql = f"""
    UPDATE {_TABLE_SQL}
       SET series = CASE WHEN :series IS NOT NULL THEN :series ELSE series END,
           security_name = CASE WHEN :security_name IS NOT NULL THEN :security_name ELSE security_name END,
           prev_close = CASE WHEN :prev_close IS NOT NULL THEN :prev_close ELSE prev_close END,
           close_price = CASE WHEN :close_price IS NOT NULL THEN :close_price ELSE close_price END,
           total_traded_qty = CASE WHEN :total_traded_qty IS NOT NULL THEN :total_traded_qty ELSE total_traded_qty END,
           turnover_lacs = CASE WHEN :turnover_lacs IS NOT NULL THEN :turnover_lacs ELSE turnover_lacs END,
           no_of_trades = CASE WHEN :no_of_trades IS NOT NULL THEN :no_of_trades ELSE no_of_trades END,
           delivery_qty = CASE WHEN :delivery_qty IS NOT NULL THEN :delivery_qty ELSE delivery_qty END,
           delivery_pct = CASE WHEN :delivery_pct IS NOT NULL THEN :delivery_pct ELSE delivery_pct END,
           response_payload = CASE WHEN :response_payload IS NOT NULL THEN TO_CLOB(:response_payload) ELSE response_payload END,
           fetch_status = :fetch_status,
           error_message = CASE
             WHEN :fetch_status = 'SUCCESS' THEN NULL
             WHEN :error_message IS NOT NULL THEN :error_message
             ELSE error_message
           END,
           fetch_ts = :trade_date,
           updated_ts = SYSTIMESTAMP,
           created_by = CASE WHEN :created_by IS NOT NULL THEN :created_by ELSE created_by END
     WHERE trade_date = :trade_date
       AND symbol = :symbol
       AND source_name = :source_name
  """
  insert_sql = f"""
    INSERT INTO {_TABLE_SQL} (
      id, trade_date, symbol, source_name, series, security_name, prev_close, close_price,
      total_traded_qty, turnover_lacs, no_of_trades, delivery_qty, delivery_pct,
      response_payload, fetch_status, error_message, fetch_ts, created_by, updated_ts
    ) VALUES (
      :id, :trade_date, :symbol, :source_name, :series, :security_name, :prev_close, :close_price,
      :total_traded_qty, :turnover_lacs, :no_of_trades, :delivery_qty, :delivery_pct,
      TO_CLOB(:response_payload), :fetch_status, :error_message, :trade_date, :created_by, SYSTIMESTAMP
    )
  """
  try:
    ensure_runtime(conn)
    explicit_id_required = not mcap._table_supports_implicit_id(conn, _TABLE_SQL)
    if explicit_id_required:
      mcap._assign_missing_record_ids(conn, _TABLE_SQL, records, force=True)
    with conn.cursor() as cur:
      for record in records:
        cur.execute('SAVEPOINT NSE_DELIVERY_UPSERT_SP')
        update_record = {key: value for key, value in record.items() if key != 'id'}
        try:
          cur.execute(update_sql, update_record)
          if not cur.rowcount:
            cur.execute(insert_sql, record)
          success_count += 1
        except Exception as exc:
          cur.execute('ROLLBACK TO SAVEPOINT NSE_DELIVERY_UPSERT_SP')
          try:
            if (not explicit_id_required) and 'ORA-00001' in str(exc):
              cur.execute(update_sql, update_record)
              if cur.rowcount:
                success_count += 1
                continue
          except Exception:
            cur.execute('ROLLBACK TO SAVEPOINT NSE_DELIVERY_UPSERT_SP')
          
          is_dup = False
          if isinstance(exc, oracledb.DatabaseError):
            err_obj = exc.args[0] if exc.args else None
            if err_obj and hasattr(err_obj, 'code') and err_obj.code == 1:
              is_dup = True
            elif err_obj and hasattr(err_obj, 'message') and 'ORA-00001' in err_obj.message:
              is_dup = True
          if not is_dup and 'ORA-00001' in str(exc):
            is_dup = True

          if is_dup:
            skipped_count += 1
          else:
            failure_count += 1
            logger.exception(
              'NSE delivery upsert failed symbol=%s source=%s error=%s',
              record.get('symbol'),
              record.get('source_name'),
              exc,
            )
      conn.commit()
  finally:
    conn.close()
  return success_count, failure_count, skipped_count


def _existing_file_symbols(trade_date: dt.date, source_name: str = _FILE_SOURCE) -> set[str]:
  conn = mcap.pool.acquire()
  if conn is None:
    return set()
  try:
    ensure_runtime(conn)
    with conn.cursor() as cur:
      cur.execute(
        f'''SELECT symbol
              FROM {_TABLE_SQL}
             WHERE trade_date = :trade_date
               AND source_name = :source_name''',
        {'trade_date': trade_date, 'source_name': str(source_name or _FILE_SOURCE).strip().upper()},
      )
      return {str(row[0]).strip().upper() for row in (cur.fetchall() or []) if row and row[0]}
  finally:
    try:
      conn.close()
    except Exception:
      pass


def _existing_file_row_count(trade_date: dt.date) -> int:
  conn = mcap.pool.acquire()
  if conn is None:
    return 0
  try:
    ensure_runtime(conn)
    with conn.cursor() as cur:
      cur.execute(
        f'''SELECT COUNT(*)
              FROM {_TABLE_SQL}
             WHERE trade_date = :trade_date
               AND source_name = :source_name''',
        {'trade_date': trade_date, 'source_name': _FILE_SOURCE},
      )
      row = cur.fetchone()
      return int(row[0] or 0) if row else 0
  finally:
    try:
      conn.close()
    except Exception:
      pass


def _safe_existing_file_row_count(trade_date: dt.date) -> int:
  try:
    return _existing_file_row_count(trade_date)
  except Exception as exc:
    logger.warning('NSE delivery row-count verification failed trade_date=%s error=%s', mcap._iso_date(trade_date), exc)
    return 0


def _delivery_db_verification(trade_date: dt.date, rows_before: int, rows_after: int, load_summary: Dict[str, Any]) -> Dict[str, Any]:
  failed_rows = int(load_summary.get('failureCount') or 0)
  inserted_rows = int(load_summary.get('loadedCount') or 0)
  skipped_rows = (
    int(load_summary.get('skippedCount') or 0)
    + int(load_summary.get('universeSkippedCount') or 0)
    + int(load_summary.get('alreadyLoadedCount') or 0)
  )
  return {
    'table': _TABLE_SQL,
    'tradingDate': mcap._iso_date(trade_date),
    'rowCountBefore': int(rows_before or 0),
    'rowCountAfter': int(rows_after or 0),
    'insertedRows': inserted_rows,
    'updatedRows': 0,
    'skippedRows': skipped_rows,
    'failedRows': failed_rows,
    'commitConfirmed': rows_after >= rows_before and failed_rows == 0,
  }


def _result_already_loaded(result: Dict[str, Any]) -> bool:
  inspection = result.get('inspection') or {}
  load = result.get('load') or {}
  return bool(inspection.get('alreadyLoaded') or load.get('alreadyLoaded'))
def _coerce_allowed_symbols(allowed_symbols: Optional[Sequence[str]]) -> Optional[set[str]]:
  if allowed_symbols is None:
    return None
  cleaned = {str(item or '').strip().upper() for item in allowed_symbols if str(item or '').strip()}
  return cleaned or None


def inspect_delivery_csv(csv_path: Path, trade_date: dt.date, eq_only: bool = _EQ_ONLY_DEFAULT, allowed_symbols: Optional[Sequence[str]] = None) -> Dict[str, Any]:
  universe_symbols = _coerce_allowed_symbols(allowed_symbols)
  input_rows = matched_rows = parse_error_rows = skipped_rows = blank_rows = series_skipped_rows = universe_skipped_rows = 0
  matched_symbols: List[str] = []
  fieldnames: List[str] = []
  with csv_path.open('r', encoding='utf-8-sig', newline='') as handle:
    reader = csv.DictReader(handle)
    if not reader.fieldnames:
      raise ValueError('CSV file does not contain a header row.')
    fieldnames = list(reader.fieldnames or [])
    column_map = {mcap._normalize_header(field): field for field in reader.fieldnames if field}
    symbol_col = mcap._resolve_header(column_map, _SYMBOL_COLUMNS)
    if not symbol_col:
      raise ValueError(f'Unable to identify delivery symbol column. Found headers: {", ".join(reader.fieldnames)}')
    series_col = mcap._resolve_header(column_map, _SERIES_COLUMNS)
    deliv_qty_col = mcap._resolve_header(column_map, _DELIVERY_QTY_COLUMNS)
    deliv_pct_col = mcap._resolve_header(column_map, _DELIVERY_PCT_COLUMNS)
    if not deliv_qty_col and not deliv_pct_col:
      raise ValueError(f'Unable to identify delivery columns. Found headers: {", ".join(reader.fieldnames)}')
    seen: set[str] = set()
    for row in reader:
      if not any(str(value or '').strip() for value in row.values()):
        skipped_rows += 1
        blank_rows += 1
        continue
      input_rows += 1
      symbol = str(row.get(symbol_col) or '').strip().upper()
      if not symbol:
        skipped_rows += 1
        continue
      series = str(row.get(series_col) or '').strip().upper() if series_col else None
      if eq_only and series and series != 'EQ':
        skipped_rows += 1
        series_skipped_rows += 1
        continue
      if universe_symbols and symbol not in universe_symbols:
        skipped_rows += 1
        universe_skipped_rows += 1
        continue
      deliv_qty = mcap._parse_decimal(row.get(deliv_qty_col)) if deliv_qty_col else None
      deliv_pct = mcap._parse_decimal(row.get(deliv_pct_col)) if deliv_pct_col else None
      if deliv_qty is None and deliv_pct is None:
        parse_error_rows += 1
        continue
      matched_rows += 1
      if symbol not in seen:
        seen.add(symbol)
        matched_symbols.append(symbol)
  return {
    'ok': True,
    'tradeDate': trade_date.strftime('%Y-%m-%d'),
    'csvPath': str(csv_path),
    'headers': fieldnames,
    'eqOnly': bool(eq_only),
    'nifty500Only': bool(universe_symbols is not None),
    'nifty500Path': mcap._nifty500_source_path(),
    'inputRows': input_rows,
    'matchedRows': matched_rows,
    'matchedSymbolsCount': len(matched_symbols),
    'matchedSymbols': matched_symbols,
    'parseErrorRows': parse_error_rows,
    'skippedRows': skipped_rows,
    'blankRows': blank_rows,
    'seriesSkippedRows': series_skipped_rows,
    'universeSkippedRows': universe_skipped_rows,
  }


def load_delivery_csv(
  csv_path: Path,
  trade_date: dt.date,
  eq_only: bool = _EQ_ONLY_DEFAULT,
  allowed_symbols: Optional[Sequence[str]] = None,
  line_logger: Optional[Callable[[str], None]] = None,
  skip_if_existing: bool = False,
  existing_symbols: Optional[set[str]] = None,
) -> Dict[str, Any]:
  ensure_runtime()
  existing_symbol_set = (
    {str(item or '').strip().upper() for item in (existing_symbols or set()) if str(item or '').strip()}
    if skip_if_existing and existing_symbols is not None
    else (_existing_file_symbols(trade_date) if skip_if_existing else set())
  )
  if existing_symbol_set and line_logger and skip_if_existing:
    line_logger(
      f'[INFO] Existing delivery symbols detected for {trade_date.strftime("%d-%m-%Y")} '
      f'count={len(existing_symbol_set)}; duplicate rows will be skipped.'
    )
  universe_symbols = _coerce_allowed_symbols(allowed_symbols)
  input_rows = loaded = failures = skipped = universe_skipped = duplicate_rows = already_loaded_count = 0
  matched_rows = 0
  matched_symbol_seen: set[str] = set()
  matched_symbols: List[str] = []
  seen_symbols: set[str] = set()
  batch: List[Dict[str, Any]] = []
  errors: List[Dict[str, Any]] = []
  with csv_path.open('r', encoding='utf-8-sig', newline='') as handle:
    reader = csv.DictReader(handle)
    if not reader.fieldnames:
      raise ValueError('CSV file does not contain a header row.')
    column_map = {mcap._normalize_header(field): field for field in reader.fieldnames if field}
    symbol_col = mcap._resolve_header(column_map, _SYMBOL_COLUMNS)
    if not symbol_col:
      raise ValueError(f'Unable to identify delivery symbol column. Found headers: {", ".join(reader.fieldnames)}')
    series_col = mcap._resolve_header(column_map, _SERIES_COLUMNS)
    name_col = mcap._resolve_header(column_map, _NAME_COLUMNS)
    prev_close_col = mcap._resolve_header(column_map, _PREV_CLOSE_COLUMNS)
    close_col = mcap._resolve_header(column_map, _CLOSE_COLUMNS)
    total_qty_col = mcap._resolve_header(column_map, _TOTAL_QTY_COLUMNS)
    turnover_col = mcap._resolve_header(column_map, _TURNOVER_COLUMNS)
    trade_count_col = mcap._resolve_header(column_map, _TRADE_COUNT_COLUMNS)
    deliv_qty_col = mcap._resolve_header(column_map, _DELIVERY_QTY_COLUMNS)
    deliv_pct_col = mcap._resolve_header(column_map, _DELIVERY_PCT_COLUMNS)
    if not deliv_qty_col and not deliv_pct_col:
      raise ValueError(f'Unable to identify delivery columns. Found headers: {", ".join(reader.fieldnames)}')
    for line_number, row in enumerate(reader, start=2):
      if not any(str(value or '').strip() for value in row.values()):
        skipped += 1
        continue
      input_rows += 1
      symbol = str(row.get(symbol_col) or '').strip().upper()
      if not symbol:
        skipped += 1
        continue
      series = str(row.get(series_col) or '').strip().upper() if series_col else None
      if eq_only and series and series != 'EQ':
        skipped += 1
        continue
      if universe_symbols and symbol not in universe_symbols:
        skipped += 1
        universe_skipped += 1
        continue
      if symbol not in matched_symbol_seen:
        matched_symbol_seen.add(symbol)
        matched_symbols.append(symbol)
      if skip_if_existing and symbol in seen_symbols:
        duplicate_rows += 1
        continue
      if skip_if_existing:
        seen_symbols.add(symbol)
      if skip_if_existing and symbol in existing_symbol_set:
        duplicate_rows += 1
        already_loaded_count += 1
        continue
      deliv_qty = mcap._parse_decimal(row.get(deliv_qty_col)) if deliv_qty_col else None
      deliv_pct = mcap._parse_decimal(row.get(deliv_pct_col)) if deliv_pct_col else None
      if deliv_qty is None and deliv_pct is None:
        failures += 1
        payload = json.dumps(row, default=mcap._json_default, ensure_ascii=True)
        errors.append(_record(symbol, trade_date, series=series, security_name=str(row.get(name_col) or '').strip() if name_col else None, fetch_status='PARSE_ERROR', error_message=f'Unable to parse delivery values from line {line_number}', response_payload=payload))
        if len(errors) >= 60:
          _upsert_records(errors)
          errors.clear()
        continue
      matched_rows += 1
      payload = json.dumps(row, default=mcap._json_default, ensure_ascii=True)
      record = _record(symbol, trade_date, series=series, security_name=str(row.get(name_col) or '').strip() if name_col else None, prev_close=row.get(prev_close_col) if prev_close_col else None, close_price=row.get(close_col) if close_col else None, total_traded_qty=row.get(total_qty_col) if total_qty_col else None, turnover_lacs=row.get(turnover_col) if turnover_col else None, no_of_trades=row.get(trade_count_col) if trade_count_col else None, delivery_qty=deliv_qty, delivery_pct=deliv_pct, response_payload=payload)
      batch.append(record)
      if len(batch) >= 100:
        res = _upsert_records(batch)
        ok_count, bad_count = res[0], res[1]
        skip_count = res[2] if len(res) > 2 else 0
        loaded += ok_count
        failures += bad_count
        skipped += skip_count
        duplicate_rows += skip_count
        batch.clear()
      if len(errors) >= 60:
        _upsert_records(errors)
        errors.clear()
  if batch:
    res = _upsert_records(batch)
    ok_count, bad_count = res[0], res[1]
    skip_count = res[2] if len(res) > 2 else 0
    loaded += ok_count
    failures += bad_count
    skipped += skip_count
    duplicate_rows += skip_count
  if errors:
    _upsert_records(errors)
  if line_logger:
    line_logger(
      f'[INFO] Delivery CSV load finished rows={input_rows} loaded={loaded} failures={failures} '
      f'skipped={skipped} universeSkipped={universe_skipped} duplicates={duplicate_rows} '
      f'alreadyLoaded={already_loaded_count}'
    )
  already_loaded = bool(existing_symbol_set and already_loaded_count > 0 and loaded == 0 and failures == 0 and duplicate_rows > 0)
  return {
    'inputRows': input_rows,
    'matchedRows': matched_rows,
    'matchedSymbolsCount': len(matched_symbols),
    'matchedSymbols': matched_symbols,
    'loadedCount': loaded,
    'failureCount': failures,
    'skippedCount': skipped,
    'universeSkippedCount': universe_skipped,
    'duplicateCount': duplicate_rows,
    'alreadyLoaded': already_loaded,
    'alreadyLoadedCount': already_loaded_count,
  }


def _parse_runtime_payload(payload: Dict[str, Any], line_logger: Optional[Callable[[str], None]] = None) -> Tuple[List[dt.date], bool, Optional[set[str]]]:
  trade_dates = mcap._parse_trade_dates(
    payload.get('tradeDate') or payload.get('trade_date'),
    payload.get('startDate') or payload.get('start_date'),
    payload.get('endDate') or payload.get('end_date'),
    range_value=payload.get('range') or payload.get('dateRange') or payload.get('date_range'),
    allow_override=mcap._allow_market_date_override(payload),
  )
  eq_only = mcap._coerce_bool(payload.get('eqOnly'), _EQ_ONLY_DEFAULT)
  allowed_symbols = mcap._runtime_filter_symbols()
  if line_logger and allowed_symbols is not None:
    line_logger(f'[INFO] Filtering delivery data against NIFTY500 universe count={len(allowed_symbols)} path={mcap._nifty500_source_path()}')
  if line_logger and len(trade_dates) > 1:
    line_logger(f'[INFO] Processing delivery trade date range {mcap._trade_date_label(trade_dates)} businessDates={len(trade_dates)}')
  return trade_dates, eq_only, allowed_symbols


def _is_unavailable_trade_date_error(exc: Exception) -> bool:
  text = str(exc or '').strip().lower()
  return 'unable to download nse delivery csv for' in text



def _unavailable_trade_date_result(trade_date: dt.date, exc: Exception, *, include_load: bool = False) -> Dict[str, Any]:
  message = f'No NSE delivery CSV available for {mcap._display_date(trade_date)}. Skipping likely holiday / non-trading date.'
  result: Dict[str, Any] = {
    'ok': True,
    'message': message,
    'tradeDate': mcap._iso_date(trade_date),
    'downloadPath': None,
    'inspection': {'alreadyLoaded': False, 'alreadyLoadedCount': 0},
    'skippedUnavailable': True,
    'skipCategory': 'HOLIDAY_OR_UNAVAILABLE',
    'skipReason': str(exc),
  }
  if include_load:
    result['load'] = {
      'inputRows': 0,
      'loadedCount': 0,
      'failureCount': 0,
      'skippedCount': 0,
      'universeSkippedCount': 0,
      'alreadyLoaded': False,
      'alreadyLoadedCount': 0,
    }
  return result



def _result_unavailable(result: Dict[str, Any]) -> bool:
  return bool(result.get('skippedUnavailable'))



def _run_range_stage(trade_dates: Sequence[dt.date], runner: Callable[[dt.date], Dict[str, Any]], *, line_logger: Optional[Callable[[str], None]] = None, include_load: bool = False, stage_label: Optional[str] = None) -> List[Dict[str, Any]]:
  results: List[Dict[str, Any]] = []
  for trade_date in trade_dates:
    if line_logger and stage_label:
      line_logger(f'[INFO] {stage_label} tradeDate={mcap._iso_date(trade_date)}')
    try:
      results.append(runner(trade_date))
    except Exception as exc:
      if not _is_unavailable_trade_date_error(exc):
        raise
      if line_logger:
        line_logger(f'[WARN] No NSE delivery CSV available for tradeDate={mcap._iso_date(trade_date)}; skipping likely holiday / unavailable date. {exc}')
      results.append(_unavailable_trade_date_result(trade_date, exc, include_load=include_load))
  return results



def _aggregate_inspection(results: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
  items = [result.get('inspection') or {} for result in results]
  matched_symbols = sorted({str(symbol).upper() for item in items for symbol in (item.get('matchedSymbols') or []) if str(symbol).strip()})
  all_already_loaded = bool(items) and all(bool(item.get('alreadyLoaded')) for item in items)
  return {
    'headers': next((list(item.get('headers') or []) for item in items if item.get('headers')), []),
    'tradeDateCount': len(results),
    'inputRows': sum(int(item.get('inputRows') or 0) for item in items),
    'matchedRows': sum(int(item.get('matchedRows') or 0) for item in items),
    'matchedSymbolsCount': len(matched_symbols),
    'matchedSymbols': matched_symbols,
    'parseErrorRows': sum(int(item.get('parseErrorRows') or 0) for item in items),
    'skippedRows': sum(int(item.get('skippedRows') or 0) for item in items),
    'blankRows': sum(int(item.get('blankRows') or 0) for item in items),
    'seriesSkippedRows': sum(int(item.get('seriesSkippedRows') or 0) for item in items),
    'universeSkippedRows': sum(int(item.get('universeSkippedRows') or 0) for item in items),
    'eqOnly': next((item.get('eqOnly') for item in items if 'eqOnly' in item), _EQ_ONLY_DEFAULT),
    'nifty500Only': any(bool(item.get('nifty500Only')) for item in items),
    'nifty500Path': next((item.get('nifty500Path') for item in items if item.get('nifty500Path')), None),
    'alreadyLoaded': all_already_loaded,
    'alreadyLoadedCount': sum(int(item.get('alreadyLoadedCount') or 0) for item in items),
  }



def _aggregate_load(results: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
  items = [result.get('load') or {} for result in results if result.get('load') is not None]
  all_already_loaded = bool(items) and all(bool(item.get('alreadyLoaded')) for item in items)
  return {
    'inputRows': sum(int(item.get('inputRows') or 0) for item in items),
    'loadedCount': sum(int(item.get('loadedCount') or 0) for item in items),
    'failureCount': sum(int(item.get('failureCount') or 0) for item in items),
    'skippedCount': sum(int(item.get('skippedCount') or 0) for item in items),
    'universeSkippedCount': sum(int(item.get('universeSkippedCount') or 0) for item in items),
    'alreadyLoaded': all_already_loaded,
    'alreadyLoadedCount': sum(int(item.get('alreadyLoadedCount') or 0) for item in items),
  }



def _aggregate_date_results(results: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
  return [
    {
      'tradeDate': result.get('tradeDate'),
      'message': result.get('message'),
      'downloadPath': result.get('downloadPath'),
      'alreadyLoaded': _result_already_loaded(result),
      'skippedUnavailable': _result_unavailable(result),
      'skipReason': result.get('skipReason'),
      'skipCategory': result.get('skipCategory'),
    }
    for result in results
  ]



def _aggregate_stage_response(trade_dates: Sequence[dt.date], results: Sequence[Dict[str, Any]], message: str, *, include_load: bool = False, include_summary: bool = False) -> Dict[str, Any]:
  response: Dict[str, Any] = {'ok': all(bool(result.get('ok', True)) for result in results), 'message': message}
  response.update(mcap._date_context(trade_dates))
  download_paths = [str(result.get('downloadPath')) for result in results if result.get('downloadPath')]
  unavailable_dates = [
    {
      'tradeDate': result.get('tradeDate'),
      'displayDate': mcap._display_date(mcap._parse_date(result.get('tradeDate'), 'tradeDate')) if result.get('tradeDate') else None,
      'reason': result.get('skipReason') or result.get('message'),
      'category': result.get('skipCategory') or 'HOLIDAY_OR_UNAVAILABLE',
    }
    for result in results if _result_unavailable(result)
  ]
  response['downloadPath'] = download_paths[-1] if download_paths else None
  if len(download_paths) > 1:
    response['downloadPaths'] = download_paths
  response['processedDateCount'] = sum(1 for result in results if not _result_already_loaded(result) and not _result_unavailable(result))
  response['skippedDateCount'] = sum(1 for result in results if _result_already_loaded(result) or _result_unavailable(result))
  response['skippedUnavailableDateCount'] = len(unavailable_dates)
  response['skippedUnavailableDates'] = unavailable_dates
  response['skippedHolidayDates'] = unavailable_dates
  response['dateResults'] = _aggregate_date_results(results)
  response['inspection'] = _aggregate_inspection(results)
  if include_load:
    response['load'] = _aggregate_load(results)
  if include_summary:
    response['summary'] = get_dashboard(limit=None, start_date_text=mcap._iso_date(trade_dates[0]), end_date_text=mcap._iso_date(trade_dates[-1])).get('summary', {})
  return response



def _stage_message(base_message: str, trade_dates: Sequence[dt.date], results: Sequence[Dict[str, Any]]) -> str:
  label = mcap._trade_date_label(trade_dates)
  already_loaded = [result for result in results if _result_already_loaded(result)]
  unavailable = [result for result in results if _result_unavailable(result)]
  if results and len(already_loaded) == len(results):
    return mcap._duplicate_trade_date_message(trade_dates[-1]) if len(trade_dates) == 1 else f'Already data inserted for {label}.'
  if results and len(unavailable) == len(results):
    skipped_text = ', '.join(mcap._display_date(mcap._parse_date(result.get('tradeDate'), 'tradeDate')) for result in unavailable if result.get('tradeDate'))
    return f'No NSE delivery CSV files available for {label}. Skipped likely holiday / unavailable trade date(s): {skipped_text}.'
  suffix_parts: List[str] = []
  if already_loaded:
    suffix_parts.append(f'Skipped {len(already_loaded)} already-loaded trade date(s).')
  if unavailable:
    skipped_text = ', '.join(mcap._display_date(mcap._parse_date(result.get('tradeDate'), 'tradeDate')) for result in unavailable if result.get('tradeDate'))
    suffix_parts.append(f'Skipped {len(unavailable)} holiday / unavailable trade date(s): {skipped_text}.')
  suffix = f" {' '.join(suffix_parts)}" if suffix_parts else ''
  return f'{base_message} for {label}.{suffix}'


def _status_is_failure(status: str) -> bool:
  return status in {'FAILED', 'CANCELLED', 'TIMED_OUT'}


def _pipeline_status_message(status: str, payload: Dict[str, Any]) -> str:
  existing = str(payload.get('message') or '').strip()
  if existing:
    return existing
  if status == 'SUCCESS':
    return 'Delivery data processed successfully.'
  if status == 'PARTIAL':
    return 'Delivery data processed with partial results.'
  if status in {'NO_ACTION', 'ALREADY_EXISTS', 'SKIPPED'}:
    return 'Delivery data already up to date.'
  if status == 'TIMED_OUT':
    return 'Delivery data process timed out.'
  if status == 'CANCELLED':
    return 'Delivery data process cancelled.'
  return 'Delivery data process failed.'


def _enrich_pipeline_response(result: Dict[str, Any], *, durations: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
  payload = dict(result or {})
  status = mcap._status_token(payload.get('status')) or mcap._final_status_from_result(payload)
  has_pipeline_counts = any(
    payload.get(key) is not None
    for key in ('rowsInserted', 'rowsSkipped', 'rowsFailed', 'totalRowsProcessed')
  ) or isinstance(payload.get('load'), dict) or isinstance(payload.get('inspection'), dict) or isinstance(payload.get('counts'), dict)
  if status in {'NO_ACTION', 'ALREADY_EXISTS'} and payload.get('ok') and not has_pipeline_counts:
    status = 'SUCCESS'
  if not status:
    status = 'FAILED' if not payload.get('ok') else 'SUCCESS'
  payload['status'] = status
  payload['done'] = True
  payload['ok'] = not _status_is_failure(status)
  counts = mcap._derive_job_counts({'result': payload})
  load = payload.get('load') if isinstance(payload.get('load'), dict) else {}
  inspection = payload.get('inspection') if isinstance(payload.get('inspection'), dict) else {}
  rows_inserted = int(counts.get('insertedRows') or load.get('loadedCount') or 0)
  rows_failed = int(counts.get('failedRows') or load.get('failureCount') or 0)
  rows_skipped = int(counts.get('skippedRows') or load.get('skippedCount') or 0) + int(counts.get('duplicateRows') or load.get('duplicateCount') or 0)
  already_loaded_count = int(load.get('alreadyLoadedCount') or inspection.get('alreadyLoadedCount') or 0)
  if rows_inserted <= 0 and already_loaded_count > rows_skipped:
    rows_skipped = already_loaded_count
  total_rows = int(counts.get('expectedRows') or load.get('inputRows') or inspection.get('inputRows') or (rows_inserted + rows_skipped + rows_failed))
  failure = _status_is_failure(status)
  payload['downloadStatus'] = 'COMPLETED'
  payload['extractValidateStatus'] = 'COMPLETED'
  payload['insertProcessStatus'] = 'FAILED' if failure else 'COMPLETED'
  payload['successStatus'] = 'FAILED' if failure else 'COMPLETED'
  payload['rowsInserted'] = rows_inserted
  payload['rowsSkipped'] = rows_skipped
  payload['rowsFailed'] = rows_failed
  payload['totalRowsProcessed'] = max(0, total_rows)
  payload['latestTradingDate'] = str(payload.get('tradeDate') or payload.get('endDate') or '').strip()
  payload['updatedTime'] = dt.datetime.now().strftime('%I:%M %p')
  payload['message'] = _pipeline_status_message(status, payload)
  stage_durations = durations if isinstance(durations, dict) else {}
  payload['duration'] = {
    'downloadSeconds': round(float(stage_durations.get('downloadSeconds') or 0.0), 3),
    'extractValidateSeconds': round(float(stage_durations.get('extractValidateSeconds') or 0.0), 3),
    'insertProcessSeconds': round(float(stage_durations.get('insertProcessSeconds') or 0.0), 3),
    'successSeconds': round(float(stage_durations.get('successSeconds') or 0.0), 3),
  }
  return payload



def init_runtime_api() -> Dict[str, Any]:
  return ensure_runtime()



def _download_api_single(trade_date: dt.date, eq_only: bool, allowed_symbols: Optional[set[str]], line_logger: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
  existing_count = _existing_file_row_count(trade_date)
  if existing_count > 0:
    message = mcap._duplicate_trade_date_message(trade_date).strip()
    return {
      'ok': True,
      'message': message,
      'tradeDate': mcap._iso_date(trade_date),
      'downloadPath': None,
      'inspection': {'alreadyLoaded': True, 'alreadyLoadedCount': existing_count},
    }
  csv_path = download_delivery_csv(trade_date, line_logger=line_logger)
  inspection = inspect_delivery_csv(csv_path, trade_date, eq_only=eq_only, allowed_symbols=allowed_symbols)
  return {
    'ok': True,
    'message': 'NSE delivery file downloaded and extracted.',
    'tradeDate': mcap._iso_date(trade_date),
    'downloadPath': str(csv_path),
    'inspection': inspection,
  }



def download_api(payload: Dict[str, Any]) -> Dict[str, Any]:
  trade_dates, eq_only, allowed_symbols = _parse_runtime_payload(payload)
  if len(trade_dates) == 1:
    return mcap._apply_run_contract_fields(_download_api_single(trade_dates[0], eq_only, allowed_symbols), page='DELIVERY', mode='MANUAL', stage='download')
  results = _run_range_stage(
    trade_dates,
    lambda trade_date: _download_api_single(trade_date, eq_only, allowed_symbols),
    include_load=False,
    stage_label='Downloading delivery CSV',
  )
  return mcap._apply_run_contract_fields(_aggregate_stage_response(trade_dates, results, _stage_message('NSE delivery files downloaded and extracted', trade_dates, results)), page='DELIVERY', mode='MANUAL', stage='download')



def _validate_api_single(trade_date: dt.date, eq_only: bool, allowed_symbols: Optional[set[str]], line_logger: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
  existing_count = _existing_file_row_count(trade_date)
  if existing_count > 0:
    message = mcap._duplicate_trade_date_message(trade_date).strip()
    return {
      'ok': True,
      'message': message,
      'tradeDate': mcap._iso_date(trade_date),
      'downloadPath': None,
      'inspection': {'alreadyLoaded': True, 'alreadyLoadedCount': existing_count},
    }
  csv_path = download_delivery_csv(trade_date, line_logger=line_logger)
  inspection = inspect_delivery_csv(csv_path, trade_date, eq_only=eq_only, allowed_symbols=allowed_symbols)
  return {
    'ok': True,
    'message': 'NSE delivery CSV validated.',
    'tradeDate': mcap._iso_date(trade_date),
    'downloadPath': str(csv_path),
    'inspection': inspection,
  }



def validate_api(payload: Dict[str, Any]) -> Dict[str, Any]:
  trade_dates, eq_only, allowed_symbols = _parse_runtime_payload(payload)
  if len(trade_dates) == 1:
    return mcap._apply_run_contract_fields(_validate_api_single(trade_dates[0], eq_only, allowed_symbols), page='DELIVERY', mode='MANUAL', stage='validate')
  results = _run_range_stage(
    trade_dates,
    lambda trade_date: _validate_api_single(trade_date, eq_only, allowed_symbols),
    include_load=False,
    stage_label='Validating delivery CSV',
  )
  return mcap._apply_run_contract_fields(_aggregate_stage_response(trade_dates, results, _stage_message('NSE delivery CSV validation completed', trade_dates, results)), page='DELIVERY', mode='MANUAL', stage='validate')



def _process_api_single(trade_date: dt.date, eq_only: bool, allowed_symbols: Optional[set[str]], line_logger: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
  existing_count = _existing_file_row_count(trade_date)
  if existing_count > 0:
    message = mcap._duplicate_trade_date_message(trade_date).strip()
    if line_logger:
      line_logger(f'[INFO] {message} existingRows={existing_count}')
    load_summary = {
      'inputRows': 0,
      'loadedCount': 0,
      'failureCount': 0,
      'skippedCount': 0,
      'universeSkippedCount': 0,
      'alreadyLoaded': True,
      'alreadyLoadedCount': existing_count,
    }
    return {
      'ok': True,
      'status': 'ALREADY_EXISTS',
      'done': True,
      'message': message,
      'tradeDate': mcap._iso_date(trade_date),
      'downloadPath': None,
      'inspection': {'alreadyLoaded': True, 'alreadyLoadedCount': existing_count},
      'load': load_summary,
      'dbVerification': _delivery_db_verification(trade_date, existing_count, existing_count, load_summary),
    }
  rows_before = int(existing_count or 0)
  if line_logger:
    line_logger(mcap._flow_marker('download', f'Downloading NSE delivery CSV for {mcap._iso_date(trade_date)}.'))
  csv_path = download_delivery_csv(trade_date, line_logger=line_logger)
  if line_logger:
    line_logger(mcap._flow_marker('validate', f'Validating NSE delivery CSV for {mcap._iso_date(trade_date)}.'))
  inspection = inspect_delivery_csv(csv_path, trade_date, eq_only=eq_only, allowed_symbols=allowed_symbols)
  if line_logger:
    line_logger(mcap._flow_marker('process', f'Inserting NSE delivery rows into Oracle for {mcap._iso_date(trade_date)}.'))
  load_summary = load_delivery_csv(csv_path, trade_date, eq_only=eq_only, allowed_symbols=allowed_symbols, line_logger=line_logger)
  rows_after = _safe_existing_file_row_count(trade_date)
  if mcap._load_summary_failed(load_summary, inspection):
    return {
      'ok': False,
      'status': 'FAILED',
      'done': True,
      'message': 'NSE delivery CSV insert failed. No rows were written to Oracle.',
      'tradeDate': mcap._iso_date(trade_date),
      'downloadPath': str(csv_path),
      'inspection': inspection,
      'load': load_summary,
      'summary': {},
      'dbVerification': _delivery_db_verification(trade_date, rows_before, rows_after, load_summary),
    }
  return {
    'ok': True,
    'status': mcap._final_status_from_result({'inspection': inspection, 'load': load_summary}),
    'done': True,
    'message': 'NSE delivery CSV inserted into Oracle.',
    'tradeDate': mcap._iso_date(trade_date),
    'downloadPath': str(csv_path),
    'inspection': inspection,
    'load': load_summary,
    'summary': _get_dashboard_single(mcap._iso_date(trade_date)).get('summary', {}),
    'dbVerification': _delivery_db_verification(trade_date, rows_before, rows_after, load_summary),
  }



def process_api(payload: Dict[str, Any], line_logger: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
  trade_dates, eq_only, allowed_symbols = _parse_runtime_payload(payload, line_logger=line_logger)
  if len(trade_dates) == 1:
    result = _enrich_pipeline_response(_process_api_single(trade_dates[0], eq_only, allowed_symbols, line_logger=line_logger))
  else:
    results = _run_range_stage(
      trade_dates,
      lambda trade_date: _process_api_single(trade_date, eq_only, allowed_symbols, line_logger=line_logger),
      line_logger=line_logger,
      include_load=True,
      stage_label='Processing delivery CSV',
    )
    message = _stage_message('NSE delivery CSV inserted into Oracle', trade_dates, results)
    result = _enrich_pipeline_response(_aggregate_stage_response(trade_dates, results, message, include_load=True, include_summary=True))
  decorated = mcap._apply_run_contract_fields(result, page='DELIVERY', mode='MANUAL', stage='process')
  try:
    mcap._persist_completed_run_record(_RUN_TYPE, trade_dates[-1], payload, decorated, mode='MANUAL', stage='process')
  except Exception:
    logger.exception('Unable to persist NSE delivery manual process run for tradeDate=%s', mcap._iso_date(trade_dates[-1]))
  return decorated



def _run_pipeline_single(trade_date: dt.date, eq_only: bool, allowed_symbols: Optional[set[str]], line_logger: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
  durations = {
    'downloadSeconds': 0.0,
    'extractValidateSeconds': 0.0,
    'insertProcessSeconds': 0.0,
    'successSeconds': 0.0,
  }
  existing_count = _existing_file_row_count(trade_date)
  if existing_count > 0:
    message = mcap._duplicate_trade_date_message(trade_date).strip()
    if line_logger:
      line_logger(f'[INFO] {message} existingRows={existing_count}')
    load_summary = {
      'inputRows': 0,
      'loadedCount': 0,
      'failureCount': 0,
      'skippedCount': 0,
      'universeSkippedCount': 0,
      'alreadyLoaded': True,
      'alreadyLoadedCount': existing_count,
    }
    return {
      'ok': True,
      'status': 'ALREADY_EXISTS',
      'done': True,
      'message': message,
      'tradeDate': mcap._iso_date(trade_date),
      'downloadPath': None,
      'inspection': {'alreadyLoaded': True, 'alreadyLoadedCount': existing_count},
      'load': load_summary,
      'summary': _get_dashboard_single(mcap._iso_date(trade_date)).get('summary', {}),
      'dbVerification': _delivery_db_verification(trade_date, existing_count, existing_count, load_summary),
      '_durations': durations,
    }
  rows_before = int(existing_count or 0)
  if line_logger:
    line_logger(mcap._flow_marker('download', f'Downloading NSE delivery CSV for {mcap._iso_date(trade_date)}.'))
  download_started = time.perf_counter()
  csv_path = download_delivery_csv(trade_date, line_logger=line_logger)
  durations['downloadSeconds'] = max(0.0, time.perf_counter() - download_started)
  if line_logger:
    line_logger(mcap._flow_marker('validate', f'Validating NSE delivery CSV for {mcap._iso_date(trade_date)}.'))
  validate_started = time.perf_counter()
  inspection = inspect_delivery_csv(csv_path, trade_date, eq_only=eq_only, allowed_symbols=allowed_symbols)
  durations['extractValidateSeconds'] = max(0.0, time.perf_counter() - validate_started)
  if line_logger:
    line_logger(mcap._flow_marker('process', f'Inserting NSE delivery rows into Oracle for {mcap._iso_date(trade_date)}.'))
  process_started = time.perf_counter()
  load_summary = load_delivery_csv(csv_path, trade_date, eq_only=eq_only, allowed_symbols=allowed_symbols, line_logger=line_logger)
  durations['insertProcessSeconds'] = max(0.0, time.perf_counter() - process_started)
  rows_after = _safe_existing_file_row_count(trade_date)
  if mcap._load_summary_failed(load_summary, inspection):
    return {
      'ok': False,
      'status': 'FAILED',
      'done': True,
      'message': 'NSE delivery pipeline failed during Oracle insert. No rows were written to Oracle.',
      'tradeDate': mcap._iso_date(trade_date),
      'downloadPath': str(csv_path),
      'inspection': inspection,
      'load': load_summary,
      'summary': {},
      'dbVerification': _delivery_db_verification(trade_date, rows_before, rows_after, load_summary),
      '_durations': durations,
    }
  return {
    'ok': True,
    'status': mcap._final_status_from_result({'inspection': inspection, 'load': load_summary}),
    'done': True,
    'message': 'NSE delivery pipeline completed.',
    'tradeDate': mcap._iso_date(trade_date),
    'downloadPath': str(csv_path),
    'inspection': inspection,
    'load': load_summary,
    'summary': _get_dashboard_single(mcap._iso_date(trade_date)).get('summary', {}),
    'dbVerification': _delivery_db_verification(trade_date, rows_before, rows_after, load_summary),
    '_durations': durations,
  }



def run_pipeline(payload: Dict[str, Any], line_logger: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
  trade_dates, eq_only, allowed_symbols = _parse_runtime_payload(payload, line_logger=line_logger)
  if len(trade_dates) == 1:
    single = dict(_run_pipeline_single(trade_dates[0], eq_only, allowed_symbols, line_logger=line_logger))
    durations = single.pop('_durations', None)
    result = _enrich_pipeline_response(single, durations=durations)
  else:
    results = _run_range_stage(
      trade_dates,
      lambda trade_date: _run_pipeline_single(trade_date, eq_only, allowed_symbols, line_logger=line_logger),
      line_logger=line_logger,
      include_load=True,
      stage_label='Running delivery pipeline',
    )
    message = _stage_message('NSE delivery pipeline completed', trade_dates, results)
    result = _enrich_pipeline_response(_aggregate_stage_response(trade_dates, results, message, include_load=True, include_summary=True))
  decorated = mcap._apply_run_contract_fields(result, page='DELIVERY', mode='AUTOMATION', stage='pipeline')
  if not str((payload or {}).get('jobRunId') or '').strip():
    try:
      mcap._persist_completed_run_record(_RUN_TYPE, trade_dates[-1], payload, decorated, mode='AUTOMATION', stage='pipeline')
    except Exception:
      logger.exception('Unable to persist NSE delivery automation run for tradeDate=%s', mcap._iso_date(trade_dates[-1]))
  return decorated



def process_existing_csv_for_symbols_api(payload: Dict[str, Any]) -> Dict[str, Any]:
  request_payload = payload if isinstance(payload, dict) else {}
  configured_dir = request_payload.get('downloadDir') or request_payload.get('download_dir')
  download_dir = Path(str(configured_dir).strip()) if str(configured_dir or '').strip() else _download_dir()
  existing_symbols_cache: Dict[str, set[str]] = {}

  def _load_existing_delivery_csv_cached(
    csv_path: Path,
    trade_date: dt.date,
    *,
    eq_only: bool,
    allowed_symbols: Optional[Sequence[str]],
    line_logger: Optional[Callable[[str], None]],
  ) -> Dict[str, Any]:
    cache_key = trade_date.isoformat()
    symbols_for_date = existing_symbols_cache.get(cache_key)
    if symbols_for_date is None:
      symbols_for_date = _existing_file_symbols(trade_date)
      existing_symbols_cache[cache_key] = symbols_for_date
    return load_delivery_csv(
      csv_path,
      trade_date,
      eq_only=eq_only,
      allowed_symbols=allowed_symbols,
      line_logger=line_logger,
      skip_if_existing=True,
      existing_symbols=symbols_for_date,
    )

  config = existing_csv_svc.ExistingCsvDatasetConfig(
    dataset_type='delivery_data',
    download_dir=download_dir,
    parse_trade_date=_trade_date_from_delivery_csv,
    inspect_csv=inspect_delivery_csv,
    load_csv=_load_existing_delivery_csv_cached,
    use_load_result_for_matching=True,
  )
  return existing_csv_svc.process_existing_csv_for_symbols(
    request_payload.get('symbols') or request_payload.get('symbol'),
    config,
    symbol_file_path=request_payload.get('symbolFilePath') or request_payload.get('symbol_file_path'),
    eq_only=mcap._coerce_bool(request_payload.get('eqOnly'), _EQ_ONLY_DEFAULT),
  )


def _get_data_overview(trade_date: Optional[dt.date], conn: Any = None, start_date: Optional[dt.date] = None, end_date: Optional[dt.date] = None) -> Dict[str, Any]:
  own_conn = conn is None
  connection = conn or mcap.pool.acquire()
  try:
    if own_conn:
      ensure_runtime(connection)
    return data_overview_svc.build_overview(connection, _TABLE_SQL, trade_date, start_date=start_date, end_date=end_date)
  finally:
    if own_conn:
      connection.close()


def get_trading_day_verification(year: Optional[int] = None, as_of_date: Optional[dt.date] = None) -> Dict[str, Any]:
  conn = mcap.pool.acquire()
  try:
    return mcap.build_trading_day_verification(conn, _TABLE_SQL, 'Delivery', year=year, as_of_date=as_of_date)
  finally:
    conn.close()
def _get_dashboard_single(trade_date_text: Optional[str] = None, limit: Optional[int] = None, include_overview: bool = True) -> Dict[str, Any]:
  conn = mcap.pool.acquire()
  try:
    ensure_runtime(conn)
    trade_date = mcap._parse_date(trade_date_text, 'tradeDate') if trade_date_text else mcap._business_date()
    overview: Dict[str, Any] = {}
    with conn.cursor() as cur:
      cur.execute(f"SELECT MAX(TRADE_DATE) FROM {_TABLE_SQL} WHERE TRADE_DATE = :trade_date AND FETCH_STATUS IN ('SUCCESS', 'PARTIAL')", {'trade_date': trade_date})
      if (cur.fetchone() or [None])[0] is None:
        cur.execute(f"SELECT MAX(TRADE_DATE) FROM {_TABLE_SQL} WHERE FETCH_STATUS IN ('SUCCESS', 'PARTIAL')")
        latest = (cur.fetchone() or [None])[0]
        if latest is not None and not trade_date_text:
          trade_date = mcap._parse_date(latest, 'tradeDate')
      if include_overview:
        overview = _get_data_overview(trade_date, conn=conn)
      cur.execute(
        f'''WITH latest_delivery AS (
              SELECT symbol, delivery_qty, delivery_pct,
                     ROW_NUMBER() OVER (
                       PARTITION BY symbol
                       ORDER BY fetch_ts DESC NULLS LAST, updated_ts DESC NULLS LAST, id DESC NULLS LAST
                     ) rn
              FROM {_TABLE_SQL}
              WHERE trade_date = :trade_date
                AND delivery_qty IS NOT NULL
            ),
            summary_stats AS (
              SELECT COUNT(*) total_rows, COUNT(DISTINCT symbol) distinct_symbols, MAX(fetch_ts) latest_fetch_ts,
                   SUM(CASE WHEN fetch_status = 'SUCCESS' THEN 1 ELSE 0 END) success_rows,
                   SUM(CASE WHEN fetch_status IN ('FAILED', 'PARSE_ERROR') THEN 1 ELSE 0 END) failure_rows,
                   SUM(CASE WHEN fetch_status = 'SKIPPED' THEN 1 ELSE 0 END) skipped_rows
              FROM {_TABLE_SQL}
              WHERE trade_date = :trade_date
            ),
            delivery_total AS (
              SELECT COUNT(*) delivery_rows,
                     NVL(SUM(delivery_qty), 0) delivery_qty_sum,
                     AVG(delivery_pct) delivery_pct_avg
              FROM latest_delivery
              WHERE rn = 1
            )
            SELECT s.total_rows, s.distinct_symbols, s.latest_fetch_ts,
                   s.success_rows, s.failure_rows, s.skipped_rows,
                   d.delivery_rows, d.delivery_qty_sum, d.delivery_pct_avg
            FROM summary_stats s
            CROSS JOIN delivery_total d''',
        {'trade_date': trade_date}
      )
      summary_row = mcap._row_to_dict(cur, cur.fetchone() or [])
      try:
        requested_limit = int(limit) if limit not in (None, '') else 0
      except (TypeError, ValueError):
        requested_limit = 0
      row_limit = requested_limit if requested_limit > 0 else int(summary_row.get('distinct_symbols') or 0)

      cur.execute(
        f'''SELECT id, trade_date, symbol, source_name, series, security_name,
                   prev_close, close_price, total_traded_qty, turnover_lacs,
                   no_of_trades, delivery_qty, delivery_pct, fetch_status,
                   error_message, fetch_ts, created_by, updated_ts
            FROM (
              SELECT t.*, ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fetch_ts DESC, updated_ts DESC, id DESC) rn
              FROM {_TABLE_SQL} t
              WHERE trade_date = :trade_date
            )
            WHERE rn = 1 AND ROWNUM <= :limit_value
            ORDER BY symbol''',
        {'trade_date': trade_date, 'limit_value': row_limit}
      )
      rows = mcap._apply_latest_row_insertion_metadata([mcap._row_to_dict(cur, row) for row in (cur.fetchall() or [])])

      cur.execute(
        f'''SELECT * FROM (
              SELECT run_id, trade_date, run_type, status, message, download_file_path, started_ts, finished_ts, created_by
              FROM {mcap._RUNS_TABLE_SQL}
              WHERE trade_date = :trade_date
                AND run_type = :run_type
              ORDER BY started_ts DESC
            ) WHERE ROWNUM <= 12''',
        {'trade_date': trade_date, 'run_type': _RUN_TYPE}
      )
      runs = [mcap._row_to_dict(cur, row) for row in (cur.fetchall() or [])]

      run_stats = mcap._load_trade_date_run_mode_stats(cur, mcap._RUNS_TABLE_SQL, trade_date)

    return mcap._apply_trade_date_metadata({
      'ok': True,
      'tradeDate': trade_date.strftime('%Y-%m-%d'),
      'downloadDir': str(_download_dir()),
      'summary': mcap._apply_insertion_summary_metadata({
        'totalRows': int(summary_row.get('total_rows') or 0),
        'distinctSymbols': int(summary_row.get('distinct_symbols') or 0),
        'latestFetchTs': summary_row.get('latest_fetch_ts'),
        'successRows': int(summary_row.get('success_rows') or 0),
        'failureRows': int(summary_row.get('failure_rows') or 0),
        'skippedRows': int(summary_row.get('skipped_rows') or 0),
        'deliveryRows': int(summary_row.get('delivery_rows') or 0),
        'deliveryQtySum': float(summary_row.get('delivery_qty_sum') or 0),
        'deliveryPctAvg': float(summary_row.get('delivery_pct_avg') or 0),
        'manualRows': int(run_stats.get('manual_runs') or 0),
        'automationRows': int(run_stats.get('auto_runs') or 0),
      }),
      'rows': rows,
      'recentRuns': runs,
      'sources': {'file': _FILE_SOURCE},
      'objects': {'table': _TABLE_SQL, 'runsTable': mcap._RUNS_TABLE_SQL, 'view': _LATEST_VIEW_SQL},
      'dataOverview': overview,
    }, trade_date)
  finally:
    conn.close()


def _get_dashboard_all(limit: Optional[int] = None) -> Dict[str, Any]:
  conn = mcap.pool.acquire()
  try:
    ensure_runtime(conn)
    with conn.cursor() as cur:
      cur.execute(f"SELECT MAX(TRADE_DATE) latest_trade_date FROM {_TABLE_SQL} WHERE FETCH_STATUS IN ('SUCCESS', 'PARTIAL')")
      latest_row = mcap._row_to_dict(cur, cur.fetchone() or [])
      latest_trade_date = latest_row.get('latest_trade_date')
    latest_trade_text = ''
    latest_payload: Dict[str, Any] = {'rows': [], 'recentRuns': []}
    if latest_trade_date:
      latest_trade_text = mcap._iso_date(latest_trade_date)
      latest_payload = _get_dashboard_single(latest_trade_text, limit=limit, include_overview=False)
    summary = dict(latest_payload.get('summary') or {})
    if not summary:
      summary = mcap._apply_insertion_summary_metadata({
        'totalRows': 0,
        'distinctSymbols': 0,
        'latestFetchTs': None,
        'successRows': 0,
        'failureRows': 0,
        'skippedRows': 0,
        'deliveryRows': 0,
        'deliveryQtySum': 0.0,
        'deliveryPctAvg': 0.0,
      })
    return mcap._apply_trade_date_metadata({
      'ok': True,
      'tradeDate': latest_trade_text,
      'downloadDir': str(_download_dir()),
      'summary': summary,
      'rows': latest_payload.get('rows') or [],
      'recentRuns': latest_payload.get('recentRuns') or [],
      'sources': {'file': _FILE_SOURCE},
      'objects': {'table': _TABLE_SQL, 'runsTable': mcap._RUNS_TABLE_SQL, 'view': _LATEST_VIEW_SQL},
      'dataOverview': _get_data_overview(None),
    }, latest_trade_text)
  finally:
    conn.close()


def _aggregate_dashboard_summary(items: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
  latest_fetch = None
  delivery_pct_weighted_total = 0.0
  summary = {
    'totalRows': 0,
    'distinctSymbols': 0,
    'latestFetchTs': None,
    'successRows': 0,
    'failureRows': 0,
    'skippedRows': 0,
    'deliveryRows': 0,
    'deliveryQtySum': 0.0,
    'deliveryPctAvg': 0.0,
  }
  for item in items:
    current = item.get('summary') or {}
    summary['totalRows'] += int(current.get('totalRows') or 0)
    summary['distinctSymbols'] += int(current.get('distinctSymbols') or 0)
    summary['successRows'] += int(current.get('successRows') or 0)
    summary['failureRows'] += int(current.get('failureRows') or 0)
    summary['skippedRows'] += int(current.get('skippedRows') or 0)
    summary['deliveryRows'] += int(current.get('deliveryRows') or 0)
    summary['deliveryQtySum'] += float(current.get('deliveryQtySum') or 0)
    delivery_pct_weighted_total += float(current.get('deliveryPctAvg') or 0) * int(current.get('deliveryRows') or 0)
    candidate_fetch = current.get('latestFetchTs')
    if candidate_fetch and (latest_fetch is None or str(candidate_fetch) > str(latest_fetch)):
      latest_fetch = candidate_fetch
  summary['latestFetchTs'] = latest_fetch
  if summary['deliveryRows'] > 0:
    summary['deliveryPctAvg'] = delivery_pct_weighted_total / float(summary['deliveryRows'])
  return mcap._apply_insertion_summary_metadata(summary)


def _aggregate_dashboard_rows(items: Sequence[Dict[str, Any]], limit: Optional[int]) -> List[Dict[str, Any]]:
  try:
    requested_limit = int(limit) if limit not in (None, '') else 0
  except (TypeError, ValueError):
    requested_limit = 0
  row_limit = requested_limit if requested_limit > 0 else 0
  latest_rows: List[Dict[str, Any]] = []
  latest_trade_key = ''
  for item in items:
    rows = list(item.get('rows') or [])
    if not rows:
      continue
    trade_key = str(item.get('tradeDate') or item.get('dataOverview', {}).get('selectedTradeDate') or rows[0].get('trade_date') or '')
    if trade_key >= latest_trade_key:
      latest_trade_key = trade_key
      latest_rows = rows
  if not latest_rows:
    return []
  return latest_rows[:row_limit] if row_limit > 0 else latest_rows

def get_dashboard(trade_date_text: Optional[str] = None, limit: Optional[int] = None, start_date_text: Optional[str] = None, end_date_text: Optional[str] = None, range_text: Optional[str] = None) -> Dict[str, Any]:
  requested_trade_date = str(trade_date_text or '').strip()
  requested_start_date = str(start_date_text or '').strip()
  requested_end_date = str(end_date_text or '').strip()
  requested_range = mcap._normalize_history_range(range_text)
  if not requested_trade_date and not requested_start_date and not requested_end_date and (not requested_range or requested_range == 'MAX'):
    return _get_dashboard_all(limit=limit)
  trade_dates = mcap._parse_trade_dates(
    requested_trade_date or None,
    requested_start_date or None,
    requested_end_date or None,
    range_value=requested_range,
  )
  if len(trade_dates) == 1:
    single_trade_date = requested_trade_date or (mcap._iso_date(trade_dates[0]) if (requested_start_date or requested_end_date) else None)
    result = _get_dashboard_single(single_trade_date, limit=limit)
    result['tradeDateLabel'] = mcap._trade_date_label(trade_dates)
    return result
  dashboards = [_get_dashboard_single(mcap._iso_date(trade_date), limit=limit, include_overview=False) for trade_date in trade_dates]
  base = dict(dashboards[-1])
  base.update(mcap._date_context(trade_dates))
  base['summary'] = _aggregate_dashboard_summary(dashboards)
  base['rows'] = _aggregate_dashboard_rows(dashboards, limit)
  base['dataOverview'] = _get_data_overview(trade_dates[-1], start_date=trade_dates[0], end_date=trade_dates[-1])
  return base



def _cleanup_jobs(now_ts: float) -> None:
  removed = mcap.prune_finished_jobs(
    _JOBS,
    now_ts=now_ts,
    ttl_seconds=_JOB_TTL_SEC,
    max_finished_items=mcap._JOB_MAX_RETAINED,
  )
  if removed:
    logger.info('Pruned %s completed NSE delivery job(s) from private memory.', len(removed))



def _serialize_job(job: Dict[str, Any], tail_lines: Optional[int]) -> Dict[str, Any]:
  return mcap._serialize_job(job, tail_lines)


def _parse_job_mode(payload: Dict[str, Any]) -> str:
  raw = str(payload.get('jobMode') or payload.get('job_mode') or '').strip().lower()
  if not raw or raw == 'pipeline':
    return 'pipeline'
  if raw in {'download', 'download-only', 'download_only'}:
    return 'download'
  raise ValueError('jobMode must be "download" or "pipeline".')



def _job_stats_from_result(result: Dict[str, Any]) -> Dict[str, Any]:
  inspection = result.get('inspection') or {}
  load = result.get('load') or {}
  inserted = int(load.get('loadedCount') or 0)
  return {
    'totalSymbolsProcessed': max(int(inspection.get('matchedSymbolsCount') or 0), int(inspection.get('matchedRows') or 0)),
    'totalRecordsDownloaded': int(inspection.get('inputRows') or 0),
    'totalRecordsValidated': int(inspection.get('matchedRows') or 0),
    'totalRecordsInserted': inserted,
    'totalFailed': int(load.get('failureCount') or 0),
    'totalSkipped': int(load.get('skippedCount') or 0) + int(load.get('universeSkippedCount') or 0),
    'insertPerformed': inserted > 0,
  }


def _latest_rows_for_payload(payload: Dict[str, Any], *, allow_existing_rows: bool = False, limit: Optional[int] = None) -> List[Dict[str, Any]]:
  request_payload = mcap._clone_request_payload(payload)
  try:
    dashboard = get_dashboard(
      request_payload.get('tradeDate'),
      limit=limit,
      start_date_text=request_payload.get('startDate'),
      end_date_text=request_payload.get('endDate'),
    )
    rows = dashboard.get('rows') or []
    if not rows:
      return []
    return list(rows[:limit]) if isinstance(limit, int) and limit > 0 else list(rows)
  except Exception:
    if allow_existing_rows:
      logger.exception('Unable to refresh NSE delivery latest rows from payload=%s', request_payload)
    return []


def _enrich_job_result(payload: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
  enriched = dict(result or {})
  stats = _job_stats_from_result(enriched)
  allow_existing_rows = bool((enriched.get('load') or {}).get('alreadyLoaded'))
  enriched['stats'] = stats
  enriched['latestRows'] = _latest_rows_for_payload(payload, allow_existing_rows=allow_existing_rows or bool(stats.get('insertPerformed')))
  return enriched


def start_pipeline_job(payload: Dict[str, Any]) -> Dict[str, Any]:
  ensure_runtime()
  trade_dates = mcap._parse_trade_dates(
    payload.get('tradeDate') or payload.get('trade_date'),
    payload.get('startDate') or payload.get('start_date'),
    payload.get('endDate') or payload.get('end_date'),
    range_value=payload.get('range') or payload.get('dateRange') or payload.get('date_range'),
    allow_override=mcap._allow_market_date_override(payload),
  )
  trade_date = trade_dates[-1]
  job_mode = _parse_job_mode(payload)
  request_payload = mcap._clone_request_payload(payload)
  try:
    duplicate_row = mcap._find_persisted_run_by_identity(
      request_payload,
      run_type=_RUN_TYPE,
      statuses=list(mcap._JOB_ACTIVE_STATUSES),
    )
  except Exception:
    duplicate_row = None
    logger.warning('Unable to check active NSE delivery pipeline run; continuing with start request.', exc_info=True)
  if duplicate_row:
    duplicate_job = mcap._persisted_job_from_row(duplicate_row, 180)
    duplicate_job['message'] = str(duplicate_job.get('message') or 'NSE delivery job is already running for this logical batch.')
    return duplicate_job
  job_id = uuid.uuid4().hex
  job_message = 'Delivery download job started.' if job_mode == 'download' else ('Delivery pipeline job started.' if len(trade_dates) == 1 else f'Delivery pipeline job started for {mcap._trade_date_label(trade_dates)}.')
  job = {
    'id': job_id,
    'jobType': 'delivery',
    'pipelineType': 'delivery',
    'jobMode': job_mode,
    'status': 'running',
    'message': job_message,
    'startedAt': dt.datetime.utcnow().replace(microsecond=0).isoformat() + 'Z',
    'updatedAt': dt.datetime.utcnow().replace(microsecond=0).isoformat() + 'Z',
    'finishedAt': None,
    'finished_ts': 0.0,
    'request': request_payload,
    'result': None,
    'stats': mcap._empty_job_stats(),
    'latestRows': [],
    'downloadPath': None,
    'logs': [],
    'flow': mcap._new_job_flow('Preparing background pipeline.' if job_mode == 'pipeline' else 'Preparing download job.'),
  }

  def _worker() -> None:
    def _log(line: str) -> None:
      with _JOBS_LOCK:
        current = _JOBS.get(job_id)
        if current and line:
          text = str(line).rstrip()
          marker = mcap._parse_flow_marker(text)
          if marker:
            mcap._advance_job_flow(current, marker[0], marker[1] or None)
          else:
            current['logs'].append(text)
            if len(current['logs']) > 1200:
              del current['logs'][: len(current['logs']) - 900]
          current['updatedAt'] = dt.datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'
          current['message'] = str(current.get('flow', {}).get('detail') or current.get('message') or job_message)
          mcap._maybe_persist_job_snapshot(job_id, current, force=bool(marker))

    status = 'FAILED'
    message = 'Delivery pipeline job failed.' if job_mode == 'pipeline' else 'Delivery download job failed.'
    metrics: Dict[str, Any]
    download_path: Optional[str] = None
    flow_ok = False
    try:
      metrics = download_api(payload) if job_mode == 'download' else run_pipeline(payload, _log)
      if job_mode == 'pipeline':
        metrics = _enrich_pipeline_response(metrics)
      if metrics.get('ok'):
        with _JOBS_LOCK:
          current = _JOBS.get(job_id)
          if current:
            finalizing_detail = 'Finalizing delivery download results.' if job_mode == 'download' else 'Finalizing NSE delivery pipeline results.'
            mcap._enter_job_finalizing_stage(current, finalizing_detail)
            mcap._maybe_persist_job_snapshot(job_id, current, force=True)
      metrics = _enrich_job_result(request_payload, metrics)
      status = mcap._final_status_from_result(metrics)
      if not status:
        status = 'SUCCESS' if metrics.get('ok') else 'FAILED'
      if job_mode == 'download' and metrics.get('ok') and status in {'NO_ACTION', 'ALREADY_EXISTS'}:
        status = 'SUCCESS'
      flow_ok = not _status_is_failure(status)
      message = str(metrics.get('message') or ('Delivery download completed.' if job_mode == 'download' else 'Delivery pipeline completed.'))
      download_path = metrics.get('downloadPath')
    except Exception as exc:
      metrics = {'ok': False, 'status': 'FAILED', 'error': str(exc)}
      flow_ok = False
      message = str(exc)
      _log(f'[ERROR] {exc}')
      logger.exception('NSE delivery pipeline job failed')
    with _JOBS_LOCK:
      current = _JOBS.get(job_id)
      logs = []
      if current:
        current['status'] = status
        current['message'] = message
        current['updatedAt'] = dt.datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'
        current['finishedAt'] = current['updatedAt']
        current['finished_ts'] = time.time()
        current['result'] = metrics
        current['stats'] = metrics.get('stats') if isinstance(metrics, dict) else mcap._empty_job_stats()
        current['latestRows'] = list(metrics.get('latestRows') or []) if isinstance(metrics, dict) else []
        current['downloadPath'] = download_path
        mcap._finish_job_flow(current, flow_ok, message, when_ts=current['finished_ts'])
        logs = list(current.get('logs') or [])
        mcap._maybe_persist_job_snapshot(job_id, current, force=True)
    mcap._save_run_finish(job_id, status, message, metrics, logs, download_path, job=current if current else None)

  with _JOBS_LOCK:
    _cleanup_jobs(time.time())
    _JOBS[job_id] = job
  mcap._save_run_start(job_id, trade_date, _RUN_TYPE, payload)
  mcap._maybe_persist_job_snapshot(job_id, job, force=True)
  threading.Thread(target=_worker, daemon=True, name=f'nse-delivery-pipeline-{job_id[:8]}').start()
  return {'ok': True, 'jobId': job_id, 'jobType': 'delivery', 'jobMode': job_mode, 'status': 'running', 'message': job_message, 'flow': mcap._serialize_job_flow(job.get('flow'))}



def get_job(job_id: str, tail_lines: Optional[int] = None) -> Dict[str, Any]:
  token = str(job_id or '').strip()
  if not token:
    raise ValueError('jobId is required.')
  with _JOBS_LOCK:
    _cleanup_jobs(time.time())
    job = _JOBS.get(token)
    if job:
      return _serialize_job(job, tail_lines)
  persisted = mcap._fetch_persisted_run_row(run_id=token, run_type=_RUN_TYPE)
  if persisted:
    return mcap._persisted_job_from_row(persisted, tail_lines)
  raise ValueError(f'NSE delivery job not found: {token}')


def get_latest_job(tail_lines: Optional[int] = None) -> Dict[str, Any]:
  with _JOBS_LOCK:
    _cleanup_jobs(time.time())
    jobs = list(_JOBS.values())
    if jobs:
      running = [job for job in jobs if str(job.get('status') or '').strip().lower() == 'running']
      candidates = running or jobs
      candidates.sort(key=lambda item: str(item.get('startedAt') or ''), reverse=True)
      return _serialize_job(candidates[0], tail_lines)
  persisted = mcap._fetch_persisted_run_row(run_type=_RUN_TYPE)
  if persisted:
    return mcap._persisted_job_from_row(persisted, tail_lines)
  raise ValueError('No NSE delivery jobs found.')
