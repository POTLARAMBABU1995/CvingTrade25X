from __future__ import annotations

import logging
from typing import Any, Dict

from flask import Blueprint, jsonify, request

try:
    from ..services.strategy_agent_runtime_service import (
        cancel_strategy_agent_execution,
        get_strategy_agent_execution,
        start_strategy_agent_execution,
    )
    from ..services.strategy_agent_service import (
        get_strategy_agent_backtests,
        get_strategy_agent_status,
    )
except ImportError:  # pragma: no cover
    from services.strategy_agent_runtime_service import (  # type: ignore
        cancel_strategy_agent_execution,
        get_strategy_agent_execution,
        start_strategy_agent_execution,
    )
    from services.strategy_agent_service import (  # type: ignore
        get_strategy_agent_backtests,
        get_strategy_agent_status,
    )


bp = Blueprint('strategy_agent', __name__)
_logger = logging.getLogger(__name__)


@bp.get('/api/strategy-agent/status')
def api_strategy_agent_status():
    strategy = (request.args.get('strategy') or 'asura').strip().lower()
    try:
        payload = get_strategy_agent_status(strategy)
        payload['execution'] = get_strategy_agent_execution(strategy_name=strategy)
        return jsonify(payload)
    except ValueError as exc:
        return jsonify({'ok': False, 'detail': str(exc)}), 400
    except Exception as exc:  # pragma: no cover
        _logger.exception('Strategy agent status failed')
        return jsonify({'ok': False, 'detail': str(exc)}), 500


@bp.get('/api/strategy-agent/backtests')
def api_strategy_agent_backtests():
    strategy = (request.args.get('strategy') or 'asura').strip().lower()
    limit_raw = request.args.get('limit')
    try:
        limit = int(limit_raw) if limit_raw else 50
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'detail': 'limit must be an integer'}), 400
    try:
        return jsonify(get_strategy_agent_backtests(strategy, limit=limit))
    except ValueError as exc:
        return jsonify({'ok': False, 'detail': str(exc)}), 400
    except Exception as exc:  # pragma: no cover
        _logger.exception('Strategy agent backtests failed')
        return jsonify({'ok': False, 'detail': str(exc)}), 500


@bp.post('/api/strategy-agent/run')
def api_strategy_agent_run():
    payload: Dict[str, Any] = request.get_json(silent=True) or {}
    strategy = (payload.get('strategy') or request.args.get('strategy') or 'all').strip().lower()
    run_source = (payload.get('source') or request.args.get('source') or 'manual').strip().lower()
    try:
        result = start_strategy_agent_execution(strategy, run_source=run_source)
        return jsonify({'ok': True, **result})
    except ValueError as exc:
        return jsonify({'ok': False, 'detail': str(exc)}), 400
    except Exception as exc:  # pragma: no cover
        _logger.exception('Strategy agent run failed')
        return jsonify({'ok': False, 'detail': str(exc)}), 500


@bp.post('/api/strategy-agent/cancel')
def api_strategy_agent_cancel():
    payload: Dict[str, Any] = request.get_json(silent=True) or {}
    strategy = (payload.get('strategy') or request.args.get('strategy') or '').strip().lower() or None
    job_id = (payload.get('jobId') or request.args.get('jobId') or '').strip() or None
    if not strategy and not job_id:
        return jsonify({'ok': False, 'detail': 'strategy or jobId is required'}), 400
    try:
        result = cancel_strategy_agent_execution(strategy_name=strategy, job_id=job_id)
        return jsonify({'ok': True, **result})
    except ValueError as exc:
        return jsonify({'ok': False, 'detail': str(exc)}), 404
    except Exception as exc:  # pragma: no cover
        _logger.exception('Strategy agent cancel failed')
        return jsonify({'ok': False, 'detail': str(exc)}), 500
