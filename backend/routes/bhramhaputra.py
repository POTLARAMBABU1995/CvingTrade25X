from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from flask import Blueprint, jsonify, request

from cache import TTLCache, background_refresh, load_json_snapshot, save_json_snapshot
from services.ath_service import log_stale_snapshot_warning
from services.bhramhaputra_service import (
    backfill_manual_sr_display_rows,
    compute_bhramhaputra_payload,
    fetch_bhramhaputra_last_ltc_date,
    insert_bhramhaputra_rows,
    normalize_bhramhaputra_payload_fields,
)
from services import nse_mcap_service as nse_mcap_svc

try:
    from ..services.ui_notification_service import publish_notification
except ImportError:  # pragma: no cover
    from services.ui_notification_service import publish_notification  # type: ignore


_logger = logging.getLogger(__name__)

bp = Blueprint("bhramhaputra", __name__)

_cache = TTLCache(ttl_seconds=int(os.getenv("BHRAMHAPUTRA_CACHE_TTL") or "900"))
_snapshot_dir = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data",
)
VALID_TIMEFRAMES = ("daily", "weekly", "monthly", "yearly")
BHRAMHAPUTRA_AUTO_INSERT_ENABLED = os.getenv("BHRAMHAPUTRA_AUTO_INSERT_ENABLED", "1").strip().lower() not in ("0", "false", "no")
BHRAMHAPUTRA_AUTO_INSERT_TIME = os.getenv("BHRAMHAPUTRA_AUTO_INSERT_TIME", "18:00").strip() or "18:00"
_ASYNC_COLD_WAIT_MS = max(0, int(os.getenv("BHRAMHAPUTRA_ASYNC_COLD_WAIT_MS") or "1500"))
_ASYNC_COLD_POLL_MS = max(25, int(os.getenv("BHRAMHAPUTRA_ASYNC_COLD_POLL_MS") or "50"))
_ATH_SOURCE_TABLE = "NSE_NIFTY500_DAILY_RAW_DATA_DEV"
_auto_insert_started = False


def _normalize_timeframe(value: str | None) -> str:
    if value is None or not str(value).strip():
        return "daily"
    tf = str(value).strip().lower()
    if tf not in VALID_TIMEFRAMES:
        raise ValueError("Invalid timeframe")
    return tf


def _snapshot_path(timeframe: str) -> str:
    os.makedirs(_snapshot_dir, exist_ok=True)
    tf_suffix = timeframe.lower()
    return os.path.join(_snapshot_dir, f"snapshot_bhramhaputra_tf_{tf_suffix}.json")


def invalidate_bhramhaputra_cache(*, clear_snapshots: bool = False) -> None:
    _cache.clear()
    if not clear_snapshots:
        return
    removed = 0
    for timeframe in VALID_TIMEFRAMES:
        try:
            os.remove(_snapshot_path(timeframe))
            removed += 1
        except FileNotFoundError:
            continue
        except Exception:
            _logger.exception("Bhramhaputra snapshot invalidation failed timeframe=%s", timeframe)
    _logger.info("Bhramhaputra cache invalidated clear_snapshots=%s snapshots_removed=%s", clear_snapshots, removed)


def _snapshot_has_move_fields(payload: Dict[str, Any] | None) -> bool:
    if not payload or not isinstance(payload, dict):
        return False
    rows = payload.get("rows") or []
    if not isinstance(rows, list) or len(rows) == 0:
        return True
    sample = next((row for row in rows if isinstance(row, dict)), None)
    if not sample:
        return True
    return ("move22dPct" in sample) or ("move_22d_pct" in sample)


def _snapshot_has_current_cutoff(payload: Dict[str, Any] | None) -> bool:
    if not payload or not isinstance(payload, dict):
        return False
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        return False
    return str(meta.get("cutoffAnchor") or "").strip().lower() == "current"


def _snapshot_has_ath_source(payload: Dict[str, Any] | None) -> bool:
    if not payload or not isinstance(payload, dict):
        return False
    source = str(payload.get("athSource") or "").strip().upper()
    return source == _ATH_SOURCE_TABLE


def _snapshot_has_manual_sr_display_fields(payload: Dict[str, Any] | None) -> bool:
    if not payload or not isinstance(payload, dict):
        return False
    rows = payload.get("rows") or []
    if not isinstance(rows, list) or len(rows) == 0:
        return True
    sample = next((row for row in rows if isinstance(row, dict)), None)
    if not sample:
        return True
    has_support_display = any(key in sample for key in ("supportDisplay", "support_display", "SUPPORT_DISPLAY"))
    has_resistance_display = any(key in sample for key in ("resistanceDisplay", "resistance_display", "RESISTANCE_DISPLAY"))
    return has_support_display and has_resistance_display


def _normalize_iso_date(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text[:10] if text else ""


def _resolve_latest_ltc_date(rows: Any) -> str:
    latest = ""
    items = rows if isinstance(rows, list) else []
    for row in items:
        if not isinstance(row, dict):
            continue
        token = _normalize_iso_date(
            row.get("ltcDate")
            or row.get("buyDate")
            or row.get("buyingDate")
            or row.get("tradeDate")
            or row.get("BUY_DATE")
            or row.get("LTC_DATE")
        )
        if token and (not latest or token > latest):
            latest = token
    return latest


def _strict_daily_rows(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    return [
        row for row in (payload.get("rows") or [])
        if isinstance(row, dict)
        and str(row.get("conditionsMet") or "").strip().upper() == "YES"
    ]


def _publish_auto_insert_notification(
    *,
    reason: str,
    message: str,
    inserted: int,
    skipped: int,
    latest_ltc_date: str,
) -> None:
    try:
        publish_notification(
            source="bhramhaputra_auto_insert",
            message=message,
            level="success",
            metadata={
                "reason": reason,
                "insertedRows": inserted,
                "skippedRows": skipped,
                "ltcDate": latest_ltc_date or "",
            },
        )
    except Exception as exc:
        _logger.warning("Bhramhaputra auto-insert notification failed error=%s", exc)


def _build_payload(timeframe: str) -> Dict[str, Any]:
    payload = compute_bhramhaputra_payload(timeframe=timeframe)
    insert_result: Dict[str, Any] = {
        "insertedCount": 0,
        "skippedCount": 0,
        "updatedCount": 0,
        "totalProcessed": 0,
        "latestLtcDate": None,
        "message": "DB insertion skipped.",
    }
    error = None
    if timeframe == "daily":
        try:
            strict_rows = [
                row for row in (payload.get("rows") or [])
                if str((row or {}).get("conditionsMet") or "").strip().upper() == "YES"
            ]
            insert_result = insert_bhramhaputra_rows(strict_rows)
            payload["dbUpsertRows"] = len(strict_rows)
        except Exception as exc:
            error = "Bhramhaputra DB insert failed. Check backend logs."
            _logger.exception("Bhramhaputra DB insert failed")
    else:
        payload["dbSkipped"] = True
    payload["dbInserted"] = int(insert_result.get("insertedCount") or 0)
    payload["dbSkippedRows"] = int(insert_result.get("skippedCount") or 0)
    payload["dbUpdated"] = int(insert_result.get("updatedCount") or 0)
    payload["dbInsertResult"] = insert_result
    if insert_result.get("latestLtcDate"):
        payload["latestLtcDate"] = insert_result.get("latestLtcDate")
    if error:
        payload["dbError"] = error
    payload = nse_mcap_svc.enrich_payload_marketcap_index(payload, row_keys=("rows",))
    return normalize_bhramhaputra_payload_fields(payload)


def _build_and_save_payload(timeframe: str) -> Dict[str, Any]:
    payload = _build_payload(timeframe)
    save_json_snapshot(_snapshot_path(timeframe), payload)
    return payload


def _schedule_refresh(cache_key: str, timeframe: str) -> None:
    background_refresh(_cache, cache_key, lambda: _build_and_save_payload(timeframe))


def _wait_for_cached_payload(cache_key: str, wait_ms: int) -> Dict[str, Any] | None:
    if wait_ms <= 0:
        return None
    deadline = time.perf_counter() + (wait_ms / 1000.0)
    while time.perf_counter() < deadline:
        warmed = _cache.get(cache_key)
        if warmed is not None:
            return warmed
        time.sleep(_ASYNC_COLD_POLL_MS / 1000.0)
    return None


def _warming_payload(timeframe: str) -> Dict[str, Any]:
    return {
        "rows": [],
        "count": 0,
        "generatedAt": datetime.utcnow().isoformat() + "Z",
        "timeframe": timeframe,
        "cached": True,
        "refreshing": True,
        "stale": True,
        "staleReasons": ["cold_start"],
    }


def _snapshot_stale_reasons(payload: Dict[str, Any] | None) -> list[str]:
    reasons: list[str] = []
    if not _snapshot_has_move_fields(payload):
        reasons.append("move_fields")
    if not _snapshot_has_current_cutoff(payload):
        reasons.append("cutoff_anchor")
    if not _snapshot_has_ath_source(payload):
        reasons.append("ath_source")
    if not _snapshot_has_manual_sr_display_fields(payload):
        reasons.append("manual_sr_display")
    return reasons


def _repair_manual_sr_display_fields(payload: Dict[str, Any], timeframe: str) -> Dict[str, Any]:
    normalized = normalize_bhramhaputra_payload_fields(payload)
    rows = normalized.get("rows") or []
    if not isinstance(rows, list) or not rows or _snapshot_has_manual_sr_display_fields(normalized):
        return normalized
    repaired = {
        **normalized,
        "rows": backfill_manual_sr_display_rows(rows, timeframe=timeframe),
    }
    save_json_snapshot(_snapshot_path(timeframe), repaired)
    return repaired


def _auto_insert_once(reason: str = "schedule") -> Optional[Dict[str, Any]]:
    if not BHRAMHAPUTRA_AUTO_INSERT_ENABLED:
        return None
    correlation_id = str(uuid.uuid4())
    started = time.perf_counter()
    try:
        payload = compute_bhramhaputra_payload(timeframe="daily")
        rows = _strict_daily_rows(payload)
        page_date = _resolve_latest_ltc_date(rows) or _resolve_latest_ltc_date(payload.get("rows"))
        if not rows:
            _logger.info(
                "Bhramhaputra auto-insert skipped correlationId=%s reason=%s rows=0 pageDate=%s",
                correlation_id,
                reason,
                page_date,
            )
            return {
                "status": "skipped",
                "reason": "no_rows",
                "insertedCount": 0,
                "skippedCount": 0,
                "latestLtcDate": page_date or None,
            }

        last_inserted_date = fetch_bhramhaputra_last_ltc_date()
        if page_date and last_inserted_date and page_date <= last_inserted_date:
            skipped = len(rows)
            message = f"Bhramhaputra auto insertion already up to date for {page_date}."
            _publish_auto_insert_notification(
                reason=reason,
                message=message,
                inserted=0,
                skipped=skipped,
                latest_ltc_date=page_date,
            )
            _logger.info(
                "Bhramhaputra auto-insert up-to-date correlationId=%s reason=%s pageDate=%s lastInsertedDate=%s rows=%s duration_ms=%s",
                correlation_id,
                reason,
                page_date,
                last_inserted_date,
                skipped,
                round((time.perf_counter() - started) * 1000, 2),
            )
            return {
                "status": "ok",
                "upToDate": True,
                "insertedCount": 0,
                "skippedCount": skipped,
                "latestLtcDate": page_date,
                "message": message,
            }

        result = insert_bhramhaputra_rows(rows)
        inserted = int(result.get("insertedCount") or 0)
        skipped = int(result.get("skippedCount") or 0)
        latest_ltc_date = str(result.get("latestLtcDate") or page_date or "")
        message = (
            f"Bhramhaputra auto insertion completed successfully for {inserted} rows."
            if inserted > 0
            else f"Bhramhaputra auto insertion completed successfully; existing rows already present for {latest_ltc_date or 'latest date'}."
        )
        _publish_auto_insert_notification(
            reason=reason,
            message=message,
            inserted=inserted,
            skipped=skipped,
            latest_ltc_date=latest_ltc_date,
        )
        _logger.info(
            "Bhramhaputra auto-insert done correlationId=%s reason=%s rows=%s inserted=%s skipped=%s latestLtcDate=%s duration_ms=%s",
            correlation_id,
            reason,
            len(rows),
            inserted,
            skipped,
            latest_ltc_date,
            round((time.perf_counter() - started) * 1000, 2),
        )
        return {
            "status": "ok",
            **result,
        }
    except Exception:
        _logger.exception("Bhramhaputra auto-insert failed correlationId=%s reason=%s", correlation_id, reason)
        return None


def start_bhramhaputra_auto_insert() -> None:
    global _auto_insert_started
    if _auto_insert_started or not BHRAMHAPUTRA_AUTO_INSERT_ENABLED:
        return
    _auto_insert_started = True

    def _loop() -> None:
        startup_delay = max(5, int(os.getenv("BHRAMHAPUTRA_AUTO_INSERT_STARTUP_DELAY_SEC", "25")))
        try:
            time.sleep(startup_delay)
            _auto_insert_once(reason="startup")
        except Exception:
            _logger.exception("Bhramhaputra startup auto-insert failed")
        while True:
            try:
                now = datetime.now()
                parts = BHRAMHAPUTRA_AUTO_INSERT_TIME.split(":", 1)
                hour = int(parts[0]) if parts and parts[0].isdigit() else 18
                minute = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
                target = datetime(now.year, now.month, now.day, hour, minute)
                if target <= now:
                    target = target + timedelta(days=1)
                sleep_seconds = max(30, int((target - now).total_seconds()))
                time.sleep(sleep_seconds)
                _auto_insert_once(reason="schedule")
            except Exception:
                _logger.exception("Bhramhaputra auto-insert scheduler error")
                time.sleep(300)

    threading.Thread(target=_loop, name="bhramhaputra-auto-insert", daemon=True).start()


@bp.get("/api/bhramhaputra")
def api_bhramhaputra():
    started = time.perf_counter()
    request_id = str(uuid.uuid4())
    force_refresh = request.args.get("refresh") in ("1", "true", "yes")
    try:
        timeframe = _normalize_timeframe(request.args.get("tf") or request.args.get("timeframe"))
    except ValueError:
        _logger.info(
            "bhramhaputra_request request_id=%s tf=%s refresh=%s error=invalid_timeframe duration_ms=%s",
            request_id,
            request.args.get("tf") or request.args.get("timeframe"),
            force_refresh,
            round((time.perf_counter() - started) * 1000, 2),
        )
        return jsonify({"ok": False, "error": "Invalid timeframe"}), 400

    cache_key = f"bhramhaputra:{timeframe}"
    if force_refresh:
        payload = _build_and_save_payload(timeframe)
        _cache.set(cache_key, payload)
        _logger.info(
            "bhramhaputra_request request_id=%s tf=%s refresh=%s source=oracle rows=%s cutoff_date=%s latest_trade_date=%s duration_ms=%s",
            request_id,
            timeframe,
            force_refresh,
            len(payload.get("rows") or []),
            ((payload.get("meta") or {}).get("cutoffDateIso")),
            ((payload.get("meta") or {}).get("endDate")),
            round((time.perf_counter() - started) * 1000, 2),
        )
        return jsonify(payload)

    cached = _cache.get(cache_key)
    if cached is not None:
        cached = normalize_bhramhaputra_payload_fields(cached)
        _cache.set(cache_key, cached)
        stale_reasons = _snapshot_stale_reasons(cached)
        if "manual_sr_display" in stale_reasons:
            try:
                cached = _repair_manual_sr_display_fields(cached, timeframe)
                _cache.set(cache_key, cached)
                stale_reasons = _snapshot_stale_reasons(cached)
            except Exception:
                _logger.exception("Bhramhaputra manual SR display backfill failed source=cache tf=%s", timeframe)
        if stale_reasons:
            log_stale_snapshot_warning(endpoint="/api/bhramhaputra", source="cache_" + ",".join(stale_reasons))
            _schedule_refresh(cache_key, timeframe)
        _logger.info(
            "bhramhaputra_request request_id=%s tf=%s refresh=%s source=cache rows=%s stale=%s cutoff_date=%s latest_trade_date=%s duration_ms=%s",
            request_id,
            timeframe,
            force_refresh,
            len(cached.get("rows") or []),
            ",".join(stale_reasons) if stale_reasons else "false",
            ((cached.get("meta") or {}).get("cutoffDateIso")),
            ((cached.get("meta") or {}).get("endDate")),
            round((time.perf_counter() - started) * 1000, 2),
        )
        return jsonify({
            **cached,
            "cached": True,
            "refreshing": bool(stale_reasons),
            "stale": bool(stale_reasons),
            "staleReasons": stale_reasons,
        })

    snapshot = load_json_snapshot(_snapshot_path(timeframe))
    if snapshot:
        snapshot = normalize_bhramhaputra_payload_fields(snapshot)
        stale_reasons = _snapshot_stale_reasons(snapshot)
        if "manual_sr_display" in stale_reasons:
            try:
                snapshot = _repair_manual_sr_display_fields(snapshot, timeframe)
                stale_reasons = _snapshot_stale_reasons(snapshot)
            except Exception:
                _logger.exception("Bhramhaputra manual SR display backfill failed source=snapshot tf=%s", timeframe)
        if stale_reasons:
            log_stale_snapshot_warning(endpoint="/api/bhramhaputra", source="snapshot_" + ",".join(stale_reasons))
        _cache.set(cache_key, snapshot)
        if stale_reasons:
            _schedule_refresh(cache_key, timeframe)
        _logger.info(
            "bhramhaputra_request request_id=%s tf=%s refresh=%s source=snapshot rows=%s stale=%s cutoff_date=%s latest_trade_date=%s duration_ms=%s",
            request_id,
            timeframe,
            force_refresh,
            len(snapshot.get("rows") or []),
            ",".join(stale_reasons) if stale_reasons else "false",
            ((snapshot.get("meta") or {}).get("cutoffDateIso")),
            ((snapshot.get("meta") or {}).get("endDate")),
            round((time.perf_counter() - started) * 1000, 2),
        )
        return jsonify({
            **snapshot,
            "cached": True,
            "refreshing": bool(stale_reasons),
            "stale": bool(stale_reasons),
            "staleReasons": stale_reasons,
        })

    _schedule_refresh(cache_key, timeframe)
    warmed = _wait_for_cached_payload(cache_key, _ASYNC_COLD_WAIT_MS)
    if warmed is not None:
        _logger.info(
            "bhramhaputra_request request_id=%s tf=%s refresh=%s source=oracle_cold_async rows=%s cutoff_date=%s latest_trade_date=%s duration_ms=%s",
            request_id,
            timeframe,
            force_refresh,
            len(warmed.get("rows") or []),
            ((warmed.get("meta") or {}).get("cutoffDateIso")),
            ((warmed.get("meta") or {}).get("endDate")),
            round((time.perf_counter() - started) * 1000, 2),
        )
        return jsonify({
            **warmed,
            "cached": True,
            "refreshing": False,
            "stale": False,
            "staleReasons": [],
        })

    payload = _warming_payload(timeframe)
    _logger.info(
        "bhramhaputra_request request_id=%s tf=%s refresh=%s source=warming rows=0 cutoff_date=%s latest_trade_date=%s duration_ms=%s",
        request_id,
        timeframe,
        force_refresh,
        len(payload.get("rows") or []),
        ((payload.get("meta") or {}).get("cutoffDateIso")),
        ((payload.get("meta") or {}).get("endDate")),
        round((time.perf_counter() - started) * 1000, 2),
    )
    return jsonify(payload)


@bp.route("/api/bhramhaputra/last-ltc-date", methods=["GET", "POST"])
def api_bhramhaputra_last_ltc_date():
    try:
        return jsonify({
            "status": "ok",
            "maxLtcDate": fetch_bhramhaputra_last_ltc_date(),
        })
    except Exception:
        _logger.exception("Bhramhaputra last-ltc-date query failed")
        return jsonify({
            "status": "error",
            "message": "Bhramhaputra latest insert date query failed. Check backend logs.",
            "maxLtcDate": None,
        }), 500


@bp.post("/api/bhramhaputra/insert")
def api_bhramhaputra_insert():
    started = time.perf_counter()
    request_id = request.headers.get("X-Correlation-Id") or str(uuid.uuid4())
    payload = request.get_json(silent=True) or {}
    raw_rows = payload if isinstance(payload, list) else payload.get("rows") if isinstance(payload, dict) else None
    rows = [row for row in (raw_rows or []) if isinstance(row, dict)]
    if not rows:
        return jsonify({
            "ok": False,
            "status": "error",
            "requestId": request_id,
            "insertedCount": 0,
            "skippedCount": 0,
            "updatedCount": 0,
            "totalProcessed": 0,
            "message": "No valid Bhramhaputra rows to insert.",
        }), 400
    try:
        result = insert_bhramhaputra_rows(rows)
        _logger.info(
            "bhramhaputra_insert request_id=%s latest_ltc_date=%s processed=%s inserted=%s skipped=%s updated=%s duration_ms=%s",
            request_id,
            result.get("latestLtcDate"),
            result.get("totalProcessed"),
            result.get("insertedCount"),
            result.get("skippedCount"),
            result.get("updatedCount"),
            round((time.perf_counter() - started) * 1000, 2),
        )
        return jsonify({
            "ok": True,
            "status": "ok",
            "requestId": request_id,
            **result,
        })
    except Exception:
        _logger.exception("Bhramhaputra insert failed request_id=%s", request_id)
        return jsonify({
            "ok": False,
            "status": "error",
            "requestId": request_id,
            "insertedCount": 0,
            "skippedCount": 0,
            "updatedCount": 0,
            "totalProcessed": len(rows),
            "message": "Bhramhaputra insertion failed. Check backend logs.",
        }), 500
