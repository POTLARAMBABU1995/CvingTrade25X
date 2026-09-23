from __future__ import annotations

import os
from typing import Any, Dict

from flask import Blueprint, jsonify, request

from cache import TTLCache, background_refresh
from services.levels_service import load_levels_payload


bp = Blueprint('levels', __name__)

_ttl = int(os.getenv('LEVELS_CACHE_TTL', '900'))
_cache = TTLCache(ttl_seconds=_ttl)


def _compute_payload() -> Dict[str, Any]:
    return load_levels_payload()


@bp.get('/api/highs-lows')
def api_highs_lows():
    force_refresh = request.args.get('refresh') in ('1', 'true', 'yes')
    cached = _cache.get('default')
    if cached is not None and not force_refresh:
        return jsonify({**cached, 'cached': True})
    if cached is not None and force_refresh:
        background_refresh(_cache, 'default', _compute_payload)
        return jsonify({**cached, 'cached': True, 'refreshing': True})

    payload = _compute_payload()
    _cache.set('default', payload)
    return jsonify({**payload, 'cached': False})

