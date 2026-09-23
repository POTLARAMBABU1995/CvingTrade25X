from pathlib import Path
import sys
import types

from flask import Flask


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

db_pool_stub = types.ModuleType("db_pool")
db_pool_stub.pool = types.SimpleNamespace(acquire=lambda: None)
db_pool_stub.fetchall_dict = lambda *args, **kwargs: []
sys.modules["db_pool"] = db_pool_stub

import routes.historical_data as historical_data_route


def _client():
    app = Flask(__name__)
    app.register_blueprint(historical_data_route.bp)
    return app.test_client()


def test_tables_endpoint_returns_allowed_tables(monkeypatch):
    client = _client()
    monkeypatch.setattr(historical_data_route.svc, "DEFAULT_TABLE", "NSE_NIFTY500_DAILY_RAW_DATA_DEV")
    monkeypatch.setattr(
        historical_data_route.svc,
        "list_allowed_tables",
        lambda: ["NSE_NIFTY500_DAILY_RAW_DATA_DEV", "NSE_NIFTY500_DAILY_RAW_DATA_ORACLE"],
    )

    response = client.get("/api/historical-data/tables")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["default_table"] == "NSE_NIFTY500_DAILY_RAW_DATA_DEV"
    assert payload["tables"] == ["NSE_NIFTY500_DAILY_RAW_DATA_DEV", "NSE_NIFTY500_DAILY_RAW_DATA_ORACLE"]


def test_summary_endpoint_forwards_query_params(monkeypatch):
    client = _client()
    captured = {}

    def fake_summary(params):
        captured["params"] = dict(params)
        return {"ok": True, "total_count": 1, "data": [{"symbol": "ABC"}]}

    monkeypatch.setattr(historical_data_route.svc, "get_summary", fake_summary)

    response = client.get("/api/historical-data/summary?table_name=NSE_NIFTY500_DAILY_RAW_DATA_DEV&page=2&page_size=100")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["total_count"] == 1
    assert captured["params"]["table_name"] == "NSE_NIFTY500_DAILY_RAW_DATA_DEV"
    assert captured["params"]["page"] == "2"
    assert captured["params"]["page_size"] == "100"


def test_summary_endpoint_returns_400_for_validation_error(monkeypatch):
    client = _client()
    monkeypatch.setattr(historical_data_route.svc, "get_summary", lambda _params: (_ for _ in ()).throw(ValueError("Invalid table selected")))

    response = client.get("/api/historical-data/summary?table_name=BAD_TABLE")

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["detail"] == "Invalid table selected"


def test_symbol_endpoint_forwards_params(monkeypatch):
    client = _client()
    captured = {}

    def fake_symbol(symbol, params):
        captured["symbol"] = symbol
        captured["params"] = dict(params)
        return {"ok": True, "symbol": symbol, "data": []}

    monkeypatch.setattr(historical_data_route.svc, "get_symbol_rows", fake_symbol)

    response = client.get("/api/historical-data/symbol/RELIANCE?table_name=NSE_NIFTY500_DAILY_RAW_DATA_DEV&sort_order=ASC")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert captured["symbol"] == "RELIANCE"
    assert captured["params"]["sort_order"] == "ASC"


def test_symbol_csv_endpoint_returns_attachment_with_exact_headers(monkeypatch):
    client = _client()
    captured = {}

    def fake_symbol_csv(symbol, params):
        captured["symbol"] = symbol
        captured["params"] = dict(params)
        return (
            "RELIANCE_historical_data.csv",
            "s.no,symbol,trade_date,open,high,low,close,volume\r\n"
            "1,RELIANCE,2026-09-16,100,110,95,108,50000\r\n",
        )

    monkeypatch.setattr(historical_data_route.svc, "get_symbol_csv", fake_symbol_csv)

    response = client.get(
        "/api/historical-data/symbol/RELIANCE/csv"
        "?table_name=NSE_NIFTY500_DAILY_RAW_DATA_DEV"
    )

    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert response.headers["Content-Disposition"] == 'attachment; filename="RELIANCE_historical_data.csv"'
    assert response.get_data(as_text=True).splitlines()[0] == "s.no,symbol,trade_date,open,high,low,close,volume"
    assert captured["symbol"] == "RELIANCE"
    assert captured["params"]["table_name"] == "NSE_NIFTY500_DAILY_RAW_DATA_DEV"


def test_symbol_csv_endpoint_returns_400_for_validation_error(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        historical_data_route.svc,
        "get_symbol_csv",
        lambda _symbol, _params: (_ for _ in ()).throw(ValueError("Invalid table selected")),
    )

    response = client.get("/api/historical-data/symbol/ABC/csv?table_name=BAD_TABLE")

    assert response.status_code == 400
    assert response.get_json()["detail"] == "Invalid table selected"


def test_symbol_download_endpoint_returns_three_file_zip_attachment(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        historical_data_route.svc,
        "get_symbol_export_bundle",
        lambda symbol, _params: (f"{symbol}_historical_data.zip", b"PK-test-archive"),
    )

    response = client.get(
        "/api/historical-data/symbol/RELIANCE/download"
        "?table_name=NSE_NIFTY500_DAILY_RAW_DATA_DEV"
    )

    assert response.status_code == 200
    assert response.mimetype == "application/zip"
    assert response.headers["Content-Disposition"] == (
        'attachment; filename="RELIANCE_historical_data.zip"'
    )
    assert response.get_data() == b"PK-test-archive"


def test_delete_symbols_endpoint_forwards_payload(monkeypatch):
    client = _client()
    captured = {}

    def fake_delete(payload):
        captured["payload"] = payload
        return {
            "ok": True,
            "success": True,
            "deleted_symbols": 2,
            "dev_deleted_rows": 7,
            "oracle_deleted_rows": 5,
            "deleted_rows": 12,
        }

    monkeypatch.setattr(historical_data_route.svc, "delete_symbols", fake_delete)

    response = client.post(
        "/api/historical-data/delete-symbols",
        json={
            "table_name": "NSE_NIFTY500_DAILY_RAW_DATA_DEV",
            "symbols": ["NAUKRI", "BSE"],
            "confirm_text": "DELETE",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["success"] is True
    assert payload["dev_deleted_rows"] == 7
    assert payload["oracle_deleted_rows"] == 5
    assert payload["deleted_rows"] == 12
    assert captured["payload"]["symbols"] == ["NAUKRI", "BSE"]


def test_delete_rows_endpoint_handles_validation_error(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        historical_data_route.svc,
        "delete_rows",
        lambda _payload: (_ for _ in ()).throw(ValueError("Delete confirmation failed")),
    )

    response = client.post(
        "/api/historical-data/delete-rows",
        json={
            "table_name": "NSE_NIFTY500_DAILY_RAW_DATA_DEV",
            "symbol": "NAUKRI",
            "trading_dates": ["2025-04-01"],
            "confirm_text": "NO",
        },
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["detail"] == "Delete confirmation failed"
