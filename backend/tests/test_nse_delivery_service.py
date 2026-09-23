import datetime as dt
import sys
import types
import zipfile
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

import services.nse_delivery_service as service


class _FakeConnection:
    def close(self):
        return None


def test_get_trading_day_verification_does_not_run_runtime_init(monkeypatch):
    monkeypatch.setattr(service.mcap.pool, 'acquire', lambda: _FakeConnection())
    monkeypatch.setattr(
        service,
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

    assert payload == {'ok': True, 'page': 'Delivery', 'year': 2026}


def test_start_pipeline_job_reuses_active_persisted_run(monkeypatch):
    trade_date = dt.date(2026, 3, 17)
    persisted_row = {'run_id': 'delivery-active-run', 'status': 'RUNNING'}
    captured = {}

    monkeypatch.setattr(service, 'ensure_runtime', lambda *args, **kwargs: None)
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

    result = service.start_pipeline_job({'tradeDate': '2026-03-17', 'jobMode': 'pipeline'})

    assert result['jobId'] == 'delivery-active-run'
    assert result['status'] == 'RUNNING'
    assert captured['kwargs']['run_type'] == 'DELIVERY'
    assert 'RUNNING' in captured['kwargs']['statuses']


def test_download_delivery_csv_reuses_local_zip(monkeypatch, tmp_path):
    trade_date = dt.date(2026, 3, 17)
    zip_path = tmp_path / 'sec_bhavdata_full_17032026.zip'
    with zipfile.ZipFile(zip_path, 'w') as archive:
        archive.writestr('sec_bhavdata_full_17032026.csv', 'SYMBOL,SERIES,DELIV_QTY,DELIV_PER\nABC,EQ,100,75\n')

    monkeypatch.setattr(service, '_DOWNLOAD_DIR', tmp_path)
    monkeypatch.setattr(service, 'ensure_runtime', lambda *args, **kwargs: None)

    result = service.download_delivery_csv(trade_date)

    assert result == tmp_path / 'sec_bhavdata_full_17032026.csv'
    assert 'ABC' in result.read_text(encoding='utf-8')


def test_inspect_delivery_csv_filters_allowed_symbols(tmp_path):
    trade_date = dt.date(2026, 3, 17)
    csv_path = tmp_path / 'sec_bhavdata_full_17032026.csv'
    csv_path.write_text(
        'SYMBOL,SERIES,DELIV_QTY,DELIV_PER,CLOSE_PRICE,TTL_TRD_QNTY\nABC,EQ,100,75,10,1000\nXYZ,EQ,200,80,20,2000\nDEF,BE,300,90,30,3000\n',
        encoding='utf-8',
    )

    result = service.inspect_delivery_csv(csv_path, trade_date, eq_only=True, allowed_symbols=['ABC'])

    assert result['matchedRows'] == 1
    assert result['matchedSymbols'] == ['ABC']
    assert result['seriesSkippedRows'] == 1
    assert result['universeSkippedRows'] == 1


def test_load_delivery_csv_filters_to_allowed_symbols(monkeypatch, tmp_path):
    trade_date = dt.date(2026, 3, 17)
    csv_path = tmp_path / 'sec_bhavdata_full_17032026.csv'
    csv_path.write_text(
        'SYMBOL,SERIES,DELIV_QTY,DELIV_PER,CLOSE_PRICE,TTL_TRD_QNTY\nABC,EQ,100,75,10,1000\nXYZ,EQ,200,80,20,2000\n',
        encoding='utf-8',
    )
    upserts = []

    monkeypatch.setattr(service, 'ensure_runtime', lambda *args, **kwargs: None)
    monkeypatch.setattr(service, '_upsert_records', lambda records: (upserts.extend(records) or (len(records), 0)))

    result = service.load_delivery_csv(csv_path, trade_date, eq_only=True, allowed_symbols=['ABC'])

    assert result['loadedCount'] == 1
    assert result['universeSkippedCount'] == 1
    assert [row['symbol'] for row in upserts] == ['ABC']


def test_load_delivery_csv_skip_if_existing_skips_existing_records(monkeypatch, tmp_path):
    trade_date = dt.date(2026, 3, 17)
    csv_path = tmp_path / 'sec_bhavdata_full_17032026.csv'
    csv_path.write_text(
        'SYMBOL,SERIES,DELIV_QTY,DELIV_PER,CLOSE_PRICE,TTL_TRD_QNTY\nABC,EQ,100,75,10,1000\nXYZ,EQ,200,80,20,2000\n',
        encoding='utf-8',
    )
    upserts = []

    monkeypatch.setattr(service, 'ensure_runtime', lambda *args, **kwargs: None)
    monkeypatch.setattr(service, '_existing_file_symbols', lambda *args, **kwargs: {'ABC'})
    monkeypatch.setattr(service, '_upsert_records', lambda records: (upserts.extend(records) or (len(records), 0)))

    result = service.load_delivery_csv(csv_path, trade_date, eq_only=True, skip_if_existing=True)

    assert result['loadedCount'] == 1
    assert result['alreadyLoadedCount'] == 1
    assert result['duplicateCount'] == 1
    assert [row['symbol'] for row in upserts] == ['XYZ']


def test_trade_date_from_delivery_csv_parses_filename():
    assert service._trade_date_from_delivery_csv(Path('sec_bhavdata_full_23042026.csv')) == dt.date(2026, 4, 23)
    assert service._trade_date_from_delivery_csv(Path('delivery.csv')) is None


def test_process_existing_csv_for_symbols_api_forwards_to_shared_service(monkeypatch, tmp_path):
    monkeypatch.setattr(service, '_DOWNLOAD_DIR', tmp_path)
    captured = {}

    def fake_process(symbols_input, config, **kwargs):
        captured['symbols_input'] = symbols_input
        captured['config'] = config
        captured['kwargs'] = kwargs
        return {'ok': True, 'status': 'success', 'dataset_type': 'delivery_data'}

    monkeypatch.setattr(service.existing_csv_svc, 'process_existing_csv_for_symbols', fake_process)

    result = service.process_existing_csv_for_symbols_api({'symbols': 'ITC,RELIANCE'})

    assert result['ok'] is True
    assert captured['symbols_input'] == 'ITC,RELIANCE'
    assert captured['config'].dataset_type == 'delivery_data'
    assert captured['config'].download_dir == tmp_path
    assert captured['config'].use_load_result_for_matching is True


def test_download_api_single_skips_when_trade_date_already_loaded(monkeypatch):
    trade_date = dt.date(2026, 3, 17)

    monkeypatch.setattr(service, '_existing_file_row_count', lambda *_args, **_kwargs: 42)
    monkeypatch.setattr(
        service,
        'download_delivery_csv',
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('download_delivery_csv should not be called')),
    )

    result = service._download_api_single(trade_date, True, {'ABC'})

    assert result['ok'] is True
    assert result['downloadPath'] is None
    assert result['inspection']['alreadyLoaded'] is True
    assert result['inspection']['alreadyLoadedCount'] == 42
    assert 'already data inserted' in result['message'].lower()


def test_run_pipeline_single_marks_failed_insert_when_no_rows_written(monkeypatch, tmp_path):
    trade_date = dt.date(2026, 3, 30)
    csv_path = tmp_path / 'sec_bhavdata_full_30032026.csv'

    monkeypatch.setattr(service, '_existing_file_row_count', lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(service, 'download_delivery_csv', lambda *args, **kwargs: csv_path)
    monkeypatch.setattr(service, 'inspect_delivery_csv', lambda *args, **kwargs: {'matchedRows': 2, 'matchedSymbolsCount': 2})
    monkeypatch.setattr(
        service,
        'load_delivery_csv',
        lambda *args, **kwargs: {'inputRows': 2, 'loadedCount': 0, 'failureCount': 2, 'skippedCount': 0, 'universeSkippedCount': 0},
    )

    result = service._run_pipeline_single(trade_date, True, {'ABC'})

    assert result['ok'] is False
    assert 'failed during oracle insert' in result['message'].lower()


def test_run_pipeline_single_skips_when_trade_date_already_loaded(monkeypatch):
    trade_date = dt.date(2026, 3, 30)

    monkeypatch.setattr(service, '_existing_file_row_count', lambda *_args, **_kwargs: 12)
    monkeypatch.setattr(
        service,
        'download_delivery_csv',
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('download_delivery_csv should not be called')),
    )
    monkeypatch.setattr(service, '_get_dashboard_single', lambda *_args, **_kwargs: {'summary': {'totalRows': 12}})

    result = service._run_pipeline_single(trade_date, True, {'ABC'})

    assert result['ok'] is True
    assert result['downloadPath'] is None
    assert result['inspection']['alreadyLoaded'] is True
    assert result['load']['alreadyLoaded'] is True
    assert result['summary']['totalRows'] == 12


def test_get_dashboard_max_range_uses_all_data(monkeypatch):
    called = {'all': [], 'parse': []}

    monkeypatch.setattr(
        service,
        '_get_dashboard_all',
        lambda limit=None: called['all'].append(limit) or {'ok': True, 'summary': {'totalRows': 0}},
    )
    monkeypatch.setattr(
        service.mcap,
        '_parse_trade_dates',
        lambda *args, **kwargs: called['parse'].append((args, kwargs)) or [dt.date(2026, 3, 19)],
    )

    result = service.get_dashboard(limit=44, range_text='max')

    assert result['ok'] is True
    assert called['all'] == [44]
    assert called['parse'] == []


def test_upsert_records_omits_id_from_delivery_update_binds(monkeypatch):
    execute_calls = []

    class FakeCursor:
        rowcount = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, binds=None):
            execute_calls.append((sql, dict(binds or {})))
            normalized_sql = sql.lstrip()
            if normalized_sql == 'SAVEPOINT NSE_DELIVERY_UPSERT_SP':
                return
            if normalized_sql == 'ROLLBACK TO SAVEPOINT NSE_DELIVERY_UPSERT_SP':
                return
            if normalized_sql.startswith('UPDATE '):
                assert 'id' not in binds
                self.rowcount = 0
                return
            if normalized_sql.startswith('INSERT INTO '):
                assert binds['id'] == 11
                self.rowcount = 1
                return
            raise AssertionError(f'Unexpected SQL: {sql}')

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def commit(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr(service.mcap.pool, 'acquire', lambda: FakeConn())
    monkeypatch.setattr(service, 'ensure_runtime', lambda *args, **kwargs: None)
    monkeypatch.setattr(service.mcap, '_table_supports_implicit_id', lambda conn, table: False)
    monkeypatch.setattr(
        service.mcap,
        '_assign_missing_record_ids',
        lambda conn, table, records, force=False: records[0].update({'id': 11}) or True,
    )

    success_count, failure_count, skipped_count = service._upsert_records([service._record('ABC', dt.date(2026, 3, 30), delivery_qty=10, delivery_pct=60)])

    assert success_count == 1
    assert failure_count == 0
    assert skipped_count == 0
    assert any(sql.lstrip().startswith('UPDATE ') for sql, _binds in execute_calls)
    assert any(sql.lstrip().startswith('INSERT INTO ') for sql, _binds in execute_calls)


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
    monkeypatch.setattr(service, 'ensure_runtime', lambda *args, **kwargs: None)
    monkeypatch.setattr(service.mcap, '_save_run_start', lambda *args, **kwargs: saved.update({'start': args}))
    monkeypatch.setattr(service.mcap, '_save_run_finish', lambda *args, **kwargs: saved.update({'finish': args}))
    monkeypatch.setattr(service, 'run_pipeline', lambda payload, line_logger=None: {'ok': True, 'message': 'done', 'downloadPath': 'C:/temp/delivery.csv'})

    result = service.start_pipeline_job({'tradeDate': '2026-03-17'})
    job = service.get_job(result['jobId'])

    assert result['ok'] is True
    assert result['jobMode'] == 'pipeline'
    assert job['done'] is True
    assert job['status'] == 'SUCCESS'
    assert job['jobMode'] == 'pipeline'
    assert saved['start'] is not None
    assert saved['finish'] is not None


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
    monkeypatch.setattr(service.mcap, '_save_run_start', lambda *args, **kwargs: saved.update({'start': args}))
    monkeypatch.setattr(service.mcap, '_save_run_finish', lambda *args, **kwargs: saved.update({'finish': args}))
    monkeypatch.setattr(service, 'download_api', lambda payload: {'ok': True, 'message': 'download complete', 'downloadPath': 'C:/temp/delivery.csv'})
    monkeypatch.setattr(service, 'run_pipeline', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('run_pipeline should not be called for download-only jobs')))

    result = service.start_pipeline_job({'tradeDate': '2026-03-17', 'jobMode': 'download'})
    job = service.get_job(result['jobId'])

    assert result['ok'] is True
    assert result['jobMode'] == 'download'
    assert job['done'] is True
    assert job['status'] == 'SUCCESS'
    assert job['jobMode'] == 'download'
    assert job['downloadPath'] == 'C:/temp/delivery.csv'
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
            line_logger(service.mcap._flow_marker('validate', 'Validating NSE delivery CSV.'))
            line_logger(service.mcap._flow_marker('process', 'Loading NSE delivery rows into Oracle.'))
        return {'ok': True, 'message': 'done', 'downloadPath': 'C:/temp/delivery.csv'}

    monkeypatch.setattr(service.threading, 'Thread', ImmediateThread)
    monkeypatch.setattr(service, 'ensure_runtime', lambda *args, **kwargs: None)
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


def test_start_pipeline_job_marks_success_stage_while_finalizing(monkeypatch):
    service._JOBS.clear()
    observed = {}

    class ImmediateThread:
        def __init__(self, target=None, daemon=None, name=None):
            self._target = target

        def start(self):
            if self._target:
                self._target()

    def fake_run_pipeline(payload, line_logger=None):
        if line_logger:
            line_logger(service.mcap._flow_marker('validate', 'Validating NSE delivery CSV.'))
            line_logger(service.mcap._flow_marker('process', 'Loading NSE delivery rows into Oracle.'))
        return {'ok': True, 'message': 'done', 'downloadPath': 'C:/temp/delivery.csv'}

    def fake_enrich_job_result(payload, result):
        current = next(iter(service._JOBS.values()))
        observed['activeKey'] = current['flow']['activeKey']
        observed['processCompleted'] = current['flow']['completed']['process']
        observed['successCompleted'] = current['flow']['completed']['success']
        observed['message'] = current['message']
        return {**result, 'stats': service.mcap._empty_job_stats(), 'latestRows': []}

    monkeypatch.setattr(service.threading, 'Thread', ImmediateThread)
    monkeypatch.setattr(service, 'ensure_runtime', lambda *args, **kwargs: None)
    monkeypatch.setattr(service.mcap, '_save_run_start', lambda *args, **kwargs: None)
    monkeypatch.setattr(service.mcap, '_save_run_finish', lambda *args, **kwargs: None)
    monkeypatch.setattr(service, 'run_pipeline', fake_run_pipeline)
    monkeypatch.setattr(service, '_enrich_job_result', fake_enrich_job_result)

    service.start_pipeline_job({'tradeDate': '2026-03-17'})

    assert observed['activeKey'] == 'success'
    assert observed['processCompleted'] is True
    assert observed['successCompleted'] is False
    assert 'finalizing nse delivery pipeline results' in observed['message'].lower()


def test_candidate_specs_prioritize_products_content_urls():
    trade_date = dt.date(2026, 3, 17)

    specs = service._candidate_specs(trade_date)

    assert specs[0][0] == 'products_delivery_csv'
    assert '/products/content/sec_bhavdata_full_17032026.csv' in specs[0][1]
    assert any(key == 'legacy_products_delivery_csv' for key, _ in specs)

def test_process_api_range_skips_unavailable_trade_dates(monkeypatch):
    date_one = dt.date(2026, 3, 17)
    date_two = dt.date(2026, 3, 18)

    monkeypatch.setattr(service, '_parse_runtime_payload', lambda payload, line_logger=None: ([date_one, date_two], True, {'ABC'}))

    def fake_process_single(trade_date, eq_only, allowed_symbols, line_logger=None):
        if trade_date == date_one:
            raise RuntimeError('Unable to download NSE delivery CSV for 2026-03-17: missing archive')
        return {
            'ok': True,
            'message': 'processed',
            'tradeDate': trade_date.strftime('%Y-%m-%d'),
            'downloadPath': 'C:/temp/sec_bhavdata_full_18032026.csv',
            'inspection': {
                'headers': ['SYMBOL'],
                'inputRows': 1,
                'matchedRows': 1,
                'matchedSymbols': ['ABC'],
                'matchedSymbolsCount': 1,
                'parseErrorRows': 0,
                'skippedRows': 0,
                'blankRows': 0,
                'seriesSkippedRows': 0,
                'universeSkippedRows': 0,
            },
            'load': {
                'inputRows': 1,
                'loadedCount': 1,
                'failureCount': 0,
                'skippedCount': 0,
                'universeSkippedCount': 0,
            },
        }

    monkeypatch.setattr(service, '_process_api_single', fake_process_single)
    monkeypatch.setattr(service, 'get_dashboard', lambda *args, **kwargs: {'summary': {'totalRows': 1, 'deliveryRows': 1}})

    result = service.process_api({'startDate': '2026-03-17', 'endDate': '2026-03-18'})

    assert result['ok'] is True
    assert result['dateCount'] == 2
    assert result['processedDateCount'] == 1
    assert result['skippedUnavailableDateCount'] == 1
    assert result['load']['loadedCount'] == 1
    assert result['summary']['totalRows'] == 1
    assert '17-03-2026' in result['message']


def test_run_pipeline_persists_delivery_automation_run(monkeypatch):
    trade_date = dt.date(2026, 3, 17)
    persisted = {}

    monkeypatch.setattr(service, '_parse_runtime_payload', lambda payload, line_logger=None: ([trade_date], True, {'ABC'}))
    monkeypatch.setattr(service, '_run_pipeline_single', lambda *args, **kwargs: {'ok': True, 'status': 'SUCCESS', 'tradeDate': '2026-03-17', '_durations': {'successSeconds': 1.0}})
    monkeypatch.setattr(service, '_enrich_pipeline_response', lambda result, durations=None: {**result, 'durations': durations})
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

    result = service.run_pipeline({'tradeDate': '2026-03-17'})

    assert result['mode'] == 'AUTOMATION'
    assert persisted['run_type'] == service._RUN_TYPE
    assert persisted['trade_date'] == trade_date
    assert persisted['mode'] == 'AUTOMATION'
    assert persisted['stage'] == 'pipeline'

