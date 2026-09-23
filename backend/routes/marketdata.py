from __future__ import annotations

import logging
import os
import sys
import threading
import time
import datetime as dt

from flask import Blueprint, jsonify, request, g
from error_log_service import capture_api_error

try:  # Support running as package or as loose module
    from ..services import marketdata_service as svc
    from ..services import fyers_holdings_service as fyers_holdings_svc
    from ..services import nifty500_sync_service as nifty500_svc
    from ..services import nse_mcap_service as nse_mcap_svc
    from ..services import nse_ffmc_service as nse_ffmc_svc
    from ..services import nse_delivery_service as nse_delivery_svc
    from ..services.marketdata_service import SymbolNotFoundError
    from ..services.sector_rotation_v3_refresh_service import refresh_sector_rotation_v3_if_stale
    from ..services.sector_snapshot_service import get_latest_ltc_date_fast
    from ..services.ui_notification_service import publish_notification
except ImportError:  # pragma: no cover
    from services import marketdata_service as svc  # type: ignore
    from services import fyers_holdings_service as fyers_holdings_svc  # type: ignore
    from services import nifty500_sync_service as nifty500_svc  # type: ignore
    from services import nse_mcap_service as nse_mcap_svc  # type: ignore
    from services import nse_ffmc_service as nse_ffmc_svc  # type: ignore
    from services import nse_delivery_service as nse_delivery_svc  # type: ignore
    from services.marketdata_service import SymbolNotFoundError  # type: ignore
    from services.sector_rotation_v3_refresh_service import refresh_sector_rotation_v3_if_stale  # type: ignore
    from services.sector_snapshot_service import get_latest_ltc_date_fast  # type: ignore
    from services.ui_notification_service import publish_notification  # type: ignore

bp = Blueprint("marketdata", __name__, url_prefix="/api/marketdata")
_logger = logging.getLogger(__name__)

def _env_int(name: str, default: int, minimum: int) -> int:
    raw = str(os.getenv(name, str(default))).strip()
    try:
        value = int(raw)
    except Exception:
        value = int(default)
    return max(int(minimum), value)


def _env_bool(name: str, default: bool = True) -> bool:
    raw = str(os.getenv(name, "1" if default else "0")).strip().lower()
    if raw in {"1", "true", "yes", "y", "on"}:
        return True
    if raw in {"0", "false", "no", "n", "off"}:
        return False
    return bool(default)


MARKETDATA_AUTO_MERGE_ENABLED = _env_bool(
    "AUTO_MERGE_ENABLED",
    _env_bool("MARKETDATA_AUTO_MERGE_ENABLED", True),
)
MARKETDATA_AUTO_MERGE_INITIAL_DELAY_SEC = _env_int(
    "AUTO_MERGE_STARTUP_DELAY_SECONDS",
    _env_int("MARKETDATA_AUTO_MERGE_INITIAL_DELAY_SEC", 15, 5),
    5,
)
MARKETDATA_AUTO_MERGE_INTERVAL_SEC = _env_int(
    "AUTO_MERGE_INTERVAL_SECONDS",
    _env_int("MARKETDATA_AUTO_MERGE_INTERVAL_SEC", 120, 30),
    30,
)
_auto_merge_started = False
_auto_merge_lock = threading.Lock()
_auto_merge_status_lock = threading.Lock()
_auto_merge_status: dict[str, object] = {}
_last_skip_notification_signature = ""


def _json_error(message: str, status: int = 400):
    safe_message = "Internal server error." if int(status) >= 500 else str(message or "Invalid request parameter")
    payload = {
        "status": "error",
        "message": safe_message,
        "request_id": getattr(g, "request_id", "") or request.headers.get("X-Request-ID", ""),
    }
    if status >= 500:
        exc = sys.exc_info()[1]
        payload.update(capture_api_error(
            request=request,
            status=status,
            message=safe_message,
            extra={"blueprint": bp.name},
            exc=exc if isinstance(exc, BaseException) else None,
        ))
    return jsonify(payload), status


def _fyers_json_response(payload: dict):
    status = str(payload.get("status") or "").strip().upper()
    code = str(payload.get("code") or payload.get("errorCode") or "").strip().upper()
    if payload.get("canExtract") is False and (
        status in {
            "AUTH_REQUIRED",
            "AUTH_VALIDATION_FAILED",
            "INVALID_REFRESH_TOKEN",
            "STALE_CALLBACK",
        }
        or code.startswith("FYERS_AUTH")
        or code in {"FYERS_INVALID_REFRESH_TOKEN", "FYERS_STALE_CALLBACK"}
    ):
        return jsonify(payload), 428
    return jsonify(payload)


def _as_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


@bp.get("/symbols")
def symbols_endpoint():
    q = request.args.get("q")
    limit = request.args.get("limit", type=int)
    source = request.args.get("source")
    if limit is not None and (limit < 1 or limit > svc.MAX_LIMIT):
        return _json_error("Invalid request parameter: limit", 400)
    try:
        rows = svc.list_symbols(q, limit, source=source)
        return jsonify(rows)
    except ValueError as exc:
        return _json_error(str(exc), 400)


@bp.get("/stock/summary")
def stock_summary_endpoint():
    symbol = request.args.get("symbol", "", type=str)
    source = request.args.get("source")
    try:
        data = svc.stock_summary(symbol, source=source)
        return jsonify(data)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except SymbolNotFoundError as exc:
        return _json_error(str(exc), 404)


@bp.get("/summary/table")
def summary_table_endpoint():
    timeframe = request.args.get("timeframe", "daily")
    symbol = request.args.get("symbol")
    source = request.args.get("source")
    try:
        rows = svc.summary_table(timeframe, symbol, source=source)
        return jsonify(rows)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except SymbolNotFoundError as exc:
        return _json_error(str(exc), 404)


@bp.get("/stats")
def market_stats_endpoint():
    source = request.args.get("source")
    try:
        data = svc.market_stats(source=source)
        return jsonify(data)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.get("/stock/ohlcv")
def stock_ohlcv_endpoint():
    symbol = request.args.get("symbol", "", type=str)
    granularity = request.args.get("granularity", "daily")
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    try:
        rows = svc.stock_ohlcv(symbol, granularity, date_from, date_to)
        return jsonify(rows)
    except SymbolNotFoundError as exc:
        return _json_error(str(exc), 404)
    except ValueError as exc:
        return _json_error(str(exc), 400)


def _refresh_ui_caches_after_merge() -> None:
    try:
        try:
            from .asura import invalidate_asura_cache
            from .bhramhaputra import invalidate_bhramhaputra_cache
            from .bhramhastra import invalidate_bhramhastra_cache
            from .dashboard import invalidate_dashboard_cache, warm_dashboard_cache
            from .trend import invalidate_trend_cache, warm_trend_cache
            from .volume import invalidate_volume_cache, warm_volume_cache
        except ImportError:  # pragma: no cover
            from backend.routes.asura import invalidate_asura_cache  # type: ignore
            from backend.routes.bhramhaputra import invalidate_bhramhaputra_cache  # type: ignore
            from backend.routes.bhramhastra import invalidate_bhramhastra_cache  # type: ignore
            from backend.routes.dashboard import invalidate_dashboard_cache, warm_dashboard_cache  # type: ignore
            from backend.routes.trend import invalidate_trend_cache, warm_trend_cache  # type: ignore
            from backend.routes.volume import invalidate_volume_cache, warm_volume_cache  # type: ignore

        invalidate_asura_cache()
        invalidate_bhramhaputra_cache(clear_snapshots=True)
        invalidate_bhramhastra_cache(clear_snapshots=True)
        invalidate_dashboard_cache()
        invalidate_trend_cache(clear_latest_date=True)
        invalidate_volume_cache()
        warm_dashboard_cache()
        warm_trend_cache()
        warm_volume_cache()

        # Refresh sector materialized views and caches
        try:
            from db import get_oracle_connection
            from services.sector_cache_service import sector_cache_service
            
            # Clear in-memory caches
            sector_cache_service.clear_sector_cache()
            
            # Refresh Oracle materialized views
            conn = get_oracle_connection()
            with conn.cursor() as cursor:
                try:
                    cursor.execute("BEGIN DBMS_MVIEW.REFRESH('MV_NSE_SECTOR_UI_SNAPSHOT', 'C'); END;")
                except Exception:
                    _logger.exception("Failed MV refresh for MV_NSE_SECTOR_UI_SNAPSHOT")
                try:
                    cursor.execute("BEGIN DBMS_MVIEW.REFRESH('MV_NSE_SECTOR_BREADTH', 'C'); END;")
                except Exception:
                    _logger.exception("Failed MV refresh for MV_NSE_SECTOR_BREADTH")
            conn.commit()
            conn.close()
        except Exception:
            _logger.exception("Failed to refresh sector MVs in _refresh_ui_caches_after_merge")
    except Exception:
        return


def _now_iso() -> str:
    return dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def _next_run_id(source: str) -> str:
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    token = str(source or "auto").strip().upper().replace("-", "_")
    return f"AUTO_MERGE_{token}_{stamp}"


def _to_int(value: object) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _build_merge_running_status(
    *,
    source: str,
    run_id: str,
    started: str,
    message: str = "Auto merge is running.",
) -> dict[str, object]:
    return {
        "ok": True,
        "run_id": run_id,
        "status": "RUNNING",
        "is_running": True,
        "message": message,
        "started_at": started,
        "completed_at": "",
        "duration_ms": 0,
        "source": source,
        "source_table": "",
        "targets": [],
        "latest_trading_date": "",
        "source_latest_rows": 0,
        "dev_latest_date": "",
        "oracle_latest_date": "",
        "pending_dev_rows": 0,
        "pending_oracle_rows": 0,
        "merge_required": False,
        "dev_inserted": 0,
        "dev_updated": 0,
        "dev_skipped": 0,
        "oracle_inserted": 0,
        "oracle_updated": 0,
        "oracle_skipped": 0,
        "inserted_dev": 0,
        "updated_dev": 0,
        "inserted_oracle": 0,
        "updated_oracle": 0,
        "skip_reason": "",
        "error": "",
        "auto_merge_enabled": bool(MARKETDATA_AUTO_MERGE_ENABLED),
        "auto_merge_interval_seconds": int(MARKETDATA_AUTO_MERGE_INTERVAL_SEC),
        "auto_merge_startup_delay_seconds": int(MARKETDATA_AUTO_MERGE_INITIAL_DELAY_SEC),
    }


def _status_payload_snapshot() -> dict[str, object]:
    with _auto_merge_status_lock:
        if not _auto_merge_status:
            return {
                "ok": True,
                "run_id": "",
                "status": "IDLE",
                "is_running": False,
                "message": "Auto merge is idle.",
                "started_at": "",
                "completed_at": "",
                "duration_ms": 0,
                "source": "",
                "source_table": "",
                "targets": [],
                "latest_trading_date": "",
                "source_latest_rows": 0,
                "dev_latest_date": "",
                "oracle_latest_date": "",
                "pending_dev_rows": 0,
                "pending_oracle_rows": 0,
                "merge_required": False,
                "dev_inserted": 0,
                "dev_updated": 0,
                "dev_skipped": 0,
                "oracle_inserted": 0,
                "oracle_updated": 0,
                "oracle_skipped": 0,
                "inserted_dev": 0,
                "updated_dev": 0,
                "inserted_oracle": 0,
                "updated_oracle": 0,
                "error": "",
                "auto_merge_enabled": bool(MARKETDATA_AUTO_MERGE_ENABLED),
                "auto_merge_interval_seconds": int(MARKETDATA_AUTO_MERGE_INTERVAL_SEC),
                "auto_merge_startup_delay_seconds": int(MARKETDATA_AUTO_MERGE_INITIAL_DELAY_SEC),
            }
        return dict(_auto_merge_status)


def _save_status(payload: dict[str, object]) -> dict[str, object]:
    with _auto_merge_status_lock:
        _auto_merge_status.clear()
        _auto_merge_status.update(payload)
        return dict(_auto_merge_status)


def _save_merge_already_running_status(*, source: str, run_id: str, started: str, started_ts: float) -> dict[str, object]:
    current = _status_payload_snapshot()
    duration_ms = int((time.perf_counter() - started_ts) * 1000)
    payload = {
        **current,
        "ok": True,
        "run_id": str(current.get("run_id") or run_id),
        "status": "RUNNING",
        "is_running": True,
        "source": str(current.get("source") or source),
        "started_at": str(current.get("started_at") or started),
        "completed_at": "",
        "duration_ms": duration_ms,
        "message": "Merge is already running. Track completion from the toolbar/status toast.",
        "skip_reason": "Merge is already running.",
        "auto_merge_enabled": bool(MARKETDATA_AUTO_MERGE_ENABLED),
        "auto_merge_interval_seconds": int(MARKETDATA_AUTO_MERGE_INTERVAL_SEC),
        "auto_merge_startup_delay_seconds": int(MARKETDATA_AUTO_MERGE_INITIAL_DELAY_SEC),
    }
    _logger.info("[AUTO_MERGE_LOCKED_ALREADY_RUNNING] source=%s run_id=%s", source, run_id)
    return _save_status(payload)


def _build_merge_message(status: str, payload: dict[str, object]) -> str:
    state = str(status or "").upper()
    dev_inserted = _to_int(payload.get("dev_inserted"))
    dev_updated = _to_int(payload.get("dev_updated"))
    oracle_inserted = _to_int(payload.get("oracle_inserted"))
    oracle_updated = _to_int(payload.get("oracle_updated"))
    dev_merged = dev_inserted + dev_updated
    oracle_merged = oracle_inserted + oracle_updated

    if state == "FAILED":
        return str(payload.get("error") or payload.get("message") or "Auto merge failed. Check backend logs.")
    if state in {"SKIPPED", "SKIPPED_ALREADY_RUNNING"}:
        return "Already Up-to-Date"
    if dev_merged == oracle_merged:
        return f"{dev_merged} merged both the tables."
    return f"Dev:{dev_merged} and Oracle:{oracle_merged} merged both the tables."


def _merge_has_new_rows(payload: dict | None) -> bool:
    data = payload if isinstance(payload, dict) else {}
    dev = int(data.get("inserted_dev") or data.get("insertedDev") or 0)
    dev += int(data.get("inserted_dev_reconciled") or 0)
    dev += int(data.get("updated_dev") or data.get("updatedDev") or 0)
    oracle = int(data.get("inserted_oracle") or data.get("insertedOracle") or 0)
    oracle += int(data.get("updated_oracle") or data.get("updatedOracle") or 0)
    if (dev + oracle) > 0:
        return True
    message = str(data.get("message") or "").strip().lower()
    return bool(message) and "no new rows" not in message


def _publish_auto_merge_notification(payload: dict | None) -> None:
    global _last_skip_notification_signature
    data = payload if isinstance(payload, dict) else {}
    run_id = str(data.get("run_id") or "").strip()
    status = str(data.get("status") or "").strip().upper()
    source = str(data.get("source") or "scheduler").strip().lower()
    if not run_id:
        return
    if source not in {"scheduler", "auto", "manual", "fyers", "startup"}:
        source = "scheduler"
    if status in {"SKIPPED", "SKIPPED_ALREADY_RUNNING"}:
        skip_signature = "|".join([
            status,
            str(data.get("latest_trading_date") or ""),
            str(data.get("pending_dev_rows") or ""),
            str(data.get("pending_oracle_rows") or ""),
        ])
        if skip_signature == _last_skip_notification_signature:
            return
        _last_skip_notification_signature = skip_signature
    else:
        _last_skip_notification_signature = ""

    level = "success"
    if status == "FAILED":
        level = "error"
    elif status in {"SKIPPED", "SKIPPED_ALREADY_RUNNING"}:
        level = "info"
    message = _build_merge_message(status, data)
    publish_notification(
        source="database_auto_merge",
        level=level,
        message=message,
        metadata={
            "reason": "database_auto_merge",
            "runId": run_id,
            "status": status,
            "sourceTable": data.get("source_table"),
            "targets": data.get("targets") or [],
            "latestTradingDate": data.get("latest_trading_date"),
            "devInserted": _to_int(data.get("dev_inserted")),
            "devUpdated": _to_int(data.get("dev_updated")),
            "devSkipped": _to_int(data.get("dev_skipped")),
            "oracleInserted": _to_int(data.get("oracle_inserted")),
            "oracleUpdated": _to_int(data.get("oracle_updated")),
            "oracleSkipped": _to_int(data.get("oracle_skipped")),
            "pendingDevRows": _to_int(data.get("pending_dev_rows")),
            "pendingOracleRows": _to_int(data.get("pending_oracle_rows")),
            "durationMs": _to_int(data.get("duration_ms")),
        },
    )


def _trigger_post_merge_automations() -> None:
    targets = [("sector_rotation_v3", _refresh_sector_rotation_v3_after_merge)]
    try:
        try:
            from .asura import _auto_insert_once as asura_auto_insert_once
        except ImportError:  # pragma: no cover
            from backend.routes.asura import _auto_insert_once as asura_auto_insert_once  # type: ignore
        targets.append(("asura", asura_auto_insert_once))
    except Exception:
        _logger.exception("Database auto-merge could not load Asura auto insert")
    try:
        try:
            from .bhramhaputra import _auto_insert_once as bhramhaputra_auto_insert_once
        except ImportError:  # pragma: no cover
            from backend.routes.bhramhaputra import _auto_insert_once as bhramhaputra_auto_insert_once  # type: ignore
        targets.append(("bhramhaputra", bhramhaputra_auto_insert_once))
    except Exception:
        _logger.exception("Database auto-merge could not load Bhramhaputra auto insert")
    try:
        try:
            from .bhramhastra import _auto_insert_once as bhramhastra_auto_insert_once
        except ImportError:  # pragma: no cover
            from backend.routes.bhramhastra import _auto_insert_once as bhramhastra_auto_insert_once  # type: ignore
        targets.append(("bhramhastra", bhramhastra_auto_insert_once))
    except Exception:
        _logger.exception("Database auto-merge could not load Bhramhastra auto insert")
    try:
        try:
            from .yamuna import run_yamuna_auto_ingest_once
        except ImportError:  # pragma: no cover
            from backend.routes.yamuna import run_yamuna_auto_ingest_once  # type: ignore
        targets.append(("yamuna", run_yamuna_auto_ingest_once))
    except Exception:
        _logger.exception("Database auto-merge could not load Yamuna auto ingest")

    for name, fn in targets:
        try:
            fn(reason="latest_available")
        except Exception:
            _logger.exception("Database auto-merge downstream automation failed for %s", name)


def _refresh_sector_rotation_v3_after_merge(*, reason: str) -> dict[str, object]:
    latest_dev_date = get_latest_ltc_date_fast()
    if latest_dev_date is None:
        _logger.info(
            "sector_rotation_v3_post_merge stage=skip reason=no_dev_date trigger=%s",
            reason,
        )
        return {"ok": True, "skipped": True, "reason": "NO_DEV_DATE"}
    result = refresh_sector_rotation_v3_if_stale(
        latest_dev_date,
        force_reference_sync=True,
    )
    _logger.info(
        "sector_rotation_v3_post_merge stage=complete trigger=%s as_of_date=%s skipped=%s run_id=%s",
        reason,
        result.get("asOfDate"),
        bool(result.get("skipped")),
        result.get("runId"),
    )
    return result


def _execute_merge_cycle(
    *,
    source: str,
    force: bool = False,
    run_id: str | None = None,
    started: str | None = None,
    started_ts: float | None = None,
    lock_already_acquired: bool = False,
) -> dict[str, object]:
    started = started or _now_iso()
    started_ts = started_ts if started_ts is not None else time.perf_counter()
    run_id = run_id or _next_run_id(source)
    acquired_lock = bool(lock_already_acquired)
    if not acquired_lock:
        acquired_lock = _auto_merge_lock.acquire(blocking=False)
    if not acquired_lock:
        return _save_merge_already_running_status(source=source, run_id=run_id, started=started, started_ts=started_ts)
    status_running = _save_status(_build_merge_running_status(source=source, run_id=run_id, started=started))

    try:
        availability = svc.get_auto_merge_availability()
        source_latest = str(availability.get("source_latest_trade_date") or "")
        dev_latest = str(availability.get("dev_latest_trade_date") or "")
        oracle_latest = str(availability.get("oracle_latest_trade_date") or "")
        pending_dev = _to_int(availability.get("pending_dev_rows"))
        pending_oracle = _to_int(availability.get("pending_oracle_rows"))
        merge_required = bool(availability.get("merge_required"))
        source_rows = _to_int(availability.get("source_latest_row_count"))
        oracle_available = bool(availability.get("oracle_available", True))
        oracle_error = str(availability.get("oracle_error") or "").strip()
        _logger.info(
            "[AUTO_MERGE_CHECK] run_id=%s source=%s source_latest=%s dev_latest=%s oracle_latest=%s pending_dev=%s pending_oracle=%s merge_required=%s",
            run_id,
            source,
            source_latest or "-",
            dev_latest or "-",
            oracle_latest or "-",
            pending_dev,
            pending_oracle if oracle_available else -1,
            merge_required,
        )

        base_payload = {
            **status_running,
            "source_table": str(availability.get("source_table") or ""),
            "targets": [
                str(availability.get("dev_table") or ""),
                str(availability.get("oracle_table") or ""),
            ],
            "latest_trading_date": source_latest,
            "source_latest_rows": source_rows,
            "dev_latest_date": dev_latest,
            "oracle_latest_date": oracle_latest,
            "pending_dev_rows": pending_dev,
            "pending_oracle_rows": pending_oracle if oracle_available else 0,
            "merge_required": merge_required,
            "oracle_available": oracle_available,
            "oracle_error": oracle_error,
        }

        if not source_latest:
            duration_ms = int((time.perf_counter() - started_ts) * 1000)
            payload = {
                **base_payload,
                "status": "SKIPPED",
                "is_running": False,
                "completed_at": _now_iso(),
                "duration_ms": duration_ms,
                "message": "Auto merge skipped: STOCK_EOD_HISTORY has no rows.",
                "skip_reason": "Auto merge skipped: STOCK_EOD_HISTORY has no rows.",
            }
            _logger.info("[AUTO_MERGE_SKIP_NO_SOURCE_DATA] run_id=%s source=%s", run_id, source)
            return _save_status(payload)

        if not merge_required:
            duration_ms = int((time.perf_counter() - started_ts) * 1000)
            payload = {
                **base_payload,
                "status": "SKIPPED",
                "is_running": False,
                "completed_at": _now_iso(),
                "duration_ms": duration_ms,
                "message": "Already Up-to-Date",
                "skip_reason": "Already Up-to-Date",
            }
            _logger.info("[AUTO_MERGE_SKIP_NO_NEW_DATA] run_id=%s source=%s latest=%s", run_id, source, source_latest)
            return _save_status(payload)

        summary = svc.merge_latest()
        try:
            from services.market_table_sync_service import sync_latest_market_tables
            sync_latest_market_tables()
        except Exception:
            _logger.exception("Auto sync of market tables failed after merge")
        _refresh_ui_caches_after_merge()
        post_availability = svc.get_auto_merge_availability()
        dev_inserted = _to_int(summary.get("inserted_dev"))
        oracle_inserted = _to_int(summary.get("inserted_oracle"))
        dev_updated = _to_int(summary.get("updated_dev"))
        oracle_updated = _to_int(summary.get("updated_oracle"))
        dev_skipped = max(0, pending_dev - dev_inserted - dev_updated)
        oracle_skipped = max(0, pending_oracle - oracle_inserted - oracle_updated) if oracle_available else 0
        has_new_rows = _merge_has_new_rows(summary)
        status = "SUCCESS" if has_new_rows else "SKIPPED"
        duration_ms = int((time.perf_counter() - started_ts) * 1000)
        payload = {
            **base_payload,
            "status": status,
            "is_running": False,
            "completed_at": _now_iso(),
            "duration_ms": duration_ms,
            "dev_inserted": dev_inserted,
            "dev_updated": dev_updated,
            "dev_skipped": dev_skipped,
            "oracle_inserted": oracle_inserted,
            "oracle_updated": oracle_updated,
            "oracle_skipped": oracle_skipped,
            "inserted_dev": dev_inserted,
            "updated_dev": dev_updated,
            "inserted_oracle": oracle_inserted,
            "updated_oracle": oracle_updated,
            "dev_latest_date": str(post_availability.get("dev_latest_trade_date") or dev_latest),
            "oracle_latest_date": str(post_availability.get("oracle_latest_trade_date") or oracle_latest),
            "pending_dev_rows": _to_int(post_availability.get("pending_dev_rows")),
            "pending_oracle_rows": _to_int(post_availability.get("pending_oracle_rows")) if oracle_available else 0,
            "merge_required": bool(post_availability.get("merge_required")),
        }
        payload["message"] = _build_merge_message(status, payload)
        if has_new_rows:
            _logger.info(
                "[AUTO_MERGE_DEV_SUCCESS] run_id=%s source=%s inserted=%s updated=%s duration_ms=%s",
                run_id,
                source,
                dev_inserted,
                dev_updated,
                duration_ms,
            )
            _logger.info(
                "[AUTO_MERGE_ORACLE_SUCCESS] run_id=%s source=%s inserted=%s updated=%s duration_ms=%s",
                run_id,
                source,
                oracle_inserted,
                oracle_updated,
                duration_ms,
            )
            if source in {"scheduler", "startup", "manual", "fyers"}:
                threading.Thread(
                    target=_trigger_post_merge_automations,
                    name=f"marketdata-post-merge-{source}",
                    daemon=True,
                ).start()
        else:
            payload["skip_reason"] = "Already Up-to-Date"
            _logger.info("[AUTO_MERGE_SKIP_NO_NEW_DATA] run_id=%s source=%s latest=%s", run_id, source, source_latest)
        return _save_status(payload)
    except Exception as exc:
        duration_ms = int((time.perf_counter() - started_ts) * 1000)
        _logger.exception("[AUTO_MERGE_FAILED] run_id=%s source=%s", run_id, source)
        payload = {
            **status_running,
            "ok": False,
            "status": "FAILED",
            "is_running": False,
            "completed_at": _now_iso(),
            "duration_ms": duration_ms,
            "error": str(exc or "").strip() or "Unknown merge failure.",
            "message": "Auto merge failed. Check backend logs.",
        }
        return _save_status(payload)
    finally:
        if acquired_lock:
            try:
                _auto_merge_lock.release()
            except Exception:
                pass


def _run_auto_merge_cycle(*, source: str) -> None:
    payload = _execute_merge_cycle(source=source, force=False)
    _publish_auto_merge_notification(payload)


def _run_manual_merge_cycle_background(*, run_id: str, started: str, started_ts: float) -> None:
    payload = _execute_merge_cycle(
        source="manual",
        force=True,
        run_id=run_id,
        started=started,
        started_ts=started_ts,
        lock_already_acquired=True,
    )
    _publish_auto_merge_notification(payload)


def _start_manual_merge_cycle_background() -> dict[str, object]:
    started = _now_iso()
    started_ts = time.perf_counter()
    run_id = _next_run_id("manual")
    if not _auto_merge_lock.acquire(blocking=False):
        return _save_merge_already_running_status(
            source="manual",
            run_id=run_id,
            started=started,
            started_ts=started_ts,
        )

    status_running = _save_status(_build_merge_running_status(
        source="manual",
        run_id=run_id,
        started=started,
        message="Manual merge started in background. Track completion from the toolbar/status toast.",
    ))
    try:
        threading.Thread(
            target=_run_manual_merge_cycle_background,
            kwargs={"run_id": run_id, "started": started, "started_ts": started_ts},
            name=f"marketdata-manual-merge-{run_id}",
            daemon=True,
        ).start()
    except Exception as exc:
        try:
            _auto_merge_lock.release()
        except Exception:
            pass
        payload = {
            **status_running,
            "ok": False,
            "status": "FAILED",
            "is_running": False,
            "completed_at": _now_iso(),
            "duration_ms": int((time.perf_counter() - started_ts) * 1000),
            "error": str(exc or "").strip() or "Failed to start manual merge worker.",
            "message": "Manual merge failed to start.",
        }
        _logger.exception("[AUTO_MERGE_MANUAL_START_FAILED] run_id=%s", run_id)
        return _save_status(payload)
    return {
        **status_running,
        "accepted": True,
        "message": "Manual merge started in background. Track completion from the toolbar/status toast.",
    }


def start_marketdata_auto_merge() -> None:
    global _auto_merge_started
    if _auto_merge_started or not MARKETDATA_AUTO_MERGE_ENABLED:
        return
    _auto_merge_started = True
    _logger.info(
        "[AUTO_MERGE_START] enabled=%s initial_delay_sec=%s interval_sec=%s",
        MARKETDATA_AUTO_MERGE_ENABLED,
        MARKETDATA_AUTO_MERGE_INITIAL_DELAY_SEC,
        MARKETDATA_AUTO_MERGE_INTERVAL_SEC,
    )

    def _loop() -> None:
        time.sleep(MARKETDATA_AUTO_MERGE_INITIAL_DELAY_SEC)
        while True:
            try:
                _run_auto_merge_cycle(source="scheduler")
            except Exception:
                _logger.exception("Marketdata auto-merge scheduler error")
            time.sleep(MARKETDATA_AUTO_MERGE_INTERVAL_SEC)

    threading.Thread(target=_loop, name="marketdata-auto-merge", daemon=True).start()


@bp.post("/merge-latest")
def merge_latest_endpoint():
    payload = _start_manual_merge_cycle_background()
    status_code = 202 if payload.get("is_running") else 200
    if str(payload.get("status") or "").upper() == "FAILED":
        status_code = 500
    return jsonify(payload), status_code


@bp.get("/merge/status/latest")
def merge_latest_status_endpoint():
    return jsonify(_status_payload_snapshot())


@bp.post("/stock-eod/clear")
@bp.post("/stock-eod/clear/")
def clear_stock_eod_history_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        result = svc.clear_stock_eod_history(payload.get("confirm_text"))
        _refresh_ui_caches_after_merge()
        return jsonify(result)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except svc.StockEodDeleteError as exc:
        return _json_error(str(exc), 409)
    except Exception as exc:
        _logger.exception("STOCK_EOD_HISTORY delete failed")
        return jsonify({
            "ok": False,
            "success": False,
            "status": "error",
            "message": "Failed to delete STOCK_EOD_HISTORY rows. Check backend logs for details.",
            "request_id": getattr(g, "request_id", "") or request.headers.get("X-Request-ID", ""),
        }), 500


def _nse_calendar_page_service(page: str):
    token = str(page or "").strip().upper().replace("-", "_").replace(" ", "_")
    if token in {"FFMC", "NSE_FFMC"}:
        return nse_ffmc_svc.get_trading_day_verification
    if token in {"DELIVERY", "NSE_DELIVERY", "NSE_DELIVERY_DATA", "DELIVERY_DATA"}:
        return nse_delivery_svc.get_trading_day_verification
    if token in {"MARKET_CAP", "MARKETCAP", "MCAP", "NSE_MCAP", "NSE_MARKET_CAP"}:
        return nse_mcap_svc.get_trading_day_verification
    raise ValueError("page must be one of FFMC, DELIVERY, or MARKET_CAP.")


@bp.get("/market-calendar/trading-day-verification")
def nse_trading_day_verification_endpoint():
    page = request.args.get("page", "", type=str)
    raw_year = request.args.get("year", "", type=str).strip()
    try:
        year = int(raw_year) if raw_year else None
        if year is not None and (year < 1900 or year > 2100):
            raise ValueError("year must be between 1900 and 2100.")
        verifier = _nse_calendar_page_service(page)
        return jsonify(verifier(year=year))
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)



@bp.post("/nse-mcap/init")
def nse_mcap_init_endpoint():
    try:
        return jsonify(nse_mcap_svc.init_runtime_api())
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.get("/nse-mcap/summary")
def nse_mcap_summary_endpoint():
    trade_date = request.args.get("tradeDate") or request.args.get("trade_date")
    start_date = request.args.get("startDate") or request.args.get("start_date")
    end_date = request.args.get("endDate") or request.args.get("end_date")
    range_value = request.args.get("range") or request.args.get("dateRange") or request.args.get("date_range")
    limit = request.args.get("limit", type=int)
    try:
        data = nse_mcap_svc.get_dashboard(trade_date, limit=limit, start_date_text=start_date, end_date_text=end_date, range_text=range_value)
        summary = data.get("summary") if isinstance(data, dict) else {}
        _logger.info("NSE MCAP summary served tradeDate=%s successRows=%s insertedRows=%s source=%s",
                     data.get("tradeDate") if isinstance(data, dict) else trade_date,
                     (summary or {}).get("successRows"),
                     (summary or {}).get("insertedRows"),
                     (summary or {}).get("insertionSource"))
        return jsonify(data)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.get("/nse-mcap-index/latest")
def nse_mcap_index_latest_endpoint():
    try:
        return jsonify(nse_mcap_svc.get_marketcap_index_latest())
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.post("/nse-mcap/download")
def nse_mcap_download_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(nse_mcap_svc.download_api(payload))
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.post("/nse-mcap/validate")
def nse_mcap_validate_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(nse_mcap_svc.validate_api(payload))
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.post("/nse-mcap/process")
def nse_mcap_process_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(nse_mcap_svc.process_api(payload))
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.post("/nse-mcap/process-existing-csv-symbols")
def nse_mcap_process_existing_csv_symbols_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(nse_mcap_svc.process_existing_csv_for_symbols_api(payload))
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.post("/nse-mcap/pipeline/start")
def nse_mcap_pipeline_start_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(nse_mcap_svc.start_pipeline_job(payload))
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.get("/nse-mcap/jobs/latest")
def nse_mcap_latest_job_endpoint():
    tail = request.args.get("tail", type=int)
    try:
        return jsonify(nse_mcap_svc.get_latest_job(tail_lines=tail))
    except ValueError as exc:
        return _json_error(str(exc), 404)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.get("/nse-mcap/jobs/<job_id>")
def nse_mcap_job_endpoint(job_id: str):
    tail = request.args.get("tail", type=int)
    try:
        return jsonify(nse_mcap_svc.get_job(job_id, tail_lines=tail))
    except ValueError as exc:
        return _json_error(str(exc), 404)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.post("/nse-ffmc/init")
def nse_ffmc_init_endpoint():
    try:
        return jsonify(nse_ffmc_svc.init_runtime_api())
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.get("/nse-ffmc/summary")
def nse_ffmc_summary_endpoint():
    trade_date = request.args.get("tradeDate") or request.args.get("trade_date")
    start_date = request.args.get("startDate") or request.args.get("start_date")
    end_date = request.args.get("endDate") or request.args.get("end_date")
    range_value = request.args.get("range") or request.args.get("dateRange") or request.args.get("date_range")
    limit = request.args.get("limit", type=int)
    try:
        data = nse_ffmc_svc.get_dashboard(trade_date, limit=limit, start_date_text=start_date, end_date_text=end_date, range_text=range_value)
        summary = data.get("summary") if isinstance(data, dict) else {}
        _logger.info("NSE FFMC summary served tradeDate=%s successRows=%s insertedRows=%s source=%s",
                     data.get("tradeDate") if isinstance(data, dict) else trade_date,
                     (summary or {}).get("successRows"),
                     (summary or {}).get("insertedRows"),
                     (summary or {}).get("insertionSource"))
        return jsonify(data)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.post("/nse-ffmc/download")
def nse_ffmc_download_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(nse_ffmc_svc.download_api(payload))
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.post("/nse-ffmc/validate")
def nse_ffmc_validate_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(nse_ffmc_svc.validate_api(payload))
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.post("/nse-ffmc/process")
def nse_ffmc_process_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(nse_ffmc_svc.process_api(payload))
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.post("/nse-ffmc/process-existing-csv-symbols")
def nse_ffmc_process_existing_csv_symbols_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(nse_ffmc_svc.process_existing_csv_for_symbols_api(payload))
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.post("/nse-ffmc/pipeline/start")
def nse_ffmc_pipeline_start_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(nse_ffmc_svc.start_pipeline_job(payload))
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.get("/nse-ffmc/jobs/latest")
def nse_ffmc_latest_job_endpoint():
    tail = request.args.get("tail", type=int)
    try:
        return jsonify(nse_ffmc_svc.get_latest_job(tail_lines=tail))
    except ValueError as exc:
        return _json_error(str(exc), 404)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.get("/nse-ffmc/jobs/<job_id>")
def nse_ffmc_job_endpoint(job_id: str):
    tail = request.args.get("tail", type=int)
    try:
        return jsonify(nse_ffmc_svc.get_job(job_id, tail_lines=tail))
    except ValueError as exc:
        return _json_error(str(exc), 404)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.post("/nse-delivery/init")
def nse_delivery_init_endpoint():
    try:
        return jsonify(nse_delivery_svc.init_runtime_api())
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.get("/nse-delivery/summary")
def nse_delivery_summary_endpoint():
    trade_date = request.args.get("tradeDate") or request.args.get("trade_date")
    start_date = request.args.get("startDate") or request.args.get("start_date")
    end_date = request.args.get("endDate") or request.args.get("end_date")
    range_value = request.args.get("range") or request.args.get("dateRange") or request.args.get("date_range")
    limit = request.args.get("limit", type=int)
    try:
        data = nse_delivery_svc.get_dashboard(trade_date, limit=limit, start_date_text=start_date, end_date_text=end_date, range_text=range_value)
        summary = data.get("summary") if isinstance(data, dict) else {}
        _logger.info("NSE delivery summary served tradeDate=%s successRows=%s insertedRows=%s source=%s",
                     data.get("tradeDate") if isinstance(data, dict) else trade_date,
                     (summary or {}).get("successRows"),
                     (summary or {}).get("insertedRows"),
                     (summary or {}).get("insertionSource"))
        return jsonify(data)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.post("/nse-delivery/download")
def nse_delivery_download_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(nse_delivery_svc.download_api(payload))
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.post("/nse-delivery/validate")
def nse_delivery_validate_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(nse_delivery_svc.validate_api(payload))
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.post("/nse-delivery/process")
def nse_delivery_process_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(nse_delivery_svc.process_api(payload))
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.post("/nse-delivery/process-existing-csv-symbols")
def nse_delivery_process_existing_csv_symbols_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(nse_delivery_svc.process_existing_csv_for_symbols_api(payload))
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.post("/nse-delivery/pipeline/start")
def nse_delivery_pipeline_start_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(nse_delivery_svc.start_pipeline_job(payload))
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.get("/nse-delivery/jobs/latest")
def nse_delivery_latest_job_endpoint():
    tail = request.args.get("tail", type=int)
    try:
        return jsonify(nse_delivery_svc.get_latest_job(tail_lines=tail))
    except ValueError as exc:
        return _json_error(str(exc), 404)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.get("/nse-delivery/jobs/<job_id>")
def nse_delivery_job_endpoint(job_id: str):
    tail = request.args.get("tail", type=int)
    try:
        return jsonify(nse_delivery_svc.get_job(job_id, tail_lines=tail))
    except ValueError as exc:
        return _json_error(str(exc), 404)
    except Exception as exc:
        return _json_error(str(exc), 500)

@bp.get("/fyers/nifty500-sync")
def fyers_nifty500_sync_snapshot_endpoint():
    try:
        payload = nifty500_svc.get_nifty500_sync_snapshot()
        return jsonify(payload)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


def _read_nifty500_sync_upload_payload():
    if not request.files:
        return request.get_json(silent=True) or {}

    uploaded_files = request.files.getlist("files") or []
    if not uploaded_files:
        single = request.files.get("file")
        if single is not None:
            uploaded_files = [single]

    payload = dict(request.form or {})
    payload["uploadedFiles"] = [
        {
            "filename": uploaded.filename or "",
            "content": uploaded.read(),
        }
        for uploaded in uploaded_files
        if uploaded is not None and (uploaded.filename or "").strip()
    ]
    if payload["uploadedFiles"]:
        payload.setdefault("filename", payload["uploadedFiles"][0]["filename"])
    return payload


@bp.post("/fyers/nifty500-sync/compare")
def fyers_nifty500_sync_compare_endpoint():
    payload = _read_nifty500_sync_upload_payload()
    try:
        result = nifty500_svc.compare_nifty500_sync(payload)
        return jsonify(result)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.post("/fyers/nifty500-sync/merge")
def fyers_nifty500_sync_merge_endpoint():
    payload = _read_nifty500_sync_upload_payload()
    try:
        result = nifty500_svc.merge_missing_nifty500_symbols(payload)
        return jsonify(result)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.post("/fyers/nifty500-sync/rows")
def fyers_nifty500_sync_add_symbol_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        result = nifty500_svc.add_nifty500_symbol(payload)
        return jsonify(result)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.put("/fyers/nifty500-sync/rows")
def fyers_nifty500_sync_update_symbol_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        result = nifty500_svc.update_nifty500_symbol(payload)
        return jsonify(result)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.delete("/fyers/nifty500-sync/rows")
def fyers_nifty500_sync_delete_symbol_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        result = nifty500_svc.delete_nifty500_symbol(payload)
        return jsonify(result)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.post("/fyers/authorize")
def fyers_authorize_endpoint():
    raw = request.get_json(silent=True) or {}
    force = _as_bool(raw.get("force"), default=False)
    try:
        payload = svc.fyers_start_authorize_job({"force": force})
        return jsonify(payload)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return jsonify({
            "ok": False,
            "stage": "authorize",
            "message": str(exc),
            "stats": {"inserted": 0, "skipped": 0, "failed": 1, "errors": 1},
        })


@bp.get("/fyers/auth-status")
def fyers_auth_status_endpoint():
    try:
        payload = svc.fyers_auth_status()
        return jsonify(payload)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return jsonify({
            "ok": False,
            "stage": "authorize",
            "message": str(exc),
            "authenticatedToday": False,
        }), 500


@bp.get("/fyers/failed-symbols")
def fyers_failed_symbols_endpoint():
    params = {
        "status": request.args.get("status", "", type=str),
        "symbol": request.args.get("symbol", "", type=str),
        "from_date": request.args.get("from_date", "", type=str),
        "to_date": request.args.get("to_date", "", type=str),
        "source_mode": request.args.get("source_mode", "", type=str),
        "limit": request.args.get("limit", default=25, type=int),
        "offset": request.args.get("offset", default=0, type=int),
    }
    try:
        payload = svc.list_fyers_failed_symbols(params)
        return jsonify(payload)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.route("/fyers/failed-symbols", methods=["DELETE"])
def fyers_failed_symbols_delete_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        result = svc.delete_fyers_failed_symbols(payload)
        return jsonify(result)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return jsonify({
            "ok": False,
            "stage": "failed-symbol-delete",
            "message": str(exc),
            "deletedCount": 0,
        }), 500


@bp.post("/fyers/failed-symbols/rerun")
def fyers_failed_symbols_rerun_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        result = svc.fyers_rerun_failed_symbols_compat(payload, max_wait_seconds=0)
        return _fyers_json_response(result)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return jsonify({
            "ok": False,
            "stage": "failed-symbol-rerun",
            "message": str(exc),
            "stats": {"processed": 0, "inserted": 0, "skipped": 0, "failed": 1},
        }), 500


@bp.post("/fyers/failed-symbols/rerun/start")
def fyers_failed_symbols_rerun_start_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        result = svc.fyers_start_failed_symbols_rerun_job(payload)
        return _fyers_json_response(result)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return jsonify({
            "ok": False,
            "stage": "failed-symbol-rerun",
            "message": str(exc),
        }), 500


@bp.post("/fyers/single")
def fyers_single_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        result = svc.fyers_run_single(payload)
        return _fyers_json_response(result)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return jsonify({
            "ok": False,
            "stage": "single",
            "message": str(exc),
            "stats": {"inserted": 0, "skipped": 0, "failed": 1, "errors": 1},
        })


@bp.post("/fyers/single/start")
def fyers_single_start_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        result = svc.fyers_start_single_job(payload)
        return _fyers_json_response(result)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return jsonify({
            "ok": False,
            "stage": "single",
            "message": str(exc),
        }), 500


@bp.post("/fyers/batch")
def fyers_batch_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        result = svc.fyers_run_batch(payload)
        return _fyers_json_response(result)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return jsonify({
            "ok": False,
            "stage": "batch",
            "message": str(exc),
            "stats": {"inserted": 0, "skipped": 0, "failed": 1, "errors": 1},
        })


@bp.post("/fyers/batch/start")
@bp.post("/fyers/automation/start")
@bp.post("/fyers/extract/start")
def fyers_batch_start_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        result = svc.fyers_start_batch_job(payload)
        return _fyers_json_response(result)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return jsonify({
            "ok": False,
            "stage": "batch",
            "message": str(exc),
        }), 500


@bp.get("/fyers/jobs/latest")
def fyers_latest_job_endpoint():
    try:
        payload = svc.fyers_get_latest_job()
        return jsonify(payload)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.get("/fyers/jobs/<job_id>")
@bp.get("/fyers/automation/status/<job_id>")
@bp.get("/fyers/extract/status/<job_id>")
def fyers_job_status_endpoint(job_id: str):
    if job_id == "latest":
        return fyers_latest_job_endpoint()
    tail = request.args.get("tail", type=int)
    include_symbols = not (
        request.path.startswith("/api/marketdata/fyers/automation/status/")
        or request.path.startswith("/api/marketdata/fyers/extract/status/")
    )
    try:
        payload = svc.fyers_get_job(
            job_id,
            tail_lines=tail,
            include_symbols=include_symbols,
        )
        return jsonify(payload)
    except ValueError as exc:
        message = str(exc)
        request_id = getattr(g, "request_id", "") or request.headers.get("X-Request-ID", "")
        _logger.warning(
            "[FYERS][JOB_STATUS_404] request_id=%s job_id=%s tail=%s message=%s",
            request_id,
            job_id,
            tail,
            message,
        )
        if "FYERS job not found:" in message:
            return jsonify({
                "status": "error",
                "code": "FYERS_JOB_NOT_FOUND",
                "job_id": job_id,
                "message": message,
                "request_id": request_id,
                "timestamp": dt.datetime.utcnow().isoformat() + "Z",
            }), 404
        return _json_error(message, 404)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.post("/fyers/automation/stop")
def fyers_job_stop_endpoint():
    payload = request.get_json(silent=True) or {}
    job_id = str(payload.get("jobId") or payload.get("job_id") or "").strip()
    try:
        result = svc.fyers_request_stop(job_id)
        return jsonify(result)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.post("/fyers/automation/stop/<job_id>")
@bp.post("/fyers/extract/stop/<job_id>")
def fyers_job_stop_path_endpoint(job_id: str):
    try:
        return jsonify(svc.fyers_request_stop(job_id))
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


def _fyers_automation_action(handler):
    payload = request.get_json(silent=True) or {}
    try:
        return _fyers_json_response(handler(payload))
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.post("/fyers/automation/resume")
def fyers_automation_resume_endpoint():
    return _fyers_automation_action(svc.fyers_resume_job)


@bp.post("/fyers/automation/rerun-failed")
@bp.post("/fyers/extract/rerun-failed")
def fyers_automation_rerun_failed_endpoint():
    return _fyers_automation_action(svc.fyers_rerun_failed_job)


@bp.post("/fyers/automation/rerun-remaining")
@bp.post("/fyers/extract/rerun-remaining")
def fyers_automation_rerun_remaining_endpoint():
    return _fyers_automation_action(svc.fyers_rerun_remaining_job)


@bp.get("/fyers/automation/latest-active-job")
def fyers_automation_latest_active_job_endpoint():
    try:
        return jsonify(svc.fyers_get_latest_active_job())
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.get("/fyers/automation/skipped-symbols/<job_id>")
def fyers_automation_skipped_symbols_endpoint(job_id: str):
    try:
        return jsonify(svc.fyers_get_skipped_symbols(job_id))
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.post("/fyers/maintenance/cleanup-data-files")
def fyers_cleanup_data_files_endpoint():
    payload = request.get_json(silent=True) or {}
    dry_run = _as_bool(payload.get("dry_run") or payload.get("dryRun"), default=False)
    retention_days = payload.get("retention_days") or payload.get("retentionDays")
    try:
        result = svc.cleanup_fyers_data_files(
            retention_days=int(retention_days) if retention_days not in {None, ""} else None,
            dry_run=dry_run,
        )
        return jsonify(result)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.post("/fyers/holdings/import")
def fyers_holdings_import_endpoint():
    if request.files:
        uploaded = request.files.get("file")
        if uploaded is None:
            return _json_error("Holdings CSV file is required.", 400)
        try:
            csv_text = uploaded.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            return _json_error("Unable to decode holdings CSV. Use UTF-8 text.", 400)
        payload = dict(request.form or {})
        payload["csvText"] = csv_text
        payload.setdefault("filename", uploaded.filename or "")
    else:
        payload = request.get_json(silent=True) or {}
    try:
        result = fyers_holdings_svc.import_holdings(payload)
        return jsonify(result)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.get("/fyers/holdings")
def fyers_holdings_list_endpoint():
    try:
        result = fyers_holdings_svc.list_holdings(request.args.to_dict(flat=True))
        if isinstance(result, dict) and isinstance(result.get("holdings"), list):
            result = {
                **result,
                "holdings": nse_mcap_svc.enrich_rows_with_marketcap_index(
                    result.get("holdings") or [],
                    symbol_keys=("symbolCode", "symbol", "symbolRaw", "SYMBOL", "stock", "STOCK"),
                    allow_base_table_fallback=False,
                ),
            }
        return jsonify(result)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.get("/fyers/holdings/reconcile")
def fyers_holdings_reconcile_endpoint():
    try:
        result = fyers_holdings_svc.reconcile_holdings(request.args.to_dict(flat=True))
        return jsonify(result)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.get("/fyers/holdings/summary")
def fyers_holdings_summary_endpoint():
    try:
        result = fyers_holdings_svc.get_holdings_summary(request.args.to_dict(flat=True))
        return jsonify(result)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.get("/fyers/holdings/imports")
def fyers_holdings_imports_endpoint():
    try:
        result = fyers_holdings_svc.list_import_runs(request.args.to_dict(flat=True))
        return jsonify(result)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.post("/fyers/holdings")
def fyers_holdings_create_endpoint():
    payload = request.get_json(silent=True) or {}
    try:
        result = fyers_holdings_svc.create_holding(payload)
        return jsonify(result)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.put("/fyers/holdings/<int:holding_id>")
def fyers_holdings_update_endpoint(holding_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        result = fyers_holdings_svc.update_holding(holding_id, payload)
        return jsonify(result)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)


@bp.delete("/fyers/holdings/<int:holding_id>")
def fyers_holdings_delete_endpoint(holding_id: int):
    try:
        result = fyers_holdings_svc.delete_holding(holding_id)
        return jsonify(result)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception as exc:
        return _json_error(str(exc), 500)

