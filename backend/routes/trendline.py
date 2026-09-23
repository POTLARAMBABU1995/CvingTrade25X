from __future__ import annotations

import logging

from flask import Blueprint, jsonify

from routes.strong_technicals import _request_params
from services.trendline_service import fetch_trendline_page


bp = Blueprint('trendline', __name__)
_logger = logging.getLogger(__name__)


@bp.get('/api/technicals/trendline')
def api_trendline():
  try:
    return jsonify(fetch_trendline_page(**_request_params()))
  except ValueError as exc:
    return jsonify({'ok': False, 'detail': str(exc)}), 400
  except Exception:
    _logger.exception('Failed to build trendline payload')
    return jsonify({'ok': False, 'detail': 'Failed to build trendline payload'}), 500
