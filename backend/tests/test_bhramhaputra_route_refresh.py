from pathlib import Path
import sys

from flask import Flask


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import routes.bhramhaputra as bhramhaputra_route


class DummyCache:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value


def test_refresh_returns_fresh_payload(monkeypatch):
    dummy_cache = DummyCache()
    stale_snapshot = {
        "rows": [{"symbol": "STALE"}],
        "count": 1,
        "generatedAt": "2020-01-01T00:00:00Z",
        "timeframe": "daily",
    }
    fresh_payload = {
        "rows": [{"symbol": "FRESH"}],
        "count": 1,
        "generatedAt": "2026-02-21T00:00:00Z",
        "timeframe": "daily",
        "meta": {
            "cutoffMonths": 24,
            "cutoffDateIso": "2024-02-21",
            "endDate": "2026-02-21",
            "timeframe": "daily",
        },
    }

    save_calls = {"count": 0}
    refresh_calls = {"count": 0}

    monkeypatch.setattr(bhramhaputra_route, "_cache", dummy_cache)
    monkeypatch.setattr(bhramhaputra_route, "load_json_snapshot", lambda _path: stale_snapshot)
    monkeypatch.setattr(bhramhaputra_route, "_build_payload", lambda _tf: fresh_payload)
    monkeypatch.setattr(
        bhramhaputra_route,
        "save_json_snapshot",
        lambda _path, _payload: save_calls.__setitem__("count", save_calls["count"] + 1),
    )
    monkeypatch.setattr(
        bhramhaputra_route,
        "background_refresh",
        lambda *_args, **_kwargs: refresh_calls.__setitem__("count", refresh_calls["count"] + 1),
    )

    app = Flask(__name__)
    app.register_blueprint(bhramhaputra_route.bp)
    client = app.test_client()

    response = client.get("/api/bhramhaputra?refresh=1&tf=daily")
    assert response.status_code == 200

    payload = response.get_json()
    assert payload["rows"][0]["symbol"] == "FRESH"
    assert payload.get("cached") is not True
    assert dummy_cache.store["bhramhaputra:daily"]["rows"][0]["symbol"] == "FRESH"
    assert save_calls["count"] == 1
    assert refresh_calls["count"] == 0


def test_stale_snapshot_returns_without_sync_compute(monkeypatch):
    dummy_cache = DummyCache()
    stale_snapshot = {
        "rows": [{
            "symbol": "STALE",
            "move22dPct": 3.14,
            "ltcDate": "2026-05-04",
            "price": 100,
            "support1": 92,
            "resistance1": 118,
            "supportDisplay": "S1: 92, S2: 88, S3: 84",
            "resistanceDisplay": "R1: 118, R2: 124, R3: 130",
        }],
        "count": 1,
        "generatedAt": "2026-05-04T00:00:00Z",
        "timeframe": "daily",
        "athSource": "NSE_NIFTY500_DAILY_RAW_DATA_DEV",
        "meta": {
            "cutoffAnchor": "latest_trade_date",
            "cutoffDateIso": "2024-05-04",
            "endDate": "2026-05-04",
            "timeframe": "daily",
        },
    }
    refresh_calls = {"count": 0}

    monkeypatch.setattr(bhramhaputra_route, "_cache", dummy_cache)
    monkeypatch.setattr(bhramhaputra_route, "load_json_snapshot", lambda _path: stale_snapshot)
    monkeypatch.setattr(
        bhramhaputra_route,
        "_build_payload",
        lambda _tf: (_ for _ in ()).throw(AssertionError("sync compute must not run for stale snapshot")),
    )
    monkeypatch.setattr(
        bhramhaputra_route,
        "background_refresh",
        lambda *_args, **_kwargs: refresh_calls.__setitem__("count", refresh_calls["count"] + 1),
    )

    app = Flask(__name__)
    app.register_blueprint(bhramhaputra_route.bp)
    client = app.test_client()

    response = client.get("/api/bhramhaputra?tf=daily")
    assert response.status_code == 200

    payload = response.get_json()
    row = payload["rows"][0]
    assert row["symbol"] == "STALE"
    assert row["cutoffDate"] == "2024-05-04"
    assert row["buyPrice"] == 100
    assert row["stopLoss"] == 95
    assert row["target1"] == 110
    assert row["target2"] == 115
    assert row["support"] == 92
    assert row["resistance"] == 118
    assert payload["cached"] is True
    assert payload["refreshing"] is True
    assert payload["stale"] is True
    assert payload["staleReasons"] == ["cutoff_anchor"]
    assert refresh_calls["count"] == 1
    assert dummy_cache.store["bhramhaputra:daily"]["rows"][0]["symbol"] == "STALE"


def test_snapshot_missing_manual_sr_display_backfills_without_sync_compute(monkeypatch):
    dummy_cache = DummyCache()
    stale_snapshot = {
        "rows": [{
            "symbol": "STALE",
            "move22dPct": 3.14,
            "ltcDate": "2026-05-04",
            "price": 100,
            "support1": 92,
            "resistance1": 118,
        }],
        "count": 1,
        "generatedAt": "2026-05-04T00:00:00Z",
        "timeframe": "daily",
        "athSource": "NSE_NIFTY500_DAILY_RAW_DATA_DEV",
        "meta": {
            "cutoffAnchor": "current",
            "cutoffDateIso": "2024-05-04",
            "endDate": "2026-05-04",
            "timeframe": "daily",
        },
    }
    save_calls = {"count": 0}
    refresh_calls = {"count": 0}

    monkeypatch.setattr(bhramhaputra_route, "_cache", dummy_cache)
    monkeypatch.setattr(bhramhaputra_route, "load_json_snapshot", lambda _path: stale_snapshot)
    monkeypatch.setattr(
        bhramhaputra_route,
        "_build_payload",
        lambda _tf: (_ for _ in ()).throw(AssertionError("sync compute must not run for manual SR display repair")),
    )
    monkeypatch.setattr(
        bhramhaputra_route,
        "backfill_manual_sr_display_rows",
        lambda rows, timeframe=None: [{
            **rows[0],
            "supportDisplay": "S1: 92, S2: 88, S3: 84",
            "resistanceDisplay": "R1: 118, R2: 124, R3: 130",
        }],
    )
    monkeypatch.setattr(
        bhramhaputra_route,
        "save_json_snapshot",
        lambda _path, _payload: save_calls.__setitem__("count", save_calls["count"] + 1),
    )
    monkeypatch.setattr(
        bhramhaputra_route,
        "background_refresh",
        lambda *_args, **_kwargs: refresh_calls.__setitem__("count", refresh_calls["count"] + 1),
    )

    app = Flask(__name__)
    app.register_blueprint(bhramhaputra_route.bp)
    client = app.test_client()

    response = client.get("/api/bhramhaputra?tf=daily")
    assert response.status_code == 200

    payload = response.get_json()
    assert payload["rows"][0]["symbol"] == "STALE"
    assert payload["rows"][0]["supportDisplay"] == "S1: 92, S2: 88, S3: 84"
    assert payload["rows"][0]["resistanceDisplay"] == "R1: 118, R2: 124, R3: 130"
    assert payload["cached"] is True
    assert payload["refreshing"] is False
    assert payload["stale"] is False
    assert payload["staleReasons"] == []
    assert save_calls["count"] == 1
    assert refresh_calls["count"] == 0
    assert dummy_cache.store["bhramhaputra:daily"]["rows"][0]["supportDisplay"] == "S1: 92, S2: 88, S3: 84"


def test_cold_load_without_snapshot_returns_warming_payload(monkeypatch):
    dummy_cache = DummyCache()
    refresh_calls = {"count": 0}

    monkeypatch.setattr(bhramhaputra_route, "_cache", dummy_cache)
    monkeypatch.setattr(bhramhaputra_route, "_ASYNC_COLD_WAIT_MS", 0)
    monkeypatch.setattr(bhramhaputra_route, "load_json_snapshot", lambda _path: None)
    monkeypatch.setattr(
        bhramhaputra_route,
        "_build_payload",
        lambda _tf: (_ for _ in ()).throw(AssertionError("sync compute must not run on cold page load")),
    )
    monkeypatch.setattr(
        bhramhaputra_route,
        "background_refresh",
        lambda *_args, **_kwargs: refresh_calls.__setitem__("count", refresh_calls["count"] + 1),
    )

    app = Flask(__name__)
    app.register_blueprint(bhramhaputra_route.bp)
    client = app.test_client()

    response = client.get("/api/bhramhaputra?tf=daily")
    assert response.status_code == 200

    payload = response.get_json()
    assert payload["rows"] == []
    assert payload["cached"] is True
    assert payload["refreshing"] is True
    assert payload["stale"] is True
    assert payload["staleReasons"] == ["cold_start"]
    assert refresh_calls["count"] == 1


def test_payload_normalization_preserves_zero_values():
    payload = bhramhaputra_route.normalize_bhramhaputra_payload_fields({
        "rows": [{
            "symbol": "ZERO",
            "price": 0,
            "support1": 0,
            "resistance1": 0,
        }],
        "meta": {"cutoffDateIso": "2024-05-04"},
    })

    row = payload["rows"][0]
    assert row["cutoffDate"] == "2024-05-04"
    assert row["buyPrice"] == 0
    assert row["stopLoss"] == 0
    assert row["target1"] == 0
    assert row["target2"] == 0
    assert row["support"] == 0
    assert row["resistance"] == 0


def test_last_ltc_date_accepts_get_and_post(monkeypatch):
    monkeypatch.setattr(bhramhaputra_route, "fetch_bhramhaputra_last_ltc_date", lambda: "2026-05-05")

    app = Flask(__name__)
    app.register_blueprint(bhramhaputra_route.bp)
    client = app.test_client()

    for method in ("get", "post"):
        response = getattr(client, method)("/api/bhramhaputra/last-ltc-date")
        assert response.status_code == 200
        assert response.get_json()["maxLtcDate"] == "2026-05-05"


def test_auto_insert_once_inserts_latest_strict_daily_rows(monkeypatch):
    inserted_rows = {}
    notifications = []
    monkeypatch.setattr(bhramhaputra_route, "BHRAMHAPUTRA_AUTO_INSERT_ENABLED", True)
    monkeypatch.setattr(
        bhramhaputra_route,
        "compute_bhramhaputra_payload",
        lambda timeframe="daily": {
            "rows": [
                {"symbol": "ABC", "conditionsMet": "YES", "buyDate": "2026-05-07"},
                {"symbol": "XYZ", "conditionsMet": "NO", "buyDate": "2026-05-07"},
            ]
        },
    )
    monkeypatch.setattr(bhramhaputra_route, "fetch_bhramhaputra_last_ltc_date", lambda: "2026-05-06")

    def fake_insert(rows):
        inserted_rows["rows"] = rows
        return {
            "insertedCount": 1,
            "skippedCount": 0,
            "updatedCount": 0,
            "totalProcessed": len(rows),
            "latestLtcDate": "2026-05-07",
        }

    monkeypatch.setattr(bhramhaputra_route, "insert_bhramhaputra_rows", fake_insert)
    monkeypatch.setattr(
        bhramhaputra_route,
        "publish_notification",
        lambda **kwargs: notifications.append(kwargs) or kwargs,
    )

    result = bhramhaputra_route._auto_insert_once(reason="test")

    assert result["status"] == "ok"
    assert result["insertedCount"] == 1
    assert inserted_rows["rows"] == [{"symbol": "ABC", "conditionsMet": "YES", "buyDate": "2026-05-07"}]
    assert notifications[0]["source"] == "bhramhaputra_auto_insert"
    assert notifications[0]["metadata"]["ltcDate"] == "2026-05-07"


def test_auto_insert_once_reports_up_to_date_without_insert(monkeypatch):
    notifications = []
    monkeypatch.setattr(bhramhaputra_route, "BHRAMHAPUTRA_AUTO_INSERT_ENABLED", True)
    monkeypatch.setattr(
        bhramhaputra_route,
        "compute_bhramhaputra_payload",
        lambda timeframe="daily": {
            "rows": [
                {"symbol": "ABC", "conditionsMet": "YES", "buyDate": "2026-05-07"},
            ]
        },
    )
    monkeypatch.setattr(bhramhaputra_route, "fetch_bhramhaputra_last_ltc_date", lambda: "2026-05-07")
    monkeypatch.setattr(
        bhramhaputra_route,
        "insert_bhramhaputra_rows",
        lambda _rows: (_ for _ in ()).throw(AssertionError("insert should not run when already up to date")),
    )
    monkeypatch.setattr(
        bhramhaputra_route,
        "publish_notification",
        lambda **kwargs: notifications.append(kwargs) or kwargs,
    )

    result = bhramhaputra_route._auto_insert_once(reason="test")

    assert result["status"] == "ok"
    assert result["upToDate"] is True
    assert result["insertedCount"] == 0
    assert result["skippedCount"] == 1
    assert notifications[0]["message"] == "Bhramhaputra auto insertion already up to date for 2026-05-07."
