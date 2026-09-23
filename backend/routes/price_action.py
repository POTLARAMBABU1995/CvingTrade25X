from __future__ import annotations

import logging
import os
import re
import uuid
from collections import OrderedDict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional

from flask import Blueprint, jsonify, request
from routes.strong_technicals import _request_params
from services.price_action_service import fetch_price_action_page
from services import nse_mcap_service

try:
    from ..db_pool import fetchall_dict, pool
except ImportError:  # pragma: no cover
    from db_pool import fetchall_dict, pool  # type: ignore


bp = Blueprint('price_action', __name__)
_logger = logging.getLogger(__name__)

_IDENT_RE = re.compile(r'^[A-Za-z0-9_.$#]+$')
_LEVEL_SPLIT_RE = re.compile(r'[\n,;|]+')
_DEFAULT_LEVEL_TYPE = 'SR'
_DEFAULT_TF = '1D'
_DISPLAY_TD = '1D'

_SCHEMA = (os.getenv('PRICE_ACTION_SR_SCHEMA') or os.getenv('ORACLE_SCHEMA') or '').strip()
_TABLE = (os.getenv('PRICE_ACTION_SR_LEVELS_MANUALLY_TABLE') or 'PRICE_ACTION_SR_LEVELS_MANUALLY').strip()


def _safe_identifier(value: str) -> str:
    name = (value or '').strip()
    if not name or not _IDENT_RE.match(name):
        raise ValueError(f'Invalid identifier: {value!r}')
    return name


def _qualified_table() -> str:
    table = _safe_identifier(_TABLE)
    if '.' in table:
        return table
    schema = _safe_identifier(_SCHEMA) if _SCHEMA else ''
    return f'{schema}.{table}' if schema else table


def _to_text(value: Any) -> str:
    return str(value or '').strip()


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = _to_text(value).replace(',', '')
    if not text:
        raise ValueError('SR level is required.')
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f'Invalid SR level: {value}') from exc


def _format_decimal(value: Any) -> str:
    dec = _to_decimal(value)
    text = format(dec.quantize(Decimal('0.000001')), 'f')
    text = text.rstrip('0').rstrip('.')
    return text or '0'


def _format_oracle_date(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.strftime('%d-%m-%Y')
    text = _to_text(value)
    return text or None


def _normalize_symbol(value: Any) -> str:
    symbol = _to_text(value).upper()
    if not symbol:
        raise ValueError('Symbol is required.')
    return symbol


def _split_levels(raw: Any) -> List[Decimal]:
    values: List[Decimal] = []
    seen: set[str] = set()

    if isinstance(raw, list):
        candidates: Iterable[Any] = raw
    elif raw is None:
        candidates = []
    elif isinstance(raw, (int, float, Decimal)):
        candidates = [raw]
    else:
        candidates = [part for part in _LEVEL_SPLIT_RE.split(_to_text(raw)) if part.strip()]

    for item in candidates:
        level = _to_decimal(item)
        key = _format_decimal(level)
        if key in seen:
            continue
        seen.add(key)
        values.append(level)
    return values


def _parse_single_level(payload: Dict[str, Any]) -> tuple[str, Decimal]:
    symbol = _normalize_symbol(payload.get('symbol') or payload.get('SYMBOL'))
    levels = _split_levels(
        payload.get('sr_level')
        or payload.get('srLevel')
        or payload.get('sr_levels')
        or payload.get('srLevels')
        or payload.get('levels')
    )
    if len(levels) != 1:
        raise ValueError('Exactly one SR level is required.')
    return symbol, levels[0]


def _tf_filter_clause() -> str:
    return "TRIM(UPPER(NVL(TF, '1D'))) IN ('1D', 'D')"


def _fetch_grouped_rows(conn, search: Optional[str] = None) -> List[Dict[str, Any]]:
    table = _qualified_table()
    sql = f'''
        SELECT LEVEL_ID,
               SYMBOL,
               TF,
               LEVEL_TYPE,
               CREATED_AT,
               UPDATED_AT,
               SR_LEVEL
        FROM {table}
        WHERE {_tf_filter_clause()}
    '''
    binds: Dict[str, Any] = {}
    if search:
        sql += ' AND UPPER(SYMBOL) LIKE :search'
        binds['search'] = f"%{search.upper()}%"
    sql += ' ORDER BY SYMBOL ASC, SR_LEVEL ASC, CREATED_AT ASC, LEVEL_ID ASC'

    with conn.cursor() as cur:
        cur.execute(sql, binds)
        rows = fetchall_dict(cur)

    grouped: 'OrderedDict[str, Dict[str, Any]]' = OrderedDict()
    for row in rows:
        symbol = _normalize_symbol(row.get('symbol'))
        bucket = grouped.setdefault(
            symbol,
            {
                'symbol': symbol,
                'td': _DISPLAY_TD,
                'levels': [],
                'level_count': 0,
                'created_at': None,
                'updated_at': None,
            },
        )
        created_at = _format_oracle_date(row.get('created_at'))
        updated_at = _format_oracle_date(row.get('updated_at'))
        bucket['levels'].append(
            {
                'level_id': _to_text(row.get('level_id')),
                'value': _format_decimal(row.get('sr_level')),
                'level_type': _to_text(row.get('level_type')) or _DEFAULT_LEVEL_TYPE,
                'created_at': created_at,
                'updated_at': updated_at,
            }
        )
        bucket['level_count'] += 1
        if bucket['created_at'] is None and created_at:
            bucket['created_at'] = created_at
        if updated_at:
            bucket['updated_at'] = updated_at

    result: List[Dict[str, Any]] = []
    for index, bucket in enumerate(grouped.values(), start=1):
        result.append(
            {
                's_no': index,
                'symbol': bucket['symbol'],
                'td': bucket['td'],
                'sr_level': ','.join(level['value'] for level in bucket['levels']),
                'level_count': bucket['level_count'],
                'levels': bucket['levels'],
                'created_at': bucket['created_at'],
                'updated_at': bucket['updated_at'],
            }
        )
    return result


def _find_level_row(conn, level_id: str) -> Optional[Dict[str, Any]]:
    table = _qualified_table()
    sql = f'''
        SELECT LEVEL_ID,
               SYMBOL,
               SR_LEVEL,
               CREATED_AT,
               UPDATED_AT,
               LEVEL_TYPE
        FROM {table}
        WHERE LEVEL_ID = :level_id
          AND {_tf_filter_clause()}
    '''
    with conn.cursor() as cur:
        cur.execute(sql, {'level_id': level_id})
        rows = fetchall_dict(cur)
    return rows[0] if rows else None


def _level_exists(conn, symbol: str, level: Decimal, exclude_level_id: Optional[str] = None) -> bool:
    table = _qualified_table()
    sql = f'''
        SELECT COUNT(1)
        FROM {table}
        WHERE SYMBOL = :symbol
          AND SR_LEVEL = :sr_level
          AND {_tf_filter_clause()}
          AND (:exclude_level_id IS NULL OR LEVEL_ID <> :exclude_level_id)
    '''
    with conn.cursor() as cur:
        cur.execute(
            sql,
            {
                'symbol': symbol,
                'sr_level': level,
                'exclude_level_id': exclude_level_id,
            },
        )
        row = cur.fetchone()
    return bool(row and int(row[0] or 0) > 0)


def _symbol_exists(conn, symbol: str) -> bool:
    table = _qualified_table()
    sql = f'''
        SELECT COUNT(1)
        FROM {table}
        WHERE SYMBOL = :symbol
          AND {_tf_filter_clause()}
    '''
    with conn.cursor() as cur:
        cur.execute(sql, {'symbol': symbol})
        row = cur.fetchone()
    return bool(row and int(row[0] or 0) > 0)


def _insert_level(conn, symbol: str, level: Decimal) -> Dict[str, Any]:
    if _level_exists(conn, symbol, level):
        raise ValueError(f'SR level {_format_decimal(level)} already exists for {symbol}.')

    table = _qualified_table()
    level_id = f'PA-{uuid.uuid4().hex[:24].upper()}'
    sql = f'''
        INSERT INTO {table} (
            LEVEL_ID,
            SYMBOL,
            TF,
            LEVEL_TYPE,
            CREATED_AT,
            UPDATED_AT,
            SR_LEVEL
        ) VALUES (
            :level_id,
            :symbol,
            :tf,
            :level_type,
            SYSDATE,
            SYSDATE,
            :sr_level
        )
    '''
    with conn.cursor() as cur:
        cur.execute(
            sql,
            {
                'level_id': level_id,
                'symbol': symbol,
                'tf': _DEFAULT_TF,
                'level_type': _DEFAULT_LEVEL_TYPE,
                'sr_level': level,
            },
        )
    conn.commit()
    return {
        'mode': 'insert',
        'level_id': level_id,
        'symbol': symbol,
        'sr_level': _format_decimal(level),
        'td': _DISPLAY_TD,
    }


def _insert_symbol_levels(conn, symbol: str, levels: List[Decimal]) -> Dict[str, Any]:
    if not levels:
        raise ValueError('At least one SR level is required.')

    table = _qualified_table()
    sql = f'''
        INSERT INTO {table} (
            LEVEL_ID,
            SYMBOL,
            TF,
            LEVEL_TYPE,
            CREATED_AT,
            UPDATED_AT,
            SR_LEVEL
        ) VALUES (
            :level_id,
            :symbol,
            :tf,
            :level_type,
            SYSDATE,
            SYSDATE,
            :sr_level
        )
    '''

    inserted_levels: List[Dict[str, str]] = []
    skipped_levels: List[str] = []
    try:
        with conn.cursor() as cur:
            for level in levels:
                if _level_exists(conn, symbol, level):
                    skipped_levels.append(_format_decimal(level))
                    continue
                level_id = f'PA-{uuid.uuid4().hex[:24].upper()}'
                cur.execute(
                    sql,
                    {
                        'level_id': level_id,
                        'symbol': symbol,
                        'tf': _DEFAULT_TF,
                        'level_type': _DEFAULT_LEVEL_TYPE,
                        'sr_level': level,
                    },
                )
                inserted_levels.append(
                    {
                        'level_id': level_id,
                        'sr_level': _format_decimal(level),
                    }
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {
        'mode': 'append_symbol',
        'symbol': symbol,
        'td': _DISPLAY_TD,
        'inserted_count': len(inserted_levels),
        'skipped_count': len(skipped_levels),
        'skipped_levels': skipped_levels,
        'levels': inserted_levels,
    }


def _update_level(conn, level_id: str, symbol: str, level: Decimal) -> Dict[str, Any]:
    existing = _find_level_row(conn, level_id)
    if not existing:
        raise ValueError(f'LEVEL_ID {level_id} was not found.')
    if _level_exists(conn, symbol, level, exclude_level_id=level_id):
        raise ValueError(f'SR level {_format_decimal(level)} already exists for {symbol}.')

    table = _qualified_table()
    sql = f'''
        UPDATE {table}
        SET SYMBOL = :symbol,
            TF = :tf,
            LEVEL_TYPE = :level_type,
            SR_LEVEL = :sr_level,
            UPDATED_AT = SYSDATE
        WHERE LEVEL_ID = :level_id
    '''
    with conn.cursor() as cur:
        cur.execute(
            sql,
            {
                'level_id': level_id,
                'symbol': symbol,
                'tf': _DEFAULT_TF,
                'level_type': _DEFAULT_LEVEL_TYPE,
                'sr_level': level,
            },
        )
        updated = cur.rowcount if cur.rowcount is not None else 0
    conn.commit()
    if not updated:
        raise ValueError(f'LEVEL_ID {level_id} was not found.')
    return {
        'mode': 'update',
        'level_id': level_id,
        'symbol': symbol,
        'sr_level': _format_decimal(level),
        'td': _DISPLAY_TD,
    }


def _delete_level(conn, level_id: str) -> Dict[str, Any]:
    existing = _find_level_row(conn, level_id)
    if not existing:
        raise ValueError(f'LEVEL_ID {level_id} was not found.')

    table = _qualified_table()
    sql = f'DELETE FROM {table} WHERE LEVEL_ID = :level_id'
    with conn.cursor() as cur:
        cur.execute(sql, {'level_id': level_id})
        deleted = cur.rowcount if cur.rowcount is not None else 0
    conn.commit()
    if not deleted:
        raise ValueError(f'LEVEL_ID {level_id} was not found.')
    return {
        'mode': 'delete',
        'level_id': level_id,
        'symbol': _normalize_symbol(existing.get('symbol')),
        'sr_level': _format_decimal(existing.get('sr_level')),
        'deleted_rows': int(deleted or 0),
    }


@bp.get('/api/price-action-sr-levels-manually')
def api_price_action_sr_levels_manually():
    search = _to_text(request.args.get('search')) or None
    try:
        with pool.acquire() as conn:
            rows = _fetch_grouped_rows(conn, search=search)
        rows = nse_mcap_service.enrich_rows_with_marketcap_index(rows)
        return jsonify({'ok': True, 'rows': rows, 'meta': {'total_rows': len(rows), 'search': search or ''}})
    except Exception as exc:
        _logger.exception('Failed to read price action SR levels')
        return jsonify({'ok': False, 'error': str(exc)}), 500


@bp.get('/api/technicals/price-action')
def api_technical_price_action():
    try:
        return jsonify(fetch_price_action_page(**_request_params()))
    except ValueError as exc:
        return jsonify({'ok': False, 'detail': str(exc)}), 400
    except Exception:
        _logger.exception('Failed to build technical price action payload')
        return jsonify({'ok': False, 'detail': 'Failed to build technical price action payload'}), 500


@bp.post('/api/price-action-sr-levels-manually')
def api_price_action_sr_levels_manually_save():
    payload = request.get_json(silent=True) or {}
    mode = _to_text(payload.get('mode') or 'insert').lower()
    level_id = _to_text(payload.get('level_id') or payload.get('levelId'))
    try:
        with pool.acquire() as conn:
            if mode == 'delete':
                if not level_id:
                    raise ValueError('LEVEL_ID is required for delete.')
                result = _delete_level(conn, level_id)
                result['ok'] = True
                return jsonify(result)

            if mode == 'create_symbol':
                symbol = _normalize_symbol(payload.get('symbol') or payload.get('SYMBOL'))
                levels = _split_levels(
                    payload.get('sr_levels')
                    or payload.get('srLevels')
                    or payload.get('sr_level')
                    or payload.get('srLevel')
                    or payload.get('levels')
                )
                result = _insert_symbol_levels(conn, symbol, levels)
                result['ok'] = True
                return jsonify(result)

            symbol, level = _parse_single_level(payload)
            if mode in {'update', 'edit'}:
                if not level_id:
                    raise ValueError('LEVEL_ID is required for update.')
                result = _update_level(conn, level_id, symbol, level)
                result['ok'] = True
                return jsonify(result)

            if mode in {'insert', 'create'}:
                result = _insert_level(conn, symbol, level)
                result['ok'] = True
                return jsonify(result)

            raise ValueError(f'Unsupported mode: {mode}')
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400
    except Exception as exc:
        _logger.exception('Failed to save price action SR levels')
        return jsonify({'ok': False, 'error': str(exc)}), 500
