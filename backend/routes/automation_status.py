from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from flask import Blueprint, jsonify

try:
  from ..services import automation_status_service as status_svc
except ImportError:  # pragma: no cover
  from services import automation_status_service as status_svc  # type: ignore


bp = Blueprint("automation_status", __name__, url_prefix="/api/automation/nse-marketdata")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
AUTOMATION_CONFIG_PATH = PROJECT_ROOT / "config" / "nse_marketdata_automation.json"
DEFAULT_RETRY_MINUTES = 5
DEFAULT_SCHEDULE_WINDOW = "17:00-09:00"


def _safe_int(value: object, default: int = 0) -> int:
  try:
    return int(value)
  except Exception:
    return int(default)


def _parse_hhmm(token: str) -> dt.time:
  return dt.datetime.strptime(str(token or "").strip(), "%H:%M").time()


def _parse_schedule_window(token: str) -> tuple[dt.time, dt.time]:
  value = str(token or "").strip() or DEFAULT_SCHEDULE_WINDOW
  parts = value.split("-", 1)
  if len(parts) != 2:
    return _parse_hhmm("17:00"), _parse_hhmm("09:00")
  try:
    return _parse_hhmm(parts[0]), _parse_hhmm(parts[1])
  except Exception:
    return _parse_hhmm("17:00"), _parse_hhmm("09:00")


def _load_retry_minutes() -> int:
  try:
    payload = json.loads(AUTOMATION_CONFIG_PATH.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
      return max(1, _safe_int(payload.get("retry_minutes"), DEFAULT_RETRY_MINUTES))
  except Exception:
    pass
  return DEFAULT_RETRY_MINUTES


def _parse_iso_datetime(token: str) -> dt.datetime | None:
  text = str(token or "").strip()
  if not text:
    return None
  try:
    value = dt.datetime.fromisoformat(text)
  except Exception:
    return None
  if value.tzinfo is None:
    return value.replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
  return value


def _is_within_window(now_time: dt.time, start_time: dt.time, end_time: dt.time) -> bool:
  if start_time == end_time:
    return True
  if start_time < end_time:
    return start_time <= now_time < end_time
  return now_time >= start_time or now_time < end_time


def _next_window_start(now_local: dt.datetime, start_time: dt.time, end_time: dt.time) -> dt.datetime:
  today_start = now_local.replace(hour=start_time.hour, minute=start_time.minute, second=0, microsecond=0)
  crosses_midnight = start_time > end_time
  if not crosses_midnight:
    return today_start if now_local.time() < start_time else (today_start + dt.timedelta(days=1))
  if now_local.time() >= start_time:
    return today_start + dt.timedelta(days=1)
  return today_start


def _compute_next_retry_at(schedule_window: str, *, base_time: dt.datetime | None = None) -> str:
  now_local = (base_time or dt.datetime.now().astimezone()).replace(microsecond=0)
  retry_minutes = _load_retry_minutes()
  start_time, end_time = _parse_schedule_window(schedule_window)
  if _is_within_window(now_local.time(), start_time, end_time):
    candidate = now_local + dt.timedelta(minutes=retry_minutes)
    if _is_within_window(candidate.time(), start_time, end_time):
      return candidate.isoformat()
  return _next_window_start(now_local, start_time, end_time).isoformat()


def _coerce_status_payload() -> dict:
  payload = status_svc.load_status(create_if_missing=True)
  normalized = status_svc.normalize_status_payload(payload)
  if normalized.get("is_running"):
    normalized["running_state"] = "RUNNING"
  else:
    normalized["running_state"] = "IDLE"
  schedule_window = str(normalized.get("schedule_window") or DEFAULT_SCHEDULE_WINDOW).strip() or DEFAULT_SCHEDULE_WINDOW
  normalized["schedule_window"] = schedule_window
  status_token = str(normalized.get("current_status") or "").strip().upper()
  next_retry_at = str(normalized.get("next_retry_at") or "").strip()
  retryable_statuses = {
    "IDLE",
    "SKIPPED",
    "FAILED",
    "DATA_NOT_AVAILABLE_RETRY_LATER",
    "PREVIOUS_TRADE_DATE_PENDING",
    "WAITING_FOR_5PM_WINDOW",
    "CURRENT_TRADE_DATE_RETRYING",
    "RUNNING",
  }
  if not next_retry_at and bool(normalized.get("automation_enabled", True)) and status_token in retryable_statuses:
    now_local = dt.datetime.now().astimezone()
    base_time = (
      _parse_iso_datetime(str(normalized.get("last_completed_at") or ""))
      or _parse_iso_datetime(str(normalized.get("last_started_at") or ""))
      or now_local
    )
    if base_time < now_local:
      base_time = now_local
    normalized["next_retry_at"] = _compute_next_retry_at(schedule_window, base_time=base_time)
  return normalized


@bp.get("/status")
def nse_marketdata_status_endpoint():
  return jsonify(_coerce_status_payload())


@bp.get("/latest-result")
def nse_marketdata_latest_result_endpoint():
  payload = _coerce_status_payload()
  latest = payload.get("latest_result") if isinstance(payload.get("latest_result"), dict) else {}
  if not latest:
    latest = status_svc.build_latest_result_snapshot(payload)
  if not latest.get("completed_at"):
    latest = {}
  return jsonify(latest)
