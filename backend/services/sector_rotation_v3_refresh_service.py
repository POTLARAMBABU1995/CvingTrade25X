from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime
from typing import Any

from services.sector_rotation_service import (
    ensure_sector_reference_data_synced,
    fetch_sector_rotation_rows,
)
from services.sector_rotation_v3_repository import (
    is_sector_rotation_v3_schema_available,
    publish_local_sector_rotation_v3_snapshot,
    publish_sector_rotation_v3_snapshot,
    read_latest_published_v3_snapshot,
)
from services.sector_rotation_v3_service import build_sector_rotation_v3_envelope
from services.sector_rotation_v3_stock_service import (
    read_sector_rotation_v3_stock_snapshot,
    refresh_sector_rotation_v3_stock_snapshot,
)


logger = logging.getLogger(__name__)
_REFRESH_LOCK = threading.RLock()


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    token = str(value or "").strip()[:10]
    if not token:
        return None
    try:
        return date.fromisoformat(token)
    except ValueError:
        return None


def refresh_sector_rotation_v3_snapshot(
    trade_date: date | None = None,
    *,
    force_reference_sync: bool = False,
) -> dict[str, Any]:
    """Calculate and atomically publish one V3 snapshot outside the API request path."""

    with _REFRESH_LOCK:
        started_at = time.perf_counter()
        logger.info(
            "sector_rotation_v3_refresh stage=start as_of_date=%s",
            trade_date.isoformat() if trade_date else "latest",
        )
        ensure_sector_reference_data_synced(force=force_reference_sync)
        rows = fetch_sector_rotation_rows(trade_date, include_history=True)
        if not rows:
            raise RuntimeError("No sector rows were available for the V3 refresh")
        envelope = build_sector_rotation_v3_envelope(
            rows,
            engine_version="v3",
            as_of_date=trade_date,
            cache_status="REFRESH",
            enforce_feature_gate=True,
        )
        persistence = "ORACLE"
        if is_sector_rotation_v3_schema_available():
            run_id = publish_sector_rotation_v3_snapshot(envelope)
        else:
            run_id = publish_local_sector_rotation_v3_snapshot(envelope)
            persistence = "LOCAL"
        published_envelope = {
            **envelope,
            "runId": run_id,
            "asOfDate": envelope.get("asOfDate"),
        }
        stock_snapshot = refresh_sector_rotation_v3_stock_snapshot(published_envelope)
        duration_ms = (time.perf_counter() - started_at) * 1000.0
        logger.info(
            "sector_rotation_v3_refresh stage=complete run_id=%s as_of_date=%s rows=%s duration_ms=%.2f",
            run_id,
            envelope.get("asOfDate"),
            len(envelope.get("rows") or []),
            duration_ms,
        )
        return {
            "ok": True,
            "runId": run_id,
            "modelVersion": envelope.get("modelVersion"),
            "asOfDate": envelope.get("asOfDate"),
            "rowCount": len(envelope.get("rows") or []),
            "durationMs": round(duration_ms, 2),
            "persistence": persistence,
            "stockSnapshot": {
                "modelVersion": stock_snapshot.get("modelVersion"),
                "sectorCount": stock_snapshot.get("sectorCount"),
                "stockCount": stock_snapshot.get("stockCount"),
                "technicalSourceDate": stock_snapshot.get("technicalSourceDate"),
            },
        }


def refresh_sector_rotation_v3_if_stale(
    trade_date: date,
    *,
    force_reference_sync: bool = False,
) -> dict[str, Any]:
    """Publish V3 only when the latest successful run is older than ``trade_date``."""

    with _REFRESH_LOCK:
        snapshot = read_latest_published_v3_snapshot()
        published_date = _as_date((snapshot or {}).get("asOfDate"))
        if published_date is not None and published_date >= trade_date:
            stock_snapshot = read_sector_rotation_v3_stock_snapshot()
            stock_matches = bool(
                stock_snapshot
                and str(stock_snapshot.get("runId") or "") == str((snapshot or {}).get("runId") or "")
                and _as_date(stock_snapshot.get("asOfDate")) == published_date
            )
            if not stock_matches:
                repaired = refresh_sector_rotation_v3_stock_snapshot(snapshot or {})
                return {
                    "ok": True,
                    "skipped": False,
                    "reason": "STOCK_SNAPSHOT_REPAIRED",
                    "runId": (snapshot or {}).get("runId"),
                    "modelVersion": (snapshot or {}).get("modelVersion"),
                    "asOfDate": published_date.isoformat(),
                    "rowCount": len((snapshot or {}).get("rows") or []),
                    "stockCount": repaired.get("stockCount"),
                    "durationMs": 0.0,
                }
            logger.info(
                "sector_rotation_v3_refresh stage=skip reason=already_current published_date=%s target_date=%s",
                published_date.isoformat(),
                trade_date.isoformat(),
            )
            return {
                "ok": True,
                "skipped": True,
                "reason": "ALREADY_CURRENT",
                "runId": (snapshot or {}).get("runId"),
                "modelVersion": (snapshot or {}).get("modelVersion"),
                "asOfDate": published_date.isoformat(),
                "rowCount": len((snapshot or {}).get("rows") or []),
                "durationMs": 0.0,
            }
        result = refresh_sector_rotation_v3_snapshot(
            trade_date,
            force_reference_sync=force_reference_sync,
        )
        return {**result, "skipped": False}


__all__ = [
    "refresh_sector_rotation_v3_if_stale",
    "refresh_sector_rotation_v3_snapshot",
]
