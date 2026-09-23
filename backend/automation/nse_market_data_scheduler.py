from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence, Set, Tuple

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
  sys.path.insert(0, str(BACKEND_ROOT))

try:  # Package import path
  from ..app.utils import market_calendar
  from ..services import automation_status_service as status_svc
  from ..services import nse_delivery_service as nse_delivery_svc
  from ..services import nse_ffmc_service as nse_ffmc_svc
  from ..services import nse_mcap_service as nse_mcap_svc
except ImportError:  # pragma: no cover
  try:
    from app.utils import market_calendar  # type: ignore
    from services import automation_status_service as status_svc  # type: ignore
    from services import nse_delivery_service as nse_delivery_svc  # type: ignore
    from services import nse_ffmc_service as nse_ffmc_svc  # type: ignore
    from services import nse_mcap_service as nse_mcap_svc  # type: ignore
  except ImportError:
    from backend.app.utils import market_calendar  # type: ignore
    from backend.services import automation_status_service as status_svc  # type: ignore
    from backend.services import nse_delivery_service as nse_delivery_svc  # type: ignore
    from backend.services import nse_ffmc_service as nse_ffmc_svc  # type: ignore
    from backend.services import nse_mcap_service as nse_mcap_svc  # type: ignore


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "nse_marketdata_automation.json"
HOLIDAY_PATH = PROJECT_ROOT / "config" / "nse_holidays.json"
LOG_PATH = PROJECT_ROOT / "logs" / "nse_marketdata_automation.log"
LOCK_PATH = PROJECT_ROOT / "runtime" / "locks" / "nse_marketdata_automation.lock"

STATUS_STARTED = "STARTED"
STATUS_OUTSIDE_WINDOW = "SKIPPED_OUTSIDE_WINDOW"
STATUS_HOLIDAY = "SKIPPED_MARKET_HOLIDAY"
STATUS_LOADED = "SKIPPED_ALREADY_LOADED"
STATUS_RUNNING = "SKIPPED_ALREADY_RUNNING"
STATUS_RETRY = "DATA_NOT_AVAILABLE_RETRY_LATER"
STATUS_PREVIOUS_PENDING = "PREVIOUS_TRADE_DATE_PENDING"
STATUS_WAITING_5PM = "WAITING_FOR_5PM_WINDOW"
STATUS_CURRENT_RETRYING = "CURRENT_TRADE_DATE_RETRYING"
STATUS_SUCCESS = "SUCCESS"
STATUS_FAILED = "FAILED"
STATUS_SKIPPED = "SKIPPED"

MODULE_MCAP = "mcap"
MODULE_FFMC = "ffmc"
MODULE_DELIVERY = "delivery"
MODULES = (MODULE_MCAP, MODULE_FFMC, MODULE_DELIVERY)

RUNTIME_STATUS_SUCCESS = "SUCCESS"
RUNTIME_STATUS_FAILED = "FAILED"
RUNTIME_STATUS_RETRY = "DATA_NOT_AVAILABLE_RETRY_LATER"
RUNTIME_STATUS_RUNNING = "RUNNING"
RUNTIME_STATUS_IDLE = "IDLE"
RUNTIME_STATUS_SKIPPED = "SKIPPED"
RUNTIME_STATUS_PREVIOUS_PENDING = STATUS_PREVIOUS_PENDING
RUNTIME_STATUS_WAITING_5PM = STATUS_WAITING_5PM
RUNTIME_STATUS_CURRENT_RETRYING = STATUS_CURRENT_RETRYING

TARGET_PREVIOUS = "PREVIOUS_TRADING_DATE"
TARGET_CURRENT = "CURRENT_TRADING_DATE"
MODULE_SOURCE_TABLES = getattr(status_svc, "MODULE_SOURCE_TABLES", {
  MODULE_MCAP: "CVING_NSE_MARKET_CAP_HIST",
  MODULE_FFMC: "CVING_NSE_FFMC_HIST",
  MODULE_DELIVERY: "CVING_NSE_DELIVERY_HIST",
})

DEFAULT_CONFIG: Dict[str, Any] = {
  "enabled": True,
  "window_start": "17:00",
  "window_end": "09:00",
  "current_day_start_time": "17:00",
  "previous_trade_date_retry_until_success": True,
  "current_trade_date_retry_until_success": True,
  "retry_minutes": 5,
  "max_retry_hours_for_previous_pending": 72,
  "modules": {
    MODULE_MCAP: True,
    MODULE_FFMC: True,
    MODULE_DELIVERY: True,
  },
  "refresh_ui_after_success": True,
  "skip_if_rows_exist": True,
  "min_rows_threshold": {
    MODULE_MCAP: 1,
    MODULE_FFMC: 1,
    MODULE_DELIVERY: 1,
  },
}
_AUTO_SCHEDULER_STARTED = False
_AUTO_SCHEDULER_LOCK = threading.Lock()


def _safe_int(value: Any, default: int = 0) -> int:
  try:
    return int(value)
  except Exception:
    return int(default)


def _first_non_negative_int(*values: Any) -> int:
  for value in values:
    number = _safe_int(value, -1)
    if number >= 0:
      return number
  return 0


def _first_positive_int(*values: Any) -> int:
  for value in values:
    number = _safe_int(value, -1)
    if number > 0:
      return number
  return 0


def _parse_hhmm(value: str, *, field_name: str) -> dt.time:
  text = str(value or "").strip()
  try:
    return dt.datetime.strptime(text, "%H:%M").time()
  except ValueError as exc:
    raise ValueError(f"Invalid {field_name} value: {text!r}. Expected HH:MM.") from exc


def _coerce_bool(value: Any, default: bool = False) -> bool:
  if isinstance(value, bool):
    return value
  token = str(value or "").strip().lower()
  if token in {"1", "true", "yes", "y", "on"}:
    return True
  if token in {"0", "false", "no", "n", "off"}:
    return False
  return bool(default)


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
  merged: Dict[str, Any] = dict(base)
  for key, value in (override or {}).items():
    if isinstance(merged.get(key), dict) and isinstance(value, dict):
      merged[key] = _deep_merge(dict(merged[key]), value)
    else:
      merged[key] = value
  return merged


def _load_json(path: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
  if not path.exists():
    return None, f"Config file not found: {path}"
  try:
    data = json.loads(path.read_text(encoding="utf-8"))
  except Exception as exc:
    return None, f"Unable to read JSON file {path}: {exc}"
  if not isinstance(data, dict):
    return None, f"Invalid JSON object in {path}"
  return data, None


def _load_scheduler_config() -> Tuple[Dict[str, Any], Optional[str]]:
  payload, error = _load_json(CONFIG_PATH)
  if payload is None:
    return dict(DEFAULT_CONFIG), error
  return _deep_merge(DEFAULT_CONFIG, payload), None


def _retry_interval_seconds() -> int:
  config, _ = _load_scheduler_config()
  retry_minutes = max(1, _safe_int(config.get("retry_minutes"), _safe_int(DEFAULT_CONFIG.get("retry_minutes"), 5)))
  return max(60, retry_minutes * 60)


def _load_holidays() -> Tuple[Set[dt.date], Optional[str]]:
  holidays: Set[dt.date] = set(market_calendar.get_nse_holidays(2026))
  if not HOLIDAY_PATH.exists():
    return holidays, f"Holiday file not found: {HOLIDAY_PATH}. Using built-in NSE 2026 holiday calendar."
  try:
    payload = json.loads(HOLIDAY_PATH.read_text(encoding="utf-8"))
  except Exception as exc:
    return holidays, f"Unable to parse holiday file {HOLIDAY_PATH}: {exc}. Using built-in NSE 2026 holiday calendar."
  raw_items = payload.get("holidays") if isinstance(payload, dict) else None
  if not isinstance(raw_items, list):
    return holidays, f"Invalid holiday file structure in {HOLIDAY_PATH}. Using built-in NSE 2026 holiday calendar."
  for item in raw_items:
    token = str(item or "").strip()
    if not token:
      continue
    try:
      holidays.add(dt.datetime.strptime(token, "%Y-%m-%d").date())
    except ValueError:
      continue
  return holidays, None


def _is_within_window(now_time: dt.time, start_time: dt.time, end_time: dt.time) -> bool:
  if start_time == end_time:
    return True
  if start_time < end_time:
    return start_time <= now_time < end_time
  return now_time >= start_time or now_time < end_time


def _is_market_day(day: dt.date, holidays: Set[dt.date]) -> bool:
  return market_calendar.is_market_working_day(day) and day not in holidays


def _resolve_reference_date(now_local: dt.datetime, start_time: dt.time, end_time: dt.time) -> dt.date:
  base = now_local.date()
  crosses_midnight = start_time > end_time
  if crosses_midnight and now_local.time() < end_time:
    return base - dt.timedelta(days=1)
  return base


def _resolve_expected_trade_date(reference_day: dt.date, holidays: Set[dt.date], lookback_days: int = 370) -> Optional[dt.date]:
  for offset in range(0, max(1, lookback_days)):
    candidate = reference_day - dt.timedelta(days=offset)
    if _is_market_day(candidate, holidays):
      return candidate
  return None


def _next_window_start(now_local: dt.datetime, start_time: dt.time, end_time: dt.time) -> dt.datetime:
  base = now_local.replace(hour=start_time.hour, minute=start_time.minute, second=0, microsecond=0)
  crosses_midnight = start_time > end_time
  if not crosses_midnight:
    return base if now_local.time() < start_time else (base + dt.timedelta(days=1))
  if now_local.time() >= start_time:
    return base + dt.timedelta(days=1)
  return base


def _timestamp_text(timestamp: Optional[dt.datetime] = None) -> str:
  current = timestamp or dt.datetime.now()
  return current.strftime("%Y-%m-%d %H:%M:%S")


def _build_run_id(now_local: Optional[dt.datetime] = None) -> str:
  current = now_local or dt.datetime.now()
  return f"RUN_{current.strftime('%Y%m%d_%H%M%S')}"


def _format_log_line(
  *,
  timestamp: Optional[dt.datetime],
  run_id: str,
  target_date_type: str,
  module: str,
  trade_date: Optional[dt.date],
  status: str,
  rows_success: int,
  rows_failed: int,
  rows_skipped: int,
  next_retry_at: str,
  message: str,
) -> str:
  ts = _timestamp_text(timestamp)
  trade_date_token = trade_date.isoformat() if isinstance(trade_date, dt.date) else "-"
  target_type_token = str(target_date_type or "-").strip() or "-"
  next_retry_token = str(next_retry_at or "-").strip() or "-"
  clean_message = str(message or "").replace("\r", " ").replace("\n", " ").strip()
  return f"{ts} | {str(run_id or '-').strip() or '-'} | {target_type_token} | {module} | {trade_date_token} | {status} | {max(0, int(rows_success))} | {max(0, int(rows_failed))} | {max(0, int(rows_skipped))} | {next_retry_token} | {clean_message}"


def _append_log(line: str) -> None:
  LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
  with LOG_PATH.open("a", encoding="utf-8") as handle:
    handle.write(line.rstrip() + "\n")


def _emit(
  run_id: str,
  module: str,
  trade_date: Optional[dt.date],
  status: str,
  message: str,
  *,
  rows_success: int = 0,
  rows_failed: int = 0,
  rows_skipped: int = 0,
  duration_ms: int = 0,
  target_date_type: str = "-",
  next_retry_at: str = "",
) -> None:
  line = _format_log_line(
    timestamp=dt.datetime.now(),
    run_id=run_id,
    target_date_type=target_date_type,
    module=module,
    trade_date=trade_date,
    status=status,
    message=message,
    rows_success=rows_success,
    rows_failed=rows_failed,
    rows_skipped=rows_skipped,
    next_retry_at=next_retry_at,
  )
  _append_log(line)
  print(line)


def _is_process_alive(pid: Any) -> bool:
  try:
    pid_int = int(pid)
  except (TypeError, ValueError):
    return False
  if pid_int <= 0:
    return False
  if pid_int == os.getpid():
    return True
  try:
    os.kill(pid_int, 0)
    return True
  except PermissionError:
    return True
  except OSError:
    return False
  except Exception:
    # Windows can occasionally raise non-OSError variants from os.kill(pid, 0)
    # ("returned a result with an exception set"). Treat as not-alive so the
    # scheduler lock path fails safe instead of crashing the background loop.
    return False


def _acquire_lock(lock_path: Path, stale_seconds: int) -> Tuple[bool, str]:
  lock_path.parent.mkdir(parents=True, exist_ok=True)
  now_ts = time.time()
  if lock_path.exists():
    existing_started_ts: Optional[float] = None
    existing_pid: Optional[Any] = None
    try:
      payload = json.loads(lock_path.read_text(encoding="utf-8"))
      existing_started_ts = float(payload.get("started_ts") or 0.0)
      existing_pid = payload.get("pid")
    except Exception:
      existing_started_ts = None
    if existing_started_ts is None or existing_started_ts <= 0:
      try:
        existing_started_ts = lock_path.stat().st_mtime
      except Exception:
        existing_started_ts = None
    if (
      existing_started_ts is not None
      and (now_ts - existing_started_ts) <= max(1, stale_seconds)
      and _is_process_alive(existing_pid)
    ):
      return False, "Another automation run is already active."
    try:
      lock_path.unlink()
    except Exception:
      return False, "Another automation run is already active."
  lock_payload = {
    "pid": os.getpid(),
    "started_ts": now_ts,
    "started_at": dt.datetime.now().replace(microsecond=0).isoformat(),
  }
  try:
    fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
  except FileExistsError:
    return False, "Another automation run is already active."
  with os.fdopen(fd, "w", encoding="utf-8") as handle:
    json.dump(lock_payload, handle, ensure_ascii=True)
  return True, ""


def _release_lock(lock_path: Path) -> None:
  try:
    if lock_path.exists():
      lock_path.unlink()
  except Exception:
    pass


def _read_lock_state(lock_path: Path) -> Tuple[Optional[float], Optional[Any]]:
  if not lock_path.exists():
    return None, None
  try:
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    return float(payload.get("started_ts") or 0.0), payload.get("pid")
  except Exception:
    try:
      return float(lock_path.stat().st_mtime), None
    except Exception:
      return None, None


def _parse_status_timestamp(value: Any) -> Optional[float]:
  text = str(value or "").strip()
  if not text:
    return None
  try:
    return dt.datetime.fromisoformat(text).timestamp()
  except Exception:
    return None


def _recover_stale_running_status(
  *,
  now_ts: float,
  now_local: dt.datetime,
  lock_stale_seconds: int,
) -> bool:
  current = status_svc.load_status(create_if_missing=True)
  if str(current.get("current_status") or "").strip().upper() != RUNTIME_STATUS_RUNNING:
    return False
  if not bool(current.get("is_running")):
    return False

  lock_started_ts, lock_pid = _read_lock_state(LOCK_PATH)
  status_started_ts = _parse_status_timestamp(current.get("last_started_at"))
  started_ts = lock_started_ts or status_started_ts
  if started_ts is None or started_ts <= 0:
    return False

  if (float(now_ts) - float(started_ts)) <= max(1, int(lock_stale_seconds)):
    return False
  if lock_pid is not None and _is_process_alive(lock_pid):
    return False

  trade_date_text = str(current.get("target_trade_date") or "").strip()
  interrupted_message = (
    f"Previous automation run {str(current.get('last_run_id') or '-')} was interrupted before completion; "
    "stale runtime state recovered. Missing modules will retry on the next scheduler cycle."
  )
  modules_payload = current.get("modules") if isinstance(current.get("modules"), dict) else {}
  recovered_modules: Dict[str, Dict[str, Any]] = {}
  in_progress_statuses = {
    "PENDING_RETRY",
    "RUNNING",
    "STARTED",
    "DATA_NOT_AVAILABLE_RETRY_LATER",
  }
  for module_name in MODULES:
    module_data = modules_payload.get(module_name) if isinstance(modules_payload, dict) else {}
    status = str((module_data or {}).get("status") or "IDLE").strip().upper()
    if status in in_progress_statuses:
      recovered_modules[module_name] = {
        "source_table": MODULE_SOURCE_TABLES.get(module_name, ""),
        "status": "FAILED",
        "rows_success": max(0, _safe_int((module_data or {}).get("rows_success"), 0)),
        "rows_failed": max(1, _safe_int((module_data or {}).get("rows_failed"), 0)),
        "rows_skipped": max(0, _safe_int((module_data or {}).get("rows_skipped"), 0)),
        "target_trade_date": str((module_data or {}).get("target_trade_date") or trade_date_text),
        "message": "Previous automation run was interrupted before completion; module will retry.",
      }
    else:
      recovered_modules[module_name] = {
        "source_table": MODULE_SOURCE_TABLES.get(module_name, ""),
        "status": status or "IDLE",
        "rows_success": max(0, _safe_int((module_data or {}).get("rows_success"), 0)),
        "rows_failed": max(0, _safe_int((module_data or {}).get("rows_failed"), 0)),
        "rows_skipped": max(0, _safe_int((module_data or {}).get("rows_skipped"), 0)),
        "target_trade_date": str((module_data or {}).get("target_trade_date") or trade_date_text),
        "message": str((module_data or {}).get("message") or "").strip(),
      }

  _update_runtime_status({
    "current_status": RUNTIME_STATUS_FAILED,
    "is_running": False,
    "last_completed_at": now_local.replace(microsecond=0).isoformat(),
    "message": interrupted_message,
    "modules": recovered_modules,
    "totals": _calculate_totals(recovered_modules),
    "next_retry_at": "",
  })
  _emit(
    str(current.get("last_run_id") or _build_run_id(now_local.replace(tzinfo=None))),
    "scheduler",
    None,
    STATUS_FAILED,
    interrupted_message,
    rows_failed=1,
    target_date_type=str(current.get("target_date_type") or "-"),
  )
  return True


def _status_token(result: Dict[str, Any]) -> str:
  return str((result or {}).get("status") or "").strip().upper()


def _message_token(result: Dict[str, Any]) -> str:
  return str((result or {}).get("message") or "").strip()


def _is_data_not_available(status_token: str, message: str) -> bool:
  status = str(status_token or "").strip().upper()
  text = str(message or "").strip().lower()
  if status in {"NO_ACTION", "SKIPPED"} and ("no nse" in text or "not available" in text or "unavailable" in text):
    return True
  if "no nse" in text and ("not available" in text or "skipping likely holiday" in text):
    return True
  if "unable to download nse" in text and ("not available" in text or "trade date" in text):
    return True
  return False


def _extract_module_counts(result: Dict[str, Any], *, rows_before: int, rows_after: int, status: str) -> Dict[str, int]:
  payload = result if isinstance(result, dict) else {}
  counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
  load = payload.get("load") if isinstance(payload.get("load"), dict) else {}
  stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
  inspection = payload.get("inspection") if isinstance(payload.get("inspection"), dict) else {}
  enrichment = payload.get("enrichment") if isinstance(payload.get("enrichment"), dict) else {}

  rows_success = _first_positive_int(
    payload.get("rowsInserted"),
    counts.get("insertedRows"),
    load.get("loadedCount"),
    stats.get("totalRecordsInserted"),
    enrichment.get("successCount"),
    rows_after - rows_before if rows_after > rows_before else 0,
  )
  rows_failed = _first_non_negative_int(
    payload.get("rowsFailed"),
    counts.get("failedRows"),
    load.get("failureCount"),
    stats.get("totalFailed"),
    enrichment.get("failureCount"),
    0,
  )
  rows_skipped = _first_non_negative_int(
    payload.get("rowsSkipped"),
    counts.get("skippedRows"),
    load.get("skippedCount"),
    stats.get("totalSkipped"),
    enrichment.get("skippedCount"),
    load.get("alreadyLoadedCount"),
    inspection.get("alreadyLoadedCount"),
    0,
  )

  if status == STATUS_LOADED:
    rows_skipped = max(rows_skipped, max(0, rows_before))
  if status == STATUS_SUCCESS and rows_success <= 0 and rows_after > rows_before:
    rows_success = rows_after - rows_before
  if status == STATUS_RETRY:
    rows_success = 0

  return {
    "rows_success": max(0, int(rows_success)),
    "rows_failed": max(0, int(rows_failed)),
    "rows_skipped": max(0, int(rows_skipped)),
  }


def _normalize_module_result(
  *,
  result: Dict[str, Any],
  rows_before: int,
  rows_after: int,
) -> Tuple[str, str, Dict[str, int]]:
  status_token = _status_token(result)
  message = _message_token(result)
  if _is_data_not_available(status_token, message):
    counts = {"rows_success": 0, "rows_failed": 0, "rows_skipped": 0}
    return STATUS_RETRY, message or "NSE latest file is not available yet. Retry later in allowed window.", counts
  if status_token in {"ALREADY_EXISTS", "SKIPPED"}:
    counts = {"rows_success": 0, "rows_failed": 0, "rows_skipped": max(0, rows_before)}
    return STATUS_LOADED, message or "Rows already present for target trade date. Skipping.", counts
  if status_token == "NO_ACTION":
    if rows_after > 0:
      counts = {"rows_success": 0, "rows_failed": 0, "rows_skipped": max(0, rows_before)}
      return STATUS_LOADED, message or "No new rows inserted because data already exists.", counts
    counts = {"rows_success": 0, "rows_failed": 0, "rows_skipped": 0}
    return STATUS_RETRY, message or "No actionable NSE data available yet. Retry later.", counts
  if bool(result.get("ok")):
    status = STATUS_SUCCESS if rows_after > rows_before else STATUS_LOADED
    counts = _extract_module_counts(result, rows_before=rows_before, rows_after=rows_after, status=status)
    return status, message or ("Pipeline completed and rows inserted." if status == STATUS_SUCCESS else "Pipeline completed with no new inserts."), counts
  counts = _extract_module_counts(result, rows_before=rows_before, rows_after=rows_after, status=STATUS_FAILED)
  if counts["rows_failed"] <= 0 and counts["rows_success"] <= 0 and counts["rows_skipped"] <= 0:
    counts["rows_failed"] = 1
  return STATUS_FAILED, message or "Pipeline execution failed.", counts


def _line_logger(run_id: str, module_name: str, trade_date: dt.date, target_date_type: str = "-") -> Callable[[str], None]:
  def _emit_line(line: str) -> None:
    text = str(line or "").strip()
    if not text:
      return
    _emit(run_id, module_name, trade_date, STATUS_STARTED, f"PIPELINE: {text}", target_date_type=target_date_type)
  return _emit_line


def _mcap_existing_rows(trade_date: dt.date) -> int:
  return max(0, nse_mcap_svc.get_mcap_trade_date_row_count(trade_date, source="all"))


def _ffmc_existing_rows(trade_date: dt.date) -> int:
  payload = nse_ffmc_svc.get_dashboard(trade_date.isoformat(), limit=1)
  summary = payload.get("summary") if isinstance(payload, dict) else {}
  return max(0, _safe_int((summary or {}).get("totalRows")))


def _delivery_existing_rows(trade_date: dt.date) -> int:
  payload = nse_delivery_svc.get_dashboard(trade_date.isoformat(), limit=1)
  summary = payload.get("summary") if isinstance(payload, dict) else {}
  return max(0, _safe_int((summary or {}).get("totalRows")))


def _run_mcap(run_id: str, trade_date: dt.date, target_date_type: str = "-") -> Dict[str, Any]:
  return nse_mcap_svc.run_mcap_pipeline_for_trade_date(
    trade_date,
    force=False,
    automation=True,
    line_logger=_line_logger(run_id, MODULE_MCAP, trade_date, target_date_type),
  )


def _run_ffmc(run_id: str, trade_date: dt.date, target_date_type: str = "-") -> Dict[str, Any]:
  payload = {
    "tradeDate": trade_date.isoformat(),
    "jobMode": "pipeline",
    "autoInsertAfterDownload": True,
    "eqOnly": True,
  }
  return nse_ffmc_svc.run_pipeline(payload, line_logger=_line_logger(run_id, MODULE_FFMC, trade_date, target_date_type))


def _run_delivery(run_id: str, trade_date: dt.date, target_date_type: str = "-") -> Dict[str, Any]:
  payload = {
    "tradeDate": trade_date.isoformat(),
    "jobMode": "pipeline",
    "autoInsertAfterDownload": True,
    "eqOnly": True,
  }
  return nse_delivery_svc.run_pipeline(payload, line_logger=_line_logger(run_id, MODULE_DELIVERY, trade_date, target_date_type))


def _module_existing_rows(module_name: str, trade_date: dt.date) -> int:
  if module_name == MODULE_MCAP:
    return _mcap_existing_rows(trade_date)
  if module_name == MODULE_FFMC:
    return _ffmc_existing_rows(trade_date)
  if module_name == MODULE_DELIVERY:
    return _delivery_existing_rows(trade_date)
  raise ValueError(f"Unsupported module: {module_name}")


def _enabled_modules(config: Dict[str, Any]) -> Tuple[str, ...]:
  modules_cfg = config.get("modules") if isinstance(config.get("modules"), dict) else {}
  return tuple(module_name for module_name in MODULES if _coerce_bool((modules_cfg or {}).get(module_name), True))


def _module_missing_for_date(module_name: str, trade_date: dt.date, config: Dict[str, Any]) -> bool:
  threshold_map = config.get("min_rows_threshold") if isinstance(config.get("min_rows_threshold"), dict) else {}
  min_threshold = max(0, _safe_int((threshold_map or {}).get(module_name), 1))
  return _module_existing_rows(module_name, trade_date) < min_threshold


def _missing_modules_for_date(trade_date: dt.date, config: Dict[str, Any]) -> Tuple[str, ...]:
  missing = []
  for module_name in _enabled_modules(config):
    if _module_missing_for_date(module_name, trade_date, config):
      missing.append(module_name)
  return tuple(missing)


def _iter_previous_market_dates(today: dt.date, holidays: Set[dt.date], lookback_days: int) -> Sequence[dt.date]:
  dates = []
  for offset in range(1, max(1, lookback_days) + 1):
    candidate = today - dt.timedelta(days=offset)
    if _is_market_day(candidate, holidays):
      dates.append(candidate)
  return dates


def _next_market_start_after(now_local: dt.datetime, start_time: dt.time, holidays: Set[dt.date]) -> dt.datetime:
  for offset in range(0, 30):
    candidate_day = now_local.date() + dt.timedelta(days=offset)
    if not _is_market_day(candidate_day, holidays):
      continue
    candidate = dt.datetime.combine(candidate_day, start_time).replace(tzinfo=now_local.tzinfo)
    if candidate > now_local:
      return candidate.replace(microsecond=0)
  return (now_local + dt.timedelta(days=1)).replace(hour=start_time.hour, minute=start_time.minute, second=0, microsecond=0)


def _retry_at_iso(now_local: dt.datetime, config: Dict[str, Any]) -> str:
  retry_minutes = max(1, _safe_int(config.get("retry_minutes"), 5))
  return (now_local + dt.timedelta(minutes=retry_minutes)).replace(microsecond=0).isoformat()


def _target_context(
  *,
  now_local: dt.datetime,
  config: Dict[str, Any],
  holidays: Set[dt.date],
  current_start_time: dt.time,
) -> Dict[str, Any]:
  today = now_local.date()
  previous_trade_date = _resolve_expected_trade_date(today - dt.timedelta(days=1), holidays)
  if previous_trade_date is not None:
    missing_modules = _missing_modules_for_date(previous_trade_date, config)
    if missing_modules:
      return {
        "should_run": True,
        "trade_date": previous_trade_date,
        "target_date_type": TARGET_PREVIOUS,
        "current_status": RUNTIME_STATUS_PREVIOUS_PENDING,
        "retry_until_success": _coerce_bool(config.get("previous_trade_date_retry_until_success"), True),
        "next_retry_at": "",
        "message": f"Previous trading date data missing for {previous_trade_date.isoformat()} ({', '.join(missing_modules)}). Retrying until DB insertion success.",
      }

  if not _is_market_day(today, holidays):
    next_retry_at = _next_market_start_after(now_local, current_start_time, holidays).isoformat()
    return {
      "should_run": False,
      "trade_date": _resolve_expected_trade_date(today, holidays),
      "target_date_type": TARGET_CURRENT,
      "current_status": RUNTIME_STATUS_IDLE,
      "retry_until_success": True,
      "next_retry_at": next_retry_at,
      "message": "Today is not an NSE market working day. Current trading date automation is waiting for the next market day after 5 PM.",
    }

  current_trade_date = today
  if now_local.time() < current_start_time:
    next_retry_at = dt.datetime.combine(today, current_start_time).replace(tzinfo=now_local.tzinfo, microsecond=0).isoformat()
    return {
      "should_run": False,
      "trade_date": current_trade_date,
      "target_date_type": TARGET_CURRENT,
      "current_status": RUNTIME_STATUS_WAITING_5PM,
      "retry_until_success": _coerce_bool(config.get("current_trade_date_retry_until_success"), True),
      "next_retry_at": next_retry_at,
      "message": "Current trading date automation starts after 5 PM IST.",
    }

  return {
    "should_run": True,
    "trade_date": current_trade_date,
    "target_date_type": TARGET_CURRENT,
    "current_status": RUNTIME_STATUS_CURRENT_RETRYING,
    "retry_until_success": _coerce_bool(config.get("current_trade_date_retry_until_success"), True),
    "next_retry_at": "",
    "message": "Current trading date is eligible after 5 PM IST. Extraction/insertion will run until DB insertion succeeds.",
  }


def _run_module_pipeline(run_id: str, module_name: str, trade_date: dt.date, target_date_type: str = "-") -> Dict[str, Any]:
  if module_name == MODULE_MCAP:
    return _run_mcap(run_id, trade_date, target_date_type)
  if module_name == MODULE_FFMC:
    return _run_ffmc(run_id, trade_date, target_date_type)
  if module_name == MODULE_DELIVERY:
    return _run_delivery(run_id, trade_date, target_date_type)
  raise ValueError(f"Unsupported module: {module_name}")


def _empty_runtime_module(module_name: str = "", trade_date: Optional[dt.date] = None, *, status: str = "IDLE", message: str = "") -> Dict[str, Any]:
  return {
    "source_table": MODULE_SOURCE_TABLES.get(module_name, ""),
    "status": str(status or "IDLE").strip().upper(),
    "rows_success": 0,
    "rows_failed": 0,
    "rows_skipped": 0,
    "target_trade_date": trade_date.isoformat() if isinstance(trade_date, dt.date) else "",
    "message": str(message or "").strip(),
  }


def _empty_runtime_modules(trade_date: Optional[dt.date] = None, *, status: str = "IDLE", message: str = "") -> Dict[str, Dict[str, Any]]:
  return {module_name: _empty_runtime_module(module_name, trade_date, status=status, message=message) for module_name in MODULES}


def _runtime_module_status(exec_status: str, *, dry_run: bool = False, module_enabled: bool = True) -> str:
  if not module_enabled:
    return STATUS_SKIPPED
  if dry_run and exec_status == STATUS_STARTED:
    return STATUS_STARTED
  if exec_status == STATUS_SUCCESS:
    return "SUCCESS"
  if exec_status == STATUS_FAILED:
    return "FAILED"
  if exec_status == STATUS_LOADED:
    return "SKIPPED_ALREADY_LOADED"
  if exec_status == STATUS_RETRY:
    return "DATA_NOT_AVAILABLE_RETRY_LATER"
  if exec_status in {STATUS_PREVIOUS_PENDING, STATUS_CURRENT_RETRYING, STATUS_WAITING_5PM}:
    return "PENDING_RETRY"
  return STATUS_SKIPPED


def _build_runtime_module_payload(
  exec_status: str,
  message: str,
  counts: Dict[str, int],
  *,
  dry_run: bool = False,
  module_enabled: bool = True,
  module_name: str = "",
  trade_date: Optional[dt.date] = None,
) -> Dict[str, Any]:
  return {
    "source_table": MODULE_SOURCE_TABLES.get(module_name, ""),
    "status": _runtime_module_status(exec_status, dry_run=dry_run, module_enabled=module_enabled),
    "rows_success": max(0, _safe_int(counts.get("rows_success"), 0)),
    "rows_failed": max(0, _safe_int(counts.get("rows_failed"), 0)),
    "rows_skipped": max(0, _safe_int(counts.get("rows_skipped"), 0)),
    "target_trade_date": trade_date.isoformat() if isinstance(trade_date, dt.date) else "",
    "message": str(message or "").strip(),
  }


def _calculate_totals(modules_payload: Dict[str, Dict[str, Any]]) -> Dict[str, int]:
  rows_success = 0
  rows_failed = 0
  rows_skipped = 0
  for module_name in MODULES:
    module_data = modules_payload.get(module_name) if isinstance(modules_payload, dict) else {}
    rows_success += max(0, _safe_int((module_data or {}).get("rows_success"), 0))
    rows_failed += max(0, _safe_int((module_data or {}).get("rows_failed"), 0))
    rows_skipped += max(0, _safe_int((module_data or {}).get("rows_skipped"), 0))
  return {
    "rows_success": rows_success,
    "rows_failed": rows_failed,
    "rows_skipped": rows_skipped,
  }


def _dashboard_snapshot(module_name: str, trade_date: dt.date) -> Dict[str, Any]:
  if module_name == MODULE_MCAP:
    payload = nse_mcap_svc.get_dashboard(trade_date.isoformat(), limit=1)
  elif module_name == MODULE_FFMC:
    payload = nse_ffmc_svc.get_dashboard(trade_date.isoformat(), limit=1)
  elif module_name == MODULE_DELIVERY:
    payload = nse_delivery_svc.get_dashboard(trade_date.isoformat(), limit=1)
  else:
    payload = {}
  data = payload if isinstance(payload, dict) else {}
  return {
    "source_table": MODULE_SOURCE_TABLES.get(module_name, ""),
    "trade_date": str(data.get("tradeDate") or trade_date.isoformat()),
    "summary": data.get("summary") if isinstance(data.get("summary"), dict) else {},
    "dataOverview": data.get("dataOverview") if isinstance(data.get("dataOverview"), dict) else {},
  }


def _latest_db_summary(trade_date: Optional[dt.date]) -> Dict[str, Any]:
  if not isinstance(trade_date, dt.date):
    return {}
  snapshots: Dict[str, Any] = {}
  for module_name in MODULES:
    try:
      snapshots[module_name] = _dashboard_snapshot(module_name, trade_date)
    except Exception as exc:
      snapshots[module_name] = {
        "source_table": MODULE_SOURCE_TABLES.get(module_name, ""),
        "trade_date": trade_date.isoformat(),
        "summary": {},
        "dataOverview": {},
        "error": str(exc),
      }
  return snapshots


def _resolve_final_runtime_status(module_execution_status: Dict[str, str], *, dry_run: bool = False, target_date_type: str = "") -> str:
  statuses = [str(module_execution_status.get(module_name) or "").upper() for module_name in MODULES if module_name in module_execution_status]
  if not statuses:
    return RUNTIME_STATUS_IDLE
  if dry_run:
    return RUNTIME_STATUS_SKIPPED
  if any(status == STATUS_FAILED for status in statuses):
    return RUNTIME_STATUS_FAILED
  if any(status == STATUS_RETRY for status in statuses):
    if target_date_type == TARGET_PREVIOUS:
      return RUNTIME_STATUS_PREVIOUS_PENDING
    if target_date_type == TARGET_CURRENT:
      return RUNTIME_STATUS_CURRENT_RETRYING
    return RUNTIME_STATUS_RETRY
  if any(status == STATUS_SUCCESS for status in statuses):
    return RUNTIME_STATUS_SUCCESS
  if all(status in {STATUS_LOADED, STATUS_HOLIDAY, STATUS_SKIPPED, STATUS_STARTED} for status in statuses):
    return RUNTIME_STATUS_SUCCESS if all(status in {STATUS_LOADED, STATUS_SKIPPED} for status in statuses) else RUNTIME_STATUS_SKIPPED
  return RUNTIME_STATUS_IDLE


def _update_runtime_status(payload: Dict[str, Any]) -> Dict[str, Any]:
  return status_svc.merge_status(payload)


def _execute_module(
  run_id: str,
  module_name: str,
  trade_date: dt.date,
  config: Dict[str, Any],
  *,
  dry_run: bool = False,
  target_date_type: str = "-",
) -> Dict[str, Any]:
  started_at = time.time()
  skip_if_rows_exist = _coerce_bool(config.get("skip_if_rows_exist"), True)
  threshold_map = config.get("min_rows_threshold") if isinstance(config.get("min_rows_threshold"), dict) else {}
  min_threshold = max(0, _safe_int((threshold_map or {}).get(module_name), 1))
  rows_before = _module_existing_rows(module_name, trade_date)

  if skip_if_rows_exist and rows_before >= min_threshold:
    duration_ms = int((time.time() - started_at) * 1000)
    message = f"Rows already exist for {trade_date.isoformat()} (rows={rows_before}, threshold={min_threshold})."
    counts = {"rows_success": 0, "rows_failed": 0, "rows_skipped": max(0, rows_before)}
    _emit(
      run_id,
      module_name,
      trade_date,
      STATUS_LOADED,
      message,
      rows_success=counts["rows_success"],
      rows_failed=counts["rows_failed"],
      rows_skipped=counts["rows_skipped"],
      duration_ms=duration_ms,
      target_date_type=target_date_type,
    )
    return {"status": STATUS_LOADED, "failed": False, "retry": False, "message": message, "counts": counts}

  if dry_run:
    duration_ms = int((time.time() - started_at) * 1000)
    message = f"Dry run only. Pipeline would execute for {trade_date.isoformat()} (existingRows={rows_before})."
    counts = {"rows_success": 0, "rows_failed": 0, "rows_skipped": 0}
    _emit(
      run_id,
      module_name,
      trade_date,
      STATUS_STARTED,
      message,
      rows_success=0,
      rows_failed=0,
      rows_skipped=0,
      duration_ms=duration_ms,
      target_date_type=target_date_type,
    )
    return {"status": STATUS_STARTED, "failed": False, "retry": False, "message": message, "counts": counts}

  _emit(run_id, module_name, trade_date, STATUS_STARTED, f"Automation pipeline execution started for {trade_date.isoformat()}.", target_date_type=target_date_type)
  try:
    result = _run_module_pipeline(run_id, module_name, trade_date, target_date_type)
  except Exception as exc:
    duration_ms = int((time.time() - started_at) * 1000)
    counts = {"rows_success": 0, "rows_failed": 1, "rows_skipped": 0}
    message = f"Pipeline exception: {exc}"
    _emit(
      run_id,
      module_name,
      trade_date,
      STATUS_FAILED,
      message,
      rows_success=counts["rows_success"],
      rows_failed=counts["rows_failed"],
      rows_skipped=counts["rows_skipped"],
      duration_ms=duration_ms,
      target_date_type=target_date_type,
      next_retry_at=_retry_at_iso(dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))), config),
    )
    return {"status": STATUS_FAILED, "failed": True, "retry": False, "message": message, "counts": counts}

  rows_after = _module_existing_rows(module_name, trade_date)
  status, message, counts = _normalize_module_result(result=result if isinstance(result, dict) else {}, rows_before=rows_before, rows_after=rows_after)
  duration_ms = int((time.time() - started_at) * 1000)
  next_retry_at = _retry_at_iso(dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))), config) if status == STATUS_RETRY else ""
  _emit(
    run_id,
    module_name,
    trade_date,
    status,
    message,
    rows_success=counts["rows_success"],
    rows_failed=counts["rows_failed"],
    rows_skipped=counts["rows_skipped"],
    duration_ms=duration_ms,
    target_date_type=target_date_type,
    next_retry_at=next_retry_at,
  )
  return {
    "status": status,
    "failed": status == STATUS_FAILED,
    "retry": status == STATUS_RETRY,
    "message": message,
    "counts": counts,
  }


def run_scheduler(*, dry_run: bool = False, lock_stale_seconds: int = 3 * 60 * 60) -> int:
  status_svc.ensure_status_file()
  config, config_warning = _load_scheduler_config()
  start_window = str(config.get("window_start") or DEFAULT_CONFIG["window_start"])
  end_window = str(config.get("window_end") or DEFAULT_CONFIG["window_end"])
  schedule_window = f"{start_window}-{end_window}"
  automation_enabled = _coerce_bool(config.get("enabled"), True)
  _update_runtime_status({
    "automation_enabled": automation_enabled,
    "schedule_window": schedule_window,
  })

  run_id = _build_run_id()
  if config_warning:
    _emit(run_id, "scheduler", None, STATUS_STARTED, config_warning)

  if not automation_enabled:
    message = "Automation is disabled in configuration."
    _emit(run_id, "scheduler", None, STATUS_HOLIDAY, message)
    idle_modules = _empty_runtime_modules()
    _update_runtime_status({
      "current_status": RUNTIME_STATUS_IDLE,
      "is_running": False,
      "last_run_id": run_id,
      "last_completed_at": dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).replace(microsecond=0).isoformat(),
      "target_date_type": "",
      "retry_until_success": True,
      "message": message,
      "modules": idle_modules,
      "totals": _calculate_totals(idle_modules),
      "next_retry_at": "",
    })
    return 0

  now_local = dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30)))
  _recover_stale_running_status(
    now_ts=time.time(),
    now_local=now_local,
    lock_stale_seconds=lock_stale_seconds,
  )

  lock_ok, lock_message = _acquire_lock(LOCK_PATH, lock_stale_seconds)
  if not lock_ok:
    _emit(run_id, "scheduler", None, STATUS_RUNNING, lock_message)
    skipped_modules = _empty_runtime_modules()
    _update_runtime_status({
      "current_status": STATUS_RUNNING,
      "is_running": False,
      "last_run_id": run_id,
      "last_completed_at": dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).replace(microsecond=0).isoformat(),
      "target_date_type": "",
      "retry_until_success": True,
      "message": lock_message,
      "modules": skipped_modules,
      "totals": _calculate_totals(skipped_modules),
      "next_retry_at": "",
    })
    return 0

  has_failures = False
  try:
    now_local = dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30)))
    run_id = _build_run_id(now_local.replace(tzinfo=None))
    current_start_text = str(config.get("current_day_start_time") or start_window or DEFAULT_CONFIG["current_day_start_time"])
    current_start_time = _parse_hhmm(current_start_text, field_name="current_day_start_time")

    holidays, holiday_warning = _load_holidays()
    if holiday_warning:
      _emit(run_id, "scheduler", None, STATUS_STARTED, holiday_warning)

    target = _target_context(
      now_local=now_local,
      config=config,
      holidays=holidays,
      current_start_time=current_start_time,
    )
    trade_date = target.get("trade_date") if isinstance(target.get("trade_date"), dt.date) else None
    target_date_type = str(target.get("target_date_type") or "").strip().upper()
    context_status = str(target.get("current_status") or RUNTIME_STATUS_IDLE).strip().upper()
    retry_until_success = bool(target.get("retry_until_success", True))
    context_message = str(target.get("message") or "").strip()
    context_next_retry_at = str(target.get("next_retry_at") or "").strip()

    if trade_date is None:
      message = context_message or "No valid NSE market day found for automation target resolution."
      _emit(run_id, "scheduler", None, STATUS_HOLIDAY, message, target_date_type=target_date_type, next_retry_at=context_next_retry_at)
      holiday_modules = _empty_runtime_modules(status="IDLE", message=message)
      _update_runtime_status({
        "current_status": RUNTIME_STATUS_IDLE,
        "is_running": False,
        "last_run_id": run_id,
        "last_completed_at": now_local.replace(microsecond=0).isoformat(),
        "target_trade_date": "",
        "target_date_type": target_date_type,
        "retry_until_success": retry_until_success,
        "message": message,
        "modules": holiday_modules,
        "totals": _calculate_totals(holiday_modules),
        "next_retry_at": context_next_retry_at,
      })
      return 0

    if not bool(target.get("should_run")):
      waiting_status = "PENDING_RETRY" if context_status == RUNTIME_STATUS_WAITING_5PM else "IDLE"
      waiting_modules = _empty_runtime_modules(trade_date, status=waiting_status, message=context_message)
      _emit(
        run_id,
        "scheduler",
        trade_date,
        context_status,
        context_message,
        target_date_type=target_date_type,
        next_retry_at=context_next_retry_at,
      )
      final_payload = {
        "current_status": context_status,
        "is_running": False,
        "last_run_id": run_id,
        "last_completed_at": now_local.replace(microsecond=0).isoformat(),
        "target_trade_date": trade_date.isoformat(),
        "target_date_type": target_date_type,
        "retry_until_success": retry_until_success,
        "message": context_message,
        "modules": waiting_modules,
        "totals": _calculate_totals(waiting_modules),
        "next_retry_at": context_next_retry_at,
        "latest_db_summary": {},
      }
      final_payload["latest_result"] = status_svc.build_latest_result_snapshot(_deep_merge(status_svc.load_status(create_if_missing=True), final_payload))
      _update_runtime_status(final_payload)
      return 0

    modules_state = _empty_runtime_modules(trade_date, status="PENDING_RETRY", message="Pending module execution.")
    _update_runtime_status({
      "current_status": RUNTIME_STATUS_RUNNING,
      "is_running": True,
      "last_run_id": run_id,
      "last_started_at": now_local.replace(microsecond=0).isoformat(),
      "target_trade_date": trade_date.isoformat(),
      "target_date_type": target_date_type,
      "retry_until_success": retry_until_success,
      "message": context_message,
      "next_retry_at": "",
      "modules": modules_state,
      "totals": _calculate_totals(modules_state),
    })
    _emit(
      run_id,
      "scheduler",
      trade_date,
      STATUS_STARTED,
      f"Scheduler cycle started (dryRun={str(bool(dry_run)).lower()}) for trade_date={trade_date.isoformat()}. {context_message}",
      target_date_type=target_date_type,
    )

    module_execution_status: Dict[str, str] = {}
    modules_cfg = config.get("modules") if isinstance(config.get("modules"), dict) else {}

    for module_name in MODULES:
      module_enabled = _coerce_bool((modules_cfg or {}).get(module_name), True)
      if not module_enabled:
        message = "Module disabled in configuration."
        counts = {"rows_success": 0, "rows_failed": 0, "rows_skipped": 0}
        _emit(run_id, module_name, trade_date, STATUS_HOLIDAY, message, target_date_type=target_date_type)
        modules_state[module_name] = _build_runtime_module_payload(STATUS_SKIPPED, message, counts, dry_run=dry_run, module_enabled=False, module_name=module_name, trade_date=trade_date)
        module_execution_status[module_name] = STATUS_SKIPPED
      else:
        module_result = _execute_module(run_id, module_name, trade_date, config, dry_run=dry_run, target_date_type=target_date_type)
        module_status = str(module_result.get("status") or STATUS_FAILED)
        module_counts = module_result.get("counts") if isinstance(module_result.get("counts"), dict) else {}
        module_message = str(module_result.get("message") or "").strip()
        modules_state[module_name] = _build_runtime_module_payload(module_status, module_message, module_counts, dry_run=dry_run, module_enabled=True, module_name=module_name, trade_date=trade_date)
        module_execution_status[module_name] = module_status
        has_failures = has_failures or bool(module_result.get("failed"))

      _update_runtime_status({
        "last_run_id": run_id,
        "target_trade_date": trade_date.isoformat(),
        "target_date_type": target_date_type,
        "retry_until_success": retry_until_success,
        "message": context_message,
        "modules": modules_state,
        "totals": _calculate_totals(modules_state),
      })

    final_status = _resolve_final_runtime_status(module_execution_status, dry_run=dry_run, target_date_type=target_date_type)
    next_retry_at = ""
    if final_status != RUNTIME_STATUS_SUCCESS and retry_until_success and not dry_run:
      next_retry_at = _retry_at_iso(dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))), config)
    module_runtime_statuses = [str((modules_state.get(module_name) or {}).get("status") or "").upper() for module_name in MODULES]
    all_already_loaded = bool(module_runtime_statuses) and all(status in {"SKIPPED_ALREADY_LOADED", "SKIPPED"} for status in module_runtime_statuses)
    if final_status == RUNTIME_STATUS_SUCCESS and all_already_loaded:
      final_message = "Target trade date data already exists in Oracle. Extraction skipped."
    elif final_status == RUNTIME_STATUS_SUCCESS:
      final_message = "Automation completed. Inserted data is available from Oracle summary endpoints."
    elif final_status == RUNTIME_STATUS_PREVIOUS_PENDING:
      final_message = "Previous trading date data is still missing. Retrying until DB insertion success."
    elif final_status == RUNTIME_STATUS_CURRENT_RETRYING:
      final_message = "Current trading date data is not available yet or not inserted. Retrying until DB insertion success."
    elif final_status == RUNTIME_STATUS_FAILED:
      final_message = "Automation failed. Review module messages and logs."
    else:
      final_message = context_message or "Automation cycle finished."
    final_totals = _calculate_totals(modules_state)
    _emit(
      run_id,
      "scheduler",
      trade_date,
      final_status,
      final_message,
      rows_success=final_totals["rows_success"],
      rows_failed=final_totals["rows_failed"],
      rows_skipped=final_totals["rows_skipped"],
      target_date_type=target_date_type,
      next_retry_at=next_retry_at,
    )

    final_payload = {
      "current_status": final_status,
      "is_running": False,
      "last_run_id": run_id,
      "last_completed_at": dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).replace(microsecond=0).isoformat(),
      "target_trade_date": trade_date.isoformat(),
      "target_date_type": target_date_type,
      "retry_until_success": retry_until_success,
      "message": final_message,
      "next_retry_at": next_retry_at,
      "modules": modules_state,
      "totals": final_totals,
      "latest_db_summary": _latest_db_summary(trade_date) if final_status == RUNTIME_STATUS_SUCCESS else {},
    }
    final_payload["latest_result"] = status_svc.build_latest_result_snapshot(_deep_merge(status_svc.load_status(create_if_missing=True), final_payload))
    _update_runtime_status(final_payload)
    return 1 if has_failures else 0
  finally:
    _release_lock(LOCK_PATH)
    _update_runtime_status({
      "is_running": False,
    })


def start_nse_marketdata_auto_scheduler(*, initial_delay_seconds: int = 10) -> None:
  global _AUTO_SCHEDULER_STARTED
  with _AUTO_SCHEDULER_LOCK:
    if _AUTO_SCHEDULER_STARTED:
      return
    _AUTO_SCHEDULER_STARTED = True

  def _loop() -> None:
    delay = max(0, _safe_int(initial_delay_seconds, 10))
    if delay > 0:
      time.sleep(delay)
    while True:
      try:
        run_scheduler(dry_run=False)
      except Exception as exc:  # pragma: no cover
        run_id = _build_run_id()
        _emit(run_id, "scheduler", None, STATUS_FAILED, f"Background scheduler exception: {exc}", rows_success=0, rows_failed=1, rows_skipped=0, duration_ms=0)
      time.sleep(_retry_interval_seconds())

  threading.Thread(target=_loop, name="nse-marketdata-auto-scheduler", daemon=True).start()


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
  parser = argparse.ArgumentParser(description="CvingTrade25X NSE market-data automation scheduler")
  parser.add_argument("--once", action="store_true", help="Run one scheduler cycle and exit.")
  parser.add_argument("--dry-run", action="store_true", help="Evaluate conditions without triggering pipeline execution.")
  parser.add_argument(
    "--lock-stale-seconds",
    type=int,
    default=3 * 60 * 60,
    help="Treat lock files older than this value as stale (default: 10800).",
  )
  return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
  args = _parse_args(argv)
  _ = bool(args.once)  # Single-cycle execution is the only supported mode for this runner.
  return run_scheduler(dry_run=bool(args.dry_run), lock_stale_seconds=max(60, int(args.lock_stale_seconds or 10800)))


if __name__ == "__main__":
  raise SystemExit(main(sys.argv[1:]))
