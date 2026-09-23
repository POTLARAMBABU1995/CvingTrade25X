from __future__ import annotations

import csv
import copy
import datetime as dt
import hashlib
import json
import logging
import math
import os
import random
import re
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal, InvalidOperation
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener
import oracledb

from cache import TTLCache

try:
  from .. import db_pool as db_pool_module
  from ..db_pool import pool
  from . import nifty500_sync_service as nifty500_svc
  from . import nse_existing_csv_symbol_service as existing_csv_svc
  from . import nse_data_overview_service as data_overview_svc
  from .job_memory_policy import prune_finished_jobs
except ImportError:  # pragma: no cover
  import db_pool as db_pool_module  # type: ignore
  from db_pool import pool  # type: ignore
  from services import nifty500_sync_service as nifty500_svc  # type: ignore
  from services import nse_existing_csv_symbol_service as existing_csv_svc  # type: ignore
  from services import nse_data_overview_service as data_overview_svc  # type: ignore
  from services.job_memory_policy import prune_finished_jobs  # type: ignore

try:
  from app.utils import market_calendar
except ImportError:  # pragma: no cover
  from backend.app.utils import market_calendar  # type: ignore

logger = logging.getLogger(__name__)

_TABLE = (os.getenv('NSE_MCAP_TABLE') or 'CVING_NSE_MARKET_CAP_HIST').strip()
_RUNS_TABLE = (os.getenv('NSE_MCAP_RUNS_TABLE') or 'CVING_NSE_MCAP_PIPELINE_RUNS').strip()
_LATEST_VIEW = (os.getenv('NSE_MCAP_LATEST_VIEW') or 'VW_CVING_NSE_MARKET_CAP_LATEST').strip()
_INDEX_VIEW = (os.getenv('NSE_MCAP_INDEX_VIEW') or 'V_NSE_MARKET_CAP_INDEX').strip()
_DELIVERY_TABLE = (os.getenv('NSE_DELIVERY_TABLE') or 'CVING_NSE_DELIVERY_HIST').strip()
_RUN_TYPE = 'MCAP'
_FILE_SOURCE = (os.getenv('NSE_MCAP_SOURCE_NAME') or 'NSE_MCAP_FILE').strip().upper()
_QUOTE_SOURCE = (os.getenv('NSE_MCAP_QUOTE_SOURCE_NAME') or 'NSE_QUOTE_API').strip().upper()
_CREATED_BY = (os.getenv('NSE_MCAP_CREATED_BY') or 'CVING_NSE_MCAP_UI').strip() or 'CVING_NSE_MCAP_UI'

_NSE_BASE = (os.getenv('NSE_BASE_URL') or 'https://www.nseindia.com').strip().rstrip('/')
_ARCHIVE_BASE = (os.getenv('NSE_ARCHIVE_BASE_URL') or 'https://nsearchives.nseindia.com').strip().rstrip('/')
_TIMEOUT_SEC = max(5, int(str(os.getenv('NSE_MCAP_REQUEST_TIMEOUT', '25')).strip() or '25'))
_RETRY_COUNT = max(1, int(str(os.getenv('NSE_MCAP_RETRY_COUNT', '4')).strip() or '4'))
_MIN_SLEEP = max(0.0, float(str(os.getenv('NSE_MCAP_MIN_SLEEP_SEC', '0.45')).strip() or '0.45'))
_MAX_SLEEP = max(_MIN_SLEEP, float(str(os.getenv('NSE_MCAP_MAX_SLEEP_SEC', '1.15')).strip() or '1.15'))
_QUOTE_TIMEOUT_SEC = max(3, int(str(os.getenv('NSE_MCAP_QUOTE_REQUEST_TIMEOUT', '10')).strip() or '10'))
_QUOTE_RETRY_COUNT = max(1, int(str(os.getenv('NSE_MCAP_QUOTE_RETRY_COUNT', '2')).strip() or '2'))
_QUOTE_MIN_SLEEP = max(0.0, float(str(os.getenv('NSE_MCAP_QUOTE_MIN_SLEEP_SEC', '0.0')).strip() or '0.0'))
_QUOTE_MAX_SLEEP = max(_QUOTE_MIN_SLEEP, float(str(os.getenv('NSE_MCAP_QUOTE_MAX_SLEEP_SEC', '0.08')).strip() or '0.08'))
_DOWNLOAD_TIMEOUT_SEC = max(3, int(str(os.getenv('NSE_DOWNLOAD_REQUEST_TIMEOUT', '8')).strip() or '8'))
_DOWNLOAD_RETRY_COUNT = max(1, int(str(os.getenv('NSE_DOWNLOAD_RETRY_COUNT', '2')).strip() or '2'))
_DOWNLOAD_MIN_SLEEP = max(0.0, float(str(os.getenv('NSE_DOWNLOAD_MIN_SLEEP_SEC', '0.05')).strip() or '0.05'))
_DOWNLOAD_MAX_SLEEP = max(_DOWNLOAD_MIN_SLEEP, float(str(os.getenv('NSE_DOWNLOAD_MAX_SLEEP_SEC', '0.25')).strip() or '0.25'))
_DISCOVERY_TIMEOUT_SEC = max(3, int(str(os.getenv('NSE_DISCOVERY_REQUEST_TIMEOUT', '6')).strip() or '6'))
_DISCOVERY_RETRY_COUNT = max(1, int(str(os.getenv('NSE_DISCOVERY_RETRY_COUNT', '1')).strip() or '1'))
_NSE_SESSION_WARM_TTL_SEC = max(5, int(str(os.getenv('NSE_SESSION_WARM_TTL_SEC', '45')).strip() or '45'))
_EQ_ONLY_DEFAULT = str(os.getenv('NSE_MCAP_EQ_ONLY', 'true')).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}
_FILTER_TO_NIFTY500 = str(os.getenv('NSE_MCAP_FILTER_TO_NIFTY500', 'true')).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}
_JOB_TTL_SEC = max(900, int(str(os.getenv('NSE_MCAP_JOB_TTL_SEC', '43200')).strip() or '43200'))
_JOB_MAX_RETAINED = max(1, int(str(os.getenv('NSE_JOB_MAX_RETAINED', '4')).strip() or '4'))
_JOB_TIMEOUT_SEC = max(900, int(str(os.getenv('NSE_MCAP_JOB_TIMEOUT_SEC', '2700')).strip() or '2700'))
_LOOKUP_CACHE_TTL_SEC = max(0, int(str(os.getenv('NSE_MCAP_LOOKUP_CACHE_TTL_SEC', '300')).strip() or '300'))
_LOOKUP_CACHE_MAX_ITEMS = max(1, int(str(os.getenv('NSE_MCAP_LOOKUP_CACHE_MAX_ITEMS', '64')).strip() or '64'))
_LOOKUP_CACHE_MAX_MEMORY_MB = max(1, int(str(os.getenv('NSE_MCAP_LOOKUP_CACHE_MAX_MEMORY_MB', '64')).strip() or '64'))
_MAX_ROWS = 500
_LOAD_BATCH_SIZE = max(100, int(str(os.getenv('NSE_MCAP_LOAD_BATCH_SIZE', '500')).strip() or '500'))
_ENRICH_BATCH_SIZE = max(1, int(str(os.getenv('NSE_MCAP_ENRICH_BATCH_SIZE', '100')).strip() or '100'))
_ENRICH_CONCURRENCY = max(1, int(str(os.getenv('NSE_MCAP_ENRICH_CONCURRENCY', '8')).strip() or '8'))

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DOWNLOAD_DIR = Path(
  os.getenv('MARKET_CAP_DOWNLOAD_DIR')
  or os.getenv('NSE_MCAP_DOWNLOAD_DIR')
  or (_PROJECT_ROOT / 'batch' / 'nse_market_cap' / 'downloads')
)
_DOWNLOAD_HINTS_FILE = 'nse_mcap_source_cache.json'
_IDENT_RE = re.compile(r'^[A-Za-z0-9_.$#]+$')
_HEADER_RE = re.compile(r'[^A-Z0-9]+')
_NON_NUMERIC_RE = re.compile(r'[^0-9.\-]')
_HREF_RE = re.compile(r'''(?:href|src)=["']([^"']+)["']''', re.IGNORECASE)
_TEXT_URL_RE = re.compile(r'''https?://[^\s"'<>]+''', re.IGNORECASE)
_FILENAME_CANDIDATE_RE = re.compile(r'''(?i)\b(?:pr\d{6}\.zip|mcap\d{8}\.csv)\b''')
_LOCAL_MCAP_CSV_RE = re.compile(r'(?i)^mcap(?P<date>\d{8})\.csv$')

_SYMBOL_COLUMNS = ('SYMBOL', 'SYMB', 'SYM', 'TICKER')
_SERIES_COLUMNS = ('SERIES', 'SR', 'SER')
_NAME_COLUMNS = ('SECURITYNAME', 'SECURITY_NAME', 'SECURITY', 'NAMEOFCOMPANY', 'COMPANYNAME')
_MCAP_COLUMNS = ('MARKETCAPRS', 'MARKETCAPRSCR', 'MARKETCAP', 'TOTALMARKETCAPRS', 'TOTALMARKETCAP', 'MCAPRS', 'MCAP')
_FFMC_COLUMNS = ('FFMC', 'FREEFLOATMARKETCAP', 'FREEFLOATMCAP')
_USER_AGENTS = (
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
  'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15',
)
_UNIT_FACTORS = {'CR': Decimal('1'), 'RS': Decimal('0.0000001'), 'LAC': Decimal('0.01')}
_UNIT_ALIASES = {'CRORE': 'CR', 'CRORES': 'CR', 'CR': 'CR', 'RS': 'RS', 'RUPEE': 'RS', 'RUPEES': 'RS', 'INR': 'RS', 'LAC': 'LAC', 'LAKH': 'LAC', 'LAKHS': 'LAC'}
_SUPPORTED_HISTORY_RANGES: Dict[str, Optional[int]] = {
  '2Y': 2,
  '3Y': 3,
  '5Y': 5,
  'MAX': None,
}

_RUNTIME_READY = False
_RUNTIME_LOCK = threading.Lock()
_DOWNLOAD_HINTS_LOCK = threading.Lock()
_TABLE_ID_GENERATION_CACHE: Dict[str, bool] = {}
_MARKETCAP_LOOKUP_CACHE = TTLCache(
  ttl_seconds=_LOOKUP_CACHE_TTL_SEC,
  max_items=_LOOKUP_CACHE_MAX_ITEMS,
  max_bytes=_LOOKUP_CACHE_MAX_MEMORY_MB * 1024 * 1024,
)
_INDEX_VIEW_AVAILABLE: Optional[bool] = None
_NSE_SESSION_STATE_LOCK = threading.Lock()
_NSE_SESSION_WARM_UNTIL_TS = 0.0
_NSE_SESSION_WARM_IN_FLIGHT = False
_NSE_SESSION_COOKIE_SNAPSHOT: List[Any] = []
_JOBS: Dict[str, Dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()
_FLOW_KEYS = ('download', 'validate', 'process', 'success')
_ABANDONED_JOB_MAX_AGE_SECONDS = 2 * 60 * 60
_FLOW_MARKER_RE = re.compile(r'^\[FLOW\]\s*stage=(?P<stage>download|validate|process|success)(?:\s+detail=(?P<detail>.+))?$', re.IGNORECASE)
_RUN_ROW_SELECT_SQL = '''RUN_ID, TRADE_DATE, RUN_TYPE, STATUS,
                 DBMS_LOB.SUBSTR(REQUEST_JSON, 4000, 1) AS REQUEST_JSON,
                 DBMS_LOB.SUBSTR(METRICS_JSON, 4000, 1) AS METRICS_JSON,
                 MESSAGE, DOWNLOAD_FILE_PATH,
                 DBMS_LOB.SUBSTR(LOGS_CLOB, 4000, 1) AS LOGS_CLOB,
                 STARTED_TS, FINISHED_TS, CREATED_BY'''


def _is_closed_pool_error(exc: Exception) -> bool:
  return isinstance(exc, oracledb.InterfaceError) and 'DPY-1002' in str(exc)


def _acquire_connection():
  global pool
  try:
    return pool.acquire()
  except Exception as exc:
    if not _is_closed_pool_error(exc):
      raise
    logger.warning('Oracle pool was closed; recreating pool for NSE market-data services.')
    pool = db_pool_module.recreate_pool()
    return pool.acquire()


_JOB_ACTIVE_STATUSES = {
  'QUEUED',
  'RUNNING',
  'DOWNLOADING',
  'DOWNLOADED',
  'EXTRACTING',
  'EXTRACTED',
  'VALIDATING',
  'VALIDATED',
  'INSERTING',
  'RECONCILING',
}
_JOB_TERMINAL_STATUSES = {
  'SUCCESS',
  'PARTIAL',
  'FAILED',
  'CANCELLED',
  'TIMED_OUT',
  'SKIPPED',
  'ALREADY_EXISTS',
  'NO_ACTION',
}
_JOB_FAILURE_STATUSES = {'FAILED', 'CANCELLED', 'TIMED_OUT'}
_JOB_NON_FAILURE_TERMINAL_STATUSES = _JOB_TERMINAL_STATUSES - _JOB_FAILURE_STATUSES


def _safe_ident(value: str) -> str:
  text = str(value or '').strip()
  if not text or not _IDENT_RE.match(text):
    raise ValueError(f'Invalid identifier: {value!r}')
  return text


_TABLE_SQL = _safe_ident(_TABLE)
_RUNS_TABLE_SQL = _safe_ident(_RUNS_TABLE)
_LATEST_VIEW_SQL = _safe_ident(_LATEST_VIEW)
_INDEX_VIEW_SQL = _safe_ident(_INDEX_VIEW)
_DELIVERY_TABLE_SQL = _safe_ident(_DELIVERY_TABLE)


def _split_ident(value: str) -> Tuple[Optional[str], str]:
  text = _safe_ident(value)
  if '.' in text:
    owner, name = text.rsplit('.', 1)
    return owner.upper(), name.upper()
  return None, text.upper()


def _table_supports_implicit_id(conn: Any, table_ident: str) -> bool:
  cache_key = _safe_ident(table_ident).upper()
  cached = _TABLE_ID_GENERATION_CACHE.get(cache_key)
  if cached is not None:
    return cached
  owner, table_name = _split_ident(table_ident)
  column_sql = '''
    SELECT data_default, identity_column
      FROM user_tab_columns
     WHERE table_name = :table_name
       AND column_name = 'ID'
  '''
  trigger_sql = '''
    SELECT 1
      FROM user_triggers
     WHERE table_name = :table_name
       AND status = 'ENABLED'
       AND triggering_event LIKE '%INSERT%'
       AND ROWNUM = 1
  '''
  binds: Dict[str, Any] = {'table_name': table_name}
  if owner:
    column_sql = '''
      SELECT data_default, identity_column
        FROM all_tab_columns
       WHERE owner = :owner
         AND table_name = :table_name
         AND column_name = 'ID'
    '''
    trigger_sql = '''
      SELECT 1
        FROM all_triggers
       WHERE table_owner = :owner
         AND table_name = :table_name
         AND status = 'ENABLED'
         AND triggering_event LIKE '%INSERT%'
         AND ROWNUM = 1
    '''
    binds['owner'] = owner
  with conn.cursor() as cur:
    cur.execute(column_sql, binds)
    row = cur.fetchone()
    data_default = row[0] if row else None
    identity_column = str((row[1] if row else None) or '').strip().upper()
    supported = identity_column == 'YES' or bool(str(data_default or '').strip())
    if not supported:
      cur.execute(trigger_sql, binds)
      supported = cur.fetchone() is not None
  _TABLE_ID_GENERATION_CACHE[cache_key] = supported
  return supported


def _assign_missing_record_ids(conn: Any, table_ident: str, records: Sequence[Dict[str, Any]], *, force: bool = False) -> bool:
  if not records or _table_supports_implicit_id(conn, table_ident):
    return False
  pending = [record for record in records if force or record.get('id') in (None, '')]
  if not pending:
    return False
  with conn.cursor() as cur:
    cur.execute(f'LOCK TABLE {table_ident} IN EXCLUSIVE MODE')
    cur.execute(f'SELECT NVL(MAX(ID), 0) FROM {table_ident}')
    row = cur.fetchone()
    start_id = int((row[0] if row else 0) or 0)
  for offset, record in enumerate(pending, start=1):
    record['id'] = start_id + offset
  return True


def _load_summary_failed(load_summary: Optional[Dict[str, Any]], inspection: Optional[Dict[str, Any]] = None) -> bool:
  load = load_summary or {}
  if bool(load.get('alreadyLoaded')):
    return False
  failure_count = int(load.get('failureCount') or 0)
  if failure_count <= 0:
    return False
  loaded_count = int(load.get('loadedCount') or 0)
  matched_rows = int((inspection or {}).get('matchedRows') or 0)
  return loaded_count <= 0 and matched_rows > 0


def _enrichment_summary_failed(summary: Optional[Dict[str, Any]]) -> bool:
  enrichment = summary or {}
  requested = int(enrichment.get('requested') or 0)
  success_count = int(enrichment.get('successCount') or 0)
  failure_count = int(enrichment.get('failureCount') or 0)
  return requested > 0 and success_count <= 0 and failure_count > 0


def _json_default(value: Any) -> Any:
  if isinstance(value, Decimal):
    return float(value)
  if isinstance(value, (dt.date, dt.datetime)):
    return value.isoformat()
  return str(value)


def _utc_timestamp(ts: Optional[float] = None) -> str:
  value = float(ts if ts is not None else time.time())
  return dt.datetime.utcfromtimestamp(value).replace(microsecond=0).isoformat() + 'Z'


def _flow_marker(stage: str, detail: str) -> str:
  return f'[FLOW] stage={stage} detail={detail}'


def _status_token(status: Any) -> str:
  token = str(status or '').strip().upper().replace(' ', '_')
  if token in {'SUCCEEDED', 'COMPLETED'}:
    return 'SUCCESS'
  return token


def _is_job_active_status(status: Any) -> bool:
  return _status_token(status) in _JOB_ACTIVE_STATUSES


def _is_job_terminal_status(status: Any) -> bool:
  return _status_token(status) in _JOB_TERMINAL_STATUSES


def _is_job_failure_status(status: Any) -> bool:
  return _status_token(status) in _JOB_FAILURE_STATUSES


def _stage_status_from_key(stage: str) -> str:
  token = str(stage or '').strip().lower()
  if token == 'download':
    return 'DOWNLOADING'
  if token == 'validate':
    return 'VALIDATING'
  if token == 'process':
    return 'INSERTING'
  if token == 'success':
    return 'RECONCILING'
  return 'RUNNING'


def _new_job_flow(detail: str = 'Preparing NSE extraction.', *, started_ts: Optional[float] = None) -> Dict[str, Any]:
  now_ts = float(started_ts if started_ts is not None else time.time())
  started_at = _utc_timestamp(now_ts)
  return {
    'keys': list(_FLOW_KEYS),
    'activeKey': 'download',
    'failedKey': '',
    'detail': detail,
    'stageStartedAt': started_at,
    'stageStartedTs': now_ts,
    'stageFinishedAt': None,
    'stageFinishedTs': None,
    'durationsMs': {key: 0 for key in _FLOW_KEYS},
    'completed': {key: False for key in _FLOW_KEYS},
    'history': {
      key: {'startedAt': None, 'startedTs': None, 'endedAt': None, 'endedTs': None, 'elapsedMs': 0, 'status': 'NOT_STARTED'}
      for key in _FLOW_KEYS
    },
    'updatedAt': started_at,
    'finishedAt': None,
  }


def _advance_job_flow(job: Dict[str, Any], stage: str, detail: Optional[str] = None, *, when_ts: Optional[float] = None) -> None:
  if stage not in _FLOW_KEYS:
    return
  flow = job.setdefault('flow', _new_job_flow())
  now_ts = float(when_ts if when_ts is not None else time.time())
  now_at = _utc_timestamp(now_ts)
  current_stage = str(flow.get('activeKey') or '').strip().lower()
  durations = flow.setdefault('durationsMs', {key: 0 for key in _FLOW_KEYS})
  completed = flow.setdefault('completed', {key: False for key in _FLOW_KEYS})
  history = flow.setdefault('history', {key: {'startedAt': None, 'startedTs': None, 'endedAt': None, 'endedTs': None, 'elapsedMs': 0, 'status': 'NOT_STARTED'} for key in _FLOW_KEYS})
  flow['failedKey'] = ''
  if current_stage and current_stage in _FLOW_KEYS and current_stage != stage:
    stage_started_ts = float(flow.get('stageStartedTs') or now_ts)
    elapsed_ms = max(0, int(round((now_ts - stage_started_ts) * 1000)))
    durations[current_stage] = int(durations.get(current_stage) or 0) + elapsed_ms
    completed[current_stage] = True
    previous = history.setdefault(current_stage, {'startedAt': None, 'startedTs': None, 'endedAt': None, 'endedTs': None, 'elapsedMs': 0, 'status': 'NOT_STARTED'})
    previous['endedAt'] = now_at
    previous['endedTs'] = now_ts
    previous['elapsedMs'] = int(previous.get('elapsedMs') or 0) + elapsed_ms
    previous['status'] = 'COMPLETED'
  if current_stage != stage:
    flow['activeKey'] = stage
    flow['stageStartedTs'] = now_ts
    flow['stageStartedAt'] = now_at
    current = history.setdefault(stage, {'startedAt': None, 'startedTs': None, 'endedAt': None, 'endedTs': None, 'elapsedMs': 0, 'status': 'NOT_STARTED'})
    if not current.get('startedAt'):
      current['startedAt'] = now_at
      current['startedTs'] = now_ts
    current['status'] = 'STARTED'
  elif not flow.get('stageStartedAt'):
    flow['stageStartedTs'] = now_ts
    flow['stageStartedAt'] = now_at
    current = history.setdefault(stage, {'startedAt': None, 'startedTs': None, 'endedAt': None, 'endedTs': None, 'elapsedMs': 0, 'status': 'NOT_STARTED'})
    if not current.get('startedAt'):
      current['startedAt'] = now_at
      current['startedTs'] = now_ts
    current['status'] = 'STARTED'
  if detail:
    flow['detail'] = detail
  flow['updatedAt'] = now_at


def _finish_job_flow(job: Dict[str, Any], succeeded: bool, detail: Optional[str] = None, *, when_ts: Optional[float] = None) -> None:
  flow = job.setdefault('flow', _new_job_flow())
  now_ts = float(when_ts if when_ts is not None else time.time())
  now_at = _utc_timestamp(now_ts)
  current_stage = str(flow.get('activeKey') or '').strip().lower()
  durations = flow.setdefault('durationsMs', {key: 0 for key in _FLOW_KEYS})
  completed = flow.setdefault('completed', {key: False for key in _FLOW_KEYS})
  history = flow.setdefault('history', {key: {'startedAt': None, 'startedTs': None, 'endedAt': None, 'endedTs': None, 'elapsedMs': 0, 'status': 'NOT_STARTED'} for key in _FLOW_KEYS})
  flow['failedKey'] = ''
  if current_stage and current_stage in _FLOW_KEYS:
    stage_started_ts = float(flow.get('stageStartedTs') or now_ts)
    elapsed_ms = max(0, int(round((now_ts - stage_started_ts) * 1000)))
    durations[current_stage] = int(durations.get(current_stage) or 0) + elapsed_ms
    current = history.setdefault(current_stage, {'startedAt': None, 'startedTs': None, 'endedAt': None, 'endedTs': None, 'elapsedMs': 0, 'status': 'NOT_STARTED'})
    if not current.get('startedAt'):
      current['startedAt'] = flow.get('stageStartedAt') or now_at
      current['startedTs'] = stage_started_ts
    current['endedAt'] = now_at
    current['endedTs'] = now_ts
    current['elapsedMs'] = int(current.get('elapsedMs') or 0) + elapsed_ms
    if succeeded:
      completed[current_stage] = True
      current['status'] = 'COMPLETED'
    else:
      current['status'] = 'FAILED'
  if succeeded:
    flow['activeKey'] = 'success'
    completed['success'] = True
    flow['stageStartedTs'] = now_ts
    flow['stageStartedAt'] = now_at
    success_stage = history.setdefault('success', {'startedAt': None, 'startedTs': None, 'endedAt': None, 'endedTs': None, 'elapsedMs': 0, 'status': 'NOT_STARTED'})
    if not success_stage.get('startedAt'):
      success_stage['startedAt'] = now_at
      success_stage['startedTs'] = now_ts
    success_stage['endedAt'] = now_at
    success_stage['endedTs'] = now_ts
    success_stage['status'] = 'COMPLETED'
  else:
    flow['activeKey'] = current_stage if current_stage in _FLOW_KEYS else ''
    if current_stage in _FLOW_KEYS:
      flow['failedKey'] = current_stage
  if detail:
    flow['detail'] = detail
  flow['updatedAt'] = now_at
  flow['finishedAt'] = now_at
  flow['stageFinishedAt'] = now_at
  flow['stageFinishedTs'] = now_ts


def _enter_job_finalizing_stage(job: Dict[str, Any], detail: str, *, when_ts: Optional[float] = None) -> None:
  now_ts = float(when_ts if when_ts is not None else time.time())
  now_at = _utc_timestamp(now_ts)
  _advance_job_flow(job, 'success', detail, when_ts=now_ts)
  job['updatedAt'] = now_at
  job['message'] = detail


def _serialize_job_flow(flow: Optional[Dict[str, Any]]) -> Dict[str, Any]:
  current = flow or _new_job_flow()
  durations = current.get('durationsMs') or {}
  completed = current.get('completed') or {}
  history = current.get('history') or {}
  return {
    'keys': list(current.get('keys') or list(_FLOW_KEYS)),
    'activeKey': current.get('activeKey') or '',
    'failedKey': current.get('failedKey') or '',
    'detail': current.get('detail') or '',
    'stageStartedAt': current.get('stageStartedAt'),
    'stageFinishedAt': current.get('stageFinishedAt'),
    'durationsMs': {key: int(durations.get(key) or 0) for key in _FLOW_KEYS},
    'completed': {key: bool(completed.get(key)) for key in _FLOW_KEYS},
    'history': {
      key: {
        'startedAt': (history.get(key) or {}).get('startedAt'),
        'startedTs': (history.get(key) or {}).get('startedTs'),
        'endedAt': (history.get(key) or {}).get('endedAt'),
        'endedTs': (history.get(key) or {}).get('endedTs'),
        'elapsedMs': int((history.get(key) or {}).get('elapsedMs') or 0),
        'status': str((history.get(key) or {}).get('status') or 'NOT_STARTED'),
      }
      for key in _FLOW_KEYS
    },
    'updatedAt': current.get('updatedAt'),
    'finishedAt': current.get('finishedAt'),
  }


def _normalized_job_flow_snapshot(flow: Optional[Dict[str, Any]], job_status: Any, *, finished_at: Optional[str] = None) -> Dict[str, Any]:
  snapshot = _serialize_job_flow(flow)
  status_token = _status_token(job_status)
  if status_token in _JOB_NON_FAILURE_TERMINAL_STATUSES:
    snapshot['failedKey'] = ''
    snapshot['activeKey'] = 'success'
    snapshot['completed']['success'] = True
    snapshot['finishedAt'] = snapshot.get('finishedAt') or finished_at or snapshot.get('updatedAt')
  elif status_token in _JOB_FAILURE_STATUSES:
    active_key = str(snapshot.get('activeKey') or '').strip().lower()
    if not snapshot.get('failedKey') and active_key in _FLOW_KEYS:
      snapshot['failedKey'] = active_key
    snapshot['activeKey'] = ''
    snapshot['finishedAt'] = snapshot.get('finishedAt') or finished_at or snapshot.get('updatedAt')
  return snapshot


def _candidate_int(value: Any) -> Optional[int]:
  if value is None or value == '':
    return None
  try:
    return int(value)
  except (TypeError, ValueError):
    try:
      numeric = float(value)
    except (TypeError, ValueError):
      return None
    if math.isnan(numeric) or math.isinf(numeric):
      return None
    return int(numeric)


def _first_int(*values: Any) -> Optional[int]:
  for value in values:
    parsed = _candidate_int(value)
    if parsed is not None:
      return parsed
  return None


def _max_int(*values: Any) -> Optional[int]:
  candidates = [candidate for candidate in (_candidate_int(value) for value in values) if candidate is not None]
  return max(candidates) if candidates else None


def _positive_int(*values: Any) -> Optional[int]:
  candidates = [candidate for candidate in (_candidate_int(value) for value in values) if candidate is not None and candidate > 0]
  return max(candidates) if candidates else None


def _mcap_persisted_row_count(payload: Optional[Dict[str, Any]]) -> int:
  source = payload if isinstance(payload, dict) else {}
  summary = source.get('summary') if isinstance(source.get('summary'), dict) else {}
  db_verification = source.get('dbVerification') if isinstance(source.get('dbVerification'), dict) else {}
  return _positive_int(
    summary.get('insertedRows'),
    summary.get('inserted_rows'),
    summary.get('successRows'),
    summary.get('success_rows'),
    summary.get('fileRows'),
    summary.get('file_rows'),
    summary.get('totalRows'),
    summary.get('total_rows'),
    db_verification.get('rowCountAfter'),
    db_verification.get('row_count_after'),
  ) or 0


def _job_status_token(status: Any) -> str:
  return _status_token(status)


def _job_status_for_run_row(status: Any) -> str:
  token = _status_token(status)
  if not token:
    return 'IDLE'
  if token in _JOB_ACTIVE_STATUSES:
    return 'RUNNING'
  return token


def _request_signature_payload(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
  request = _clone_request_payload(payload)
  range_token = _normalize_history_range(request.get('range') or request.get('dateRange') or request.get('date_range'))
  normalized = {
    'tradeDate': request.get('tradeDate') or request.get('trade_date') or '',
    'startDate': request.get('startDate') or request.get('start_date') or '',
    'endDate': request.get('endDate') or request.get('end_date') or '',
    'range': range_token or '',
    'eqOnly': bool(_coerce_bool(request.get('eqOnly'), _EQ_ONLY_DEFAULT)),
    'jobMode': _parse_job_mode(request),
    'autoInsertAfterDownload': bool(_coerce_bool(request.get('autoInsertAfterDownload'), False)),
    'allowMarketHoliday': bool(_allow_market_date_override(request)),
    'enrichLimit': _candidate_int(request.get('enrichLimit') or request.get('enrich_limit')),
    'symbols': [],
    'pipelineType': str(request.get('pipelineType') or 'market-cap').strip().lower(),
  }
  symbols = request.get('symbols')
  if isinstance(symbols, list):
    cleaned = [str(item).strip().upper() for item in symbols if str(item).strip()]
  else:
    cleaned = [str(item).strip().upper() for item in str(symbols or '').split(',') if str(item).strip()]
  normalized['symbols'] = sorted(dict.fromkeys(cleaned))
  return normalized


def _logical_dataset_key(payload: Optional[Dict[str, Any]]) -> str:
  encoded = json.dumps(_request_signature_payload(payload), sort_keys=True, separators=(',', ':'), default=_json_default)
  return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def _job_request_metadata(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
  request = _request_signature_payload(payload)
  request['logicalDatasetKey'] = _logical_dataset_key(request)
  return request


def _request_mode_from_payload(payload: Optional[Dict[str, Any]]) -> str:
  source = payload if isinstance(payload, dict) else {}
  mode = str(
    source.get('mode')
    or source.get('sourceMode')
    or source.get('source_mode')
    or source.get('runMode')
    or source.get('run_mode')
    or ''
  ).strip().upper()
  if mode in {'MANUAL', 'AUTOMATION'}:
    return mode
  job_mode = str(source.get('jobMode') or source.get('job_mode') or '').strip().lower()
  if job_mode == 'pipeline' or _coerce_bool(source.get('automation'), False):
    return 'AUTOMATION'
  stage = str(source.get('stage') or '').strip().lower()
  if stage in {'download', 'validate', 'process'}:
    return 'MANUAL'
  return 'MANUAL'


def _calculate_trade_date_run_mode_stats(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
  manual_runs = 0
  automation_runs = 0
  for row in rows or []:
    status = _status_token(row.get('status'))
    if status not in {'SUCCESS', 'COMPLETED', 'ALREADY_EXISTS', 'NO_ACTION', 'SKIPPED'}:
      continue
    request_payload = _safe_json_payload(row.get('request_json'))
    if _request_mode_from_payload(request_payload) == 'AUTOMATION':
      automation_runs += 1
    else:
      manual_runs += 1
  return {
    'manual_runs': manual_runs,
    'auto_runs': automation_runs,
    'manual_flag': 'Y' if manual_runs > 0 else 'N',
    'automation_flag': 'Y' if automation_runs > 0 else 'N',
  }


def _load_trade_date_run_mode_stats(cur: Any, runs_table_sql: str, trade_date: dt.date) -> Dict[str, Any]:
  cur.execute(
    f'''SELECT REQUEST_JSON, STATUS
          FROM {runs_table_sql}
         WHERE TRADE_DATE = :trade_date''',
    {'trade_date': trade_date},
  )
  rows = [_row_to_dict(cur, row) for row in (cur.fetchall() or [])]
  return _calculate_trade_date_run_mode_stats(rows)


def _file_checksum(path: Path) -> str:
  digest = hashlib.sha256()
  with path.open('rb') as handle:
    for chunk in iter(lambda: handle.read(65536), b''):
      if not chunk:
        break
      digest.update(chunk)
  return digest.hexdigest()


def _fetch_persisted_run_rows(run_type: Optional[str] = None) -> List[Dict[str, Any]]:
  conn = _acquire_connection()
  try:
    ensure_runtime(conn)
    with conn.cursor() as cur:
      params: Dict[str, Any] = {}
      where_sql = ''
      if run_type:
        where_sql = 'WHERE RUN_TYPE = :run_type'
        params['run_type'] = run_type
      cur.execute(
        f'''SELECT {_RUN_ROW_SELECT_SQL}
              FROM {_RUNS_TABLE_SQL}
              {where_sql}
          ORDER BY STARTED_TS DESC''',
        params,
      )
      return [_row_to_dict(cur, row) for row in (cur.fetchall() or [])]
  finally:
    conn.close()


def _find_persisted_run_by_identity(payload: Optional[Dict[str, Any]], *, run_type: Optional[str] = None, statuses: Optional[Sequence[str]] = None) -> Optional[Dict[str, Any]]:
  logical_key = _logical_dataset_key(payload)
  status_filter = {_status_token(status) for status in statuses} if statuses else None
  for row in _fetch_persisted_run_rows(run_type=run_type):
    request_payload = _safe_json_payload(row.get('request_json'))
    candidate_key = str(request_payload.get('logicalDatasetKey') or _logical_dataset_key(request_payload) or '').strip()
    if candidate_key != logical_key:
      continue
    if status_filter and _status_token(row.get('status')) not in status_filter:
      continue
    return row
  return None


def _request_job_mode(payload: Optional[Dict[str, Any]]) -> str:
  raw = str((payload or {}).get('jobMode') or (payload or {}).get('job_mode') or '').strip().lower()
  return 'download' if raw in {'download', 'download-only', 'download_only'} else 'pipeline'


def _request_pipeline_type(payload: Optional[Dict[str, Any]], default: str) -> str:
  raw = str((payload or {}).get('pipelineType') or '').strip().upper()
  return raw or default


def _flow_stage_statuses(flow: Optional[Dict[str, Any]], job_status: Any) -> Dict[str, str]:
  snapshot = _serialize_job_flow(flow)
  active_key = str(snapshot.get('activeKey') or '').strip().lower()
  failed_key = str(snapshot.get('failedKey') or '').strip().lower()
  durations = snapshot.get('durationsMs') or {}
  completed = snapshot.get('completed') or {}
  statuses: Dict[str, str] = {}
  for key in _FLOW_KEYS:
    if failed_key == key:
      statuses[key] = 'FAILED'
    elif bool(completed.get(key)):
      statuses[key] = 'COMPLETED'
    elif active_key == key:
      statuses[key] = 'STARTED' if int(durations.get(key) or 0) <= 0 else 'WORKING'
    else:
      statuses[key] = 'NOT_STARTED'
  if _is_job_terminal_status(job_status) and not _is_job_failure_status(job_status):
    statuses['success'] = 'COMPLETED'
  return statuses


def _flow_current_stage(flow: Optional[Dict[str, Any]], job_status: Any) -> str:
  snapshot = _serialize_job_flow(flow)
  failed_key = str(snapshot.get('failedKey') or '').strip().lower()
  if failed_key in _FLOW_KEYS:
    return failed_key
  active_key = str(snapshot.get('activeKey') or '').strip().lower()
  if active_key in _FLOW_KEYS:
    return active_key
  if _is_job_terminal_status(job_status) and not _is_job_failure_status(job_status) and bool((snapshot.get('completed') or {}).get('success')):
    return 'success'
  return ''


def _derive_job_counts(payload: Optional[Dict[str, Any]]) -> Dict[str, Optional[int]]:
  source = payload if isinstance(payload, dict) else {}
  result = source.get('result') if isinstance(source.get('result'), dict) else source
  inspection = result.get('inspection') if isinstance(result.get('inspection'), dict) else {}
  load = result.get('load') if isinstance(result.get('load'), dict) else {}
  enrichment = result.get('enrichment') if isinstance(result.get('enrichment'), dict) else {}
  summary = result.get('summary') if isinstance(result.get('summary'), dict) else {}
  explicit_counts = result.get('counts') if isinstance(result.get('counts'), dict) else {}
  symbol_source = source.get('symbolSource') if isinstance(source.get('symbolSource'), dict) else {}
  progress = source.get('progress') if isinstance(source.get('progress'), dict) else {}
  parse_error_rows = _first_int(inspection.get('parseErrorRows'))
  skipped_rows = _first_int(explicit_counts.get('skippedRows'), inspection.get('skippedRows'), load.get('skippedCount'))
  duplicate_rows = _first_int(explicit_counts.get('duplicateRows'), inspection.get('duplicateRows'), load.get('duplicateCount'), load.get('alreadyLoadedCount'))
  invalid_rows = _first_int(explicit_counts.get('invalidRows'), parse_error_rows, load.get('failureCount'))
  failed_rows = _first_int(explicit_counts.get('failedRows'), load.get('failureCount'), enrichment.get('failureCount'), summary.get('failureRows'))
  already_loaded = bool(load.get('alreadyLoaded') or inspection.get('alreadyLoaded'))
  persisted_rows = _mcap_persisted_row_count(result)
  can_reconcile_persisted_rows = (
    persisted_rows
    if persisted_rows > 0
    and not already_loaded
    and int(failed_rows or 0) <= 0
    and int(invalid_rows or 0) <= 0
    and int(skipped_rows or 0) <= 0
    and int(duplicate_rows or 0) <= 0
    else 0
  )
  input_rows = _first_int(explicit_counts.get('expectedRows'), inspection.get('inputRows'), load.get('inputRows'), summary.get('fileRows'), summary.get('totalRows'))
  if (input_rows is None or input_rows <= 0) and can_reconcile_persisted_rows > 0:
    input_rows = can_reconcile_persisted_rows
  valid_rows = _first_int(explicit_counts.get('validRows'), inspection.get('matchedRows'), load.get('loadedCount'))
  if (valid_rows is None or valid_rows <= 0) and can_reconcile_persisted_rows > 0:
    valid_rows = can_reconcile_persisted_rows
  inserted_rows = _first_int(explicit_counts.get('insertedRows'), load.get('loadedCount'))
  if (inserted_rows is None or inserted_rows <= 0) and can_reconcile_persisted_rows > 0:
    inserted_rows = can_reconcile_persisted_rows
  warning_rows = max(0, int(duplicate_rows or 0) + int(skipped_rows or 0))
  quote_success_rows = _first_int(explicit_counts.get('quoteSuccessRows'), enrichment.get('successCount'), summary.get('quoteRows'))
  quote_failed_rows = _first_int(explicit_counts.get('quoteFailedRows'), enrichment.get('failureCount'))
  quote_skipped_rows = _first_int(explicit_counts.get('quoteSkippedRows'), enrichment.get('skippedCount'))
  total_symbols = _first_int(
    _positive_int(explicit_counts.get('totalSymbols')),
    inspection.get('matchedSymbolsCount'),
    inspection.get('symbolsCount'),
    summary.get('distinctSymbols'),
    symbol_source.get('count'),
    progress.get('total'),
    enrichment.get('requested'),
    load.get('loadedCount'),
  )
  total_downloaded = _first_int(
    _positive_int(explicit_counts.get('totalDownloaded')),
    inspection.get('inputRows'),
    load.get('inputRows'),
    summary.get('fileRows'),
    summary.get('totalRows'),
    progress.get('current') if _request_job_mode(source.get('request')) == 'download' else None,
  )
  total_validated = _first_int(
    _positive_int(explicit_counts.get('totalValidated')),
    inspection.get('matchedRows'),
    inspection.get('matchedSymbolsCount'),
    load.get('inputRows'),
    summary.get('fileRows'),
    summary.get('totalRows'),
  )
  total_processed = _first_int(
    _positive_int(explicit_counts.get('totalProcessed')),
    inserted_rows if int(inserted_rows or 0) > 0 else None,
    enrichment.get('processed'),
    load.get('loadedCount'),
    summary.get('quoteRows'),
    summary.get('ffmcRows'),
    summary.get('deliveryRows'),
    progress.get('current'),
  )
  total_inserted = _first_int(
    _positive_int(explicit_counts.get('totalInserted')),
    inserted_rows if int(inserted_rows or 0) > 0 else None,
    load.get('loadedCount'),
    summary.get('quoteRows'),
    summary.get('ffmcRows'),
    summary.get('deliveryRows'),
    summary.get('totalRows'),
  )
  total_failed = _max_int(
    explicit_counts.get('totalFailed'),
    load.get('failureCount'),
    enrichment.get('failureCount'),
    summary.get('failureRows'),
  )
  total_skipped = _max_int(
    explicit_counts.get('totalSkipped'),
    load.get('skippedCount'),
    load.get('universeSkippedCount'),
    enrichment.get('skippedCount'),
    summary.get('skippedRows'),
    inspection.get('universeSkippedRows'),
  )
  return {
    'expectedRows': input_rows,
    'parsedRows': max(0, int(input_rows or 0) - int(parse_error_rows or 0)) if input_rows is not None else None,
    'validRows': valid_rows,
    'invalidRows': invalid_rows,
    'insertedRows': inserted_rows,
    'skippedRows': skipped_rows,
    'duplicateRows': duplicate_rows,
    'failedRows': failed_rows,
    'warningCount': warning_rows,
    'quoteSuccessRows': quote_success_rows,
    'quoteFailedRows': quote_failed_rows,
    'quoteSkippedRows': quote_skipped_rows,
    'totalSymbols': total_symbols,
    'totalDownloaded': total_downloaded,
    'totalValidated': total_validated,
    'totalProcessed': total_processed,
    'totalInserted': total_inserted,
    'totalFailed': total_failed,
    'totalSkipped': total_skipped,
  }


def _final_status_from_result(result: Optional[Dict[str, Any]]) -> str:
  payload = result if isinstance(result, dict) else {}
  status_token = _status_token(payload.get('status'))
  if status_token in _JOB_TERMINAL_STATUSES and status_token != 'PARTIAL':
    return status_token
  if payload.get('skippedUnavailable'):
    return 'SKIPPED'
  inspection = payload.get('inspection') if isinstance(payload.get('inspection'), dict) else {}
  load = payload.get('load') if isinstance(payload.get('load'), dict) else {}
  counts = _derive_job_counts({'result': payload})
  valid_rows = int(counts.get('validRows') or 0)
  parsed_rows = int(counts.get('parsedRows') or 0)
  inserted_rows = int(counts.get('insertedRows') or 0)
  invalid_rows = int(counts.get('invalidRows') or 0)
  skipped_rows = int(counts.get('skippedRows') or 0)
  duplicate_rows = int(counts.get('duplicateRows') or 0)
  failed_rows = int(counts.get('failedRows') or 0)
  already_loaded = bool(load.get('alreadyLoaded') or inspection.get('alreadyLoaded'))
  has_validation_payload = bool(inspection or load)
  if not payload.get('ok', True):
    if inserted_rows <= 0 and (already_loaded or duplicate_rows > 0 or (skipped_rows > 0 and invalid_rows <= 0)):
      if already_loaded or duplicate_rows > 0:
        return 'ALREADY_EXISTS'
      if skipped_rows > 0 and invalid_rows <= 0:
        return 'NO_ACTION'
    return 'FAILED'
  if inserted_rows <= 0:
    if already_loaded or duplicate_rows > 0:
      return 'ALREADY_EXISTS'
    if has_validation_payload and parsed_rows <= 0:
      return 'FAILED'
    if invalid_rows > 0:
      return 'FAILED'
    if skipped_rows > 0:
      return 'NO_ACTION'
    return 'NO_ACTION'
  if failed_rows > 0 or invalid_rows > 0 or duplicate_rows > 0 or skipped_rows > 0:
    return 'PARTIAL'
  if valid_rows > 0 and inserted_rows >= valid_rows:
    return 'SUCCESS'
  return 'SUCCESS'


def _final_status_message(status: str, result: Optional[Dict[str, Any]] = None) -> str:
  payload = result if isinstance(result, dict) else {}
  counts = _derive_job_counts({'result': payload})
  request = payload.get('request') if isinstance(payload.get('request'), dict) else {}
  trade_date = str(payload.get('tradeDate') or request.get('tradeDate') or '').strip()
  date_label = f' for {trade_date}' if trade_date else ''
  inserted = int(counts.get('insertedRows') or 0)
  valid = int(counts.get('validRows') or 0)
  duplicates = int(counts.get('duplicateRows') or 0)
  skipped = int(counts.get('skippedRows') or 0)
  failed = int(counts.get('failedRows') or 0)
  invalid = int(counts.get('invalidRows') or 0)
  if status == 'SUCCESS':
    return f'NSE MCAP ingestion completed successfully{date_label}.'
  if status == 'PARTIAL':
    return f'NSE MCAP ingestion completed with partial results{date_label}: inserted={inserted}, valid={valid}, duplicates={duplicates}, skipped={skipped}, invalid={invalid}, failed={failed}.'
  if status in {'ALREADY_EXISTS', 'SKIPPED'}:
    return f'NSE MCAP data already exists{date_label}; no new rows were inserted.'
  if status == 'NO_ACTION':
    return f'No actionable NSE MCAP rows were found{date_label}.'
  if status == 'TIMED_OUT':
    return f'NSE MCAP job timed out after {_JOB_TIMEOUT_SEC} seconds{date_label}.'
  if status == 'CANCELLED':
    return f'NSE MCAP job was cancelled{date_label}.'
  return str(payload.get('message') or 'NSE MCAP job failed.').strip() or 'NSE MCAP job failed.'


def _normalize_result_status(result: Dict[str, Any]) -> Dict[str, Any]:
  normalized = dict(result or {})
  status = _final_status_from_result(normalized)
  normalized['status'] = status
  normalized['done'] = _is_job_terminal_status(status)
  normalized['ok'] = status not in _JOB_FAILURE_STATUSES and status != 'FAILED'
  normalized['counts'] = _derive_job_counts({'result': normalized})
  normalized['message'] = _final_status_message(status, normalized)
  if status in _JOB_FAILURE_STATUSES or status == 'FAILED':
    normalized['errorMessage'] = normalized.get('errorMessage') or normalized['message']
  return normalized


def _augment_job_payload(payload: Dict[str, Any], *, pipeline_type: str) -> Dict[str, Any]:
  enriched = dict(payload or {})
  enriched['pipelineType'] = pipeline_type
  enriched['jobMode'] = _request_job_mode(enriched.get('request'))
  enriched['status'] = _job_status_token(enriched.get('status'))
  enriched['stageStatus'] = _flow_stage_statuses(enriched.get('flow'), enriched.get('status'))
  enriched['currentStage'] = _flow_current_stage(enriched.get('flow'), enriched.get('status'))
  enriched['counts'] = _derive_job_counts(enriched)
  if 'done' not in enriched:
    enriched['done'] = _is_job_terminal_status(enriched.get('status'))
  enriched['ok'] = bool(enriched.get('ok', not _is_job_failure_status(enriched.get('status'))))
  if not enriched.get('errorMessage') and _is_job_failure_status(enriched.get('status')):
    enriched['errorMessage'] = str(
      enriched.get('message')
      or ((enriched.get('result') or {}).get('error') if isinstance(enriched.get('result'), dict) else '')
      or ''
    )
  return enriched


def _parse_flow_marker(line: str) -> Optional[Tuple[str, str]]:
  match = _FLOW_MARKER_RE.match(str(line or '').strip())
  if not match:
    return None
  return match.group('stage').lower(), str(match.group('detail') or '').strip()


def _row_to_dict(cur, row: Sequence[Any]) -> Dict[str, Any]:
  cols = [str(col[0]).lower() for col in (cur.description or []) if col and col[0]]
  out: Dict[str, Any] = {}
  for idx, key in enumerate(cols):
    value = row[idx]
    if isinstance(value, Decimal):
      out[key] = float(value)
    elif isinstance(value, dt.datetime):
      out[key] = value.strftime('%Y-%m-%d %H:%M:%S')
    elif isinstance(value, dt.date):
      out[key] = value.strftime('%Y-%m-%d')
    else:
      out[key] = value
  return out


def _non_negative_int(value: Any) -> int:
  try:
    numeric = int(Decimal(str(value)))
  except Exception:
    return 0
  return max(0, numeric)


def _first_present(*values: Any) -> Any:
  for value in values:
    if value is not None and value != '':
      return value
  return None


def _display_date_only(value: Any) -> Optional[str]:
  if value in (None, ''):
    return None
  if isinstance(value, dt.datetime):
    return value.strftime('%d-%m-%Y')
  if isinstance(value, dt.date):
    return value.strftime('%d-%m-%Y')
  text = str(value or '').strip()
  if not text:
    return None
  iso = re.match(r'^(\d{4})-(\d{2})-(\d{2})(?:[T\s].*)?$', text)
  if iso:
    return f'{iso.group(3)}-{iso.group(2)}-{iso.group(1)}'
  legacy = re.match(r'^(\d{2})-(\d{2})-(\d{4})(?:\s+\d{2}:\d{2}(?::\d{2})?)?$', text)
  if legacy:
    return f'{legacy.group(1)}-{legacy.group(2)}-{legacy.group(3)}'
  return text


def _apply_insertion_summary_metadata(summary: Dict[str, Any]) -> Dict[str, Any]:
  if not isinstance(summary, dict):
    return summary
  inserted_rows = _non_negative_int(_first_present(summary.get('insertedRows'), summary.get('inserted_rows'), summary.get('successRows'), summary.get('success_rows')))
  manual_rows = _non_negative_int(_first_present(summary.get('manualRows'), summary.get('manual_rows')))
  automation_rows = _non_negative_int(_first_present(summary.get('automationRows'), summary.get('automation_rows')))
  manual_flag = 'Y' if manual_rows > 0 else 'N'
  automation_flag = 'Y' if automation_rows > 0 else 'N'
  summary.update({
    'manualRows': manual_rows,
    'manual_rows': manual_rows,
    'manualFlag': manual_flag,
    'manual_flag': manual_flag,
    'automationRows': automation_rows,
    'automation_rows': automation_rows,
    'automationFlag': automation_flag,
    'automation_flag': automation_flag,
    'insertedRows': inserted_rows,
    'inserted_rows': inserted_rows,
    'insertionSource': 'UNKNOWN',
    'insertion_source': 'UNKNOWN',
  })
  return summary


def _apply_latest_row_insertion_metadata(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
  decorated: List[Dict[str, Any]] = []
  for item in rows or []:
    row = dict(item or {})
    trade_date_value = (
      row.get('trade_date')
      or row.get('TRADE_DATE')
      or row.get('tradeDate')
      or row.get('fetched_timestamp')
      or row.get('fetchedTimestamp')
      or row.get('fetch_ts')
    )
    fetched_timestamp = _display_date_only(trade_date_value)
    status = str(row.get('status') or row.get('fetch_status') or row.get('fetchStatus') or '').strip().upper()
    insertion_source = str(
      row.get('insertion_source')
      or row.get('insertionSource')
      or row.get('source_name')
      or row.get('sourceName')
      or row.get('source')
      or 'UNKNOWN'
    ).strip().upper() or 'UNKNOWN'
    inserted_rows = row.get('inserted_rows') if 'inserted_rows' in row else row.get('insertedRows')
    row.setdefault('fetched_timestamp', fetched_timestamp)
    row.setdefault('fetchedTimestamp', fetched_timestamp)
    row.setdefault('trade_date', trade_date_value)
    row.setdefault('TRADE_DATE', trade_date_value)
    row.setdefault('tradeDate', trade_date_value)
    if status:
      row['status'] = status
      row['fetchStatus'] = status
    row['insertion_source'] = insertion_source
    row['insertionSource'] = insertion_source
    row['inserted_rows'] = inserted_rows if inserted_rows not in ('', None) else None
    row['insertedRows'] = row['inserted_rows']
    decorated.append(row)
  return decorated


def _parse_date(value: Any, field_name: str = 'tradeDate') -> dt.date:
  if isinstance(value, dt.datetime):
    return value.date()
  if isinstance(value, dt.date):
    return value
  text = str(value or '').strip()
  if not text:
    raise ValueError(f'{field_name} is required.')
  normalized = text.replace('Z', '+00:00')
  for candidate in (normalized, normalized.split('T', 1)[0], normalized.split(' ', 1)[0]):
    try:
      return dt.datetime.fromisoformat(candidate).date()
    except ValueError:
      continue
  for fmt in ('%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%d-%m-%Y', '%d-%b-%Y', '%d-%b-%y', '%d%m%Y'):
    try:
      return dt.datetime.strptime(text, fmt).date()
    except ValueError:
      continue
  raise ValueError(f'Invalid {field_name}. Expected YYYY-MM-DD.')


def _coerce_bool(value: Any, default: bool = False) -> bool:
  if value is None:
    return default
  if isinstance(value, bool):
    return value
  if isinstance(value, (int, float, Decimal)):
    return bool(value)
  text = str(value).strip().lower()
  if not text:
    return default
  if text in {'1', 'true', 'yes', 'y', 'on'}:
    return True
  if text in {'0', 'false', 'no', 'n', 'off'}:
    return False
  return default


def _allow_market_date_override(payload: Optional[Dict[str, Any]]) -> bool:
  source = payload if isinstance(payload, dict) else {}
  return _coerce_bool(
    source.get('allowMarketHoliday')
    if source.get('allowMarketHoliday') is not None else
    source.get('allow_market_holiday')
    if source.get('allow_market_holiday') is not None else
    source.get('allowOverride')
    if source.get('allowOverride') is not None else
    source.get('allow_override'),
    False,
  )


def _business_date(base_date: Optional[dt.date] = None) -> dt.date:
  return market_calendar.get_previous_market_working_day(base_date or dt.date.today())


def _iso_date(value: Any) -> str:
  return _parse_date(value, 'tradeDate').strftime('%Y-%m-%d')


def _display_date(value: Any) -> str:
  return _parse_date(value, 'tradeDate').strftime('%d-%m-%Y')


def _date_list_iso(values: Sequence[Any]) -> List[str]:
  return [_iso_date(value) for value in values]


def _fetch_distinct_trade_dates_for_year(conn: Any, table_sql: str, year: int) -> List[dt.date]:
  table_name = _safe_ident(table_sql)
  start_date = dt.date(int(year), 1, 1)
  end_date = dt.date(int(year) + 1, 1, 1)
  with conn.cursor() as cur:
    cur.execute(
      f'''SELECT DISTINCT TRADE_DATE
            FROM {table_name}
           WHERE TRADE_DATE >= :start_date
             AND TRADE_DATE < :end_date
           ORDER BY TRADE_DATE''',
      {'start_date': start_date, 'end_date': end_date},
    )
    dates: List[dt.date] = []
    for row in (cur.fetchall() or []):
      value = row[0] if isinstance(row, (list, tuple)) else row
      if value is None:
        continue
      dates.append(_parse_date(value, 'tradeDate'))
    return sorted(set(dates))


def build_trading_day_verification(
  conn: Any,
  table_sql: str,
  page_name: str,
  *,
  year: Optional[int] = None,
  as_of_date: Optional[dt.date] = None,
) -> Dict[str, Any]:
  current_date = as_of_date or dt.date.today()
  target_year = int(year or current_date.year)
  actual_dates = _fetch_distinct_trade_dates_for_year(conn, table_sql, target_year)
  verification = market_calendar.get_trading_day_verification(
    target_year,
    actual_dates,
    current_date=current_date,
  )
  missing_dates = _date_list_iso(verification.get('missing_trading_dates') or [])
  future_pending_dates = _date_list_iso(verification.get('future_pending_dates') or [])
  actual_trading_dates = _date_list_iso(verification.get('actual_trading_dates') or [])
  expected_trading_dates = _date_list_iso(verification.get('trading_dates') or [])
  invalid_non_trading_dates = _date_list_iso(verification.get('invalid_non_trading_dates') or [])
  status_text = str(verification.get('verification_status') or 'MISSING').upper()
  last_verified_at = dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
  row = {
    'S_NO': 1,
    'sNo': 1,
    'pageName': page_name,
    'PAGE_NAME': page_name,
    'year': target_year,
    'YEAR': target_year,
    'NON_TD': int(verification.get('non_trading_days') or 0),
    'TDCY': int(verification.get('trading_days_cy') or 0),
    'TDCRY': int(verification.get('trading_days_remaining_cy') or 0),
    'TDAPT': int(verification.get('trading_days_available_in_table') or 0),
    'TDMD': int(verification.get('trading_days_missing_count') or 0),
    'TDMD_DATES': missing_dates,
    'tdmdDatesText': ', '.join(missing_dates) if missing_dates else '-',
    'STATUS': status_text,
    'verificationStatus': status_text,
    'LAST_VERIFIED_AT': last_verified_at,
    'lastVerifiedAt': last_verified_at,
  }
  return {
    'ok': True,
    'status': 'SUCCESS',
    'page': page_name,
    'pageName': page_name,
    'year': target_year,
    'as_of_date': _iso_date(current_date),
    'asOfDate': _iso_date(current_date),
    'non_trading_days': row['NON_TD'],
    'weekend_count': int(verification.get('weekend_count') or 0),
    'holiday_count': int(verification.get('holiday_count') or 0),
    'special_working_day_count': int(verification.get('special_working_day_count') or 0),
    'trading_days_cy': row['TDCY'],
    'trading_days_completed_cy': int(verification.get('trading_days_completed_cy') or 0),
    'trading_days_remaining_cy': row['TDCRY'],
    'trading_days_available_in_table': row['TDAPT'],
    'trading_days_missing_count': row['TDMD'],
    'historical_missing_count': int(verification.get('historical_missing_count') or 0),
    'future_pending_count': int(verification.get('future_pending_count') or 0),
    'missing_trading_dates': missing_dates,
    'historical_missing_dates': missing_dates,
    'future_pending_dates': future_pending_dates,
    'trading_dates_present': actual_trading_dates,
    'expected_trading_dates': expected_trading_dates,
    'invalid_non_trading_dates': invalid_non_trading_dates,
    'last_verified_at': last_verified_at,
    'verification_status': status_text,
    'message': 'Trading day verification completed successfully.',
    'cards': [
      {'label': 'Non Trading Days', 'value': row['NON_TD'], 'alias': 'NON_TD'},
      {'label': 'Trading Days CY', 'value': row['TDCY'], 'alias': 'TDCY'},
      {'label': 'Trading Days Remaining CY', 'value': row['TDCRY'], 'alias': 'TDCRY'},
      {'label': 'Available In Table', 'value': row['TDAPT'], 'alias': 'TDAPT'},
      {'label': 'Missing Trading Days', 'value': row['TDMD'], 'alias': 'TDMD', 'status': status_text},
    ],
    'rows': [row],
    **row,
  }


def get_trading_day_verification(year: Optional[int] = None, as_of_date: Optional[dt.date] = None) -> Dict[str, Any]:
  conn = _acquire_connection()
  try:
    return build_trading_day_verification(conn, _TABLE_SQL, 'Market Cap', year=year, as_of_date=as_of_date)
  finally:
    conn.close()


def _normalize_symbol_token(value: Any) -> str:
  token = str(value or '').strip().upper()
  for prefix in ('NSE:', 'BSE:'):
    if token.startswith(prefix):
      token = token[len(prefix):].strip()
      break
  for suffix in (':EQ', '-EQ'):
    if token.endswith(suffix):
      token = token[:-len(suffix)].strip()
      break
  return token


def _normalized_symbol_expr(expr: str) -> str:
  return (
    "UPPER(TRIM(REGEXP_REPLACE("
    "REGEXP_REPLACE("
    "REGEXP_REPLACE(TRIM("
    f"{expr}"
    "), '^(NSE|BSE):', '', 1, 0, 'i'), "
    "'(:EQ|-EQ)$', '', 1, 0, 'i'), "
    "'[[:space:]]+', '')))"
  )


def _first_non_blank(*values: Any) -> Optional[str]:
  for value in values:
    text = str(value or '').strip()
    if text and text != '-':
      return text
  return None


def _iter_trade_dates(start_date: dt.date, end_date: dt.date, *, allow_override: bool = False) -> List[dt.date]:
  if start_date > end_date:
    raise ValueError('startDate must be on or before endDate.')
  dates: List[dt.date] = []
  current = start_date
  while current <= end_date:
    if allow_override or market_calendar.is_market_working_day(current):
      dates.append(current)
    current += dt.timedelta(days=1)
  if not dates:
    raise ValueError('Selected date range does not contain any NSE market working dates.')
  return dates


def _normalize_history_range(value: Any) -> Optional[str]:
  token = str(value or '').strip().upper()
  return token if token in _SUPPORTED_HISTORY_RANGES else None


def _shift_years(base_date: dt.date, years: int) -> dt.date:
  if years <= 0:
    return base_date
  target_year = base_date.year - years
  month = base_date.month
  day = base_date.day
  while True:
    try:
      return dt.date(target_year, month, day)
    except ValueError:
      day -= 1
      if day <= 0:
        return dt.date(target_year, month, 1)


def _history_range_dates(range_value: Any, *, as_of_date: Optional[dt.date] = None) -> Optional[List[dt.date]]:
  token = _normalize_history_range(range_value)
  if not token:
    return None
  years = _SUPPORTED_HISTORY_RANGES[token]
  if years is None:
    return None
  anchor = _business_date(as_of_date)
  start = _shift_years(anchor, years)
  return _iter_trade_dates(start, anchor)


def _parse_trade_dates(
  trade_date_value: Any = None,
  start_date_value: Any = None,
  end_date_value: Any = None,
  default_to_business: bool = True,
  range_value: Any = None,
  allow_override: bool = False,
) -> List[dt.date]:
  trade_date_text = str(trade_date_value or '').strip()
  start_date_text = str(start_date_value or '').strip()
  end_date_text = str(end_date_value or '').strip()
  if start_date_text or end_date_text:
    fallback = trade_date_text or _business_date().strftime('%Y-%m-%d')
    start_date = _parse_date(start_date_text or end_date_text or fallback, 'startDate')
    end_date = _parse_date(end_date_text or start_date_text or fallback, 'endDate')
    return _iter_trade_dates(start_date, end_date, allow_override=allow_override)
  if trade_date_text:
    return [market_calendar.validate_market_date(_parse_date(trade_date_text, 'tradeDate'), allow_override=allow_override)]
  history_dates = _history_range_dates(range_value)
  if history_dates:
    return history_dates
  if default_to_business:
    return [_business_date()]
  raise ValueError('tradeDate is required.')


def _trade_date_label(trade_dates: Sequence[dt.date]) -> str:
  if not trade_dates:
    return '-'
  start_date = trade_dates[0]
  end_date = trade_dates[-1]
  return _display_date(start_date) if start_date == end_date else f'{_display_date(start_date)} to {_display_date(end_date)}'


def _date_context(trade_dates: Sequence[dt.date]) -> Dict[str, Any]:
  if not trade_dates:
    raise ValueError('At least one trade date is required.')
  context: Dict[str, Any] = {
    'tradeDate': _iso_date(trade_dates[-1]),
    'tradeDateLabel': _trade_date_label(trade_dates),
    'dateCount': len(trade_dates),
  }
  if len(trade_dates) > 1:
    context['startDate'] = _iso_date(trade_dates[0])
    context['endDate'] = _iso_date(trade_dates[-1])
  return context


def _apply_run_contract_fields(result: Dict[str, Any], *, page: str, mode: str, stage: str = 'pipeline') -> Dict[str, Any]:
  payload = result if isinstance(result, dict) else {}
  counts = _derive_job_counts({'result': payload})
  inspection = payload.get('inspection') if isinstance(payload.get('inspection'), dict) else {}
  load = payload.get('load') if isinstance(payload.get('load'), dict) else {}
  enrichment = payload.get('enrichment') if isinstance(payload.get('enrichment'), dict) else {}
  trade_date = str(payload.get('tradeDate') or payload.get('trade_date') or '').strip()
  status = _status_token(payload.get('status'))
  if not status or status == 'PARTIAL':
    status = _final_status_from_result(payload)
  parsed_count = _first_int(
    counts.get('parsedRows'),
    counts.get('validRows'),
    inspection.get('matchedRows'),
    inspection.get('matchedSymbolsCount'),
    inspection.get('symbolsCount'),
    load.get('inputRows'),
    enrichment.get('processed'),
  ) or 0
  inserted_count = _first_int(
    counts.get('insertedRows'),
    load.get('loadedCount'),
    enrichment.get('successCount'),
  ) or 0
  skipped_count = _max_int(
    counts.get('skippedRows'),
    load.get('skippedCount'),
    load.get('universeSkippedCount'),
    load.get('alreadyLoadedCount'),
    inspection.get('alreadyLoadedCount'),
    enrichment.get('skippedCount'),
  ) or 0
  failed_count = _max_int(
    counts.get('failedRows'),
    load.get('failureCount'),
    enrichment.get('failureCount'),
    inspection.get('parseErrorRows'),
  ) or 0
  already_loaded = bool(load.get('alreadyLoaded') or inspection.get('alreadyLoaded'))
  db_ok = inserted_count > 0 or (already_loaded and skipped_count > 0)
  terminal_failure = status in _JOB_FAILURE_STATUSES or status == 'FAILED' or bool(payload.get('ok') is False)
  if stage in {'validate', 'process', 'pipeline'} and parsed_count <= 0 and not already_loaded:
    terminal_failure = True
    status = 'FAILED'
  if stage in {'process', 'pipeline'} and inserted_count <= 0 and failed_count > 0 and not already_loaded:
    terminal_failure = True
    status = 'FAILED'
  payload['status'] = status
  payload['page'] = page
  payload['mode'] = mode
  payload['trading_date'] = trade_date
  payload['downloaded'] = bool(payload.get('downloadPath')) or already_loaded
  payload['validated'] = parsed_count > 0 or already_loaded
  payload['processed'] = stage in {'process', 'pipeline'} and (bool(load) or bool(enrichment) or already_loaded)
  payload['db_inserted'] = db_ok
  payload['downloaded_file_count'] = 1 if payload.get('downloadPath') else 0
  payload['parsed_row_count'] = parsed_count
  payload['inserted_row_count'] = inserted_count
  payload['updated_row_count'] = int(payload.get('updated_row_count') or 0)
  payload['skipped_row_count'] = skipped_count
  payload['failed_row_count'] = failed_count
  if terminal_failure:
    payload['ok'] = False
    payload.setdefault('error', str(payload.get('error') or payload.get('message') or 'NSE ingestion failed.'))
  return payload


def _trade_date_metadata(value: Any) -> Dict[str, str]:
  text = str(value or '').strip()
  if not text:
    return {
      'latestTradeDate': '',
      'latest_trade_date': '',
      'tradeDateDisplay': '-',
      'trade_date_display': '-',
    }
  try:
    iso_value = _iso_date(value)
    display_value = _display_date(value)
  except ValueError:
    iso_value = text
    display_value = text
  return {
    'latestTradeDate': iso_value,
    'latest_trade_date': iso_value,
    'tradeDateDisplay': display_value,
    'trade_date_display': display_value,
  }


def _apply_trade_date_metadata(payload: Dict[str, Any], trade_date_value: Any) -> Dict[str, Any]:
  metadata = _trade_date_metadata(trade_date_value)
  payload.update(metadata)
  if metadata['latest_trade_date']:
    payload['tradeDate'] = metadata['latest_trade_date']
    payload['tradeDateLabel'] = metadata['trade_date_display']
  else:
    payload.setdefault('tradeDate', '')
    payload['tradeDateLabel'] = '-'
  summary = payload.get('summary')
  latest_fetch_ts = None
  if isinstance(summary, dict):
    summary.update(metadata)
    if metadata['latest_trade_date']:
      summary.setdefault('tradeDate', metadata['latest_trade_date'])
      summary.setdefault('trade_date', metadata['latest_trade_date'])
    payload['manualRows'] = summary.get('manualRows', summary.get('manual_rows', 0))
    payload['automationRows'] = summary.get('automationRows', summary.get('automation_rows', 0))
    payload['manualFlag'] = summary.get('manualFlag', summary.get('manual_flag', 'N'))
    payload['automationFlag'] = summary.get('automationFlag', summary.get('automation_flag', 'N'))
    payload['insertedRows'] = summary.get('insertedRows', summary.get('inserted_rows', 0))
    payload['successRows'] = summary.get('successRows', summary.get('success_rows', 0))
    payload['failureRows'] = summary.get('failureRows', summary.get('failure_rows', 0))
    payload['skippedRows'] = summary.get('skippedRows', summary.get('skipped_rows', 0))
    latest_fetch_ts = summary.get('latestFetchTs')
  if not latest_fetch_ts:
    latest_fetch_ts = payload.get('latestFetchTs')

  fetched_at_str = '-'
  if latest_fetch_ts:
    if isinstance(latest_fetch_ts, dt.datetime):
      fetched_at_str = latest_fetch_ts.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    elif isinstance(latest_fetch_ts, dt.date):
      fetched_at_str = latest_fetch_ts.strftime('%Y-%m-%d %H:%M:%S.000')
    else:
      text = str(latest_fetch_ts).strip()
      try:
        if 'T' in text or ' ' in text:
          parsed = dt.datetime.fromisoformat(text.replace('Z', '+00:00'))
          fetched_at_str = parsed.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        else:
          fetched_at_str = text
      except Exception:
        fetched_at_str = text

  payload['fetchedAt'] = fetched_at_str
  if isinstance(summary, dict):
    summary['fetchedAt'] = fetched_at_str

  return payload


def _normalize_header(name: str) -> str:
  return _HEADER_RE.sub('', str(name or '').upper())


def _resolve_header(column_map: Dict[str, str], candidates: Sequence[str]) -> Optional[str]:
  for candidate in candidates:
    token = _normalize_header(candidate)
    if token in column_map:
      return column_map[token]
  return None


def _parse_decimal(value: Any) -> Optional[Decimal]:
  if value is None:
    return None
  if isinstance(value, Decimal):
    return value
  if isinstance(value, bool):
    return Decimal(1 if value else 0)
  if isinstance(value, (int, float)):
    if isinstance(value, float) and not math.isfinite(value):
      return None
    return Decimal(str(value))
  text = str(value).replace(',', '').strip()
  if not text:
    return None
  cleaned = _NON_NUMERIC_RE.sub('', text)
  if cleaned in {'', '-', '.', '-.'}:
    return None
  try:
    return Decimal(cleaned)
  except (InvalidOperation, ValueError):
    return None


def _normalize_unit(value: Any, default: str = 'CR') -> str:
  if isinstance(value, dict):
    for key in ('unit', 'units', 'displayUnit'):
      if key in value:
        return _normalize_unit(value.get(key), default)
    return default
  text = re.sub(r'[^A-Z]', '', str(value or '').upper())
  if not text:
    return default
  return _UNIT_ALIASES.get(text, text)


def _to_crores(value: Any, unit: str) -> Optional[Decimal]:
  parsed = _parse_decimal(value)
  if parsed is None:
    return None
  factor = _UNIT_FACTORS.get((unit or '').strip().upper())
  if factor is None:
    raise ValueError(f'Unsupported market cap unit: {unit}')
  return (parsed * factor).quantize(Decimal('0.000001'))


def _find_value(node: Any, keys: set[str]) -> Any:
  if isinstance(node, dict):
    for key, value in node.items():
      token = re.sub(r'[^a-z0-9]', '', str(key).lower())
      if token in keys and value not in (None, '', [], {}):
        return value
      found = _find_value(value, keys)
      if found not in (None, '', [], {}):
        return found
  elif isinstance(node, list):
    for item in node:
      found = _find_value(item, keys)
      if found not in (None, '', [], {}):
        return found
  return None


def _sleep_jitter(min_sleep: float = _MIN_SLEEP, max_sleep: float = _MAX_SLEEP) -> None:
  if max_sleep <= 0:
    return
  time.sleep(random.uniform(min_sleep, max_sleep))


def _download_dir() -> Path:
  _DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
  return _DOWNLOAD_DIR


def _download_hints_path() -> Path:
  return _download_dir() / _DOWNLOAD_HINTS_FILE


def _read_download_hints() -> Dict[str, Any]:
  path = _download_hints_path()
  if not path.exists() or not path.is_file():
    return {}
  try:
    payload = json.loads(path.read_text(encoding='utf-8'))
  except Exception:
    logger.warning('NSE MCAP download hints are unreadable: %s', path)
    return {}
  return payload if isinstance(payload, dict) else {}


def _write_download_hints(**updates: Any) -> None:
  if not updates:
    return
  path = _download_hints_path()
  with _DOWNLOAD_HINTS_LOCK:
    payload = _read_download_hints()
    for key, value in updates.items():
      if value not in (None, ''):
        payload[key] = value
    payload['updatedAt'] = dt.datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'
    path.write_text(json.dumps(payload, ensure_ascii=True, separators=(',', ':')), encoding='utf-8')


def _load_nifty500_symbol_set(*, require_file: bool = True) -> set[str]:
  try:
    symbols = nifty500_svc.load_existing_symbols(require_file=require_file)
  except FileNotFoundError as exc:
    raise ValueError(str(exc)) from exc
  return {str(item or '').strip().upper() for item in symbols if str(item or '').strip()}


def _nifty500_source_path() -> str:
  return str(nifty500_svc.resolve_existing_csv_path())


def _coerce_allowed_symbols(allowed_symbols: Optional[Sequence[str]]) -> Optional[set[str]]:
  if allowed_symbols is None:
    return None
  cleaned = {str(item or '').strip().upper() for item in allowed_symbols if str(item or '').strip()}
  return cleaned or None


def _runtime_filter_symbols() -> Optional[set[str]]:
  if not _FILTER_TO_NIFTY500:
    return None
  return _load_nifty500_symbol_set(require_file=True)


def _table_exists(conn, table_name: str) -> bool:
  owner, name = _split_ident(table_name)
  sql = 'SELECT 1 FROM USER_TABLES WHERE TABLE_NAME = :name'
  binds: Dict[str, Any] = {'name': name}
  if owner:
    sql = 'SELECT 1 FROM ALL_TABLES WHERE OWNER = :owner AND TABLE_NAME = :name'
    binds['owner'] = owner
  with conn.cursor() as cur:
    cur.execute(sql, binds)
    return cur.fetchone() is not None


def _index_exists(conn, index_name: str) -> bool:
  owner, name = _split_ident(index_name)
  sql = 'SELECT 1 FROM USER_INDEXES WHERE INDEX_NAME = :name'
  binds: Dict[str, Any] = {'name': name}
  if owner:
    sql = 'SELECT 1 FROM ALL_INDEXES WHERE OWNER = :owner AND INDEX_NAME = :name'
    binds['owner'] = owner
  with conn.cursor() as cur:
    cur.execute(sql, binds)
    return cur.fetchone() is not None


def _view_exists(conn, view_name: str) -> bool:
  owner, name = _split_ident(view_name)
  sql = 'SELECT 1 FROM USER_VIEWS WHERE VIEW_NAME = :name'
  binds: Dict[str, Any] = {'name': name}
  if owner:
    sql = 'SELECT 1 FROM ALL_VIEWS WHERE OWNER = :owner AND VIEW_NAME = :name'
    binds['owner'] = owner
  with conn.cursor() as cur:
    cur.execute(sql, binds)
    return cur.fetchone() is not None


def _idx_name(table_ident: str, suffix: str) -> str:
  return f"IDX_{_split_ident(table_ident)[1][-18:]}_{suffix}"


def _ck_name(table_ident: str, suffix: str) -> str:
  return f"CK_{_split_ident(table_ident)[1][-18:]}_{suffix}"


def _exec_ddl(conn, ddl: str) -> None:
  with conn.cursor() as cur:
    try:
      cur.execute(ddl)
    except Exception as exc:
      if 'ORA-00955' in str(exc) or 'ORA-01408' in str(exc):
        return
      raise


def ensure_runtime(conn=None) -> Dict[str, Any]:
  global _RUNTIME_READY
  owns_conn = conn is None
  if owns_conn:
    conn = _acquire_connection()
  try:
    with _RUNTIME_LOCK:
      if not _table_exists(conn, _TABLE_SQL):
        _exec_ddl(conn, f'''
          CREATE TABLE {_TABLE_SQL} (
            ID NUMBER GENERATED BY DEFAULT ON NULL AS IDENTITY PRIMARY KEY,
            TRADE_DATE DATE NOT NULL,
            SYMBOL VARCHAR2(50) NOT NULL,
            SOURCE_NAME VARCHAR2(50) NOT NULL,
            SERIES VARCHAR2(10),
            SECURITY_NAME VARCHAR2(300),
            RAW_TOTAL_MCAP NUMBER(24,6),
            RAW_TOTAL_MCAP_UNIT VARCHAR2(30),
            TOTAL_MCAP_CR NUMBER(24,6),
            RAW_FFMC NUMBER(24,6),
            RAW_FFMC_UNIT VARCHAR2(30),
            FFMC_CR NUMBER(24,6),
            RESPONSE_PAYLOAD CLOB,
            FETCH_STATUS VARCHAR2(30) DEFAULT 'SUCCESS' NOT NULL,
            ERROR_MESSAGE VARCHAR2(2000),
            FETCH_TS TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
            CREATED_BY VARCHAR2(128) DEFAULT USER NOT NULL,
            UPDATED_TS TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
            CONSTRAINT UQ_{_split_ident(_TABLE_SQL)[1][-20:]} UNIQUE (TRADE_DATE, SYMBOL, SOURCE_NAME),
            CONSTRAINT {_ck_name(_TABLE_SQL, 'STATUS')} CHECK (FETCH_STATUS IN ('SUCCESS', 'FAILED', 'PARTIAL', 'SKIPPED', 'PARSE_ERROR')),
            CONSTRAINT {_ck_name(_TABLE_SQL, 'PAYLOAD')} CHECK (RESPONSE_PAYLOAD IS JSON OR RESPONSE_PAYLOAD IS NULL)
          ) TABLESPACE CVING_DATA
        ''')
      if not _table_exists(conn, _RUNS_TABLE_SQL):
        _exec_ddl(conn, f'''
          CREATE TABLE {_RUNS_TABLE_SQL} (
            RUN_ID VARCHAR2(36) PRIMARY KEY,
            TRADE_DATE DATE NOT NULL,
            RUN_TYPE VARCHAR2(20) NOT NULL,
            STATUS VARCHAR2(20) NOT NULL,
            REQUEST_JSON CLOB,
            METRICS_JSON CLOB,
            MESSAGE VARCHAR2(4000),
            DOWNLOAD_FILE_PATH VARCHAR2(1000),
            LOGS_CLOB CLOB,
            STARTED_TS TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
            FINISHED_TS TIMESTAMP,
            CREATED_BY VARCHAR2(128) DEFAULT USER NOT NULL,
            CONSTRAINT {_ck_name(_RUNS_TABLE_SQL, 'REQJSON')} CHECK (REQUEST_JSON IS JSON OR REQUEST_JSON IS NULL),
            CONSTRAINT {_ck_name(_RUNS_TABLE_SQL, 'METJSON')} CHECK (METRICS_JSON IS JSON OR METRICS_JSON IS NULL)
          ) TABLESPACE CVING_DATA
        ''')
      for idx_sql in (
        f'CREATE INDEX {_idx_name(_TABLE_SQL, "TRDSRC")} ON {_TABLE_SQL} (TRADE_DATE, SOURCE_NAME, FETCH_STATUS) TABLESPACE CVING_INDEX',
        f'CREATE INDEX {_idx_name(_TABLE_SQL, "SYMDATE")} ON {_TABLE_SQL} (SYMBOL, TRADE_DATE DESC) TABLESPACE CVING_INDEX',
        f'CREATE INDEX {_idx_name(_RUNS_TABLE_SQL, "TRDRUN")} ON {_RUNS_TABLE_SQL} (TRADE_DATE, RUN_TYPE, STATUS) TABLESPACE CVING_INDEX',
        f'CREATE INDEX {_idx_name(_RUNS_TABLE_SQL, "START")} ON {_RUNS_TABLE_SQL} (STARTED_TS DESC) TABLESPACE CVING_INDEX',
      ):
        idx_name = idx_sql.split()[2]
        if not _index_exists(conn, idx_name):
          _exec_ddl(conn, idx_sql)
      if not _view_exists(conn, _LATEST_VIEW_SQL):
        with conn.cursor() as cur:
          cur.execute(f'''
            CREATE OR REPLACE FORCE NONEDITIONABLE VIEW {_LATEST_VIEW_SQL} AS
            SELECT id, trade_date, symbol, source_name, series, security_name,
                   raw_total_mcap, raw_total_mcap_unit, total_mcap_cr,
                   raw_ffmc, raw_ffmc_unit, ffmc_cr, response_payload,
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
      return {'ok': True, 'table': _TABLE_SQL, 'runsTable': _RUNS_TABLE_SQL, 'view': _LATEST_VIEW_SQL, 'downloadDir': str(_download_dir())}
  finally:
    if owns_conn and conn is not None:
      conn.close()


class _HttpClient:
  def __init__(
    self,
    *,
    warmup: bool = False,
    timeout_sec: Optional[int] = None,
    retry_count: Optional[int] = None,
    min_sleep: Optional[float] = None,
    max_sleep: Optional[float] = None,
  ) -> None:
    self._cookie_jar = CookieJar()
    self._opener = build_opener(HTTPCookieProcessor(self._cookie_jar))
    self._warm_urls = (_NSE_BASE, f'{_NSE_BASE}/market-data/live-equity-market', f'{_NSE_BASE}/all-reports')
    self._warmed = False
    self._timeout_sec = max(3, int(timeout_sec if timeout_sec is not None else _TIMEOUT_SEC))
    self._retry_count = max(1, int(retry_count if retry_count is not None else _RETRY_COUNT))
    self._min_sleep = max(0.0, float(min_sleep if min_sleep is not None else _MIN_SLEEP))
    self._max_sleep = max(self._min_sleep, float(max_sleep if max_sleep is not None else _MAX_SLEEP))
    self._import_shared_session(force=False)
    if warmup:
      self._warmup()

  def _headers(self, accept: str) -> Dict[str, str]:
    return {
      'User-Agent': random.choice(_USER_AGENTS),
      'Accept': accept,
      'Accept-Language': 'en-US,en;q=0.9',
      'Referer': _NSE_BASE,
      'Origin': _NSE_BASE,
      'Cache-Control': 'no-cache',
      'Pragma': 'no-cache',
      'Connection': 'keep-alive',
    }

  def _warmup(self, *, force: bool = False) -> None:
    if self._warmed and not force:
      return
    if self._import_shared_session(force=False) and not force:
      return
    should_run = False
    while True:
      with _NSE_SESSION_STATE_LOCK:
        shared_ready = _NSE_SESSION_WARM_UNTIL_TS > time.time() and bool(_NSE_SESSION_COOKIE_SNAPSHOT)
        if shared_ready:
          cookies = list(_NSE_SESSION_COOKIE_SNAPSHOT)
          self._apply_cookie_snapshot(cookies)
          self._warmed = True
          return
        if not _NSE_SESSION_WARM_IN_FLIGHT:
          should_run = True
          globals()['_NSE_SESSION_WARM_IN_FLIGHT'] = True
          break
      time.sleep(0.05)
    try:
      warmed = self._execute_warmup_requests()
      self._warmed = warmed
      if warmed:
        self._publish_shared_session()
    finally:
      if should_run:
        with _NSE_SESSION_STATE_LOCK:
          globals()['_NSE_SESSION_WARM_IN_FLIGHT'] = False

  def _execute_warmup_requests(self) -> bool:
    warmed = False
    for url in self._warm_urls:
      try:
        with self._opener.open(Request(url, headers=self._headers('text/html,*/*')), timeout=self._timeout_sec):
          warmed = True
      except Exception as exc:
        logger.warning('NSE warmup failed url=%s error=%s', url, exc)
    return warmed

  def _cookie_snapshot(self) -> List[Any]:
    return [copy.copy(cookie) for cookie in self._cookie_jar]

  def _apply_cookie_snapshot(self, cookies: Sequence[Any]) -> None:
    for cookie in cookies:
      self._cookie_jar.set_cookie(copy.copy(cookie))

  def _publish_shared_session(self) -> None:
    cookies = self._cookie_snapshot()
    if not cookies:
      return
    with _NSE_SESSION_STATE_LOCK:
      globals()['_NSE_SESSION_COOKIE_SNAPSHOT'] = cookies
      globals()['_NSE_SESSION_WARM_UNTIL_TS'] = time.time() + _NSE_SESSION_WARM_TTL_SEC

  def _import_shared_session(self, *, force: bool) -> bool:
    if self._warmed and not force:
      return False
    with _NSE_SESSION_STATE_LOCK:
      shared_ready = _NSE_SESSION_WARM_UNTIL_TS > time.time() and bool(_NSE_SESSION_COOKIE_SNAPSHOT)
      if not shared_ready:
        return False
      cookies = list(_NSE_SESSION_COOKIE_SNAPSHOT)
    self._apply_cookie_snapshot(cookies)
    self._warmed = True
    return True

  def read(self, url: str, accept: str) -> Tuple[bytes, Dict[str, str]]:
    last_error: Optional[Exception] = None
    for attempt in range(1, self._retry_count + 1):
      _sleep_jitter(self._min_sleep, self._max_sleep)
      try:
        with self._opener.open(Request(url, headers=self._headers(accept)), timeout=self._timeout_sec) as response:
          payload = response.read()
          self._warmed = True
          self._publish_shared_session()
          return payload, {str(k): str(v) for k, v in response.headers.items()}
      except HTTPError as exc:
        code = getattr(exc, 'code', None)
        if code in (401, 403):
          self._warmup(force=True)
          time.sleep(min(1.0, 0.25 * attempt))
          continue
        if code in (429, 500, 502, 503, 504):
          time.sleep(min(6.0, 0.8 * attempt))
          last_error = exc
          continue
        raise
      except URLError as exc:
        last_error = exc
        time.sleep(min(6.0, 0.8 * attempt))
      except Exception as exc:
        last_error = exc
        time.sleep(min(6.0, 0.8 * attempt))
    if last_error is not None:
      raise last_error
    raise RuntimeError(f'Unable to fetch url: {url}')

  def read_text(self, url: str) -> str:
    payload, _headers = self.read(url, 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8')
    try:
      return payload.decode('utf-8')
    except UnicodeDecodeError:
      return payload.decode('latin-1', errors='replace')

  def read_json(self, url: str) -> Dict[str, Any]:
    payload, _headers = self.read(url, 'application/json,text/plain,*/*')
    try:
      return json.loads(payload.decode('utf-8'))
    except UnicodeDecodeError:
      return json.loads(payload.decode('latin-1'))


def _candidate_specs(trade_date: dt.date) -> List[Tuple[str, str]]:
  ddmmyyyy = trade_date.strftime('%d%m%Y')
  month = trade_date.strftime('%b').upper()
  year = trade_date.strftime('%Y')
  specs = [
    ('historical_mcap_lower', f'{_ARCHIVE_BASE}/content/historical/EQUITIES/{year}/{month}/mcap{ddmmyyyy}.csv'),
    ('historical_mcap_upper', f'{_ARCHIVE_BASE}/content/historical/EQUITIES/{year}/{month}/MCAP{ddmmyyyy}.csv'),
  ]
  preferred = str(_read_download_hints().get('preferredCandidate') or '').strip()
  if preferred:
    specs.sort(key=lambda item: (0 if item[0] == preferred else 1, item[0]))
  seen: set[str] = set()
  deduped: List[Tuple[str, str]] = []
  for key, url in specs:
    if url in seen:
      continue
    seen.add(url)
    deduped.append((key, url))
  return deduped


def _hinted_candidate_specs(trade_date: dt.date) -> List[Tuple[str, str]]:
  hints = _read_download_hints()
  last_success_url = str(hints.get('lastSuccessUrl') or '').strip()
  if not last_success_url:
    return []
  year = trade_date.strftime('%Y')
  month = trade_date.strftime('%b').upper()
  ddmmyy = trade_date.strftime('%d%m%y')
  ddmmyyyy = trade_date.strftime('%d%m%Y')
  hinted_url = last_success_url
  changed = False
  replacements = (
    (re.compile(r'(?i)mcap\d{8}\.csv'), f'mcap{ddmmyyyy}.csv'),
    (re.compile(r'(?i)pr\d{6}\.zip'), f'PR{ddmmyy}.zip'),
    (re.compile(r'(?i)/content/historical/EQUITIES/\d{4}/[A-Z]{3}/'), f'/content/historical/EQUITIES/{year}/{month}/'),
  )
  for pattern, replacement in replacements:
    next_url = pattern.sub(replacement, hinted_url)
    if next_url != hinted_url:
      hinted_url = next_url
      changed = True
  if not changed:
    return []
  return [('hint_last_success', hinted_url)]


def _archive_candidate_specs(trade_date: dt.date) -> List[Tuple[str, str]]:
  ddmmyy = trade_date.strftime('%d%m%y')
  month = trade_date.strftime('%b').upper()
  year = trade_date.strftime('%Y')
  specs = [
    ('historical_pr_upper', f'{_ARCHIVE_BASE}/content/historical/EQUITIES/{year}/{month}/PR{ddmmyy}.zip'),
    ('historical_pr_lower', f'{_ARCHIVE_BASE}/content/historical/EQUITIES/{year}/{month}/pr{ddmmyy}.zip'),
    ('equities_bhavcopy_pr', f'{_ARCHIVE_BASE}/content/equities/bhavcopy/pr/PR{ddmmyy}.zip'),
    ('archives_bhavcopy_pr', f'{_ARCHIVE_BASE}/archives/equities/bhavcopy/pr/PR{ddmmyy}.zip'),
  ]
  preferred = str(_read_download_hints().get('preferredCandidate') or '').strip()
  if preferred:
    specs.sort(key=lambda item: (0 if item[0] == preferred else 1, item[0]))
  seen: set[str] = set()
  deduped: List[Tuple[str, str]] = []
  for key, url in specs:
    if url in seen:
      continue
    seen.add(url)
    deduped.append((key, url))
  return deduped


def _extract_discovered_urls(page_url: str, text: str, targets: set[str]) -> List[str]:
  urls: List[str] = []
  seen: set[str] = set()
  fragments = [*_HREF_RE.findall(text), *_TEXT_URL_RE.findall(text), *_FILENAME_CANDIDATE_RE.findall(text)]
  for fragment in fragments:
    token = str(fragment or '').strip().replace('\\/', '/')
    if not token:
      continue
    lower = token.lower()
    if not any(target in lower for target in targets):
      continue
    url = urljoin(page_url, token)
    if url in seen:
      continue
    seen.add(url)
    urls.append(url)
  return urls


def _discovery_pages(trade_date: dt.date, include_archive: bool = False) -> List[str]:
  month = trade_date.strftime('%b').upper()
  year = trade_date.strftime('%Y')
  pages = [
    f'{_ARCHIVE_BASE}/content/historical/EQUITIES/{year}/{month}/',
    f'{_NSE_BASE}/report-detail/eq_security',
    f'{_NSE_BASE}/all-reports',
  ]
  if include_archive:
    pages.extend([
      f'{_ARCHIVE_BASE}/content/equities/bhavcopy/pr/',
      f'{_ARCHIVE_BASE}/archives/equities/bhavcopy/pr/',
    ])
  return pages


def _discover_urls(client: _HttpClient, trade_date: dt.date, line_logger: Optional[Callable[[str], None]] = None, include_archive: bool = False) -> List[str]:
  ddmmyy = trade_date.strftime('%d%m%y')
  ddmmyyyy = trade_date.strftime('%d%m%Y')
  targets = {f'mcap{ddmmyyyy}.csv'}
  if include_archive:
    targets.add(f'pr{ddmmyy}.zip')
  urls: List[str] = []
  if line_logger:
    line_logger('[INFO] Discovering MCAP CSV URLs from official NSE pages...' if not include_archive else '[INFO] Discovering official PR ZIP containers for MCAP extraction...')
  for page_url in _discovery_pages(trade_date, include_archive=include_archive):
    try:
      html = client.read_text(page_url)
    except Exception as exc:
      logger.warning('NSE discovery page failed url=%s error=%s', page_url, exc)
      continue
    matches = _extract_discovered_urls(page_url, html, targets)
    if matches:
      urls.extend(matches)
      if line_logger:
        line_logger(f'[INFO] Discovery matched {len(matches)} candidate url(s) via {page_url}')
  return list(dict.fromkeys(urls))


def _extract_zip(zip_path: Path, trade_date: dt.date) -> Path:
  out_path = _download_dir() / f'mcap{trade_date.strftime("%d%m%Y")}.csv'
  with zipfile.ZipFile(zip_path, 'r') as archive:
    chosen = None
    for member in archive.namelist():
      lower = member.lower()
      if lower.endswith('.csv') and 'mcap' in lower:
        chosen = member
        break
    if chosen is None:
      raise RuntimeError(f'MCAP CSV not found inside archive: {zip_path.name}')
    with archive.open(chosen) as source, out_path.open('wb') as target:
      target.write(source.read())
  return out_path

def _expected_csv_path(trade_date: dt.date) -> Path:
  return _download_dir() / f'mcap{trade_date.strftime("%d%m%Y")}.csv'


def _expected_zip_path(trade_date: dt.date) -> Path:
  return _download_dir() / f'PR{trade_date.strftime("%d%m%y")}.zip'


def _trade_date_from_mcap_csv(csv_path: Path) -> Optional[dt.date]:
  match = _LOCAL_MCAP_CSV_RE.match(csv_path.name or '')
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
      line_logger(f'[INFO] Reusing local MCAP CSV {csv_path}')
    return csv_path

  zip_path = _expected_zip_path(trade_date)
  if zip_path.exists() and zip_path.is_file() and zip_path.stat().st_size > 0:
    if line_logger:
      line_logger(f'[INFO] Reusing local MCAP ZIP {zip_path}')
    return _extract_zip(zip_path, trade_date)

  return None

def download_mcap_csv(trade_date: dt.date, line_logger: Optional[Callable[[str], None]] = None) -> Path:
  ensure_runtime()
  local_path = _reuse_local_download(trade_date, line_logger=line_logger)
  if local_path is not None:
    return local_path
  download_client = _HttpClient(
    warmup=False,
    timeout_sec=_DOWNLOAD_TIMEOUT_SEC,
    retry_count=_DOWNLOAD_RETRY_COUNT,
    min_sleep=_DOWNLOAD_MIN_SLEEP,
    max_sleep=_DOWNLOAD_MAX_SLEEP,
  )
  discovery_client = _HttpClient(
    warmup=False,
    timeout_sec=_DISCOVERY_TIMEOUT_SEC,
    retry_count=_DISCOVERY_RETRY_COUNT,
    min_sleep=_DOWNLOAD_MIN_SLEEP,
    max_sleep=_DOWNLOAD_MAX_SLEEP,
  )
  last_error: Optional[Exception] = None
  attempted: set[str] = set()

  def _download_from_url(url: str, candidate_key: Optional[str] = None, client: Optional[_HttpClient] = None) -> Optional[Path]:
    nonlocal last_error
    try:
      if line_logger:
        if candidate_key and '_pr_' in candidate_key:
          line_logger(f'[INFO] Downloading official PR ZIP container {url}')
        else:
          line_logger(f'[INFO] Downloading {url}')
      payload, headers = (client or download_client).read(url, '*/*')
      ctype = str(headers.get('Content-Type') or headers.get('content-type') or '').lower()
      if url.lower().endswith('.zip') or 'zip' in ctype or payload[:2] == b'PK':
        zip_path = _expected_zip_path(trade_date)
        zip_path.write_bytes(payload)
        path = _extract_zip(zip_path, trade_date)
        hint_updates = {'lastSuccessUrl': url}
        if candidate_key and not candidate_key.startswith('hint_'):
          hint_updates['preferredCandidate'] = candidate_key
        _write_download_hints(**hint_updates)
        return path
      if url.lower().endswith('.csv') or 'csv' in ctype or (b',' in payload[:200] and b'\n' in payload[:500]):
        csv_path = _expected_csv_path(trade_date)
        csv_path.write_bytes(payload)
        hint_updates = {'lastSuccessUrl': url}
        if candidate_key and not candidate_key.startswith('hint_'):
          hint_updates['preferredCandidate'] = candidate_key
        _write_download_hints(**hint_updates)
        return csv_path
      raise RuntimeError(f'Unexpected response type for {url}')
    except Exception as exc:
      last_error = exc
      logger.warning('NSE MCAP download failed url=%s error=%s', url, exc)
      if line_logger:
        line_logger(f'[WARN] Download candidate failed: {url} :: {exc}')
      return None

  for candidate_key, url in _hinted_candidate_specs(trade_date):
    attempted.add(url)
    downloaded = _download_from_url(url, candidate_key=candidate_key)
    if downloaded is not None:
      return downloaded

  for candidate_key, url in _candidate_specs(trade_date):
    attempted.add(url)
    downloaded = _download_from_url(url, candidate_key=candidate_key)
    if downloaded is not None:
      return downloaded

  for candidate_key, url in _archive_candidate_specs(trade_date):
    if url in attempted:
      continue
    attempted.add(url)
    downloaded = _download_from_url(url, candidate_key=candidate_key)
    if downloaded is not None:
      return downloaded

  for url in _discover_urls(discovery_client, trade_date, line_logger=line_logger):
    if url in attempted:
      continue
    attempted.add(url)
    downloaded = _download_from_url(url, client=download_client)
    if downloaded is not None:
      return downloaded

  if line_logger:
    line_logger('[INFO] Direct NSE archive paths failed; falling back to discovery pages for PR ZIP extraction...')

  for url in _discover_urls(discovery_client, trade_date, line_logger=line_logger, include_archive=True):
    if url in attempted:
      continue
    attempted.add(url)
    downloaded = _download_from_url(url, client=download_client)
    if downloaded is not None:
      return downloaded
  raise RuntimeError(f'Unable to download NSE MCAP CSV for {trade_date.isoformat()}: {last_error}')

def _merge_sql() -> str:
  return f"""
    MERGE INTO {_TABLE_SQL} target
    USING (
      SELECT CAST(:id AS NUMBER) id,
             CAST(:trade_date AS DATE) trade_date,
             CAST(:symbol AS VARCHAR2(50)) symbol,
             CAST(:source_name AS VARCHAR2(50)) source_name,
             CAST(:series AS VARCHAR2(10)) series,
             CAST(:security_name AS VARCHAR2(300)) security_name,
             CAST(:raw_total_mcap AS NUMBER(24,6)) raw_total_mcap,
             CAST(:raw_total_mcap_unit AS VARCHAR2(30)) raw_total_mcap_unit,
             CAST(:total_mcap_cr AS NUMBER(24,6)) total_mcap_cr,
             CAST(:raw_ffmc AS NUMBER(24,6)) raw_ffmc,
             CAST(:raw_ffmc_unit AS VARCHAR2(30)) raw_ffmc_unit,
             CAST(:ffmc_cr AS NUMBER(24,6)) ffmc_cr,
             TO_CLOB(:response_payload) response_payload,
             CAST(:fetch_status AS VARCHAR2(30)) fetch_status,
             CAST(:error_message AS VARCHAR2(2000)) error_message,
             CAST(:created_by AS VARCHAR2(128)) created_by
      FROM dual
    ) source
    ON (target.TRADE_DATE = source.trade_date AND target.SYMBOL = source.symbol AND target.SOURCE_NAME = source.source_name)
    WHEN MATCHED THEN UPDATE SET
      target.SERIES = CASE WHEN source.series IS NOT NULL THEN source.series ELSE target.SERIES END,
      target.SECURITY_NAME = CASE WHEN source.security_name IS NOT NULL THEN source.security_name ELSE target.SECURITY_NAME END,
      target.RAW_TOTAL_MCAP = CASE WHEN source.raw_total_mcap IS NOT NULL THEN source.raw_total_mcap ELSE target.RAW_TOTAL_MCAP END,
      target.RAW_TOTAL_MCAP_UNIT = CASE WHEN source.raw_total_mcap_unit IS NOT NULL THEN source.raw_total_mcap_unit ELSE target.RAW_TOTAL_MCAP_UNIT END,
      target.TOTAL_MCAP_CR = CASE WHEN source.total_mcap_cr IS NOT NULL THEN source.total_mcap_cr ELSE target.TOTAL_MCAP_CR END,
      target.RAW_FFMC = CASE WHEN source.raw_ffmc IS NOT NULL THEN source.raw_ffmc ELSE target.RAW_FFMC END,
      target.RAW_FFMC_UNIT = CASE WHEN source.raw_ffmc_unit IS NOT NULL THEN source.raw_ffmc_unit ELSE target.RAW_FFMC_UNIT END,
      target.FFMC_CR = CASE WHEN source.ffmc_cr IS NOT NULL THEN source.ffmc_cr ELSE target.FFMC_CR END,
      target.RESPONSE_PAYLOAD = CASE WHEN source.response_payload IS NOT NULL THEN source.response_payload ELSE target.RESPONSE_PAYLOAD END,
      target.FETCH_STATUS = source.fetch_status,
      target.ERROR_MESSAGE = CASE WHEN source.fetch_status IN ('SUCCESS', 'PARTIAL') THEN NULL ELSE CASE WHEN source.error_message IS NOT NULL THEN source.error_message ELSE target.ERROR_MESSAGE END END,
      target.FETCH_TS = source.trade_date,
      target.UPDATED_TS = SYSTIMESTAMP,
      target.CREATED_BY = CASE WHEN source.created_by IS NOT NULL THEN source.created_by ELSE target.CREATED_BY END
    WHEN NOT MATCHED THEN INSERT (
      ID, TRADE_DATE, SYMBOL, SOURCE_NAME, SERIES, SECURITY_NAME,
      RAW_TOTAL_MCAP, RAW_TOTAL_MCAP_UNIT, TOTAL_MCAP_CR,
      RAW_FFMC, RAW_FFMC_UNIT, FFMC_CR,
      RESPONSE_PAYLOAD, FETCH_STATUS, ERROR_MESSAGE, FETCH_TS, CREATED_BY, UPDATED_TS
    ) VALUES (
      source.id, source.trade_date, source.symbol, source.source_name, source.series, source.security_name,
      source.raw_total_mcap, source.raw_total_mcap_unit, source.total_mcap_cr,
      source.raw_ffmc, source.raw_ffmc_unit, source.ffmc_cr,
      source.response_payload, source.fetch_status, source.error_message, source.trade_date, source.created_by, SYSTIMESTAMP
    )
  """

def _record(symbol: str, trade_date: dt.date, source_name: str, **kwargs: Any) -> Dict[str, Any]:
  raw_total = kwargs.get('raw_total_mcap')
  raw_total_unit = kwargs.get('raw_total_mcap_unit')
  total_cr = kwargs.get('total_mcap_cr')
  if total_cr is None and raw_total is not None and raw_total_unit:
    total_cr = _to_crores(raw_total, raw_total_unit)
  raw_ffmc = kwargs.get('raw_ffmc')
  raw_ffmc_unit = kwargs.get('raw_ffmc_unit')
  ffmc_cr = kwargs.get('ffmc_cr')
  if ffmc_cr is None and raw_ffmc is not None and raw_ffmc_unit:
    ffmc_cr = _to_crores(raw_ffmc, raw_ffmc_unit)
  return {
    'id': kwargs.get('id'),
    'trade_date': trade_date,
    'symbol': str(symbol).strip().upper(),
    'source_name': source_name.strip().upper(),
    'series': (kwargs.get('series') or None),
    'security_name': (kwargs.get('security_name') or None),
    'raw_total_mcap': raw_total,
    'raw_total_mcap_unit': raw_total_unit,
    'total_mcap_cr': total_cr,
    'raw_ffmc': raw_ffmc,
    'raw_ffmc_unit': raw_ffmc_unit,
    'ffmc_cr': ffmc_cr,
    'response_payload': kwargs.get('response_payload'),
    'fetch_status': str(kwargs.get('fetch_status') or 'SUCCESS').upper(),
    'error_message': (str(kwargs.get('error_message') or '')[:2000] or None),
    'created_by': kwargs.get('created_by') or _CREATED_BY,
  }


def _upsert_records(records: List[Dict[str, Any]]) -> Tuple[int, int]:
  if not records:
    return 0, 0
  conn = _acquire_connection()
  success_count = 0
  failure_count = 0
  try:
    ensure_runtime(conn)
    explicit_id_required = not _table_supports_implicit_id(conn, _TABLE_SQL)
    if explicit_id_required:
      _assign_missing_record_ids(conn, _TABLE_SQL, records, force=True)
    with conn.cursor() as cur:
      if explicit_id_required:
        for record in records:
          cur.execute('SAVEPOINT NSE_MCAP_UPSERT_SP')
          try:
            cur.execute(_merge_sql(), record)
            success_count += 1
          except Exception:
            cur.execute('ROLLBACK TO SAVEPOINT NSE_MCAP_UPSERT_SP')
            failure_count += 1
            logger.exception('NSE MCAP upsert failed symbol=%s source=%s', record.get('symbol'), record.get('source_name'))
        conn.commit()
      else:
        try:
          cur.executemany(_merge_sql(), records)
          success_count = len(records)
          conn.commit()
        except Exception:
          conn.rollback()
          for record in records:
            cur.execute('SAVEPOINT NSE_MCAP_UPSERT_SP')
            try:
              cur.execute(_merge_sql(), record)
              success_count += 1
            except Exception:
              cur.execute('ROLLBACK TO SAVEPOINT NSE_MCAP_UPSERT_SP')
              failure_count += 1
              logger.exception('NSE MCAP upsert failed symbol=%s source=%s', record.get('symbol'), record.get('source_name'))
          conn.commit()
  finally:
    conn.close()
  return success_count, failure_count


def _insert_sql() -> str:
  return f"""
    INSERT INTO {_TABLE_SQL} (
      ID, TRADE_DATE, SYMBOL, SOURCE_NAME, SERIES, SECURITY_NAME,
      RAW_TOTAL_MCAP, RAW_TOTAL_MCAP_UNIT, TOTAL_MCAP_CR,
      RAW_FFMC, RAW_FFMC_UNIT, FFMC_CR,
      RESPONSE_PAYLOAD, FETCH_STATUS, ERROR_MESSAGE, FETCH_TS, CREATED_BY, UPDATED_TS
    ) VALUES (
      :id, :trade_date, :symbol, :source_name, :series, :security_name,
      :raw_total_mcap, :raw_total_mcap_unit, :total_mcap_cr,
      :raw_ffmc, :raw_ffmc_unit, :ffmc_cr,
      TO_CLOB(:response_payload), :fetch_status, :error_message, :trade_date, :created_by, SYSTIMESTAMP
    )
  """


def _insert_records(records: List[Dict[str, Any]]) -> Tuple[int, int, int]:
  import oracledb
  if not records:
    return 0, 0, 0
  conn = _acquire_connection()
  success_count = 0
  failure_count = 0
  skipped_count = 0
  try:
    ensure_runtime(conn)
    explicit_id_required = not _table_supports_implicit_id(conn, _TABLE_SQL)
    if explicit_id_required:
      _assign_missing_record_ids(conn, _TABLE_SQL, records, force=True)
    insert_sql = _insert_sql()
    with conn.cursor() as cur:
      try:
        cur.executemany(insert_sql, records)
        conn.commit()
        return len(records), 0, 0
      except Exception as e:
        conn.rollback()
        for record in records:
          cur.execute('SAVEPOINT NSE_MCAP_INSERT_SP')
          try:
            cur.execute(insert_sql, record)
            success_count += 1
          except Exception as exc:
            cur.execute('ROLLBACK TO SAVEPOINT NSE_MCAP_INSERT_SP')
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
              logger.exception('NSE MCAP insert failed symbol=%s source=%s', record.get('symbol'), record.get('source_name'))
        conn.commit()
  finally:
    conn.close()
  return success_count, failure_count, skipped_count


def _existing_file_symbols(trade_date: dt.date, source_name: str = _FILE_SOURCE) -> set[str]:
  conn = _acquire_connection()
  if conn is None:
    return set()
  try:
    with conn.cursor() as cur:
      cur.execute(
        f'''SELECT symbol
              FROM {_TABLE_SQL}
             WHERE trade_date = :trade_date
               AND source_name = :source_name''',
        {'trade_date': trade_date, 'source_name': source_name},
      )
      return {str(row[0]).strip().upper() for row in (cur.fetchall() or []) if row and row[0]}
  finally:
    try:
      conn.close()
    except Exception:
      pass


def _existing_file_row_count(trade_date: dt.date) -> int:
  conn = _acquire_connection()
  if conn is None:
    return 0
  try:
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


def _duplicate_trade_date_message(trade_date: dt.date) -> str:
  return f'Already data inserted for {trade_date.strftime("%d-%m-%Y")}.'


def inspect_mcap_csv(csv_path: Path, trade_date: dt.date, eq_only: bool = _EQ_ONLY_DEFAULT, allowed_symbols: Optional[Sequence[str]] = None) -> Dict[str, Any]:
  universe_symbols = _coerce_allowed_symbols(allowed_symbols)
  input_rows = matched_rows = parse_error_rows = skipped_rows = blank_rows = series_skipped_rows = universe_skipped_rows = 0
  matched_symbols: List[str] = []
  fieldnames: List[str] = []
  with csv_path.open('r', encoding='utf-8-sig', newline='') as handle:
    reader = csv.DictReader(handle)
    if not reader.fieldnames:
      raise ValueError('CSV file does not contain a header row.')
    fieldnames = list(reader.fieldnames or [])
    column_map = {_normalize_header(field): field for field in reader.fieldnames if field}
    symbol_col = _resolve_header(column_map, _SYMBOL_COLUMNS)
    mcap_col = _resolve_header(column_map, _MCAP_COLUMNS)
    if not symbol_col or not mcap_col:
      raise ValueError(f'Unable to identify required CSV columns. Found headers: {", ".join(reader.fieldnames)}')
    series_col = _resolve_header(column_map, _SERIES_COLUMNS)
    ffmc_col = _resolve_header(column_map, _FFMC_COLUMNS)
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
      raw_total = _parse_decimal(row.get(mcap_col))
      if raw_total is None:
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
    'nifty500Path': _nifty500_source_path(),
    'inputRows': input_rows,
    'matchedRows': matched_rows,
    'matchedSymbolsCount': len(matched_symbols),
    'matchedSymbols': matched_symbols,
    'duplicateRows': max(0, matched_rows - len(matched_symbols)),
    'parseErrorRows': parse_error_rows,
    'skippedRows': skipped_rows,
    'blankRows': blank_rows,
    'seriesSkippedRows': series_skipped_rows,
    'universeSkippedRows': universe_skipped_rows,
    'hasFfmcColumn': bool(ffmc_col),
  }


def load_mcap_csv(csv_path: Path, trade_date: dt.date, eq_only: bool = _EQ_ONLY_DEFAULT, allowed_symbols: Optional[Sequence[str]] = None, line_logger: Optional[Callable[[str], None]] = None, skip_if_existing: bool = True) -> Dict[str, int]:
  ensure_runtime()
  existing_symbols = _existing_file_symbols(trade_date) if skip_if_existing else set()
  if existing_symbols and line_logger:
    line_logger(f'[INFO] Existing MCAP symbols detected for {trade_date.strftime("%d-%m-%Y")} count={len(existing_symbols)}; duplicate rows will be skipped.')
  input_rows = loaded = failures = skipped = universe_skipped = duplicate_rows = already_loaded_count = 0
  universe_symbols = _coerce_allowed_symbols(allowed_symbols)
  valid_batch: List[Dict[str, Any]] = []
  invalid_batch: List[Dict[str, Any]] = []
  seen_symbols: set[str] = set()
  batch_number = 0

  def flush_valid_batch() -> None:
    nonlocal valid_batch, loaded, failures, skipped, duplicate_rows, batch_number
    if not valid_batch:
      return
    batch_number += 1
    batch_size = len(valid_batch)
    started_at = time.perf_counter()
    res = _insert_records(valid_batch)
    ok_count, bad_count = res[0], res[1]
    skip_count = res[2] if len(res) > 2 else 0
    loaded += ok_count
    failures += bad_count
    skipped += skip_count
    duplicate_rows += skip_count
    elapsed_ms = int(round((time.perf_counter() - started_at) * 1000))
    if line_logger:
      line_logger(
        f'[INFO] NSE MCAP insert batch={batch_number} kind=valid stage=insert size={batch_size} '
        f'inserted={ok_count} failed={bad_count} skipped={skip_count} elapsedMs={elapsed_ms} tradeDate={_iso_date(trade_date)}'
      )
    if bad_count and line_logger:
      line_logger(f'[WARN] NSE MCAP valid-row batch insert partially failed :: ok={ok_count} bad={bad_count}')
    valid_batch = []

  def flush_invalid_batch() -> None:
    nonlocal invalid_batch, loaded, failures, skipped, duplicate_rows, batch_number
    if not invalid_batch:
      return
    batch_number += 1
    batch_size = len(invalid_batch)
    started_at = time.perf_counter()
    res = _insert_records(invalid_batch)
    ok_count, bad_count = res[0], res[1]
    skip_count = res[2] if len(res) > 2 else 0
    loaded += ok_count
    failures += bad_count
    skipped += skip_count
    duplicate_rows += skip_count
    elapsed_ms = int(round((time.perf_counter() - started_at) * 1000))
    if line_logger:
      line_logger(
        f'[INFO] NSE MCAP insert batch={batch_number} kind=invalid stage=insert size={batch_size} '
        f'inserted={ok_count} failed={bad_count} skipped={skip_count} elapsedMs={elapsed_ms} tradeDate={_iso_date(trade_date)}'
      )
    if bad_count and line_logger:
      line_logger(f'[WARN] NSE MCAP invalid-row batch insert partially failed :: ok={ok_count} bad={bad_count}')
    invalid_batch = []

  with csv_path.open('r', encoding='utf-8-sig', newline='') as handle:
    reader = csv.DictReader(handle)
    if not reader.fieldnames:
      raise ValueError('CSV file does not contain a header row.')
    column_map = {_normalize_header(field): field for field in reader.fieldnames if field}
    symbol_col = _resolve_header(column_map, _SYMBOL_COLUMNS)
    mcap_col = _resolve_header(column_map, _MCAP_COLUMNS)
    if not symbol_col or not mcap_col:
      raise ValueError(f'Unable to identify required CSV columns. Found headers: {", ".join(reader.fieldnames)}')
    series_col = _resolve_header(column_map, _SERIES_COLUMNS)
    name_col = _resolve_header(column_map, _NAME_COLUMNS)
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
      if symbol in seen_symbols:
        duplicate_rows += 1
        continue
      seen_symbols.add(symbol)
      if symbol in existing_symbols:
        duplicate_rows += 1
        already_loaded_count += 1
        continue
      name = str(row.get(name_col) or '').strip() if name_col else None
      raw_total = _parse_decimal(row.get(mcap_col))
      if raw_total is None:
        failures += 1
        invalid_batch.append(_record(symbol, trade_date, _FILE_SOURCE, series=series, security_name=name, fetch_status='PARSE_ERROR', error_message=f'Unable to parse total market cap from line {line_number}'))
      else:
        valid_batch.append(_record(symbol, trade_date, _FILE_SOURCE, series=series, security_name=name, raw_total_mcap=raw_total, raw_total_mcap_unit='RS', fetch_status='SUCCESS'))
      if len(valid_batch) >= _LOAD_BATCH_SIZE:
        flush_valid_batch()
      if len(invalid_batch) >= _LOAD_BATCH_SIZE:
        flush_invalid_batch()
  flush_valid_batch()
  flush_invalid_batch()
  if line_logger:
    line_logger(
      f'[INFO] CSV load finished stage=insert tradeDate={_iso_date(trade_date)} rows={input_rows} '
      f'loaded={loaded} failures={failures} skipped={skipped} universeSkipped={universe_skipped} '
      f'duplicates={duplicate_rows} alreadyLoaded={already_loaded_count}'
    )
  already_loaded = bool(existing_symbols and already_loaded_count > 0 and loaded == 0 and failures == 0 and duplicate_rows > 0)
  return {
    'inputRows': input_rows,
    'loadedCount': loaded,
    'failureCount': failures,
    'skippedCount': skipped,
    'universeSkippedCount': universe_skipped,
    'duplicateCount': duplicate_rows,
    'alreadyLoaded': already_loaded,
    'alreadyLoadedCount': already_loaded_count,
  }




def _quote_market_caps(payload: Dict[str, Any]) -> Tuple[Optional[Decimal], Optional[str], Optional[Decimal], Optional[str]]:
  total_value = _find_value(payload, {'totalmarketcap', 'marketcap', 'totalmcap'})
  ffmc_value = _find_value(payload, {'ffmc', 'freefloatmarketcap', 'freefloatmcap'})
  raw_total = _parse_decimal(total_value)
  raw_ffmc = _parse_decimal(ffmc_value)
  total_unit = _normalize_unit(total_value, 'CR') if raw_total is not None else None
  ffmc_unit = _normalize_unit(ffmc_value, total_unit or 'CR') if raw_ffmc is not None else None
  if raw_total is None:
    issued_size = _parse_decimal(_find_value(payload, {'issuedsize'}))
    price_value = _find_value(payload, {'lastprice', 'finalprice', 'previousclose', 'closeprice'})
    last_price = _parse_decimal(price_value)
    if issued_size is not None and last_price is not None:
      raw_total = (issued_size * last_price).quantize(Decimal('0.000001'))
      total_unit = 'RS'
  return raw_total, total_unit, raw_ffmc, ffmc_unit


def _build_quote_result(symbol: str, trade_date: dt.date, payload: Optional[Dict[str, Any]] = None, error: Optional[Exception] = None, *, allow_preopen_short_circuit: bool = False) -> Dict[str, Any]:
  if error is not None:
    return {
      'symbol': symbol,
      'status': 'FAILED',
      'record': None,
      'persistRecord': False,
      'successDelta': 0,
      'failureDelta': 1,
      'skipDelta': 0,
      'preopenShortCircuit': False,
      'errorMessage': str(error),
    }

  safe_payload = payload or {}
  raw_total, raw_total_unit, raw_ffmc, raw_ffmc_unit = _quote_market_caps(safe_payload)
  current_market_type = str(safe_payload.get('currentMarketType') or '').strip().upper()
  response_payload = json.dumps(safe_payload, default=_json_default, ensure_ascii=True)
  status = 'SUCCESS'
  error_message = None
  success_delta = 0
  skip_delta = 0
  preopen_short_circuit = False

  if current_market_type == 'PO' and raw_ffmc is None:
    status = 'SKIPPED'
    error_message = 'NSE quote payload is in pre-open mode and does not expose FFMC values.'
    skip_delta = 1
    preopen_short_circuit = allow_preopen_short_circuit
    record = _record(symbol, trade_date, _QUOTE_SOURCE, raw_total_mcap=raw_total, raw_total_mcap_unit=raw_total_unit, response_payload=response_payload, fetch_status=status, error_message=error_message)
  else:
    if raw_total is None and raw_ffmc is None:
      status = 'SKIPPED'
      error_message = 'Quote payload did not contain total market cap or free-float market cap.'
      skip_delta = 1
    elif raw_total is None or raw_ffmc is None:
      status = 'PARTIAL'
      success_delta = 1
      error_message = 'Only one quote market cap value was returned by NSE.'
    else:
      success_delta = 1
    record = _record(symbol, trade_date, _QUOTE_SOURCE, raw_total_mcap=raw_total, raw_total_mcap_unit=raw_total_unit or raw_ffmc_unit, raw_ffmc=raw_ffmc, raw_ffmc_unit=raw_ffmc_unit or raw_total_unit, response_payload=response_payload, fetch_status=status, error_message=error_message)

  return {
    'symbol': symbol,
    'status': status,
    'record': record,
    'successDelta': success_delta,
    'failureDelta': 0,
    'skipDelta': skip_delta,
    'preopenShortCircuit': preopen_short_circuit,
    'errorMessage': error_message,
  }


def _read_quote_payload(client: _HttpClient, symbol: str) -> Dict[str, Any]:
  return client.read_json(f'{_NSE_BASE}/api/quote-equity?symbol={quote(symbol, safe="")}')


def _new_quote_client() -> _HttpClient:
  return _HttpClient(
    warmup=False,
    timeout_sec=_QUOTE_TIMEOUT_SEC,
    retry_count=_QUOTE_RETRY_COUNT,
    min_sleep=_QUOTE_MIN_SLEEP,
    max_sleep=_QUOTE_MAX_SLEEP,
  )


def _thread_client(local_state: threading.local) -> _HttpClient:
  client = getattr(local_state, 'client', None)
  if client is None:
    client = _new_quote_client()
    local_state.client = client
  return client

def _symbols_for_enrichment(trade_date: dt.date, limit: Optional[int], override_symbols: Optional[List[str]]) -> List[str]:
  if override_symbols:
    cleaned: List[str] = []
    seen: set[str] = set()
    for item in override_symbols:
      token = str(item or '').strip().upper()
      if token and token not in seen:
        seen.add(token)
        cleaned.append(token)
    return cleaned[:limit] if limit else cleaned
  conn = _acquire_connection()
  try:
    with conn.cursor() as cur:
      cur.execute(f'''
        SELECT symbol FROM (
          SELECT file_rows.symbol
          FROM {_TABLE_SQL} file_rows
          LEFT JOIN {_TABLE_SQL} quote_rows
            ON quote_rows.trade_date = file_rows.trade_date
           AND quote_rows.symbol = file_rows.symbol
           AND quote_rows.source_name = :quote_source
          WHERE file_rows.trade_date = :trade_date
            AND file_rows.source_name = :file_source
            AND file_rows.fetch_status IN ('SUCCESS', 'PARTIAL')
            AND (quote_rows.symbol IS NULL OR quote_rows.ffmc_cr IS NULL OR quote_rows.fetch_status NOT IN ('SUCCESS', 'PARTIAL'))
          GROUP BY file_rows.symbol
          ORDER BY file_rows.symbol
        )
      ''', {'trade_date': trade_date, 'file_source': _FILE_SOURCE, 'quote_source': _QUOTE_SOURCE})
      rows = [str(row[0]).upper() for row in (cur.fetchall() or []) if row and row[0]]
      return rows[:limit] if limit else rows
  finally:
    conn.close()


def enrich_quotes(trade_date: dt.date, limit: Optional[int] = None, symbols: Optional[List[str]] = None, line_logger: Optional[Callable[[str], None]] = None) -> Dict[str, int]:
  ensure_runtime()
  target_symbols = _symbols_for_enrichment(trade_date, limit, symbols)
  if not target_symbols:
    return {'requested': 0, 'processed': 0, 'successCount': 0, 'failureCount': 0, 'skippedCount': 0, 'elapsedSec': 0.0}

  success_count = failure_count = skipped_count = 0
  pending_records: List[Dict[str, Any]] = []
  started_at = time.perf_counter()
  processed_count = 0
  total_symbols = len(target_symbols)

  def flush_pending() -> None:
    nonlocal pending_records
    if not pending_records:
      return
    ok_count, bad_count = _upsert_records(pending_records)
    if bad_count and line_logger:
      line_logger(f'[WARN] FFMC Oracle upsert batch partially failed :: ok={ok_count} bad={bad_count}')
    pending_records = []

  def apply_result(result: Dict[str, Any], *, allow_short_circuit_skip: bool = False, remaining_symbols: int = 0) -> bool:
    nonlocal success_count, failure_count, skipped_count, processed_count
    success_count += int(result.get('successDelta') or 0)
    failure_count += int(result.get('failureDelta') or 0)
    skipped_count += int(result.get('skipDelta') or 0)
    record = result.get('record')
    if result.get('persistRecord') is not False and isinstance(record, dict):
      pending_records.append(record)
    processed_count += 1
    if len(pending_records) >= _ENRICH_BATCH_SIZE:
      flush_pending()
    if line_logger:
      line_logger(f'[INFO] Quote enrichment {result["symbol"]} -> {result["status"]}')
      if processed_count == total_symbols or processed_count % max(10, min(_ENRICH_BATCH_SIZE, 25)) == 0:
        elapsed = time.perf_counter() - started_at
        rate = processed_count / elapsed if elapsed > 0 else 0.0
        line_logger(f'[INFO] Quote enrichment progress {processed_count}/{total_symbols} elapsed={elapsed:.1f}s rate={rate:.2f} symbols/sec')
    if allow_short_circuit_skip and result.get('preopenShortCircuit'):
      skipped_count += remaining_symbols
      flush_pending()
      if line_logger:
        line_logger(f'[INFO] Quote enrichment {result["symbol"]} -> SKIPPED (pre-open payload returned no FFMC values)')
        if remaining_symbols > 0:
          line_logger(f'[INFO] Skipping remaining {remaining_symbols} symbol(s) because NSE pre-open quote payload has no FFMC data.')
      return True
    return False

  first_symbol = target_symbols[0]
  first_client = _new_quote_client()
  try:
    first_payload = _read_quote_payload(first_client, first_symbol)
    first_result = _build_quote_result(first_symbol, trade_date, first_payload, allow_preopen_short_circuit=True)
  except Exception as exc:
    first_result = _build_quote_result(first_symbol, trade_date, error=exc)
    if line_logger:
      line_logger(f'[WARN] Quote enrichment {first_symbol} failed :: {exc}')
  if apply_result(first_result, allow_short_circuit_skip=True, remaining_symbols=total_symbols - 1):
    elapsed = time.perf_counter() - started_at
    return {'requested': total_symbols, 'processed': processed_count, 'successCount': success_count, 'failureCount': failure_count, 'skippedCount': skipped_count, 'elapsedSec': round(elapsed, 3)}

  remaining_targets = target_symbols[1:]
  if _ENRICH_CONCURRENCY <= 1 or len(remaining_targets) <= 1:
    client = first_client
    for symbol in remaining_targets:
      try:
        payload = _read_quote_payload(client, symbol)
        result = _build_quote_result(symbol, trade_date, payload)
      except Exception as exc:
        result = _build_quote_result(symbol, trade_date, error=exc)
        if line_logger:
          line_logger(f'[WARN] Quote enrichment {symbol} failed :: {exc}')
      apply_result(result)
  else:
    local_state = threading.local()

    def worker(symbol: str) -> Dict[str, Any]:
      client = _thread_client(local_state)
      try:
        payload = _read_quote_payload(client, symbol)
        return _build_quote_result(symbol, trade_date, payload)
      except Exception as exc:
        return _build_quote_result(symbol, trade_date, error=exc)

    max_workers = min(_ENRICH_CONCURRENCY, len(remaining_targets))
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix='nse-quote') as executor:
      futures = {executor.submit(worker, symbol): symbol for symbol in remaining_targets}
      for future in as_completed(futures):
        symbol = futures[future]
        try:
          result = future.result()
        except Exception as exc:
          result = _build_quote_result(symbol, trade_date, error=exc)
        if result['status'] == 'FAILED' and line_logger:
          line_logger(f'[WARN] Quote enrichment {symbol} failed :: {result.get("errorMessage") or "Unknown error"}')
        apply_result(result)

  flush_pending()
  elapsed = time.perf_counter() - started_at
  return {'requested': total_symbols, 'processed': processed_count, 'successCount': success_count, 'failureCount': failure_count, 'skippedCount': skipped_count, 'elapsedSec': round(elapsed, 3)}

def _save_run_start(run_id: str, trade_date: dt.date, run_type: str, payload: Dict[str, Any]) -> None:
  conn = _acquire_connection()
  try:
    with conn.cursor() as cur:
      cur.execute(
        f'''INSERT INTO {_RUNS_TABLE_SQL} (RUN_ID, TRADE_DATE, RUN_TYPE, STATUS, REQUEST_JSON, MESSAGE, STARTED_TS, CREATED_BY)
            VALUES (:run_id, :trade_date, :run_type, 'RUNNING', :request_json, :message, SYSTIMESTAMP, :created_by)''',
        {'run_id': run_id, 'trade_date': trade_date, 'run_type': run_type, 'request_json': json.dumps(payload, default=_json_default, ensure_ascii=True), 'message': f'{run_type} job started.', 'created_by': _CREATED_BY}
      )
    conn.commit()
  finally:
    conn.close()


def _save_run_finish(run_id: str, status: str, message: str, metrics: Dict[str, Any], logs: List[str], download_path: Optional[str], job: Optional[Dict[str, Any]] = None) -> None:
  conn = _acquire_connection()
  try:
    with conn.cursor() as cur:
      cur.execute(
        f'''UPDATE {_RUNS_TABLE_SQL}
               SET STATUS = :status,
                   MESSAGE = :message,
                   DOWNLOAD_FILE_PATH = :download_file_path,
                   METRICS_JSON = :metrics_json,
                   LOGS_CLOB = :logs_clob,
                   FINISHED_TS = SYSTIMESTAMP
             WHERE RUN_ID = :run_id''',
        {
          'run_id': run_id,
          'status': status,
          'message': message[:4000],
          'download_file_path': (download_path or '')[:1000] or None,
          'metrics_json': json.dumps(_job_snapshot_payload(job, 180) if job is not None else metrics, default=_json_default, ensure_ascii=True),
          'logs_clob': '\n'.join(logs) if logs else None,
        }
      )
    conn.commit()
  finally:
    conn.close()


def _persist_completed_run_record(
  run_type: str,
  trade_date: dt.date,
  payload: Optional[Dict[str, Any]],
  result: Dict[str, Any],
  *,
  mode: str,
  stage: str,
) -> None:
  request_payload = _clone_request_payload(payload)
  request_payload['mode'] = str(mode or '').strip().upper() or 'MANUAL'
  request_payload['stage'] = str(stage or '').strip().lower() or 'process'
  request_payload['jobMode'] = 'pipeline' if request_payload['mode'] == 'AUTOMATION' else 'manual'
  request_payload['logicalDatasetKey'] = _logical_dataset_key(request_payload)
  run_id = uuid.uuid4().hex
  status = _status_token(result.get('status')) or _final_status_from_result(result)
  message = str(result.get('message') or _final_status_message(status, result))
  _save_run_start(run_id, trade_date, run_type, request_payload)
  _save_run_finish(run_id, status, message, result, [], result.get('downloadPath'), job=None)


def _get_data_overview(trade_date: Optional[dt.date], conn: Any = None, start_date: Optional[dt.date] = None, end_date: Optional[dt.date] = None) -> Dict[str, Any]:
  own_conn = conn is None
  connection = conn or _acquire_connection()
  try:
    if own_conn:
      ensure_runtime(connection)
    return data_overview_svc.build_overview(connection, _TABLE_SQL, trade_date, start_date=start_date, end_date=end_date)
  finally:
    if own_conn:
      connection.close()


def _get_dashboard_single(trade_date_text: Optional[str] = None, limit: Optional[int] = None, include_overview: bool = True) -> Dict[str, Any]:
  conn = _acquire_connection()
  try:
    ensure_runtime(conn)
    trade_date = _parse_date(trade_date_text, 'tradeDate') if trade_date_text else _business_date()
    overview: Dict[str, Any] = {}
    with conn.cursor() as cur:
      cur.execute(f"SELECT MAX(TRADE_DATE) FROM {_TABLE_SQL} WHERE TRADE_DATE = :trade_date AND FETCH_STATUS IN ('SUCCESS', 'PARTIAL')", {'trade_date': trade_date})
      if (cur.fetchone() or [None])[0] is None:
        cur.execute(f"SELECT MAX(TRADE_DATE) FROM {_TABLE_SQL} WHERE FETCH_STATUS IN ('SUCCESS', 'PARTIAL')")
        latest = (cur.fetchone() or [None])[0]
        if latest is not None and not trade_date_text:
          trade_date = _parse_date(latest, 'tradeDate')
      if include_overview:
        overview = _get_data_overview(trade_date, conn=conn)
      cur.execute(
        f'''WITH latest_mcap AS (
              SELECT symbol, total_mcap_cr,
                     ROW_NUMBER() OVER (
                       PARTITION BY symbol
                       ORDER BY total_mcap_cr DESC NULLS LAST, fetch_ts DESC NULLS LAST, updated_ts DESC NULLS LAST, id DESC NULLS LAST
                     ) rn
              FROM {_TABLE_SQL}
              WHERE trade_date = :trade_date
                AND total_mcap_cr IS NOT NULL
            ),
            latest_ffmc AS (
              SELECT symbol, ffmc_cr,
                     ROW_NUMBER() OVER (
                       PARTITION BY symbol
                       ORDER BY fetch_ts DESC NULLS LAST, updated_ts DESC NULLS LAST, id DESC NULLS LAST
                     ) rn
              FROM {_TABLE_SQL}
              WHERE trade_date = :trade_date
                AND source_name = :quote_source
                AND ffmc_cr IS NOT NULL
            ),
            raw_stats AS (
              SELECT COUNT(*) total_rows, COUNT(DISTINCT symbol) distinct_symbols, MAX(fetch_ts) latest_fetch_ts,
                   SUM(CASE WHEN source_name = :file_source THEN 1 ELSE 0 END) file_rows,
                   SUM(CASE WHEN source_name = :quote_source THEN 1 ELSE 0 END) quote_rows
              FROM {_TABLE_SQL}
              WHERE trade_date = :trade_date
            ),
            file_status AS (
              SELECT symbol, fetch_status,
                     ROW_NUMBER() OVER (
                       PARTITION BY symbol
                       ORDER BY fetch_ts DESC NULLS LAST, updated_ts DESC NULLS LAST, id DESC NULLS LAST
                     ) rn
              FROM {_TABLE_SQL}
              WHERE trade_date = :trade_date
                AND source_name = :file_source
            ),
            quote_status AS (
              SELECT symbol, fetch_status,
                     ROW_NUMBER() OVER (
                       PARTITION BY symbol
                       ORDER BY fetch_ts DESC NULLS LAST, updated_ts DESC NULLS LAST, id DESC NULLS LAST
                     ) rn
              FROM {_TABLE_SQL}
              WHERE trade_date = :trade_date
                AND source_name = :quote_source
            ),
            effective_status AS (
              SELECT COALESCE(f.symbol, q.symbol) symbol,
                     CASE
                       WHEN q.fetch_status IN ('SUCCESS', 'PARTIAL') THEN q.fetch_status
                       WHEN f.fetch_status IN ('SUCCESS', 'PARTIAL') THEN 'SUCCESS'
                       ELSE COALESCE(q.fetch_status, f.fetch_status, 'FAILED')
                     END fetch_status
              FROM (SELECT symbol, fetch_status FROM file_status WHERE rn = 1) f
              FULL OUTER JOIN (SELECT symbol, fetch_status FROM quote_status WHERE rn = 1) q
                ON q.symbol = f.symbol
            ),
            summary_stats AS (
              SELECT COUNT(*) effective_rows,
                     SUM(CASE WHEN fetch_status IN ('SUCCESS', 'PARTIAL') THEN 1 ELSE 0 END) success_rows,
                     SUM(CASE WHEN fetch_status IN ('FAILED', 'PARSE_ERROR') THEN 1 ELSE 0 END) failure_rows,
                     SUM(CASE WHEN fetch_status = 'SKIPPED' THEN 1 ELSE 0 END) skipped_rows
              FROM effective_status
            ),
            mcap_total AS (
              SELECT NVL(SUM(total_mcap_cr), 0) total_mcap_cr_sum
              FROM latest_mcap
              WHERE rn = 1
            ),
            ffmc_total AS (
              SELECT COUNT(*) ffmc_rows, NVL(SUM(ffmc_cr), 0) ffmc_cr_sum
              FROM latest_ffmc
              WHERE rn = 1
            )
            SELECT r.total_rows, r.distinct_symbols, r.latest_fetch_ts, r.file_rows, r.quote_rows,
                   s.success_rows, s.failure_rows, s.skipped_rows,
                   f.ffmc_rows, m.total_mcap_cr_sum, f.ffmc_cr_sum
            FROM raw_stats r
            CROSS JOIN summary_stats s
            CROSS JOIN mcap_total m
            CROSS JOIN ffmc_total f''',
        {'trade_date': trade_date, 'file_source': _FILE_SOURCE, 'quote_source': _QUOTE_SOURCE}
      )
      summary_row = _row_to_dict(cur, cur.fetchone() or [])
      try:
        requested_limit = int(limit) if limit not in (None, '') else 0
      except (TypeError, ValueError):
        requested_limit = 0
      row_limit = requested_limit if requested_limit > 0 else int(summary_row.get('distinct_symbols') or 0)
      row_limit = max(1, row_limit)
      cur.execute(
        f'''WITH file_rows AS (
              SELECT * FROM (
                SELECT t.trade_date, t.symbol, t.source_name, t.series, t.security_name,
                       t.raw_total_mcap, t.raw_total_mcap_unit, t.total_mcap_cr,
                       t.fetch_status AS file_fetch_status,
                       t.fetch_ts AS file_fetch_ts,
                       ROW_NUMBER() OVER (
                         PARTITION BY t.symbol
                         ORDER BY t.fetch_ts DESC, t.updated_ts DESC, t.id DESC
                       ) rn
                FROM {_TABLE_SQL} t
                WHERE t.trade_date = :trade_date
                  AND t.source_name = :file_source
              ) WHERE rn = 1
            ),
            quote_rows AS (
              SELECT * FROM (
                SELECT t.trade_date, t.symbol,
                       t.source_name AS quote_source_name,
                       t.raw_ffmc, t.raw_ffmc_unit, t.ffmc_cr,
                       t.fetch_status AS quote_fetch_status,
                       t.fetch_ts AS quote_fetch_ts,
                       ROW_NUMBER() OVER (
                         PARTITION BY t.symbol
                         ORDER BY t.fetch_ts DESC, t.updated_ts DESC, t.id DESC
                       ) rn
                FROM {_TABLE_SQL} t
                WHERE t.trade_date = :trade_date
                  AND t.source_name = :quote_source
              ) WHERE rn = 1
            )
            SELECT symbol, trade_date, source_name, series, security_name, raw_total_mcap, raw_total_mcap_unit,
                   total_mcap_cr, raw_ffmc, raw_ffmc_unit, ffmc_cr, fetch_status, inserted_rows, fetch_ts
            FROM (
            SELECT file_rows.symbol,
                     file_rows.trade_date,
                     CASE
                       WHEN quote_rows.quote_source_name IS NOT NULL THEN file_rows.source_name || ' + ' || quote_rows.quote_source_name
                       ELSE file_rows.source_name
                     END AS source_name,
                     file_rows.series,
                     file_rows.security_name,
                     file_rows.raw_total_mcap,
                     file_rows.raw_total_mcap_unit,
                     file_rows.total_mcap_cr,
                     quote_rows.raw_ffmc,
                     quote_rows.raw_ffmc_unit,
                     quote_rows.ffmc_cr,
                     CASE
                       WHEN quote_rows.quote_fetch_status IN ('SUCCESS', 'PARTIAL') THEN quote_rows.quote_fetch_status
                       WHEN file_rows.file_fetch_status IN ('SUCCESS', 'PARTIAL') THEN 'SUCCESS'
                       ELSE COALESCE(quote_rows.quote_fetch_status, file_rows.file_fetch_status)
                     END AS fetch_status,
                     (
                       CASE WHEN file_rows.file_fetch_status IN ('SUCCESS', 'PARTIAL') THEN 1 ELSE 0 END
                       + CASE WHEN quote_rows.quote_fetch_status IN ('SUCCESS', 'PARTIAL') THEN 1 ELSE 0 END
                     ) AS inserted_rows,
                     COALESCE(quote_rows.quote_fetch_ts, file_rows.file_fetch_ts) AS fetch_ts,
                     ROW_NUMBER() OVER (
                       ORDER BY COALESCE(quote_rows.quote_fetch_ts, file_rows.file_fetch_ts) DESC,
                                file_rows.symbol DESC
                     ) rn
              FROM file_rows
              LEFT JOIN quote_rows
                ON quote_rows.symbol = file_rows.symbol
            ) WHERE rn <= :limit_value
            ORDER BY fetch_ts DESC, symbol DESC''',
        {'trade_date': trade_date, 'file_source': _FILE_SOURCE, 'quote_source': _QUOTE_SOURCE, 'limit_value': row_limit}
      )
      rows = _apply_latest_row_insertion_metadata([_row_to_dict(cur, row) for row in (cur.fetchall() or [])])
      cur.execute(
        f'''SELECT * FROM (
              SELECT run_id, trade_date, run_type, status, message, download_file_path, started_ts, finished_ts, created_by
              FROM {_RUNS_TABLE_SQL}
              WHERE trade_date = :trade_date
              ORDER BY started_ts DESC
            ) WHERE ROWNUM <= 12''',
        {'trade_date': trade_date}
      )
      runs = [_row_to_dict(cur, row) for row in (cur.fetchall() or [])]

      run_stats = _load_trade_date_run_mode_stats(cur, _RUNS_TABLE_SQL, trade_date)

    return _apply_trade_date_metadata({
      'ok': True,
      'tradeDate': trade_date.strftime('%Y-%m-%d'),
      'downloadDir': str(_download_dir()),
      'summary': _apply_insertion_summary_metadata({
        'totalRows': int(summary_row.get('total_rows') or 0),
        'distinctSymbols': int(summary_row.get('distinct_symbols') or 0),
        'latestFetchTs': summary_row.get('latest_fetch_ts'),
        'fileRows': int(summary_row.get('file_rows') or 0),
        'quoteRows': int(summary_row.get('quote_rows') or 0),
        'successRows': int(summary_row.get('success_rows') or 0),
        'failureRows': int(summary_row.get('failure_rows') or 0),
        'skippedRows': int(summary_row.get('skipped_rows') or 0),
        'ffmcRows': int(summary_row.get('ffmc_rows') or 0),
        'totalMcapCrSum': float(summary_row.get('total_mcap_cr_sum') or 0),
        'ffmcCrSum': float(summary_row.get('ffmc_cr_sum') or 0),
        'manualRows': int(run_stats.get('manual_runs') or 0),
        'automationRows': int(run_stats.get('auto_runs') or 0),
      }),
      'rows': rows,
      'recentRuns': runs,
      'sources': {'file': _FILE_SOURCE, 'quote': _QUOTE_SOURCE},
      'objects': {'table': _TABLE_SQL, 'runsTable': _RUNS_TABLE_SQL, 'view': _LATEST_VIEW_SQL},
      'dataOverview': overview,
    }, trade_date)
  finally:
    conn.close()


def _get_dashboard_all(limit: Optional[int] = None) -> Dict[str, Any]:
  conn = _acquire_connection()
  try:
    ensure_runtime(conn)
    with conn.cursor() as cur:
      cur.execute(f"SELECT MAX(TRADE_DATE) latest_trade_date FROM {_TABLE_SQL} WHERE FETCH_STATUS IN ('SUCCESS', 'PARTIAL')")
      latest_row = _row_to_dict(cur, cur.fetchone() or [])
      latest_trade_date = latest_row.get('latest_trade_date')
    latest_trade_text = ''
    latest_payload: Dict[str, Any] = {'rows': [], 'recentRuns': []}
    if latest_trade_date:
      latest_trade_text = _iso_date(latest_trade_date)
      latest_payload = _get_dashboard_single(latest_trade_text, limit=limit, include_overview=False)
    summary = dict(latest_payload.get('summary') or {})
    if not summary:
      summary = _apply_insertion_summary_metadata({
        'totalRows': 0,
        'distinctSymbols': 0,
        'latestFetchTs': None,
        'fileRows': 0,
        'quoteRows': 0,
        'successRows': 0,
        'failureRows': 0,
        'skippedRows': 0,
        'ffmcRows': 0,
        'totalMcapCrSum': 0.0,
        'ffmcCrSum': 0.0,
      })
    return _apply_trade_date_metadata({
      'ok': True,
      'tradeDate': latest_trade_text,
      'downloadDir': str(_download_dir()),
      'summary': summary,
      'rows': latest_payload.get('rows') or [],
      'recentRuns': latest_payload.get('recentRuns') or [],
      'sources': {'file': _FILE_SOURCE, 'quote': _QUOTE_SOURCE},
      'objects': {'table': _TABLE_SQL, 'runsTable': _RUNS_TABLE_SQL, 'view': _LATEST_VIEW_SQL},
      'dataOverview': _get_data_overview(None),
    }, latest_trade_text)
  finally:
    conn.close()


def _aggregate_dashboard_summary(items: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
  latest_fetch = None
  summary = {
    'totalRows': 0,
    'distinctSymbols': 0,
    'latestFetchTs': None,
    'fileRows': 0,
    'quoteRows': 0,
    'successRows': 0,
    'failureRows': 0,
    'skippedRows': 0,
    'ffmcRows': 0,
    'totalMcapCrSum': 0.0,
    'ffmcCrSum': 0.0,
  }
  for item in items:
    current = item.get('summary') or {}
    summary['totalRows'] += int(current.get('totalRows') or 0)
    summary['distinctSymbols'] += int(current.get('distinctSymbols') or 0)
    summary['fileRows'] += int(current.get('fileRows') or 0)
    summary['quoteRows'] += int(current.get('quoteRows') or 0)
    summary['successRows'] += int(current.get('successRows') or 0)
    summary['failureRows'] += int(current.get('failureRows') or 0)
    summary['skippedRows'] += int(current.get('skippedRows') or 0)
    summary['ffmcRows'] += int(current.get('ffmcRows') or 0)
    summary['totalMcapCrSum'] += float(current.get('totalMcapCrSum') or 0)
    summary['ffmcCrSum'] += float(current.get('ffmcCrSum') or 0)
    candidate_fetch = current.get('latestFetchTs')
    if candidate_fetch and (latest_fetch is None or str(candidate_fetch) > str(latest_fetch)):
      latest_fetch = candidate_fetch
  summary['latestFetchTs'] = latest_fetch
  return _apply_insertion_summary_metadata(summary)


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
  requested_range = _normalize_history_range(range_text)
  if not requested_trade_date and not requested_start_date and not requested_end_date and (not requested_range or requested_range == 'MAX'):
    return _get_dashboard_all(limit=limit)
  trade_dates = _parse_trade_dates(
    requested_trade_date or None,
    requested_start_date or None,
    requested_end_date or None,
    range_value=requested_range,
  )
  if len(trade_dates) == 1:
    single_trade_date = requested_trade_date or (_iso_date(trade_dates[0]) if (requested_start_date or requested_end_date) else None)
    result = _get_dashboard_single(single_trade_date, limit=limit)
    result['tradeDateLabel'] = _trade_date_label(trade_dates)
    return result
  dashboards = [_get_dashboard_single(_iso_date(trade_date), limit=limit, include_overview=False) for trade_date in trade_dates]
  base = dict(dashboards[-1])
  base.update(_date_context(trade_dates))
  base['summary'] = _aggregate_dashboard_summary(dashboards)
  base['rows'] = _aggregate_dashboard_rows(dashboards, limit)
  base['dataOverview'] = _get_data_overview(trade_dates[-1], start_date=trade_dates[0], end_date=trade_dates[-1])
  return base


def _load_marketcap_index_enrichment(cur: Any, latest_trade_date: Any) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
  mcap_meta: Dict[str, Dict[str, Any]] = {}
  delivery_dates: Dict[str, Any] = {}
  mcap_symbol_expr = _normalized_symbol_expr('t.symbol')
  delivery_symbol_expr = _normalized_symbol_expr('d.symbol')
  try:
    cur.execute(
      f'''SELECT symbol_key,
                 mcap_series,
                 security_name
          FROM (
            SELECT {mcap_symbol_expr} AS symbol_key,
                   TRIM(t.series) AS mcap_series,
                   TRIM(t.security_name) AS security_name,
                   ROW_NUMBER() OVER (
                     PARTITION BY {mcap_symbol_expr}
                     ORDER BY
                       CASE WHEN t.series IS NOT NULL THEN 0 ELSE 1 END,
                       CASE WHEN t.security_name IS NOT NULL THEN 0 ELSE 1 END,
                       CASE WHEN t.source_name = :file_source THEN 0 ELSE 1 END,
                       t.fetch_ts DESC NULLS LAST,
                       t.updated_ts DESC NULLS LAST,
                       t.id DESC NULLS LAST
                   ) rn
              FROM {_TABLE_SQL} t
             WHERE t.trade_date = :trade_date
               AND t.symbol IS NOT NULL
               AND (t.series IS NOT NULL OR t.security_name IS NOT NULL)
          )
          WHERE rn = 1''',
      {'trade_date': latest_trade_date, 'file_source': _FILE_SOURCE}
    )
    for row in (cur.fetchall() or []):
      item = _row_to_dict(cur, row)
      symbol_key = _normalize_symbol_token(item.get('symbol_key'))
      if not symbol_key:
        continue
      mcap_meta[symbol_key] = {
        'mcap_series': _first_non_blank(item.get('mcap_series')),
        'security_name': _first_non_blank(item.get('security_name')),
      }
  except Exception:
    logger.exception('NSE MCAP INDEX API metadata enrichment failed table=%s', _TABLE_SQL)

  try:
    cur.execute(
      f'''SELECT {delivery_symbol_expr} AS symbol_key,
                 MAX(d.trade_date) AS ltc_date
            FROM {_DELIVERY_TABLE_SQL} d
           WHERE d.symbol IS NOT NULL
           GROUP BY {delivery_symbol_expr}'''
    )
    for row in (cur.fetchall() or []):
      item = _row_to_dict(cur, row)
      symbol_key = _normalize_symbol_token(item.get('symbol_key'))
      if symbol_key:
        delivery_dates[symbol_key] = item.get('ltc_date')
  except Exception:
    logger.exception('NSE MCAP INDEX API delivery LTC_DATE enrichment failed table=%s', _DELIVERY_TABLE_SQL)

  return mcap_meta, delivery_dates



def get_marketcap_index_latest() -> Dict[str, Any]:
  conn = _acquire_connection()
  try:
    logger.info('NSE MCAP INDEX API query start table=%s file_source=%s', _TABLE_SQL, _FILE_SOURCE)
    with conn.cursor() as cur:
      cur.execute(
        f'''SELECT MAX(trade_date) AS latest_trade_date
              FROM {_TABLE_SQL}
             WHERE total_mcap_cr IS NOT NULL'''
      )
      latest_trade_date = (cur.fetchone() or [None])[0]
      if latest_trade_date is None:
        logger.info('NSE MCAP INDEX API no latest trade_date found with total_mcap_cr IS NOT NULL')
        return {
          'status': 'success',
          'latestDate': '',
          'summary': {
            'totalSymbols': 0,
            'totalMarketCapCrores': 0.0,
            'largeSymbols': 0,
            'largeMarketCapCrores': 0.0,
            'midSymbols': 0,
            'midMarketCapCrores': 0.0,
            'smallSymbols': 0,
            'smallMarketCapCrores': 0.0,
            'indexWise': [],
          },
          'data': [],
        }
      logger.info('NSE MCAP INDEX API latest_trade_date=%s', _iso_date(latest_trade_date))
      rows: List[Dict[str, Any]] = []
      try:
        cur.execute(
          f'''SELECT script,
                     symbol,
                     index_category,
                     mcap_rank,
                     market_cap_crores,
                     mcap_series,
                     security_name
              FROM {_INDEX_VIEW_SQL}
              ORDER BY mcap_rank ASC'''
        )
        rows = [_row_to_dict(cur, row) for row in (cur.fetchall() or [])]
        logger.info('NSE MCAP INDEX API view rows fetched=%s view=%s', len(rows), _INDEX_VIEW_SQL)
      except Exception as exc:
        logger.warning(
          'NSE MCAP INDEX API view query failed; falling back to base-table derivation view=%s error=%s',
          _INDEX_VIEW_SQL,
          exc,
        )
        cur.execute(
          f'''SELECT symbol,
                     series AS mcap_series,
                     security_name,
                     total_mcap_cr AS market_cap_crores
              FROM {_TABLE_SQL}
              WHERE trade_date = :trade_date
                AND total_mcap_cr IS NOT NULL
              ORDER BY total_mcap_cr DESC, symbol ASC''',
          {'trade_date': latest_trade_date}
        )
        raw_rows = [_row_to_dict(cur, row) for row in (cur.fetchall() or [])]
        dedup: Dict[str, Dict[str, Any]] = {}
        for item in raw_rows:
          symbol_key = str(item.get('symbol') or '').strip().upper()
          if symbol_key and symbol_key not in dedup:
            dedup[symbol_key] = item
        rank = 0
        for item in dedup.values():
          rank += 1
          rows.append({
            'script': item.get('symbol'),
            'symbol': item.get('symbol'),
            'index_category': 'LARGE' if rank <= 100 else ('MID' if rank <= 250 else 'SMALL'),
            'mcap_rank': rank,
            'market_cap_crores': item.get('market_cap_crores'),
            'mcap_series': item.get('mcap_series'),
            'security_name': item.get('security_name'),
          })
      logger.info('NSE MCAP INDEX API rows fetched=%s', len(rows))
      mcap_meta_by_symbol, delivery_ltc_by_symbol = _load_marketcap_index_enrichment(cur, latest_trade_date)

    normalized_rows: List[Dict[str, Any]] = []
    for row in rows:
      symbol_value = row.get('symbol') or row.get('script') or '-'
      symbol_key = _normalize_symbol_token(symbol_value)
      mcap_meta = mcap_meta_by_symbol.get(symbol_key, {})
      ltc_date_value = delivery_ltc_by_symbol.get(symbol_key)
      ltc_date_iso = _iso_date(ltc_date_value) if ltc_date_value else None
      mcap_series = _first_non_blank(row.get('mcap_series'), mcap_meta.get('mcap_series')) or '-'
      security_name = _first_non_blank(row.get('security_name'), mcap_meta.get('security_name')) or '-'
      rank_value = int(row.get('mcap_rank') or 0)
      market_cap = row.get('market_cap_crores')
      market_cap_num = float(market_cap) if market_cap is not None else 0.0
      if not math.isfinite(market_cap_num):
        market_cap_num = 0.0
      idx = str(row.get('index_category') or row.get('index') or '').strip().upper()
      if idx not in {'LARGE', 'MID', 'SMALL'}:
        idx = 'LARGE' if 1 <= rank_value <= 100 else ('MID' if 101 <= rank_value <= 250 else 'SMALL')
      normalized_rows.append({
        'script': row.get('script') or symbol_value,
        'symbol': symbol_value,
        'ltc_date': ltc_date_iso,
        'ltcDate': ltc_date_iso,
        'INDEX': idx,
        'index': idx,
        'MCAP': market_cap_num,
        'mcap': market_cap_num,
        'MCAP_RANK': rank_value,
        'mcapRank': rank_value,
        'marketCapCrores': market_cap_num,
        'mcapSeries': mcap_series,
        'mcap_series': mcap_series,
        'securityName': security_name,
        'security_name': security_name,
      })

    totals = {
      'LARGE': {'symbolsCount': 0, 'marketCapCrores': 0.0},
      'MID': {'symbolsCount': 0, 'marketCapCrores': 0.0},
      'SMALL': {'symbolsCount': 0, 'marketCapCrores': 0.0},
    }
    total_market_cap = 0.0
    for row in normalized_rows:
      value = float(row.get('marketCapCrores') or 0.0)
      idx = str(row.get('index') or '').upper()
      total_market_cap += value
      if idx in totals:
        totals[idx]['symbolsCount'] += 1
        totals[idx]['marketCapCrores'] += value

    return {
      'status': 'success',
      'latestDate': _iso_date(latest_trade_date),
      'summary': {
        'totalSymbols': len(normalized_rows),
        'totalMarketCapCrores': total_market_cap,
        'largeSymbols': totals['LARGE']['symbolsCount'],
        'largeMarketCapCrores': totals['LARGE']['marketCapCrores'],
        'midSymbols': totals['MID']['symbolsCount'],
        'midMarketCapCrores': totals['MID']['marketCapCrores'],
        'smallSymbols': totals['SMALL']['symbolsCount'],
        'smallMarketCapCrores': totals['SMALL']['marketCapCrores'],
        'indexWise': [
          {'index': 'LARGE', 'symbolsCount': totals['LARGE']['symbolsCount'], 'marketCapCrores': totals['LARGE']['marketCapCrores']},
          {'index': 'MID', 'symbolsCount': totals['MID']['symbolsCount'], 'marketCapCrores': totals['MID']['marketCapCrores']},
          {'index': 'SMALL', 'symbolsCount': totals['SMALL']['symbolsCount'], 'marketCapCrores': totals['SMALL']['marketCapCrores']},
        ],
      },
      'data': normalized_rows,
    }
  except Exception:
    logger.exception('NSE MCAP INDEX API failed')
    raise
  finally:
    conn.close()


def _marketcap_chunks(values: Sequence[str], size: int = 500) -> List[List[str]]:
  cleaned = [str(value or '').strip().upper() for value in values if str(value or '').strip()]
  return [cleaned[index:index + size] for index in range(0, len(cleaned), size)]


def _marketcap_first_value(source: Dict[str, Any], keys: Sequence[str]) -> Any:
  for key in keys:
    if key in source and source[key] not in (None, ''):
      return source[key]
  return None


def _marketcap_float(value: Any) -> Optional[float]:
  if value in (None, ''):
    return None
  try:
    number = float(value)
  except (TypeError, ValueError):
    return None
  return number if math.isfinite(number) else None


def _marketcap_int(value: Any) -> Optional[int]:
  if value in (None, ''):
    return None
  try:
    number = int(float(value))
  except (TypeError, ValueError):
    return None
  return number if number > 0 else None


def _marketcap_index_value(value: Any, rank: Any = None) -> str:
  token = str(value or '').strip().upper()
  if token in {'LARGE', 'MID', 'SMALL'}:
    return token
  rank_value = _marketcap_int(rank)
  if rank_value is None:
    return '-'
  if rank_value <= 100:
    return 'LARGE'
  if rank_value <= 250:
    return 'MID'
  return 'SMALL'


def _marketcap_lookup_copy(lookup: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
  return {key: dict(value) for key, value in (lookup or {}).items()}


def _marketcap_lookup_from_view(cur: Any, symbol_keys: Sequence[str]) -> Dict[str, Dict[str, Any]]:
  result: Dict[str, Dict[str, Any]] = {}
  symbol_expr = _normalized_symbol_expr('COALESCE(v.symbol, v.script)')
  for batch in _marketcap_chunks(symbol_keys):
    binds = {f'sym_{idx}': symbol for idx, symbol in enumerate(batch)}
    bind_sql = ', '.join(f':sym_{idx}' for idx in range(len(batch)))
    cur.execute(
      f'''
      SELECT q.symbol_key,
             q.index_category,
             q.mcap_rank,
             q.market_cap_crores
        FROM (
          SELECT {symbol_expr} AS symbol_key,
                 v.index_category,
                 v.mcap_rank,
                 v.market_cap_crores
            FROM {_INDEX_VIEW_SQL} v
           WHERE v.symbol IS NOT NULL OR v.script IS NOT NULL
        ) q
       WHERE q.symbol_key IN ({bind_sql})
      ''',
      binds,
    )
    for row in (cur.fetchall() or []):
      item = _row_to_dict(cur, row)
      key = _normalize_symbol_token(item.get('symbol_key'))
      if not key:
        continue
      rank_value = _marketcap_int(item.get('mcap_rank'))
      mcap_value = _marketcap_float(item.get('market_cap_crores'))
      result[key] = {
        'index': _marketcap_index_value(item.get('index_category'), rank_value),
        'mcap': mcap_value,
        'mcapRank': rank_value,
      }
  return result


def _marketcap_lookup_from_base_table(cur: Any, symbol_keys: Sequence[str]) -> Dict[str, Dict[str, Any]]:
  result: Dict[str, Dict[str, Any]] = {}
  symbol_expr = _normalized_symbol_expr('t.symbol')
  for batch in _marketcap_chunks(symbol_keys):
    binds = {f'sym_{idx}': symbol for idx, symbol in enumerate(batch)}
    bind_sql = ', '.join(f':sym_{idx}' for idx in range(len(batch)))
    cur.execute(
      f'''
      SELECT ranked.symbol_key,
             CASE
               WHEN ranked.mcap_rank <= 100 THEN 'LARGE'
               WHEN ranked.mcap_rank <= 250 THEN 'MID'
               ELSE 'SMALL'
             END AS index_category,
             ranked.mcap_rank,
             ranked.market_cap_crores
        FROM (
          SELECT latest.symbol_key,
                 latest.market_cap_crores,
                 ROW_NUMBER() OVER (
                   ORDER BY latest.market_cap_crores DESC NULLS LAST, latest.symbol_key ASC
                 ) AS mcap_rank
            FROM (
              SELECT {symbol_expr} AS symbol_key,
                     MAX(t.total_mcap_cr) KEEP (
                       DENSE_RANK LAST ORDER BY t.trade_date, t.fetch_ts
                     ) AS market_cap_crores
                FROM {_TABLE_SQL} t
               WHERE t.trade_date = (
                       SELECT MAX(trade_date)
                         FROM {_TABLE_SQL}
                        WHERE total_mcap_cr IS NOT NULL
                     )
                 AND t.symbol IS NOT NULL
                 AND t.total_mcap_cr IS NOT NULL
               GROUP BY {symbol_expr}
            ) latest
        ) ranked
       WHERE ranked.symbol_key IN ({bind_sql})
      ''',
      binds,
    )
    for row in (cur.fetchall() or []):
      item = _row_to_dict(cur, row)
      key = _normalize_symbol_token(item.get('symbol_key'))
      if not key:
        continue
      rank_value = _marketcap_int(item.get('mcap_rank'))
      mcap_value = _marketcap_float(item.get('market_cap_crores'))
      result[key] = {
        'index': _marketcap_index_value(item.get('index_category'), rank_value),
        'mcap': mcap_value,
        'mcapRank': rank_value,
      }
  return result


def _marketcap_lookup_from_latest_per_symbol(cur: Any, symbol_keys: Sequence[str]) -> Dict[str, Dict[str, Any]]:
  result: Dict[str, Dict[str, Any]] = {}
  symbol_expr = _normalized_symbol_expr('t.symbol')
  for batch in _marketcap_chunks(symbol_keys):
    binds = {f'sym_{idx}': symbol for idx, symbol in enumerate(batch)}
    bind_sql = ', '.join(f':sym_{idx}' for idx in range(len(batch)))
    cur.execute(
      f'''
      SELECT ranked.symbol_key,
             CASE
               WHEN ranked.mcap_rank <= 100 THEN 'LARGE'
               WHEN ranked.mcap_rank <= 250 THEN 'MID'
               ELSE 'SMALL'
             END AS index_category,
             ranked.mcap_rank,
             ranked.market_cap_crores
        FROM (
          SELECT latest.symbol_key,
                 latest.market_cap_crores,
                 ROW_NUMBER() OVER (
                   ORDER BY latest.market_cap_crores DESC NULLS LAST, latest.symbol_key ASC
                 ) AS mcap_rank
            FROM (
              SELECT {symbol_expr} AS symbol_key,
                     MAX(t.total_mcap_cr) KEEP (
                       DENSE_RANK LAST ORDER BY t.trade_date, t.fetch_ts
                     ) AS market_cap_crores
                FROM {_TABLE_SQL} t
               WHERE t.symbol IS NOT NULL
                 AND t.total_mcap_cr IS NOT NULL
               GROUP BY {symbol_expr}
            ) latest
        ) ranked
       WHERE ranked.symbol_key IN ({bind_sql})
      ''',
      binds,
    )
    for row in (cur.fetchall() or []):
      item = _row_to_dict(cur, row)
      key = _normalize_symbol_token(item.get('symbol_key'))
      if not key:
        continue
      rank_value = _marketcap_int(item.get('mcap_rank'))
      mcap_value = _marketcap_float(item.get('market_cap_crores'))
      result[key] = {
        'index': _marketcap_index_value(item.get('index_category'), rank_value),
        'mcap': mcap_value,
        'mcapRank': rank_value,
      }
  return result


def get_marketcap_index_lookup(
  symbols: Sequence[Any],
  *,
  allow_stale_per_symbol: bool = False,
  allow_base_table_fallback: bool = True,
) -> Dict[str, Dict[str, Any]]:
  """Return INDEX, MCAP, and MCAP_RANK metadata keyed by normalized symbol."""
  symbol_keys = sorted({
    _normalize_symbol_token(symbol)
    for symbol in (symbols or [])
    if _normalize_symbol_token(symbol)
  })
  if not symbol_keys:
    return {}

  lookup_mode = 'latest_global'
  if allow_stale_per_symbol:
    lookup_mode = 'latest_per_symbol'
  if not allow_base_table_fallback:
    lookup_mode += '_view_only'
  cache_key = (lookup_mode, *symbol_keys)
  if _LOOKUP_CACHE_TTL_SEC > 0:
    cached = _MARKETCAP_LOOKUP_CACHE.get(cache_key)
    if isinstance(cached, dict):
      return _marketcap_lookup_copy(cached)

  conn = _acquire_connection()
  try:
    with conn.cursor() as cur:
      global _INDEX_VIEW_AVAILABLE
      can_use_view = _INDEX_VIEW_AVAILABLE is not False
      if can_use_view:
        try:
          result = _marketcap_lookup_from_view(cur, symbol_keys)
          missing = [symbol for symbol in symbol_keys if symbol not in result]
          _INDEX_VIEW_AVAILABLE = True
        except Exception as exc:
          if 'ORA-00942' in str(exc):
            _INDEX_VIEW_AVAILABLE = False
            logger.warning('NSE MCAP index lookup view unavailable (ORA-00942); using base table fallback view=%s', _INDEX_VIEW_SQL)
          else:
            logger.exception('NSE MCAP index lookup view failed; falling back to base table view=%s', _INDEX_VIEW_SQL)
          result = {}
          missing = list(symbol_keys)
      else:
        result = {}
        missing = list(symbol_keys)
      if missing and allow_base_table_fallback:
        fallback = _marketcap_lookup_from_base_table(cur, missing)
        result.update({key: value for key, value in fallback.items() if key not in result})
        missing = [symbol for symbol in symbol_keys if symbol not in result]
      if missing and allow_stale_per_symbol:
        fallback = _marketcap_lookup_from_latest_per_symbol(cur, missing)
        result.update({key: value for key, value in fallback.items() if key not in result})
      if _LOOKUP_CACHE_TTL_SEC > 0:
        _MARKETCAP_LOOKUP_CACHE.set(cache_key, _marketcap_lookup_copy(result))
      return result
  except Exception:
    logger.exception('NSE MCAP index lookup failed table=%s view=%s', _TABLE_SQL, _INDEX_VIEW_SQL)
    return {}
  finally:
    conn.close()


def _row_symbol_for_marketcap(row: Dict[str, Any], symbol_keys: Sequence[str]) -> str:
  for key in symbol_keys:
    value = row.get(key)
    if value not in (None, ''):
      return str(value).strip()
  return ''


def enrich_rows_with_marketcap_index(
  rows: Sequence[Dict[str, Any]] | None,
  *,
  symbol_keys: Sequence[str] = ('symbol', 'SYMBOL', 'stock', 'STOCK', 'stockName', 'STOCK_NAME', 'script', 'SCRIPT'),
  allow_stale_per_symbol: bool = False,
  allow_base_table_fallback: bool = True,
) -> List[Dict[str, Any]]:
  """Append market-cap index metadata to symbol-based API rows without mutating input rows."""
  source_rows = [row for row in (rows or []) if isinstance(row, dict)]
  raw_symbols = [_row_symbol_for_marketcap(row, symbol_keys) for row in source_rows]
  lookup = get_marketcap_index_lookup(
    raw_symbols,
    allow_stale_per_symbol=allow_stale_per_symbol,
    allow_base_table_fallback=allow_base_table_fallback,
  )
  enriched: List[Dict[str, Any]] = []

  for row in source_rows:
    output = dict(row)
    symbol_key = _normalize_symbol_token(_row_symbol_for_marketcap(output, symbol_keys))
    meta = lookup.get(symbol_key, {}) if symbol_key else {}

    rank_value = _marketcap_int(_marketcap_first_value(output, (
      'MCAP_RANK', 'mcapRank', 'mcap_rank', 'marketCapRank', 'market_cap_rank',
    )))
    if rank_value is None:
      rank_value = _marketcap_int(_marketcap_first_value(meta, (
        'MCAP_RANK', 'mcapRank', 'mcap_rank', 'marketCapRank', 'market_cap_rank',
      )))

    mcap_value = _marketcap_float(_marketcap_first_value(output, (
      'MCAP', 'mcap', 'totalMcap', 'total_mcap', 'TOTAL_MCAP', 'TOTAL_MCAP_CR',
      'marketCapCrores', 'MARKET_CAP_CRORES', 'market_cap_crores',
    )))
    if mcap_value is None:
      mcap_value = _marketcap_float(_marketcap_first_value(meta, (
        'MCAP', 'mcap', 'totalMcap', 'total_mcap', 'TOTAL_MCAP', 'TOTAL_MCAP_CR',
        'marketCapCrores', 'MARKET_CAP_CRORES', 'market_cap_crores',
      )))

    index_value = _marketcap_index_value(
      _marketcap_first_value(output, (
        'INDEX', 'index', 'index_value', 'INDEX_VALUE', 'market_cap_index',
        'MARKET_CAP_INDEX', 'indexCategory', 'index_category',
      )) or _marketcap_first_value(meta, (
        'INDEX', 'index', 'index_value', 'INDEX_VALUE', 'market_cap_index',
        'MARKET_CAP_INDEX', 'indexCategory', 'index_category',
      )),
      rank_value,
    )

    output['INDEX'] = index_value
    output['index'] = index_value
    output['MCAP'] = mcap_value
    output['mcap'] = mcap_value
    output['mcapSort'] = mcap_value
    output['MCAP_RANK'] = rank_value
    output['mcapRank'] = rank_value
    output['mcap_rank'] = rank_value
    output['mcapRankSort'] = rank_value
    enriched.append(output)

  return enriched


def enrich_payload_marketcap_index(
  payload: Dict[str, Any] | None,
  *,
  row_keys: Sequence[str] = ('rows',),
  symbol_keys: Sequence[str] = ('symbol', 'SYMBOL', 'stock', 'STOCK', 'stockName', 'STOCK_NAME', 'script', 'SCRIPT'),
  allow_stale_per_symbol: bool = False,
) -> Dict[str, Any]:
  """Append market-cap metadata to each configured row list in an API payload."""
  if not isinstance(payload, dict):
    return {}
  output = dict(payload)
  for key in row_keys:
    rows = output.get(key)
    if isinstance(rows, list):
      output[key] = enrich_rows_with_marketcap_index(
        rows,
        symbol_keys=symbol_keys,
        allow_stale_per_symbol=allow_stale_per_symbol,
      )
  return output


def _parse_runtime_payload(payload: Dict[str, Any], line_logger: Optional[Callable[[str], None]] = None) -> Tuple[List[dt.date], bool, Optional[int], List[str], Optional[set[str]]]:
  trade_dates = _parse_trade_dates(
    payload.get('tradeDate') or payload.get('trade_date'),
    payload.get('startDate') or payload.get('start_date'),
    payload.get('endDate') or payload.get('end_date'),
    range_value=payload.get('range') or payload.get('dateRange') or payload.get('date_range'),
    allow_override=_allow_market_date_override(payload),
  )
  eq_only = _coerce_bool(payload.get('eqOnly'), _EQ_ONLY_DEFAULT)
  symbols = [str(item).strip().upper() for item in (payload.get('symbols') or '').split(',') if str(item).strip()] if not isinstance(payload.get('symbols'), list) else [str(item).strip().upper() for item in payload.get('symbols') if str(item).strip()]
  try:
    enrich_limit = int(payload.get('enrichLimit') or payload.get('enrich_limit') or 0) or None
  except (TypeError, ValueError):
    enrich_limit = None
  allowed_symbols = _runtime_filter_symbols()
  if line_logger and allowed_symbols is not None:
    line_logger(f'[INFO] Filtering against NIFTY500 universe count={len(allowed_symbols)} path={_nifty500_source_path()}')
  if line_logger and len(trade_dates) > 1:
    line_logger(f'[INFO] Processing trade date range {_trade_date_label(trade_dates)} businessDates={len(trade_dates)}')
  return trade_dates, eq_only, enrich_limit, symbols, allowed_symbols


def _is_unavailable_trade_date_error(exc: Exception) -> bool:
  text = str(exc or '').strip().lower()
  return 'unable to download nse mcap csv for' in text



def _unavailable_trade_date_result(trade_date: dt.date, exc: Exception, *, include_load: bool = False, include_enrichment: bool = False) -> Dict[str, Any]:
  message = f'No NSE MCAP file available for {_display_date(trade_date)}. Skipping likely holiday / non-trading date.'
  result: Dict[str, Any] = {
    'ok': True,
    'message': message,
    'tradeDate': _iso_date(trade_date),
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
  if include_enrichment:
    result['enrichment'] = {'requested': 0, 'processed': 0, 'successCount': 0, 'failureCount': 0, 'skippedCount': 0, 'elapsedSec': 0.0}
  return result



def _result_unavailable(result: Dict[str, Any]) -> bool:
  return bool(result.get('skippedUnavailable'))



def _run_range_stage(trade_dates: Sequence[dt.date], runner: Callable[[dt.date], Dict[str, Any]], *, line_logger: Optional[Callable[[str], None]] = None, include_load: bool = False, include_enrichment: bool = False, stage_label: Optional[str] = None) -> List[Dict[str, Any]]:
  results: List[Dict[str, Any]] = []
  for trade_date in trade_dates:
    if line_logger and stage_label:
      line_logger(f'[INFO] {stage_label} tradeDate={_iso_date(trade_date)}')
    try:
      results.append(runner(trade_date))
    except Exception as exc:
      if not _is_unavailable_trade_date_error(exc):
        raise
      if line_logger:
        line_logger(f'[WARN] No NSE MCAP file available for tradeDate={_iso_date(trade_date)}; skipping likely holiday / unavailable date. {exc}')
      results.append(_unavailable_trade_date_result(trade_date, exc, include_load=include_load, include_enrichment=include_enrichment))
  return results


def _result_already_loaded(result: Dict[str, Any]) -> bool:
  inspection = result.get('inspection') or {}
  load = result.get('load') or {}
  return bool(inspection.get('alreadyLoaded') or load.get('alreadyLoaded'))


def _aggregate_inspection(results: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
  items = [result.get('inspection') or {} for result in results]
  matched_symbols = sorted({str(symbol).upper() for item in items for symbol in (item.get('matchedSymbols') or []) if str(symbol).strip()})
  all_already_loaded = bool(items) and all(bool(item.get('alreadyLoaded')) for item in items)
  return {
    'headers': next((list(item.get('headers') or []) for item in items if item.get('headers')), []),
    'inputRows': sum(int(item.get('inputRows') or 0) for item in items),
    'matchedRows': sum(int(item.get('matchedRows') or 0) for item in items),
    'matchedSymbolsCount': len(matched_symbols),
    'matchedSymbols': matched_symbols,
    'parseErrorRows': sum(int(item.get('parseErrorRows') or 0) for item in items),
    'skippedRows': sum(int(item.get('skippedRows') or 0) for item in items),
    'blankRows': sum(int(item.get('blankRows') or 0) for item in items),
    'seriesSkippedRows': sum(int(item.get('seriesSkippedRows') or 0) for item in items),
    'universeSkippedRows': sum(int(item.get('universeSkippedRows') or 0) for item in items),
    'hasFfmcColumn': any(bool(item.get('hasFfmcColumn')) for item in items),
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


def _aggregate_enrichment(results: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
  items = [result.get('enrichment') or {} for result in results if result.get('enrichment') is not None]
  return {
    'requested': sum(int(item.get('requested') or 0) for item in items),
    'processed': sum(int(item.get('processed') or 0) for item in items),
    'successCount': sum(int(item.get('successCount') or 0) for item in items),
    'failureCount': sum(int(item.get('failureCount') or 0) for item in items),
    'skippedCount': sum(int(item.get('skippedCount') or 0) for item in items),
    'elapsedSec': round(sum(float(item.get('elapsedSec') or 0.0) for item in items), 3),
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


def _aggregate_stage_response(trade_dates: Sequence[dt.date], results: Sequence[Dict[str, Any]], message: str, include_load: bool = False, include_enrichment: bool = False, include_summary: bool = False) -> Dict[str, Any]:
  response: Dict[str, Any] = {'ok': all(bool(result.get('ok', True)) for result in results), 'message': message}
  response.update(_date_context(trade_dates))
  download_paths = [str(result.get('downloadPath')) for result in results if result.get('downloadPath')]
  unavailable_dates = [
    {
      'tradeDate': result.get('tradeDate'),
      'displayDate': _display_date(_parse_date(result.get('tradeDate'), 'tradeDate')) if result.get('tradeDate') else None,
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
  if include_enrichment:
    response['enrichment'] = _aggregate_enrichment(results)
  if include_summary:
    response['summary'] = get_dashboard(limit=None, start_date_text=_iso_date(trade_dates[0]), end_date_text=_iso_date(trade_dates[-1])).get('summary', {})
  if include_load or include_enrichment:
    status = _final_status_from_result(response)
    response['status'] = status
    response['done'] = True
    response['ok'] = status not in _JOB_FAILURE_STATUSES and status != 'FAILED'
  else:
    processed_count = int(response.get('processedDateCount') or 0)
    skipped_count = int(response.get('skippedDateCount') or 0)
    all_unavailable = bool(results) and response.get('skippedUnavailableDateCount') == len(results)
    all_already_loaded = bool(response.get('inspection', {}).get('alreadyLoaded')) and processed_count == 0
    if all_unavailable:
      response['status'] = 'SKIPPED'
    elif all_already_loaded:
      response['status'] = 'ALREADY_EXISTS'
    elif processed_count > 0 and skipped_count > 0:
      response['status'] = 'PARTIAL'
    elif processed_count > 0:
      response['status'] = 'SUCCESS'
    else:
      response['status'] = 'NO_ACTION'
    response['done'] = True
  return response


def _stage_message(base_message: str, trade_dates: Sequence[dt.date], results: Sequence[Dict[str, Any]]) -> str:
  label = _trade_date_label(trade_dates)
  already_loaded = [result for result in results if _result_already_loaded(result)]
  unavailable = [result for result in results if _result_unavailable(result)]
  if results and len(already_loaded) == len(results):
    return f'Already data inserted for {label}.'
  if results and len(unavailable) == len(results):
    skipped_text = ', '.join(_display_date(_parse_date(result.get('tradeDate'), 'tradeDate')) for result in unavailable if result.get('tradeDate'))
    return f'No NSE MCAP files available for {label}. Skipped likely holiday / unavailable trade date(s): {skipped_text}.'
  suffix_parts: List[str] = []
  if already_loaded:
    suffix_parts.append(f'Skipped {len(already_loaded)} already-loaded trade date(s).')
  if unavailable:
    skipped_text = ', '.join(_display_date(_parse_date(result.get('tradeDate'), 'tradeDate')) for result in unavailable if result.get('tradeDate'))
    suffix_parts.append(f'Skipped {len(unavailable)} holiday / unavailable trade date(s): {skipped_text}.')
  suffix = f" {' '.join(suffix_parts)}" if suffix_parts else ''
  return f'{base_message} for {label}.{suffix}'


def _download_api_single(trade_date: dt.date, eq_only: bool, allowed_symbols: Optional[set[str]], line_logger: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
  csv_path = download_mcap_csv(trade_date, line_logger=line_logger)
  inspection = inspect_mcap_csv(csv_path, trade_date, eq_only=eq_only, allowed_symbols=allowed_symbols)
  return {
    'ok': True,
    'status': 'SUCCESS',
    'message': 'NSE MCAP file downloaded and extracted.',
    'done': True,
    'tradeDate': _iso_date(trade_date),
    'downloadPath': str(csv_path),
    'inspection': inspection,
  }


def _validate_api_single(trade_date: dt.date, eq_only: bool, allowed_symbols: Optional[set[str]], line_logger: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
  csv_path = download_mcap_csv(trade_date, line_logger=line_logger)
  inspection = inspect_mcap_csv(csv_path, trade_date, eq_only=eq_only, allowed_symbols=allowed_symbols)
  return {
    'ok': True,
    'status': 'SUCCESS',
    'message': 'NSE MCAP CSV validated.',
    'done': True,
    'tradeDate': _iso_date(trade_date),
    'downloadPath': str(csv_path),
    'inspection': inspection,
  }


def _process_api_single(trade_date: dt.date, eq_only: bool, allowed_symbols: Optional[set[str]], line_logger: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
  rows_before = _safe_mcap_trade_date_row_count(trade_date, source='all')
  if line_logger:
    line_logger(_flow_marker('download', f'Downloading NSE MCAP CSV for {_iso_date(trade_date)}.'))
  csv_path = download_mcap_csv(trade_date, line_logger=line_logger)
  if line_logger:
    line_logger(_flow_marker('validate', f'Validating NSE MCAP CSV for {_iso_date(trade_date)}.'))
  inspection = inspect_mcap_csv(csv_path, trade_date, eq_only=eq_only, allowed_symbols=allowed_symbols)
  if line_logger:
    line_logger(_flow_marker('process', f'Inserting NSE MCAP rows into Oracle for {_iso_date(trade_date)}.'))
  load_summary = load_mcap_csv(csv_path, trade_date, eq_only=eq_only, allowed_symbols=allowed_symbols, line_logger=line_logger)
  rows_after = _safe_mcap_trade_date_row_count(trade_date, source='all')
  if _load_summary_failed(load_summary, inspection):
    return _apply_run_contract_fields({
      'ok': False,
      'status': 'FAILED',
      'done': True,
      'message': 'NSE MCAP CSV insert failed. No rows were written to Oracle.',
      'tradeDate': _iso_date(trade_date),
      'downloadPath': str(csv_path),
      'inspection': inspection,
      'load': load_summary,
      'summary': {},
      'dbVerification': {
        'table': _TABLE_SQL,
        'tradingDate': _iso_date(trade_date),
        'rowCountBefore': rows_before,
        'rowCountAfter': rows_after,
        'insertedRows': int(load_summary.get('loadedCount') or 0),
        'updatedRows': 0,
        'skippedRows': int(load_summary.get('skippedCount') or 0) + int(load_summary.get('alreadyLoadedCount') or 0),
        'failedRows': int(load_summary.get('failureCount') or 0),
        'commitConfirmed': False,
      },
    }, page='MARKET_CAP', mode='MANUAL', stage='process')
  result = {
    'ok': True,
    'message': 'NSE MCAP CSV inserted into Oracle.',
    'tradeDate': _iso_date(trade_date),
    'downloadPath': str(csv_path),
    'inspection': inspection,
    'load': load_summary,
    'summary': get_dashboard(_iso_date(trade_date)).get('summary', {}),
    'dbVerification': {
      'table': _TABLE_SQL,
      'tradingDate': _iso_date(trade_date),
      'rowCountBefore': rows_before,
      'rowCountAfter': rows_after,
      'insertedRows': int(load_summary.get('loadedCount') or 0),
      'updatedRows': 0,
      'skippedRows': int(load_summary.get('skippedCount') or 0) + int(load_summary.get('alreadyLoadedCount') or 0),
      'failedRows': int(load_summary.get('failureCount') or 0),
      'commitConfirmed': rows_after >= rows_before and int(load_summary.get('failureCount') or 0) == 0,
    },
  }
  status = _final_status_from_result(result)
  result['status'] = status
  result['done'] = True
  result['ok'] = status not in _JOB_FAILURE_STATUSES and status != 'FAILED'
  if status != 'SUCCESS':
    result['message'] = _final_status_message(status, result)
  return _apply_run_contract_fields(result, page='MARKET_CAP', mode='MANUAL', stage='process')


def _run_pipeline_single(trade_date: dt.date, eq_only: bool, enrich_limit: Optional[int], symbols: List[str], allowed_symbols: Optional[set[str]], line_logger: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
  rows_before = _safe_mcap_trade_date_row_count(trade_date, source='all')
  if line_logger:
    line_logger(_flow_marker('download', f'Downloading NSE MCAP CSV for {_iso_date(trade_date)}.'))
  csv_path = download_mcap_csv(trade_date, line_logger=line_logger)
  if line_logger:
    line_logger(_flow_marker('validate', f'Validating NSE MCAP CSV for {_iso_date(trade_date)}.'))
  inspection = inspect_mcap_csv(csv_path, trade_date, eq_only=eq_only, allowed_symbols=allowed_symbols)
  if line_logger:
    line_logger(_flow_marker('process', f'Inserting NSE MCAP rows into Oracle for {_iso_date(trade_date)}.'))
  load_summary = load_mcap_csv(csv_path, trade_date, eq_only=eq_only, allowed_symbols=allowed_symbols, line_logger=line_logger)
  rows_after_file = _safe_mcap_trade_date_row_count(trade_date, source='all')
  if _load_summary_failed(load_summary, inspection):
    return _apply_run_contract_fields({
      'ok': False,
      'status': 'FAILED',
      'done': True,
      'message': 'NSE Market Cap pipeline failed during Oracle insert. No rows were written to Oracle.',
      'tradeDate': _iso_date(trade_date),
      'downloadPath': str(csv_path),
      'inspection': inspection,
      'load': load_summary,
      'enrichment': {'requested': 0, 'processed': 0, 'successCount': 0, 'failureCount': 0, 'skippedCount': 0, 'elapsedSec': 0.0},
      'summary': {},
      'dbVerification': {
        'table': _TABLE_SQL,
        'tradingDate': _iso_date(trade_date),
        'rowCountBefore': rows_before,
        'rowCountAfter': rows_after_file,
        'insertedRows': int(load_summary.get('loadedCount') or 0),
        'updatedRows': 0,
        'skippedRows': int(load_summary.get('skippedCount') or 0) + int(load_summary.get('alreadyLoadedCount') or 0),
        'failedRows': int(load_summary.get('failureCount') or 0),
        'commitConfirmed': False,
      },
    }, page='MARKET_CAP', mode='AUTOMATION', stage='pipeline')
  if line_logger:
    line_logger(_flow_marker('process', f'Enriching NSE quote data for {_iso_date(trade_date)}.'))
  enrichment_summary = enrich_quotes(trade_date, limit=enrich_limit, symbols=symbols or None, line_logger=line_logger)
  rows_after = _safe_mcap_trade_date_row_count(trade_date, source='all')
  quote_unavailable = _enrichment_summary_failed(enrichment_summary)
  if quote_unavailable and line_logger:
    line_logger('[WARN] NSE quote enrichment unavailable; MCAP file rows were inserted successfully and quote rows will be treated as optional.')
  result = {
    'ok': True,
    'message': 'NSE Market Cap pipeline completed.' if not quote_unavailable else 'NSE Market Cap file rows inserted successfully; quote enrichment unavailable.',
    'tradeDate': _iso_date(trade_date),
    'downloadPath': str(csv_path),
    'inspection': inspection,
    'load': load_summary,
    'enrichment': enrichment_summary,
    'summary': get_dashboard(_iso_date(trade_date)).get('summary', {}),
    'dbVerification': {
      'table': _TABLE_SQL,
      'tradingDate': _iso_date(trade_date),
      'rowCountBefore': rows_before,
      'rowCountAfter': rows_after,
      'insertedRows': int(load_summary.get('loadedCount') or 0) + int(enrichment_summary.get('successCount') or 0),
      'updatedRows': 0,
      'skippedRows': int(load_summary.get('skippedCount') or 0) + int(load_summary.get('alreadyLoadedCount') or 0) + int(enrichment_summary.get('skippedCount') or 0),
      'failedRows': int(load_summary.get('failureCount') or 0) + int(enrichment_summary.get('failureCount') or 0),
      'commitConfirmed': rows_after >= rows_before and int(load_summary.get('failureCount') or 0) == 0,
    },
  }
  status = 'SUCCESS' if quote_unavailable else _final_status_from_result(result)
  result['status'] = status
  result['done'] = True
  result['ok'] = status not in _JOB_FAILURE_STATUSES and status != 'FAILED'
  if status != 'SUCCESS':
    result['message'] = _final_status_message(status, result)
  return _apply_run_contract_fields(result, page='MARKET_CAP', mode='AUTOMATION', stage='pipeline')


def download_api(payload: Dict[str, Any]) -> Dict[str, Any]:
  duplicate = _duplicate_stage_result(payload, message='NSE MCAP file already exists for this logical batch; no download was performed.')
  if duplicate is not None:
    return _apply_run_contract_fields(duplicate, page='MARKET_CAP', mode='MANUAL', stage='download')
  trade_dates, eq_only, _enrich_limit, _symbols, allowed_symbols = _parse_runtime_payload(payload)
  if len(trade_dates) == 1:
    return _apply_run_contract_fields(_download_api_single(trade_dates[0], eq_only, allowed_symbols), page='MARKET_CAP', mode='MANUAL', stage='download')
  results = _run_range_stage(trade_dates, lambda trade_date: _download_api_single(trade_date, eq_only, allowed_symbols))
  return _apply_run_contract_fields(_aggregate_stage_response(trade_dates, results, _stage_message('NSE MCAP files downloaded and extracted', trade_dates, results)), page='MARKET_CAP', mode='MANUAL', stage='download')


def validate_api(payload: Dict[str, Any]) -> Dict[str, Any]:
  duplicate = _duplicate_stage_result(payload, message='NSE MCAP file already exists for this logical batch; no validation was performed.')
  if duplicate is not None:
    return _apply_run_contract_fields(duplicate, page='MARKET_CAP', mode='MANUAL', stage='validate')
  trade_dates, eq_only, _enrich_limit, _symbols, allowed_symbols = _parse_runtime_payload(payload)
  if len(trade_dates) == 1:
    return _apply_run_contract_fields(_validate_api_single(trade_dates[0], eq_only, allowed_symbols), page='MARKET_CAP', mode='MANUAL', stage='validate')
  results = _run_range_stage(trade_dates, lambda trade_date: _validate_api_single(trade_date, eq_only, allowed_symbols))
  return _apply_run_contract_fields(_aggregate_stage_response(trade_dates, results, _stage_message('NSE MCAP CSVs validated', trade_dates, results)), page='MARKET_CAP', mode='MANUAL', stage='validate')


def process_api(payload: Dict[str, Any], line_logger: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
  duplicate = _duplicate_stage_result(payload, message='NSE MCAP data already exists for this logical batch; no insert was performed.')
  if duplicate is not None:
    return _apply_run_contract_fields(duplicate, page='MARKET_CAP', mode='MANUAL', stage='process')
  trade_dates, eq_only, _enrich_limit, _symbols, allowed_symbols = _parse_runtime_payload(payload, line_logger=line_logger)
  if len(trade_dates) == 1:
    result = _process_api_single(trade_dates[0], eq_only, allowed_symbols, line_logger=line_logger)
  else:
    results = _run_range_stage(
      trade_dates,
      lambda trade_date: _process_api_single(trade_date, eq_only, allowed_symbols, line_logger=line_logger),
      line_logger=line_logger,
      include_load=True,
      stage_label='Processing NSE MCAP insert for',
    )
    result = _aggregate_stage_response(trade_dates, results, _stage_message('NSE MCAP CSVs inserted into Oracle', trade_dates, results), include_load=True, include_summary=True)
  decorated = _apply_run_contract_fields(result, page='MARKET_CAP', mode='MANUAL', stage='process')
  try:
    _persist_completed_run_record(_RUN_TYPE, trade_dates[-1], payload, decorated, mode='MANUAL', stage='process')
  except Exception:
    logger.exception('Unable to persist NSE MCAP manual process run for tradeDate=%s', _iso_date(trade_dates[-1]))
  return decorated


def init_runtime_api() -> Dict[str, Any]:
  return ensure_runtime()


def run_pipeline(payload: Dict[str, Any], line_logger: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
  duplicate = _duplicate_stage_result(payload, message='NSE Market Cap pipeline already exists for this logical batch; no new work was started.')
  if duplicate is not None:
    return _apply_run_contract_fields(duplicate, page='MARKET_CAP', mode='AUTOMATION', stage='pipeline')
  trade_dates, eq_only, enrich_limit, symbols, allowed_symbols = _parse_runtime_payload(payload, line_logger=line_logger)
  if len(trade_dates) == 1:
    result = _run_pipeline_single(trade_dates[0], eq_only, enrich_limit, symbols, allowed_symbols, line_logger=line_logger)
  else:
    results = _run_range_stage(
      trade_dates,
      lambda trade_date: _run_pipeline_single(trade_date, eq_only, enrich_limit, symbols, allowed_symbols, line_logger=line_logger),
      line_logger=line_logger,
      include_load=True,
      include_enrichment=True,
      stage_label='Running NSE MCAP pipeline for',
    )
    result = _aggregate_stage_response(trade_dates, results, _stage_message('NSE Market Cap pipeline completed', trade_dates, results), include_load=True, include_enrichment=True, include_summary=True)
  decorated = _apply_run_contract_fields(result, page='MARKET_CAP', mode='AUTOMATION', stage='pipeline')
  if not str((payload or {}).get('jobRunId') or '').strip():
    try:
      _persist_completed_run_record(_RUN_TYPE, trade_dates[-1], payload, decorated, mode='AUTOMATION', stage='pipeline')
    except Exception:
      logger.exception('Unable to persist NSE MCAP automation run for tradeDate=%s', _iso_date(trade_dates[-1]))
  return decorated


def get_mcap_trade_date_row_count(trade_date: Any, *, source: str = 'file') -> int:
  target_trade_date = _parse_date(trade_date, 'tradeDate') if not isinstance(trade_date, dt.date) else trade_date
  source_key = str(source or 'file').strip().lower()
  if source_key not in {'file', 'quote', 'all'}:
    raise ValueError('source must be one of: file, quote, all.')
  conn = _acquire_connection()
  if conn is None:
    return 0
  try:
    ensure_runtime(conn)
    with conn.cursor() as cur:
      if source_key == 'all':
        cur.execute(
          f'''SELECT COUNT(*)
                FROM {_TABLE_SQL}
               WHERE trade_date = :trade_date''',
          {'trade_date': target_trade_date},
        )
      else:
        source_name = _FILE_SOURCE if source_key == 'file' else _QUOTE_SOURCE
        cur.execute(
          f'''SELECT COUNT(*)
                FROM {_TABLE_SQL}
               WHERE trade_date = :trade_date
                 AND source_name = :source_name''',
          {'trade_date': target_trade_date, 'source_name': source_name},
        )
      row = cur.fetchone()
      return int(row[0] or 0) if row else 0
  finally:
    try:
      conn.close()
    except Exception:
      pass


def _safe_mcap_trade_date_row_count(trade_date: Any, *, source: str = 'file') -> int:
  try:
    return get_mcap_trade_date_row_count(trade_date, source=source)
  except Exception as exc:
    logger.warning(
      'NSE MCAP row-count verification failed trade_date=%s source=%s error=%s',
      trade_date,
      source,
      exc,
    )
    return 0


def run_mcap_pipeline_for_trade_date(
  trade_date: Any,
  *,
  force: bool = False,
  automation: bool = False,
  eq_only: Optional[bool] = None,
  enrich_limit: Optional[int] = None,
  symbols: Optional[Sequence[str]] = None,
  line_logger: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
  target_trade_date = _parse_date(trade_date, 'tradeDate') if not isinstance(trade_date, dt.date) else trade_date
  target_iso = _iso_date(target_trade_date)
  if not force:
    existing_file_rows = get_mcap_trade_date_row_count(target_trade_date, source='file')
    if existing_file_rows > 0:
      return {
        'ok': True,
        'status': 'ALREADY_EXISTS',
        'done': True,
        'tradeDate': target_iso,
        'message': _duplicate_trade_date_message(target_trade_date),
        'counts': {'insertedRows': 0, 'existingRows': existing_file_rows},
      }
  payload: Dict[str, Any] = {
    'tradeDate': target_iso,
    'eqOnly': _EQ_ONLY_DEFAULT if eq_only is None else bool(eq_only),
    'autoInsertAfterDownload': True,
  }
  if enrich_limit not in (None, ''):
    payload['enrichLimit'] = int(enrich_limit)
  if symbols:
    clean_symbols = [str(item or '').strip().upper() for item in symbols if str(item or '').strip()]
    if clean_symbols:
      payload['symbols'] = ','.join(clean_symbols)
  if force:
    payload['force'] = True
  if automation:
    payload['automation'] = True
  result = run_pipeline(payload, line_logger=line_logger)
  normalized = dict(result or {})
  status = _status_token(normalized.get('status')) or _final_status_from_result(normalized)
  normalized['status'] = status
  normalized['done'] = True
  normalized['ok'] = status not in _JOB_FAILURE_STATUSES and status != 'FAILED'
  normalized.setdefault('tradeDate', target_iso)
  return normalized


def _load_existing_mcap_csv(
  csv_path: Path,
  trade_date: dt.date,
  *,
  eq_only: bool,
  allowed_symbols: Optional[Sequence[str]],
  line_logger: Optional[Callable[[str], None]],
) -> Dict[str, Any]:
  return load_mcap_csv(
    csv_path,
    trade_date,
    eq_only=eq_only,
    allowed_symbols=allowed_symbols,
    line_logger=line_logger,
    skip_if_existing=True,
  )


def process_existing_csv_for_symbols_api(payload: Dict[str, Any]) -> Dict[str, Any]:
  request_payload = payload if isinstance(payload, dict) else {}
  configured_dir = request_payload.get('downloadDir') or request_payload.get('download_dir')
  download_dir = Path(str(configured_dir).strip()) if str(configured_dir or '').strip() else _download_dir()
  config = existing_csv_svc.ExistingCsvDatasetConfig(
    dataset_type='market_cap',
    download_dir=download_dir,
    parse_trade_date=_trade_date_from_mcap_csv,
    inspect_csv=inspect_mcap_csv,
    load_csv=_load_existing_mcap_csv,
  )
  return existing_csv_svc.process_existing_csv_for_symbols(
    request_payload.get('symbols') or request_payload.get('symbol'),
    config,
    symbol_file_path=request_payload.get('symbolFilePath') or request_payload.get('symbol_file_path'),
    eq_only=_coerce_bool(request_payload.get('eqOnly'), _EQ_ONLY_DEFAULT),
  )


def _cleanup_jobs(now_ts: float) -> None:
  removed = prune_finished_jobs(
    _JOBS,
    now_ts=now_ts,
    ttl_seconds=_JOB_TTL_SEC,
    max_finished_items=_JOB_MAX_RETAINED,
  )
  if removed:
    logger.info('Pruned %s completed NSE MCAP job(s) from private memory.', len(removed))


def _empty_job_stats() -> Dict[str, Any]:
  return {
    'totalSymbolsProcessed': 0,
    'totalRecordsDownloaded': 0,
    'totalRecordsValidated': 0,
    'totalRecordsInserted': 0,
    'totalFailed': 0,
    'totalSkipped': 0,
    'insertPerformed': False,
  }


def _clone_request_payload(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
  if not payload or not isinstance(payload, dict):
    return {}
  try:
    return json.loads(json.dumps(payload, default=_json_default, ensure_ascii=True))
  except Exception:
    return dict(payload)


def _normalize_timestamp_text(value: Any) -> Optional[str]:
  if value is None or value == '':
    return None
  if isinstance(value, dt.datetime):
    return value.replace(microsecond=0).isoformat() + ('Z' if value.tzinfo is None else '')
  if isinstance(value, dt.date):
    return dt.datetime.combine(value, dt.time()).replace(microsecond=0).isoformat() + 'Z'
  text = str(value).strip()
  if not text:
    return None
  match = re.match(r'^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})$', text)
  if match:
    return f'{match.group(1)}T{match.group(2)}Z'
  return text


def _timestamp_text_to_epoch(value: Any) -> Optional[float]:
  text = _normalize_timestamp_text(value)
  if not text:
    return None
  token = str(text).strip()
  if token.endswith('Z'):
    token = token[:-1] + '+00:00'
  try:
    parsed = dt.datetime.fromisoformat(token)
  except ValueError:
    return None
  if parsed.tzinfo is None:
    parsed = parsed.replace(tzinfo=dt.timezone.utc)
  return parsed.timestamp()


def _is_abandoned_persisted_job(job: Dict[str, Any], *, now_ts: Optional[float] = None) -> bool:
  if not _is_job_active_status(job.get('status')):
    return False
  reference_ts = (
    _timestamp_text_to_epoch(job.get('updatedAt'))
    or _timestamp_text_to_epoch(job.get('startedAt'))
    or _timestamp_text_to_epoch(job.get('finishedAt'))
  )
  if reference_ts is None:
    return True
  current_ts = float(now_ts if now_ts is not None else time.time())
  return (current_ts - reference_ts) >= _ABANDONED_JOB_MAX_AGE_SECONDS


def _mark_abandoned_job_failed(job: Dict[str, Any], detail: Optional[str] = None, *, when_ts: Optional[float] = None) -> Dict[str, Any]:
  now_ts = float(when_ts if when_ts is not None else time.time())
  now_at = _utc_timestamp(now_ts)
  flow_payload = _serialize_job_flow(job.get('flow'))
  active_key = str(flow_payload.get('failedKey') or flow_payload.get('activeKey') or '').strip().lower()
  if active_key not in _FLOW_KEYS:
    active_key = ''
  flow_payload['activeKey'] = ''
  flow_payload['failedKey'] = active_key
  flow_payload['detail'] = detail or 'Background job was interrupted before completion.'
  flow_payload['updatedAt'] = now_at
  flow_payload['finishedAt'] = now_at
  job['status'] = 'FAILED'
  job['message'] = flow_payload['detail']
  job['updatedAt'] = now_at
  job['finishedAt'] = now_at
  job['flow'] = flow_payload
  logs = list(job.get('logs') or [])
  note = f'[WARN] {flow_payload["detail"]}'
  if not logs or logs[-1] != note:
    logs.append(note)
  job['logs'] = logs
  return job


def _mark_abandoned_job_timed_out(job: Dict[str, Any], detail: Optional[str] = None, *, when_ts: Optional[float] = None) -> Dict[str, Any]:
  now_ts = float(when_ts if when_ts is not None else time.time())
  now_at = _utc_timestamp(now_ts)
  flow_payload = _serialize_job_flow(job.get('flow'))
  active_key = str(flow_payload.get('activeKey') or '').strip().lower()
  if active_key not in _FLOW_KEYS:
    active_key = ''
  flow_payload['activeKey'] = ''
  flow_payload['failedKey'] = active_key
  flow_payload['detail'] = detail or 'Background job exceeded the configured timeout.'
  flow_payload['updatedAt'] = now_at
  flow_payload['finishedAt'] = now_at
  job['status'] = 'TIMED_OUT'
  job['message'] = flow_payload['detail']
  job['updatedAt'] = now_at
  job['finishedAt'] = now_at
  job['flow'] = flow_payload
  logs = list(job.get('logs') or [])
  note = f'[WARN] {flow_payload["detail"]}'
  if not logs or logs[-1] != note:
    logs.append(note)
  job['logs'] = logs
  return job


def _stage_statuses(flow: Optional[Dict[str, Any]]) -> Dict[str, str]:
  current = _serialize_job_flow(flow)
  completed = current.get('completed') or {}
  active_key = str(current.get('activeKey') or '').strip().lower()
  failed_key = str(current.get('failedKey') or '').strip().lower()
  finished_at = current.get('finishedAt')
  statuses: Dict[str, str] = {}
  for key in _FLOW_KEYS:
    if failed_key == key:
      statuses[key] = 'FAILED'
    elif bool(completed.get(key)):
      statuses[key] = 'COMPLETED'
    elif active_key == key and not finished_at:
      statuses[key] = 'WORKING'
    else:
      statuses[key] = 'NOT_STARTED'
  return statuses


def _job_snapshot_payload(job: Dict[str, Any], tail_lines: Optional[int] = None) -> Dict[str, Any]:
  return {'job': _serialize_job(job, tail_lines)}


def _serialize_job(job: Dict[str, Any], tail_lines: Optional[int]) -> Dict[str, Any]:
  tail = max(20, min(int(tail_lines or 180), 500))
  logs = list(job.get('logs') or [])
  flow_payload = _normalized_job_flow_snapshot(job.get('flow'), job.get('status'), finished_at=job.get('finishedAt') or job.get('updatedAt'))
  request_payload = _clone_request_payload(job.get('request') if isinstance(job.get('request'), dict) else {})
  stats_payload = job.get('stats') if isinstance(job.get('stats'), dict) else _empty_job_stats()
  counts_payload = _derive_job_counts(job)
  latest_rows = list(job.get('latestRows') or [])
  stage_status = _stage_statuses(flow_payload)
  failed_key = str(flow_payload.get('failedKey') or '').strip().lower()
  active_key = str(flow_payload.get('activeKey') or '').strip().lower()
  status_token = _status_token(job.get('status'))
  return {
    'ok': status_token not in _JOB_FAILURE_STATUSES and status_token != 'FAILED',
    'jobId': job.get('id'),
    'pipelineType': job.get('pipelineType') or job.get('jobType') or 'market-cap',
    'jobType': job.get('jobType'),
    'jobMode': job.get('jobMode') or 'pipeline',
    'status': job.get('status'),
    'done': _is_job_terminal_status(status_token),
    'message': job.get('message') or '',
    'startedAt': job.get('startedAt'),
    'updatedAt': job.get('updatedAt'),
    'finishedAt': job.get('finishedAt'),
    'currentStage': failed_key or active_key or ('success' if bool(flow_payload.get('completed', {}).get('success')) else ''),
    'stageStatus': stage_status,
    'request': request_payload,
    'result': job.get('result'),
    'downloadPath': job.get('downloadPath'),
    'flow': flow_payload,
    'counts': counts_payload,
    'stats': {
      'totalSymbolsProcessed': int(stats_payload.get('totalSymbolsProcessed') or 0),
      'totalRecordsDownloaded': int(stats_payload.get('totalRecordsDownloaded') or 0),
      'totalRecordsValidated': int(stats_payload.get('totalRecordsValidated') or 0),
      'totalRecordsInserted': int(stats_payload.get('totalRecordsInserted') or 0),
      'totalFailed': int(stats_payload.get('totalFailed') or 0),
      'totalSkipped': int(stats_payload.get('totalSkipped') or 0),
      'insertPerformed': bool(stats_payload.get('insertPerformed')),
    },
    'latestRows': latest_rows,
    'symbolSource': job.get('symbolSource'),
    'progress': job.get('progress'),
    'logs': {'tail': logs[-tail:], 'totalLines': len(logs)},
  }


def _db_run_status(job_status: Any) -> str:
  token = _status_token(job_status)
  return token or 'IDLE'


def _save_run_snapshot(run_id: str, status: str, message: str, job: Dict[str, Any], download_path: Optional[str] = None) -> None:
  conn = _acquire_connection()
  try:
    with conn.cursor() as cur:
      cur.execute(
        f'''UPDATE {_RUNS_TABLE_SQL}
               SET STATUS = :status,
                   MESSAGE = :message,
                   DOWNLOAD_FILE_PATH = CASE
                     WHEN :download_file_path IS NOT NULL THEN :download_file_path
                     ELSE DOWNLOAD_FILE_PATH
                   END,
                   METRICS_JSON = :metrics_json
             WHERE RUN_ID = :run_id''',
        {
          'run_id': run_id,
          'status': status,
          'message': str(message or '')[:4000],
          'download_file_path': (download_path or '')[:1000] or None,
          'metrics_json': json.dumps(_job_snapshot_payload(job), default=_json_default, ensure_ascii=True),
        },
      )
    conn.commit()
  finally:
    conn.close()


def _maybe_persist_job_snapshot(run_id: str, job: Dict[str, Any], *, force: bool = False) -> None:
  now_ts = time.time()
  last_ts = float(job.get('_lastSnapshotPersistTs') or 0.0)
  if not force and (now_ts - last_ts) < 2.0:
    return
  job['_lastSnapshotPersistTs'] = now_ts
  try:
    _save_run_snapshot(
      run_id,
      _db_run_status(job.get('status')),
      str(job.get('message') or ''),
      job,
      download_path=job.get('downloadPath'),
    )
  except Exception:
    logger.exception('Unable to persist NSE MCAP job snapshot run_id=%s', run_id)


def _safe_text_payload(value: Any, *, label: str = 'payload') -> str:
  if value is None:
    return ''
  try:
    if hasattr(value, 'read') and callable(value.read):
      value = value.read()
    return str(value or '').strip()
  except Exception as exc:
    logger.warning('Unable to read persisted NSE job %s text: %s', label, exc)
    return ''


def _safe_json_payload(value: Any) -> Dict[str, Any]:
  if isinstance(value, dict):
    return value
  text = _safe_text_payload(value, label='json')
  if not text:
    return {}
  try:
    loaded = json.loads(text)
    return loaded if isinstance(loaded, dict) else {}
  except Exception:
    return {}


def _persisted_job_from_row(row: Dict[str, Any], tail_lines: Optional[int]) -> Dict[str, Any]:
  request_payload = _safe_json_payload(row.get('request_json'))
  metrics_payload = _safe_json_payload(row.get('metrics_json'))
  snapshot = metrics_payload.get('job') if isinstance(metrics_payload.get('job'), dict) else {}
  snapshot_logs = snapshot.get('logs', {}).get('tail') if isinstance(snapshot.get('logs'), dict) else []
  logs_text = _safe_text_payload(row.get('logs_clob'), label='logs')
  logs = logs_text.splitlines() if logs_text else list(snapshot_logs or [])
  status_token = _status_token(snapshot.get('status') or row.get('status'))
  job = {
    'id': snapshot.get('jobId') or row.get('run_id'),
    'jobType': snapshot.get('jobType') or 'pipeline',
    'pipelineType': snapshot.get('pipelineType') or 'market-cap',
    'jobMode': snapshot.get('jobMode') or request_payload.get('jobMode') or 'pipeline',
    'status': snapshot.get('status') or status_token or 'RUNNING',
    'message': snapshot.get('message') or row.get('message') or '',
    'startedAt': snapshot.get('startedAt') or _normalize_timestamp_text(row.get('started_ts')),
    'updatedAt': snapshot.get('updatedAt') or snapshot.get('finishedAt') or _normalize_timestamp_text(row.get('finished_ts')) or _normalize_timestamp_text(row.get('started_ts')),
    'finishedAt': snapshot.get('finishedAt') or _normalize_timestamp_text(row.get('finished_ts')),
    'result': snapshot.get('result') or metrics_payload.get('result'),
    'downloadPath': snapshot.get('downloadPath') or row.get('download_file_path'),
    'request': snapshot.get('request') or request_payload,
    'flow': snapshot.get('flow') or _new_job_flow(row.get('message') or 'Preparing NSE extraction.'),
    'stats': snapshot.get('stats') or _empty_job_stats(),
    'latestRows': snapshot.get('latestRows') or [],
    'symbolSource': snapshot.get('symbolSource'),
    'progress': snapshot.get('progress'),
    'logs': logs,
  }
  if _is_job_active_status(job.get('status')):
    _mark_abandoned_job_timed_out(job, 'Recovered a persisted RUNNING job without a live worker. Marked it timed out to avoid stale reconnect state.')
    try:
      _save_run_finish(
        str(job.get('id') or row.get('run_id') or ''),
        'TIMED_OUT',
        str(job.get('message') or ''),
        snapshot.get('result') or metrics_payload.get('result') or {},
        list(job.get('logs') or []),
        job.get('downloadPath'),
        job=job,
      )
    except Exception:
      logger.exception('Unable to persist abandoned NSE job recovery run_id=%s', row.get('run_id'))
  return _serialize_job(job, tail_lines)


def _persisted_stage_result_from_row(row: Dict[str, Any], *, status: str = 'ALREADY_EXISTS', message: Optional[str] = None) -> Dict[str, Any]:
  job = _persisted_job_from_row(row, 180)
  result = dict(job.get('result') or {})
  request_payload = job.get('request') if isinstance(job.get('request'), dict) else {}
  trade_date = str(request_payload.get('tradeDate') or job.get('startedAt') or row.get('trade_date') or '').strip()
  result['ok'] = True
  result['done'] = True
  result['status'] = status
  result['message'] = message or _final_status_message(status, {'tradeDate': trade_date, 'request': request_payload, 'counts': job.get('counts')})
  result['tradeDate'] = result.get('tradeDate') or trade_date
  result['downloadPath'] = result.get('downloadPath') or job.get('downloadPath')
  result['request'] = request_payload
  result['counts'] = job.get('counts') or result.get('counts') or {}
  result['jobId'] = job.get('jobId')
  result['logicalDatasetKey'] = str(request_payload.get('logicalDatasetKey') or '')
  result['fileChecksum'] = str(request_payload.get('fileChecksum') or '')
  result['fileName'] = str(request_payload.get('fileName') or '')
  return result


def _duplicate_stage_result(payload: Dict[str, Any], *, message: Optional[str] = None) -> Optional[Dict[str, Any]]:
  if 'jobMode' not in (payload or {}) and 'jobRunId' not in (payload or {}):
    return None
  run_id = str((payload or {}).get('jobRunId') or '').strip()
  duplicate_row = _find_persisted_run_by_identity(
    payload,
    statuses=list(_JOB_ACTIVE_STATUSES | _JOB_NON_FAILURE_TERMINAL_STATUSES),
  )
  if not duplicate_row:
    return None
  duplicate_run_id = str(duplicate_row.get('run_id') or '').strip()
  if run_id and duplicate_run_id == run_id:
    return None
  duplicate_job = _persisted_job_from_row(duplicate_row, 180)
  duplicate_status = _status_token(duplicate_job.get('status'))
  if duplicate_status in _JOB_FAILURE_STATUSES or duplicate_status == 'TIMED_OUT':
    return None
  duplicate_message = message or ('NSE MCAP job is already running for this logical batch.' if duplicate_status in _JOB_ACTIVE_STATUSES else None)
  return _persisted_stage_result_from_row(duplicate_row, status='ALREADY_EXISTS', message=duplicate_message)


def _fetch_persisted_run_row(run_id: Optional[str] = None, run_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
  conn = _acquire_connection()
  try:
    ensure_runtime(conn)
    with conn.cursor() as cur:
      if run_id:
        cur.execute(
          f'''SELECT {_RUN_ROW_SELECT_SQL}
                FROM {_RUNS_TABLE_SQL}
               WHERE RUN_ID = :run_id''',
          {'run_id': run_id},
        )
      else:
        params: Dict[str, Any] = {}
        where_sql = ''
        if run_type:
          where_sql = 'WHERE RUN_TYPE = :run_type'
          params['run_type'] = run_type
        cur.execute(
          f'''SELECT * FROM (
                SELECT {_RUN_ROW_SELECT_SQL}
                  FROM {_RUNS_TABLE_SQL}
                  {where_sql}
                 ORDER BY STARTED_TS DESC
              ) WHERE ROWNUM = 1''',
          params,
        )
      row = cur.fetchone()
      return _row_to_dict(cur, row) if row else None
  finally:
    conn.close()


def _latest_in_memory_job() -> Optional[Dict[str, Any]]:
  with _JOBS_LOCK:
    _cleanup_jobs(time.time())
    jobs = list(_JOBS.values())
    if not jobs:
      return None
    running = [job for job in jobs if str(job.get('status') or '').strip().lower() == 'running']
    candidates = running or jobs
    candidates.sort(key=lambda item: str(item.get('startedAt') or ''), reverse=True)
    current = candidates[0]
    if _is_job_active_status(current.get('status')) and _is_abandoned_persisted_job(current):
      _mark_abandoned_job_timed_out(current, 'Background job exceeded the configured timeout.')
      try:
        _save_run_finish(
          str(current.get('id') or ''),
          'TIMED_OUT',
          str(current.get('message') or ''),
          current.get('result') or {},
          list(current.get('logs') or []),
          current.get('downloadPath'),
          job=current,
        )
      except Exception:
        logger.exception('Unable to persist timed out in-memory NSE job id=%s', current.get('id'))
    return dict(current)


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
  enrichment = result.get('enrichment') or {}
  total_inserted = int(load.get('loadedCount') or 0) + int(enrichment.get('successCount') or 0)
  total_failed = int(load.get('failureCount') or 0) + int(enrichment.get('failureCount') or 0)
  total_skipped = int(load.get('skippedCount') or 0) + int(load.get('universeSkippedCount') or 0) + int(enrichment.get('skippedCount') or 0)
  return {
    'totalSymbolsProcessed': max(int(enrichment.get('processed') or 0), int(inspection.get('matchedSymbolsCount') or 0), int(inspection.get('matchedRows') or 0)),
    'totalRecordsDownloaded': int(inspection.get('inputRows') or 0),
    'totalRecordsValidated': int(inspection.get('matchedRows') or 0),
    'totalRecordsInserted': total_inserted,
    'totalFailed': total_failed,
    'totalSkipped': total_skipped,
    'insertPerformed': total_inserted > 0,
  }


def _latest_rows_for_payload(payload: Dict[str, Any], *, allow_existing_rows: bool = False, limit: Optional[int] = None) -> List[Dict[str, Any]]:
  request_payload = _clone_request_payload(payload)
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
      logger.exception('Unable to refresh NSE MCAP latest rows from dashboard payload=%s', request_payload)
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
  trade_dates = _parse_trade_dates(
    payload.get('tradeDate') or payload.get('trade_date'),
    payload.get('startDate') or payload.get('start_date'),
    payload.get('endDate') or payload.get('end_date'),
    range_value=payload.get('range') or payload.get('dateRange') or payload.get('date_range'),
    allow_override=_allow_market_date_override(payload),
  )
  trade_date = trade_dates[-1]
  job_mode = _parse_job_mode(payload)
  request_payload = _job_request_metadata(payload)
  duplicate_row = _find_persisted_run_by_identity(request_payload, statuses=list(_JOB_ACTIVE_STATUSES | _JOB_NON_FAILURE_TERMINAL_STATUSES))
  if duplicate_row:
    duplicate_job = _persisted_job_from_row(duplicate_row, 180)
    duplicate_status = _status_token(duplicate_job.get('status'))
    if duplicate_status in _JOB_ACTIVE_STATUSES:
      return duplicate_job
    if duplicate_status in _JOB_NON_FAILURE_TERMINAL_STATUSES:
      duplicate_job['status'] = 'ALREADY_EXISTS'
      duplicate_job['done'] = True
      duplicate_job['ok'] = True
      duplicate_job['message'] = _final_status_message('ALREADY_EXISTS', {'tradeDate': _iso_date(trade_date), 'request': request_payload, 'counts': duplicate_job.get('counts')})
      return duplicate_job
  job_id = uuid.uuid4().hex
  request_payload['jobRunId'] = job_id
  job_message = 'Download job started.' if job_mode == 'download' else ('Pipeline job started.' if len(trade_dates) == 1 else f'Pipeline job started for {_trade_date_label(trade_dates)}.')
  flow_detail = 'Preparing download job.' if job_mode == 'download' else 'Preparing background pipeline.'
  job = {
    'id': job_id,
    'jobType': 'pipeline',
    'pipelineType': 'market-cap',
    'jobMode': job_mode,
    'status': 'RUNNING',
    'message': job_message,
    'startedAt': dt.datetime.utcnow().replace(microsecond=0).isoformat() + 'Z',
    'updatedAt': dt.datetime.utcnow().replace(microsecond=0).isoformat() + 'Z',
    'finishedAt': None,
    'finished_ts': 0.0,
    'request': request_payload,
    'result': None,
    'stats': _empty_job_stats(),
    'latestRows': [],
    'downloadPath': None,
    'logs': [],
    'flow': _new_job_flow(flow_detail),
  }
  def _worker() -> None:
    worker_payload = dict(request_payload)
    def _log(line: str) -> None:
      with _JOBS_LOCK:
        current = _JOBS.get(job_id)
        if not current or not line:
          return
        text = str(line).rstrip()
        marker = _parse_flow_marker(text)
        if marker:
          _advance_job_flow(current, marker[0], marker[1] or None)
        else:
          current['logs'].append(text)
          if len(current['logs']) > 1200:
            del current['logs'][: len(current['logs']) - 900]
        current['updatedAt'] = dt.datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'
        current['message'] = str(current.get('flow', {}).get('detail') or current.get('message') or job_message)
        _maybe_persist_job_snapshot(job_id, current, force=bool(marker))
    status = 'FAILED'
    message = 'Pipeline job failed.' if job_mode == 'pipeline' else 'Download job failed.'
    metrics: Dict[str, Any]
    download_path: Optional[str] = None
    try:
      metrics = download_api(worker_payload) if job_mode == 'download' else run_pipeline(worker_payload, _log)
      if metrics.get('ok'):
        with _JOBS_LOCK:
          current = _JOBS.get(job_id)
          if current:
            finalizing_detail = 'Finalizing download results.' if job_mode == 'download' else 'Finalizing NSE MCAP pipeline results.'
            _enter_job_finalizing_stage(current, finalizing_detail)
            _maybe_persist_job_snapshot(job_id, current, force=True)
      metrics = _enrich_job_result(request_payload, metrics)
      status = _status_token(metrics.get('status')) or _final_status_from_result(metrics)
      metrics['status'] = status
      metrics['done'] = _is_job_terminal_status(status)
      metrics['ok'] = status not in _JOB_FAILURE_STATUSES and status != 'FAILED'
      message = str(metrics.get('message') or _final_status_message(status, metrics))
      download_path = metrics.get('downloadPath')
    except Exception as exc:
      metrics = {'ok': False, 'error': str(exc), 'status': 'FAILED', 'message': str(exc)}
      message = str(exc)
      _log(f'[ERROR] {exc}')
      logger.exception('NSE MCAP pipeline job failed')
    with _JOBS_LOCK:
      current = _JOBS.get(job_id)
      logs = []
      if current:
        current_status = _status_token(current.get('status'))
        if _is_job_terminal_status(current_status) and current_status != status:
          current['status'] = current_status
          current['message'] = str(current.get('message') or message)
          current['updatedAt'] = dt.datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'
          current['finishedAt'] = current.get('finishedAt') or current['updatedAt']
          current['finished_ts'] = current.get('finished_ts') or time.time()
          logs = list(current.get('logs') or [])
          _save_run_finish(job_id, current_status, str(current.get('message') or message), current.get('result') or metrics, logs, current.get('downloadPath'), job=current)
          return
        current['status'] = status
        current['message'] = message
        current['updatedAt'] = dt.datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'
        current['finishedAt'] = current['updatedAt']
        current['finished_ts'] = time.time()
        current['result'] = metrics
        current['stats'] = metrics.get('stats') if isinstance(metrics, dict) else _empty_job_stats()
        current['latestRows'] = list(metrics.get('latestRows') or []) if isinstance(metrics, dict) else []
        current['downloadPath'] = download_path
        _finish_job_flow(current, status not in _JOB_FAILURE_STATUSES and status != 'FAILED', message, when_ts=current['finished_ts'])
        logs = list(current.get('logs') or [])
        _maybe_persist_job_snapshot(job_id, current, force=True)
    _save_run_finish(job_id, status, message, metrics, logs, download_path, job=current if current else None)
  with _JOBS_LOCK:
    _cleanup_jobs(time.time())
    _JOBS[job_id] = job
  _save_run_start(job_id, trade_date, 'PIPELINE', request_payload)
  _maybe_persist_job_snapshot(job_id, job, force=True)
  threading.Thread(target=_worker, daemon=True, name=f'nse-mcap-pipeline-{job_id[:8]}').start()
  return {'ok': True, 'jobId': job_id, 'jobType': 'pipeline', 'jobMode': job_mode, 'status': 'RUNNING', 'message': job_message, 'flow': _serialize_job_flow(job.get('flow'))}


def get_job(job_id: str, tail_lines: Optional[int] = None) -> Dict[str, Any]:
  token = str(job_id or '').strip()
  if not token:
    raise ValueError('jobId is required.')
  with _JOBS_LOCK:
    _cleanup_jobs(time.time())
    job = _JOBS.get(token)
    if job:
      if _is_job_active_status(job.get('status')) and _is_abandoned_persisted_job(job):
        _mark_abandoned_job_timed_out(job, 'Background job exceeded the configured timeout.')
        try:
          _save_run_finish(
            str(job.get('id') or token),
            'TIMED_OUT',
            str(job.get('message') or ''),
            job.get('result') or {},
            list(job.get('logs') or []),
            job.get('downloadPath'),
            job=job,
          )
        except Exception:
          logger.exception('Unable to persist timed out NSE job id=%s', token)
      return _serialize_job(job, tail_lines)
  persisted = _fetch_persisted_run_row(run_id=token)
  if persisted:
    return _persisted_job_from_row(persisted, tail_lines)
  raise ValueError(f'NSE MCAP job not found: {token}')


def get_latest_job(tail_lines: Optional[int] = None) -> Dict[str, Any]:
  memory_job = _latest_in_memory_job()
  if memory_job:
    return _serialize_job(memory_job, tail_lines)
  persisted = _fetch_persisted_run_row(run_type='PIPELINE')
  if persisted:
    return _persisted_job_from_row(persisted, tail_lines)
  raise ValueError('No NSE MCAP jobs found.')













