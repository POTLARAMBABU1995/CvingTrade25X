from pathlib import Path
import sys
import types
from datetime import datetime

from flask import Flask


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

db_pool_stub = types.ModuleType("db_pool")
db_pool_stub.pool = None
db_pool_stub.fetchall_dict = lambda _cur: []
sys.modules["db_pool"] = db_pool_stub

import routes.asura_v3 as asura_v3_route
import services.asura_v3_service as asura_v3_service


def test_latest_signals_route_forwards_query_params(monkeypatch):
    captured: dict[str, object] = {}

    def _fake_latest_signals(**kwargs):
        captured.update(kwargs)
        return {"items": [{"symbol": "TDPOWERSYS"}], "limit": kwargs["limit"], "offset": kwargs["offset"], "total": 1}

    monkeypatch.setattr(asura_v3_route, "fetch_asura_v3_latest_signals", _fake_latest_signals)

    app = Flask(__name__)
    app.register_blueprint(asura_v3_route.bp)
    response = app.test_client().get(
        "/api/strategy/asura-v3/latest-signals"
        "?q=tdpow"
        "&rating=PREMIUM"
        "&grade=A"
        "&limit=25"
        "&offset=0"
        "&sort_by=SIGNAL_DATE"
        "&sort_dir=DESC"
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["status"] == "success"
    assert payload["total"] == 1
    assert payload["items"][0]["symbol"] == "TDPOWERSYS"
    assert captured == {
        "q": "tdpow",
        "rating": "PREMIUM",
        "grade": "A",
        "limit": 25,
        "offset": 0,
        "sort_by": "SIGNAL_DATE",
        "sort_dir": "DESC",
    }


def test_latest_signals_route_rejects_invalid_sort_column():
    app = Flask(__name__)
    app.register_blueprint(asura_v3_route.bp)

    response = app.test_client().get("/api/strategy/asura-v3/latest-signals?sort_by=INVALID_SORT_KEY")
    payload = response.get_json()

    assert response.status_code == 400
    assert payload["status"] == "error"
    assert payload["message"] == "Invalid request parameter: sort_by"


def test_yearly_summary_normalizes_oracle_date_signal_year():
    rows = asura_v3_service._normalize_yearly_summary_rows(
        [
            {"SIGNAL_YEAR": datetime(2026, 1, 1), "TOTAL_TRADES": 14},
            {"SIGNAL_YEAR": "2025-01-01T00:00:00", "TOTAL_TRADES": 61},
            {"SIGNAL_YEAR": 2024, "TOTAL_TRADES": 198},
        ]
    )

    assert [row["signalYear"] for row in rows] == [2026, 2025, 2024]
    assert rows[0]["totalTrades"] == 14


def test_dashboard_summary_route_returns_safe_error_payload(monkeypatch):
    monkeypatch.setattr(
        asura_v3_route,
        "fetch_asura_v3_dashboard_summary",
        lambda: (_ for _ in ()).throw(RuntimeError("oracle unavailable")),
    )

    app = Flask(__name__)
    app.register_blueprint(asura_v3_route.bp)

    response = app.test_client().get("/api/strategy/asura-v3/dashboard-summary")
    payload = response.get_json()

    assert response.status_code == 500
    assert payload == {
        "message": "Failed to load Asura V3 dashboard summary.",
        "request_id": "",
        "status": "error",
    }
