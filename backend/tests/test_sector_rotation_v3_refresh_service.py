from __future__ import annotations

from datetime import date

from services import sector_rotation_v3_refresh_service as refresh_service


def test_refresh_builds_then_atomically_publishes_v3_snapshot(monkeypatch):
    events: list[str] = []
    monkeypatch.setattr(
        refresh_service,
        "ensure_sector_reference_data_synced",
        lambda force=False: events.append(f"sync:{force}"),
    )
    monkeypatch.setattr(
        refresh_service,
        "fetch_sector_rotation_rows",
        lambda trade_date, include_history: [
            {"sectorCode": "AUTO", "sectorName": "Auto", "asOfDate": trade_date}
        ],
    )

    def build(rows, **kwargs):
        events.append("build")
        assert kwargs["engine_version"] == "v3"
        assert kwargs["cache_status"] == "REFRESH"
        return {
            "modelVersion": "SECTOR_ROTATION_V3",
            "asOfDate": "2026-07-15",
            "rows": [{"sectorCode": "AUTO", "modelVersion": "SECTOR_ROTATION_V3"}],
        }

    monkeypatch.setattr(refresh_service, "build_sector_rotation_v3_envelope", build)
    monkeypatch.setattr(refresh_service, "is_sector_rotation_v3_schema_available", lambda: True)
    monkeypatch.setattr(
        refresh_service,
        "publish_sector_rotation_v3_snapshot",
        lambda envelope: events.append("publish") or "run-1",
    )
    monkeypatch.setattr(
        refresh_service,
        "refresh_sector_rotation_v3_stock_snapshot",
        lambda envelope: events.append("publish-stocks") or {
            "modelVersion": "SECTOR_ROTATION_V3_STOCK_STRENGTH_1",
            "sectorCount": 1,
            "stockCount": 3,
            "technicalSourceDate": "2026-07-15",
        },
    )

    result = refresh_service.refresh_sector_rotation_v3_snapshot(
        date(2026, 7, 15),
        force_reference_sync=True,
    )

    assert events == ["sync:True", "build", "publish", "publish-stocks"]
    assert result["ok"] is True
    assert result["runId"] == "run-1"
    assert result["rowCount"] == 1
    assert result["stockSnapshot"]["stockCount"] == 3


def test_refresh_if_stale_skips_an_already_current_snapshot(monkeypatch):
    monkeypatch.setattr(
        refresh_service,
        "read_latest_published_v3_snapshot",
        lambda: {
            "asOfDate": "2026-07-22",
            "modelVersion": "SECTOR_ROTATION_V3",
            "runId": "run-current",
            "rows": [{"sectorCode": "AUTO"}],
        },
    )
    monkeypatch.setattr(
        refresh_service,
        "read_sector_rotation_v3_stock_snapshot",
        lambda: {"asOfDate": "2026-07-22", "runId": "run-current"},
    )
    monkeypatch.setattr(
        refresh_service,
        "refresh_sector_rotation_v3_snapshot",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not republish")),
    )

    result = refresh_service.refresh_sector_rotation_v3_if_stale(date(2026, 7, 22))

    assert result["ok"] is True
    assert result["skipped"] is True
    assert result["reason"] == "ALREADY_CURRENT"
    assert result["runId"] == "run-current"


def test_refresh_if_stale_publishes_target_dev_date(monkeypatch):
    calls: list[tuple[date, bool]] = []
    monkeypatch.setattr(
        refresh_service,
        "read_latest_published_v3_snapshot",
        lambda: {"asOfDate": "2026-07-20", "runId": "run-old", "rows": [{}]},
    )

    def refresh(trade_date, *, force_reference_sync=False):
        calls.append((trade_date, force_reference_sync))
        return {"ok": True, "runId": "run-new", "asOfDate": trade_date.isoformat()}

    monkeypatch.setattr(refresh_service, "refresh_sector_rotation_v3_snapshot", refresh)

    result = refresh_service.refresh_sector_rotation_v3_if_stale(
        date(2026, 7, 22),
        force_reference_sync=True,
    )

    assert calls == [(date(2026, 7, 22), True)]
    assert result["skipped"] is False
    assert result["asOfDate"] == "2026-07-22"
