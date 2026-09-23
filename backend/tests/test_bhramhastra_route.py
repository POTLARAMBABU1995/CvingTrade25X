from pathlib import Path
import sys

from flask import Flask


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import routes.bhramhastra as bhramhastra_route


class DummyCache:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value


def test_bhramhastra_marketcap_enrichment_uses_latest_per_symbol_fallback(monkeypatch):
    captured = {}

    def fake_enrich(payload, **kwargs):
        captured.update(kwargs)
        return {
            **payload,
            "rows": [
                {
                    **payload["rows"][0],
                    "INDEX": "SMALL",
                    "MCAP": 4970.33,
                    "MCAP_RANK": 704,
                }
            ],
        }

    monkeypatch.setattr(bhramhastra_route.nse_mcap_svc, "enrich_payload_marketcap_index", fake_enrich)

    payload = bhramhastra_route._enrich_bhramhastra_payload({"rows": [{"symbol": "TVSSCS"}]})

    assert captured["row_keys"] == ("rows",)
    assert captured["allow_stale_per_symbol"] is True
    assert payload["rows"][0]["MCAP_RANK"] == 704


def test_bhramhastra_cached_payload_skips_marketcap_lookup_when_already_enriched(monkeypatch):
    monkeypatch.setattr(
        bhramhastra_route.nse_mcap_svc,
        "enrich_payload_marketcap_index",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("cached enriched payload must not hit market-cap lookup")),
    )

    payload = bhramhastra_route._enrich_bhramhastra_payload({
        "rows": [{
            "symbol": "ABC",
            "INDEX": "LARGE",
            "MCAP": 12345.67,
            "MCAP_RANK": 42,
        }]
    })

    assert payload["rows"][0]["MCAP_RANK"] == 42


def test_snapshot_missing_display_fields_is_marked_stale(monkeypatch):
    monkeypatch.setattr(bhramhastra_route, "fetch_bhramhastra_source_max_ltc_date", lambda: "2026-05-15")

    payload = {
        "rows": [{"symbol": "ABC", "ltcDate": "2026-05-15", "ema50": 101.5}],
        "athSource": "NSE_NIFTY500_DAILY_RAW_DATA_DEV",
    }

    assert "display_fields" in bhramhastra_route._snapshot_stale_reasons(payload)


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
        "generatedAt": "2026-03-24T00:00:00Z",
        "timeframe": "daily",
        "cutoffDateIso": "2025-03-24",
    }

    save_calls = {"count": 0}
    refresh_calls = {"count": 0}

    monkeypatch.setattr(bhramhastra_route, "_cache", dummy_cache)
    monkeypatch.setattr(bhramhastra_route, "load_json_snapshot", lambda _path: None)
    monkeypatch.setattr(bhramhastra_route, "_build_payload", lambda _tf: fresh_payload)
    monkeypatch.setattr(
        bhramhastra_route,
        "save_json_snapshot",
        lambda _path, _payload: save_calls.__setitem__("count", save_calls["count"] + 1),
    )
    monkeypatch.setattr(
        bhramhastra_route,
        "background_refresh",
        lambda *_args, **_kwargs: refresh_calls.__setitem__("count", refresh_calls["count"] + 1),
    )

    app = Flask(__name__)
    app.register_blueprint(bhramhastra_route.bp)
    client = app.test_client()

    response = client.get("/api/bhramhastra?refresh=1&tf=daily")
    assert response.status_code == 200

    payload = response.get_json()
    assert payload["rows"][0]["symbol"] == "FRESH"
    assert payload.get("cached") is not True
    assert dummy_cache.store["bhramhastra:daily"]["rows"][0]["symbol"] == "FRESH"
    assert save_calls["count"] == 1
    assert refresh_calls["count"] == 0


def test_stale_snapshot_returns_without_sync_compute(monkeypatch):
    dummy_cache = DummyCache()
    stale_snapshot = {
        "rows": [{
            "symbol": "STALE",
            "ltcDate": "2026-05-04",
            "ema20": 100,
            "ema50": 101,
            "ema100": 102,
            "ema200": 103,
            "adx14": 25,
            "trendDirection": "UPTREND",
            "gap": -5.0,
            "setupType": "EMA50 + RSI50-55 + MACD + Volume",
        }],
        "count": 1,
        "generatedAt": "2026-05-04T00:00:00Z",
        "timeframe": "daily",
        "athSource": "NSE_NIFTY500_DAILY_RAW_DATA_DEV",
    }
    refresh_calls = {"count": 0}

    monkeypatch.setattr(bhramhastra_route, "_cache", dummy_cache)
    monkeypatch.setattr(bhramhastra_route, "load_json_snapshot", lambda _path: stale_snapshot)
    monkeypatch.setattr(bhramhastra_route, "fetch_bhramhastra_source_max_ltc_date", lambda: "2026-05-05")
    monkeypatch.setattr(
        bhramhastra_route,
        "_build_payload",
        lambda _tf: (_ for _ in ()).throw(AssertionError("sync compute must not run for stale snapshot")),
    )
    monkeypatch.setattr(
        bhramhastra_route,
        "background_refresh",
        lambda *_args, **_kwargs: refresh_calls.__setitem__("count", refresh_calls["count"] + 1),
    )

    app = Flask(__name__)
    app.register_blueprint(bhramhastra_route.bp)
    client = app.test_client()

    response = client.get("/api/bhramhastra?tf=daily")
    assert response.status_code == 200

    payload = response.get_json()
    assert payload["rows"][0]["symbol"] == "STALE"
    assert payload["cached"] is True
    assert payload["refreshing"] is True
    assert payload["stale"] is True
    assert payload["staleReasons"] == ["ltc_date"]
    assert refresh_calls["count"] == 1


def test_snapshot_missing_display_fields_is_repaired_before_response(monkeypatch):
    dummy_cache = DummyCache()
    snapshot = {
        "rows": [{
            "symbol": "ABC",
            "ltcDate": "2026-05-15",
            "ema50": 101.5,
            "ath": 120,
            "entryPrice": 100,
        }],
        "count": 1,
        "generatedAt": "2026-05-15T00:00:00Z",
        "timeframe": "daily",
        "athSource": "NSE_NIFTY500_DAILY_RAW_DATA_DEV",
    }
    save_calls = {"count": 0}
    refresh_calls = {"count": 0}

    def fake_repair(payload, timeframe=None):
        payload["rows"][0].update({
            "ema20": 99.5,
            "ema100": 95.5,
            "ema200": 90.5,
            "adx14": 27.0,
            "trendDirection": "UPTREND",
            "gap": -16.67,
            "gapSort": -16.6667,
            "setupType": "EMA50 + RSI50-55 + MACD + Volume",
        })
        return payload, 1

    monkeypatch.setattr(bhramhastra_route, "_cache", dummy_cache)
    monkeypatch.setattr(bhramhastra_route, "load_json_snapshot", lambda _path: snapshot)
    monkeypatch.setattr(bhramhastra_route, "fetch_bhramhastra_source_max_ltc_date", lambda: "2026-05-15")
    monkeypatch.setattr(bhramhastra_route, "repair_bhramhastra_display_fields", fake_repair)
    monkeypatch.setattr(
        bhramhastra_route,
        "save_json_snapshot",
        lambda _path, _payload: save_calls.__setitem__("count", save_calls["count"] + 1),
    )
    monkeypatch.setattr(
        bhramhastra_route,
        "background_refresh",
        lambda *_args, **_kwargs: refresh_calls.__setitem__("count", refresh_calls["count"] + 1),
    )

    app = Flask(__name__)
    app.register_blueprint(bhramhastra_route.bp)
    client = app.test_client()

    response = client.get("/api/bhramhastra?tf=daily")
    assert response.status_code == 200

    payload = response.get_json()
    row = payload["rows"][0]
    assert row["ema20"] == 99.5
    assert row["ema100"] == 95.5
    assert row["ema200"] == 90.5
    assert row["adx14"] == 27.0
    assert row["trendDirection"] == "UPTREND"
    assert row["gap"] == -16.67
    assert payload["stale"] is False
    assert payload["refreshing"] is False
    assert payload["staleReasons"] == []
    assert save_calls["count"] == 1
    assert refresh_calls["count"] == 0


def test_cold_start_returns_warming_payload_and_schedules_refresh(monkeypatch):
    dummy_cache = DummyCache()
    refresh_calls = {"count": 0}

    monkeypatch.setattr(bhramhastra_route, "_cache", dummy_cache)
    monkeypatch.setattr(bhramhastra_route, "load_json_snapshot", lambda _path: None)
    monkeypatch.setattr(bhramhastra_route, "_wait_for_cached_payload", lambda _key, _wait_ms: None)
    monkeypatch.setattr(
        bhramhastra_route,
        "_build_payload",
        lambda _tf: (_ for _ in ()).throw(AssertionError("sync compute must not run for cold start without refresh")),
    )
    monkeypatch.setattr(
        bhramhastra_route,
        "background_refresh",
        lambda *_args, **_kwargs: refresh_calls.__setitem__("count", refresh_calls["count"] + 1),
    )

    app = Flask(__name__)
    app.register_blueprint(bhramhastra_route.bp)
    client = app.test_client()

    response = client.get("/api/bhramhastra?tf=daily")
    assert response.status_code == 200

    payload = response.get_json()
    assert payload["rows"] == []
    assert payload["count"] == 0
    assert payload["cached"] is True
    assert payload["refreshing"] is True
    assert payload["stale"] is True
    assert payload["staleReasons"] == ["cold_start"]
    assert refresh_calls["count"] == 1


def test_cold_start_returns_warmed_payload_when_background_finishes_fast(monkeypatch):
    dummy_cache = DummyCache()
    refresh_calls = {"count": 0}
    warmed_payload = {
        "rows": [{"symbol": "WARM"}],
        "count": 1,
        "generatedAt": "2026-05-11T00:00:00Z",
        "timeframe": "daily",
    }

    monkeypatch.setattr(bhramhastra_route, "_cache", dummy_cache)
    monkeypatch.setattr(bhramhastra_route, "load_json_snapshot", lambda _path: None)
    monkeypatch.setattr(bhramhastra_route, "_wait_for_cached_payload", lambda _key, _wait_ms: warmed_payload)
    monkeypatch.setattr(
        bhramhastra_route,
        "_build_payload",
        lambda _tf: (_ for _ in ()).throw(AssertionError("sync compute must not run for async warmed response")),
    )
    monkeypatch.setattr(
        bhramhastra_route,
        "background_refresh",
        lambda *_args, **_kwargs: refresh_calls.__setitem__("count", refresh_calls["count"] + 1),
    )

    app = Flask(__name__)
    app.register_blueprint(bhramhastra_route.bp)
    client = app.test_client()

    response = client.get("/api/bhramhastra?tf=daily")
    assert response.status_code == 200

    payload = response.get_json()
    assert payload["rows"][0]["symbol"] == "WARM"
    assert payload["cached"] is True
    assert payload["refreshing"] is False
    assert payload["stale"] is False
    assert payload["staleReasons"] == []
    assert refresh_calls["count"] == 1



def test_last_ltc_date_route_degrades_when_db_lookup_fails(monkeypatch):
    monkeypatch.setattr(
        bhramhastra_route,
        "fetch_bhramhastra_max_ltc_date",
        lambda: (_ for _ in ()).throw(RuntimeError("db unavailable")),
    )

    app = Flask(__name__)
    app.register_blueprint(bhramhastra_route.bp)
    client = app.test_client()

    response = client.get("/api/bhramhastra/last-ltc-date")
    assert response.status_code == 200

    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["maxLtcDate"] is None
    assert payload["message"] == "db unavailable"
def test_insert_route_triggers_agent_when_rows_are_inserted(monkeypatch):
    monkeypatch.setattr(
        bhramhastra_route,
        "compute_bhramhastra_scan",
        lambda timeframe='daily': ({"rows": []}, {"ABC": {"tradeDate": "2026-03-24", "high": 120, "low": 90}}),
    )
    monkeypatch.setattr(
        bhramhastra_route,
        "upsert_bhramhastra_rows",
        lambda rows, latest_snapshot: {
            "inserted": 2,
            "skipped": 1,
            "updated": 0,
            "latestLtcDate": "2026-03-24",
        },
    )
    monkeypatch.setattr(
        bhramhastra_route,
        "start_strategy_agent_execution",
        lambda strategy_name, run_source='manual': {
            "job": {"jobId": "job-bhram", "strategy": strategy_name, "status": "QUEUED"},
            "alreadyRunning": False,
        },
    )

    app = Flask(__name__)
    app.register_blueprint(bhramhastra_route.bp)
    client = app.test_client()

    response = client.post(
        "/api/bhramhastra/insert",
        json={
            "rows": [
                {"symbol": "ABC", "ltcDate": "2026-03-24", "entryPrice": 100, "atr": 5, "rsi": 52, "macd": 0.4},
                {"symbol": "XYZ", "ltcDate": "2026-03-24", "entryPrice": 200, "atr": 8, "rsi": 54, "macd": 0.8},
            ]
        },
    )
    assert response.status_code == 200

    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["insertedCount"] == 2
    assert payload["skippedCount"] == 1
    assert payload["latestLtcDate"] == "2026-03-24"
    assert payload["agent"]["job"]["strategy"] == "bhramhastra"


def test_auto_insert_once_reports_up_to_date_with_success_notification(monkeypatch):
    notifications = []
    monkeypatch.setattr(bhramhastra_route, "BHRAMHASTRA_AUTO_INSERT_ENABLED", True)
    monkeypatch.setattr(
        bhramhastra_route,
        "compute_bhramhastra_scan",
        lambda timeframe="daily": (
            {"rows": [{"symbol": "ABC", "ltcDate": "2026-05-07"}]},
            {"ABC": {"tradeDate": "2026-05-07"}},
        ),
    )
    monkeypatch.setattr(bhramhastra_route, "fetch_bhramhastra_max_ltc_date", lambda: "2026-05-07")
    monkeypatch.setattr(
        bhramhastra_route,
        "upsert_bhramhastra_rows",
        lambda _rows, _snapshot: (_ for _ in ()).throw(AssertionError("upsert should not run when already up to date")),
    )
    monkeypatch.setattr(
        bhramhastra_route,
        "publish_notification",
        lambda **kwargs: notifications.append(kwargs) or kwargs,
    )

    result = bhramhastra_route._auto_insert_once(reason="test")

    assert result["status"] == "ok"
    assert result["upToDate"] is True
    assert result["insertedCount"] == 0
    assert result["skippedCount"] == 1
    assert notifications[0]["source"] == "bhramhastra_auto_insert"
    assert notifications[0]["metadata"]["ltcDate"] == "2026-05-07"


