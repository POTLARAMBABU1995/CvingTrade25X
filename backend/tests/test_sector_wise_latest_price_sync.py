from datetime import date
from pathlib import Path
import importlib
import sys

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

sector_rotation = importlib.import_module('routes.sector_rotation')
trend_service = importlib.import_module('services.trend_service')


class _DummyCache:
    def __init__(self):
        self._store = {}

    def get(self, key):
        return self._store.get(key)

    def set(self, key, value):
        self._store[key] = value


def _patch_common(monkeypatch, *, raw_rows, latest_trade_map):
    monkeypatch.setattr(sector_rotation, '_popup_cache', _DummyCache())
    monkeypatch.setattr(sector_rotation, '_resolve_sector_candidates', lambda _sector: ['AUTO'])
    monkeypatch.setattr(sector_rotation, '_is_sector_snapshot_stale', lambda force_refresh=False: False)
    monkeypatch.setattr(sector_rotation, '_latest_raw_trading_date', lambda: None)
    monkeypatch.setattr(sector_rotation, '_load_strict_sector_symbols', lambda _sector: [])
    monkeypatch.setattr(sector_rotation, '_build_sector_wise_rows_sql', lambda _candidates, _symbols=None: ('SELECT 1', {}))
    monkeypatch.setattr(sector_rotation, '_query_rows', lambda _sql, _binds: raw_rows)
    monkeypatch.setattr(sector_rotation, '_load_sector_wise_trend_map', lambda force_refresh=False: {})
    monkeypatch.setattr(
        sector_rotation,
        '_load_sector_wise_raw_latest_trade_rows',
        lambda symbols, as_of_date: latest_trade_map,
    )
    monkeypatch.setattr(sector_rotation, 'get_all_time_high_for_symbols', lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        sector_rotation,
        'calculate_sector_stock_trend',
        lambda **_kwargs: {'trend': 'Uptrend', 'trendSort': 1, 'decisionReason': 'TEST'},
    )


def test_sector_wise_ema_bootstrap_matches_ema_page():
    closes = [100.0, 112.0, 108.5, 120.25, 117.0]
    period = 3
    state = None
    seed_window = []
    for close in closes:
        state = sector_rotation._next_ema(state, close, period, seed_window)

    assert state == pytest.approx(trend_service.ema(closes, period))


def test_sector_wise_raw_ema_reads_full_history(monkeypatch):
    executed = {}

    class _FakeCursor:
        description = [('stock',), ('tradingDate',), ('closeVal',)]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, _binds):
            executed['sql'] = sql

        def fetchall(self):
            return [
                ('ABC', date(2026, 1, 1), 100.0),
                ('ABC', date(2026, 1, 2), 112.0),
                ('ABC', date(2026, 1, 3), 108.5),
                ('ABC', date(2026, 1, 4), 120.25),
                ('ABC', date(2026, 1, 5), 117.0),
            ]

    class _FakeConnection:
        def cursor(self):
            return _FakeCursor()

        def close(self):
            return None

    monkeypatch.setattr(sector_rotation, '_raw_sma_source', lambda: ('NSE_NIFTY500_DAILY_RAW_DATA_DEV', 'PREVIOUS_CLOSE'))
    monkeypatch.setattr(sector_rotation, '_symbol_variants', lambda symbols: list(symbols))
    monkeypatch.setattr(sector_rotation, 'get_oracle_connection', lambda: _FakeConnection())

    result = sector_rotation._load_sector_wise_raw_ema(['ABC'], date(2026, 1, 5))

    assert 'RN <= 1000' not in executed['sql'].upper()
    assert result['ABC']['ema20'] == pytest.approx(trend_service.ema([100.0, 112.0, 108.5, 120.25, 117.0], 20))


def test_sector_wise_payload_uses_latest_raw_close_when_latest_date_advances(monkeypatch):
    raw_rows = [{
        'stock': 'ABC',
        'ltcDate': '2026-04-20',
        'price': 101.0,
        'ath': 120.0,
        'high52w': 130.0,
        'low52w': 80.0,
        'ema20': 95.0,
        'ema50': 90.0,
        'ema100': 85.0,
        'ema200': 75.0,
        'ema20FlagRaw': 'Y',
        'ema50FlagRaw': 'Y',
        'ema100FlagRaw': 'Y',
        'ema200FlagRaw': 'Y',
    }]
    latest_trade_map = {
        'ABC': {
            'latestDate': date(2026, 4, 21),
            'latestClose': 110.5,
        }
    }
    _patch_common(monkeypatch, raw_rows=raw_rows, latest_trade_map=latest_trade_map)

    payload = sector_rotation._load_sector_wise_payload(
        sector_code='AUTO',
        page=1,
        page_size=15,
        sort_key='STOCK',
        sort_dir='ASC',
        search_text='',
        force_refresh=True,
    )

    row = payload['rows'][0]
    assert row['ltcDate'] == '2026-04-21'
    assert row['price'] == 110.5
    assert row['gapPct'] == -7.92
    assert row['gap'] == '-7.92%'


def test_sector_wise_payload_fills_missing_price_from_latest_raw_close(monkeypatch):
    raw_rows = [{
        'stock': 'ABC',
        'ltcDate': '2026-04-21',
        'price': None,
        'ath': 120.0,
        'high52w': 130.0,
        'low52w': 80.0,
        'ema20': 95.0,
        'ema50': 90.0,
        'ema100': 85.0,
        'ema200': 75.0,
        'ema20FlagRaw': 'Y',
        'ema50FlagRaw': 'Y',
        'ema100FlagRaw': 'Y',
        'ema200FlagRaw': 'Y',
    }]
    latest_trade_map = {
        'ABC': {
            'latestDate': date(2026, 4, 21),
            'latestClose': 109.2,
        }
    }
    _patch_common(monkeypatch, raw_rows=raw_rows, latest_trade_map=latest_trade_map)

    payload = sector_rotation._load_sector_wise_payload(
        sector_code='AUTO',
        page=1,
        page_size=15,
        sort_key='STOCK',
        sort_dir='ASC',
        search_text='',
        force_refresh=True,
    )

    row = payload['rows'][0]
    assert row['ltcDate'] == '2026-04-21'
    assert row['price'] == 109.2
    assert row['gapPct'] == -9.0
    assert row['gap'] == '-9.00%'


def test_sector_wise_gap_uses_price_and_ath_after_latest_price_sync(monkeypatch):
    raw_rows = [{
        'stock': 'HINDALCO',
        'ltcDate': '2026-04-20',
        'price': 942.55,
        'ath': 1048.70,
        'high52w': 1048.70,
        'low52w': 500.0,
        'ema20': 1000.0,
        'ema50': 980.0,
        'ema100': 940.0,
        'ema200': 900.0,
        'ema20FlagRaw': 'Y',
        'ema50FlagRaw': 'Y',
        'ema100FlagRaw': 'Y',
        'ema200FlagRaw': 'Y',
    }]
    latest_trade_map = {
        'HINDALCO': {
            'latestDate': date(2026, 4, 21),
            'latestClose': 1039.90,
        }
    }
    _patch_common(monkeypatch, raw_rows=raw_rows, latest_trade_map=latest_trade_map)

    payload = sector_rotation._load_sector_wise_payload(
        sector_code='AUTO',
        page=1,
        page_size=15,
        sort_key='STOCK',
        sort_dir='ASC',
        search_text='',
        force_refresh=True,
    )

    row = payload['rows'][0]
    assert row['stock'] == 'HINDALCO'
    assert row['price'] == 1039.90
    assert row['ath'] == 1048.70
    assert row['gapPct'] == -0.84
    assert row['gap'] == '-0.84%'


def test_sector_wise_payload_reuses_expired_current_snapshot_before_db_reload(monkeypatch):
    class _SnapshotCacheStub:
        def __init__(self):
            self.renewed = None
            self.memory_cache = None

        def get_memory_cache(self, _key):
            return None

        def delete_memory_cache(self, _key):
            return None

        def get_snapshot(self, _table_name):
            return None

        def peek_snapshot(self, _table_name):
            return {
                'rows': [{
                    'stock': 'ABC',
                    'ltcDate': '2026-05-14',
                    'price': 110.5,
                    'ath': 120.0,
                    'high52w': 130.0,
                    'low52w': 80.0,
                    'ema20': 95.0,
                    'ema50': 90.0,
                    'ema100': 85.0,
                    'ema200': 75.0,
                    'index': 'AUTO',
                    'totalMcap': 1000.0,
                    'trend': 'Uptrend',
                    'score': 87.0,
                }],
                'ttlSeconds': 3600,
                'expiresAt': None,
            }

        def set_snapshot(self, table_name, *, sector_name, rows, ttl_seconds=None):
            self.renewed = {
                'table_name': table_name,
                'sector_name': sector_name,
                'rows': rows,
                'ttl_seconds': ttl_seconds,
            }
            return None

        def set_memory_cache(self, cache_key, *, table_name, sector_name, rows, ttl_seconds):
            self.memory_cache = {
                'cache_key': cache_key,
                'table_name': table_name,
                'sector_name': sector_name,
                'rows': rows,
                'ttl_seconds': ttl_seconds,
            }
            return self.memory_cache

        def delete_snapshot(self, _table_name):
            return None

    snapshot_cache = _SnapshotCacheStub()

    monkeypatch.setattr(sector_rotation, '_popup_cache', _DummyCache())
    monkeypatch.setattr(sector_rotation, '_resolve_sector_candidates', lambda _sector: ['AUTO'])
    monkeypatch.setattr(sector_rotation, '_load_strict_sector_symbols', lambda _sector: [])
    monkeypatch.setattr(sector_rotation, '_is_sector_snapshot_stale', lambda force_refresh=False: True)
    monkeypatch.setattr(sector_rotation, '_latest_raw_trading_date', lambda: date(2026, 5, 14))
    monkeypatch.setattr(sector_rotation, 'sector_cache_service', type('LegacyCache', (), {'get_cache': lambda self, _key: None, 'delete_cache': lambda self, _key: None})())
    monkeypatch.setattr(sector_rotation, 'sector_stock_cache_service', snapshot_cache)
    monkeypatch.setattr(
        sector_rotation,
        '_query_rows',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError('DB query should not run for a current expired snapshot')),
    )

    payload = sector_rotation._load_sector_wise_payload(
        sector_code='AUTO',
        page=1,
        page_size=15,
        sort_key='STOCK',
        sort_dir='ASC',
        search_text='',
        force_refresh=False,
    )

    assert payload['source'] == 'snapshot'
    assert payload['rows'][0]['stock'] == 'ABC'
    assert snapshot_cache.renewed is not None
    assert snapshot_cache.renewed['table_name'] == 'NSE_NIFTY_AUTO_STAGING'
    assert snapshot_cache.memory_cache is not None


def test_sector_wise_payload_serves_stale_snapshot_before_db_reload(monkeypatch):
    class _SnapshotCacheStub:
        def __init__(self):
            self.deleted_snapshot = False
            self.memory_cache = None
            self.renewed = None

        def get_memory_cache(self, _key):
            return None

        def delete_memory_cache(self, _key):
            return None

        def get_snapshot(self, _table_name):
            return None

        def peek_snapshot(self, _table_name):
            return {
                'rows': [{
                    'stock': 'ABC',
                    'ltcDate': '2026-06-30',
                    'price': 110.5,
                    'ath': 120.0,
                    'high52w': 130.0,
                    'low52w': 80.0,
                    'ema20': 95.0,
                    'ema50': 90.0,
                    'ema100': 85.0,
                    'ema200': 75.0,
                    'index': 'SMALL',
                    'totalMcap': 1000.0,
                    'mcapRank': 500,
                    'trend': 'Uptrend',
                    'score': 87.0,
                }],
                'loadedAt': '2026-07-01T09:09:14',
                'ttlSeconds': 3600,
                'expiresAt': None,
            }

        def set_snapshot(self, table_name, *, sector_name, rows, ttl_seconds=None):
            self.renewed = {
                'table_name': table_name,
                'sector_name': sector_name,
                'rows': rows,
                'ttl_seconds': ttl_seconds,
            }
            return None

        def set_memory_cache(self, cache_key, *, table_name, sector_name, rows, ttl_seconds):
            self.memory_cache = {
                'cache_key': cache_key,
                'table_name': table_name,
                'sector_name': sector_name,
                'rows': rows,
                'ttl_seconds': ttl_seconds,
            }
            return self.memory_cache

        def delete_snapshot(self, _table_name):
            self.deleted_snapshot = True

    snapshot_cache = _SnapshotCacheStub()

    monkeypatch.setattr(sector_rotation, '_popup_cache', _DummyCache())
    monkeypatch.setattr(sector_rotation, '_resolve_sector_candidates', lambda _sector: ['RUBBER_PRODUCTS_TYRES'])
    monkeypatch.setattr(sector_rotation, '_load_strict_sector_symbols', lambda _sector: ['ABC'])
    monkeypatch.setattr(sector_rotation, '_is_sector_snapshot_stale', lambda force_refresh=False: True)
    monkeypatch.setattr(sector_rotation, '_latest_raw_trading_date', lambda: date(2026, 7, 1))
    monkeypatch.setattr(sector_rotation, 'sector_cache_service', type('LegacyCache', (), {'get_cache': lambda self, _key: None, 'delete_cache': lambda self, _key: None})())
    monkeypatch.setattr(sector_rotation, 'sector_stock_cache_service', snapshot_cache)
    monkeypatch.setattr(
        sector_rotation,
        '_query_rows',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError('DB query should not run for a stale snapshot fast load')),
    )

    payload = sector_rotation._load_sector_wise_payload(
        sector_code='RUBBER_PRODUCTS_TYRES',
        page=1,
        page_size=25,
        sort_key='STOCK',
        sort_dir='ASC',
        search_text='',
        force_refresh=False,
    )

    assert payload['source'] == 'stale_snapshot'
    assert payload['isStale'] is True
    assert payload['staleReason'] == 'snapshot_behind_latest_raw_date'
    assert payload['loadedAt'] == '2026-07-01T09:09:14'
    assert payload['rows'][0]['stock'] == 'ABC'
    assert snapshot_cache.deleted_snapshot is False
    assert snapshot_cache.renewed is None
    assert snapshot_cache.memory_cache is not None
    assert snapshot_cache.memory_cache['ttl_seconds'] == sector_rotation._SECTOR_STALE_SNAPSHOT_CACHE_TTL_SECONDS
