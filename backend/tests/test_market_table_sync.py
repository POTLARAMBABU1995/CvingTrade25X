from datetime import date
from pathlib import Path
import sys
from flask import Flask

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import routes.database as database_route
import services.market_table_sync_service as sync_svc

def test_get_sync_status_endpoints(monkeypatch):
    # Mock get_sync_status output
    mock_status = {
        'dev_ltc_date': '2026-06-25',
        'mcap_ltc_date': '2026-06-25',
        'ffmc_ltc_date': '2026-06-25',
        'delivery_ltc_date': '2026-06-25',
        'is_fully_synced': True,
        'missing_mcap_count': 0,
        'missing_ffmc_count': 0,
        'missing_delivery_count': 0,
        'stale_tables': [],
        'missing_symbols': {'mcap': [], 'ffmc': [], 'delivery': []},
        'last_sync_time': '2026-06-26T08:00:00',
        'message': 'All tables fully synchronized.'
    }
    
    monkeypatch.setattr(sync_svc, 'get_sync_status', lambda: mock_status)
    
    app = Flask(__name__)
    app.register_blueprint(database_route.bp)
    client = app.test_client()
    
    response = client.get('/api/database/sync-status')
    assert response.status_code == 200
    
    payload = response.get_json()
    assert payload['is_fully_synced'] is True
    assert payload['dev_ltc_date'] == '2026-06-25'


def test_post_sync_latest_market_tables_endpoint(monkeypatch):
    mock_result = {
        'ok': True,
        'message': 'Sync process completed.',
        'summary': {
            'mcap': {'processed': False, 'status': 'ALREADY_EXISTS'},
            'ffmc': {'processed': False, 'status': 'ALREADY_EXISTS'},
            'delivery': {'processed': False, 'status': 'ALREADY_EXISTS'}
        }
    }
    
    monkeypatch.setattr(sync_svc, 'sync_latest_market_tables', lambda: mock_result)
    
    app = Flask(__name__)
    app.register_blueprint(database_route.bp)
    client = app.test_client()
    
    response = client.post('/api/database/sync-latest-market-tables')
    assert response.status_code == 200
    
    payload = response.get_json()
    assert payload['ok'] is True
    assert 'summary' in payload
