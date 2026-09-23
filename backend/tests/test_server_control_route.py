from pathlib import Path
import sys

from flask import Flask


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import routes.server_control as server_control_route


def test_server_control_status_returns_script_metadata(monkeypatch):
    monkeypatch.setattr(
        server_control_route,
        '_script_payload',
        lambda server_state='UP': {
            'projectRoot': 'C:/repo',
            'startScript': 'C:/repo/start_cvingtrade25x_hidden.vbs',
            'stopScript': 'C:/repo/stop_cvingtrade25x.bat',
            'startExists': True,
            'stopExists': True,
        },
    )

    app = Flask(__name__)
    app.register_blueprint(server_control_route.bp)
    client = app.test_client()

    response = client.get('/api/server-control/status')
    assert response.status_code == 200

    payload = response.get_json()
    assert payload['ok'] is True
    assert payload['startExists'] is True
    assert payload['stopExists'] is True


def test_server_control_start_calls_launch(monkeypatch):
    launch_calls = {'count': 0}
    monkeypatch.setattr(server_control_route, '_launch_start_script', lambda: launch_calls.__setitem__('count', launch_calls['count'] + 1))
    monkeypatch.setattr(
        server_control_route,
        '_script_payload',
        lambda server_state='UP': {
            'projectRoot': 'C:/repo',
            'startScript': 'C:/repo/start_cvingtrade25x_hidden.vbs',
            'stopScript': 'C:/repo/stop_cvingtrade25x.bat',
            'startExists': True,
            'stopExists': True,
        },
    )

    app = Flask(__name__)
    app.register_blueprint(server_control_route.bp)
    client = app.test_client()

    response = client.post('/api/server-control/start')
    assert response.status_code == 200

    payload = response.get_json()
    assert payload['ok'] is True
    assert payload['action'] == 'start'
    assert launch_calls['count'] == 1


def test_server_control_stop_calls_launch(monkeypatch):
    launch_calls = {'count': 0}
    monkeypatch.setattr(server_control_route, '_launch_stop_script', lambda: launch_calls.__setitem__('count', launch_calls['count'] + 1))
    monkeypatch.setattr(
        server_control_route,
        '_script_payload',
        lambda server_state='UP': {
            'projectRoot': 'C:/repo',
            'startScript': 'C:/repo/start_cvingtrade25x_hidden.vbs',
            'stopScript': 'C:/repo/stop_cvingtrade25x.bat',
            'startExists': True,
            'stopExists': True,
        },
    )

    app = Flask(__name__)
    app.register_blueprint(server_control_route.bp)
    client = app.test_client()

    response = client.post('/api/server-control/stop')
    assert response.status_code == 200

    payload = response.get_json()
    assert payload['ok'] is True
    assert payload['action'] == 'stop'
    assert launch_calls['count'] == 1


def test_server_control_restart_calls_launch(monkeypatch):
    launch_calls = {'count': 0}
    monkeypatch.setattr(server_control_route, '_launch_restart_script', lambda: launch_calls.__setitem__('count', launch_calls['count'] + 1))
    monkeypatch.setattr(
        server_control_route,
        '_script_payload',
        lambda server_state='UP': {
            'projectRoot': 'C:/repo',
            'startScript': 'C:/repo/start_cvingtrade25x_hidden.vbs',
            'stopScript': 'C:/repo/stop_cvingtrade25x.bat',
            'startExists': True,
            'stopExists': True,
        },
    )

    app = Flask(__name__)
    app.register_blueprint(server_control_route.bp)
    client = app.test_client()

    response = client.post('/api/server-control/restart')
    assert response.status_code == 200

    payload = response.get_json()
    assert payload['ok'] is True
    assert payload['action'] == 'restart'
    assert launch_calls['count'] == 1

