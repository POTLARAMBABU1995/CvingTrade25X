from __future__ import annotations

import copy
import datetime as dt
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATUS_PATH = PROJECT_ROOT / "runtime" / "status" / "nse_marketdata_automation_status.json"
MODULE_KEYS = ("mcap", "ffmc", "delivery")
MODULE_SOURCE_TABLES = {
  "mcap": "CVING_NSE_MARKET_CAP_HIST",
  "ffmc": "CVING_NSE_FFMC_HIST",
  "delivery": "CVING_NSE_DELIVERY_HIST",
}


def _now_iso() -> str:
  return dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def _safe_int(value: Any, default: int = 0) -> int:
  try:
    return int(value)
  except Exception:
    return int(default)


def _clean_text(value: Any, default: str = "") -> str:
  text = str(value or "").strip()
  return text if text else str(default or "")


def _module_template(module_key: str = "") -> Dict[str, Any]:
  return {
    "source_table": MODULE_SOURCE_TABLES.get(module_key, ""),
    "status": "IDLE",
    "rows_success": 0,
    "rows_failed": 0,
    "rows_skipped": 0,
    "target_trade_date": "",
    "message": "",
  }


def _totals_template() -> Dict[str, int]:
  return {
    "rows_success": 0,
    "rows_failed": 0,
    "rows_skipped": 0,
  }


def default_status_payload() -> Dict[str, Any]:
  modules = {key: _module_template(key) for key in MODULE_KEYS}
  return {
    "automation_enabled": True,
    "schedule_window": "17:00-09:00",
    "current_status": "IDLE",
    "is_running": False,
    "last_run_id": "",
    "last_started_at": "",
    "last_completed_at": "",
    "target_trade_date": "",
    "target_date_type": "",
    "retry_until_success": True,
    "next_retry_at": "",
    "message": "",
    "modules": modules,
    "totals": _totals_template(),
    "latest_result": {},
    "latest_db_summary": {},
    "updated_at": _now_iso(),
  }


def _normalize_module(payload: Any, module_key: str = "") -> Dict[str, Any]:
  base = _module_template(module_key)
  data = payload if isinstance(payload, dict) else {}
  base["source_table"] = MODULE_SOURCE_TABLES.get(module_key, _clean_text(data.get("source_table"), base["source_table"])).upper()
  base["status"] = _clean_text(data.get("status"), "IDLE").upper()
  base["rows_success"] = max(0, _safe_int(data.get("rows_success"), 0))
  base["rows_failed"] = max(0, _safe_int(data.get("rows_failed"), 0))
  base["rows_skipped"] = max(0, _safe_int(data.get("rows_skipped"), 0))
  base["target_trade_date"] = _clean_text(data.get("target_trade_date"), "")
  base["message"] = _clean_text(data.get("message"), "")
  return base


def _normalize_totals(payload: Any) -> Dict[str, int]:
  data = payload if isinstance(payload, dict) else {}
  return {
    "rows_success": max(0, _safe_int(data.get("rows_success"), 0)),
    "rows_failed": max(0, _safe_int(data.get("rows_failed"), 0)),
    "rows_skipped": max(0, _safe_int(data.get("rows_skipped"), 0)),
  }


def _normalize_latest_result(payload: Any) -> Dict[str, Any]:
  data = payload if isinstance(payload, dict) else {}
  if not data:
    return {}
  modules_payload = data.get("modules") if isinstance(data.get("modules"), dict) else {}
  modules = {key: _normalize_module(modules_payload.get(key), key) for key in MODULE_KEYS}
  return {
    "run_id": _clean_text(data.get("run_id"), ""),
    "completed_at": _clean_text(data.get("completed_at"), ""),
    "trade_date": _clean_text(data.get("trade_date"), ""),
    "target_date_type": _clean_text(data.get("target_date_type"), "").upper(),
    "current_status": _clean_text(data.get("current_status"), "").upper(),
    "message": _clean_text(data.get("message"), ""),
    "modules": modules,
    "totals": _normalize_totals(data.get("totals")),
  }


def normalize_status_payload(payload: Any) -> Dict[str, Any]:
  data = payload if isinstance(payload, dict) else {}
  base = default_status_payload()
  base["automation_enabled"] = bool(data.get("automation_enabled", base["automation_enabled"]))
  base["schedule_window"] = _clean_text(data.get("schedule_window"), base["schedule_window"])
  base["current_status"] = _clean_text(data.get("current_status"), base["current_status"]).upper()
  base["is_running"] = bool(data.get("is_running", base["is_running"]))
  base["last_run_id"] = _clean_text(data.get("last_run_id"), "")
  base["last_started_at"] = _clean_text(data.get("last_started_at"), "")
  base["last_completed_at"] = _clean_text(data.get("last_completed_at"), "")
  base["target_trade_date"] = _clean_text(data.get("target_trade_date"), "")
  base["target_date_type"] = _clean_text(data.get("target_date_type"), "").upper()
  base["retry_until_success"] = bool(data.get("retry_until_success", base["retry_until_success"]))
  base["next_retry_at"] = _clean_text(data.get("next_retry_at"), "")
  base["message"] = _clean_text(data.get("message"), "")

  modules_payload = data.get("modules") if isinstance(data.get("modules"), dict) else {}
  base["modules"] = {key: _normalize_module(modules_payload.get(key), key) for key in MODULE_KEYS}
  base["totals"] = _normalize_totals(data.get("totals"))
  base["latest_result"] = _normalize_latest_result(data.get("latest_result"))
  base["latest_db_summary"] = data.get("latest_db_summary") if isinstance(data.get("latest_db_summary"), dict) else {}
  base["updated_at"] = _clean_text(data.get("updated_at"), _now_iso())
  return base


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  temp_path: Path | None = None
  try:
    with tempfile.NamedTemporaryFile("w", delete=False, dir=str(path.parent), prefix=f"{path.name}.", suffix=".tmp", encoding="utf-8") as handle:
      temp_path = Path(handle.name)
      json.dump(payload, handle, ensure_ascii=True, indent=2)
      handle.flush()
      os.fsync(handle.fileno())
    os.replace(str(temp_path), str(path))
    temp_path = None
  finally:
    if temp_path and temp_path.exists():
      try:
        temp_path.unlink()
      except Exception:
        pass


def save_status(payload: Any) -> Dict[str, Any]:
  normalized = normalize_status_payload(payload)
  normalized["updated_at"] = _now_iso()
  _atomic_write_json(STATUS_PATH, normalized)
  return copy.deepcopy(normalized)


def load_status(*, create_if_missing: bool = True) -> Dict[str, Any]:
  if not STATUS_PATH.exists():
    default_payload = default_status_payload()
    if create_if_missing:
      return save_status(default_payload)
    return default_payload
  try:
    payload = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
  except Exception:
    payload = default_status_payload()
    if create_if_missing:
      return save_status(payload)
    return payload
  normalized = normalize_status_payload(payload)
  if create_if_missing and normalized != payload:
    return save_status(normalized)
  return normalized


def ensure_status_file() -> Dict[str, Any]:
  return load_status(create_if_missing=True)


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
  merged: Dict[str, Any] = dict(base)
  for key, value in (override or {}).items():
    if isinstance(merged.get(key), dict) and isinstance(value, dict):
      merged[key] = _deep_merge(dict(merged[key]), value)
    else:
      merged[key] = value
  return merged


def merge_status(update_payload: Dict[str, Any]) -> Dict[str, Any]:
  current = load_status(create_if_missing=True)
  merged = _deep_merge(current, update_payload if isinstance(update_payload, dict) else {})
  return save_status(merged)


def build_latest_result_snapshot(payload: Dict[str, Any]) -> Dict[str, Any]:
  data = normalize_status_payload(payload)
  return {
    "run_id": data.get("last_run_id") or "",
    "completed_at": data.get("last_completed_at") or "",
    "trade_date": data.get("target_trade_date") or "",
    "target_date_type": data.get("target_date_type") or "",
    "current_status": data.get("current_status") or "",
    "message": data.get("message") or "",
    "modules": copy.deepcopy(data.get("modules") or {}),
    "totals": copy.deepcopy(data.get("totals") or _totals_template()),
  }
