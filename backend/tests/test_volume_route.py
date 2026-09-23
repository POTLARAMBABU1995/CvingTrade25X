from pathlib import Path
import sys

from flask import Flask


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import routes.volume as volume_route


def _valid_payload(symbol: str = "ABC"):
    return {
        "rows": [{"symbol": symbol, "volumeRatio": 4.2}],
        "count": 1,
        "cachedAt": "2026-04-23T00:00:00Z",
        "meta": {
            "cutoffMonths": volume_route.VOLUME_MONTHS,
            "startDate": "2025-10-01",
            "endDate": "2026-04-23",
        },
    }


class _DummyCache:
    def __init__(self, payload=None):
        self.payload = payload

    def get(self, key):
        if key != "volume":
            return None
        return self.payload

    def clear(self):
        self.payload = None


def _build_client():
    app = Flask(__name__)
    app.register_blueprint(volume_route.bp)
    return app.test_client()


def test_api_volume_returns_cached_payload_without_refresh(monkeypatch):
    monkeypatch.setattr(volume_route, "_cache", _DummyCache(_valid_payload("CACHED")))
    client = _build_client()

    response = client.get("/api/volume")
    assert response.status_code == 200
    payload = response.get_json()

    assert payload["cached"] is True
    assert payload.get("refreshing") is not True
    assert payload["rows"][0]["symbol"] == "CACHED"


def test_api_volume_refresh_uses_cached_payload_and_schedules_background_refresh(monkeypatch):
    refresh_calls = {"count": 0}

    monkeypatch.setattr(volume_route, "_cache", _DummyCache(_valid_payload("CACHED")))
    monkeypatch.setattr(
        volume_route,
        "background_refresh",
        lambda *_args, **_kwargs: refresh_calls.__setitem__("count", refresh_calls["count"] + 1),
    )
    client = _build_client()

    response = client.get("/api/volume?refresh=1")
    assert response.status_code == 200
    payload = response.get_json()

    assert payload["cached"] is True
    assert payload["refreshing"] is True
    assert payload["rows"][0]["symbol"] == "CACHED"
    assert refresh_calls["count"] == 1


def test_api_volume_snapshot_response_is_marked_stale_without_client_retry(monkeypatch):
    refresh_calls = {"count": 0}

    monkeypatch.setattr(volume_route, "_cache", _DummyCache(None))
    monkeypatch.setattr(volume_route, "load_json_snapshot", lambda _path: _valid_payload("SNAPSHOT"))
    monkeypatch.setattr(
        volume_route,
        "background_refresh",
        lambda *_args, **_kwargs: refresh_calls.__setitem__("count", refresh_calls["count"] + 1),
    )
    client = _build_client()

    response = client.get("/api/volume")
    assert response.status_code == 200
    payload = response.get_json()

    assert payload["cached"] is True
    assert payload.get("refreshing") is not True
    assert payload["stale"] is True
    assert payload["rows"][0]["symbol"] == "SNAPSHOT"
    assert refresh_calls["count"] == 1


def test_api_volume_cold_start_returns_placeholder_and_background_refresh(monkeypatch):
    refresh_calls = {"count": 0}

    monkeypatch.setattr(volume_route, "_cache", _DummyCache(None))
    monkeypatch.setattr(volume_route, "load_json_snapshot", lambda _path: None)
    monkeypatch.setattr(
        volume_route,
        "background_refresh",
        lambda *_args, **_kwargs: refresh_calls.__setitem__("count", refresh_calls["count"] + 1),
    )
    client = _build_client()

    response = client.get("/api/volume")
    assert response.status_code == 200
    payload = response.get_json()

    assert payload["cached"] is False
    assert payload["refreshing"] is True
    assert payload["stale"] is True
    assert payload["rows"] == []
    assert refresh_calls["count"] == 1
