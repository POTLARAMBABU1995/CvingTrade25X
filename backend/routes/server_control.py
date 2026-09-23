from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any, Dict

from flask import Blueprint, jsonify, request


try:
    from ..services.ui_notification_service import list_notifications
except ImportError:  # pragma: no cover
    from services.ui_notification_service import list_notifications  # type: ignore


bp = Blueprint('server_control', __name__)
_logger = logging.getLogger(__name__)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_START_SCRIPT = _PROJECT_ROOT / 'start_cvingtrade25x_hidden.vbs'
_STOP_SCRIPT = _PROJECT_ROOT / 'stop_cvingtrade25x.bat'
_DETACH_FLAGS = getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)


def _script_payload(server_state: str = 'UP') -> Dict[str, Any]:
    return {
        'projectRoot': str(_PROJECT_ROOT),
        'startScript': str(_START_SCRIPT),
        'stopScript': str(_STOP_SCRIPT),
        'startExists': _START_SCRIPT.exists(),
        'stopExists': _STOP_SCRIPT.exists(),
        'serverState': str(server_state or 'UP').upper(),
    }


def _ensure_script_exists(script_path: Path) -> None:
    if not script_path.exists():
        raise FileNotFoundError(f'Script not found: {script_path}')


def _launch_start_script() -> None:
    _ensure_script_exists(_START_SCRIPT)
    subprocess.Popen(
        ['wscript.exe', str(_START_SCRIPT)],
        cwd=str(_PROJECT_ROOT),
        creationflags=_DETACH_FLAGS,
    )


def _launch_stop_script() -> None:
    _ensure_script_exists(_STOP_SCRIPT)
    command = f'ping 127.0.0.1 -n 2 >nul && call "{_STOP_SCRIPT}"'
    subprocess.Popen(
        ['cmd.exe', '/c', command],
        cwd=str(_PROJECT_ROOT),
        creationflags=_DETACH_FLAGS,
    )


def _launch_restart_script() -> None:
    _ensure_script_exists(_STOP_SCRIPT)
    _ensure_script_exists(_START_SCRIPT)
    command = (
        f'ping 127.0.0.1 -n 2 >nul && '
        f'call "{_STOP_SCRIPT}" && '
        f'ping 127.0.0.1 -n 4 >nul && '
        f'wscript.exe "{_START_SCRIPT}"'
    )
    subprocess.Popen(
        ['cmd.exe', '/c', command],
        cwd=str(_PROJECT_ROOT),
        creationflags=_DETACH_FLAGS,
    )


@bp.get('/api/server-control/status')
def api_server_control_status():
    return jsonify({'ok': True, **_script_payload('UP')})


@bp.post('/api/server-control/start')
def api_server_control_start():
    try:
        _launch_start_script()
        return jsonify({
            'ok': True,
            'action': 'start',
            'message': 'Startup requested using start_cvingtrade25x_hidden.vbs.',
            **_script_payload('STARTING'),
        })
    except FileNotFoundError as exc:
        return jsonify({'ok': False, 'detail': str(exc), **_script_payload('DOWN')}), 404
    except Exception as exc:  # pragma: no cover
        _logger.exception('Server startup request failed')
        return jsonify({'ok': False, 'detail': str(exc), **_script_payload('DOWN')}), 500


@bp.post('/api/server-control/stop')
def api_server_control_stop():
    try:
        _launch_stop_script()
        return jsonify({
            'ok': True,
            'action': 'stop',
            'message': 'Shutdown requested using stop_cvingtrade25x.bat. The backend may go offline shortly.',
            **_script_payload('STOPPING'),
        })
    except FileNotFoundError as exc:
        return jsonify({'ok': False, 'detail': str(exc), **_script_payload('DOWN')}), 404
    except Exception as exc:  # pragma: no cover
        _logger.exception('Server shutdown request failed')
        return jsonify({'ok': False, 'detail': str(exc), **_script_payload('DOWN')}), 500


@bp.post('/api/server-control/restart')
def api_server_control_restart():
    try:
        _launch_restart_script()
        return jsonify({
            'ok': True,
            'action': 'restart',
            'message': 'Restart requested using stop_cvingtrade25x.bat and start_cvingtrade25x_hidden.vbs.',
            **_script_payload('RESTARTING'),
        })
    except FileNotFoundError as exc:
        return jsonify({'ok': False, 'detail': str(exc), **_script_payload('DOWN')}), 404
    except Exception as exc:  # pragma: no cover
        _logger.exception('Server restart request failed')
        return jsonify({'ok': False, 'detail': str(exc), **_script_payload('DOWN')}), 500


@bp.get('/api/server-control/notifications')
def api_server_control_notifications():
    since_ts = request.args.get('sinceTs', default=0, type=int)
    if since_ts in (None, 0):
        since_ts = request.args.get('since', default=0, type=int) or 0
    limit = request.args.get('limit', default=20, type=int) or 20
    return jsonify({
        'ok': True,
        'items': list_notifications(since_ts=since_ts, limit=limit),
    })

