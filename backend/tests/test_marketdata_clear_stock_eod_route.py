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


class _FakeCursor:
    def __init__(self, *, counts, delete_rowcount):
        self._counts = list(counts)
        self._delete_rowcount = delete_rowcount
        self.rowcount = 0
        self.sql = []

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, sql, _binds=None):
        self.sql.append(sql)
        if str(sql).strip().upper().startswith("DELETE"):
            self.rowcount = self._delete_rowcount
        else:
            self.rowcount = 0

    def fetchone(self):
        if not self._counts:
            return [0]
        value = self._counts.pop(0)
        if isinstance(value, (list, tuple)):
            return list(value)
        return [value]


class _FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class _FakePool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return self.connection


def _client():
    app = Flask(__name__)
    app.register_blueprint(marketdata_route.bp)
    return app.test_client()


def test_clear_stock_eod_endpoint_success(monkeypatch):
    client = _client()

    monkeypatch.setattr(
        marketdata_route.svc,
        'clear_stock_eod_history',
        lambda confirm_text: {
            'ok': True,
            'success': True,
            'table_name': 'STOCK_EOD_HISTORY',
            'deleted_rows': 125,
            'previous_record_count': 125,
            'before_count': 125,
            'remaining_rows': 0,
            'message': 'Delete completed successfully.',
        },
    )

    response = client.post('/api/marketdata/stock-eod/clear', json={'confirm_text': 'DELETE'})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['ok'] is True
    assert payload['success'] is True
    assert payload['table_name'] == 'STOCK_EOD_HISTORY'
    assert payload['deleted_rows'] == 125
    assert payload['remaining_rows'] == 0


def test_clear_stock_eod_endpoint_invalid_confirmation(monkeypatch):
    client = _client()

    def _raise(_confirm_text):
        raise ValueError('Delete confirmation failed. Type DELETE to confirm.')

    monkeypatch.setattr(marketdata_route.svc, 'clear_stock_eod_history', _raise)

    response = client.post('/api/marketdata/stock-eod/clear', json={'confirm_text': 'NO'})

    assert response.status_code == 400
    payload = response.get_json()
    assert payload['status'] == 'error'
    assert 'Type DELETE to confirm' in payload['message']


def test_symbols_endpoint_passes_stock_eod_source(monkeypatch):
    client = _client()
    captured = {}

    def _list_symbols(prefix=None, limit=None, source=None):
        captured.update({"prefix": prefix, "limit": limit, "source": source})
        return []

    monkeypatch.setattr(marketdata_route.svc, 'list_symbols', _list_symbols)

    response = client.get('/api/marketdata/symbols?source=stock_eod&limit=5000')

    assert response.status_code == 200
    assert response.get_json() == []
    assert captured == {"prefix": None, "limit": 5000, "source": "stock_eod"}


def test_market_stats_stock_eod_source_uses_stock_eod_table(monkeypatch):
    cursor = _FakeCursor(counts=[(None, 0, 0)], delete_rowcount=0)
    connection = _FakeConnection(cursor)

    def _fetchall_dict(cur):
        sql = str(cur.sql[-1]).upper()
        assert "FROM STOCK_EOD_HISTORY" in sql
        return [{"record_count": 0, "stock_count": 0}]

    monkeypatch.setattr(marketdata_route.svc, 'pool', _FakePool(connection))
    monkeypatch.setattr(marketdata_route.svc, 'fetchall_dict', _fetchall_dict)
    monkeypatch.setattr(marketdata_route.svc, '_stock_eod_pending_dev_summary', lambda _cur: {
        'stock_eod_latest_trade_date': None,
        'stock_eod_latest_source_rows': 0,
        'stock_eod_pending_dev_count': 0,
        'stock_eod_latest_pending_dev_count': 0,
    })
    monkeypatch.setattr(marketdata_route.svc, '_stock_eod_sync_card_summary', lambda _cur: {
        'stock_eod_synced_rows': 0,
        'stock_eod_synched_rows': 0,
        'stock_eod_unsynced_rows': 0,
        'stock_eod_unsynched_rows': 0,
        'stock_eod_pending_sync_count': 0,
        'stockEodSyncedRows': 0,
        'stockEodUnsyncedRows': 0,
    })
    monkeypatch.delenv('MARKETDATA_STOCK_EOD_TABLE', raising=False)

    payload = marketdata_route.svc.market_stats(source='stock_eod')

    assert payload['source'] == 'STOCK_EOD_HISTORY'
    assert payload['record_count'] == 0
    assert payload['stock_count'] == 0
    assert payload['stock_eod_record_count'] == 0
    assert payload['stock_eod_pending_dev_count'] == 0
    assert payload['stock_eod_synched_rows'] == 0
    assert payload['stock_eod_unsynched_rows'] == 0


def test_stock_eod_sync_card_summary_counts_both_target_status(monkeypatch):
    cursor = _FakeCursor(counts=[(123, 7)], delete_rowcount=0)
    monkeypatch.delenv('MARKETDATA_STOCK_EOD_TABLE', raising=False)

    payload = marketdata_route.svc._stock_eod_sync_card_summary(cursor)

    assert payload['stock_eod_synched_rows'] == 123
    assert payload['stock_eod_unsynched_rows'] == 7
    assert payload['stockEodSyncedRows'] == 123
    assert payload['stockEodUnsyncedRows'] == 7
    sql = " ".join(cursor.sql[-1].split()).upper()
    assert "LEFT JOIN NSE_NIFTY500_DAILY_RAW_DATA_DEV D" in sql
    assert "LEFT JOIN NSE_NIFTY500_DAILY_RAW_DATA_ORACLE O" in sql


def test_clear_stock_eod_endpoint_delete_verification_error(monkeypatch):
    client = _client()

    def _raise(_confirm_text):
        raise marketdata_route.svc.StockEodDeleteError(
            'Delete verification failed for STOCK_EOD_HISTORY: before_count=125, deleted_rows=0.'
        )

    monkeypatch.setattr(marketdata_route.svc, 'clear_stock_eod_history', _raise)

    response = client.post('/api/marketdata/stock-eod/clear', json={'confirm_text': 'DELETE'})

    assert response.status_code == 409
    payload = response.get_json()
    assert payload['status'] == 'error'
    assert 'before_count=125' in payload['message']


def test_clear_stock_eod_history_deletes_all_rows_and_commits(monkeypatch):
    cursor = _FakeCursor(counts=[125, 0], delete_rowcount=125)
    connection = _FakeConnection(cursor)
    monkeypatch.setattr(marketdata_route.svc, 'pool', _FakePool(connection))
    monkeypatch.delenv('MARKETDATA_STOCK_EOD_TABLE', raising=False)

    payload = marketdata_route.svc.clear_stock_eod_history('DELETE')

    assert payload['success'] is True
    assert payload['deleted_rows'] == 125
    assert payload['before_count'] == 125
    assert payload['remaining_rows'] == 0
    assert connection.committed is True
    assert connection.rolled_back is False
    assert cursor.sql == [
        'SELECT COUNT(*) FROM STOCK_EOD_HISTORY',
        'DELETE FROM STOCK_EOD_HISTORY',
        'SELECT COUNT(*) FROM STOCK_EOD_HISTORY',
    ]


def test_clear_stock_eod_history_rolls_back_when_delete_matches_zero(monkeypatch):
    cursor = _FakeCursor(counts=[125, 125], delete_rowcount=0)
    connection = _FakeConnection(cursor)
    monkeypatch.setattr(marketdata_route.svc, 'pool', _FakePool(connection))
    monkeypatch.delenv('MARKETDATA_STOCK_EOD_TABLE', raising=False)

    try:
        marketdata_route.svc.clear_stock_eod_history('DELETE')
    except marketdata_route.svc.StockEodDeleteError as exc:
        assert 'deleted_rows=0' in str(exc)
    else:
        raise AssertionError('expected StockEodDeleteError')

    assert connection.committed is False
    assert connection.rolled_back is True
