from pathlib import Path
import sys

from flask import Flask


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import routes.strategy_agent as strategy_agent_route


def test_status_includes_execution_payload(monkeypatch):
    monkeypatch.setattr(
        strategy_agent_route,
        'get_strategy_agent_status',
        lambda strategy: {
            'ok': True,
            'summary': {'successRate': 50.0},
            'params': {},
            'lastRun': None,
        },
    )
    monkeypatch.setattr(
        strategy_agent_route,
        'get_strategy_agent_execution',
        lambda strategy_name=None, job_id=None: {
            'jobId': 'job-1',
            'strategy': strategy_name,
            'status': 'RUNNING',
            'message': 'Running on backend.',
        },
    )

    app = Flask(__name__)
    app.register_blueprint(strategy_agent_route.bp)
    client = app.test_client()

    response = client.get('/api/strategy-agent/status?strategy=yamuna')
    assert response.status_code == 200

    payload = response.get_json()
    assert payload['ok'] is True
    assert payload['execution']['jobId'] == 'job-1'
    assert payload['execution']['strategy'] == 'yamuna'


def test_run_returns_background_job_metadata(monkeypatch):
    monkeypatch.setattr(
        strategy_agent_route,
        'start_strategy_agent_execution',
        lambda strategy, run_source='manual': {
            'job': {
                'jobId': 'job-2',
                'strategy': strategy,
                'status': 'QUEUED',
                'message': 'Run queued on backend.',
            },
            'alreadyRunning': False,
        },
    )

    app = Flask(__name__)
    app.register_blueprint(strategy_agent_route.bp)
    client = app.test_client()

    response = client.post('/api/strategy-agent/run', json={'strategy': 'asura', 'source': 'ui'})
    assert response.status_code == 200

    payload = response.get_json()
    assert payload['ok'] is True
    assert payload['alreadyRunning'] is False
    assert payload['job']['jobId'] == 'job-2'
    assert payload['job']['strategy'] == 'asura'


def test_cancel_returns_cancel_state(monkeypatch):
    monkeypatch.setattr(
        strategy_agent_route,
        'cancel_strategy_agent_execution',
        lambda strategy_name=None, job_id=None: {
            'job': {
                'jobId': job_id,
                'strategy': strategy_name,
                'status': 'CANCELLING',
                'message': 'Cancellation requested. Stopping after the current backend step...',
            },
            'cancelAccepted': True,
        },
    )

    app = Flask(__name__)
    app.register_blueprint(strategy_agent_route.bp)
    client = app.test_client()

    response = client.post('/api/strategy-agent/cancel', json={'strategy': 'yamuna', 'jobId': 'job-3'})
    assert response.status_code == 200

    payload = response.get_json()
    assert payload['ok'] is True
    assert payload['cancelAccepted'] is True
    assert payload['job']['jobId'] == 'job-3'
    assert payload['job']['strategy'] == 'yamuna'
