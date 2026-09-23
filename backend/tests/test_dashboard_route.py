from pathlib import Path
import sys

from flask import Flask


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import routes.dashboard as dashboard_route


def _current_payload():
    return {
        'tradingDate': '04-04-2026',
        'gainers': [],
        'losers': [],
        'breadth': {'advances': 250, 'declines': 190, 'unchanged': 58, 'skip': 2, 'totalSymbols': 500},
        'breadthRows': [
            {'segment': 'nifty50'},
            {'segment': 'next50'},
            {'segment': 'midcap'},
            {'segment': 'smallcap'},
            {'segment': 'nifty500'},
        ],
    }


def test_dashboard_route_accepts_near_complete_cached_payload_without_next50(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(dashboard_route.bp)
    client = app.test_client()

    near_complete_payload = {
        'tradingDate': '02-04-2026',
        'gainers': [],
        'losers': [],
        'breadth': {'advances': 220, 'declines': 226, 'unchanged': 2, 'skip': 0, 'totalSymbols': 448},
        'breadthRows': [
            {'segment': 'nifty50'},
            {'segment': 'midcap'},
            {'segment': 'smallcap'},
            {'segment': 'nifty500'},
        ],
    }

    dashboard_route._cache.clear()
    dashboard_route._cache.set('movers:nifty50:5', near_complete_payload)
    monkeypatch.setattr(dashboard_route, '_refresh_payload_sync', lambda segment, limit: (_ for _ in ()).throw(RuntimeError('should not refresh')))
    monkeypatch.setattr(dashboard_route, 'load_json_snapshot', lambda path: None)
    monkeypatch.setattr(dashboard_route, 'get_dashboard_latest_trading_date', lambda segment=None: '02-04-2026')

    response = client.get('/api/dashboard/movers')
    assert response.status_code == 200

    payload = response.get_json()
    assert payload['cached'] is True
    assert [row['segment'] for row in payload['breadthRows']] == ['nifty50', 'midcap', 'smallcap', 'nifty500']


def test_dashboard_route_accepts_current_cached_payload(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(dashboard_route.bp)
    client = app.test_client()

    fresh_payload = _current_payload()
    dashboard_route._cache.clear()
    dashboard_route._cache.set('movers:nifty50:5', fresh_payload)
    monkeypatch.setattr(dashboard_route, 'get_dashboard_latest_trading_date', lambda segment=None: '04-04-2026')

    response = client.get('/api/dashboard/movers')
    assert response.status_code == 200

    payload = response.get_json()
    assert payload['cached'] is True
    assert [row['segment'] for row in payload['breadthRows']] == ['nifty50', 'next50', 'midcap', 'smallcap', 'nifty500']


def test_dashboard_route_rejects_invalid_fallback_when_refresh_fails(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(dashboard_route.bp)
    client = app.test_client()

    invalid_payload = {
        'tradingDate': '02-04-2026',
        'gainers': [],
        'losers': [],
        'breadth': {'advances': 220, 'declines': 226, 'unchanged': 2, 'skip': 0, 'totalSymbols': 448},
        'breadthRows': [],
    }

    dashboard_route._cache.clear()
    dashboard_route._cache.set('movers:nifty50:5', invalid_payload)
    monkeypatch.setattr(dashboard_route, '_refresh_payload_sync', lambda segment, limit: (_ for _ in ()).throw(RuntimeError('boom')))
    monkeypatch.setattr(dashboard_route, 'load_json_snapshot', lambda path: invalid_payload)

    response = client.get('/api/dashboard/movers')
    assert response.status_code == 503

    payload = response.get_json()
    assert payload['message'] == 'Dashboard data unavailable'
    assert 'breadthRows' not in payload


def test_dashboard_route_serves_snapshot_without_blocking_refresh(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(dashboard_route.bp)
    client = app.test_client()

    snapshot_payload = _current_payload()
    refresh_calls = []

    dashboard_route._cache.clear()
    monkeypatch.setattr(dashboard_route, 'load_json_snapshot', lambda path: snapshot_payload)
    monkeypatch.setattr(dashboard_route, '_refresh_payload_sync', lambda segment, limit: (_ for _ in ()).throw(RuntimeError('should not refresh synchronously')))
    monkeypatch.setattr(dashboard_route, '_schedule_background_refresh', lambda segment, limit, key: refresh_calls.append((segment, limit, key)))
    monkeypatch.setattr(dashboard_route, 'get_dashboard_latest_trading_date', lambda segment=None: '04-04-2026')

    response = client.get('/api/dashboard/movers')
    assert response.status_code == 200

    payload = response.get_json()
    assert payload['cached'] is True
    assert 'stale' not in payload
    assert 'refreshing' not in payload
    assert refresh_calls == []


def test_dashboard_route_schedules_snapshot_refresh_only_when_forced(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(dashboard_route.bp)
    client = app.test_client()

    snapshot_payload = _current_payload()
    refresh_calls = []

    dashboard_route._cache.clear()
    monkeypatch.setattr(dashboard_route, 'load_json_snapshot', lambda path: snapshot_payload)
    monkeypatch.setattr(dashboard_route, '_refresh_payload_sync', lambda segment, limit: (_ for _ in ()).throw(RuntimeError('should not refresh synchronously')))
    monkeypatch.setattr(dashboard_route, '_schedule_background_refresh', lambda segment, limit, key: refresh_calls.append((segment, limit, key)))
    monkeypatch.setattr(dashboard_route, 'get_dashboard_latest_trading_date', lambda segment=None: '04-04-2026')

    response = client.get('/api/dashboard/movers?refresh=1')
    assert response.status_code == 200

    payload = response.get_json()
    assert payload['cached'] is True
    assert payload['refreshing'] is True
    assert refresh_calls == [('nifty50', 5, 'movers:nifty50:5')]


def test_dashboard_route_serves_cached_payload_without_waiting_for_latest_date(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(dashboard_route.bp)
    client = app.test_client()

    stale_payload = _current_payload()
    stale_payload['tradingDate'] = '12-06-2026'
    dashboard_route._cache.clear()
    dashboard_route._cache.set('movers:nifty50:5', stale_payload)
    monkeypatch.setattr(dashboard_route, 'load_json_snapshot', lambda path: None)

    response = client.get('/api/dashboard/movers')
    assert response.status_code == 200

    payload = response.get_json()
    assert payload['cached'] is True
    assert payload['tradingDate'] == '12-06-2026'


def test_dashboard_route_serves_snapshot_payload_without_waiting_for_latest_date(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(dashboard_route.bp)
    client = app.test_client()

    stale_snapshot = _current_payload()
    stale_snapshot['tradingDate'] = '12-06-2026'

    dashboard_route._cache.clear()
    monkeypatch.setattr(dashboard_route, 'load_json_snapshot', lambda path: stale_snapshot)

    response = client.get('/api/dashboard/movers')
    assert response.status_code == 200

    payload = response.get_json()
    assert payload['cached'] is True
    assert payload['tradingDate'] == '12-06-2026'


def test_dashboard_route_serves_snapshot_with_incomplete_optional_marketcap_metadata(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(dashboard_route.bp)
    client = app.test_client()

    snapshot_payload = _current_payload()
    snapshot_payload['gainers'] = [{'symbol': 'EXAMPLE', 'volume': 100}]
    dashboard_route._cache.clear()
    monkeypatch.setattr(dashboard_route, 'load_json_snapshot', lambda path: snapshot_payload)
    monkeypatch.setattr(
        dashboard_route.nse_mcap_svc,
        'enrich_rows_with_marketcap_index',
        lambda rows: (_ for _ in ()).throw(RuntimeError('snapshot request must not query Oracle metadata')),
    )

    response = client.get('/api/dashboard/movers?segment=nifty500&limit=25')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['cached'] is True
    assert payload['gainers'][0]['symbol'] == 'EXAMPLE'
