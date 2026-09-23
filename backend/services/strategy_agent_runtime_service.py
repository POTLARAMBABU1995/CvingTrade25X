from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

try:
    from ..services.strategy_agent_service import (
        DEFAULT_STRATEGY_PARAMS,
        run_all_strategy_agent_cycles,
        run_strategy_agent_cycle,
    )
except ImportError:  # pragma: no cover
    from services.strategy_agent_service import (  # type: ignore
        DEFAULT_STRATEGY_PARAMS,
        run_all_strategy_agent_cycles,
        run_strategy_agent_cycle,
    )


_logger = logging.getLogger(__name__)
_ACTIVE_EXECUTION_STATUSES = {'QUEUED', 'RUNNING', 'CANCELLING'}
_TERMINAL_EXECUTION_STATUSES = {'COMPLETED', 'FAILED', 'CANCELLED'}
_EXECUTION_LOCK = threading.Lock()
_ACTIVE_EXECUTIONS: Dict[str, 'StrategyAgentExecution'] = {}
_LATEST_EXECUTIONS: Dict[str, 'StrategyAgentExecution'] = {}
_EXECUTIONS_BY_ID: Dict[str, 'StrategyAgentExecution'] = {}
_AUTO_SCHEDULER_STARTED = False
_INTERACTIVE_RUN_SOURCES = {'manual', 'ui'}
_BACKGROUND_EXECUTION_ENABLED = os.getenv('STRATEGY_AGENT_BACKGROUND_ENABLED', '0').strip().lower() not in {'0', 'false', 'no'}
_AUTO_SCHEDULER_ENABLED = _BACKGROUND_EXECUTION_ENABLED and os.getenv('STRATEGY_AGENT_AUTO_RUN_ENABLED', '1').strip().lower() not in {'0', 'false', 'no'}
_AUTO_SCHEDULER_INTERVAL_SECONDS = max(300, int(float(os.getenv('STRATEGY_AGENT_AUTO_RUN_INTERVAL_MINUTES', '60')) * 60))
_AUTO_SCHEDULER_STARTUP_DELAY_SECONDS = max(15, int(os.getenv('STRATEGY_AGENT_AUTO_RUN_STARTUP_DELAY_SECONDS', '60')))


class StrategyAgentExecutionCancelled(RuntimeError):
    pass


@dataclass
class StrategyAgentExecution:
    job_id: str
    strategy_name: str
    run_source: str
    requested_at: datetime
    status: str = 'QUEUED'
    stage: str = 'QUEUED'
    message: str = 'Run queued on backend.'
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    cancel_requested_at: Optional[datetime] = None
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    progress: Dict[str, Any] = field(default_factory=dict)
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False, compare=False)
    thread: Optional[threading.Thread] = field(default=None, repr=False, compare=False)


def _reset_execution_state() -> None:
    with _EXECUTION_LOCK:
        _ACTIVE_EXECUTIONS.clear()
        _LATEST_EXECUTIONS.clear()
        _EXECUTIONS_BY_ID.clear()


def _normalize_strategy_name(strategy_name: str | None) -> str:
    text = str(strategy_name or '').strip().lower()
    if not text or text in {'*', 'all'}:
        return 'all'
    return text


def _validate_strategy_name(strategy_name: str | None) -> str:
    strategy = _normalize_strategy_name(strategy_name)
    if strategy != 'all' and strategy not in DEFAULT_STRATEGY_PARAMS:
        raise ValueError(f'Unsupported strategy {strategy_name!r}')
    return strategy


def _normalize_run_source(run_source: str | None) -> str:
    return (str(run_source or 'manual').strip().lower() or 'manual')


def _is_background_run_source(run_source: str | None) -> bool:
    return _normalize_run_source(run_source) not in _INTERACTIVE_RUN_SOURCES


def _build_paused_job_payload(strategy_name: str, run_source: str) -> Dict[str, Any]:
    requested_at = datetime.utcnow()
    return {
        'jobId': str(uuid.uuid4()),
        'strategy': strategy_name,
        'runSource': run_source,
        'status': 'SKIPPED',
        'stage': 'PAUSED',
        'message': 'Background strategy-agent runs are paused.',
        'requestedAt': _serialize_datetime(requested_at),
        'startedAt': None,
        'finishedAt': _serialize_datetime(requested_at),
        'cancelRequested': False,
        'cancelRequestedAt': None,
        'error': None,
        'progress': {},
        'result': None,
        'active': False,
        'terminal': True,
    }


def _serialize_datetime(value: Optional[datetime]) -> Optional[str]:
    if not value:
        return None
    return value.strftime('%Y-%m-%d %H:%M:%S')


def _is_active_execution(execution: Optional[StrategyAgentExecution]) -> bool:
    return bool(execution and execution.status in _ACTIVE_EXECUTION_STATUSES)


def _summarize_result(result: Optional[Dict[str, Any]], strategy_name: str) -> Optional[Dict[str, Any]]:
    if not isinstance(result, dict):
        return None
    if strategy_name == 'all':
        return {
            'strategyCount': len(result),
            'strategies': list(result.keys()),
        }
    return {
        'runId': result.get('runId'),
        'applied': bool(result.get('applied')),
        'rowsStored': result.get('rowsStored'),
        'selectedSummary': result.get('selectedSummary'),
    }


def _serialize_execution(execution: Optional[StrategyAgentExecution]) -> Optional[Dict[str, Any]]:
    if execution is None:
        return None
    return {
        'jobId': execution.job_id,
        'strategy': execution.strategy_name,
        'runSource': execution.run_source,
        'status': execution.status,
        'stage': execution.stage,
        'message': execution.message,
        'requestedAt': _serialize_datetime(execution.requested_at),
        'startedAt': _serialize_datetime(execution.started_at),
        'finishedAt': _serialize_datetime(execution.finished_at),
        'cancelRequested': execution.cancel_event.is_set(),
        'cancelRequestedAt': _serialize_datetime(execution.cancel_requested_at),
        'error': execution.error,
        'progress': dict(execution.progress or {}),
        'result': _summarize_result(execution.result, execution.strategy_name),
        'active': execution.status in _ACTIVE_EXECUTION_STATUSES,
        'terminal': execution.status in _TERMINAL_EXECUTION_STATUSES,
    }


def _set_execution_state(execution: StrategyAgentExecution, **changes: Any) -> None:
    with _EXECUTION_LOCK:
        for key, value in changes.items():
            setattr(execution, key, value)
        _LATEST_EXECUTIONS[execution.strategy_name] = execution
        _EXECUTIONS_BY_ID[execution.job_id] = execution


def _set_execution_progress(execution: StrategyAgentExecution, payload: Dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        return
    progress = {key: value for key, value in payload.items() if key not in {'stage', 'message'}}
    with _EXECUTION_LOCK:
        if 'stage' in payload and payload['stage']:
            execution.stage = str(payload['stage'])
        if 'message' in payload and payload['message']:
            execution.message = str(payload['message'])
        if progress:
            execution.progress.update(progress)
        _LATEST_EXECUTIONS[execution.strategy_name] = execution
        _EXECUTIONS_BY_ID[execution.job_id] = execution


def _raise_if_cancelled(execution: StrategyAgentExecution) -> None:
    if not execution.cancel_event.is_set():
        return
    with _EXECUTION_LOCK:
        execution.status = 'CANCELLING'
        execution.stage = 'CANCELLING'
        execution.message = 'Cancellation requested. Stopping after the current backend step...'
        execution.cancel_requested_at = execution.cancel_requested_at or datetime.utcnow()
        _LATEST_EXECUTIONS[execution.strategy_name] = execution
        _EXECUTIONS_BY_ID[execution.job_id] = execution
    raise StrategyAgentExecutionCancelled('Run cancelled by user.')


def _build_progress_callback(execution: StrategyAgentExecution):
    def callback(payload: Dict[str, Any]) -> None:
        _raise_if_cancelled(execution)
        _set_execution_progress(execution, payload)
    return callback


def _build_cancel_check(execution: StrategyAgentExecution):
    def cancel_check() -> None:
        _raise_if_cancelled(execution)
    return cancel_check


def _build_completion_message(execution: StrategyAgentExecution, result: Optional[Dict[str, Any]]) -> str:
    if execution.strategy_name == 'all':
        return 'All strategy agent runs completed.'
    if isinstance(result, dict):
        if result.get('applied') is True:
            return f'{execution.strategy_name.upper()} run completed and applied.'
        if result.get('applied') is False:
            return f'{execution.strategy_name.upper()} run completed with no parameter change.'
    return f'{execution.strategy_name.upper()} run completed.'


def _execute_strategy_agent_job(execution: StrategyAgentExecution) -> Dict[str, Any]:
    progress_callback = _build_progress_callback(execution)
    cancel_check = _build_cancel_check(execution)
    progress_callback({
        'stage': 'INITIALIZING',
        'message': f'{execution.strategy_name.upper()}: preparing background run...',
    })
    if execution.strategy_name == 'all':
        return run_all_strategy_agent_cycles(
            run_source=execution.run_source,
            cancel_check=cancel_check,
            progress_callback=progress_callback,
        )
    return run_strategy_agent_cycle(
        execution.strategy_name,
        run_source=execution.run_source,
        cancel_check=cancel_check,
        progress_callback=progress_callback,
    )


def _run_execution_thread(execution: StrategyAgentExecution) -> None:
    _set_execution_state(
        execution,
        status='RUNNING',
        stage='INITIALIZING',
        started_at=datetime.utcnow(),
        message=f'{execution.strategy_name.upper()}: background run started.',
    )
    try:
        result = _execute_strategy_agent_job(execution)
        _set_execution_state(
            execution,
            status='COMPLETED',
            stage='COMPLETED',
            finished_at=datetime.utcnow(),
            message=_build_completion_message(execution, result),
            result=result,
            error=None,
        )
    except StrategyAgentExecutionCancelled as exc:
        _set_execution_state(
            execution,
            status='CANCELLED',
            stage='CANCELLED',
            finished_at=datetime.utcnow(),
            message=str(exc) or 'Run cancelled by user.',
            error=str(exc) or 'cancelled',
        )
    except Exception as exc:  # pragma: no cover
        _logger.exception('Strategy agent background run failed for %s', execution.strategy_name)
        _set_execution_state(
            execution,
            status='FAILED',
            stage='FAILED',
            finished_at=datetime.utcnow(),
            message=f'Run failed: {str(exc)[:200]}',
            error=str(exc),
        )
    finally:
        with _EXECUTION_LOCK:
            active = _ACTIVE_EXECUTIONS.get(execution.strategy_name)
            if active is execution:
                _ACTIVE_EXECUTIONS.pop(execution.strategy_name, None)
            _LATEST_EXECUTIONS[execution.strategy_name] = execution
            _EXECUTIONS_BY_ID[execution.job_id] = execution


def _find_conflicting_execution(strategy_name: str) -> Optional[StrategyAgentExecution]:
    with _EXECUTION_LOCK:
        if strategy_name == 'all':
            for execution in _ACTIVE_EXECUTIONS.values():
                if _is_active_execution(execution):
                    return execution
            return None
        current = _ACTIVE_EXECUTIONS.get(strategy_name)
        if _is_active_execution(current):
            return current
        batch = _ACTIVE_EXECUTIONS.get('all')
        if _is_active_execution(batch):
            return batch
        return None


def _resolve_execution_for_lookup(strategy_name: Optional[str], job_id: Optional[str]) -> Optional[StrategyAgentExecution]:
    execution = None
    if job_id:
        return _EXECUTIONS_BY_ID.get(str(job_id).strip())
    if not strategy_name:
        return None

    strategy = _normalize_strategy_name(strategy_name)
    execution = _ACTIVE_EXECUTIONS.get(strategy) or _LATEST_EXECUTIONS.get(strategy)
    if _is_active_execution(execution):
        return execution

    batch_execution = _ACTIVE_EXECUTIONS.get('all') or _LATEST_EXECUTIONS.get('all')
    if _is_active_execution(batch_execution):
        return batch_execution
    return execution


def start_strategy_agent_execution(strategy_name: str, run_source: str = 'manual') -> Dict[str, Any]:
    strategy = _validate_strategy_name(strategy_name)
    normalized_run_source = _normalize_run_source(run_source)
    if not _BACKGROUND_EXECUTION_ENABLED and _is_background_run_source(normalized_run_source):
        _logger.info(
            'Strategy agent background run skipped for %s source=%s because background execution is paused',
            strategy,
            normalized_run_source,
        )
        return {
            'job': _build_paused_job_payload(strategy, normalized_run_source),
            'alreadyRunning': False,
            'backgroundPaused': True,
        }
    existing = _find_conflicting_execution(strategy)
    if existing is not None:
        return {
            'job': _serialize_execution(existing),
            'alreadyRunning': True,
        }

    execution = StrategyAgentExecution(
        job_id=str(uuid.uuid4()),
        strategy_name=strategy,
        run_source=normalized_run_source,
        requested_at=datetime.utcnow(),
    )
    thread = threading.Thread(
        target=_run_execution_thread,
        args=(execution,),
        name=f'strategy-agent-{strategy}-{execution.job_id[:8]}',
        daemon=True,
    )
    execution.thread = thread
    with _EXECUTION_LOCK:
        _ACTIVE_EXECUTIONS[strategy] = execution
        _LATEST_EXECUTIONS[strategy] = execution
        _EXECUTIONS_BY_ID[execution.job_id] = execution
    thread.start()
    return {
        'job': _serialize_execution(execution),
        'alreadyRunning': False,
    }


def get_strategy_agent_execution(
    strategy_name: Optional[str] = None,
    job_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    with _EXECUTION_LOCK:
        execution = _resolve_execution_for_lookup(strategy_name=strategy_name, job_id=job_id)
        return _serialize_execution(execution)


def cancel_strategy_agent_execution(
    strategy_name: Optional[str] = None,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    execution: Optional[StrategyAgentExecution]
    with _EXECUTION_LOCK:
        execution = _resolve_execution_for_lookup(strategy_name=strategy_name, job_id=job_id)
    if execution is None:
        raise ValueError('No strategy agent execution found to cancel.')
    if not _is_active_execution(execution):
        return {
            'job': _serialize_execution(execution),
            'cancelAccepted': False,
        }
    execution.cancel_event.set()
    _set_execution_state(
        execution,
        status='CANCELLING',
        stage='CANCELLING',
        message='Cancellation requested. Stopping after the current backend step...',
        cancel_requested_at=datetime.utcnow(),
    )
    return {
        'job': _serialize_execution(execution),
        'cancelAccepted': True,
    }



def _scheduled_strategy_names() -> list[str]:
    raw = (os.getenv('STRATEGY_AGENT_AUTO_RUN_STRATEGIES') or 'asura,yamuna,bhramhastra').strip()
    values = [token.strip().lower() for token in raw.split(',') if token.strip()]
    return [name for name in values if name in DEFAULT_STRATEGY_PARAMS]


def _run_scheduler_cycle() -> None:
    for strategy_name in _scheduled_strategy_names():
        try:
            start_strategy_agent_execution(strategy_name, run_source='scheduler')
        except Exception as exc:  # pragma: no cover
            _logger.warning('Strategy agent scheduler failed for %s: %s', strategy_name, exc)


def start_strategy_agent_scheduler() -> None:
    global _AUTO_SCHEDULER_STARTED
    if _AUTO_SCHEDULER_STARTED or not _AUTO_SCHEDULER_ENABLED:
        return
    _AUTO_SCHEDULER_STARTED = True

    def _loop() -> None:
        time.sleep(_AUTO_SCHEDULER_STARTUP_DELAY_SECONDS)
        while True:
            try:
                _run_scheduler_cycle()
            except Exception:  # pragma: no cover
                _logger.exception('Strategy agent scheduler loop failed')
            time.sleep(_AUTO_SCHEDULER_INTERVAL_SECONDS)

    threading.Thread(target=_loop, name='strategy-agent-scheduler', daemon=True).start()

__all__ = [
    'StrategyAgentExecutionCancelled',
    'cancel_strategy_agent_execution',
    'get_strategy_agent_execution',
    'start_strategy_agent_execution',
    'start_strategy_agent_scheduler',
]




