from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from services import sector_hierarchy_service as hierarchy_service

bp = Blueprint('sector_hierarchy', __name__)
logger = logging.getLogger(__name__)


def _as_bool(value: str | None) -> bool:
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'y', 'on'}


def _required_query_param(name: str) -> str:
    value = ' '.join(str(request.args.get(name) or '').strip().split())
    if not value:
        raise ValueError(f'{name} is required')
    return value


def _error(message: str, code: str, status: int = 400):
    return jsonify(
        {
            'success': False,
            'message': message,
            'errorCode': code,
        }
    ), status


def _ok(payload: dict):
    return jsonify(
        {
            'success': True,
            **payload,
        }
    )


@bp.get('/api/sector-hierarchy/parents')
def api_sector_hierarchy_parents():
    refresh = _as_bool(request.args.get('refresh'))
    try:
        return _ok(hierarchy_service.get_parents(refresh=refresh))
    except Exception:
        logger.exception('[SECTOR_HIERARCHY_ERROR] endpoint=parents errorCode=SECTOR_HIERARCHY_DB_QUERY_FAILED')
        return _error('Unable to load sector hierarchy parents.', 'SECTOR_HIERARCHY_DB_QUERY_FAILED', 500)


@bp.get('/api/sector-hierarchy/industries')
def api_sector_hierarchy_industries():
    refresh = _as_bool(request.args.get('refresh'))
    try:
        parent_sector = _required_query_param('parentSector')
    except ValueError as exc:
        return _error(str(exc), 'SECTOR_HIERARCHY_VALIDATION_ERROR', 400)

    try:
        return _ok(hierarchy_service.get_industries(parent_sector=parent_sector, refresh=refresh))
    except Exception:
        logger.exception(
            '[SECTOR_HIERARCHY_ERROR] endpoint=industries parentSector=%s errorCode=SECTOR_HIERARCHY_DB_QUERY_FAILED',
            parent_sector,
        )
        return _error('Unable to load sector hierarchy industries.', 'SECTOR_HIERARCHY_DB_QUERY_FAILED', 500)


@bp.get('/api/sector-hierarchy/sub-sectors')
def api_sector_hierarchy_sub_sectors():
    refresh = _as_bool(request.args.get('refresh'))
    try:
        parent_sector = _required_query_param('parentSector')
        industry_sector = _required_query_param('industrySector')
    except ValueError as exc:
        return _error(str(exc), 'SECTOR_HIERARCHY_VALIDATION_ERROR', 400)

    try:
        return _ok(
            hierarchy_service.get_sub_sectors(
                parent_sector=parent_sector,
                industry_sector=industry_sector,
                refresh=refresh,
            )
        )
    except Exception:
        logger.exception(
            '[SECTOR_HIERARCHY_ERROR] endpoint=sub-sectors parentSector=%s industrySector=%s errorCode=SECTOR_HIERARCHY_DB_QUERY_FAILED',
            parent_sector,
            industry_sector,
        )
        return _error('Unable to load sector hierarchy sub-sectors.', 'SECTOR_HIERARCHY_DB_QUERY_FAILED', 500)


@bp.get('/api/sector-hierarchy/stocks')
def api_sector_hierarchy_stocks():
    refresh = _as_bool(request.args.get('refresh'))
    parent_sector = ' '.join(str(request.args.get('parentSector') or '').strip().split()) or None
    industry_sector = ' '.join(str(request.args.get('industrySector') or '').strip().split()) or None
    sub_sector = ' '.join(str(request.args.get('subSector') or '').strip().split()) or None

    try:
        return _ok(
            hierarchy_service.get_stocks(
                parent_sector=parent_sector,
                industry_sector=industry_sector,
                sub_sector=sub_sector,
                refresh=refresh,
            )
        )
    except Exception:
        logger.exception(
            '[SECTOR_HIERARCHY_ERROR] endpoint=stocks parentSector=%s industrySector=%s subSector=%s errorCode=SECTOR_HIERARCHY_DB_QUERY_FAILED',
            parent_sector or '',
            industry_sector or '',
            sub_sector or '',
        )
        return _error('Unable to load sector hierarchy stocks.', 'SECTOR_HIERARCHY_DB_QUERY_FAILED', 500)


@bp.get('/api/sector-hierarchy/summary')
def api_sector_hierarchy_summary():
    refresh = _as_bool(request.args.get('refresh'))
    try:
        parent_sector = _required_query_param('parentSector')
    except ValueError as exc:
        return _error(str(exc), 'SECTOR_HIERARCHY_VALIDATION_ERROR', 400)

    try:
        return _ok(hierarchy_service.get_summary(parent_sector=parent_sector, refresh=refresh))
    except Exception:
        logger.exception(
            '[SECTOR_HIERARCHY_ERROR] endpoint=summary parentSector=%s errorCode=SECTOR_HIERARCHY_DB_QUERY_FAILED',
            parent_sector,
        )
        return _error('Unable to load sector hierarchy summary.', 'SECTOR_HIERARCHY_DB_QUERY_FAILED', 500)


@bp.get('/api/sector-hierarchy/tree')
def api_sector_hierarchy_tree():
    refresh = _as_bool(request.args.get('refresh'))
    try:
        parent_sector = _required_query_param('parentSector')
    except ValueError as exc:
        return _error(str(exc), 'SECTOR_HIERARCHY_VALIDATION_ERROR', 400)

    try:
        return _ok(hierarchy_service.get_tree(parent_sector=parent_sector, refresh=refresh))
    except Exception:
        logger.exception(
            '[SECTOR_HIERARCHY_ERROR] endpoint=tree parentSector=%s errorCode=SECTOR_HIERARCHY_DB_QUERY_FAILED',
            parent_sector,
        )
        return _error('Unable to load sector hierarchy tree.', 'SECTOR_HIERARCHY_DB_QUERY_FAILED', 500)
