import datetime as dt
import io
import json
import sys
import threading
import time
import types
import zipfile
from http.cookiejar import Cookie
from pathlib import Path
from urllib.error import HTTPError

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
SERVICES_ROOT = BACKEND_ROOT / 'services'
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(SERVICES_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICES_ROOT))

sys.modules.setdefault(
    'db_pool',
    types.SimpleNamespace(pool=types.SimpleNamespace(acquire=lambda: None)),
)

import services.nse_mcap_service as service


class _FakeConnection:
    def close(self):
        return None


def _test_cookie(value: str) -> Cookie:
    return Cookie(
        version=0,
        name='nse-token',
        value=value,
        port=None,
        port_specified=False,
        domain='www.nseindia.com',
        domain_specified=True,
        domain_initial_dot=False,
        path='/',
        path_specified=True,
        secure=False,
        expires=None,
        discard=True,
        comment=None,
        comment_url=None,
        rest={},
        rfc2109=False,
    )


def test_latest_row_metadata_adds_date_only_fetched_timestamp():
    rows = service._apply_latest_row_insertion_metadata([
        {
            'symbol': 'ABC',
            'fetch_ts': '2026-05-29 00:00:00',
            'source_name': 'NSE_MCAP_FILE',
            'fetch_status': 'SUCCESS',
            'inserted_rows': 1,
        },
        {
            'symbol': 'XYZ',
            'trade_date': dt.date(2026, 5, 30),
            'source_name': 'NSE_MCAP_FILE',
            'fetch_status': 'SUCCESS',
            'inserted_rows': 1,
        },
    ])

    assert rows[0]['fetched_timestamp'] == '29-05-2026'
    assert rows[0]['fetchedTimestamp'] == '29-05-2026'
    assert rows[0]['fetch_ts'] == '2026-05-29 00:00:00'
    assert rows[1]['fetched_timestamp'] == '30-05-2026'


def test_market_calendar_verification_splits_historical_and_future_dates():
    verification = service.market_calendar.get_trading_day_verification(
        2026,
        [
            dt.date(2026, 1, 1),
            dt.date(2026, 1, 1),
            dt.date(2026, 1, 2),
            dt.date(2026, 1, 3),
            dt.date(2026, 1, 15),
            dt.date(2026, 1, 26),
            dt.date(2026, 2, 1),
        ],
        current_date=dt.date(2026, 1, 2),
    )

    assert dt.date(2026, 1, 3) not in verification['trading_dates']
    assert dt.date(2026, 1, 15) not in verification['trading_dates']
    assert service.market_calendar.is_nse_holiday(dt.date(2026, 1, 15)) is True
    assert dt.date(2026, 1, 26) not in verification['trading_dates']
    assert dt.date(2026, 2, 1) in verification['trading_dates']
    assert service.market_calendar.is_nse_holiday(dt.date(2026, 11, 10)) is False
    assert service.market_calendar.is_nse_holiday(dt.date(2026, 11, 11)) is True
    assert dt.date(2026, 1, 15) in verification['invalid_non_trading_dates']
    assert verification['trading_days_cy'] == verification['calendar_days'] - verification['non_trading_days']
    assert verification['trading_days_available_in_table'] == 3
    assert verification['trading_days_missing_count'] == 0
    assert verification['future_pending_count'] > 0
    assert verification['verification_status'] == 'FUTURE_PENDING'


def test_build_trading_day_verification_uses_distinct_table_dates():
    executed = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, binds=None):
            executed.append((sql, binds))

        def fetchall(self):
            return [
                (dt.date(2026, 1, 1),),
                (dt.datetime(2026, 1, 2, 10, 30),),
                (dt.date(2026, 1, 2),),
            ]

    class FakeConn:
        def cursor(self):
            return FakeCursor()

    payload = service.build_trading_day_verification(
        FakeConn(),
        service._TABLE_SQL,
        'Market Cap',
        year=2026,
        as_of_date=dt.date(2026, 1, 2),
    )

    assert payload['status'] == 'SUCCESS'
    assert payload['page'] == 'Market Cap'
    assert payload['S_NO'] == 1
    assert payload['TDAPT'] == 2
    assert payload['TDMD'] == 0
    assert payload['verification_status'] == 'FUTURE_PENDING'
    assert payload['trading_dates_present'] == ['2026-01-01', '2026-01-02']
    assert payload['rows'][0]['tdmdDatesText'] == '-'
    normalized_sql = ' '.join(executed[0][0].split())
    assert 'SELECT DISTINCT TRADE_DATE' in normalized_sql
    assert 'ORDER BY TRADE_DATE' in normalized_sql
    assert 'TRUNC(TRADE_DATE)' not in normalized_sql
    assert executed[0][1]['start_date'] == dt.date(2026, 1, 1)
    assert executed[0][1]['end_date'] == dt.date(2027, 1, 1)


def test_build_trading_day_verification_marks_empty_table_missing():
    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, binds=None):
            return None

        def fetchall(self):
            return []

    class FakeConn:
        def cursor(self):
            return FakeCursor()

    payload = service.build_trading_day_verification(
        FakeConn(),
        service._TABLE_SQL,
        'Market Cap',
        year=2026,
        as_of_date=dt.date(2026, 1, 2),
    )

    assert payload['verification_status'] == 'MISSING'
    assert payload['TDAPT'] == 0
    assert payload['TDMD'] == 2
    assert payload['missing_trading_dates'] == ['2026-01-01', '2026-01-02']


def test_get_trading_day_verification_does_not_run_runtime_init(monkeypatch):
    monkeypatch.setattr(service, '_acquire_connection', lambda: _FakeConnection())
    monkeypatch.setattr(
        service,
        'ensure_runtime',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError('verification must stay read-only')),
    )
    monkeypatch.setattr(
        service,
        'build_trading_day_verification',
        lambda conn, table_sql, page_name, year=None, as_of_date=None: {
            'ok': True,
            'page': page_name,
            'year': year,
        },
    )

    payload = service.get_trading_day_verification(year=2026)

    assert payload == {'ok': True, 'page': 'Market Cap', 'year': 2026}


def test_assign_missing_record_ids_when_table_has_no_identity():
    service._TABLE_ID_GENERATION_CACHE.clear()
    executed_sql = []

    class FakeCursor:
        def __init__(self):
            self._row = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, binds=None):
            executed_sql.append((sql, binds))
            if 'FROM user_tab_columns' in sql:
                self._row = (None, 'NO')
                return
            if 'FROM user_triggers' in sql:
                self._row = None
                return
            if sql.startswith('LOCK TABLE'):
                self._row = None
                return
            if 'SELECT NVL(MAX(ID), 0)' in sql:
                self._row = (41,)
                return
            raise AssertionError(f'Unexpected SQL: {sql}')

        def fetchone(self):
            return self._row

    class FakeConn:
        def cursor(self):
            return FakeCursor()

    records = [{'symbol': 'ABC'}, {'symbol': 'XYZ', 'id': 99}]

    changed = service._assign_missing_record_ids(FakeConn(), service._TABLE_SQL, records)

    assert changed is True
    assert records[0]['id'] == 42
    assert records[1]['id'] == 99
    assert any(sql.startswith('LOCK TABLE') for sql, _binds in executed_sql)


def test_download_mcap_csv_reuses_local_csv(monkeypatch, tmp_path):
    trade_date = dt.date(2026, 3, 2)
    csv_path = tmp_path / 'mcap02032026.csv'
    csv_path.write_text('SYMBOL,MARKETCAPRS\nABC,100\n', encoding='utf-8')

    monkeypatch.setattr(service, '_DOWNLOAD_DIR', tmp_path)
    monkeypatch.setattr(service, 'ensure_runtime', lambda *args, **kwargs: None)

    class UnexpectedClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError('network client should not be created when local csv exists')

    monkeypatch.setattr(service, '_HttpClient', UnexpectedClient)

    result = service.download_mcap_csv(trade_date)

    assert result == csv_path


def test_download_mcap_csv_reuses_local_zip(monkeypatch, tmp_path):
    trade_date = dt.date(2026, 3, 2)
    zip_path = tmp_path / 'PR020326.zip'
    with zipfile.ZipFile(zip_path, 'w') as archive:
        archive.writestr('mcap02032026.csv', 'SYMBOL,MARKETCAPRS\nABC,100\n')

    monkeypatch.setattr(service, '_DOWNLOAD_DIR', tmp_path)
    monkeypatch.setattr(service, 'ensure_runtime', lambda *args, **kwargs: None)

    class UnexpectedClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError('network client should not be created when local zip exists')

    monkeypatch.setattr(service, '_HttpClient', UnexpectedClient)

    result = service.download_mcap_csv(trade_date)

    assert result == tmp_path / 'mcap02032026.csv'
    assert result.read_text(encoding='utf-8') == 'SYMBOL,MARKETCAPRS\nABC,100\n'


def test_candidate_specs_prefers_cached_candidate(monkeypatch, tmp_path):
    trade_date = dt.date(2026, 3, 2)
    cache_path = tmp_path / service._DOWNLOAD_HINTS_FILE
    cache_path.write_text(json.dumps({'preferredCandidate': 'historical_mcap_upper'}), encoding='utf-8')

    monkeypatch.setattr(service, '_DOWNLOAD_DIR', tmp_path)

    specs = service._candidate_specs(trade_date)

    assert specs[0][0] == 'historical_mcap_upper'
    assert [key for key, _url in specs] == ['historical_mcap_upper', 'historical_mcap_lower']


def test_download_mcap_csv_uses_discovered_url_after_static_candidates_fail(monkeypatch, tmp_path):
    trade_date = dt.date(2026, 3, 2)
    attempts = []

    monkeypatch.setattr(service, '_DOWNLOAD_DIR', tmp_path)
    monkeypatch.setattr(service, 'ensure_runtime', lambda *args, **kwargs: None)
    monkeypatch.setattr(service, '_candidate_specs', lambda *_args, **_kwargs: [('stale_candidate', 'https://example.com/stale.zip')])
    monkeypatch.setattr(service, '_archive_candidate_specs', lambda *_args, **_kwargs: [])
    monkeypatch.setattr(service, '_discover_urls', lambda *_args, **_kwargs: ['https://example.com/live.csv'])

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def read(self, url, accept):
            attempts.append(url)
            if url.endswith('live.csv'):
                return (b'SYMBOL,MARKETCAPRS\nABC,100\n', {'Content-Type': 'text/csv'})
            raise HTTPError(url, 404, 'Not Found', hdrs=None, fp=None)

    monkeypatch.setattr(service, '_HttpClient', FakeClient)

    result = service.download_mcap_csv(trade_date)

    assert attempts == ['https://example.com/stale.zip', 'https://example.com/live.csv']
    assert result.read_text(encoding='utf-8') == 'SYMBOL,MARKETCAPRS\nABC,100\n'
    assert json.loads((tmp_path / service._DOWNLOAD_HINTS_FILE).read_text(encoding='utf-8'))['lastSuccessUrl'] == 'https://example.com/live.csv'


def test_hinted_candidate_specs_rebuilds_current_trade_date_url(monkeypatch, tmp_path):
    trade_date = dt.date(2026, 4, 1)
    cache_path = tmp_path / service._DOWNLOAD_HINTS_FILE
    cache_path.write_text(
        json.dumps({'lastSuccessUrl': 'https://nsearchives.nseindia.com/content/historical/EQUITIES/2026/MAR/mcap30032026.csv'}),
        encoding='utf-8',
    )

    monkeypatch.setattr(service, '_DOWNLOAD_DIR', tmp_path)

    specs = service._hinted_candidate_specs(trade_date)

    assert specs == [
        ('hint_last_success', 'https://nsearchives.nseindia.com/content/historical/EQUITIES/2026/APR/mcap01042026.csv')
    ]


def test_enrich_quotes_does_not_return_local_download_path(monkeypatch, tmp_path):
    trade_date = dt.date(2026, 3, 2)
    upserts = []

    monkeypatch.setattr(service, 'ensure_runtime', lambda *args, **kwargs: None)
    monkeypatch.setattr(service, '_reuse_local_download', lambda *args, **kwargs: tmp_path / 'mcap02032026.csv')
    monkeypatch.setattr(service, '_symbols_for_enrichment', lambda *_args, **_kwargs: ['ABC'])
    monkeypatch.setattr(service, '_upsert_records', lambda records: (upserts.extend(records) or (len(records), 0)))

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def read_json(self, url):
            return {'marketCap': '100 Cr', 'ffmc': '80 Cr'}

    monkeypatch.setattr(service, '_HttpClient', FakeClient)

    result = service.enrich_quotes(trade_date)

    assert result['successCount'] == 1
    assert upserts[0]['symbol'] == 'ABC'


def test_trade_date_from_mcap_csv_parses_filename():
    assert service._trade_date_from_mcap_csv(Path('mcap23042026.csv')) == dt.date(2026, 4, 23)
    assert service._trade_date_from_mcap_csv(Path('something_else.csv')) is None


def test_process_existing_csv_for_symbols_api_forwards_to_shared_service(monkeypatch, tmp_path):
    monkeypatch.setattr(service, '_DOWNLOAD_DIR', tmp_path)
    captured = {}

    def fake_process(symbols_input, config, **kwargs):
        captured['symbols_input'] = symbols_input
        captured['config'] = config
        captured['kwargs'] = kwargs
        return {'ok': True, 'status': 'success', 'dataset_type': 'market_cap'}

    monkeypatch.setattr(service.existing_csv_svc, 'process_existing_csv_for_symbols', fake_process)

    result = service.process_existing_csv_for_symbols_api({'symbols': 'ITC,RELIANCE'})

    assert result['ok'] is True
    assert captured['symbols_input'] == 'ITC,RELIANCE'
    assert captured['config'].dataset_type == 'market_cap'
    assert captured['config'].download_dir == tmp_path


def test_run_pipeline_single_marks_failed_insert_when_no_rows_written(monkeypatch, tmp_path):
    trade_date = dt.date(2026, 3, 30)
    csv_path = tmp_path / 'mcap30032026.csv'
    enrich_called = {'value': False}

    monkeypatch.setattr(service, 'download_mcap_csv', lambda *args, **kwargs: csv_path)
    monkeypatch.setattr(service, 'inspect_mcap_csv', lambda *args, **kwargs: {'matchedRows': 2, 'matchedSymbolsCount': 2})
    monkeypatch.setattr(
        service,
        'load_mcap_csv',
        lambda *args, **kwargs: {'inputRows': 2, 'loadedCount': 0, 'failureCount': 2, 'skippedCount': 0, 'universeSkippedCount': 0},
    )
    monkeypatch.setattr(
        service,
        'enrich_quotes',
        lambda *args, **kwargs: enrich_called.update({'value': True}) or {'requested': 0, 'processed': 0, 'successCount': 0, 'failureCount': 0, 'skippedCount': 0, 'elapsedSec': 0.0},
    )

    result = service._run_pipeline_single(trade_date, True, None, [], {'ABC'})

    assert result['ok'] is False
    assert 'failed during oracle insert' in result['message'].lower()
    assert enrich_called['value'] is False


def test_run_pipeline_single_reuses_existing_file_rows_for_quote_enrichment(monkeypatch):
    trade_date = dt.date(2026, 3, 30)
    captured = {'called': False}

    monkeypatch.setattr(service, 'download_mcap_csv', lambda *args, **kwargs: Path('C:/temp/mcap30032026.csv'))
    monkeypatch.setattr(service, 'inspect_mcap_csv', lambda *args, **kwargs: {'matchedRows': 10, 'matchedSymbolsCount': 1, 'alreadyLoaded': False})
    monkeypatch.setattr(
        service,
        'load_mcap_csv',
        lambda *args, **kwargs: {'inputRows': 10, 'loadedCount': 10, 'failureCount': 0, 'skippedCount': 0, 'universeSkippedCount': 0, 'alreadyLoaded': True, 'alreadyLoadedCount': 10},
    )
    monkeypatch.setattr(
        service,
        'enrich_quotes',
        lambda *args, **kwargs: captured.update({'called': True}) or {'requested': 1, 'processed': 1, 'successCount': 1, 'failureCount': 0, 'skippedCount': 0, 'elapsedSec': 0.2},
    )
    monkeypatch.setattr(service, 'get_dashboard', lambda *_args, **_kwargs: {'summary': {'quoteRows': 1}})

    result = service._run_pipeline_single(trade_date, True, None, ['ABC'], {'ABC'})

    assert result['ok'] is True
    assert result['load']['alreadyLoaded'] is True
    assert result['summary']['quoteRows'] == 1
    assert captured['called'] is True


def test_run_pipeline_single_keeps_file_insert_success_when_quote_unavailable(monkeypatch):
    trade_date = dt.date(2026, 3, 30)

    monkeypatch.setattr(service, 'download_mcap_csv', lambda *args, **kwargs: Path('C:/temp/mcap30032026.csv'))
    monkeypatch.setattr(service, 'inspect_mcap_csv', lambda *args, **kwargs: {'matchedRows': 10, 'matchedSymbolsCount': 1, 'alreadyLoaded': False})
    monkeypatch.setattr(
        service,
        'load_mcap_csv',
        lambda *args, **kwargs: {'inputRows': 10, 'loadedCount': 10, 'failureCount': 0, 'skippedCount': 0, 'universeSkippedCount': 0, 'alreadyLoaded': False, 'alreadyLoadedCount': 0},
    )
    monkeypatch.setattr(
        service,
        'enrich_quotes',
        lambda *args, **kwargs: {'requested': 1, 'processed': 1, 'successCount': 0, 'failureCount': 1, 'skippedCount': 0, 'elapsedSec': 0.2},
    )
    monkeypatch.setattr(service, 'get_dashboard', lambda *_args, **_kwargs: {'summary': {'fileRows': 1, 'successRows': 1, 'failureRows': 0}})

    result = service._run_pipeline_single(trade_date, True, None, ['ABC'], {'ABC'})

    assert result['ok'] is True
    assert result['status'] == 'SUCCESS'
    assert result['load']['loadedCount'] == 10
    assert 'file rows inserted successfully' in result['message']


def test_enrich_quotes_does_not_persist_failed_quote_records(monkeypatch):
    trade_date = dt.date(2026, 3, 5)
    upserts = []

    monkeypatch.setattr(service, 'ensure_runtime', lambda *args, **kwargs: None)
    monkeypatch.setattr(service, '_symbols_for_enrichment', lambda *_args, **_kwargs: ['ABC'])
    monkeypatch.setattr(service, '_upsert_records', lambda records: (upserts.extend(records) or (len(records), 0)))

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def read_json(self, _url):
            raise RuntimeError('HTTP Error 403: Forbidden')

    monkeypatch.setattr(service, '_HttpClient', FakeClient)

    result = service.enrich_quotes(trade_date)

    assert result['failureCount'] == 1
    assert upserts == []




def test_is_abandoned_persisted_job_ignores_recently_updated_running_job():
    started_at = '2026-04-01T00:00:00Z'
    updated_at = '2026-04-01T09:59:00Z'
    now_ts = dt.datetime(2026, 4, 1, 10, 0, 0, tzinfo=dt.timezone.utc).timestamp()

    job = {
        'status': 'running',
        'startedAt': started_at,
        'updatedAt': updated_at,
        'finishedAt': None,
    }

    assert service._is_abandoned_persisted_job(job, now_ts=now_ts) is False


def test_mark_abandoned_job_failed_preserves_existing_stage_duration():
    flow = {
        'keys': ['download', 'validate', 'process', 'success'],
        'activeKey': 'process',
        'failedKey': '',
        'detail': 'Inserting Oracle rows.',
        'stageStartedAt': '2026-04-01T00:10:00Z',
        'stageStartedTs': dt.datetime(2026, 4, 1, 0, 10, 0, tzinfo=dt.timezone.utc).timestamp(),
        'durationsMs': {'download': 3200, 'validate': 4100, 'process': 5800, 'success': 0},
        'completed': {'download': True, 'validate': True, 'process': False, 'success': False},
        'updatedAt': '2026-04-01T00:10:00Z',
        'finishedAt': None,
    }
    job = {
        'status': 'running',
        'message': 'Still processing insert stage.',
        'startedAt': '2026-04-01T00:00:00Z',
        'updatedAt': '2026-04-01T00:10:00Z',
        'finishedAt': None,
        'flow': flow,
        'logs': ['[INFO] Insert / Process started'],
    }

    failed = service._mark_abandoned_job_failed(
        job,
        'Background job state was stale and has been marked failed during recovery.',
        when_ts=dt.datetime(2026, 4, 1, 10, 0, 0, tzinfo=dt.timezone.utc).timestamp(),
    )

    assert failed['status'] == 'FAILED'
    assert failed['flow']['activeKey'] == ''
    assert failed['flow']['failedKey'] == 'process'
    assert failed['flow']['durationsMs']['process'] == 5800
    assert failed['finishedAt'] == '2026-04-01T10:00:00Z'
    assert failed['logs'][-1].startswith('[WARN] Background job state was stale')


def test_persisted_job_from_row_marks_stale_running_process_job_failed(monkeypatch):
    started_at = '2026-04-01T00:00:00Z'
    updated_at = '2026-04-01T00:15:00Z'
    saved = {}

    snapshot = {
        'jobId': 'job-stale-001',
        'jobType': 'pipeline',
        'pipelineType': 'market-cap',
        'jobMode': 'pipeline',
        'status': 'running',
        'message': 'Insert / Process is still running.',
        'startedAt': started_at,
        'updatedAt': updated_at,
        'finishedAt': None,
        'request': {'tradeDate': '2026-04-01', 'jobMode': 'pipeline'},
        'flow': {
            'keys': ['download', 'validate', 'process', 'success'],
            'activeKey': 'process',
            'failedKey': '',
            'detail': 'Running insert stage in background.',
            'stageStartedAt': updated_at,
            'durationsMs': {'download': 3000, 'validate': 2000, 'process': 1500, 'success': 0},
            'completed': {'download': True, 'validate': True, 'process': False, 'success': False},
            'updatedAt': updated_at,
            'finishedAt': None,
        },
        'stats': {'totalRecordsInserted': 12},
        'logs': {'tail': ['[INFO] Insert / Process started']},
    }
    row = {
        'run_id': 'job-stale-001',
        'status': 'RUNNING',
        'message': 'Insert / Process is still running.',
        'request_json': json.dumps({'tradeDate': '2026-04-01', 'jobMode': 'pipeline'}),
        'metrics_json': json.dumps({'job': snapshot}),
        'logs_clob': '',
        'download_file_path': 'D:\\data\\symbols.csv',
        'started_ts': started_at,
        'finished_ts': None,
    }

    monkeypatch.setattr(
        service,
        '_save_run_finish',
        lambda run_id, status, message, result, logs, download_path, job=None: saved.update({
            'run_id': run_id,
            'status': status,
            'message': message,
            'logs': list(logs),
            'download_path': download_path,
            'job': job,
        }),
    )
    monkeypatch.setattr(
        service.time,
        'time',
        lambda: dt.datetime(2026, 4, 1, 10, 0, 0, tzinfo=dt.timezone.utc).timestamp(),
    )

    result = service._persisted_job_from_row(row, 180)

    assert result['status'] == 'TIMED_OUT'
    assert result['done'] is True
    assert result['currentStage'] == 'process'
    assert result['flow']['failedKey'] == 'process'
    assert result['flow']['activeKey'] == ''
    assert 'timed out' in result['message'].lower()
    assert saved['run_id'] == 'job-stale-001'
    assert saved['status'] == 'TIMED_OUT'
    assert saved['job']['status'] == 'TIMED_OUT'


def test_persisted_job_from_row_tolerates_unreadable_lob_payloads():
    class BrokenLob:
        def read(self):
            raise RuntimeError('lob read failed')

        def __str__(self):
            raise RuntimeError('lob str failed')

    row = {
        'run_id': 'job-bad-lob-001',
        'status': 'SUCCESS',
        'message': 'Completed with persisted CLOB read unavailable.',
        'request_json': BrokenLob(),
        'metrics_json': BrokenLob(),
        'logs_clob': BrokenLob(),
        'download_file_path': 'C:/temp/mcap.csv',
        'started_ts': '2026-04-01 09:00:00',
        'finished_ts': '2026-04-01 09:10:00',
    }

    result = service._persisted_job_from_row(row, 20)

    assert result['jobId'] == 'job-bad-lob-001'
    assert result['status'] == 'SUCCESS'
    assert result['done'] is True
    assert result['request'] == {}
    assert result['logs']['tail'] == []


def test_serialize_job_normalizes_succeeded_flow_to_success_stage():
    job = {
        'id': 'job-success-001',
        'status': 'succeeded',
        'message': 'Pipeline completed.',
        'startedAt': '2026-04-01T09:00:00Z',
        'updatedAt': '2026-04-01T09:05:00Z',
        'finishedAt': '2026-04-01T09:05:00Z',
        'request': {'tradeDate': '2026-04-01'},
        'result': {'ok': True},
        'downloadPath': 'C:/temp/mcap.csv',
        'logs': [],
        'flow': {
            'keys': list(service._FLOW_KEYS),
            'activeKey': 'process',
            'failedKey': '',
            'detail': 'Loading NSE MCAP rows into Oracle.',
            'stageStartedAt': '2026-04-01T09:04:00Z',
            'durationsMs': {'download': 1000, 'validate': 2000, 'process': 3000, 'success': 0},
            'completed': {'download': True, 'validate': True, 'process': True, 'success': False},
            'updatedAt': '2026-04-01T09:05:00Z',
            'finishedAt': None,
        },
        'stats': service._empty_job_stats(),
        'latestRows': [],
    }

    result = service._serialize_job(job, 180)

    assert result['done'] is True
    assert result['currentStage'] == 'success'
    assert result['flow']['activeKey'] == 'success'
    assert result['flow']['completed']['process'] is True
    assert result['flow']['completed']['success'] is True
    assert result['stageStatus']['success'] == 'COMPLETED'


def test_persisted_running_job_without_live_worker_is_failed_immediately(monkeypatch):
    saved = {}
    started_at = dt.datetime(2026, 4, 1, 9, 30, 0, tzinfo=dt.timezone.utc)
    row = {
        'run_id': 'job-running-001',
        'status': 'RUNNING',
        'request_json': '{}',
        'metrics_json': json.dumps({
            'job': {
                'jobId': 'job-running-001',
                'status': 'running',
                'message': 'Finalizing NSE delivery pipeline results.',
                'startedAt': '2026-04-01T09:30:00Z',
                'updatedAt': '2026-04-01T09:31:00Z',
                'request': {'tradeDate': '2026-04-01'},
                'flow': {
                    'keys': list(service._FLOW_KEYS),
                    'activeKey': 'success',
                    'failedKey': '',
                    'detail': 'Finalizing NSE delivery pipeline results.',
                    'stageStartedAt': '2026-04-01T09:31:00Z',
                    'durationsMs': {'download': 1000, 'validate': 2000, 'process': 3000, 'success': 500},
                    'completed': {'download': True, 'validate': True, 'process': True, 'success': False},
                    'updatedAt': '2026-04-01T09:31:00Z',
                    'finishedAt': None,
                },
            }
        }),
        'message': 'Finalizing NSE delivery pipeline results.',
        'logs_clob': '',
        'download_file_path': 'C:/temp/delivery.csv',
        'started_ts': started_at,
        'finished_ts': None,
    }

    monkeypatch.setattr(
        service,
        '_save_run_finish',
        lambda run_id, status, message, result, logs, download_path, job=None: saved.update({
            'run_id': run_id,
            'status': status,
            'message': message,
            'job': job,
            'download_path': download_path,
        }),
    )
    monkeypatch.setattr(
        service.time,
        'time',
        lambda: dt.datetime(2026, 4, 1, 9, 31, 30, tzinfo=dt.timezone.utc).timestamp(),
    )

    result = service._persisted_job_from_row(row, 180)

    assert result['status'] == 'TIMED_OUT'
    assert result['done'] is True
    assert result['flow']['failedKey'] == 'success'
    assert result['flow']['activeKey'] == ''
    assert 'without a live worker' in result['message'].lower()
    assert saved['run_id'] == 'job-running-001'
    assert saved['status'] == 'TIMED_OUT'
    assert saved['job']['status'] == 'TIMED_OUT'


def test_get_dashboard_combines_file_and_quote_rows(monkeypatch):
    trade_date = dt.date(2026, 3, 2)
    executed_sql = []

    class FakeCursor:
        def __init__(self):
            self.description = []
            self._rows = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, binds=None):
            executed_sql.append(sql)
            if 'SELECT MAX(TRADE_DATE) FROM' in sql and 'WHERE TRADE_DATE = :trade_date' in sql:
                self.description = [('MAX_TRADE_DATE',)]
                self._rows = [(trade_date,)]
                return
            if 'COUNT(*) total_rows' in sql:
                self.description = [
                    ('TOTAL_ROWS',), ('DISTINCT_SYMBOLS',), ('LATEST_FETCH_TS',), ('FILE_ROWS',), ('QUOTE_ROWS',),
                    ('SUCCESS_ROWS',), ('FAILURE_ROWS',), ('SKIPPED_ROWS',), ('FFMC_ROWS',), ('TOTAL_MCAP_CR_SUM',), ('FFMC_CR_SUM',)
                ]
                self._rows = [(2, 1, None, 1, 1, 2, 0, 0, 1, 100.0, 80.0)]
                return
            if 'WITH file_rows AS (' in sql:
                self.description = [
                    ('SYMBOL',), ('SOURCE_NAME',), ('SERIES',), ('SECURITY_NAME',), ('RAW_TOTAL_MCAP',), ('RAW_TOTAL_MCAP_UNIT',),
                    ('TOTAL_MCAP_CR',), ('RAW_FFMC',), ('RAW_FFMC_UNIT',), ('FFMC_CR',), ('FETCH_STATUS',), ('INSERTED_ROWS',), ('FETCH_TS',)
                ]
                self._rows = [
                    ('ABC', 'NSE_MCAP_FILE + NSE_QUOTE_API', 'EQ', 'ABC LTD', 1000000000.0, 'RS', 100.0, 800000000.0, 'RS', 80.0, 'SUCCESS', 2, dt.datetime(2026, 3, 2, 9, 0, 0))
                ]
                return
            if 'FROM' in sql and 'run_id' in sql and 'download_file_path' in sql:
                self.description = [
                    ('RUN_ID',), ('TRADE_DATE',), ('RUN_TYPE',), ('STATUS',), ('MESSAGE',), ('DOWNLOAD_FILE_PATH',), ('STARTED_TS',), ('FINISHED_TS',), ('CREATED_BY',)
                ]
                self._rows = []
                return
            if 'SELECT REQUEST_JSON, STATUS' in sql:
                self.description = [('REQUEST_JSON',), ('STATUS',)]
                self._rows = []
                return
            raise AssertionError(f'Unexpected SQL: {sql}')

        def fetchone(self):
            return self._rows[0] if self._rows else None

        def fetchall(self):
            return list(self._rows)

    class FakeConn:
        def __init__(self):
            self.cursor_obj = FakeCursor()

        def cursor(self):
            return self.cursor_obj

        def close(self):
            return None

    monkeypatch.setattr(service, 'ensure_runtime', lambda *args, **kwargs: None)
    monkeypatch.setattr(service.pool, 'acquire', lambda: FakeConn())
    monkeypatch.setattr(service, '_get_data_overview', lambda *args, **kwargs: {'selectedTradeDate': trade_date.strftime('%Y-%m-%d'), 'dailyData': 1})

    result = service.get_dashboard(trade_date.strftime('%Y-%m-%d'))

    assert result['rows'][0]['source_name'] == 'NSE_MCAP_FILE + NSE_QUOTE_API'
    assert result['rows'][0]['status'] == 'SUCCESS'
    assert result['rows'][0]['fetchStatus'] == 'SUCCESS'
    assert result['rows'][0]['insertion_source'] == 'NSE_MCAP_FILE + NSE_QUOTE_API'
    assert result['rows'][0]['inserted_rows'] == 2
    assert result['rows'][0]['insertedRows'] == 2
    assert result['rows'][0]['ffmc_cr'] == 80.0
    assert result['dataOverview']['selectedTradeDate'] == trade_date.strftime('%Y-%m-%d')
    assert any('LEFT JOIN quote_rows' in sql for sql in executed_sql)


def test_download_mcap_csv_falls_back_to_pr_zip_container(monkeypatch, tmp_path):
    trade_date = dt.date(2026, 3, 5)
    attempts = []

    monkeypatch.setattr(service, '_DOWNLOAD_DIR', tmp_path)
    monkeypatch.setattr(service, 'ensure_runtime', lambda *args, **kwargs: None)
    monkeypatch.setattr(service, '_candidate_specs', lambda *_args, **_kwargs: [('historical_mcap_lower', 'https://example.com/mcap05032026.csv')])
    monkeypatch.setattr(service, '_archive_candidate_specs', lambda *_args, **_kwargs: [('historical_pr_upper', 'https://example.com/PR050326.zip')])
    monkeypatch.setattr(service, '_discover_urls', lambda *_args, **kwargs: [] if not kwargs.get('include_archive') else [])

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def read(self, url, accept):
            attempts.append(url)
            if url.endswith('PR050326.zip'):
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, 'w') as archive:
                    archive.writestr('mcap05032026.csv', 'SYMBOL,MARKETCAPRS\nABC,100\n')
                return (buffer.getvalue(), {'Content-Type': 'application/zip'})
            raise HTTPError(url, 404, 'Not Found', hdrs=None, fp=None)

    monkeypatch.setattr(service, '_HttpClient', FakeClient)

    result = service.download_mcap_csv(trade_date)

    assert attempts == ['https://example.com/mcap05032026.csv', 'https://example.com/PR050326.zip']
    assert result.read_text(encoding='utf-8') == 'SYMBOL,MARKETCAPRS\nABC,100\n'


def test_get_dashboard_single_coerces_string_latest_trade_date(monkeypatch):
    executed_sql = []

    class FakeCursor:
        def __init__(self):
            self.description = []
            self._rows = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, binds=None):
            executed_sql.append(sql)
            if 'SELECT MAX(TRADE_DATE) FROM' in sql and 'WHERE TRADE_DATE = :trade_date' in sql:
                self.description = [('MAX_TRADE_DATE',)]
                self._rows = [(None,)]
                return
            if 'SELECT MAX(TRADE_DATE) FROM' in sql:
                self.description = [('MAX_TRADE_DATE',)]
                self._rows = [('2026-03-05',)]
                return
            if 'COUNT(*) total_rows' in sql:
                self.description = [
                    ('TOTAL_ROWS',), ('DISTINCT_SYMBOLS',), ('LATEST_FETCH_TS',), ('FILE_ROWS',), ('QUOTE_ROWS',),
                    ('SUCCESS_ROWS',), ('FAILURE_ROWS',), ('SKIPPED_ROWS',), ('FFMC_ROWS',), ('TOTAL_MCAP_CR_SUM',), ('FFMC_CR_SUM',)
                ]
                self._rows = [(1, 1, None, 1, 0, 1, 0, 0, 0, 100.0, 0.0)]
                return
            if 'WITH file_rows AS (' in sql:
                self.description = [
                    ('SYMBOL',), ('TRADE_DATE',), ('SOURCE_NAME',), ('SERIES',), ('SECURITY_NAME',), ('RAW_TOTAL_MCAP',), ('RAW_TOTAL_MCAP_UNIT',),
                    ('TOTAL_MCAP_CR',), ('RAW_FFMC',), ('RAW_FFMC_UNIT',), ('FFMC_CR',), ('FETCH_STATUS',), ('INSERTED_ROWS',), ('FETCH_TS',)
                ]
                self._rows = [
                    ('ABC', '2026-03-05', 'NSE_MCAP_FILE', 'EQ', 'ABC LTD', 1000000000.0, 'RS', 100.0, None, None, None, 'SUCCESS', 1, dt.datetime(2026, 3, 5, 9, 0, 0))
                ]
                return
            if 'FROM' in sql and 'run_id' in sql and 'download_file_path' in sql:
                self.description = [('RUN_ID',), ('TRADE_DATE',), ('RUN_TYPE',), ('STATUS',), ('MESSAGE',), ('DOWNLOAD_FILE_PATH',), ('STARTED_TS',), ('FINISHED_TS',), ('CREATED_BY',)]
                self._rows = []
                return
            if 'SELECT REQUEST_JSON, STATUS' in sql:
                self.description = [('REQUEST_JSON',), ('STATUS',)]
                self._rows = []
                return
            raise AssertionError(f'Unexpected SQL: {sql}')

        def fetchone(self):
            return self._rows[0] if self._rows else None

        def fetchall(self):
            return list(self._rows)

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def close(self):
            return None

    monkeypatch.setattr(service, 'ensure_runtime', lambda *args, **kwargs: None)
    monkeypatch.setattr(service.pool, 'acquire', lambda: FakeConn())
    monkeypatch.setattr(service, '_get_data_overview', lambda *args, **kwargs: {'selectedTradeDate': '2026-03-05', 'dailyData': 1})

    result = service._get_dashboard_single(None, include_overview=True)

    assert result['tradeDate'] == '2026-03-05'
    assert result['dataOverview']['selectedTradeDate'] == '2026-03-05'


def test_get_dashboard_max_range_uses_all_data(monkeypatch):
    called = {'all': [], 'parse': []}

    monkeypatch.setattr(
        service,
        '_get_dashboard_all',
        lambda limit=None: called['all'].append(limit) or {'ok': True, 'summary': {'totalRows': 0}},
    )
    monkeypatch.setattr(
        service,
        '_parse_trade_dates',
        lambda *args, **kwargs: called['parse'].append((args, kwargs)) or [dt.date(2026, 3, 5)],
    )

    result = service.get_dashboard(limit=77, range_text='max')

    assert result['ok'] is True
    assert called['all'] == [77]
    assert called['parse'] == []


def test_enrich_quotes_skips_remaining_symbols_during_preopen_null_payload(monkeypatch):
    trade_date = dt.date(2026, 3, 5)
    upserts = []
    calls = []

    monkeypatch.setattr(service, 'ensure_runtime', lambda *args, **kwargs: None)
    monkeypatch.setattr(service, '_symbols_for_enrichment', lambda *_args, **_kwargs: ['ABC', 'DEF', 'GHI'])
    monkeypatch.setattr(service, '_upsert_records', lambda records: (upserts.extend(records) or (len(records), 0)))

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def read_json(self, url):
            calls.append(url)
            return {
                'currentMarketType': 'PO',
                'marketDeptOrderBook': {'tradeInfo': {'totalMarketCap': None, 'ffmc': None}},
            }

    monkeypatch.setattr(service, '_HttpClient', FakeClient)

    result = service.enrich_quotes(trade_date)

    assert len(calls) == 1
    assert result['failureCount'] == 0
    assert result['skippedCount'] == 3
    assert upserts[0]['fetch_status'] == 'SKIPPED'


def test_enrich_quotes_marks_success_when_trade_info_contains_ffmc(monkeypatch):
    trade_date = dt.date(2026, 3, 5)
    upserts = []

    monkeypatch.setattr(service, 'ensure_runtime', lambda *args, **kwargs: None)
    monkeypatch.setattr(service, '_symbols_for_enrichment', lambda *_args, **_kwargs: ['ABB'])
    monkeypatch.setattr(service, '_upsert_records', lambda records: (upserts.extend(records) or (len(records), 0)))

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def read_json(self, url):
            return {
                'marketDeptOrderBook': {
                    'tradeInfo': {
                        'totalMarketCap': 132156.66,
                        'ffmc': 32594.02289764,
                    }
                }
            }

    monkeypatch.setattr(service, '_HttpClient', FakeClient)

    result = service.enrich_quotes(trade_date)

    assert result['successCount'] == 1
    assert result['failureCount'] == 0
    assert result['skippedCount'] == 0
    assert upserts[0]['fetch_status'] == 'SUCCESS'
    assert upserts[0]['ffmc_cr'] is not None

def test_enrich_quotes_parallel_workers_process_all_symbols(monkeypatch):
    trade_date = dt.date(2026, 3, 5)
    upserts = []

    monkeypatch.setattr(service, 'ensure_runtime', lambda *args, **kwargs: None)
    monkeypatch.setattr(service, '_ENRICH_CONCURRENCY', 4)
    monkeypatch.setattr(service, '_symbols_for_enrichment', lambda *_args, **_kwargs: ['ABB', 'ACC', 'ACE', 'AIAENG'])
    monkeypatch.setattr(service, '_upsert_records', lambda records: (upserts.extend(records) or (len(records), 0)))

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def read_json(self, url):
            return {
                'marketDeptOrderBook': {
                    'tradeInfo': {
                        'totalMarketCap': 132156.66,
                        'ffmc': 32594.02289764,
                    }
                }
            }

    monkeypatch.setattr(service, '_HttpClient', FakeClient)

    result = service.enrich_quotes(trade_date)

    assert result['requested'] == 4
    assert result['processed'] == 4
    assert result['successCount'] == 4
    assert result['failureCount'] == 0
    assert len(upserts) == 4


def test_enrich_quotes_uses_quote_specific_http_client_settings(monkeypatch):
    trade_date = dt.date(2026, 3, 5)
    upserts = []
    client_kwargs = []

    monkeypatch.setattr(service, 'ensure_runtime', lambda *args, **kwargs: None)
    monkeypatch.setattr(service, '_ENRICH_CONCURRENCY', 1)
    monkeypatch.setattr(service, '_symbols_for_enrichment', lambda *_args, **_kwargs: ['ABB'])
    monkeypatch.setattr(service, '_upsert_records', lambda records: (upserts.extend(records) or (len(records), 0)))

    class FakeClient:
        def __init__(self, *args, **kwargs):
            client_kwargs.append(kwargs)

        def read_json(self, _url):
            return {
                'marketDeptOrderBook': {
                    'tradeInfo': {
                        'totalMarketCap': 132156.66,
                        'ffmc': 32594.02289764,
                    }
                }
            }

    monkeypatch.setattr(service, '_HttpClient', FakeClient)

    result = service.enrich_quotes(trade_date)

    assert result['successCount'] == 1
    assert len(upserts) == 1
    assert client_kwargs == [{
        'warmup': False,
        'timeout_sec': service._QUOTE_TIMEOUT_SEC,
        'retry_count': service._QUOTE_RETRY_COUNT,
        'min_sleep': service._QUOTE_MIN_SLEEP,
        'max_sleep': service._QUOTE_MAX_SLEEP,
    }]


def test_inspect_mcap_csv_filters_to_nifty500_symbols(tmp_path):
    trade_date = dt.date(2026, 3, 17)
    csv_path = tmp_path / 'mcap17032026.csv'
    csv_path.write_text(
        'SYMBOL,SERIES,MARKETCAPRS\nABC,EQ,100\nXYZ,EQ,200\nDEF,BE,300\n',
        encoding='utf-8',
    )

    result = service.inspect_mcap_csv(csv_path, trade_date, eq_only=True, allowed_symbols=['ABC'])

    assert result['matchedRows'] == 1
    assert result['matchedSymbols'] == ['ABC']
    assert result['seriesSkippedRows'] == 1
    assert result['universeSkippedRows'] == 1


def test_load_mcap_csv_skips_existing_trade_date(monkeypatch, tmp_path):
    trade_date = dt.date(2026, 3, 20)
    csv_path = tmp_path / 'mcap20032026.csv'
    csv_path.write_text('SYMBOL,MARKETCAPRS\nABC,100\nDEF,200\nGHI,300\nJKL,400\n', encoding='utf-8')

    monkeypatch.setattr(service, 'ensure_runtime', lambda *args, **kwargs: None)
    monkeypatch.setattr(service, '_existing_file_symbols', lambda *_args, **_kwargs: {'ABC', 'DEF', 'GHI', 'JKL'})

    result = service.load_mcap_csv(csv_path, trade_date)

    assert result['alreadyLoaded'] is True
    assert result['alreadyLoadedCount'] == 4
    assert result['loadedCount'] == 0
    assert result['failureCount'] == 0


def test_start_pipeline_job_can_run_download_only(monkeypatch):
    saved = {'start': None, 'finish': None}
    service._JOBS.clear()

    class ImmediateThread:
        def __init__(self, target=None, daemon=None, name=None):
            self._target = target

        def start(self):
            if self._target:
                self._target()

    monkeypatch.setattr(service.threading, 'Thread', ImmediateThread)
    monkeypatch.setattr(service, 'ensure_runtime', lambda *args, **kwargs: None)
    monkeypatch.setattr(service, '_find_persisted_run_by_identity', lambda *args, **kwargs: None)
    monkeypatch.setattr(service, '_save_run_start', lambda *args, **kwargs: saved.update({'start': args}))
    monkeypatch.setattr(service, '_save_run_finish', lambda *args, **kwargs: saved.update({'finish': args}))
    monkeypatch.setattr(service, 'download_api', lambda payload: {'ok': True, 'status': 'SUCCESS', 'done': True, 'message': 'download complete', 'downloadPath': 'C:/temp/mcap.csv'})
    monkeypatch.setattr(service, 'run_pipeline', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('run_pipeline should not be called for download-only jobs')))

    result = service.start_pipeline_job({'tradeDate': '2026-03-17', 'jobMode': 'download'})
    job = service.get_job(result['jobId'])

    assert result['ok'] is True
    assert result['jobMode'] == 'download'
    assert job['done'] is True
    assert job['status'] == 'SUCCESS'
    assert job['jobMode'] == 'download'
    assert job['downloadPath'] == 'C:/temp/mcap.csv'
    assert saved['start'] is not None
    assert saved['finish'] is not None


def test_start_pipeline_job_exposes_flow_state(monkeypatch):
    service._JOBS.clear()

    class ImmediateThread:
        def __init__(self, target=None, daemon=None, name=None):
            self._target = target

        def start(self):
            if self._target:
                self._target()

    def fake_run_pipeline(payload, line_logger=None):
        if line_logger:
            line_logger(service._flow_marker('validate', 'Inspecting NSE MCAP CSV.'))
            line_logger(service._flow_marker('process', 'Loading NSE MCAP rows into Oracle.'))
        return {'ok': True, 'message': 'done', 'downloadPath': 'C:/temp/mcap.csv'}

    monkeypatch.setattr(service.threading, 'Thread', ImmediateThread)
    monkeypatch.setattr(service, 'ensure_runtime', lambda *args, **kwargs: None)
    monkeypatch.setattr(service, '_find_persisted_run_by_identity', lambda *args, **kwargs: None)
    monkeypatch.setattr(service, '_save_run_start', lambda *args, **kwargs: None)
    monkeypatch.setattr(service, '_save_run_finish', lambda *args, **kwargs: None)
    monkeypatch.setattr(service, 'run_pipeline', fake_run_pipeline)

    result = service.start_pipeline_job({'tradeDate': '2026-03-17'})
    job = service.get_job(result['jobId'])

    assert 'flow' in result
    assert job['flow']['completed']['download'] is True
    assert job['flow']['completed']['validate'] is True
    assert job['flow']['completed']['process'] is True
    assert job['flow']['completed']['success'] is True



def test_process_api_returns_duplicate_message(monkeypatch, tmp_path):
    trade_date = dt.date(2026, 3, 20)
    csv_path = tmp_path / 'mcap20032026.csv'
    csv_path.write_text('SYMBOL,MARKETCAPRS\nABC,100\n', encoding='utf-8')
    inspection = {'matchedRows': 1, 'inputRows': 1}

    monkeypatch.setattr(service, 'download_mcap_csv', lambda *_args, **_kwargs: csv_path)
    monkeypatch.setattr(service, 'inspect_mcap_csv', lambda *_args, **_kwargs: inspection)
    monkeypatch.setattr(
        service,
        'load_mcap_csv',
        lambda *_args, **_kwargs: {'inputRows': 1, 'loadedCount': 0, 'failureCount': 0, 'skippedCount': 0, 'universeSkippedCount': 0, 'duplicateCount': 1, 'alreadyLoaded': True, 'alreadyLoadedCount': 1},
    )
    monkeypatch.setattr(service, 'get_dashboard', lambda *_args, **_kwargs: {'summary': {'fileRows': 0}})

    result = service.process_api({'tradeDate': trade_date.strftime('%Y-%m-%d')})

    assert result['status'] == 'ALREADY_EXISTS'
    assert result['message'] == 'NSE MCAP data already exists for 2026-03-20; no new rows were inserted.'
    assert result['load']['alreadyLoaded'] is True
    assert result['load']['alreadyLoadedCount'] == 1


def test_normalize_status_reconciles_zero_counts_with_persisted_mcap_rows():
    result = service._normalize_result_status({
        'ok': True,
        'status': 'PARTIAL',
        'tradeDate': '2026-04-24',
        'counts': {
            'insertedRows': 0,
            'validRows': 0,
            'duplicateRows': 0,
            'skippedRows': 0,
            'invalidRows': 0,
            'failedRows': 0,
        },
        'inspection': {'inputRows': 0, 'matchedRows': 0, 'parseErrorRows': 0, 'skippedRows': 0},
        'load': {
            'inputRows': 0,
            'loadedCount': 0,
            'failureCount': 0,
            'skippedCount': 0,
            'universeSkippedCount': 0,
            'duplicateCount': 0,
            'alreadyLoaded': False,
            'alreadyLoadedCount': 0,
        },
        'summary': {'fileRows': 778, 'successRows': 778, 'insertedRows': 778, 'failureRows': 0, 'skippedRows': 0},
        'dbVerification': {'rowCountBefore': 0, 'rowCountAfter': 778, 'failedRows': 0, 'skippedRows': 0},
    })

    assert result['status'] == 'SUCCESS'
    assert result['ok'] is True
    assert result['message'] == 'NSE MCAP ingestion completed successfully for 2026-04-24.'


def test_process_api_single_uses_db_verified_rows_when_load_summary_is_zero(monkeypatch, tmp_path):
    trade_date = dt.date(2026, 4, 24)
    csv_path = tmp_path / 'mcap24042026.csv'
    csv_path.write_text('SYMBOL,MARKETCAPRS\n', encoding='utf-8')
    row_counts = iter([0, 778])

    monkeypatch.setattr(service, '_runtime_filter_symbols', lambda: None)
    monkeypatch.setattr(service, '_safe_mcap_trade_date_row_count', lambda *_args, **_kwargs: next(row_counts))
    monkeypatch.setattr(service, 'download_mcap_csv', lambda *_args, **_kwargs: csv_path)
    monkeypatch.setattr(service, 'inspect_mcap_csv', lambda *_args, **_kwargs: {'inputRows': 0, 'matchedRows': 0, 'matchedSymbolsCount': 0, 'parseErrorRows': 0, 'skippedRows': 0})
    monkeypatch.setattr(
        service,
        'load_mcap_csv',
        lambda *_args, **_kwargs: {
            'inputRows': 0,
            'loadedCount': 0,
            'failureCount': 0,
            'skippedCount': 0,
            'universeSkippedCount': 0,
            'duplicateCount': 0,
            'alreadyLoaded': False,
            'alreadyLoadedCount': 0,
        },
    )
    monkeypatch.setattr(
        service,
        'get_dashboard',
        lambda *_args, **_kwargs: {'summary': {'fileRows': 778, 'successRows': 778, 'insertedRows': 778, 'failureRows': 0, 'skippedRows': 0}},
    )

    result = service.process_api({'tradeDate': '2026-04-24'})

    assert result['status'] == 'SUCCESS'
    assert result['ok'] is True
    assert result['db_inserted'] is True
    assert result['inserted_row_count'] == 778
    assert result['parsed_row_count'] == 778



def test_parse_trade_dates_range_skips_weekends():
    result = service._parse_trade_dates(start_date_value='2026-03-20', end_date_value='2026-03-23')

    assert [item.strftime('%Y-%m-%d') for item in result] == ['2026-03-20', '2026-03-23']


def test_parse_trade_dates_blocks_2026_nse_holiday_by_default():
    with pytest.raises(ValueError, match='not an NSE market working day'):
        service._parse_trade_dates(trade_date_value='2026-05-28')


def test_parse_trade_dates_allows_holiday_with_manual_override():
    result = service._parse_trade_dates(trade_date_value='2026-05-28', allow_override=True)

    assert result == [dt.date(2026, 5, 28)]


def test_parse_trade_dates_allows_budget_day_special_sunday_without_override():
    result = service._parse_trade_dates(trade_date_value='01-02-2026')

    assert result == [dt.date(2026, 2, 1)]


def test_process_api_range_aggregates_business_dates(monkeypatch, tmp_path):
    trade_dates = [dt.date(2026, 3, 20), dt.date(2026, 3, 23)]
    download_calls = []
    inspect_calls = []
    load_calls = []
    dashboard_calls = []

    monkeypatch.setattr(service, '_existing_file_row_count', lambda *_args, **_kwargs: 0)

    def fake_download(trade_date, **_kwargs):
        download_calls.append(trade_date)
        csv_path = tmp_path / f'mcap{trade_date.strftime("%d%m%Y")}.csv'
        csv_path.write_text('SYMBOL,MARKETCAPRS\nABC,100\n', encoding='utf-8')
        return csv_path

    def fake_inspect(_csv_path, trade_date, **_kwargs):
        inspect_calls.append(trade_date)
        return {
            'headers': ['SYMBOL', 'MARKETCAPRS'],
            'inputRows': 1,
            'matchedRows': 1,
            'matchedSymbolsCount': 1,
            'matchedSymbols': [f'SYM{trade_date.day}'],
            'parseErrorRows': 0,
            'skippedRows': 0,
            'blankRows': 0,
            'seriesSkippedRows': 0,
            'universeSkippedRows': 0,
            'hasFfmcColumn': False,
            'nifty500Path': 'NIFTY500.csv',
        }

    def fake_load(_csv_path, trade_date, **_kwargs):
        load_calls.append(trade_date)
        return {
            'inputRows': 1,
            'loadedCount': 1,
            'failureCount': 0,
            'skippedCount': 0,
            'universeSkippedCount': 0,
            'alreadyLoaded': False,
            'alreadyLoadedCount': 0,
        }

    def fake_dashboard(trade_date_text=None, limit=None, start_date_text=None, end_date_text=None):
        dashboard_calls.append((trade_date_text, start_date_text, end_date_text, limit))
        return {
            'summary': {
                'fileRows': 2,
                'quoteRows': 0,
                'successRows': 2,
                'failureRows': 0,
            }
        }

    monkeypatch.setattr(service, 'download_mcap_csv', fake_download)
    monkeypatch.setattr(service, 'inspect_mcap_csv', fake_inspect)
    monkeypatch.setattr(service, 'load_mcap_csv', fake_load)
    monkeypatch.setattr(service, 'get_dashboard', fake_dashboard)

    result = service.process_api({'startDate': '2026-03-20', 'endDate': '2026-03-23'})

    assert download_calls == trade_dates
    assert inspect_calls == trade_dates
    assert load_calls == trade_dates
    assert result['tradeDate'] == '2026-03-23'
    assert result['startDate'] == '2026-03-20'
    assert result['endDate'] == '2026-03-23'
    assert result['dateCount'] == 2
    assert result['inspection']['matchedRows'] == 2
    assert result['inspection']['matchedSymbolsCount'] == 2
    assert result['load']['loadedCount'] == 2
    assert result['summary']['fileRows'] == 2
    assert dashboard_calls[-1] == (None, '2026-03-20', '2026-03-23', None)


def test_process_api_range_skips_unavailable_trade_dates(monkeypatch, tmp_path):
    available_date = dt.date(2026, 3, 23)
    download_calls = []
    inspect_calls = []
    load_calls = []

    monkeypatch.setattr(service, '_existing_file_row_count', lambda *_args, **_kwargs: 0)

    def fake_download(trade_date, **_kwargs):
        download_calls.append(trade_date)
        if trade_date == dt.date(2026, 3, 20):
            raise RuntimeError('Unable to download NSE MCAP CSV for 2026-03-20: HTTP Error 404: Not Found')
        csv_path = tmp_path / f'mcap{trade_date.strftime("%d%m%Y")}.csv'
        csv_path.write_text('SYMBOL,MARKETCAPRS\nABC,100\n', encoding='utf-8')
        return csv_path

    def fake_inspect(_csv_path, trade_date, **_kwargs):
        inspect_calls.append(trade_date)
        return {
            'headers': ['SYMBOL', 'MARKETCAPRS'],
            'inputRows': 1,
            'matchedRows': 1,
            'matchedSymbolsCount': 1,
            'matchedSymbols': [f'SYM{trade_date.day}'],
            'parseErrorRows': 0,
            'skippedRows': 0,
            'blankRows': 0,
            'seriesSkippedRows': 0,
            'universeSkippedRows': 0,
            'hasFfmcColumn': False,
            'nifty500Path': 'NIFTY500.csv',
        }

    def fake_load(_csv_path, trade_date, **_kwargs):
        load_calls.append(trade_date)
        return {
            'inputRows': 1,
            'loadedCount': 1,
            'failureCount': 0,
            'skippedCount': 0,
            'universeSkippedCount': 0,
            'alreadyLoaded': False,
            'alreadyLoadedCount': 0,
        }

    monkeypatch.setattr(service, 'download_mcap_csv', fake_download)
    monkeypatch.setattr(service, 'inspect_mcap_csv', fake_inspect)
    monkeypatch.setattr(service, 'load_mcap_csv', fake_load)
    monkeypatch.setattr(service, 'get_dashboard', lambda *args, **kwargs: {'summary': {'fileRows': 1}})

    result = service.process_api({'startDate': '2026-03-20', 'endDate': '2026-03-23'})

    assert download_calls == [dt.date(2026, 3, 20), available_date]
    assert inspect_calls == [available_date]
    assert load_calls == [available_date]
    assert result['processedDateCount'] == 1
    assert result['skippedUnavailableDateCount'] == 1
    assert result['skippedHolidayDates'][0]['tradeDate'] == '2026-03-20'
    assert result['load']['loadedCount'] == 1
    assert 'Skipped 1 holiday / unavailable trade date' in result['message']


def test_http_client_warmup_is_coordinated_across_threads(monkeypatch):
    service._NSE_SESSION_WARM_UNTIL_TS = 0.0
    service._NSE_SESSION_WARM_IN_FLIGHT = False
    service._NSE_SESSION_COOKIE_SNAPSHOT = []

    warmup_calls = []
    ready = threading.Event()
    release = threading.Event()

    def fake_execute(self):
        warmup_calls.append(time.time())
        ready.set()
        release.wait(timeout=2)
        self._cookie_jar.set_cookie(_test_cookie('shared'))
        return True

    monkeypatch.setattr(service._HttpClient, '_execute_warmup_requests', fake_execute)

    client_a = service._HttpClient()
    client_b = service._HttpClient()

    thread_a = threading.Thread(target=lambda: client_a._warmup(force=True))
    thread_b = threading.Thread(target=lambda: client_b._warmup(force=True))
    thread_a.start()
    assert ready.wait(timeout=1)
    thread_b.start()
    release.set()
    thread_a.join(timeout=2)
    thread_b.join(timeout=2)

    assert len(warmup_calls) == 1
    assert list(client_a._cookie_jar)
    assert list(client_b._cookie_jar)


def test_http_client_imports_recent_shared_session_without_warmup(monkeypatch):
    service._NSE_SESSION_WARM_UNTIL_TS = 0.0
    service._NSE_SESSION_WARM_IN_FLIGHT = False
    service._NSE_SESSION_COOKIE_SNAPSHOT = []

    seed_client = service._HttpClient()
    seed_client._cookie_jar.set_cookie(_test_cookie('seed'))
    seed_client._publish_shared_session()

    def unexpected_execute(self):
        raise AssertionError('warmup should not run when a shared NSE session is still fresh')

    monkeypatch.setattr(service._HttpClient, '_execute_warmup_requests', unexpected_execute)

    client = service._HttpClient()

    assert list(client._cookie_jar)


def test_calculate_trade_date_run_mode_stats_uses_request_payload_mode():
    stats = service._calculate_trade_date_run_mode_stats([
        {'status': 'SUCCESS', 'request_json': json.dumps({'mode': 'MANUAL'})},
        {'status': 'COMPLETED', 'request_json': json.dumps({'jobMode': 'pipeline'})},
        {'status': 'FAILED', 'request_json': json.dumps({'mode': 'AUTOMATION'})},
    ])

    assert stats['manual_runs'] == 1
    assert stats['auto_runs'] == 1
    assert stats['manual_flag'] == 'Y'
    assert stats['automation_flag'] == 'Y'


def test_apply_latest_row_insertion_metadata_prefers_trade_date_for_date_column():
    rows = service._apply_latest_row_insertion_metadata([
        {
            'symbol': 'ABC',
            'trade_date': '2026-06-25',
            'fetch_ts': '2026-06-28T18:30:00',
            'fetch_status': 'SUCCESS',
        }
    ])

    assert rows[0]['fetched_timestamp'] == '25-06-2026'
    assert rows[0]['tradeDate'] == '2026-06-25'


def test_process_api_persists_manual_run_record(monkeypatch):
    trade_date = dt.date(2026, 3, 17)
    persisted = {}

    monkeypatch.setattr(service, '_parse_runtime_payload', lambda payload, line_logger=None: ([trade_date], True, None, '', None))
    monkeypatch.setattr(service, '_process_api_single', lambda *args, **kwargs: {'ok': True, 'status': 'SUCCESS', 'tradeDate': '2026-03-17', 'summary': {'fileRows': 1}})
    monkeypatch.setattr(service, '_apply_run_contract_fields', lambda result, **kwargs: {**result, **kwargs})
    monkeypatch.setattr(
        service,
        '_persist_completed_run_record',
        lambda run_type, trade_date_value, payload, result, mode, stage: persisted.update({
            'run_type': run_type,
            'trade_date': trade_date_value,
            'mode': mode,
            'stage': stage,
            'result': result,
        }),
    )

    result = service.process_api({'tradeDate': '2026-03-17'})

    assert result['mode'] == 'MANUAL'
    assert persisted['run_type'] == service._RUN_TYPE
    assert persisted['trade_date'] == trade_date
    assert persisted['mode'] == 'MANUAL'
    assert persisted['stage'] == 'process'


def test_run_pipeline_persists_automation_run_when_no_job_run_id(monkeypatch):
    trade_date = dt.date(2026, 3, 17)
    persisted = {}

    monkeypatch.setattr(service, '_parse_runtime_payload', lambda payload, line_logger=None: ([trade_date], True, None, '', None))
    monkeypatch.setattr(service, '_run_pipeline_single', lambda *args, **kwargs: {'ok': True, 'status': 'SUCCESS', 'tradeDate': '2026-03-17'})
    monkeypatch.setattr(service, '_apply_run_contract_fields', lambda result, **kwargs: {**result, **kwargs})
    monkeypatch.setattr(
        service,
        '_persist_completed_run_record',
        lambda run_type, trade_date_value, payload, result, mode, stage: persisted.update({
            'run_type': run_type,
            'trade_date': trade_date_value,
            'mode': mode,
            'stage': stage,
        }),
    )

    result = service.run_pipeline({'tradeDate': '2026-03-17'})

    assert result['mode'] == 'AUTOMATION'
    assert persisted['run_type'] == service._RUN_TYPE
    assert persisted['trade_date'] == trade_date
    assert persisted['mode'] == 'AUTOMATION'
    assert persisted['stage'] == 'pipeline'
