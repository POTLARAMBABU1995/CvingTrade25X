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


def _client():
    app = Flask(__name__)
    app.register_blueprint(marketdata_route.bp)
    return app.test_client()


def test_nse_mcap_pipeline_start_uses_background_job(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        marketdata_route.nse_mcap_svc,
        'start_pipeline_job',
        lambda payload: {'ok': True, 'jobId': 'mcap-job', 'status': 'RUNNING', 'request': payload},
    )

    response = client.post('/api/marketdata/nse-mcap/pipeline/start', json={'tradeDate': '2026-03-17'})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['jobId'] == 'mcap-job'
    assert payload['status'] == 'RUNNING'
    assert payload['request']['tradeDate'] == '2026-03-17'


def test_nse_mcap_latest_job_endpoint_forwards_tail(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        marketdata_route.nse_mcap_svc,
        'get_latest_job',
        lambda tail_lines=None: {'ok': True, 'jobId': 'mcap-job', 'tail': tail_lines},
    )

    response = client.get('/api/marketdata/nse-mcap/jobs/latest?tail=77')

    assert response.status_code == 200
    assert response.get_json() == {'ok': True, 'jobId': 'mcap-job', 'tail': 77}


def test_nse_mcap_job_endpoint_forwards_tail(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        marketdata_route.nse_mcap_svc,
        'get_job',
        lambda job_id, tail_lines=None: {'ok': True, 'jobId': job_id, 'tail': tail_lines},
    )

    response = client.get('/api/marketdata/nse-mcap/jobs/mcap-job?tail=44')

    assert response.status_code == 200
    assert response.get_json() == {'ok': True, 'jobId': 'mcap-job', 'tail': 44}


def test_nse_trading_day_verification_route_dispatches_page(monkeypatch):
    client = _client()
    captured = {}

    def fake_verification(year=None):
        captured['year'] = year
        return {'ok': True, 'status': 'SUCCESS', 'page': 'FFMC', 'year': year}

    monkeypatch.setattr(marketdata_route.nse_ffmc_svc, 'get_trading_day_verification', fake_verification)

    response = client.get('/api/marketdata/market-calendar/trading-day-verification?page=FFMC&year=2026')

    assert response.status_code == 200
    assert response.get_json() == {'ok': True, 'status': 'SUCCESS', 'page': 'FFMC', 'year': 2026}
    assert captured['year'] == 2026


def test_nse_trading_day_verification_route_rejects_unknown_page():
    client = _client()

    response = client.get('/api/marketdata/market-calendar/trading-day-verification?page=unknown&year=2026')

    assert response.status_code == 400
    assert 'page must be one of' in response.get_json()['message']


def test_nse_ffmc_pipeline_start_uses_background_job(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        marketdata_route.nse_ffmc_svc,
        'start_pipeline_job',
        lambda payload: {'ok': True, 'jobId': 'ffmc-job', 'status': 'running', 'request': payload},
    )

    response = client.post('/api/marketdata/nse-ffmc/pipeline/start', json={'tradeDate': '2026-03-17'})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['jobId'] == 'ffmc-job'
    assert payload['status'] == 'running'
    assert payload['request']['tradeDate'] == '2026-03-17'


def test_nse_ffmc_latest_job_endpoint_forwards_tail(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        marketdata_route.nse_ffmc_svc,
        'get_latest_job',
        lambda tail_lines=None: {'ok': True, 'jobId': 'ffmc-job', 'tail': tail_lines},
    )

    response = client.get('/api/marketdata/nse-ffmc/jobs/latest?tail=55')

    assert response.status_code == 200
    assert response.get_json() == {'ok': True, 'jobId': 'ffmc-job', 'tail': 55}


def test_nse_ffmc_process_existing_csv_symbols_endpoint(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        marketdata_route.nse_ffmc_svc,
        'process_existing_csv_for_symbols_api',
        lambda payload: {
            'ok': True,
            'status': 'success',
            'dataset_type': 'ffmc',
            'requested_symbols': ['ITC'],
            'valid_symbols': ['ITC'],
            'invalid_symbols': [],
            'symbols_found_in_csv': ['ITC'],
            'symbols_not_found_in_csv': [],
            'records_inserted': 7,
            'records_skipped_existing': 1,
            'errors': [],
        },
    )

    response = client.post('/api/marketdata/nse-ffmc/process-existing-csv-symbols', json={'symbols': 'ITC'})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['dataset_type'] == 'ffmc'
    assert payload['records_inserted'] == 7


def test_nse_delivery_pipeline_start_uses_background_job(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        marketdata_route.nse_delivery_svc,
        'start_pipeline_job',
        lambda payload: {'ok': True, 'jobId': 'delivery-job', 'status': 'running', 'request': payload},
    )

    response = client.post('/api/marketdata/nse-delivery/pipeline/start', json={'tradeDate': '2026-03-17'})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['jobId'] == 'delivery-job'
    assert payload['status'] == 'running'
    assert payload['request']['tradeDate'] == '2026-03-17'


def test_nse_delivery_latest_job_endpoint_forwards_tail(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        marketdata_route.nse_delivery_svc,
        'get_latest_job',
        lambda tail_lines=None: {'ok': True, 'jobId': 'delivery-job', 'tail': tail_lines},
    )

    response = client.get('/api/marketdata/nse-delivery/jobs/latest?tail=33')

    assert response.status_code == 200
    assert response.get_json() == {'ok': True, 'jobId': 'delivery-job', 'tail': 33}


def test_nse_mcap_process_existing_csv_symbols_endpoint(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        marketdata_route.nse_mcap_svc,
        'process_existing_csv_for_symbols_api',
        lambda payload: {
            'ok': True,
            'status': 'success',
            'dataset_type': 'market_cap',
            'requested_symbols': ['ITC'],
            'valid_symbols': ['ITC'],
            'invalid_symbols': [],
            'symbols_found_in_csv': ['ITC'],
            'symbols_not_found_in_csv': [],
            'records_inserted': 10,
            'records_skipped_existing': 2,
            'errors': [],
        },
    )

    response = client.post('/api/marketdata/nse-mcap/process-existing-csv-symbols', json={'symbols': 'ITC'})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['dataset_type'] == 'market_cap'
    assert payload['records_inserted'] == 10


def test_nse_delivery_process_existing_csv_symbols_endpoint(monkeypatch):
    client = _client()
    monkeypatch.setattr(
        marketdata_route.nse_delivery_svc,
        'process_existing_csv_for_symbols_api',
        lambda payload: {
            'ok': True,
            'status': 'success',
            'dataset_type': 'delivery_data',
            'requested_symbols': ['ITC'],
            'valid_symbols': ['ITC'],
            'invalid_symbols': [],
            'symbols_found_in_csv': ['ITC'],
            'symbols_not_found_in_csv': [],
            'records_inserted': 12,
            'records_skipped_existing': 5,
            'errors': [],
        },
    )

    response = client.post('/api/marketdata/nse-delivery/process-existing-csv-symbols', json={'symbols': 'ITC'})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['dataset_type'] == 'delivery_data'
    assert payload['records_skipped_existing'] == 5
