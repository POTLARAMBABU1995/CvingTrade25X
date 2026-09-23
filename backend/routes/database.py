from __future__ import annotations

import logging
from flask import Blueprint, jsonify, request
import services.market_table_sync_service as sync_svc

bp = Blueprint('database', __name__, url_prefix='/api/database')
logger = logging.getLogger(__name__)

@bp.get('/sync-status')
def get_database_sync_status():
    """Retrieve synchronization alignment status of DEV, MCAP, FFMC, and DELIVERY tables."""
    try:
        status = sync_svc.get_sync_status()
        return jsonify(status)
    except Exception as exc:
        logger.exception("Failed to retrieve database sync status")
        return jsonify({'ok': False, 'message': str(exc)}), 500

@bp.post('/sync-latest-market-tables')
def post_database_sync_latest_market_tables():
    """Manually trigger alignment/extraction/upsert for missing latest rows."""
    try:
        result = sync_svc.sync_latest_market_tables()
        return jsonify(result)
    except Exception as exc:
        logger.exception("Failed to run latest market tables sync")
        return jsonify({'ok': False, 'message': str(exc)}), 500
