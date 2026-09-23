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

try:
    from ..services.bhramhastra_service import (
        compute_bhramhastra_scan,
        fetch_bhramhastra_max_ltc_date,
        fetch_bhramhastra_source_max_ltc_date,
        repair_bhramhastra_display_fields,
        upsert_bhramhastra_rows,
    )
    from ..services import nse_mcap_service as nse_mcap_svc
except ImportError:  # pragma: no cover
    from services.bhramhastra_service import (  # type: ignore
        compute_bhramhastra_scan,
        fetch_bhramhastra_max_ltc_date,
        fetch_bhramhastra_source_max_ltc_date,
        repair_bhramhastra_display_fields,
        upsert_bhramhastra_rows,
    )
    from services import nse_mcap_service as nse_mcap_svc  # type: ignore

try:
    from ..services.strategy_agent_runtime_service import start_strategy_agent_execution
except ImportError:  # pragma: no cover
    from services.strategy_agent_runtime_service import start_strategy_agent_execution  # type: ignore

try:
    from ..services.ui_notification_service import publish_notification
except ImportError:  # pragma: no cover
    from services.ui_notification_service import publish_notification  # type: ignore


_logger = logging.getLogger(__name__)

bp = Blueprint("bhramhastra", __name__)

_cache = TTLCache(ttl_seconds=int(os.getenv("BHRAMHASTRA_CACHE_TTL") or "900"))
_snapshot_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
VALID_TIMEFRAMES = ("daily", "weekly", "monthly", "yearly")
BHRAMHASTRA_AUTO_INSERT_ENABLED = os.getenv("BHRAMHASTRA_AUTO_INSERT_ENABLED", "1").strip().lower() not in ("0", "false", "no")
BHRAMHASTRA_AUTO_INSERT_TIME = os.getenv("BHRAMHASTRA_AUTO_INSERT_TIME", "18:00").strip() or "18:00"
_ASYNC_COLD_WAIT_MS = max(0, int(os.getenv("BHRAMHASTRA_ASYNC_COLD_WAIT_MS") or "1500"))
_ASYNC_COLD_POLL_MS = max(25, int(os.getenv("BHRAMHASTRA_ASYNC_COLD_POLL_MS") or "50"))
_ATH_SOURCE_TABLE = "NSE_NIFTY500_DAILY_RAW_DATA_DEV"
_auto_insert_started = False
_DISPLAY_FIELD_KEYS = ("ema20", "ema50", "ema100", "ema200", "adx14", "trendDirection", "gap", "setupType")


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
    return os.path.join(_snapshot_dir, f"snapshot_bhramhastra_tf_{tf_suffix}.json")


def invalidate_bhramhastra_cache(*, clear_snapshots: bool = False) -> None:
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
            _logger.exception("Bhramhastra snapshot invalidation failed timeframe=%s", timeframe)
    _logger.info("Bhramhastra cache invalidated clear_snapshots=%s snapshots_removed=%s", clear_snapshots, removed)


def _build_payload(timeframe: str) -> Dict[str, Any]:
    payload, _latest_snapshot = compute_bhramhastra_scan(timeframe=timeframe)
    return _enrich_bhramhastra_payload(payload, force=True)


def _payload_has_marketcap_fields(payload: Dict[str, Any] | None) -> bool:
    rows = _payload_rows(payload)
    if not rows:
        return True
    for row in rows:
        if any(
            row.get(key) is not None and str(row.get(key)).strip() != ""
            for key in ("INDEX", "index", "MCAP", "mcap", "MCAP_RANK", "mcapRank", "mcap_rank")
        ):
            return True
    return False


def _enrich_bhramhastra_payload(payload: Dict[str, Any] | None, *, force: bool = False) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    if not force and _payload_has_marketcap_fields(payload):
        return payload
    try:
        return nse_mcap_svc.enrich_payload_marketcap_index(
            payload,
            row_keys=("rows",),
            allow_stale_per_symbol=True,
        )
    except Exception:
        _logger.exception("Bhramhastra market-cap enrichment failed")
        return payload


def _repair_bhramhastra_payload_display_fields(payload: Dict[str, Any], timeframe: str, source: str) -> tuple[Dict[str, Any], int]:
    if _snapshot_has_display_fields(payload):
        return payload, 0
    try:
        repaired_payload, repaired_count = repair_bhramhastra_display_fields(payload, timeframe=timeframe)
    except Exception:
        _logger.exception("Bhramhastra display-field repair failed source=%s timeframe=%s", source, timeframe)
        return payload, 0
    if repaired_count:
        _logger.info(
            "Bhramhastra display-field repair completed source=%s timeframe=%s rows=%s",
            source,
            timeframe,
            repaired_count,
        )
    return repaired_payload, repaired_count


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


def _payload_rows(payload: Dict[str, Any] | None) -> list[Dict[str, Any]]:
    rows = (payload or {}).get("rows") if isinstance(payload, dict) else []
    return [row for row in (rows or []) if isinstance(row, dict)] if isinstance(rows, list) else []


def _first_symbols(payload: Dict[str, Any] | None) -> str:
    symbols = [
        str(row.get("symbol") or row.get("stockName") or "").strip().upper()
        for row in _payload_rows(payload)[:3]
    ]
    return ",".join([symbol for symbol in symbols if symbol]) or "-"


def _zero_reason(payload: Dict[str, Any] | None, source: str, stale_reasons: list[str] | None = None) -> str:
    if _payload_rows(payload):
        return "-"
    reasons = stale_reasons or []
    if source == "warming":
        return "cold_start_refresh_in_progress"
    if reasons:
        return "refreshing_stale_empty_payload:" + ",".join(reasons)
    if payload and payload.get("refreshing"):
        return "backend_refresh_in_progress"
    return "strategy_filters_returned_zero_rows"


def _snapshot_has_ath_source(payload: Dict[str, Any] | None) -> bool:
    if not payload or not isinstance(payload, dict):
        return False
    source = str(payload.get("athSource") or "").strip().upper()
    return source == _ATH_SOURCE_TABLE


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
        token = _normalize_iso_date(row.get("ltcDate") or row.get("tradeDate") or row.get("backtestDate"))
        if token and (not latest or token > latest):
            latest = token
    return latest


def _snapshot_has_current_ltc_date(payload: Dict[str, Any] | None) -> bool:
    if not payload or not isinstance(payload, dict):
        return False
    payload_latest = _resolve_latest_ltc_date(payload.get("rows"))
    if not payload_latest:
        return True
    try:
        source_latest = fetch_bhramhastra_source_max_ltc_date()
    except Exception:
        _logger.exception("Bhramhastra source latest date check failed")
        return True
    return (not source_latest) or payload_latest >= source_latest


def _snapshot_has_display_fields(payload: Dict[str, Any] | None) -> bool:
    rows = _payload_rows(payload)
    if not rows:
        return True
    for row in rows:
        for key in _DISPLAY_FIELD_KEYS:
            value = row.get(key)
            if value is None or str(value).strip() == "":
                return False
    return True


def _snapshot_stale_reasons(payload: Dict[str, Any] | None) -> list[str]:
    reasons: list[str] = []
    if not _snapshot_has_ath_source(payload):
        reasons.append("ath_source")
    if not _snapshot_has_current_ltc_date(payload):
        reasons.append("ltc_date")
    if not _snapshot_has_display_fields(payload):
        reasons.append("display_fields")
    return reasons


def _trigger_strategy_agent(run_source: str) -> Optional[Dict[str, Any]]:
    try:
        return start_strategy_agent_execution("bhramhastra", run_source=run_source or "manual")
    except Exception as exc:  # pragma: no cover
        _logger.warning("Bhramhastra agent trigger failed: %s", exc)
        return None


@bp.get("/api/bhramhastra")
def api_bhramhastra():
    started = time.perf_counter()
    request_id = request.headers.get("X-Correlation-Id") or str(uuid.uuid4())
    force_refresh = request.args.get("refresh") in ("1", "true", "yes")
    try:
        timeframe = _normalize_timeframe(request.args.get("tf") or request.args.get("timeframe"))
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid timeframe"}), 400

    _logger.info(
        "bhramhastra_api_called request_id=%s endpoint=/api/bhramhastra timeframe=%s refresh=%s",
        request_id,
        timeframe,
        force_refresh,
    )
    cache_key = f"bhramhastra:{timeframe}"
    cached = _cache.get(cache_key)
    if cached is not None:
        cached = _enrich_bhramhastra_payload(cached)
        cached, repaired_count = _repair_bhramhastra_payload_display_fields(cached, timeframe, "cache")
        if repaired_count:
            save_json_snapshot(_snapshot_path(timeframe), cached)
        _cache.set(cache_key, cached)
        stale_reasons = _snapshot_stale_reasons(cached)
        if stale_reasons:
            log_stale_snapshot_warning(endpoint="/api/bhramhastra", source="cache_" + ",".join(stale_reasons))
        if force_refresh or stale_reasons:
            _schedule_refresh(cache_key, timeframe)
        _logger.info(
            "bhramhastra_request request_id=%s tf=%s refresh=%s source=cache latest_trading_date=%s sql_rows_returned=%s rows_after_filter=%s first_symbols=%s stale=%s zero_reason=%s duration_ms=%s",
            request_id,
            timeframe,
            force_refresh,
            _resolve_latest_ltc_date(cached.get("rows")) or "-",
            len(_payload_rows(cached)),
            len(_payload_rows(cached)),
            _first_symbols(cached),
            ",".join(stale_reasons) if stale_reasons else "false",
            _zero_reason(cached, "cache", stale_reasons),
            round((time.perf_counter() - started) * 1000, 2),
        )
        return jsonify({
            **cached,
            "cached": True,
            "refreshing": bool(force_refresh or stale_reasons),
            "stale": bool(stale_reasons),
            "staleReasons": stale_reasons,
        })

    snapshot = load_json_snapshot(_snapshot_path(timeframe))
    if snapshot:
        snapshot = _enrich_bhramhastra_payload(snapshot)
        snapshot, repaired_count = _repair_bhramhastra_payload_display_fields(snapshot, timeframe, "snapshot")
        if repaired_count:
            save_json_snapshot(_snapshot_path(timeframe), snapshot)
        stale_reasons = _snapshot_stale_reasons(snapshot)
        if stale_reasons:
            log_stale_snapshot_warning(endpoint="/api/bhramhastra", source="snapshot_" + ",".join(stale_reasons))
        _cache.set(cache_key, snapshot)
        if force_refresh or stale_reasons:
            _schedule_refresh(cache_key, timeframe)
        _logger.info(
            "bhramhastra_request request_id=%s tf=%s refresh=%s source=snapshot latest_trading_date=%s sql_rows_returned=%s rows_after_filter=%s first_symbols=%s stale=%s zero_reason=%s duration_ms=%s",
            request_id,
            timeframe,
            force_refresh,
            _resolve_latest_ltc_date(snapshot.get("rows")) or "-",
            len(_payload_rows(snapshot)),
            len(_payload_rows(snapshot)),
            _first_symbols(snapshot),
            ",".join(stale_reasons) if stale_reasons else "false",
            _zero_reason(snapshot, "snapshot", stale_reasons),
            round((time.perf_counter() - started) * 1000, 2),
        )
        return jsonify({
            **snapshot,
            "cached": True,
            "refreshing": bool(force_refresh or stale_reasons),
            "stale": bool(stale_reasons),
            "staleReasons": stale_reasons,
        })

    if force_refresh:
        try:
            payload = _build_and_save_payload(timeframe)
        except Exception:
            _logger.exception(
                "bhramhastra_request_failed request_id=%s tf=%s refresh=%s source=oracle_cold",
                request_id,
                timeframe,
                force_refresh,
            )
            raise
        _cache.set(cache_key, payload)
        _logger.info(
            "bhramhastra_request request_id=%s tf=%s refresh=%s source=oracle_cold latest_trading_date=%s sql_rows_returned=%s rows_after_filter=%s first_symbols=%s zero_reason=%s duration_ms=%s",
            request_id,
            timeframe,
            force_refresh,
            _resolve_latest_ltc_date(payload.get("rows")) or "-",
            len(_payload_rows(payload)),
            len(_payload_rows(payload)),
            _first_symbols(payload),
            _zero_reason(payload, "oracle_cold"),
            round((time.perf_counter() - started) * 1000, 2),
        )
        return jsonify(payload)

    _schedule_refresh(cache_key, timeframe)
    warmed = _wait_for_cached_payload(cache_key, _ASYNC_COLD_WAIT_MS)
    if warmed is not None:
        warmed = _enrich_bhramhastra_payload(warmed)
        _cache.set(cache_key, warmed)
        _logger.info(
            "bhramhastra_request request_id=%s tf=%s refresh=%s source=oracle_cold_async latest_trading_date=%s sql_rows_returned=%s rows_after_filter=%s first_symbols=%s zero_reason=%s duration_ms=%s",
            request_id,
            timeframe,
            force_refresh,
            _resolve_latest_ltc_date(warmed.get("rows")) or "-",
            len(_payload_rows(warmed)),
            len(_payload_rows(warmed)),
            _first_symbols(warmed),
            _zero_reason(warmed, "oracle_cold_async"),
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
        "bhramhastra_request request_id=%s tf=%s refresh=%s source=warming latest_trading_date=- sql_rows_returned=0 rows_after_filter=0 first_symbols=- zero_reason=%s duration_ms=%s",
        request_id,
        timeframe,
        force_refresh,
        _zero_reason(payload, "warming", ["cold_start"]),
        round((time.perf_counter() - started) * 1000, 2),
    )
    return jsonify(payload)


@bp.get("/api/bhramhastra/last-ltc-date")
def api_bhramhastra_last_ltc_date():
    try:
        return jsonify({
            "status": "ok",
            "maxLtcDate": fetch_bhramhastra_max_ltc_date(),
        })
    except Exception as exc:
        _logger.exception("Bhramhastra last-ltc-date query failed")
        return jsonify({
            "status": "ok",
            "message": str(exc),
            "maxLtcDate": None,
        })


@bp.post("/api/bhramhastra/insert")
def api_bhramhastra_insert():
    correlation_id = request.headers.get("X-Correlation-Id") or str(uuid.uuid4())
    payload = request.get_json(silent=True) or {}
    raw_rows = payload if isinstance(payload, list) else payload.get("rows") if isinstance(payload, dict) else None
    rows = [row for row in (raw_rows or []) if isinstance(row, dict)]
    if not rows:
        return jsonify({
            "ok": False,
            "correlationId": correlation_id,
            "insertedCount": 0,
            "skippedCount": 0,
            "updatedCount": 0,
            "detail": "No valid rows to insert.",
        }), 400

    latest_ltc_date = _resolve_latest_ltc_date(rows)
    try:
        _payload, latest_snapshot = compute_bhramhastra_scan(timeframe="daily")
        result = upsert_bhramhastra_rows(rows, latest_snapshot)
        inserted = int(result.get("inserted") or 0)
        skipped = int(result.get("skipped") or 0)
        updated = int(result.get("updated") or 0)
        latest_ltc_date = result.get("latestLtcDate") or latest_ltc_date
        agent_result = _trigger_strategy_agent((payload.get("source") if isinstance(payload, dict) else "") or "bhramhastra_insert") if inserted > 0 else None
        return jsonify({
            "ok": True,
            "correlationId": correlation_id,
            "insertedCount": inserted,
            "skippedCount": skipped,
            "updatedCount": updated,
            "latestLtcDate": latest_ltc_date,
            "agent": agent_result,
        })
    except Exception as exc:
        _logger.exception("Bhramhastra insert failed correlationId=%s", correlation_id)
        return jsonify({
            "ok": False,
            "correlationId": correlation_id,
            "insertedCount": 0,
            "skippedCount": 0,
            "updatedCount": 0,
            "latestLtcDate": latest_ltc_date,
            "detail": str(exc),
        }), 500


def _auto_insert_once(reason: str = "schedule") -> Optional[Dict[str, Any]]:
    if not BHRAMHASTRA_AUTO_INSERT_ENABLED:
        return None
    correlation_id = str(uuid.uuid4())
    try:
        payload, latest_snapshot = compute_bhramhastra_scan(timeframe="daily")
        rows = list(payload.get("rows") or [])
        if not rows:
            _logger.info("Bhramhastra auto-insert: no rows to insert correlationId=%s reason=%s", correlation_id, reason)
            return {"status": "skipped", "reason": "no_rows", "insertedCount": 0, "skippedCount": 0}
        page_date = _resolve_latest_ltc_date(rows)
        last_inserted_date = fetch_bhramhastra_max_ltc_date()
        if page_date and last_inserted_date and page_date <= last_inserted_date:
            try:
                publish_notification(
                    source='bhramhastra_auto_insert',
                    message=f"Bhramhastra auto insertion already up to date for {page_date}.",
                    metadata={
                        'reason': reason,
                        'insertedRows': 0,
                        'skippedRows': len(rows),
                        'ltcDate': page_date,
                    },
                )
            except Exception as exc:
                _logger.warning('Bhramhastra auto-insert up-to-date notification failed correlationId=%s error=%s', correlation_id, exc)
            _logger.info(
                "Bhramhastra auto-insert skipped correlationId=%s reason=%s pageDate=%s lastInsertedDate=%s",
                correlation_id,
                reason,
                page_date,
                last_inserted_date,
            )
            return {
                "status": "ok",
                "upToDate": True,
                "insertedCount": 0,
                "skippedCount": len(rows),
                "latestLtcDate": page_date,
            }
        result = upsert_bhramhastra_rows(rows, latest_snapshot)
        inserted = int(result.get("inserted") or 0)
        updated = int(result.get("updated") or 0)
        skipped = int(result.get("skipped") or 0)
        if inserted > 0:
            _trigger_strategy_agent("bhramhastra_auto_insert")
        if inserted > 0 or skipped > 0 or updated > 0:
            try:
                publish_notification(
                    source='bhramhastra_auto_insert',
                    message=(
                        f"Bhramhastra auto insertion completed successfully for {inserted} symbols."
                        if inserted > 0
                        else f"Bhramhastra auto insertion completed successfully; existing rows already present for {result.get('latestLtcDate') or page_date or 'latest date'}."
                    ),
                    metadata={
                        'reason': reason,
                        'insertedRows': inserted,
                        'updatedRows': updated,
                        'skippedRows': skipped,
                        'ltcDate': result.get('latestLtcDate') or page_date or '',
                    },
                )
            except Exception as exc:
                _logger.warning('Bhramhastra auto-insert notification failed correlationId=%s error=%s', correlation_id, exc)
        _logger.info(
            "Bhramhastra auto-insert done correlationId=%s reason=%s rows=%s inserted=%s skipped=%s updated=%s",
            correlation_id,
            reason,
            len(rows),
            inserted,
            skipped,
            updated,
        )
        return {
            "status": "ok",
            "insertedCount": inserted,
            "skippedCount": skipped,
            "updatedCount": updated,
            "latestLtcDate": result.get("latestLtcDate") or page_date,
        }
    except Exception:
        _logger.exception("Bhramhastra auto-insert failed correlationId=%s reason=%s", correlation_id, reason)
        return None


def start_bhramhastra_auto_insert() -> None:
    global _auto_insert_started
    if _auto_insert_started or not BHRAMHASTRA_AUTO_INSERT_ENABLED:
        return
    _auto_insert_started = True

    def _loop() -> None:
        startup_delay = max(5, int(os.getenv('BHRAMHASTRA_AUTO_INSERT_STARTUP_DELAY_SEC', '25')))
        try:
            time.sleep(startup_delay)
            _auto_insert_once(reason='startup')
        except Exception:
            _logger.exception('Bhramhastra startup auto-insert failed')
        while True:
            try:
                now = datetime.now()
                parts = BHRAMHASTRA_AUTO_INSERT_TIME.split(":", 1)
                hour = int(parts[0]) if parts and parts[0].isdigit() else 18
                minute = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
                target = datetime(now.year, now.month, now.day, hour, minute)
                if target <= now:
                    target = target + timedelta(days=1)
                sleep_seconds = max(30, int((target - now).total_seconds()))
                time.sleep(sleep_seconds)
                _auto_insert_once(reason="schedule")
            except Exception:
                _logger.exception("Bhramhastra auto-insert scheduler error")
                time.sleep(300)

    threading.Thread(target=_loop, name="bhramhastra-auto-insert", daemon=True).start()

