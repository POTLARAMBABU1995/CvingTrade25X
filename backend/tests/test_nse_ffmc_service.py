import datetime as dt
import sys
import types
from pathlib import Path


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

import services.nse_ffmc_service as service


class _FakeConnection:
    def close(self):
        return None


def test_get_trading_day_verification_does_not_run_runtime_init(monkeypatch):
    monkeypatch.setattr(service.mcap.pool, 'acquire', lambda: _FakeConnection())
    monkeypatch.setattr(
        service.mcap,
        'ensure_runtime',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError('verification must stay read-only')),
    )
    monkeypatch.setattr(
        service.mcap,
        'build_trading_day_verification',
        lambda conn, table_sql, page_name, year=None, as_of_date=None: {
            'ok': True,
            'page': page_name,
            'year': year,
        },
    )

    payload = service.get_trading_day_verification(year=2026)

    assert payload == {'ok': True, 'page': 'FFMC', 'year': 2026}


def test_start_pipeline_job_reuses_active_persisted_run(monkeypatch):
    trade_date = dt.date(2026, 3, 17)
    persisted_row = {'run_id': 'ffmc-active-run', 'status': 'RUNNING'}
    captured = {}

    monkeypatch.setattr(service.mcap, 'ensure_runtime', lambda *args, **kwargs: None)
    monkeypatch.setattr(service.mcap, '_parse_trade_dates', lambda *args, **kwargs: [trade_date])
    monkeypatch.setattr(service.mcap, '_clone_request_payload', lambda payload: dict(payload or {}))
    monkeypatch.setattr(
        service.mcap,
        '_find_persisted_run_by_identity',
        lambda payload, **kwargs: captured.update({'payload': payload, 'kwargs': kwargs}) or persisted_row,
    )
    monkeypatch.setattr(
        service.mcap,
        '_persisted_job_from_row',
        lambda row, tail_lines=None: {'ok': True, 'jobId': row['run_id'], 'status': row['status'], 'tail': tail_lines},
    )
    monkeypatch.setattr(
        service.threading,
        'Thread',
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('duplicate run must not start a new thread')),
    )
    monkeypatch.setattr(
        service,
        '_symbol_source_details',
        lambda: (_ for _ in ()).throw(AssertionError('duplicate run must not reload symbol source')),
    )

    result = service.start_pipeline_job({'tradeDate': '2026-03-17', 'jobMode': 'pipeline'})

    assert result['jobId'] == 'ffmc-active-run'
    assert result['status'] == 'RUNNING'
    assert captured['kwargs']['run_type'] == 'FFMC'
    assert 'RUNNING' in captured['kwargs']['statuses']


def test_start_pipeline_job_ignores_recovered_timed_out_duplicate(monkeypatch):
    trade_date = dt.date(2026, 3, 17)
    persisted_row = {'run_id': 'ffmc-stale-run', 'status': 'RUNNING'}
    started = {'thread': False, 'run_start': None}

    class FakeThread:
        def __init__(self, target=None, daemon=None, name=None):
            self._target = target

        def start(self):
            started['thread'] = True

    monkeypatch.setattr(service.mcap, 'ensure_runtime', lambda *args, **kwargs: None)
    monkeypatch.setattr(service.mcap, '_parse_trade_dates', lambda *args, **kwargs: [trade_date])
    monkeypatch.setattr(service.mcap, '_clone_request_payload', lambda payload: dict(payload or {}))
    monkeypatch.setattr(
        service.mcap,
        '_find_persisted_run_by_identity',
        lambda payload, **kwargs: persisted_row,
    )
    monkeypatch.setattr(
        service.mcap,
        '_persisted_job_from_row',
        lambda row, tail_lines=None: {'ok': False, 'jobId': row['run_id'], 'status': 'TIMED_OUT', 'tail': tail_lines},
    )
    monkeypatch.setattr(service, '_symbol_source_details', lambda: ('C:/temp/nifty500.csv', 500))
    monkeypatch.setattr(service.threading, 'Thread', FakeThread)
    monkeypatch.setattr(service.mcap, '_save_run_start', lambda run_id, trade_date_value, run_type, payload: started.update({'run_start': (run_id, trade_date_value, run_type, payload)}))
    monkeypatch.setattr(service.mcap, '_maybe_persist_job_snapshot', lambda *args, **kwargs: None)

    result = service.start_pipeline_job({'tradeDate': '2026-03-17', 'jobMode': 'pipeline'})

    assert result['jobId'] != 'ffmc-stale-run'
    assert result['status'] == 'running'
    assert started['thread'] is True
    assert started['run_start'][2] == 'FFMC'


def test_download_api_reports_quote_fallback_when_official_ffmc_missing(monkeypatch, tmp_path):
    trade_date = dt.date(2026, 3, 17)

    monkeypatch.setattr(
        service,
        '_supporting_file',
        lambda payload, line_logger=None: (
            [trade_date],
            True,
            None,
            [],
            {'ABC'},
            tmp_path / 'mcap17032026.csv',
            {'headers': ['SYMBOL', 'MARKETCAPRS'], 'matchedSymbolsCount': 1, 'matchedSymbols': ['ABC'], 'officialFfmcCsvAvailable': False},
        ),
    )

    result = service.download_api({'tradeDate': '2026-03-17'})

    assert result['inspection']['officialFfmcCsvAvailable'] is False
    assert 'symbol universe loaded' in result['message']


def test_process_api_uses_matched_symbols_from_supporting_file(monkeypatch, tmp_path):
    trade_date = dt.date(2026, 3, 17)
    captured = {}

    monkeypatch.setattr(
        service,
        '_supporting_file',
        lambda payload, line_logger=None: (
            [trade_date],
            True,
            15,
            [],
            {'ABC', 'DEF'},
            tmp_path / 'mcap17032026.csv',
            {'matchedSymbols': ['ABC', 'DEF'], 'officialFfmcCsvAvailable': False},
        ),
    )
    monkeypatch.setattr(
        service.mcap,
        'enrich_quotes',
        lambda trade_date, limit=None, symbols=None, line_logger=None: captured.update({'tradeDate': trade_date, 'limit': limit, 'symbols': symbols}) or {'successCount': 2, 'failureCount': 0, 'skippedCount': 0},
    )
    monkeypatch.setattr(service, '_get_dashboard_single', lambda *_args, **_kwargs: {'summary': {'ffmcRows': 2}})

    result = service.process_api({'tradeDate': '2026-03-17'})

    assert result['downloadPath'] == tmp_path / 'mcap17032026.csv'
    assert captured['tradeDate'] == trade_date
    assert captured['limit'] == 15
    assert captured['symbols'] == ['ABC', 'DEF']
    assert result['summary']['ffmcRows'] == 2
    assert result['load']['loadedCount'] == 2


def test_process_existing_csv_for_symbols_api_uses_ffmc_backend(monkeypatch, tmp_path):
    download_dir = tmp_path / 'downloads'
    download_dir.mkdir()
    (download_dir / 'mcap17032026.csv').write_text('SYMBOL\nABC\n', encoding='utf-8')
    (download_dir / 'mcap18032026.csv').write_text('SYMBOL\nDEF\n', encoding='utf-8')
    symbol_file = tmp_path / 'symbols.csv'
    symbol_file.write_text('SYMBOL\nABC\nDEF\n', encoding='utf-8')
    inspected = []
    loaded = []

    def fake_inspect(csv_path, trade_date, eq_only=True, allowed_symbols=None):
        inspected.append((csv_path.name, trade_date, eq_only, sorted(allowed_symbols or [])))
        if csv_path.name == 'mcap17032026.csv':
            return {'matchedSymbols': ['ABC'], 'matchedRows': 1}
        return {'matchedSymbols': [], 'matchedRows': 0}

    def fake_load(csv_path, trade_date, eq_only=True, allowed_symbols=None, line_logger=None, skip_if_existing=False):
        loaded.append((csv_path.name, trade_date, eq_only, sorted(allowed_symbols or []), skip_if_existing))
        return {'loadedCount': 1, 'alreadyLoadedCount': 2}

    monkeypatch.setattr(service.mcap, 'inspect_mcap_csv', fake_inspect)
    monkeypatch.setattr(service.mcap, 'load_mcap_csv', fake_load)

    result = service.process_existing_csv_for_symbols_api({
        'downloadDir': str(download_dir),
        'symbolFilePath': str(symbol_file),
        'symbols': 'ABC, MISSING',
    })

    assert result['dataset_type'] == 'ffmc'
    assert result['requested_count'] == 2
    assert result['valid_symbols'] == ['ABC']
    assert result['invalid_symbols'] == ['MISSING']
    assert result['symbols_found_in_csv'] == ['ABC']
    assert result['records_inserted'] == 1
    assert result['records_skipped_existing'] == 2
    assert inspected[0][3] == ['ABC']
    assert loaded == [('mcap17032026.csv', dt.date(2026, 3, 17), True, ['ABC'], True)]


def test_process_api_marks_failed_enrichment_when_no_rows_written(monkeypatch, tmp_path):
    trade_date = dt.date(2026, 3, 30)
    source_path = str(tmp_path / 'mcap30032026.csv')

    monkeypatch.setattr(
        service,
        '_supporting_file',
        lambda payload, line_logger=None: (
            [trade_date],
            True,
            10,
            [],
            {'ABC'},
            source_path,
            {'matchedSymbols': ['ABC'], 'matchedSymbolsCount': 1, 'symbolsPath': source_path},
        ),
    )
    monkeypatch.setattr(
        service.mcap,
        'enrich_quotes',
        lambda *args, **kwargs: {'requested': 1, 'processed': 1, 'successCount': 0, 'failureCount': 1, 'skippedCount': 0},
    )
    monkeypatch.setattr(service, '_get_dashboard_single', lambda *_args, **_kwargs: {'summary': {}})

    result = service.process_api({'tradeDate': '2026-03-30'})

    assert result['ok'] is False
    assert 'failed' in result['message'].lower()


def test_process_api_treats_already_loaded_fallback_rows_as_success(monkeypatch, tmp_path):
    trade_date = dt.date(2026, 5, 29)
    source_path = str(tmp_path / 'symbols.csv')

    monkeypatch.setattr(
        service.mcap,
        'enrich_quotes',
        lambda *args, **kwargs: {
            'requested': 2,
            'processed': 2,
            'successCount': 0,
            'failureCount': 2,
            'skippedCount': 0,
        },
    )
    monkeypatch.setattr(
        service,
        '_load_mcap_file_fallback',
        lambda *args, **kwargs: (
            str(tmp_path / 'mcap29052026.csv'),
            {
                'inputRows': 4,
                'loadedCount': 0,
                'failureCount': 0,
                'skippedCount': 2,
                'universeSkippedCount': 2,
                'duplicateCount': 2,
                'alreadyLoaded': False,
                'alreadyLoadedCount': 2,
            },
            None,
        ),
    )
    row_counts = iter([0, 2])
    monkeypatch.setattr(service, '_safe_ffmc_trade_date_row_count', lambda *_args, **_kwargs: next(row_counts))
    monkeypatch.setattr(service, '_get_dashboard_single', lambda *_args, **_kwargs: {'summary': {'successRows': 2}})

    result = service._process_api_single(
        trade_date,
        None,
        ['ABC', 'DEF'],
        source_path,
        {'matchedSymbols': ['ABC', 'DEF'], 'matchedSymbolsCount': 2, 'symbolsPath': source_path},
        pipeline_mode=True,
    )

    assert result['ok'] is True
    assert result['status'] == 'SUCCESS'
    assert 'fallback' in result['message'].lower()
    assert result['load']['alreadyLoadedCount'] == 2


def test_get_dashboard_default_load_uses_mcap_ensure_runtime(monkeypatch):
    ensure_calls = []

    class FakeCursor:
        def __init__(self):
            self.description = []
            self._rows = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, binds=None):
            if 'SELECT MAX(TRADE_DATE) latest_trade_date' in sql:
                self.description = [('LATEST_TRADE_DATE',)]
                self._rows = [('2026-03-19',)]
                return
            if 'COUNT(*) total_rows' in sql:
                self.description = [
                    ('TOTAL_ROWS',), ('DISTINCT_SYMBOLS',), ('LATEST_FETCH_TS',),
                    ('SUCCESS_ROWS',), ('FAILURE_ROWS',), ('SKIPPED_ROWS',),
                    ('FFMC_ROWS',), ('TOTAL_MCAP_CR_SUM',), ('FFMC_CR_SUM',),
                ]
                self._rows = [(25, 5, None, 20, 0, 5, 20, 100.0, 80.0)]
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

    monkeypatch.setattr(service.mcap, 'ensure_runtime', lambda conn=None: ensure_calls.append(conn))
    monkeypatch.setattr(service.mcap.pool, 'acquire', lambda: FakeConn())
    monkeypatch.setattr(service, '_get_dashboard_single', lambda *args, **kwargs: {'rows': [], 'recentRuns': [], 'symbolSource': {'path': '', 'count': 0, 'label': 'NIFTY500 local universe'}})
    monkeypatch.setattr(service, '_get_data_overview', lambda *args, **kwargs: {'stocksCount': 5, 'recordsCount': 25})
    monkeypatch.setattr(service, '_symbol_source_details', lambda: ('C:/symbols.csv', 5))

    result = service.get_dashboard()

    assert result['ok'] is True
    assert result['tradeDateLabel'] == '19-03-2026'
    assert result['latest_trade_date'] == '2026-03-19'
    assert result['trade_date_display'] == '19-03-2026'
    assert len(ensure_calls) == 1


def test_get_dashboard_all_uses_latest_file_fallback_date(monkeypatch):
    calls = []

    class FakeCursor:
        description = [('LATEST_TRADE_DATE',)]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, binds=None):
            calls.append((sql, binds))

        def fetchone(self):
            return (dt.date(2026, 5, 29),)

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def close(self):
            return None

    dashboard_calls = []
    monkeypatch.setattr(service.mcap, 'ensure_runtime', lambda conn=None: None)
    monkeypatch.setattr(service.mcap.pool, 'acquire', lambda: FakeConn())
    monkeypatch.setattr(
        service,
        '_get_dashboard_single',
        lambda trade_date_text, limit=None, include_overview=True: dashboard_calls.append(trade_date_text) or {
            'summary': {'successRows': 2},
            'rows': [],
            'recentRuns': [],
        },
    )
    monkeypatch.setattr(service, '_symbol_source_details', lambda: ('C:/symbols.csv', 2))
    monkeypatch.setattr(service, '_get_data_overview', lambda *args, **kwargs: {})

    result = service._get_dashboard_all(limit=25)

    assert dashboard_calls == ['2026-05-29']
    assert result['tradeDate'] == '2026-05-29'
    assert any('source_name in' in sql.lower() for sql, _binds in calls)


def test_get_dashboard_single_sums_file_fallback_as_ffmc(monkeypatch):
    class FakeCursor:
        def __init__(self):
            self.description = []
            self._fetchone = None
            self._fetchall = []
            self.summary_sql = ''

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, binds=None):
            sql_lower = sql.lower()
            if 'summary_stats' in sql_lower:
                self.summary_sql = sql
                self.description = [
                    ('TOTAL_ROWS',),
                    ('DISTINCT_SYMBOLS',),
                    ('LATEST_FETCH_TS',),
                    ('SUCCESS_ROWS',),
                    ('FAILURE_ROWS',),
                    ('SKIPPED_ROWS',),
                    ('FFMC_ROWS',),
                    ('TOTAL_MCAP_CR_SUM',),
                    ('FFMC_CR_SUM',),
                ]
                self._fetchone = (
                    2,
                    2,
                    dt.datetime(2026, 5, 29, 18, 30),
                    2,
                    0,
                    0,
                    2,
                    300.0,
                    300.0,
                )
                self._fetchall = []
            elif 'select trade_date, symbol' in sql_lower:
                self.description = [
                    ('TRADE_DATE',),
                    ('SYMBOL',),
                    ('SOURCE_NAME',),
                    ('SERIES',),
                    ('SECURITY_NAME',),
                    ('RAW_TOTAL_MCAP',),
                    ('RAW_TOTAL_MCAP_UNIT',),
                    ('TOTAL_MCAP_CR',),
                    ('RAW_FFMC',),
                    ('RAW_FFMC_UNIT',),
                    ('FFMC_CR',),
                    ('FETCH_STATUS',),
                    ('INSERTED_ROWS',),
                    ('ERROR_MESSAGE',),
                    ('FETCH_TS',),
                ]
                self._fetchall = []
                self._fetchone = None
            elif 'run_id' in sql_lower:
                self.description = [('RUN_ID',)]
                self._fetchall = []
                self._fetchone = None
            elif 'source_name = :quote_source' in sql_lower:
                self.description = [('MAX',)]
                self._fetchone = (None,)
                self._fetchall = []
            else:
                self.description = [('MAX',)]
                self._fetchone = (dt.date(2026, 5, 27),)
                self._fetchall = []

        def fetchone(self):
            return self._fetchone

        def fetchall(self):
            return self._fetchall

    class FakeConn:
        def __init__(self):
            self.cursor_obj = FakeCursor()

        def cursor(self):
            return self.cursor_obj

        def close(self):
            return None

    fake_conn = FakeConn()
    monkeypatch.setattr(service.mcap, 'ensure_runtime', lambda conn=None: None)
    monkeypatch.setattr(service.mcap.pool, 'acquire', lambda: fake_conn)
    monkeypatch.setattr(service, '_symbol_source_details', lambda: ('C:/symbols.csv', 2))

    result = service._get_dashboard_single('2026-05-29', include_overview=False)

    assert result['summary']['ffmcRows'] == 2
    assert result['summary']['ffmcCrSum'] == 300.0
    summary_sql = fake_conn.cursor_obj.summary_sql.lower()
    assert 'from quote_rows' in summary_sql
    assert 'file_rows.total_mcap_cr' in summary_sql
    assert "when file_rows.fetch_status in ('success', 'partial')" in summary_sql


def test_get_dashboard_max_range_uses_all_data(monkeypatch):
    called = {'all': [], 'parse': []}

    monkeypatch.setattr(
        service,
        '_get_dashboard_all',
        lambda limit=None: called['all'].append(limit) or {'ok': True, 'summary': {'ffmcRows': 0}},
    )
    monkeypatch.setattr(
        service.mcap,
        '_parse_trade_dates',
        lambda *args, **kwargs: called['parse'].append((args, kwargs)) or [dt.date(2026, 3, 19)],
    )

    result = service.get_dashboard(limit=55, range_text='max')

    assert result['ok'] is True
    assert called['all'] == [55]
    assert called['parse'] == []


def test_start_pipeline_job_runs_to_completion_with_immediate_thread(monkeypatch):
    saved = {'start': None, 'finish': None}
    service._JOBS.clear()

    class ImmediateThread:
        def __init__(self, target=None, daemon=None, name=None):
            self._target = target

        def start(self):
            if self._target:
                self._target()

    monkeypatch.setattr(service.threading, 'Thread', ImmediateThread)
    monkeypatch.setattr(service.mcap, 'ensure_runtime', lambda: None)
    monkeypatch.setattr(service.mcap, '_save_run_start', lambda *args, **kwargs: saved.update({'start': args}))
    monkeypatch.setattr(service.mcap, '_save_run_finish', lambda *args, **kwargs: saved.update({'finish': args}))
    monkeypatch.setattr(service, 'run_pipeline', lambda payload, line_logger=None: {'ok': True, 'message': 'done', 'downloadPath': 'C:/temp/file.csv'})

    result = service.start_pipeline_job({'tradeDate': '2026-03-17'})
    job = service.get_job(result['jobId'])

    assert result['ok'] is True
    assert result['jobMode'] == 'pipeline'
    assert job['done'] is True
    assert job['status'] == 'SUCCESS'
    assert job['jobMode'] == 'pipeline'
    assert saved['start'] is not None
    assert saved['finish'] is not None


def test_start_pipeline_job_can_run_download_only(monkeypatch, tmp_path):
    saved = {'start': None, 'finish': None}
    service._JOBS.clear()

    class ImmediateThread:
        def __init__(self, target=None, daemon=None, name=None):
            self._target = target

        def start(self):
            if self._target:
                self._target()

    monkeypatch.setattr(service.threading, 'Thread', ImmediateThread)
    monkeypatch.setattr(service.mcap, 'ensure_runtime', lambda: None)
    monkeypatch.setattr(service.mcap, '_save_run_start', lambda *args, **kwargs: saved.update({'start': args}))
    monkeypatch.setattr(service.mcap, '_save_run_finish', lambda *args, **kwargs: saved.update({'finish': args}))
    monkeypatch.setattr(service, '_symbol_source_details', lambda: (str(tmp_path / 'mcap17032026.csv'), 1))
    monkeypatch.setattr(service, 'download_api', lambda payload: {'ok': True, 'message': 'download complete', 'downloadPath': 'C:/temp/mcap.csv'})
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
            line_logger(service.mcap._flow_marker('validate', 'Validating FFMC symbol universe.'))
            line_logger(service.mcap._flow_marker('process', 'Extracting FFMC quote data.'))
        return {'ok': True, 'message': 'done', 'downloadPath': 'C:/temp/file.csv'}

    monkeypatch.setattr(service.threading, 'Thread', ImmediateThread)
    monkeypatch.setattr(service.mcap, 'ensure_runtime', lambda: None)
    monkeypatch.setattr(service.mcap, '_save_run_start', lambda *args, **kwargs: None)
    monkeypatch.setattr(service.mcap, '_save_run_finish', lambda *args, **kwargs: None)
    monkeypatch.setattr(service, 'run_pipeline', fake_run_pipeline)

    result = service.start_pipeline_job({'tradeDate': '2026-03-17'})
    job = service.get_job(result['jobId'])

    assert 'flow' in result
    assert job['flow']['completed']['download'] is True
    assert job['flow']['completed']['validate'] is True
    assert job['flow']['completed']['process'] is True
    assert job['flow']['completed']['success'] is True

def test_process_api_range_aggregates_multiple_trade_dates(monkeypatch, tmp_path):
    date_one = dt.date(2026, 3, 17)
    date_two = dt.date(2026, 3, 18)
    source_path = str(tmp_path / 'mcap17032026.csv')
    inspection = {
        'headers': ['SYMBOL'],
        'matchedSymbols': ['ABC', 'DEF'],
        'matchedSymbolsCount': 2,
        'officialFfmcCsvAvailable': False,
        'symbolsPath': source_path,
        'symbolsCount': 2,
        'nifty500Path': source_path,
        'inputRows': 2,
        'universeSkippedRows': 0,
        'parseErrorRows': 0,
    }
    process_calls = []
    copy_calls = []

    monkeypatch.setattr(
        service,
        '_supporting_file',
        lambda payload, line_logger=None: ([date_one, date_two], True, 15, [], {'ABC', 'DEF'}, source_path, inspection),
    )

    def fake_process_single(trade_date, enrich_limit, target_symbols, symbols_path, inspection_payload, line_logger=None, pipeline_mode=False):
        process_calls.append(trade_date)
        return {
            'ok': True,
            'message': 'done',
            'tradeDate': trade_date.strftime('%Y-%m-%d'),
            'downloadPath': symbols_path,
            'inspection': dict(inspection_payload),
            'load': {'loadedCount': len(target_symbols), 'failureCount': 0, 'skippedCount': 0, 'alreadyLoaded': False},
            'enrichment': {'requested': len(target_symbols), 'processed': len(target_symbols), 'successCount': len(target_symbols), 'failureCount': 0, 'skippedCount': 0, 'elapsedSec': 1.25},
            'summary': {'ffmcRows': len(target_symbols)},
        }

    monkeypatch.setattr(service, '_process_api_single', fake_process_single)
    monkeypatch.setattr(
        service,
        '_copy_quote_rows_to_dates',
        lambda source_trade_date, target_dates, target_symbols, line_logger=None: copy_calls.append((source_trade_date, target_dates, target_symbols)) or len(target_symbols) * len(target_dates),
    )
    monkeypatch.setattr(service, 'get_dashboard', lambda *args, **kwargs: {'summary': {'ffmcRows': 4, 'ffmcCrSum': 10.0}})

    result = service.process_api({'startDate': '2026-03-17', 'endDate': '2026-03-18'})

    assert process_calls == [date_two]
    assert copy_calls == [(date_two, [date_one], ['ABC', 'DEF'])]
    assert result['ok'] is True
    assert result['dateCount'] == 2
    assert result['processedDateCount'] == 2
    assert result['load']['loadedCount'] == 4
    assert result['enrichment']['requested'] == 4
    assert result['summary']['ffmcRows'] == 4
    assert '17-03-2026 to 18-03-2026' in result['message']


def test_process_api_range_marks_partial_when_one_trade_date_is_already_loaded(monkeypatch, tmp_path):
    date_one = dt.date(2026, 3, 17)
    date_two = dt.date(2026, 3, 18)
    source_path = str(tmp_path / 'mcap17032026.csv')
    inspection = {
        'headers': ['SYMBOL'],
        'matchedSymbols': ['ABC', 'DEF'],
        'matchedSymbolsCount': 2,
        'officialFfmcCsvAvailable': False,
        'symbolsPath': source_path,
        'symbolsCount': 2,
        'nifty500Path': source_path,
        'inputRows': 2,
        'universeSkippedRows': 0,
        'parseErrorRows': 0,
    }

    monkeypatch.setattr(
        service,
        '_supporting_file',
        lambda payload, line_logger=None: ([date_one, date_two], True, 15, [], {'ABC', 'DEF'}, source_path, inspection),
    )
    monkeypatch.setattr(
        service,
        '_safe_ffmc_trade_date_row_count',
        lambda trade_date: 3 if trade_date == date_one else 0,
    )

    def fake_process_single(trade_date, enrich_limit, target_symbols, symbols_path, inspection_payload, line_logger=None, pipeline_mode=False):
        if trade_date == date_one:
            return {
                'ok': True,
                'status': 'ALREADY_EXISTS',
                'message': 'Already data inserted for 17-03-2026.',
                'tradeDate': trade_date.strftime('%Y-%m-%d'),
                'downloadPath': symbols_path,
                'inspection': {**inspection_payload, 'alreadyLoaded': True, 'alreadyLoadedCount': 3},
                'load': {'loadedCount': 0, 'failureCount': 0, 'skippedCount': 0, 'alreadyLoaded': True, 'alreadyLoadedCount': 3},
                'enrichment': {'requested': 0, 'processed': 0, 'successCount': 0, 'failureCount': 0, 'skippedCount': 0, 'elapsedSec': 0.0},
                'summary': {'ffmcRows': 3},
            }
        return {
            'ok': True,
            'status': 'SUCCESS',
            'message': 'done',
            'tradeDate': trade_date.strftime('%Y-%m-%d'),
            'downloadPath': symbols_path,
            'inspection': dict(inspection_payload),
            'load': {'loadedCount': len(target_symbols), 'failureCount': 0, 'skippedCount': 0, 'alreadyLoaded': False, 'alreadyLoadedCount': 0},
            'enrichment': {'requested': len(target_symbols), 'processed': len(target_symbols), 'successCount': len(target_symbols), 'failureCount': 0, 'skippedCount': 0, 'elapsedSec': 1.25},
            'summary': {'ffmcRows': len(target_symbols)},
        }

    monkeypatch.setattr(service, '_process_api_single', fake_process_single)
    monkeypatch.setattr(
        service,
        '_copy_quote_rows_to_dates',
        lambda source_trade_date, target_dates, target_symbols, line_logger=None: 0,
    )
    monkeypatch.setattr(service, 'get_dashboard', lambda *args, **kwargs: {'summary': {'ffmcRows': 5, 'ffmcCrSum': 10.0}})

    result = service.process_api({'startDate': '2026-03-17', 'endDate': '2026-03-18'})

    assert result['status'] == 'PARTIAL'
    assert result['processedDateCount'] == 1
    assert result['skippedDateCount'] == 1
    assert result['inspection']['alreadyLoadedCount'] == 3
    assert result['load']['alreadyLoadedCount'] == 3
    assert 'Skipped 1 already-loaded trade date(s).' in result['message']


def test_process_api_persists_manual_ffmc_run(monkeypatch):
    trade_date = dt.date(2026, 3, 17)
    persisted = {}
    inspection = {'matchedSymbols': ['ABC'], 'matchedSymbolsCount': 1}

    monkeypatch.setattr(
        service,
        '_supporting_file',
        lambda payload, line_logger=None: ([trade_date], True, None, [], {'ABC'}, 'C:/symbols.csv', inspection),
    )
    monkeypatch.setattr(service, '_target_symbols', lambda override_symbols, allowed_symbols, inspection_payload: ['ABC'])
    monkeypatch.setattr(service, '_process_api_single', lambda *args, **kwargs: {'ok': True, 'status': 'SUCCESS', 'tradeDate': '2026-03-17'})
    monkeypatch.setattr(service.mcap, '_apply_run_contract_fields', lambda result, **kwargs: {**result, **kwargs})
    monkeypatch.setattr(
        service.mcap,
        '_persist_completed_run_record',
        lambda run_type, trade_date_value, payload, result, mode, stage: persisted.update({
            'run_type': run_type,
            'trade_date': trade_date_value,
            'mode': mode,
            'stage': stage,
        }),
    )

    result = service.process_api({'tradeDate': '2026-03-17'})

    assert result['mode'] == 'MANUAL'
    assert persisted['run_type'] == service._RUN_TYPE
    assert persisted['trade_date'] == trade_date
    assert persisted['mode'] == 'MANUAL'
    assert persisted['stage'] == 'process'

