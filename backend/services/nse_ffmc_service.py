from __future__ import annotations

import datetime as dt
import importlib.util
import logging
import os
import re
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

try:  # Support running as package or as loose module
  from . import nifty500_sync_service as nifty500_svc
  from . import nse_data_overview_service as data_overview_svc
  from . import nse_existing_csv_symbol_service as existing_csv_svc
except ImportError:  # pragma: no cover
  from services import nifty500_sync_service as nifty500_svc  # type: ignore
  from services import nse_data_overview_service as data_overview_svc  # type: ignore
  from services import nse_existing_csv_symbol_service as existing_csv_svc  # type: ignore


def _load_ffmc_backend():
  module_path = Path(__file__).with_name('nse_mcap_service.py')
  backend_name = 'services._nse_ffmc_backend'
  env_updates = {
    'NSE_MCAP_TABLE': 'CVING_NSE_FFMC_HIST',
    'NSE_MCAP_RUNS_TABLE': 'CVING_NSE_FFMC_PIPELINE_RUNS',
    'NSE_MCAP_LATEST_VIEW': 'VW_CVING_NSE_FFMC_LATEST',
    'NSE_MCAP_SOURCE_NAME': 'NSE_FFMC_FILE',
    'NSE_MCAP_QUOTE_SOURCE_NAME': 'NSE_FFMC_QUOTE_API',
    'NSE_MCAP_CREATED_BY': 'CVING_NSE_FFMC_UI',
    'NSE_MCAP_DOWNLOAD_DIR': str(Path(__file__).resolve().parents[2] / 'batch' / 'nse_ffmc_data' / 'downloads'),
    'NSE_MCAP_REQUEST_TIMEOUT': '15',
    'NSE_MCAP_RETRY_COUNT': '2',
    'NSE_MCAP_MIN_SLEEP_SEC': '0.02',
    'NSE_MCAP_MAX_SLEEP_SEC': '0.08',
    'NSE_MCAP_ENRICH_BATCH_SIZE': '250',
    'NSE_MCAP_ENRICH_CONCURRENCY': '18',
  }
  saved_env = {key: os.environ.get(key) for key in env_updates}
  try:
    for key, value in env_updates.items():
      os.environ[key] = value
    spec = importlib.util.spec_from_file_location(backend_name, module_path)
    if spec is None or spec.loader is None:
      raise RuntimeError('Unable to load FFMC backend service.')
    module = importlib.util.module_from_spec(spec)
    sys.modules[backend_name] = module
    spec.loader.exec_module(module)
    return module
  finally:
    for key, value in saved_env.items():
      if value is None:
        os.environ.pop(key, None)
      else:
        os.environ[key] = value


mcap = _load_ffmc_backend()
logger = logging.getLogger(__name__)

_RUN_TYPE = 'FFMC'
_JOB_TTL_SEC = mcap._JOB_TTL_SEC
_MAX_ROWS = mcap._MAX_ROWS
_JOBS: Dict[str, Dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()
_PROGRESS_RE = re.compile(r'Quote enrichment progress (?P<current>\d+)/(?P<total>\d+)')
_UNIVERSE_RE = re.compile(r'FFMC symbol universe path=(?P<path>.+?) count=(?P<total>\d+)$')


def _symbol_source_details() -> Tuple[str, int]:
  path = str(nifty500_svc.resolve_existing_csv_path())
  try:
    symbols = nifty500_svc.load_existing_symbols(require_file=True)
    count = len([item for item in symbols if str(item or '').strip()])
  except Exception:
    count = 0
  return path, count


def _progress_payload(current: int = 0, total: int = 0, detail: str = 'Waiting for pipeline start.', phase: str = 'idle') -> Dict[str, Any]:
  total_value = max(0, int(total or 0))
  current_value = max(0, int(current or 0))
  if total_value > 0:
    current_value = min(current_value, total_value)
  percent = int(round((current_value / total_value) * 100)) if total_value > 0 else 0
  return {
    'current': current_value,
    'total': total_value,
    'percent': percent,
    'label': f'{current_value} / {total_value} symbols' if total_value > 0 else '0 / 0 symbols',
    'detail': detail,
    'phase': phase,
  }


def _parse_payload(payload: Dict[str, Any], line_logger: Optional[Callable[[str], None]] = None) -> Tuple[List[dt.date], bool, Optional[int], List[str], Optional[set[str]]]:
  return mcap._parse_runtime_payload(payload, line_logger=line_logger)



def init_runtime_api() -> Dict[str, Any]:
  payload = mcap.ensure_runtime()
  payload['message'] = 'FFMC runtime uses dedicated FFMC storage and quote enrichment tables.'
  return payload



def _supporting_file(payload: Dict[str, Any], line_logger: Optional[Callable[[str], None]] = None) -> Tuple[List[dt.date], bool, Optional[int], List[str], Optional[set[str]], str, Dict[str, Any]]:
  if line_logger:
    line_logger(mcap._flow_marker('download', 'Loading FFMC symbol universe.'))
  trade_dates, eq_only, enrich_limit, symbols, allowed_symbols = _parse_payload(payload, line_logger=line_logger)
  symbols_path = str(nifty500_svc.resolve_existing_csv_path())
  try:
    if allowed_symbols is None:
      allowed_symbols = nifty500_svc.load_existing_symbols(require_file=True)
      allowed_symbols = {str(item or '').strip().upper() for item in allowed_symbols if str(item or '').strip()}
  except Exception as exc:
    raise ValueError(f'Unable to load FFMC symbol universe from {symbols_path}: {exc}') from exc
  if not allowed_symbols:
    raise ValueError(f'No symbols are available for FFMC enrichment from {symbols_path}.')
  inspection = {
    'headers': ['SYMBOL'],
    'matchedSymbols': sorted(list(allowed_symbols or [])),
    'matchedSymbolsCount': len(allowed_symbols or []),
    'officialFfmcCsvAvailable': False,
    'symbolsPath': symbols_path,
    'symbolsCount': len(allowed_symbols or []),
    'nifty500Path': symbols_path,
    'inputRows': len(allowed_symbols or []),
    'universeSkippedRows': 0,
    'parseErrorRows': 0,
  }
  if line_logger:
    line_logger(mcap._flow_marker('validate', 'Validating FFMC symbol universe.'))
  return trade_dates, eq_only, enrich_limit, symbols, allowed_symbols, symbols_path, inspection



def _aggregate_inspection(results: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
  items = [result.get('inspection') or {} for result in results]
  matched_symbols = sorted({str(symbol).upper() for item in items for symbol in (item.get('matchedSymbols') or []) if str(symbol).strip()})
  all_already_loaded = bool(items) and all(bool(item.get('alreadyLoaded')) for item in items)
  return {
    'headers': next((list(item.get('headers') or []) for item in items if item.get('headers')), ['SYMBOL']),
    'matchedSymbols': matched_symbols,
    'matchedSymbolsCount': len(matched_symbols),
    'officialFfmcCsvAvailable': any(bool(item.get('officialFfmcCsvAvailable')) for item in items),
    'symbolsPath': next((item.get('symbolsPath') for item in items if item.get('symbolsPath')), None),
    'symbolsCount': max((int(item.get('symbolsCount') or 0) for item in items), default=0),
    'nifty500Path': next((item.get('nifty500Path') for item in items if item.get('nifty500Path')), None),
    'inputRows': sum(int(item.get('inputRows') or 0) for item in items),
    'universeSkippedRows': sum(int(item.get('universeSkippedRows') or 0) for item in items),
    'parseErrorRows': sum(int(item.get('parseErrorRows') or 0) for item in items),
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
    'alreadyLoadedCount': sum(int(item.get('alreadyLoadedCount') or 0) for item in items),
    'alreadyLoaded': all_already_loaded,
  }



def _result_already_loaded(result: Dict[str, Any]) -> bool:
  inspection = result.get('inspection') or {}
  load = result.get('load') or {}
  return bool(result.get('status') == 'ALREADY_EXISTS' or inspection.get('alreadyLoaded') or load.get('alreadyLoaded'))


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
      'skippedUnavailable': False,
      'skipReason': result.get('skipReason'),
      'skipCategory': result.get('skipCategory'),
    }
    for result in results
  ]



def _aggregate_stage_response(trade_dates: Sequence[dt.date], results: Sequence[Dict[str, Any]], message: str, *, include_load: bool = False, include_enrichment: bool = False, include_summary: bool = False) -> Dict[str, Any]:
  response: Dict[str, Any] = {'ok': all(bool(result.get('ok', True)) for result in results), 'message': message}
  response.update(mcap._date_context(trade_dates))
  download_paths = [str(result.get('downloadPath')) for result in results if result.get('downloadPath')]
  response['downloadPath'] = download_paths[-1] if download_paths else None
  if len(download_paths) > 1:
    response['downloadPaths'] = download_paths
  response['processedDateCount'] = sum(1 for result in results if not _result_already_loaded(result))
  response['skippedDateCount'] = sum(1 for result in results if _result_already_loaded(result))
  response['skippedUnavailableDateCount'] = 0
  response['skippedUnavailableDates'] = []
  response['skippedHolidayDates'] = []
  response['dateResults'] = _aggregate_date_results(results)
  response['inspection'] = _aggregate_inspection(results)
  if include_load:
    response['load'] = _aggregate_load(results)
  if include_enrichment:
    response['enrichment'] = _aggregate_enrichment(results)
  if include_summary:
    response['summary'] = get_dashboard(limit=None, start_date_text=mcap._iso_date(trade_dates[0]), end_date_text=mcap._iso_date(trade_dates[-1])).get('summary', {})
  status = mcap._final_status_from_result(response)
  if status in {'NO_ACTION', 'ALREADY_EXISTS'} and response.get('ok') and int(response.get('processedDateCount') or 0) > 0:
    status = 'PARTIAL'
  response['status'] = status
  response['done'] = True
  response['ok'] = status not in mcap._JOB_FAILURE_STATUSES and status != 'FAILED'
  return response



def _stage_message(base_message: str, trade_dates: Sequence[dt.date], results: Optional[Sequence[Dict[str, Any]]] = None) -> str:
  label = mcap._trade_date_label(trade_dates)
  result_items = list(results or [])
  if not result_items:
    return f'{base_message} for {label}.'
  already_loaded = [result for result in result_items if _result_already_loaded(result)]
  if result_items and len(already_loaded) == len(result_items):
    return mcap._duplicate_trade_date_message(trade_dates[-1]) if len(trade_dates) == 1 else f'Already data inserted for {label}.'
  suffix_parts: List[str] = []
  if already_loaded:
    suffix_parts.append(f'Skipped {len(already_loaded)} already-loaded trade date(s).')
  suffix = f" {' '.join(suffix_parts)}" if suffix_parts else ''
  return f'{base_message} for {label}.{suffix}'



def _target_symbols(override_symbols: List[str], allowed_symbols: Optional[set[str]], inspection: Dict[str, Any]) -> List[str]:
  return override_symbols or sorted(list(allowed_symbols or [])) or list(inspection.get('matchedSymbols') or [])


def _safe_ffmc_trade_date_row_count(trade_date: dt.date) -> int:
  try:
    return int(mcap._safe_mcap_trade_date_row_count(trade_date, source='all'))
  except Exception as exc:
    logger.warning('NSE FFMC row-count verification failed trade_date=%s error=%s', trade_date.strftime('%Y-%m-%d'), exc)
    return 0


def _ffmc_db_verification(trade_date: dt.date, rows_before: int, rows_after: int, load_summary: Dict[str, Any]) -> Dict[str, Any]:
  failed_rows = int(load_summary.get('failureCount') or 0)
  inserted_rows = int(load_summary.get('loadedCount') or 0)
  skipped_rows = int(load_summary.get('skippedCount') or 0) + int(load_summary.get('alreadyLoadedCount') or 0)
  return {
    'table': mcap._TABLE_SQL,
    'tradingDate': trade_date.strftime('%Y-%m-%d'),
    'rowCountBefore': int(rows_before or 0),
    'rowCountAfter': int(rows_after or 0),
    'insertedRows': inserted_rows,
    'updatedRows': 0,
    'skippedRows': skipped_rows,
    'failedRows': failed_rows,
    'commitConfirmed': rows_after >= rows_before and failed_rows == 0,
  }



def _clone_stage_result(base_result: Dict[str, Any], trade_date: dt.date) -> Dict[str, Any]:
  clone: Dict[str, Any] = {'ok': bool(base_result.get('ok', True)), 'tradeDate': trade_date.strftime('%Y-%m-%d')}
  for key in ('message', 'downloadPath'):
    clone[key] = base_result.get(key)
  for key in ('inspection', 'load', 'enrichment', 'summary'):
    value = base_result.get(key)
    clone[key] = dict(value) if isinstance(value, dict) else value
  return clone



def _load_mcap_file_fallback(
  trade_date: dt.date,
  target_symbols: List[str],
  line_logger: Optional[Callable[[str], None]] = None,
) -> Tuple[Optional[str], Dict[str, Any], Optional[str]]:
  if not target_symbols:
    return None, {'loadedCount': 0, 'failureCount': 0, 'skippedCount': 0, 'alreadyLoaded': False}, 'No symbols were available for MCAP file fallback.'
  try:
    if line_logger:
      line_logger(mcap._flow_marker('download', f'Loading official NSE MCAP CSV fallback for {trade_date.strftime("%Y-%m-%d")}.'))
    csv_path = mcap.download_mcap_csv(trade_date, line_logger=line_logger)
    if line_logger:
      line_logger(mcap._flow_marker('process', f'Inserting NSE MCAP CSV fallback rows for {trade_date.strftime("%Y-%m-%d")}.'))
    load_summary = mcap.load_mcap_csv(
      csv_path,
      trade_date,
      eq_only=True,
      allowed_symbols=target_symbols,
      line_logger=line_logger,
    )
    return str(csv_path), load_summary, None
  except Exception as exc:
    if line_logger:
      line_logger(f'[WARN] FFMC MCAP CSV fallback failed :: {exc}')
    return None, {'loadedCount': 0, 'failureCount': 1, 'skippedCount': 0, 'alreadyLoaded': False}, str(exc)


def _load_has_inserted_or_existing_rows(load_summary: Dict[str, Any]) -> bool:
  return (
    int(load_summary.get('loadedCount') or 0) > 0
    or bool(load_summary.get('alreadyLoaded'))
    or int(load_summary.get('alreadyLoadedCount') or 0) > 0
  )


def _load_existing_ffmc_csv(
  csv_path: Path,
  trade_date: dt.date,
  *,
  eq_only: bool,
  allowed_symbols: Optional[Sequence[str]],
  line_logger: Optional[Callable[[str], None]],
) -> Dict[str, Any]:
  return mcap.load_mcap_csv(
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
  download_dir = Path(str(configured_dir).strip()) if str(configured_dir or '').strip() else mcap._download_dir()
  config = existing_csv_svc.ExistingCsvDatasetConfig(
    dataset_type='ffmc',
    download_dir=download_dir,
    parse_trade_date=mcap._trade_date_from_mcap_csv,
    inspect_csv=mcap.inspect_mcap_csv,
    load_csv=_load_existing_ffmc_csv,
  )
  return existing_csv_svc.process_existing_csv_for_symbols(
    request_payload.get('symbols') or request_payload.get('symbol'),
    config,
    symbol_file_path=request_payload.get('symbolFilePath') or request_payload.get('symbol_file_path'),
    eq_only=mcap._coerce_bool(request_payload.get('eqOnly'), mcap._EQ_ONLY_DEFAULT),
  )



def _read_lob_value(value: Any) -> Any:
  if hasattr(value, 'read') and callable(getattr(value, 'read')):
    return value.read()
  return value



def _source_quote_rows(source_trade_date: dt.date, target_symbols: List[str]) -> List[Dict[str, Any]]:
  normalized_symbols = []
  seen: set[str] = set()
  for symbol in target_symbols:
    token = str(symbol or '').strip().upper()
    if token and token not in seen:
      seen.add(token)
      normalized_symbols.append(token)
  if not normalized_symbols:
    return []
  conn = mcap.pool.acquire()
  try:
    mcap.ensure_runtime(conn)
    rows: List[Dict[str, Any]] = []
    with conn.cursor() as cur:
      for start_idx in range(0, len(normalized_symbols), 900):
        chunk = normalized_symbols[start_idx:start_idx + 900]
        symbol_binds = {f'sym{idx}': symbol for idx, symbol in enumerate(chunk)}
        placeholders = ', '.join(f':sym{idx}' for idx in range(len(chunk)))
        binds: Dict[str, Any] = {'trade_date': source_trade_date, 'quote_source': mcap._QUOTE_SOURCE}
        binds.update(symbol_binds)
        cur.execute(
          f'''SELECT symbol, source_name, series, security_name, raw_total_mcap, raw_total_mcap_unit,
                     total_mcap_cr, raw_ffmc, raw_ffmc_unit, ffmc_cr, response_payload, fetch_status, error_message
                FROM {mcap._TABLE_SQL}
               WHERE trade_date = :trade_date
                 AND source_name = :quote_source
                 AND symbol IN ({placeholders})''',
          binds,
        )
        for row in cur.fetchall() or []:
          rows.append({
            'trade_date': source_trade_date,
            'symbol': str(row[0] or '').strip().upper(),
            'source_name': str(row[1] or '').strip().upper() or mcap._QUOTE_SOURCE,
            'series': row[2],
            'security_name': row[3],
            'raw_total_mcap': row[4],
            'raw_total_mcap_unit': row[5],
            'total_mcap_cr': row[6],
            'raw_ffmc': row[7],
            'raw_ffmc_unit': row[8],
            'ffmc_cr': row[9],
            'response_payload': _read_lob_value(row[10]),
            'fetch_status': row[11],
            'error_message': row[12],
            'created_by': getattr(mcap, '_CREATED_BY', None),
          })
    return rows
  finally:
    conn.close()



def _copy_quote_rows_to_dates(source_trade_date: dt.date, target_dates: List[dt.date], target_symbols: List[str], line_logger: Optional[Callable[[str], None]] = None) -> int:
  reusable_dates = [trade_date for trade_date in target_dates if trade_date != source_trade_date]
  if not reusable_dates:
    return 0
  source_rows = _source_quote_rows(source_trade_date, target_symbols)
  if not source_rows:
    raise ValueError(f'No FFMC quote rows are available to reuse for {source_trade_date.strftime("%d-%m-%Y")}.')
  if line_logger:
    line_logger(f'[INFO] Reusing FFMC quote snapshot from {source_trade_date.strftime("%Y-%m-%d")} for {len(reusable_dates)} additional trade date(s).')
  copied_rows = 0
  for index, trade_date in enumerate(reusable_dates, start=1):
    batch = [{**record, 'trade_date': trade_date} for record in source_rows]
    ok_count, bad_count = mcap._upsert_records(batch)
    if bad_count:
      raise RuntimeError(f'FFMC range copy failed for {trade_date.strftime("%Y-%m-%d")}: ok={ok_count} bad={bad_count}')
    copied_rows += ok_count
    if line_logger:
      line_logger(f'[INFO] Reused FFMC quote snapshot for tradeDate={trade_date.strftime("%Y-%m-%d")} rows={ok_count} copyStep={index}/{len(reusable_dates)}')
  return copied_rows



def _process_range(trade_dates: List[dt.date], enrich_limit: Optional[int], target_symbols: List[str], symbols_path: str, inspection: Dict[str, Any], line_logger: Optional[Callable[[str], None]] = None, *, pipeline_mode: bool = False) -> Dict[str, Any]:
  if not target_symbols:
    raise ValueError('No symbols are available for FFMC enrichment.')
  already_loaded_dates = [trade_date for trade_date in trade_dates if _safe_ffmc_trade_date_row_count(trade_date) > 0]
  pending_dates = [trade_date for trade_date in trade_dates if trade_date not in already_loaded_dates]
  if not pending_dates:
    results = [
      _process_api_single(trade_date, enrich_limit, target_symbols, symbols_path, inspection, line_logger=line_logger, pipeline_mode=pipeline_mode)
      for trade_date in trade_dates
    ]
    message = _stage_message('NSE FFMC pipeline completed' if pipeline_mode else 'FFMC enrichment completed', trade_dates, results)
    return _aggregate_stage_response(trade_dates, results, message, include_load=True, include_enrichment=True, include_summary=True)
  source_trade_date = pending_dates[-1]
  if line_logger:
    line_logger(f'[INFO] FFMC range optimization sourceTradeDate={source_trade_date.strftime("%Y-%m-%d")} requestedTradeDates={len(trade_dates)} symbolCount={len(target_symbols)} alreadyLoadedDates={len(already_loaded_dates)}')
  base_result = _process_api_single(source_trade_date, enrich_limit, target_symbols, symbols_path, inspection, line_logger=line_logger, pipeline_mode=pipeline_mode)
  if not bool(base_result.get('ok', True)):
    results = [
      _process_api_single(trade_date, enrich_limit, target_symbols, symbols_path, inspection, line_logger=line_logger, pipeline_mode=pipeline_mode)
      if trade_date in already_loaded_dates else
      _clone_stage_result(base_result, trade_date)
      for trade_date in trade_dates
    ]
    message = str(base_result.get('message') or ('FFMC pipeline failed.' if pipeline_mode else 'FFMC enrichment failed.'))
    return _aggregate_stage_response(trade_dates, results, message, include_load=True, include_enrichment=True, include_summary=False)
  copied_rows = _copy_quote_rows_to_dates(source_trade_date, pending_dates[:-1], target_symbols, line_logger=line_logger)
  if line_logger and copied_rows:
    line_logger(f'[INFO] FFMC range reuse inserted {copied_rows} copied row(s) without additional NSE quote calls.')
  results = [
    _process_api_single(trade_date, enrich_limit, target_symbols, symbols_path, inspection, line_logger=line_logger, pipeline_mode=pipeline_mode)
    if trade_date in already_loaded_dates else
    _clone_stage_result(base_result, trade_date)
    for trade_date in trade_dates
  ]
  message = _stage_message('NSE FFMC pipeline completed' if pipeline_mode else 'FFMC enrichment completed', trade_dates, results)
  return _aggregate_stage_response(trade_dates, results, message, include_load=True, include_enrichment=True, include_summary=True)



def _download_api_single(trade_date: dt.date, symbols_path: str, inspection: Dict[str, Any]) -> Dict[str, Any]:
  message = f'FFMC symbol universe loaded from {symbols_path}.'
  return {
    'ok': True,
    'message': message,
    'tradeDate': trade_date.strftime('%Y-%m-%d'),
    'downloadPath': symbols_path,
    'inspection': dict(inspection),
  }



def download_api(payload: Dict[str, Any]) -> Dict[str, Any]:
  trade_dates, _eq_only, _enrich_limit, _symbols, _allowed_symbols, symbols_path, inspection = _supporting_file(payload)
  if len(trade_dates) == 1:
    return mcap._apply_run_contract_fields(_download_api_single(trade_dates[0], symbols_path, inspection), page='FFMC', mode='MANUAL', stage='download')
  results = [_download_api_single(trade_date, symbols_path, inspection) for trade_date in trade_dates]
  return mcap._apply_run_contract_fields(_aggregate_stage_response(trade_dates, results, _stage_message('FFMC symbol universe loaded', trade_dates, results)), page='FFMC', mode='MANUAL', stage='download')



def _validate_api_single(trade_date: dt.date, symbols_path: str, inspection: Dict[str, Any]) -> Dict[str, Any]:
  message = f'FFMC symbol validation completed using {symbols_path}.'
  return {
    'ok': True,
    'message': message,
    'tradeDate': trade_date.strftime('%Y-%m-%d'),
    'downloadPath': symbols_path,
    'inspection': dict(inspection),
  }



def validate_api(payload: Dict[str, Any]) -> Dict[str, Any]:
  trade_dates, _eq_only, _enrich_limit, _symbols, _allowed_symbols, symbols_path, inspection = _supporting_file(payload)
  if len(trade_dates) == 1:
    return mcap._apply_run_contract_fields(_validate_api_single(trade_dates[0], symbols_path, inspection), page='FFMC', mode='MANUAL', stage='validate')
  results = [_validate_api_single(trade_date, symbols_path, inspection) for trade_date in trade_dates]
  return mcap._apply_run_contract_fields(_aggregate_stage_response(trade_dates, results, _stage_message('FFMC symbol validation completed', trade_dates, results)), page='FFMC', mode='MANUAL', stage='validate')



def _process_api_single(trade_date: dt.date, enrich_limit: Optional[int], target_symbols: List[str], symbols_path: str, inspection: Dict[str, Any], line_logger: Optional[Callable[[str], None]] = None, *, pipeline_mode: bool = False) -> Dict[str, Any]:
  if not target_symbols:
    raise ValueError('No symbols are available for FFMC enrichment.')
  rows_before = _safe_ffmc_trade_date_row_count(trade_date)
  if rows_before > 0:
    message = mcap._duplicate_trade_date_message(trade_date).strip()
    load_summary = {
      'inputRows': 0,
      'loadedCount': 0,
      'failureCount': 0,
      'skippedCount': 0,
      'alreadyLoaded': True,
      'alreadyLoadedCount': rows_before,
    }
    inspection_payload = dict(inspection)
    inspection_payload['alreadyLoaded'] = True
    inspection_payload['alreadyLoadedCount'] = rows_before
    if line_logger:
      line_logger(f'[INFO] {message} existingRows={rows_before}')
    return {
      'ok': True,
      'status': 'ALREADY_EXISTS',
      'done': True,
      'message': message,
      'tradeDate': trade_date.strftime('%Y-%m-%d'),
      'downloadPath': symbols_path,
      'inspection': inspection_payload,
      'load': load_summary,
      'enrichment': {'requested': 0, 'processed': 0, 'successCount': 0, 'failureCount': 0, 'skippedCount': 0, 'elapsedSec': 0.0},
      'summary': _get_dashboard_single(trade_date.strftime('%Y-%m-%d')).get('summary', {}),
      'dbVerification': _ffmc_db_verification(trade_date, rows_before, rows_before, load_summary),
    }
  if line_logger:
    line_logger(mcap._flow_marker('process', f'Extracting FFMC quote data for {trade_date.strftime("%Y-%m-%d")}.'))
    line_logger(f"[INFO] FFMC symbol universe path={inspection.get('symbolsPath')} count={len(target_symbols)}")
    line_logger(f"[INFO] FFMC quote workers={getattr(mcap, '_ENRICH_CONCURRENCY', 1)} batchSize={getattr(mcap, '_ENRICH_BATCH_SIZE', 25)} timeoutSec={getattr(mcap, '_TIMEOUT_SEC', 25)}")
  enrichment_summary = mcap.enrich_quotes(trade_date, limit=enrich_limit, symbols=target_symbols, line_logger=line_logger)
  load_summary = {
    'inputRows': int(enrichment_summary.get('requested') or len(target_symbols) or 0),
    'loadedCount': int(enrichment_summary.get('successCount') or 0),
    'failureCount': int(enrichment_summary.get('failureCount') or 0),
    'skippedCount': int(enrichment_summary.get('skippedCount') or 0),
    'alreadyLoaded': False,
  }
  fallback_path: Optional[str] = None
  fallback_error: Optional[str] = None
  if mcap._enrichment_summary_failed(enrichment_summary):
    if line_logger:
      line_logger('[WARN] FFMC quote enrichment produced zero usable rows; falling back to official NSE MCAP CSV values.')
    fallback_path, fallback_load, fallback_error = _load_mcap_file_fallback(trade_date, target_symbols, line_logger=line_logger)
    if _load_has_inserted_or_existing_rows(fallback_load):
      load_summary = fallback_load
      load_summary.setdefault('inputRows', int(inspection.get('matchedSymbolsCount') or len(target_symbols) or 0))
  rows_after = _safe_ffmc_trade_date_row_count(trade_date)
  try:
    dashboard_summary = _get_dashboard_single(trade_date.strftime('%Y-%m-%d')).get('summary', {})
  except Exception as exc:
    dashboard_summary = {}
    if line_logger:
      log_label = 'pipeline' if pipeline_mode else 'enrichment'
      line_logger(f'[WARN] FFMC dashboard refresh failed after {log_label} :: {exc}')
  fallback_ok = _load_has_inserted_or_existing_rows(load_summary)
  ok = not mcap._enrichment_summary_failed(enrichment_summary) or fallback_ok
  message = 'NSE FFMC pipeline completed.' if pipeline_mode else 'FFMC enrichment completed.'
  if fallback_ok and mcap._enrichment_summary_failed(enrichment_summary):
    message = 'NSE FFMC pipeline completed using official NSE MCAP CSV fallback.' if pipeline_mode else 'FFMC enrichment completed using official NSE MCAP CSV fallback.'
  elif not ok:
    message = 'NSE FFMC pipeline failed during Oracle insert. No quote or fallback rows were written to Oracle.' if pipeline_mode else 'FFMC enrichment failed. No quote or fallback rows were written to Oracle.'
  result = {
    'ok': ok,
    'status': 'SUCCESS' if ok else 'FAILED',
    'done': True,
    'message': message,
    'tradeDate': trade_date.strftime('%Y-%m-%d'),
    'downloadPath': fallback_path or symbols_path,
    'inspection': dict(inspection),
    'load': load_summary,
    'enrichment': enrichment_summary,
    'summary': dashboard_summary,
    'fallback': {'source': 'NSE_MCAP_FILE', 'downloadPath': fallback_path, 'error': fallback_error} if fallback_path or fallback_error else None,
    'dbVerification': _ffmc_db_verification(trade_date, rows_before, rows_after, load_summary),
  }
  status = 'FAILED' if not ok else mcap._final_status_from_result(result)
  result['status'] = status
  result['ok'] = status not in {'FAILED', 'CANCELLED', 'TIMED_OUT'}
  if status != 'SUCCESS' and result['ok']:
    result['message'] = mcap._final_status_message(status, result)
  return result



def process_api(payload: Dict[str, Any], line_logger: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
  trade_dates, _eq_only, enrich_limit, override_symbols, allowed_symbols, symbols_path, inspection = _supporting_file(payload, line_logger=line_logger)
  target_symbols = _target_symbols(override_symbols, allowed_symbols, inspection)
  if len(trade_dates) == 1:
    result = _process_api_single(trade_dates[0], enrich_limit, target_symbols, symbols_path, inspection, line_logger=line_logger)
  else:
    result = _process_range(trade_dates, enrich_limit, target_symbols, symbols_path, inspection, line_logger=line_logger)
  decorated = mcap._apply_run_contract_fields(result, page='FFMC', mode='MANUAL', stage='process')
  try:
    mcap._persist_completed_run_record(_RUN_TYPE, trade_dates[-1], payload, decorated, mode='MANUAL', stage='process')
  except Exception:
    logger.exception('Unable to persist NSE FFMC manual process run for tradeDate=%s', mcap._iso_date(trade_dates[-1]))
  return decorated



def _get_data_overview(trade_date: Optional[dt.date], conn: Any = None, start_date: Optional[dt.date] = None, end_date: Optional[dt.date] = None) -> Dict[str, Any]:
  own_conn = conn is None
  connection = conn or mcap.pool.acquire()
  try:
    if own_conn:
      mcap.ensure_runtime(connection)
    return data_overview_svc.build_overview(connection, mcap._TABLE_SQL, trade_date, start_date=start_date, end_date=end_date)
  finally:
    if own_conn:
      connection.close()


def get_trading_day_verification(year: Optional[int] = None, as_of_date: Optional[dt.date] = None) -> Dict[str, Any]:
  conn = mcap.pool.acquire()
  try:
    return mcap.build_trading_day_verification(conn, mcap._TABLE_SQL, 'FFMC', year=year, as_of_date=as_of_date)
  finally:
    conn.close()


def _get_dashboard_single(trade_date_text: Optional[str] = None, limit: Optional[int] = None, include_overview: bool = True) -> Dict[str, Any]:
  conn = mcap.pool.acquire()
  try:
    mcap.ensure_runtime(conn)
    trade_date = mcap._parse_date(trade_date_text, 'tradeDate') if trade_date_text else mcap._business_date()
    overview: Dict[str, Any] = {}
    with conn.cursor() as cur:
      cur.execute(f"SELECT MAX(TRADE_DATE) FROM {mcap._TABLE_SQL} WHERE TRADE_DATE = :trade_date AND SOURCE_NAME = :quote_source AND FETCH_STATUS IN ('SUCCESS', 'PARTIAL')", {'trade_date': trade_date, 'quote_source': mcap._QUOTE_SOURCE})
      if (cur.fetchone() or [None])[0] is None:
        cur.execute(f"SELECT MAX(TRADE_DATE) FROM {mcap._TABLE_SQL} WHERE SOURCE_NAME = :quote_source AND FETCH_STATUS IN ('SUCCESS', 'PARTIAL')", {'quote_source': mcap._QUOTE_SOURCE})
        latest = (cur.fetchone() or [None])[0]
        if latest is not None and not trade_date_text:
          trade_date = mcap._parse_date(latest, 'tradeDate')
      if include_overview:
        overview = _get_data_overview(trade_date, conn=conn)
      cur.execute(
        f'''WITH quote_rows AS (
              SELECT * FROM (
                SELECT t.symbol, t.total_mcap_cr, t.ffmc_cr, t.fetch_status,
                     ROW_NUMBER() OVER (
                       PARTITION BY t.symbol
                       ORDER BY t.fetch_ts DESC NULLS LAST, t.updated_ts DESC NULLS LAST, t.id DESC NULLS LAST
                     ) rn
                FROM {mcap._TABLE_SQL} t
                WHERE t.trade_date = :trade_date
                  AND t.source_name = :quote_source
              ) WHERE rn = 1
            ),
            file_rows AS (
              SELECT * FROM (
                SELECT t.symbol, t.total_mcap_cr, t.fetch_status,
                       ROW_NUMBER() OVER (
                         PARTITION BY t.symbol
                         ORDER BY t.fetch_ts DESC NULLS LAST, t.updated_ts DESC NULLS LAST, t.id DESC NULLS LAST
                       ) rn
                FROM {mcap._TABLE_SQL} t
                WHERE t.trade_date = :trade_date
                  AND t.source_name = :file_source
              ) WHERE rn = 1
            ),
            summary_stats AS (
              SELECT COUNT(*) total_rows,
                     COUNT(DISTINCT symbol) distinct_symbols,
                     SUM(CASE WHEN fetch_status IN ('SUCCESS', 'PARTIAL') THEN 1 ELSE 0 END) success_rows,
                     SUM(CASE WHEN fetch_status IN ('FAILED', 'PARSE_ERROR') THEN 1 ELSE 0 END) failure_rows,
                     SUM(CASE WHEN fetch_status = 'SKIPPED' THEN 1 ELSE 0 END) skipped_rows,
                     NVL(SUM(total_mcap_cr), 0) total_mcap_cr_sum
              FROM (
                SELECT COALESCE(quote_rows.symbol, file_rows.symbol) symbol,
                       COALESCE(quote_rows.total_mcap_cr, file_rows.total_mcap_cr) total_mcap_cr,
                       CASE
                         WHEN quote_rows.fetch_status IN ('SUCCESS', 'PARTIAL') THEN quote_rows.fetch_status
                         WHEN file_rows.fetch_status IN ('SUCCESS', 'PARTIAL') THEN 'SUCCESS'
                         ELSE COALESCE(quote_rows.fetch_status, file_rows.fetch_status, 'FAILED')
                       END fetch_status
                FROM quote_rows
                FULL OUTER JOIN file_rows
                  ON file_rows.symbol = quote_rows.symbol
              )
            ),
            raw_stats AS (
              SELECT MAX(fetch_ts) latest_fetch_ts
              FROM {mcap._TABLE_SQL}
              WHERE trade_date = :trade_date
                AND source_name IN (:quote_source, :file_source)
            ),
            ffmc_total AS (
              SELECT COUNT(*) ffmc_rows,
                     NVL(SUM(ffmc_cr), 0) ffmc_cr_sum
              FROM (
                SELECT CASE
                         WHEN quote_rows.fetch_status IN ('SUCCESS', 'PARTIAL') THEN quote_rows.ffmc_cr
                         WHEN file_rows.fetch_status IN ('SUCCESS', 'PARTIAL') THEN file_rows.total_mcap_cr
                         ELSE NULL
                       END ffmc_cr
                FROM quote_rows
                FULL OUTER JOIN file_rows
                  ON file_rows.symbol = quote_rows.symbol
              )
              WHERE ffmc_cr IS NOT NULL
            )
            SELECT s.total_rows, s.distinct_symbols, r.latest_fetch_ts,
                   s.success_rows, s.failure_rows, s.skipped_rows,
                   f.ffmc_rows, s.total_mcap_cr_sum, f.ffmc_cr_sum
            FROM summary_stats s
            CROSS JOIN raw_stats r
            CROSS JOIN ffmc_total f''',
        {'trade_date': trade_date, 'quote_source': mcap._QUOTE_SOURCE, 'file_source': mcap._FILE_SOURCE}
      )
      summary_row = mcap._row_to_dict(cur, cur.fetchone() or [])
      try:
        requested_limit = int(limit) if limit not in (None, '') else 0
      except (TypeError, ValueError):
        requested_limit = 0
      row_limit = requested_limit if requested_limit > 0 else int(summary_row.get('distinct_symbols') or 0)
      row_limit = max(1, row_limit)
      cur.execute(
        f'''WITH quote_rows AS (
              SELECT * FROM (
                SELECT t.trade_date, t.symbol, t.raw_total_mcap, t.raw_total_mcap_unit, t.total_mcap_cr,
                       t.raw_ffmc, t.raw_ffmc_unit, t.ffmc_cr,
                       t.fetch_status, t.error_message, t.fetch_ts,
                       ROW_NUMBER() OVER (
                         PARTITION BY t.symbol
                         ORDER BY t.fetch_ts DESC, t.updated_ts DESC, t.id DESC
                       ) rn
                FROM {mcap._TABLE_SQL} t
                WHERE t.trade_date = :trade_date
                  AND t.source_name = :quote_source
              ) WHERE rn = 1
            ),
            file_rows AS (
              SELECT * FROM (
                SELECT t.trade_date, t.symbol, t.series, t.security_name,
                       t.raw_total_mcap, t.raw_total_mcap_unit, t.total_mcap_cr,
                       t.fetch_status,
                       ROW_NUMBER() OVER (
                         PARTITION BY t.symbol
                         ORDER BY t.fetch_ts DESC, t.updated_ts DESC, t.id DESC
                       ) rn
                FROM {mcap._TABLE_SQL} t
                WHERE t.trade_date = :trade_date
                  AND t.source_name = :file_source
              ) WHERE rn = 1
            )
            SELECT trade_date, symbol, source_name, series, security_name, raw_total_mcap, raw_total_mcap_unit,
                   total_mcap_cr, raw_ffmc, raw_ffmc_unit, ffmc_cr, fetch_status, inserted_rows, error_message, fetch_ts
            FROM (
              SELECT COALESCE(quote_rows.trade_date, file_rows.trade_date) AS trade_date,
                     COALESCE(quote_rows.symbol, file_rows.symbol) AS symbol,
                     CASE
                       WHEN quote_rows.fetch_status IN ('SUCCESS', 'PARTIAL') THEN quote_rows.fetch_status
                       WHEN file_rows.fetch_status IN ('SUCCESS', 'PARTIAL') THEN 'SUCCESS'
                       ELSE COALESCE(quote_rows.fetch_status, 'FAILED')
                     END AS fetch_status,
                     CASE
                       WHEN quote_rows.fetch_status IN ('SUCCESS', 'PARTIAL') THEN 1
                       WHEN file_rows.fetch_status IN ('SUCCESS', 'PARTIAL') THEN 1
                       ELSE 0
                     END AS inserted_rows,
                     CASE
                       WHEN quote_rows.fetch_status IN ('SUCCESS', 'PARTIAL') THEN quote_rows.error_message
                       WHEN file_rows.fetch_status IN ('SUCCESS', 'PARTIAL') THEN 'Quote API unavailable; official NSE MCAP CSV fallback used.'
                       ELSE quote_rows.error_message
                     END AS error_message,
                     COALESCE(quote_rows.fetch_ts, file_rows.trade_date) AS fetch_ts,
                     COALESCE(quote_rows.raw_total_mcap, file_rows.raw_total_mcap) AS raw_total_mcap,
                     COALESCE(quote_rows.raw_total_mcap_unit, file_rows.raw_total_mcap_unit) AS raw_total_mcap_unit,
                     COALESCE(quote_rows.total_mcap_cr, file_rows.total_mcap_cr) AS total_mcap_cr,
                     COALESCE(quote_rows.raw_ffmc, file_rows.raw_total_mcap) AS raw_ffmc,
                     COALESCE(quote_rows.raw_ffmc_unit, file_rows.raw_total_mcap_unit) AS raw_ffmc_unit,
                     COALESCE(quote_rows.ffmc_cr, file_rows.total_mcap_cr) AS ffmc_cr,
                     COALESCE(file_rows.series, 'EQ') AS series,
                     file_rows.security_name,
                     CASE
                       WHEN quote_rows.symbol IS NOT NULL AND file_rows.symbol IS NOT NULL THEN :file_source || ' + ' || :quote_source
                       WHEN file_rows.symbol IS NOT NULL THEN :file_source
                       ELSE :quote_source
                     END AS source_name,
                     ROW_NUMBER() OVER (ORDER BY COALESCE(quote_rows.symbol, file_rows.symbol)) rn
              FROM quote_rows
              FULL OUTER JOIN file_rows
                ON file_rows.symbol = quote_rows.symbol
            ) WHERE rn <= :limit_value
            ORDER BY symbol''',
        {'trade_date': trade_date, 'quote_source': mcap._QUOTE_SOURCE, 'file_source': mcap._FILE_SOURCE, 'limit_value': row_limit}
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

    symbol_path, symbol_count = _symbol_source_details()
    return mcap._apply_trade_date_metadata({
      'ok': True,
      'tradeDate': trade_date.strftime('%Y-%m-%d'),
      'downloadDir': str(mcap._download_dir()),
      'summary': mcap._apply_insertion_summary_metadata({
        'totalRows': int(summary_row.get('total_rows') or 0),
        'distinctSymbols': int(summary_row.get('distinct_symbols') or 0),
        'latestFetchTs': summary_row.get('latest_fetch_ts'),
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
      'sources': {'file': mcap._FILE_SOURCE, 'quote': mcap._QUOTE_SOURCE},
      'symbolSource': {'path': symbol_path, 'count': symbol_count, 'label': 'NIFTY500 local universe'},
      'objects': {'table': mcap._TABLE_SQL, 'runsTable': mcap._RUNS_TABLE_SQL, 'view': mcap._LATEST_VIEW_SQL},
      'notes': {
        'officialFfmcCsvAvailable': False,
        'supportingCsvType': 'MCAP CSV extracted from PR archive when needed',
      },
      'dataOverview': overview,
    }, trade_date)
  finally:
    conn.close()


def _get_dashboard_all(limit: Optional[int] = None) -> Dict[str, Any]:
  conn = mcap.pool.acquire()
  try:
    mcap.ensure_runtime(conn)
    with conn.cursor() as cur:
      cur.execute(
        f'''SELECT MAX(TRADE_DATE) latest_trade_date
              FROM {mcap._TABLE_SQL}
             WHERE SOURCE_NAME IN (:quote_source, :file_source) AND FETCH_STATUS IN ('SUCCESS', 'PARTIAL')''',
        {'quote_source': mcap._QUOTE_SOURCE, 'file_source': mcap._FILE_SOURCE},
      )
      latest_row = mcap._row_to_dict(cur, cur.fetchone() or [])
      latest_trade_date = latest_row.get('latest_trade_date')
    latest_trade_text = ''
    latest_payload: Dict[str, Any] = {'rows': [], 'recentRuns': [], 'symbolSource': {'path': '', 'count': 0, 'label': 'NIFTY500 local universe'}}
    if latest_trade_date:
      latest_trade_text = mcap._iso_date(latest_trade_date)
      latest_payload = _get_dashboard_single(latest_trade_text, limit=limit, include_overview=False)
    symbol_path, symbol_count = _symbol_source_details()
    summary = dict(latest_payload.get('summary') or {})
    if not summary:
      summary = mcap._apply_insertion_summary_metadata({
        'totalRows': 0,
        'distinctSymbols': 0,
        'latestFetchTs': None,
        'successRows': 0,
        'failureRows': 0,
        'skippedRows': 0,
        'ffmcRows': 0,
        'totalMcapCrSum': 0.0,
        'ffmcCrSum': 0.0,
      })
    return mcap._apply_trade_date_metadata({
      'ok': True,
      'tradeDate': latest_trade_text,
      'downloadDir': str(mcap._download_dir()),
      'summary': summary,
      'rows': latest_payload.get('rows') or [],
      'recentRuns': latest_payload.get('recentRuns') or [],
      'sources': {'file': mcap._FILE_SOURCE, 'quote': mcap._QUOTE_SOURCE},
      'symbolSource': {'path': symbol_path, 'count': symbol_count, 'label': 'NIFTY500 local universe'},
      'objects': {'table': mcap._TABLE_SQL, 'runsTable': mcap._RUNS_TABLE_SQL, 'view': mcap._LATEST_VIEW_SQL},
      'notes': {
        'officialFfmcCsvAvailable': False,
        'supportingCsvType': 'MCAP CSV extracted from PR archive when needed',
      },
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



def run_pipeline(payload: Dict[str, Any], line_logger: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
  trade_dates, _eq_only, enrich_limit, override_symbols, allowed_symbols, symbols_path, inspection = _supporting_file(payload, line_logger=line_logger)
  target_symbols = _target_symbols(override_symbols, allowed_symbols, inspection)
  if len(trade_dates) == 1:
    result = _process_api_single(trade_dates[0], enrich_limit, target_symbols, symbols_path, inspection, line_logger=line_logger, pipeline_mode=True)
  else:
    result = _process_range(trade_dates, enrich_limit, target_symbols, symbols_path, inspection, line_logger=line_logger, pipeline_mode=True)
  decorated = mcap._apply_run_contract_fields(result, page='FFMC', mode='AUTOMATION', stage='pipeline')
  if not str((payload or {}).get('jobRunId') or '').strip():
    try:
      mcap._persist_completed_run_record(_RUN_TYPE, trade_dates[-1], payload, decorated, mode='AUTOMATION', stage='pipeline')
    except Exception:
      logger.exception('Unable to persist NSE FFMC automation run for tradeDate=%s', mcap._iso_date(trade_dates[-1]))
  return decorated



def _cleanup_jobs(now_ts: float) -> None:
  removed = mcap.prune_finished_jobs(
    _JOBS,
    now_ts=now_ts,
    ttl_seconds=_JOB_TTL_SEC,
    max_finished_items=mcap._JOB_MAX_RETAINED,
  )
  if removed:
    logger.info('Pruned %s completed NSE FFMC job(s) from private memory.', len(removed))



def _serialize_job(job: Dict[str, Any], tail_lines: Optional[int]) -> Dict[str, Any]:
  payload = mcap._serialize_job(job, tail_lines)
  payload['symbolSource'] = job.get('symbolSource')
  payload['progress'] = job.get('progress') or _progress_payload()
  return payload


def _parse_job_mode(payload: Dict[str, Any]) -> str:
  raw = str(payload.get('jobMode') or payload.get('job_mode') or '').strip().lower()
  if not raw or raw == 'pipeline':
    return 'pipeline'
  if raw in {'download', 'download-only', 'download_only'}:
    return 'download'
  raise ValueError('jobMode must be "download" or "pipeline".')



def _job_stats_from_result(result: Dict[str, Any]) -> Dict[str, Any]:
  enrichment = result.get('enrichment') or {}
  inspection = result.get('inspection') or {}
  load = result.get('load') or {}
  requested = int(enrichment.get('requested') or 0)
  validated = int(inspection.get('matchedSymbolsCount') or inspection.get('symbolsCount') or requested)
  inserted = max(int(enrichment.get('successCount') or 0), int(load.get('loadedCount') or 0))
  return {
    'totalSymbolsProcessed': int(enrichment.get('processed') or requested or validated),
    'totalRecordsDownloaded': requested or validated,
    'totalRecordsValidated': validated,
    'totalRecordsInserted': inserted,
    'totalFailed': int(load.get('failureCount') or 0),
    'totalSkipped': int(enrichment.get('skippedCount') or 0) + int(load.get('skippedCount') or 0) + int(load.get('alreadyLoadedCount') or 0),
    'insertPerformed': inserted > 0,
  }


def _latest_rows_for_payload(payload: Dict[str, Any], limit: Optional[int] = None) -> List[Dict[str, Any]]:
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
    logger.exception('Unable to refresh NSE FFMC latest rows from payload=%s', request_payload)
    return []


def _enrich_job_result(payload: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
  enriched = dict(result or {})
  enriched['stats'] = _job_stats_from_result(enriched)
  enriched['latestRows'] = _latest_rows_for_payload(payload) if enriched.get('ok') else []
  return enriched


def start_pipeline_job(payload: Dict[str, Any]) -> Dict[str, Any]:
  mcap.ensure_runtime()
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
    logger.warning('Unable to check active NSE FFMC pipeline run; continuing with start request.', exc_info=True)
  if duplicate_row:
    duplicate_job = mcap._persisted_job_from_row(duplicate_row, 180)
    duplicate_status = mcap._status_token(duplicate_job.get('status'))
    if duplicate_status in mcap._JOB_ACTIVE_STATUSES:
      duplicate_job['message'] = str(duplicate_job.get('message') or 'NSE FFMC job is already running for this logical batch.')
      return duplicate_job
  source_path, source_count = _symbol_source_details()
  job_id = uuid.uuid4().hex
  job_message = 'FFMC download job started.' if job_mode == 'download' else ('FFMC pipeline job started.' if len(trade_dates) == 1 else f'FFMC pipeline job started for {mcap._trade_date_label(trade_dates)}.')
  job = {
    'id': job_id,
    'jobType': 'ffmc',
    'pipelineType': 'ffmc',
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
    'symbolSource': {'path': source_path, 'count': source_count, 'label': 'NIFTY500 local universe'},
    'progress': _progress_payload(0, source_count, 'Preparing NSE extraction.', 'ready'),
    'logs': [],
    'flow': mcap._new_job_flow('Preparing background pipeline.' if job_mode == 'pipeline' else 'Preparing download job.'),
  }

  def _worker() -> None:
    def _log(line: str) -> None:
      with _JOBS_LOCK:
        current = _JOBS.get(job_id)
        if not current or not line:
          return
        text = str(line).rstrip()
        marker = mcap._parse_flow_marker(text)
        if marker:
          mcap._advance_job_flow(current, marker[0], marker[1] or None)
        else:
          current['logs'].append(text)
          if len(current['logs']) > 1200:
            del current['logs'][: len(current['logs']) - 900]
          universe_match = _UNIVERSE_RE.search(text)
          progress_match = _PROGRESS_RE.search(text)
          if universe_match:
            total = int(universe_match.group('total') or 0)
            current['symbolSource'] = {'path': universe_match.group('path').strip(), 'count': total, 'label': 'NIFTY500 local universe'}
            current['progress'] = _progress_payload(0, total, 'Preparing NSE extraction.', 'ready')
          elif progress_match:
            current_count = int(progress_match.group('current') or 0)
            total = int(progress_match.group('total') or 0)
            current['progress'] = _progress_payload(current_count, total, 'Extracting FFMC data from NSE quote API.', 'extracting')
        current['updatedAt'] = dt.datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'
        current['message'] = str(current.get('flow', {}).get('detail') or current.get('progress', {}).get('detail') or current.get('message') or job_message)
        mcap._maybe_persist_job_snapshot(job_id, current, force=bool(marker))

    status = 'FAILED'
    message = 'FFMC pipeline job failed.'
    metrics: Dict[str, Any]
    download_path: Optional[str] = None
    try:
      metrics = download_api(payload) if job_mode == 'download' else run_pipeline(payload, _log)
      if metrics.get('ok'):
        with _JOBS_LOCK:
          current = _JOBS.get(job_id)
          if current:
            finalizing_detail = 'Finalizing FFMC download results.' if job_mode == 'download' else 'Finalizing NSE FFMC pipeline results.'
            mcap._enter_job_finalizing_stage(current, finalizing_detail)
            progress_total = int(current.get('progress', {}).get('total') or 0)
            progress_current = int(current.get('progress', {}).get('current') or progress_total or 0)
            current['progress'] = _progress_payload(progress_current or progress_total, progress_total, finalizing_detail, 'finalizing')
            mcap._maybe_persist_job_snapshot(job_id, current, force=True)
      metrics = _enrich_job_result(request_payload, metrics)
      status = mcap._status_token(metrics.get('status')) or mcap._final_status_from_result(metrics)
      has_pipeline_counts = any(
        metrics.get(key) is not None
        for key in ('rowsInserted', 'rowsSkipped', 'rowsFailed', 'totalRowsProcessed')
      ) or isinstance(metrics.get('load'), dict) or isinstance(metrics.get('inspection'), dict) or isinstance(metrics.get('counts'), dict)
      if status in {'NO_ACTION', 'ALREADY_EXISTS'} and metrics.get('ok') and not has_pipeline_counts:
        status = 'SUCCESS'
      if not status:
        status = 'SUCCESS' if metrics.get('ok') else 'FAILED'
      message = str(metrics.get('message') or ('FFMC download completed.' if job_mode == 'download' else 'FFMC pipeline completed.'))
      download_path = metrics.get('downloadPath')
    except Exception as exc:
      metrics = {'ok': False, 'error': str(exc)}
      message = str(exc)
      _log(f'[ERROR] {exc}')
      logger.exception('NSE FFMC pipeline job failed')
    with _JOBS_LOCK:
      current = _JOBS.get(job_id)
      logs = []
      if current:
        enrichment = metrics.get('enrichment') if isinstance(metrics, dict) else {}
        requested = int((enrichment or {}).get('requested') or current.get('progress', {}).get('total') or 0)
        processed = int((enrichment or {}).get('processed') or current.get('progress', {}).get('current') or 0)
        detail = f"Success={int((enrichment or {}).get('successCount') or 0)} Failure={int((enrichment or {}).get('failureCount') or 0)} Skipped={int((enrichment or {}).get('skippedCount') or 0)}"
        phase = 'completed' if status == 'SUCCESS' else 'failed'
        current['status'] = status
        current['message'] = message
        current['updatedAt'] = dt.datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'
        current['finishedAt'] = current['updatedAt']
        current['finished_ts'] = time.time()
        current['result'] = metrics
        current['stats'] = metrics.get('stats') if isinstance(metrics, dict) else mcap._empty_job_stats()
        current['latestRows'] = list(metrics.get('latestRows') or []) if isinstance(metrics, dict) else []
        current['downloadPath'] = download_path
        current['progress'] = _progress_payload(processed or requested, requested, detail if requested else message, phase)
        mcap._finish_job_flow(current, status == 'SUCCESS', message, when_ts=current['finished_ts'])
        logs = list(current.get('logs') or [])
        mcap._maybe_persist_job_snapshot(job_id, current, force=True)
    mcap._save_run_finish(job_id, status, message, metrics, logs, download_path, job=current if current else None)

  with _JOBS_LOCK:
    _cleanup_jobs(time.time())
    _JOBS[job_id] = job
  mcap._save_run_start(job_id, trade_date, _RUN_TYPE, payload)
  mcap._maybe_persist_job_snapshot(job_id, job, force=True)
  threading.Thread(target=_worker, daemon=True, name=f'nse-ffmc-pipeline-{job_id[:8]}').start()
  return {'ok': True, 'jobId': job_id, 'jobType': 'ffmc', 'jobMode': job_mode, 'status': 'running', 'message': job_message, 'symbolSource': job['symbolSource'], 'progress': job['progress'], 'flow': mcap._serialize_job_flow(job.get('flow'))}



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
  raise ValueError(f'NSE FFMC job not found: {token}')


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
  raise ValueError('No NSE FFMC jobs found.')
