from pathlib import Path
import importlib
import sys
import threading
import time
import types


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _load_runtime_module():
    original_db = sys.modules.get('db')
    original_db_pool = sys.modules.get('db_pool')

    fake_db_pool = types.ModuleType('db_pool')

    class _DummyPool:
        def acquire(self):
            raise AssertionError('Database access is not expected in strategy agent runtime unit tests.')

    fake_db_pool.pool = _DummyPool()

    fake_db = types.ModuleType('db')
    fake_db.fetch_ohlc_series_from_oracle = lambda *args, **kwargs: {}

    sys.modules['db_pool'] = fake_db_pool
    sys.modules['db'] = fake_db
    try:
        service = importlib.import_module('services.strategy_agent_service')
        runtime = importlib.import_module('services.strategy_agent_runtime_service')
        runtime._reset_execution_state()
        return service, runtime
    finally:
        if original_db_pool is not None:
            sys.modules['db_pool'] = original_db_pool
        else:
            sys.modules.pop('db_pool', None)
        if original_db is not None:
            sys.modules['db'] = original_db
        else:
            sys.modules.pop('db', None)


service, runtime = _load_runtime_module()


def test_start_strategy_agent_execution_completes_in_background(monkeypatch):
    runtime._reset_execution_state()
    finished = threading.Event()

    def fake_execute(execution):
        finished.set()
        return {
            'runId': 'run-1',
            'strategy': execution.strategy_name,
            'applied': True,
            'rowsStored': 12,
            'selectedSummary': {'total_trades': 12},
        }

    monkeypatch.setattr(runtime, '_execute_strategy_agent_job', fake_execute)

    started = runtime.start_strategy_agent_execution('yamuna', run_source='ui')
    assert started['alreadyRunning'] is False
    assert started['job']['status'] in {'QUEUED', 'RUNNING', 'COMPLETED'}
    assert finished.wait(1.0)

    execution = runtime.get_strategy_agent_execution(strategy_name='yamuna')
    assert execution is not None
    assert execution['status'] == 'COMPLETED'
    assert execution['result']['runId'] == 'run-1'
    assert execution['result']['rowsStored'] == 12



def test_start_strategy_agent_execution_supports_bhramhastra(monkeypatch):
    runtime._reset_execution_state()
    finished = threading.Event()

    def fake_execute(execution):
        finished.set()
        return {
            'runId': 'run-bhram',
            'strategy': execution.strategy_name,
            'applied': False,
            'rowsStored': 3,
            'selectedSummary': {'total_trades': 3},
        }

    monkeypatch.setattr(runtime, '_execute_strategy_agent_job', fake_execute)

    started = runtime.start_strategy_agent_execution('bhramhastra', run_source='ui')
    assert started['alreadyRunning'] is False
    assert finished.wait(1.0)

    execution = runtime.get_strategy_agent_execution(strategy_name='bhramhastra')
    assert execution is not None
    assert execution['status'] == 'COMPLETED'
    assert execution['result']['runId'] == 'run-bhram'


def test_start_strategy_agent_execution_skips_background_sources_when_paused(monkeypatch):
    runtime._reset_execution_state()

    def fail_if_called(_execution):
        raise AssertionError('Background execution should be skipped while paused.')

    monkeypatch.setattr(runtime, '_BACKGROUND_EXECUTION_ENABLED', False)
    monkeypatch.setattr(runtime, '_execute_strategy_agent_job', fail_if_called)

    started = runtime.start_strategy_agent_execution('bhramhastra', run_source='bhramhastra_auto_insert')

    assert started['alreadyRunning'] is False
    assert started['backgroundPaused'] is True
    assert started['job']['status'] == 'SKIPPED'
    assert started['job']['stage'] == 'PAUSED'
    assert started['job']['message'] == 'Background strategy-agent runs are paused.'
    assert runtime.get_strategy_agent_execution(strategy_name='bhramhastra') is None


def test_cancel_strategy_agent_execution_marks_run_cancelled(monkeypatch):
    runtime._reset_execution_state()
    started = threading.Event()

    def fake_execute(execution):
        started.set()
        while True:
            runtime._raise_if_cancelled(execution)
            time.sleep(0.01)

    monkeypatch.setattr(runtime, '_execute_strategy_agent_job', fake_execute)

    launched = runtime.start_strategy_agent_execution('asura', run_source='ui')
    assert started.wait(1.0)

    cancelled = runtime.cancel_strategy_agent_execution(strategy_name='asura', job_id=launched['job']['jobId'])
    assert cancelled['cancelAccepted'] is True

    deadline = time.time() + 2.0
    while time.time() < deadline:
        execution = runtime.get_strategy_agent_execution(strategy_name='asura')
        if execution and execution['status'] == 'CANCELLED':
            break
        time.sleep(0.02)
    else:
        raise AssertionError('Execution did not reach CANCELLED state in time.')

    execution = runtime.get_strategy_agent_execution(strategy_name='asura')
    assert execution is not None
    assert execution['status'] == 'CANCELLED'
    assert execution['cancelRequested'] is True
    assert execution['message'] == 'Run cancelled by user.'


def test_start_strategy_agent_execution_reuses_active_job(monkeypatch):
    runtime._reset_execution_state()
    started = threading.Event()
    hold = threading.Event()

    def fake_execute(execution):
        started.set()
        hold.wait(1.0)
        return {
            'runId': 'run-hold',
            'strategy': execution.strategy_name,
            'applied': False,
            'rowsStored': 0,
            'selectedSummary': {'total_trades': 0},
        }

    monkeypatch.setattr(runtime, '_execute_strategy_agent_job', fake_execute)

    first = runtime.start_strategy_agent_execution('yamuna', run_source='ui')
    assert started.wait(1.0)
    second = runtime.start_strategy_agent_execution('yamuna', run_source='ui')

    assert first['job']['jobId'] == second['job']['jobId']
    assert second['alreadyRunning'] is True
    hold.set()


def test_strategy_lookup_surfaces_active_batch_execution(monkeypatch):
    runtime._reset_execution_state()
    started = threading.Event()
    release = threading.Event()

    def fake_execute(execution):
        started.set()
        release.wait(1.0)
        return {
            'runId': 'run-all',
            'strategy': execution.strategy_name,
            'applied': False,
            'rowsStored': 0,
            'selectedSummary': {'total_trades': 0},
        }

    monkeypatch.setattr(runtime, '_execute_strategy_agent_job', fake_execute)

    launched = runtime.start_strategy_agent_execution('all', run_source='ui')
    assert started.wait(1.0)

    execution = runtime.get_strategy_agent_execution(strategy_name='yamuna')
    assert execution is not None
    assert execution['jobId'] == launched['job']['jobId']
    assert execution['strategy'] == 'all'
    assert execution['status'] in {'RUNNING', 'COMPLETED'}

    cancelled = runtime.cancel_strategy_agent_execution(strategy_name='yamuna')
    assert cancelled['job']['jobId'] == launched['job']['jobId']
    assert cancelled['cancelAccepted'] is True
    release.set()

