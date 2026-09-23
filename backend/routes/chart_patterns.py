from __future__ import annotations

import logging

from flask import Blueprint, jsonify

from routes.strong_technicals import _request_params
from services.chart_pattern_service import fetch_chart_patterns_page


bp = Blueprint('chart_patterns', __name__)
_logger = logging.getLogger(__name__)


@bp.get('/api/technicals/chart-patterns')
def api_chart_patterns():
  try:
    return jsonify(fetch_chart_patterns_page(**_request_params()))
  except ValueError as exc:
    return jsonify({'ok': False, 'detail': str(exc)}), 400
  except Exception:
    _logger.exception('Failed to build chart patterns payload')
    return jsonify({'ok': False, 'detail': 'Failed to build chart patterns payload'}), 500
