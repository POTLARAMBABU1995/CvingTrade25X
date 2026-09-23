from __future__ import annotations

from datetime import date

from routes import marketdata as marketdata_route


def test_post_merge_v3_refresh_targets_latest_dev_date(monkeypatch):
    calls: list[tuple[date, bool]] = []
    monkeypatch.setattr(marketdata_route, "get_latest_ltc_date_fast", lambda: date(2026, 7, 22))
    monkeypatch.setattr(
        marketdata_route,
        "refresh_sector_rotation_v3_if_stale",
        lambda trade_date, force_reference_sync=False: calls.append(
            (trade_date, force_reference_sync)
        )
        or {
            "ok": True,
            "skipped": False,
            "runId": "run-new",
            "asOfDate": trade_date.isoformat(),
        },
    )

    result = marketdata_route._refresh_sector_rotation_v3_after_merge(reason="latest_available")

    assert calls == [(date(2026, 7, 22), True)]
    assert result["asOfDate"] == "2026-07-22"


def test_post_merge_v3_refresh_skips_without_dev_data(monkeypatch):
    monkeypatch.setattr(marketdata_route, "get_latest_ltc_date_fast", lambda: None)
    monkeypatch.setattr(
        marketdata_route,
        "refresh_sector_rotation_v3_if_stale",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not refresh")),
    )

    result = marketdata_route._refresh_sector_rotation_v3_after_merge(reason="latest_available")

    assert result == {"ok": True, "skipped": True, "reason": "NO_DEV_DATE"}
