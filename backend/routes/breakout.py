from __future__ import annotations

import logging

from flask import Blueprint, jsonify

from routes.strong_technicals import _request_params
from services.breakout_service import fetch_breakout_page


bp = Blueprint('breakout', __name__)
_logger = logging.getLogger(__name__)


@bp.get('/api/technicals/breakout')
def api_breakout():
  try:
    return jsonify(fetch_breakout_page(**_request_params()))
  except ValueError as exc:
    return jsonify({'ok': False, 'detail': str(exc)}), 400
  except Exception:
    _logger.exception('Failed to build breakout payload')
    return jsonify({'ok': False, 'detail': 'Failed to build breakout payload'}), 500
