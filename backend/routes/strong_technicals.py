from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from flask import Blueprint, jsonify, request

from services.strong_technicals_service import fetch_strong_technicals_page


bp = Blueprint('strong_technicals', __name__)
_logger = logging.getLogger(__name__)


def _bool_arg(name: str, default: bool = True) -> bool:
  raw = request.args.get(name)
  if raw is None:
    return default
  return str(raw).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}


def _int_arg(name: str, default: int, lower: int, upper: int) -> int:
  try:
    value = int(request.args.get(name, default))
  except (TypeError, ValueError):
    value = default
  return max(lower, min(upper, value))


def _float_arg(name: str) -> Optional[float]:
  raw = request.args.get(name)
  if raw in (None, ''):
    return None
  try:
    return float(raw)
  except (TypeError, ValueError):
    raise ValueError(f'Invalid numeric value for {name}')


def _request_params() -> Dict[str, Any]:
  return {
    'tf': request.args.get('tf', 'daily'),
    'page': _int_arg('page', 1, 1, 100000),
    'page_size': _int_arg('page_size', 50, 1, 500),
    'symbol': request.args.get('symbol', ''),
    'min_score': _float_arg('min_score'),
    'status': request.args.get('status', ''),
    'pattern': request.args.get('pattern', ''),
    'breakout_status': request.args.get('breakout_status', ''),
    'breakout_flag': request.args.get('breakout_flag', ''),
    'trendline_status': request.args.get('trendline_status', ''),
    'risk_level': request.args.get('risk_level', ''),
    'latest_only': _bool_arg('latest_only', True),
    'sort_by': request.args.get('sort_by', 'techScoreSort'),
    'sort_dir': request.args.get('sort_dir', 'desc'),
    'refresh': _bool_arg('refresh', False),
  }


@bp.get('/api/technicals/strong')
def api_strong_technicals():
  try:
    return jsonify(fetch_strong_technicals_page(**_request_params()))
  except ValueError as exc:
    return jsonify({'ok': False, 'detail': str(exc)}), 400
  except Exception:
    _logger.exception('Failed to build strong technicals payload')
    return jsonify({'ok': False, 'detail': 'Failed to build strong technicals payload'}), 500
