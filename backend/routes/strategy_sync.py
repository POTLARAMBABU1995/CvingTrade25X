from __future__ import annotations

import logging
from typing import Any, Dict

from flask import Blueprint, jsonify, request

try:
    from ..services.strategy_sync import run_strategy_sync
except ImportError:  # pragma: no cover
    from services.strategy_sync import run_strategy_sync  # type: ignore


bp = Blueprint('strategy_sync', __name__)
_logger = logging.getLogger(__name__)


@bp.route('/api/strategy/sync', methods=['GET', 'POST'])
def api_strategy_sync():
    payload: Dict[str, Any] = request.get_json(silent=True) or {}
    strategy = (payload.get('strategy') or request.args.get('strategy') or '').strip()
    timeframe = (payload.get('timeframe') or request.args.get('timeframe') or 'daily').strip().lower()
    min_signal = payload.get('min_signal', request.args.get('min_signal'))
    min_adx = payload.get('min_adx', request.args.get('min_adx'))
    breakout_only = payload.get('breakout_only', request.args.get('breakout_only'))

    if not strategy:
        return jsonify({'detail': 'strategy is required'}), 400

    try:
        result = run_strategy_sync(
            strategy,
            timeframe=timeframe,
            min_signal=min_signal,
            min_adx=min_adx,
            breakout_only=bool(int(breakout_only)) if str(breakout_only).strip() else False,
        )
        return jsonify({'ok': True, 'strategy': strategy, 'result': result})
    except ValueError as exc:
        return jsonify({'ok': False, 'detail': str(exc)}), 400
    except Exception as exc:  # pragma: no cover
        _logger.exception('Strategy sync failed')
        return jsonify({'ok': False, 'detail': str(exc)}), 500
