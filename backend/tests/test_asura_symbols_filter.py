from pathlib import Path
import sys
import types
from datetime import date

from flask import Flask


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

db_pool_stub = types.ModuleType('db_pool')
db_pool_stub.pool = types.SimpleNamespace(acquire=lambda: None)
sys.modules['db_pool'] = db_pool_stub

import routes.asura as asura_route


class _DummyCache:
    def get(self, _key):
        return None

    def set(self, _key, _value):
        return None


class _StaleCache:
    def __init__(self, payload):
        self.payload = payload
        self.get_calls = 0
        self.set_calls = 0

    def get(self, _key):
        self.get_calls += 1
        return self.payload

    def set(self, _key, _value):
        self.set_calls += 1
        return None


class _MemoryCache:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value


def _client():
    app = Flask(__name__)
    app.register_blueprint(asura_route.bp)
    return app.test_client()


def test_apply_query_filters_exact_symbols_match_normalized_codes():
    items = [
        {
            'symbol': 'TANLA',
            'stockName': 'Tanla',
            'trendDirection': 'DOWNTREND',
            'signalScore': 5,
            'adx14': 10,
            'emaStack': 'BEAR_STACK',
            'breakoutFlag': 'NONE',
            'stopLoss': 10,
            'target1': 12,
            'target2': 14,
        },
        {
            'symbol': 'IOC',
            'stockName': 'IOC',
            'trendDirection': 'UPTREND',
            'signalScore': 75,
            'adx14': 30,
            'emaStack': 'BULL_STACK',
            'breakoutFlag': 'BREAKOUT',
            'stopLoss': 10,
            'target1': 12,
            'target2': 14,
        },
    ]

    payload = asura_route._apply_query_filters(
        items,
        min_signal=0,
        min_adx=0,
        breakout_only=False,
        sort='symbol',
        order='asc',
        search=None,
        symbols=('TANLA',),
        page=1,
        page_size=50,
    )

    assert payload['total'] == 1
    assert payload['items'][0]['symbol'] == 'TANLA'


def test_apply_query_filters_without_exact_symbols_keeps_strategy_filters():
    items = [
        {
            'symbol': 'TANLA',
            'stockName': 'Tanla',
            'trendDirection': 'DOWNTREND',
            'signalScore': 5,
            'adx14': 10,
            'emaStack': 'BEAR_STACK',
            'breakoutFlag': 'NONE',
            'stopLoss': 10,
            'target1': 12,
            'target2': 14,
        }
    ]

    payload = asura_route._apply_query_filters(
        items,
        min_signal=0,
        min_adx=0,
        breakout_only=False,
        sort='symbol',
        order='asc',
        search=None,
        symbols=(),
        page=1,
        page_size=50,
    )

    assert payload['total'] == 0


def test_api_asura_forwards_normalized_symbols(monkeypatch):
    client = _client()
    captured = {}

    monkeypatch.setattr(asura_route, '_cache', _DummyCache())
    monkeypatch.setattr(asura_route, '_get_runtime_agent_defaults', lambda: {'min_signal': 60, 'min_adx': 20, 'breakout_only': False})

    def fake_compute_payload(**kwargs):
        captured['symbols'] = kwargs['symbols']
        return {'items': [], 'total': 0, 'page': 1, 'page_size': kwargs['page_size'], 'generated_at': '2026-04-13T00:00:00Z'}

    monkeypatch.setattr(asura_route, '_compute_payload', fake_compute_payload)

    response = client.get('/api/asura?symbols=NSE:TANLA-EQ,IOC')

    assert response.status_code == 200
    assert captured['symbols'] == ('TANLA', 'IOC')


def test_api_asura_exact_symbol_lookup_bypasses_stale_cache(monkeypatch):
    client = _client()
    stale_cache = _StaleCache({'items': [{'symbol': 'GAEL'}], 'total': 1, 'page': 1, 'page_size': 50})
    captured = {}

    monkeypatch.setattr(asura_route, '_cache', stale_cache)
    monkeypatch.setattr(asura_route, '_get_runtime_agent_defaults', lambda: {'min_signal': 60, 'min_adx': 20, 'breakout_only': False})

    def fake_compute_payload(**kwargs):
        captured['symbols'] = kwargs['symbols']
        return {'items': [{'symbol': 'TANLA'}, {'symbol': 'IOC'}], 'total': 2, 'page': 1, 'page_size': kwargs['page_size'], 'generated_at': '2026-04-13T00:00:00Z'}

    monkeypatch.setattr(asura_route, '_compute_payload', fake_compute_payload)

    response = client.get('/api/asura?symbols=NSE:TANLA-EQ,IOC')

    assert response.status_code == 200
    assert captured['symbols'] == ('TANLA', 'IOC')
    payload = response.get_json()
    assert payload['total'] == 2
    assert [item['symbol'] for item in payload['items']] == ['TANLA', 'IOC']
    assert stale_cache.get_calls == 0
    assert stale_cache.set_calls == 0


def test_api_asura_source_missing_uses_snapshot_fast_path(monkeypatch):
    client = _client()
    memory_cache = _MemoryCache()
    snapshot = {
        'items': [{
            'symbol': 'ABC',
            'stockName': 'ABC',
            'trendDirection': 'UPTREND',
            'signalScore': 82,
            'adx14': 31,
            'emaStack': 'BULL_STACK',
            'breakoutFlag': 'BREAKOUT',
            'stopLoss': 90,
            'target1': 110,
            'target2': 120,
        }],
        'total': 1,
        'generated_at': '2026-05-23T00:00:00Z',
        'as_of_date': '2026-05-22',
        'athSource': 'NSE_NIFTY500_DAILY_RAW_DATA_DEV',
    }

    monkeypatch.setattr(asura_route, '_cache', memory_cache)
    monkeypatch.setattr(asura_route, '_get_runtime_agent_defaults', lambda: {'min_signal': 60, 'min_adx': 20, 'breakout_only': False})
    monkeypatch.setattr(asura_route, '_has_precomputed_source', lambda: False)
    monkeypatch.setattr(asura_route, '_load_local_snapshot_payload', lambda _tf: ({**snapshot, 'cached': True}, []))
    monkeypatch.setattr(asura_route, '_schedule_local_snapshot_refresh', lambda _tf: None)
    monkeypatch.setattr(asura_route, '_wait_for_local_snapshot', lambda _tf, _wait_ms: None)
    monkeypatch.setattr(asura_route, '_compute_payload', lambda **_kwargs: (_ for _ in ()).throw(AssertionError('db compute must not run')))
    monkeypatch.setattr(asura_route, '_apply_authoritative_ath', lambda *_args, **_kwargs: {'elapsed_ms': 0, 'cache_hit': True})
    monkeypatch.setattr(asura_route.nse_mcap_svc, 'enrich_rows_with_marketcap_index', lambda rows, **_kwargs: list(rows))

    response = client.get('/api/asura?timeframe=daily&page=1&page_size=25&sort=signal_score&order=desc&conditions_only=1&skip_sync=1&include_exited=0')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['items'][0]['symbol'] == 'ABC'
    assert payload['cached'] is True
    assert payload['refreshing'] is False
    assert payload['fallback'] is True
    assert payload['local'] is True
    assert payload['meta']['source'] == 'local_snapshot'
    assert payload['meta']['snapshot_used'] is True


def test_api_asura_source_missing_cold_start_returns_warming_payload(monkeypatch):
    client = _client()
    memory_cache = _MemoryCache()
    refresh_calls = {'count': 0}

    monkeypatch.setattr(asura_route, '_cache', memory_cache)
    monkeypatch.setattr(asura_route, '_get_runtime_agent_defaults', lambda: {'min_signal': 60, 'min_adx': 20, 'breakout_only': False})
    monkeypatch.setattr(asura_route, '_has_precomputed_source', lambda: False)
    monkeypatch.setattr(asura_route, '_load_local_snapshot_payload', lambda _tf: (None, ['cold_start']))
    monkeypatch.setattr(asura_route, '_wait_for_local_snapshot', lambda _tf, _wait_ms: None)
    monkeypatch.setattr(asura_route, '_compute_payload', lambda **_kwargs: (_ for _ in ()).throw(AssertionError('sync local compute must not run')))
    monkeypatch.setattr(
        asura_route,
        '_schedule_local_snapshot_refresh',
        lambda _tf: refresh_calls.__setitem__('count', refresh_calls['count'] + 1),
    )

    response = client.get('/api/asura?timeframe=daily&page=1&page_size=25&sort=signal_score&order=desc&conditions_only=1&skip_sync=1&include_exited=0')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['items'] == []
    assert payload['total'] == 0
    assert payload['cached'] is True
    assert payload['refreshing'] is True
    assert payload['fallback'] is True
    assert payload['local'] is True
    assert payload['meta']['source'] == 'warming'
    assert payload['meta']['stale_reasons'] == ['cold_start']
    assert refresh_calls['count'] == 1


class _CursorCtx:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self._cursor

    def __exit__(self, exc_type, exc, tb):
        return False


class _ConnCtx:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, exc_type, exc, tb):
        return False


class _CaptureCursor:
    def __init__(self):
        self.executed = []
        self.arraysize = None
        self.prefetchrows = None
        self.description = []
        self._rows = []
        self._count = 0

    def execute(self, sql, binds=None):
        self.executed.append((sql, dict(binds or {})))
        if 'COUNT(*) AS CNT' in sql:
            self._count = 1
            return
        self.description = [
            ('SYMBOL',),
            ('STOCK_NAME',),
            ('TRADE_DATE',),
            ('CLOSE_PRICE',),
            ('SIGNAL_SCORE',),
            ('ADX14',),
            ('EMA_STACK',),
            ('TREND_DIRECTION',),
            ('STATUS',),
            ('TOTAL_COUNT',),
        ]
        self._rows = [
            (
                'ETERNAL',
                'Eternal',
                date(2026, 4, 23),
                100.0,
                74.0,
                35.0,
                'BULL_STACK',
                'UPTREND',
                'ACTIVE',
                1,
            )
        ]

    def fetchone(self):
        return (self._count,)

    def fetchall(self):
        return list(self._rows)


class _CaptureConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return _CursorCtx(self._cursor)


class _CapturePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _ConnCtx(self._conn)


def test_api_asura_last_buying_date_includes_latest_ltc_date(monkeypatch):
    class _LastDateCursor:
        def execute(self, _sql):
            return None

        def fetchone(self):
            return (date(2026, 5, 25),)

    monkeypatch.setattr(asura_route, 'pool', _CapturePool(_CaptureConn(_LastDateCursor())))
    monkeypatch.setattr(asura_route, 'fetch_latest_trade_date_from_oracle', lambda: date(2026, 5, 26))

    response = _client().get('/api/asura/last-buying-date')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['maxBuyingDate'] == '2026-05-25'
    assert payload['latestLtcDate'] == '2026-05-26'
    assert payload['maxLtcDate'] == '2026-05-26'


def test_api_asura_force_refresh_bypasses_cache_and_runs_sync_when_skip_sync_requested(monkeypatch):
    client = _client()
    stale_cache = _StaleCache({
        'items': [{'symbol': 'OLD', 'tradeDate': '2026-05-25'}],
        'total': 1,
        'page': 1,
        'page_size': 25,
    })
    captured = {}
    sync_calls = []

    def fake_compute_payload(**kwargs):
        captured.update(kwargs)
        return {
            'items': [{'symbol': 'NEW', 'tradeDate': '2026-05-26'}],
            'total': 1,
            'page': 1,
            'page_size': kwargs['page_size'],
            'generated_at': '2026-05-26T00:00:00Z',
        }

    monkeypatch.setattr(asura_route, '_cache', stale_cache)
    monkeypatch.setattr(asura_route, '_get_runtime_agent_defaults', lambda: {'min_signal': 60, 'min_adx': 20, 'breakout_only': False})
    monkeypatch.setattr(asura_route, 'sync_asura_bullish_strategy', lambda **kwargs: sync_calls.append(kwargs) or {'status': 'ok'})
    monkeypatch.setattr(asura_route, '_compute_payload', fake_compute_payload)
    monkeypatch.setattr(asura_route, '_with_marketcap', lambda payload: payload)

    response = client.get('/api/asura?timeframe=daily&page=1&page_size=25&sort=signal_score&order=desc&conditions_only=1&skip_sync=1&include_exited=0&refresh=1')

    assert response.status_code == 200
    payload = response.get_json()
    assert [item['symbol'] for item in payload['items']] == ['NEW']
    assert sync_calls
    assert captured['apply_authoritative_ath'] is True
    assert payload['meta']['sync_skipped'] is False
    assert stale_cache.set_calls == 1


def test_compute_payload_applies_latest_snapshot_and_exited_filter(monkeypatch):
    cursor = _CaptureCursor()
    conn = _CaptureConn(cursor)
    pool = _CapturePool(conn)
    available = {
        'SYMBOL',
        'STOCK_NAME',
        'TRADE_DATE',
        'CLOSE_PRICE',
        'SIGNAL_SCORE',
        'ADX14',
        'EMA_STACK',
        'TREND_DIRECTION',
        'STATUS',
        'STOP_LOSS',
        'TARGET1',
        'TARGET2',
    }
    monkeypatch.setattr(asura_route, 'pool', pool)
    monkeypatch.setattr(asura_route, '_resolve_source', lambda _conn: ('ASURA_SCAN_DAILY_FACT', available))
    monkeypatch.setattr(asura_route, '_apply_authoritative_ath', lambda *args, **kwargs: None)

    payload = asura_route._compute_payload(
        timeframe='daily',
        min_signal=60.0,
        min_adx=20.0,
        breakout_only=False,
        sort='signal_score',
        order='desc',
        page=1,
        page_size=15,
        search=None,
        symbols=(),
        conditions_only=True,
        include_exited=False,
        trade_start_date=None,
        trade_cutoff_date=None,
        latest_ltc_date='2026-05-26',
    )

    assert payload['total'] == 1
    assert payload['latestLtcDate'] == '2026-05-26'
    assert payload['items'][0]['ltcDate'] == '2026-05-26'
    assert payload['items'][0]['tradeDate'] == '2026-04-23'
    page_sql, page_binds = cursor.executed[0]
    normalized = " ".join(page_sql.split()).upper()
    assert 'SELECT MAX(S2.TRADE_DATE) FROM ASURA_SCAN_DAILY_FACT S2' in normalized
    assert "NOT IN ('EXITED', 'CLOSED', 'SELL', 'SOLD')" in normalized
    assert page_binds.get('min_signal') == 60.0
    assert page_binds.get('min_adx') == 20.0


def test_compute_payload_applies_date_range_filters(monkeypatch):
    cursor = _CaptureCursor()
    conn = _CaptureConn(cursor)
    pool = _CapturePool(conn)
    available = {
        'SYMBOL',
        'STOCK_NAME',
        'TRADE_DATE',
        'CLOSE_PRICE',
        'SIGNAL_SCORE',
        'ADX14',
        'EMA_STACK',
        'TREND_DIRECTION',
        'STATUS',
    }
    monkeypatch.setattr(asura_route, 'pool', pool)
    monkeypatch.setattr(asura_route, '_resolve_source', lambda _conn: ('ASURA_SCAN_DAILY_FACT', available))
    monkeypatch.setattr(asura_route, '_apply_authoritative_ath', lambda *args, **kwargs: None)

    payload = asura_route._compute_payload(
        timeframe='daily',
        min_signal=60.0,
        min_adx=20.0,
        breakout_only=False,
        sort='signal_score',
        order='desc',
        page=1,
        page_size=15,
        search=None,
        symbols=(),
        conditions_only=True,
        include_exited=True,
        trade_start_date=date(2026, 1, 1),
        trade_cutoff_date=date(2026, 4, 23),
    )

    assert payload['total'] == 1
    page_sql, page_binds = cursor.executed[0]
    normalized = " ".join(page_sql.split()).upper()
    assert 'S.TRADE_DATE BETWEEN :TRADE_START_DATE AND :TRADE_CUTOFF_DATE' in normalized
    assert page_binds.get('trade_start_date') == date(2026, 1, 1)
    assert page_binds.get('trade_cutoff_date') == date(2026, 4, 23)
    assert 'SELECT MAX(S2.TRADE_DATE)' not in normalized
