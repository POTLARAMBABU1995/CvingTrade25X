from pathlib import Path
import sys
import types

from flask import Flask


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

db_pool_stub = types.ModuleType("db_pool")
db_pool_stub.pool = None
db_pool_stub.fetchall_dict = lambda _cur: []
sys.modules["db_pool"] = db_pool_stub

import routes.prudvi_strategy as prudvi_route


def test_route_returns_prudvi_payload_with_market_cap(monkeypatch):
    def _payload(refresh=False):
        assert refresh is True
        return {
            "data": [
                {
                    "S_NO": 1,
                    "SYMBOL": "RELIANCE",
                    "ATH": 3025.5,
                    "PRICE": 2948.65,
                    "GAP": -2.54,
                    "LTC_DATE": "2026-05-14",
                    "SUPPORT": "2850, 2780",
                    "RESISTANCE": "3025, 3150",
                    "BULLISH_CANDLE": "Y",
                    "EMA_GT_20": "Y",
                    "EMA_GT_50": "Y",
                    "RSI_GT_50": "Y",
                    "ADX_GT_25": "Y",
                    "MACD_GT_0": "Y",
                    "VOLUME_GT_20": "Y",
                    "DELIVERY_GT_60": "Y",
                    "TREND": "UPTREND",
                    "TREND_SCORE": 100,
                }
            ],
            "status": "success",
            "meta": {"rows": 1, "tradingDate": "2026-05-14"},
        }

    monkeypatch.setattr(prudvi_route, "fetch_prudvi_strategy_scan", _payload)
    monkeypatch.setattr(
        prudvi_route.nse_mcap_svc,
        "enrich_payload_marketcap_index",
        lambda payload, row_keys=("data",), symbol_keys=("SYMBOL", "symbol"): {
            **payload,
            "data": [{**payload["data"][0], "INDEX": "LARGE", "MCAP": 1987654.23, "MCAP_RANK": 1}],
        },
    )

    app = Flask(__name__)
    app.register_blueprint(prudvi_route.bp)
    response = app.test_client().get("/api/strategy/prudvi?refresh=1")
    payload = response.get_json()

    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/json")
    assert payload["status"] == "success"
    assert payload["data"][0]["S_NO"] == 1
    assert payload["data"][0]["ATH"] == 3025.5
    assert payload["data"][0]["PRICE"] == 2948.65
    assert payload["data"][0]["GAP"] == -2.54
    assert payload["data"][0]["LTC_DATE"] == "2026-05-14"
    assert payload["data"][0]["SUPPORT"] == "2850, 2780"
    assert payload["data"][0]["BULLISH_CANDLE"] == "Y"
    assert payload["data"][0]["INDEX"] == "LARGE"
    assert payload["data"][0]["MCAP"] == 1987654.23
    assert payload["data"][0]["MCAP_RANK"] == 1


def test_route_returns_safe_json_error(monkeypatch):
    monkeypatch.setattr(
        prudvi_route,
        "fetch_prudvi_strategy_scan",
        lambda refresh=False: (_ for _ in ()).throw(RuntimeError("oracle failed")),
    )

    app = Flask(__name__)
    app.register_blueprint(prudvi_route.bp)
    response = app.test_client().get("/api/strategy/prudvi")
    payload = response.get_json()

    assert response.status_code == 500
    assert response.headers["Content-Type"].startswith("application/json")
    assert payload == {
        "data": [],
        "error": "Failed to load Prudvi strategy scanner.",
        "message": "Failed to load Prudvi strategy scanner.",
        "request_id": "",
        "status": "error",
    }


def test_route_filters_rows_when_required_flags_are_not_all_y(monkeypatch):
    monkeypatch.setattr(
        prudvi_route,
        "fetch_prudvi_strategy_scan",
        lambda refresh=False: {
            "data": [
                {
                    "SYMBOL": "PASS",
                    "EMA_GT_20": "Y",
                    "EMA_GT_50": "Y",
                    "RSI_GT_50": "Y",
                    "ADX_GT_25": "Y",
                    "MACD_GT_0": "Y",
                    "VOLUME_GT_20": "Y",
                },
                {
                    "SYMBOL": "FAIL",
                    "EMA_GT_20": "Y",
                    "EMA_GT_50": "Y",
                    "RSI_GT_50": "N",
                    "ADX_GT_25": "Y",
                    "MACD_GT_0": "Y",
                    "VOLUME_GT_20": "Y",
                },
            ],
            "meta": {"rows": 2, "tradingDate": "2026-05-20"},
            "status": "success",
        },
    )
    monkeypatch.setattr(
        prudvi_route.nse_mcap_svc,
        "enrich_payload_marketcap_index",
        lambda payload, row_keys=("data",), symbol_keys=("SYMBOL", "symbol"): payload,
    )

    app = Flask(__name__)
    app.register_blueprint(prudvi_route.bp)
    response = app.test_client().get("/api/strategy/prudvi")
    payload = response.get_json()

    assert response.status_code == 200
    assert len(payload["data"]) == 1
    assert payload["data"][0]["SYMBOL"] == "PASS"
    assert payload["meta"]["rows"] == 1
