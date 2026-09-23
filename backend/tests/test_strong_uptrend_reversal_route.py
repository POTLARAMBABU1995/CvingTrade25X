from pathlib import Path
import sys
import types

from flask import Flask


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

db_pool_stub = types.ModuleType('db_pool')
db_pool_stub.pool = None
db_pool_stub.fetchall_dict = lambda _cur: []
sys.modules['db_pool'] = db_pool_stub

cache_stub = types.ModuleType('cache')


class _DummyTTLCache:
    def __init__(self, *args, **kwargs):
        self._store = {}

    def get(self, key):
        return self._store.get(key)

    def set(self, key, value):
        self._store[key] = value


cache_stub.TTLCache = _DummyTTLCache
sys.modules['cache'] = cache_stub

import routes.strong_uptrend_reversal as strong_uptrend_route
sys.modules.pop('cache', None)


def test_route_returns_json_payload(monkeypatch):
    seen = {'refresh': None}

    def _payload(refresh=False):
        seen['refresh'] = refresh
        return {'data': [{'SYMBOL': 'RELIANCE', 'SCORE': 90}], 'status': 'SUCCESS', 'meta': {'rows': 1, 'tradingDate': '2026-05-14'}}

    monkeypatch.setattr(strong_uptrend_route, 'fetch_strong_uptrend_reversal_scan', _payload)
    monkeypatch.setattr(
        strong_uptrend_route.nse_mcap_svc,
        'enrich_payload_marketcap_index',
        lambda payload, row_keys=('rows',): {
            **payload,
            'data': [{**payload['data'][0], 'INDEX': 'LARGE', 'MCAP': 1900000.25, 'MCAP_RANK': 1}],
        },
    )

    app = Flask(__name__)
    app.register_blueprint(strong_uptrend_route.bp)
    client = app.test_client()

    response = client.get('/api/strategy/strong-uptrend-reversal?refresh=1')
    payload = response.get_json()

    assert response.status_code == 200
    assert response.headers['Content-Type'].startswith('application/json')
    assert seen['refresh'] is True
    assert payload['status'] == 'SUCCESS'
    assert payload['data'][0]['SYMBOL'] == 'RELIANCE'
    assert payload['data'][0]['INDEX'] == 'LARGE'
    assert payload['data'][0]['MCAP_RANK'] == 1


def test_route_returns_safe_json_error(monkeypatch):
    monkeypatch.setattr(
        strong_uptrend_route,
        'fetch_strong_uptrend_reversal_scan',
        lambda refresh=False: (_ for _ in ()).throw(RuntimeError('oracle failed')),
    )

    app = Flask(__name__)
    app.register_blueprint(strong_uptrend_route.bp)
    client = app.test_client()

    response = client.get('/api/strategy/strong-uptrend-reversal')
    payload = response.get_json()

    assert response.status_code == 500
    assert response.headers['Content-Type'].startswith('application/json')
    assert payload == {
        'data': [],
        'error': 'Failed to load strong uptrend reversal scanner.',
        'status': 'FAILED',
    }
