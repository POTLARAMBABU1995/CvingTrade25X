from pathlib import Path
import sys
import types

from flask import Flask


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

sys.modules.setdefault(
    "db_pool",
    types.SimpleNamespace(pool=types.SimpleNamespace(acquire=lambda: None), fetchall_dict=lambda *_args, **_kwargs: []),
)

import routes.chart as chart_route


def test_chart_route_returns_service_payload(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(chart_route.bp)

    def fake_fetch(symbol, timeframe):
        assert symbol == "RELIANCE"
        assert timeframe == "daily"
        return {
            "symbol": "RELIANCE",
            "timeframe": "daily",
            "latest_date": "2026-05-07",
            "total_candles": 1,
            "candles": [{"time": "2026-05-07", "open": 1, "high": 2, "low": 1, "close": 2}],
            "volume": [{"time": "2026-05-07", "value": 100, "color": "rgba(34,197,94,0.45)"}],
        }

    monkeypatch.setattr(chart_route.svc, "fetch_ohlcv_payload", fake_fetch)
    response = app.test_client().get("/api/chart/ohlcv?symbol=RELIANCE&timeframe=daily")

    assert response.status_code == 200
    assert response.get_json()["total_candles"] == 1


def test_chart_route_returns_400_for_invalid_params(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(chart_route.bp)

    def fake_fetch(_symbol, _timeframe):
        raise chart_route.svc.InvalidChartParameter("timeframe must be one of daily, weekly, monthly")

    monkeypatch.setattr(chart_route.svc, "fetch_ohlcv_payload", fake_fetch)
    response = app.test_client().get("/api/chart/ohlcv?symbol=RELIANCE&timeframe=intraday")

    assert response.status_code == 400
    assert "timeframe" in response.get_json()["message"]


def test_chart_watchlist_route_returns_service_payload(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(chart_route.bp)

    def fake_fetch_watchlist():
        return {
            "total_symbols": 2,
            "latest_trade_date": "2026-05-07",
            "rows": [
                {
                    "symbol": "RELIANCE",
                    "last": 1435.2,
                    "change": -1.0,
                    "change_percent": -0.07,
                    "volume": 8123456,
                    "trading_date": "2026-05-07",
                },
            ],
        }

    monkeypatch.setattr(chart_route.svc, "fetch_watchlist_payload", fake_fetch_watchlist)
    response = app.test_client().get("/api/chart/watchlist")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["total_symbols"] == 2
    assert payload["rows"][0]["symbol"] == "RELIANCE"
