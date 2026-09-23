from datetime import date
from pathlib import Path
import json
import sys

from flask import Flask


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import routes.sector_rotation as sector_rotation_route
import services.sector_resolver_service as sector_resolver_service
import services.sector_rotation_v3_stock_service as sector_rotation_v3_stock_service


def test_api_sector_wise_uses_local_snapshot_before_oracle(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(sector_rotation_route.bp)
    client = app.test_client()

    sector_rotation_route._cache.clear()
    snapshot_rows = [
        {'stock': 'ZZZ', 'index': 'MID', 'totalMcap': 10, 'trend': 'Sideways', 'score': 55, 'price': 100},
        {'stock': 'AAA', 'index': 'LARGE', 'totalMcap': 20, 'trend': 'Uptrend', 'score': 80, 'price': 200},
    ]
    monkeypatch.setattr(
        sector_rotation_route.sector_stock_cache_service,
        'get_snapshot',
        lambda table_name: {
            'cacheVersion': 'v7',
            'tableName': table_name,
            'sectorName': 'Auto Mobile',
            'rows': snapshot_rows,
            'totalRows': len(snapshot_rows),
            'loadedAt': '2026-07-14T04:42:55',
            'expiresAt': '2026-07-14T05:42:55',
            'ttlSeconds': 3600,
        },
    )
    monkeypatch.setattr(
        sector_rotation_route,
        'get_latest_ltc_date_fast',
        lambda: (_ for _ in ()).throw(AssertionError('local snapshot must avoid Oracle latest-date lookup')),
    )
    monkeypatch.setattr(
        sector_rotation_route,
        'read_sector_wise_snapshot',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError('local snapshot must avoid Oracle snapshot lookup')),
    )
    monkeypatch.setattr(
        sector_resolver_service,
        'resolve_sector_key',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError('known sector must avoid Oracle resolver lookup')),
    )
    monkeypatch.setattr(
        sector_rotation_route,
        '_query_rows',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError('known sector must avoid Oracle master lookup')),
    )

    response = client.get('/api/sector/AUTO/stocks/sector-wise?page=1&pageSize=200&sort=STOCK&dir=ASC')

    assert response.status_code == 200
    assert response.headers.get('X-Source') == 'LOCAL_SNAPSHOT'
    assert int(response.headers.get('X-Response-Time-Ms', '1000')) < 1000
    payload = response.get_json()
    assert payload['source'] == 'snapshot'
    assert payload['totalCount'] == 2
    assert [row['stock'] for row in payload['rows']] == ['AAA', 'ZZZ']


def test_sector_wise_snapshot_rejects_current_rows_without_52_week_range():
    rows_invalid, reason = sector_rotation_route._sector_stock_rows_need_refresh([
        {
            'stock': 'JKPAPER',
            'index': 'SMALL',
            'totalMcap': 7279.04,
            'trend': 'Uptrend',
            'score': 55,
            'price': 401.45,
            'ltcDate': '2026-07-24',
            'ath': 638.75,
            'high52w': None,
            'low52w': None,
        }
    ])

    assert rows_invalid is True
    assert reason == 'missing_52_week_range'


def test_overview_adds_only_v3_unknown_symbols_absent_from_its_rows(monkeypatch, tmp_path):
    v3_snapshot = tmp_path / 'sector_rotation_v3_stocks_latest.json'
    v3_snapshot.write_text(json.dumps({
        'sectors': {
            'AUTO': {'rows': [
                {'symbol': 'KNOWN', 'trendState': 'DATA_WEAK'},
                {'symbol': 'MISSING', 'trendState': 'DATA_WEAK'},
            ]}
        }
    }), encoding='utf-8')
    monkeypatch.setattr(sector_rotation_route, '_SECTOR_V3_STOCK_SNAPSHOT_PATH', v3_snapshot)

    payload = sector_rotation_route._supplement_overview_unknowns_from_v3({
        'rows': [{'stock': 'KNOWN', 'trend': 'Uptrend'}],
        'total_stocks': 1,
        'trend_counts': {'Uptrend': 1, 'Unknown / Insufficient Data': 0},
        'sector_data_source': 'RAW_DATA_DEV_LATEST',
    })

    assert payload['total_stocks'] == 2
    assert payload['trend_counts']['Unknown / Insufficient Data'] == 1
    assert payload['rows'][-1]['stock'] == 'MISSING'


def test_v3_breadth_uses_staging_count_when_published_map_is_incomplete(monkeypatch):
    monkeypatch.setattr(
        sector_rotation_route,
        '_read_snapshot_from_disk',
        lambda: {
            'tables': [
                {
                    'tableName': 'NSE_NIFTY_PAPER_PACKAGING_STAGING',
                    'sectorCode': 'PAPER_PACKAGING',
                    'stockCount': 30,
                }
            ]
        },
    )

    rows = sector_rotation_route._supplement_v3_breadth_membership_counts([
        {'sectorCode': 'PAPER_PACKAGING', 'totalStocks': 1, 'totalSymbols': 1}
    ])

    assert rows == [{'sectorCode': 'PAPER_PACKAGING', 'totalStocks': 30, 'totalSymbols': 30}]


def test_api_sector_wise_v3_uses_only_published_stock_snapshot(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(sector_rotation_route.bp)
    client = app.test_client()

    calls = []
    monkeypatch.setattr(
        sector_rotation_v3_stock_service,
        'get_sector_rotation_v3_stock_page',
        lambda sector_code, **kwargs: calls.append((sector_code, kwargs)) or ({
            'ok': True,
            'status': 'success',
            'source': 'V3_ATOMIC_STOCK_SNAPSHOT',
            'version': 'v3',
            'runId': 'run-v3',
            'asOfDate': '2026-07-22',
            'technicalSourceDate': '2026-07-22',
            'rows': [{'symbol': 'MARUTI', 'stockEdgeScore': 88, 'trendState': 'STRONG_UPTREND'}],
            'totalRows': 1,
        }, 200),
    )
    monkeypatch.setattr(
        sector_rotation_route,
        '_load_sector_wise_payload',
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError('V3 must not fall back to V1/V2')),
    )

    response = client.get(
        '/api/sector/AUTO/stocks/sector-wise?version=v3&page=1&pageSize=25'
        '&sort=STOCK_EDGE_SCORE&dir=DESC'
    )

    assert response.status_code == 200
    assert response.headers['X-Sector-Rotation-Version'] == 'v3'
    assert response.headers['X-Source'] == 'V3_ATOMIC_STOCK_SNAPSHOT'
    assert response.get_json()['rows'][0]['trendState'] == 'STRONG_UPTREND'
    assert calls == [('AUTO', {
        'page': 1,
        'page_size': 25,
        'search': '',
        'sort_key': 'STOCK_EDGE_SCORE',
        'sort_dir': 'DESC',
    })]


def test_api_sector_wise_symbol_returns_exact_published_row(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(sector_rotation_route.bp)
    client = app.test_client()

    monkeypatch.setattr(
        sector_rotation_v3_stock_service,
        'get_sector_rotation_v3_stock_symbol',
        lambda symbol: ({
            'ok': True,
            'source': 'V3_ATOMIC_STOCK_SNAPSHOT',
            'symbol': 'TCS',
            'row': {'symbol': 'TCS', 'sectorName': 'IT'},
        }, 200),
    )

    response = client.get('/api/sectors/sector-wise-symbol?symbol=NSE%3ATCS-EQ')

    assert response.status_code == 200
    assert response.headers['X-Sector-Rotation-Version'] == 'v3'
    assert response.headers['X-Source'] == 'V3_ATOMIC_STOCK_SNAPSHOT'
    assert response.get_json()['row']['sectorName'] == 'IT'


def test_sector_wise_snapshot_publish_rejects_wrong_membership(monkeypatch):
    published = []
    monkeypatch.setattr(
        sector_rotation_route.sector_stock_cache_service,
        'set_snapshot',
        lambda *args, **kwargs: published.append((args, kwargs)),
    )

    accepted = sector_rotation_route._publish_sector_wise_local_snapshot(
        table_name='NSE_NIFTY_AUTO_STAGING',
        sector_name='AUTO',
        rows=[
            {
                'stock': 'HINDALCO',
                'index': 'LARGE',
                'totalMcap': 1,
                'trend': 'Uptrend',
                'score': 50,
                'price': 100,
            }
        ],
        expected_symbols=['ASHOKLEY', 'MARUTI'],
    )

    assert accepted is False
    assert published == []


def test_api_sectors_breadth_uses_local_snapshot_when_oracle_snapshot_missing(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(sector_rotation_route.bp)
    client = app.test_client()

    sector_rotation_route._cache.clear()
    monkeypatch.setattr(sector_rotation_route, 'get_latest_ltc_date_fast', lambda: date(2026, 6, 16))
    monkeypatch.setattr(sector_rotation_route, 'read_sector_rotation_snapshot', lambda _ltc_date: None)
    monkeypatch.setattr(
        sector_rotation_route,
        '_load_breadth_snapshot',
        lambda: [
            {
                'sectorCode': 'AUTO',
                'sectorName': 'Auto',
                'asOfDate': '2026-06-16',
                'rsi55Pct': 72,
                'rsi50Pct': 68,
                'sma20Pct': 66,
                'sma50Pct': 64,
                'sma100Pct': 61,
                'totalSymbols': 12,
                'rotationScore': 82.5,
            }
        ],
    )
    monkeypatch.setattr(sector_rotation_route, '_supplement_breadth_rows_with_sector_tables', lambda rows: rows)
    monkeypatch.setattr(
        sector_rotation_route,
        'ensure_sector_reference_data_synced',
        lambda: (_ for _ in ()).throw(RuntimeError('should not execute live query when local snapshot exists')),
    )

    response = client.get('/api/sectors/breadth?version=v2')
    assert response.status_code == 200
    assert response.headers.get('X-Source') == 'LOCAL_SNAPSHOT'

    payload = response.get_json()
    assert len(payload) == 1
    assert payload[0]['sectorCode'] == 'AUTO'
    assert payload[0]['rotationPhase'] == 'Leading'
    assert payload[0]['confidence'] == 'HIGH'


def test_api_sectors_breadth_v3_returns_feature_gated_envelope_without_changing_v2(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(sector_rotation_route.bp)
    client = app.test_client()

    sector_rotation_route._cache.clear()
    monkeypatch.setattr(sector_rotation_route, 'get_latest_ltc_date_fast', lambda: date(2026, 7, 15))
    monkeypatch.setattr(sector_rotation_route, 'read_sector_rotation_snapshot', lambda _ltc_date: None)
    monkeypatch.setattr(
        'services.sector_rotation_v3_repository.read_latest_published_v3_snapshot',
        lambda _ltc_date: None,
    )
    monkeypatch.setattr(
        sector_rotation_route,
        '_load_breadth_snapshot',
        lambda: [
            {
                'sectorCode': 'AUTO',
                'sectorName': 'Auto',
                'asOfDate': '2026-07-15',
                'latestDataDate': '2026-07-15',
                'totalSymbols': 12,
                'screenedStocks': 12,
                'historyCoveragePercent': 100,
                'rsi55Pct': 72,
                'rsi50Pct': 78,
                'sma20Pct': 75,
                'sma50Pct': 70,
                'sma100Pct': 65,
                'relativeMomentum': 0.8,
                'absoluteTrend': 0.8,
                'riskAdjustment': 0.7,
                'stockConfirmationScoreAvg': 0.75,
                'confirmedStocks': 9,
            },
            {
                'sectorCode': 'IT',
                'sectorName': 'IT',
                'asOfDate': '2026-07-15',
                'latestDataDate': '2026-07-15',
                'totalSymbols': 10,
                'screenedStocks': 10,
                'historyCoveragePercent': 100,
                'rsi55Pct': 55,
                'rsi50Pct': 60,
                'sma20Pct': 58,
                'sma50Pct': 52,
                'sma100Pct': 48,
                'relativeMomentum': 0.2,
                'absoluteTrend': 0.4,
                'riskAdjustment': 0.3,
                'stockConfirmationScoreAvg': 0.5,
                'confirmedStocks': 5,
            },
        ],
    )
    monkeypatch.setattr(sector_rotation_route, '_supplement_breadth_rows_with_sector_tables', lambda rows: rows)

    v3_response = client.get('/api/sectors/breadth?version=v3')
    assert v3_response.status_code == 200
    assert v3_response.headers['X-Sector-Rotation-Version'] == 'v3'
    v3_payload = v3_response.get_json()
    assert v3_payload['version'] == 'v3'
    assert v3_payload['modelVersion'] == 'SECTOR_ROTATION_V3'
    assert v3_payload['asOfDate'] == '2026-07-15'
    assert len(v3_payload['rows']) == 2
    assert v3_payload['rows'][0]['currentRank'] == 1
    assert v3_payload['rows'][0]['finalRotationScore'] >= v3_payload['rows'][1]['finalRotationScore']
    assert v3_payload['rows'][0]['rotation'] == v3_payload['rows'][0]['finalRotationScore']
    assert v3_payload['rows'][0]['score'] == v3_payload['rows'][0]['legacyDisplayScore']

    sector_rotation_route._cache.clear()
    v2_response = client.get('/api/sectors/breadth?version=v2')
    assert v2_response.status_code == 200
    assert isinstance(v2_response.get_json(), list)
    assert 'X-Sector-Rotation-Version' not in v2_response.headers


def test_api_sectors_breadth_v3_serves_published_snapshot_immutably_then_hits_memory(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(sector_rotation_route.bp)
    client = app.test_client()

    sector_rotation_route._cache.clear()
    monkeypatch.setattr(sector_rotation_route, 'get_latest_ltc_date_fast', lambda: date(2026, 7, 15))
    reads = {'count': 0}
    snapshot = {
        'version': 'v3',
        'modelVersion': 'SECTOR_ROTATION_V3',
        'benchmark': 'NIFTY500',
        'asOfDate': '2026-07-14',
        'generatedAt': '2026-07-14T18:00:00+00:00',
        'calculationDurationMs': 321.5,
        'runId': 'published-run-1',
        'isStale': False,
        'rows': [
            {
                'version': 'v3',
                'modelVersion': 'SECTOR_ROTATION_V3',
                'sectorCode': 'AUTO',
                'sectorName': 'Auto',
                'latestDataDate': '2026-07-14',
                'momentumScore': None,
                'finalRotationScore': None,
                'rotationBand': 'DATA_WEAK',
                'rotationPhase': 'DATA_WEAK',
                'relativeMomentum': 99,
                'riskAdjustment': 99,
            }
        ],
    }

    def read_snapshot(_as_of_date):
        reads['count'] += 1
        return snapshot

    monkeypatch.setattr(
        'services.sector_rotation_v3_repository.read_latest_published_v3_snapshot',
        read_snapshot,
    )
    monkeypatch.setattr(
        sector_rotation_route,
        'read_sector_rotation_snapshot',
        lambda _ltc_date: (_ for _ in ()).throw(AssertionError('legacy snapshot path must not run')),
    )

    first = client.get('/api/sectors/breadth?version=v3')
    second = client.get('/api/sectors/breadth?version=v3')

    assert first.status_code == 200
    assert second.status_code == 200
    first_payload = first.get_json()
    second_payload = second.get_json()
    assert first_payload['runId'] == 'published-run-1'
    assert first_payload['generatedAt'] == '2026-07-14T18:00:00+00:00'
    assert first_payload['calculationDurationMs'] == 321.5
    assert first_payload['isStale'] is True
    assert first_payload['rows'][0]['momentumScore'] is None
    assert first_payload['rows'][0]['finalRotationScore'] is None
    assert second_payload['rows'] == first_payload['rows']
    assert second_payload['cacheStatus'] == 'HIT'
    assert second.headers['X-Source'] == 'MEMORY_CACHE'
    assert reads['count'] == 1


def test_api_sector_refresh_v3_forces_reference_sync_and_publishes_snapshot(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(sector_rotation_route.bp)
    client = app.test_client()

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, *_args, **_kwargs):
            return None

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

        def commit(self):
            return None

        def rollback(self):
            return None

        def close(self):
            return None

    calls: list[bool] = []
    monkeypatch.setattr(sector_rotation_route, 'get_oracle_connection', lambda: FakeConnection())
    monkeypatch.setattr(sector_rotation_route, '_discover_sector_staging_tables', lambda force_refresh=False: [])
    monkeypatch.setattr(sector_rotation_route, 'get_latest_ltc_date_fast', lambda: date(2026, 7, 22))
    monkeypatch.setattr(
        'services.sector_rotation_v3_refresh_service.refresh_sector_rotation_v3_snapshot',
        lambda trade_date=None, force_reference_sync=False: calls.append(force_reference_sync) or {
            'ok': True,
            'runId': 'run-v3-current',
            'asOfDate': '2026-07-22',
            'rowCount': 31,
        },
    )

    response = client.post('/api/sectors/refresh?version=v3')

    assert response.status_code == 200
    payload = response.get_json()
    assert calls == [True]
    assert payload['ok'] is True
    assert payload['v3']['runId'] == 'run-v3-current'
    assert 'NSE_SECTOR_ROTATION_V3_SNAPSHOT' in payload['refreshed']


def test_api_sector_refresh_v3_failure_preserves_existing_cache(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(sector_rotation_route.bp)
    client = app.test_client()

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, *_args, **_kwargs):
            return None

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

        def commit(self):
            return None

        def rollback(self):
            return None

        def close(self):
            return None

    sector_rotation_route._cache.set('breadth', {'runId': 'last-complete'})
    monkeypatch.setattr(sector_rotation_route, 'get_oracle_connection', lambda: FakeConnection())
    monkeypatch.setattr(
        'services.sector_rotation_v3_refresh_service.refresh_sector_rotation_v3_snapshot',
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError('stock publication failed')),
    )

    response = client.post('/api/sectors/refresh?version=v3')

    assert response.status_code == 503
    assert response.get_json()['ok'] is False
    assert sector_rotation_route._cache.get('breadth') == {'runId': 'last-complete'}


def test_api_sectors_breadth_resupplements_memory_cache_counts(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(sector_rotation_route.bp)
    client = app.test_client()

    sector_rotation_route._cache.clear()
    monkeypatch.setattr(sector_rotation_route, 'get_latest_ltc_date_fast', lambda: date(2026, 6, 30))
    monkeypatch.setattr(sector_rotation_route, '_latest_raw_trading_date', lambda: date(2026, 6, 30))
    monkeypatch.setattr(sector_rotation_route, '_apply_breadth_engine_version', lambda rows, _version: rows)
    monkeypatch.setattr(
        sector_rotation_route,
        '_discover_sector_staging_tables',
        lambda force_refresh=False: [
            {
                'sectorCode': 'PSU_BANK',
                'sectorName': 'PSU Bank',
                'tableName': 'NSE_NIFTY_PSU_BANK_STAGING',
                'stockCount': 12,
            }
        ],
    )
    monkeypatch.setattr(
        sector_rotation_route,
        '_load_sector_rotation_summary_from_sector_tables',
        lambda force_refresh=False: {
            'PSU_BANK': {
                'sectorCode': 'PSU_BANK',
                'sectorName': 'PSU Bank',
                'totalSymbols': 1,
                'totalStocks': 1,
                'availableSymbols': 1,
                'breadthComposite': 0.25,
                'screenedStocks': 1,
            }
        },
    )
    monkeypatch.setattr(
        sector_rotation_route,
        'ensure_sector_reference_data_synced',
        lambda: (_ for _ in ()).throw(RuntimeError('memory cache should satisfy this request')),
    )

    cache_key = 'sector_rotation:breadth:2026-06-30:history:0'
    sector_rotation_route._cache.set(cache_key, [
        {'sectorCode': 'PSU_BANK', 'sectorName': 'PSU Bank', 'totalStocks': 1, 'totalSymbols': 1}
    ])

    response = client.get('/api/sectors/breadth?version=v2')
    assert response.status_code == 200
    assert response.headers.get('X-Source') == 'MEMORY_CACHE'

    payload = response.get_json()
    assert len(payload) == 1
    assert payload[0]['sectorCode'] == 'PSU_BANK'
    assert payload[0]['totalStocks'] == 12
    assert payload[0]['totalSymbols'] == 12


def test_api_sectors_overview_normal_read_does_not_rebuild_without_snapshot(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(sector_rotation_route.bp)
    client = app.test_client()

    sector_rotation_route._cache.clear()
    monkeypatch.setattr(sector_rotation_route, '_read_sector_overview_payload_snapshot', lambda latest_date: None)
    monkeypatch.setattr(
        sector_rotation_route,
        '_load_sector_overview_payload',
        lambda force_refresh=False: (_ for _ in ()).throw(AssertionError('normal overview read must not rebuild')),
    )

    response = client.get('/api/sectors/overview')

    assert response.status_code == 503
    assert response.get_json()['code'] == 'SECTOR_OVERVIEW_SNAPSHOT_UNAVAILABLE'


def test_api_sectors_overview_consolidates_sector_metrics(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(sector_rotation_route.bp)
    client = app.test_client()

    sector_rotation_route._cache.clear()
    monkeypatch.setattr(sector_rotation_route, '_read_sector_overview_payload_snapshot', lambda latest_date: None)
    monkeypatch.setattr(sector_rotation_route, '_write_sector_overview_payload_snapshot', lambda payload: None)
    monkeypatch.setattr(sector_rotation_route, 'ensure_sector_reference_data_synced', lambda force=False: True)
    monkeypatch.setattr(
        sector_rotation_route,
        '_load_sector_overview_sector_tables',
        lambda force_refresh=False: [
            {'sectorCode': 'AUTO', 'sectorName': 'Auto Mobile'},
            {'sectorCode': 'IT', 'sectorName': 'IT'},
        ],
    )
    monkeypatch.setattr(sector_rotation_route, '_collapse_sector_entries_for_unique_ui', lambda entries: entries)
    monkeypatch.setattr(
        sector_rotation_route,
        '_load_strict_sector_symbols',
        lambda sector_code: {
            'AUTO': ['AUTO1', 'AUTO2', 'AUTO3'],
            'IT': ['IT1', 'IT2', 'IT3'],
        }.get(sector_code, []),
    )
    monkeypatch.setattr(
        sector_rotation_route,
        '_load_sector_overview_symbols',
        lambda sector_codes: ['AUTO1', 'AUTO2', 'AUTO3', 'IT1', 'IT2', 'IT3'],
    )
    monkeypatch.setattr(sector_rotation_route, 'get_latest_ltc_date_fast', lambda: date(2026, 6, 28))
    monkeypatch.setattr(
        sector_rotation_route,
        '_load_sector_overview_trendline_snapshot_rows',
        lambda symbols, latest_ltc_date: ({
            'AUTO1': {
                'stock': 'AUTO1',
                'ltcDate': '2026-06-28',
                'price': 100.0,
                'ath': 100.0,
                'high52w': 100.0,
                'low52w': 75.0,
                'ema20': 95.0,
                'ema50': 90.0,
                'ema100': 85.0,
                'ema200': 80.0,
            },
            'AUTO2': {
                'stock': 'AUTO2',
                'ltcDate': '2026-06-28',
                'price': 101.0,
                'ath': 120.0,
                'high52w': 115.0,
                'low52w': 85.0,
                'ema20': 101.0,
                'ema50': 101.0,
                'ema100': 101.0,
                'ema200': 101.0,
            },
            'IT1': {
                'stock': 'IT1',
                'ltcDate': '2026-06-28',
                'price': 102.0,
                'ath': 118.0,
                'high52w': 114.0,
                'low52w': 84.0,
                'ema20': 104.0,
                'ema50': 94.0,
                'ema100': 90.0,
                'ema200': 86.0,
            },
            'IT2': {
                'stock': 'IT2',
                'ltcDate': '2026-06-28',
                'price': 103.0,
                'ath': 103.0,
                'high52w': 103.0,
                'low52w': 88.0,
                'ema20': 99.0,
                'ema50': 96.0,
                'ema100': 93.0,
                'ema200': 90.0,
            },
            'IT3': {
                'stock': 'IT3',
                'ltcDate': '2026-06-28',
                'price': 80.0,
                'ath': 110.0,
                'high52w': 105.0,
                'low52w': 74.0,
                'ema20': 90.0,
                'ema50': 95.0,
                'ema100': 100.0,
                'ema200': 105.0,
            },
        }, '2026-06-28', True),
    )
    monkeypatch.setattr(
        sector_rotation_route,
        '_load_sector_overview_trend_snapshot_rows',
        lambda symbols: {},
    )
    monkeypatch.setattr(
        sector_rotation_route,
        '_load_sector_overview_latest_trade_rows',
        lambda symbols, as_of_date: {
            symbol: {
                'latestDate': date(2026, 6, 28),
                'latestClose': price,
            }
            for symbol, price in {
                'AUTO1': 100.0,
                'AUTO2': 101.0,
                'IT1': 102.0,
                'IT2': 103.0,
                'IT3': 80.0,
            }.items()
        },
    )
    monkeypatch.setattr(sector_rotation_route, '_load_sector_overview_raw_fallback_rows', lambda symbols: {})
    sector_rotation_route._sector_wise_trend_cache.clear()
    sector_rotation_route._sector_wise_trend_cache.set(
        sector_rotation_route._SECTOR_WISE_TREND_CACHE_KEY,
        {
            'AUTO1': {'trendDirection': 'Strong Up Trend'},
            'AUTO2': {'trendDirection': 'Sideways'},
            'AUTO3': {'trendDirection': 'No Historical Data'},
            'IT1': {'trendDirection': 'Pullback Uptrend'},
        },
    )
    monkeypatch.setattr(
        sector_rotation_route,
        '_load_sector_wise_trend_map',
        lambda force_refresh=False: (_ for _ in ()).throw(AssertionError('overview refresh must not rebuild the trend map')),
    )

    response = client.get('/api/sectors/overview?refresh=1')
    assert response.status_code == 200
    payload = response.get_json()

    assert payload['total_sectors'] == 2
    assert payload['total_stocks'] == 6
    assert payload['ltc_date'] == '28-06-2026'
    assert payload['ltc_date_count'] == 1
    assert payload['ltc_date_consistent'] is True
    assert payload['trend_counts']['Strong Uptrend'] == 2
    assert payload['trend_counts']['Sideway'] == 1
    assert payload['trend_counts']['Downtrend'] == 1
    assert payload['trend_counts']['Pullback in Uptrend'] == 1
    assert payload['trend_counts']['Unknown / Insufficient Data'] == 1
    assert 'Insufficient' not in payload['trend_counts']
    assert 'Consolidation' not in payload['trend_counts']
    assert payload['dynamic_trend_counts'] == {}
    assert payload['sector_data_source'] == 'TRENDLINE_SNAPSHOT+RAW_DATA_DEV_LATEST+TREND_CACHE'
    assert payload['is_stale'] is False
    assert payload['rows'] == [
        {'stock': 'AUTO1', 'ltc_date': '28-06-2026', 'price': 100.0, 'trend': 'Strong Uptrend'},
        {'stock': 'AUTO2', 'ltc_date': '28-06-2026', 'price': 101.0, 'trend': 'Sideway'},
        {'stock': 'AUTO3', 'ltc_date': '', 'price': None, 'trend': 'Unknown / Insufficient Data'},
        {'stock': 'IT1', 'ltc_date': '28-06-2026', 'price': 102.0, 'trend': 'Pullback in Uptrend'},
        {'stock': 'IT2', 'ltc_date': '28-06-2026', 'price': 103.0, 'trend': 'Strong Uptrend'},
        {'stock': 'IT3', 'ltc_date': '28-06-2026', 'price': 80.0, 'trend': 'Downtrend'},
    ]


def test_sector_overview_uses_discovery_snapshot_without_live_table_counts(monkeypatch):
    snapshot_tables = [{'sectorCode': 'AUTO', 'sectorName': 'Auto Mobile'}]
    monkeypatch.setattr(
        sector_rotation_route,
        '_read_snapshot_from_disk',
        lambda: {'tables': snapshot_tables},
    )
    monkeypatch.setattr(
        sector_rotation_route,
        '_normalize_sector_table_entries',
        lambda entries: entries,
    )
    monkeypatch.setattr(
        sector_rotation_route,
        '_discover_sector_staging_tables',
        lambda force_refresh=False: (_ for _ in ()).throw(AssertionError('live discovery must not run')),
    )

    assert sector_rotation_route._load_sector_overview_sector_tables() == snapshot_tables


def test_sector_overview_refresh_uses_metadata_without_staging_table_counts(monkeypatch):
    monkeypatch.setattr(
        sector_rotation_route,
        '_query_rows',
        lambda sql: [{'tableName': 'NSE_NIFTY_AUTO_MOBILE_STAGING'}],
    )
    monkeypatch.setattr(
        sector_rotation_route,
        '_discover_sector_staging_tables',
        lambda force_refresh=False: (_ for _ in ()).throw(AssertionError('overview refresh must not count every staging table')),
    )

    tables = sector_rotation_route._load_sector_overview_sector_tables(force_refresh=True)

    assert tables[0]['tableName'] == 'NSE_NIFTY_AUTO_MOBILE_STAGING'
    assert tables[0]['sectorCode'] == 'AUTO_MOBILE'


def test_sector_overview_fast_path_preserves_snapshot_trade_and_trend(monkeypatch):
    sector_rotation_route._sector_wise_trend_cache.clear()
    monkeypatch.setattr(
        sector_rotation_route,
        '_load_sector_overview_sector_tables',
        lambda force_refresh=False: [{'sectorCode': 'AUTO', 'sectorName': 'Auto Mobile'}],
    )
    monkeypatch.setattr(sector_rotation_route, '_collapse_sector_entries_for_unique_ui', lambda entries: entries)
    monkeypatch.setattr(sector_rotation_route, '_load_sector_overview_symbols', lambda sector_codes: ['AUTO1'])
    monkeypatch.setattr(
        sector_rotation_route,
        '_load_sector_overview_trendline_snapshot_rows',
        lambda symbols, latest_ltc_date: ({
            'AUTO1': {
                'symbol': 'AUTO1',
                'ltcDate': '2026-07-09',
                'price': 100.0,
                'trendDirection': 'UPTREND',
            },
        }, '2026-07-09', False),
    )
    monkeypatch.setattr(sector_rotation_route, '_load_sector_overview_trend_snapshot_rows', lambda symbols: {})
    monkeypatch.setattr(
        sector_rotation_route,
        '_load_sector_overview_latest_trade_rows',
        lambda symbols, latest_ltc_date: (_ for _ in ()).throw(AssertionError('fast path must not query latest trades')),
    )
    monkeypatch.setattr(
        sector_rotation_route,
        '_load_sector_overview_raw_fallback_rows',
        lambda symbols: (_ for _ in ()).throw(AssertionError('fast path must not run raw fallback')),
    )

    payload = sector_rotation_route._load_sector_overview_payload(force_refresh=False)

    assert payload['ltc_date'] == '09-07-2026'
    assert payload['trend_counts']['Uptrend'] == 1
    assert payload['trend_counts']['Unknown / Insufficient Data'] == 0
    assert payload['rows'] == [
        {'stock': 'AUTO1', 'ltc_date': '09-07-2026', 'price': 100.0, 'trend': 'Uptrend'},
    ]
    assert payload['is_stale'] is True


def test_api_sector_overview_returns_payload_snapshot_before_oracle(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(sector_rotation_route.bp)
    client = app.test_client()
    sector_rotation_route._cache.clear()

    snapshot_payload = {
        'status': 'success',
        'success': True,
        'total_sectors': 1,
        'total_stocks': 1,
        'ltc_date': '21-07-2026',
        'trend_counts': {},
        'dynamic_trend_counts': {},
        'rows': [{'stock': 'AUTO1', 'ltc_date': '21-07-2026', 'price': 100.0, 'trend': 'Uptrend'}],
        'sector_data_source': 'SNAPSHOT',
        'is_stale': False,
        'source_dev_ltc_date': '2026-07-21',
    }
    monkeypatch.setattr(
        sector_rotation_route,
        '_read_sector_overview_payload_snapshot',
        lambda latest_date: snapshot_payload,
    )
    monkeypatch.setattr(
        sector_rotation_route,
        'get_latest_ltc_date_fast',
        lambda: (_ for _ in ()).throw(AssertionError('Oracle date lookup must not run')),
    )

    response = client.get('/api/sectors/overview')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['cache_status'] == 'SNAPSHOT_HIT'
    assert payload['rows'] == snapshot_payload['rows']
    assert int(response.headers['X-Response-Time-Ms']) < 1000


def test_sector_overview_fills_snapshot_gap_from_sector_wise_dev_fallback(monkeypatch):
    monkeypatch.setattr(sector_rotation_route, '_load_sector_overview_sector_tables', lambda force_refresh=False: [{'sectorCode': 'AUTO'}])
    monkeypatch.setattr(sector_rotation_route, '_collapse_sector_entries_for_unique_ui', lambda entries: entries)
    monkeypatch.setattr(sector_rotation_route, '_load_sector_overview_symbols', lambda sector_codes: ['AUTO1', 'AUTO2'])
    monkeypatch.setattr(sector_rotation_route, 'get_latest_ltc_date_fast', lambda: date(2026, 6, 28))
    monkeypatch.setattr(sector_rotation_route, '_load_sector_overview_trendline_snapshot_rows', lambda symbols, latest_ltc_date: ({'AUTO1': {'stock': 'AUTO1', 'ltcDate': '2026-06-28', 'price': 100.0, 'ath': 100.0, 'high52w': 100.0, 'low52w': 75.0, 'ema20': 95.0, 'ema50': 90.0, 'ema100': 85.0, 'ema200': 80.0}}, '2026-06-28', True))
    monkeypatch.setattr(sector_rotation_route, '_load_sector_overview_trend_snapshot_rows', lambda symbols: {})
    monkeypatch.setattr(
        sector_rotation_route,
        '_load_sector_overview_latest_trade_rows',
        lambda symbols, as_of_date: {
            'AUTO1': {'latestDate': date(2026, 6, 28), 'latestClose': 100.0},
            'AUTO2': {'latestDate': date(2026, 6, 28), 'latestClose': 101.0},
        },
    )
    monkeypatch.setattr(sector_rotation_route, '_load_sector_overview_raw_fallback_rows', lambda symbols: {'AUTO2': {'stock': 'AUTO2', 'ltcDate': '2026-06-28', 'price': 101.0, 'trendDirection': 'Downtrend', 'ath': 120.0, 'high52w': 115.0, 'low52w': 85.0, 'ema20': 110.0, 'ema50': 105.0, 'ema100': 100.0, 'ema200': 95.0}} if symbols == ['AUTO2'] else {})
    monkeypatch.setattr(sector_rotation_route, '_load_sector_wise_trend_map', lambda force_refresh=False: {})

    payload = sector_rotation_route._load_sector_overview_payload(force_refresh=True)

    assert payload['trend_counts']['Downtrend'] == 1
    assert payload['trend_counts']['Unknown / Insufficient Data'] == 0
    assert payload['sector_data_source'] == 'TRENDLINE_SNAPSHOT+RAW_DATA_DEV_TREND_FALLBACK+RAW_DATA_DEV_LATEST'
    assert payload['rows'][1] == {'stock': 'AUTO2', 'ltc_date': '28-06-2026', 'price': 101.0, 'trend': 'Downtrend'}


def test_sector_rows_dedupe_obsolete_and_current_symbols():
    rows = sector_rotation_route._dedupe_canonical_sector_rows([
        {'stock': 'SCHLOSS', 'price': None, 'trend': 'Unknown / Insufficient Data'},
        {'stock': 'THELEELA', 'price': 455.0, 'trend': 'Uptrend'},
        {'stock': 'NSE:AIMTRON-SM', 'price': 100.0},
        {'stock': 'AIMTRON', 'price': 100.0},
    ])

    assert [row['stock'] for row in rows] == ['THELEELA', 'AIMTRON']
    assert rows[0]['price'] == 455.0


def test_symbol_variants_include_every_cash_series_and_canonical_alias():
    variants = sector_rotation_route._symbol_variants(['APTECHT', 'SSEGL', 'CELLECOR', 'CHEMFAB', 'ECOSMOBLTY', 'LTIM'])

    assert 'APTECHT-BE' in variants
    assert 'SSEGL-SM' in variants
    assert 'CELLECOR-ST' in variants
    assert 'CHEMFAB-BE' in variants
    assert 'ECOSMOBLTY-BE' in variants
    assert 'JBCHEPHARM-BE' in sector_rotation_route._symbol_variants(['JBCHEPHARM'])
    assert 'LTM-EQ' in variants
    assert 'NSE:LTM-BE' in variants


def test_sector_overview_uses_latest_dev_date_and_price_per_symbol(monkeypatch):
    monkeypatch.setattr(sector_rotation_route, '_load_sector_overview_sector_tables', lambda force_refresh=False: [{'sectorCode': 'AUTO'}])
    monkeypatch.setattr(sector_rotation_route, '_collapse_sector_entries_for_unique_ui', lambda entries: entries)
    monkeypatch.setattr(sector_rotation_route, '_load_sector_overview_symbols', lambda sector_codes: ['AUTO1'])
    monkeypatch.setattr(sector_rotation_route, 'get_latest_ltc_date_fast', lambda: date(2026, 7, 20))
    monkeypatch.setattr(sector_rotation_route, '_load_sector_overview_trendline_snapshot_rows', lambda symbols, latest_ltc_date: ({'AUTO1': {'stock': 'AUTO1', 'ltcDate': '2026-07-09', 'price': 90.0, 'ema20': 85.0}}, '2026-07-09', False))
    monkeypatch.setattr(sector_rotation_route, '_load_sector_overview_trend_snapshot_rows', lambda symbols: {})
    monkeypatch.setattr(sector_rotation_route, '_load_sector_overview_latest_trade_rows', lambda symbols, as_of_date: {'AUTO1': {'latestDate': date(2026, 7, 20), 'latestClose': 101.0}})
    monkeypatch.setattr(sector_rotation_route, '_load_sector_overview_raw_fallback_rows', lambda symbols: {})
    monkeypatch.setattr(sector_rotation_route, '_load_sector_wise_trend_map', lambda force_refresh=False: {})

    payload = sector_rotation_route._load_sector_overview_payload(force_refresh=True)

    assert payload['ltc_date'] == '20-07-2026'
    assert payload['ltc_date_scope'] == 'LATEST_PER_SYMBOL'
    assert payload['rows'][0]['ltc_date'] == '20-07-2026'
    assert payload['rows'][0]['price'] == 101.0


def test_sector_overview_latest_trade_rows_backfill_symbols_missing_on_global_date(monkeypatch):
    class FakeCursor:
        description = [('stock',), ('latestDate',), ('latestClose',)]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, *_args, **_kwargs):
            return None

        def fetchall(self):
            return [('CHEMFAB-BE', date(2026, 7, 21), 364.05)]

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

        def close(self):
            return None

    monkeypatch.setattr(sector_rotation_route, '_raw_sma_source', lambda: ('RAW_DEV', 'CLOSE_PRICE'))
    monkeypatch.setattr(sector_rotation_route, 'get_oracle_connection', lambda: FakeConnection())
    monkeypatch.setattr(
        sector_rotation_route,
        '_load_sector_wise_raw_latest_trade_rows',
        lambda symbols, as_of_date: {
            'JBCHEPHARM': {'latestDate': date(2026, 7, 16), 'latestClose': 2408.9}
        } if symbols == ['JBCHEPHARM'] and as_of_date == date(2026, 7, 21) else {},
    )

    rows = sector_rotation_route._load_sector_overview_latest_trade_rows(
        ['CHEMFAB', 'JBCHEPHARM'],
        date(2026, 7, 21),
    )

    assert rows['CHEMFAB']['latestDate'] == date(2026, 7, 21)
    assert rows['JBCHEPHARM'] == {'latestDate': date(2026, 7, 16), 'latestClose': 2408.9}


def test_resolve_sector_overview_trend_promotes_near_high_bullish_stack_to_strong_uptrend():
    trend = sector_rotation_route._resolve_sector_overview_trend(
        symbol='AUTO4',
        latest_meta={'latestClose': 118.5, 'latestDate': '2026-06-29'},
        trend_meta=None,
        extrema_meta={
            'ath': 120.0,
            'high52w': 119.25,
            'low52w': 82.0,
            'adx14': 28.0,
            'rsi': 66.0,
        },
        ema_meta={
            'ema20': 112.0,
            'ema50': 107.0,
            'ema100': 101.0,
            'ema200': 94.0,
        },
    )

    assert trend == 'Strong Uptrend'


def test_resolve_sector_overview_trend_keeps_weak_near_high_rows_as_uptrend():
    trend = sector_rotation_route._resolve_sector_overview_trend(
        symbol='AUTO5',
        latest_meta={'latestClose': 118.5, 'latestDate': '2026-06-29'},
        trend_meta=None,
        extrema_meta={
            'ath': 120.0,
            'high52w': 119.25,
            'low52w': 82.0,
            'adx14': 14.0,
            'rsi': 66.0,
        },
        ema_meta={
            'ema20': 112.0,
            'ema50': 107.0,
            'ema100': 101.0,
            'ema200': 94.0,
        },
    )

    assert trend == 'Uptrend'
