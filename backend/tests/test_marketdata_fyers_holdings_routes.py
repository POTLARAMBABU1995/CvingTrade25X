from pathlib import Path
import sys
import types

from flask import Flask


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

db_pool_stub = types.ModuleType('db_pool')
db_pool_stub.pool = types.SimpleNamespace(acquire=lambda: None)
db_pool_stub.fetchall_dict = lambda *args, **kwargs: []
sys.modules['db_pool'] = db_pool_stub

import routes.marketdata as marketdata_route
import routes.fyers_holdings_debug as fyers_holdings_debug_route


def _client():
    app = Flask(__name__)
    app.register_blueprint(marketdata_route.bp)
    return app.test_client()


def test_fyers_holdings_import_route_forwards_json_payload(monkeypatch):
    client = _client()
    captured = {}

    def fake_import(payload):
        captured['payload'] = payload
        return {'ok': True, 'stats': {'rows': 1}}

    monkeypatch.setattr(marketdata_route.fyers_holdings_svc, 'import_holdings', fake_import)

    response = client.post('/api/marketdata/fyers/holdings/import', json={'csvText': 'a,b', 'filename': 'holdings.csv'})

    assert response.status_code == 200
    assert response.get_json()['stats']['rows'] == 1
    assert captured['payload']['filename'] == 'holdings.csv'


def test_fyers_holdings_list_route_forwards_query_params(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        marketdata_route.fyers_holdings_svc,
        'list_holdings',
        lambda payload: {'ok': True, 'payload': payload, 'holdings': []},
    )

    response = client.get('/api/marketdata/fyers/holdings?clientId=XP24006&q=TANLA')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['payload']['clientId'] == 'XP24006'
    assert payload['payload']['q'] == 'TANLA'


def test_fyers_holdings_list_route_uses_fast_marketcap_enrichment(monkeypatch):
    client = _client()
    captured = {}

    monkeypatch.setattr(
        marketdata_route.fyers_holdings_svc,
        'list_holdings',
        lambda payload: {'ok': True, 'holdings': [{'symbolCode': 'TANLA'}]},
    )

    def fake_enrich(rows, **kwargs):
        captured['rows'] = rows
        captured['kwargs'] = kwargs
        return [{**row, 'INDEX': 'LARGE'} for row in rows]

    monkeypatch.setattr(marketdata_route.nse_mcap_svc, 'enrich_rows_with_marketcap_index', fake_enrich)

    response = client.get('/api/marketdata/fyers/holdings')

    assert response.status_code == 200
    assert response.get_json()['holdings'][0]['INDEX'] == 'LARGE'
    assert captured['rows'] == [{'symbolCode': 'TANLA'}]
    assert captured['kwargs']['allow_base_table_fallback'] is False


def test_fyers_holdings_summary_and_imports_routes(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        marketdata_route.fyers_holdings_svc,
        'get_holdings_summary',
        lambda payload: {'ok': True, 'summary': {'clientId': payload.get('clientId')}},
    )
    monkeypatch.setattr(
        marketdata_route.fyers_holdings_svc,
        'list_import_runs',
        lambda payload: {'ok': True, 'imports': [{'clientId': payload.get('clientId')}], 'count': 1},
    )

    summary_response = client.get('/api/marketdata/fyers/holdings/summary?clientId=XP24006')
    imports_response = client.get('/api/marketdata/fyers/holdings/imports?clientId=XP24006')

    assert summary_response.status_code == 200
    assert summary_response.get_json()['summary']['clientId'] == 'XP24006'
    assert imports_response.status_code == 200
    assert imports_response.get_json()['imports'][0]['clientId'] == 'XP24006'


def test_fyers_holdings_reconcile_route_forwards_query_params(monkeypatch):
    client = _client()
    captured = {}

    def fake_reconcile(payload):
        captured['payload'] = payload
        return {'ok': True, 'summary': {'totalSymbolsChecked': 1}, 'rows': [{'symbol': 'TANLA'}]}

    monkeypatch.setattr(marketdata_route.fyers_holdings_svc, 'reconcile_holdings', fake_reconcile)

    response = client.get('/api/marketdata/fyers/holdings/reconcile?clientId=XP24006&q=TANLA')

    assert response.status_code == 200
    assert response.get_json()['summary']['totalSymbolsChecked'] == 1
    assert captured['payload']['clientId'] == 'XP24006'
    assert captured['payload']['q'] == 'TANLA'


def test_fyers_debug_reconcile_route_forwards_query_params(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(fyers_holdings_debug_route.bp)
    client = app.test_client()
    captured = {}

    def fake_reconcile(payload):
        captured['payload'] = payload
        return {'ok': True, 'summary': {'mismatchedSymbolsCount': 0}, 'rows': []}

    monkeypatch.setattr(fyers_holdings_debug_route.fyers_holdings_svc, 'reconcile_holdings', fake_reconcile)

    response = client.get('/api/fyers/holdings/reconcile?clientId=XP24006')

    assert response.status_code == 200
    assert response.get_json()['summary']['mismatchedSymbolsCount'] == 0
    assert captured['payload']['clientId'] == 'XP24006'


def test_fyers_holdings_create_update_delete_routes(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        marketdata_route.fyers_holdings_svc,
        'create_holding',
        lambda payload: {'ok': True, 'holding': {'symbol': payload.get('symbol')}},
    )
    monkeypatch.setattr(
        marketdata_route.fyers_holdings_svc,
        'update_holding',
        lambda holding_id, payload: {'ok': True, 'holding': {'holdingId': holding_id, 'quantity': payload.get('quantity')}},
    )
    monkeypatch.setattr(
        marketdata_route.fyers_holdings_svc,
        'delete_holding',
        lambda holding_id: {'ok': True, 'holdingId': holding_id},
    )

    create_response = client.post('/api/marketdata/fyers/holdings', json={'symbol': 'NSE:IOC-EQ'})
    update_response = client.put('/api/marketdata/fyers/holdings/17', json={'quantity': 5})
    delete_response = client.delete('/api/marketdata/fyers/holdings/17')

    assert create_response.status_code == 200
    assert create_response.get_json()['holding']['symbol'] == 'NSE:IOC-EQ'
    assert update_response.status_code == 200
    assert update_response.get_json()['holding']['holdingId'] == 17
    assert delete_response.status_code == 200
    assert delete_response.get_json()['holdingId'] == 17
