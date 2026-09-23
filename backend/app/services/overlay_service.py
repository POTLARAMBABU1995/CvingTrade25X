import logging
from functools import lru_cache
from typing import Dict, List, Optional, Set

from ..cache import SimpleCache
from ..config import get_settings
from ..db import fetch_all
from ..utils.time import normalize_tf, parse_date

logger = logging.getLogger(__name__)
settings = get_settings()
cache = SimpleCache(max_items=settings.cache_max_items, ttl_seconds=settings.cache_ttl_seconds)


@lru_cache(maxsize=1)
def _resolve_sr_levels_table_name() -> str:
    return 'SR_LEVELS'


@lru_cache(maxsize=1)
def _fetch_sr_level_columns() -> Set[str]:
    table_name = _resolve_sr_levels_table_name()
    rows = fetch_all(
        """
        SELECT column_name
        FROM user_tab_columns
        WHERE table_name = :table_name
        """,
        {'table_name': table_name},
    )
    return {str(row['column_name']).upper() for row in rows}


def _resolve_sr_value_column() -> str:
    columns = _fetch_sr_level_columns()
    if 'SR_LEVEL' in columns:
        return 'SR_LEVEL'
    if 'SR_LEVELS' in columns:
        return 'SR_LEVELS'
    raise RuntimeError('SR_LEVELS table must expose SR_LEVEL or SR_LEVELS')


def fetch_sr_levels(
    symbol: str,
    tf: str,
    from_date: Optional[str],
    to_date: Optional[str],
) -> List[Dict[str, object]]:
    tf_norm = normalize_tf(tf)
    cache_key = f'sr:{symbol}:{tf_norm}:{from_date}:{to_date}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    table_name = _resolve_sr_levels_table_name()
    value_column = _resolve_sr_value_column()
    sql = f"""
        SELECT LEVEL_ID,
               LEVEL_TYPE,
               {value_column} AS SR_VALUE,
               UPDATED_AT
        FROM {table_name}
        WHERE SYMBOL = :symbol
          AND TF = :tf
          AND (:from_date IS NULL OR UPDATED_AT >= :from_date)
          AND (:to_date IS NULL OR UPDATED_AT <= :to_date)
        ORDER BY {value_column}
    """
    rows = fetch_all(sql, {
        'symbol': symbol,
        'tf': tf_norm,
        'from_date': parse_date(from_date),
        'to_date': parse_date(to_date),
    })

    annotations: List[Dict[str, object]] = []
    for row in rows:
        sr_value = row.get('sr_value')
        if sr_value is None:
            continue
        level_type = (row.get('level_type') or 'SR').upper()
        annotations.append({
            'type': 'hline',
            'id': row.get('level_id'),
            'price': float(sr_value),
            'label': 'Fib' if level_type == 'FIB' else level_type,
            'style': 'dashed' if level_type == 'FIB' else 'solid',
        })

    cache.set(cache_key, annotations)
    logger.info('sr.loaded', extra={'symbol': symbol, 'tf': tf_norm, 'count': len(annotations)})
    return annotations


def fetch_pivots(
    symbol: str,
    tf: str,
    from_date: Optional[str],
    to_date: Optional[str],
) -> List[Dict[str, object]]:
    from ..utils.time import to_epoch_seconds

    tf_norm = normalize_tf(tf)
    cache_key = f'pivots:{symbol}:{tf_norm}:{from_date}:{to_date}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    sql = """
        SELECT PIVOT_ID, BAR_DATE, PIVOT_TYPE, PRICE, STRENGTH, CONFIDENCE
        FROM PIVOTS
        WHERE SYMBOL = :symbol
          AND TF = :tf
          AND (:from_date IS NULL OR BAR_DATE >= :from_date)
          AND (:to_date IS NULL OR BAR_DATE <= :to_date)
        ORDER BY BAR_DATE
    """
    rows = fetch_all(sql, {
        'symbol': symbol,
        'tf': tf_norm,
        'from_date': parse_date(from_date),
        'to_date': parse_date(to_date),
    })

    annotations: List[Dict[str, object]] = []
    for row in rows:
        ts = to_epoch_seconds(row.get('bar_date'))
        if ts is None:
            continue
        p_type = row.get('pivot_type') or 'PIVOT'
        annotations.append({
            'type': 'marker',
            'id': row.get('pivot_id'),
            'time': ts,
            'price': float(row.get('price') or 0),
            'label': p_type.title(),
            'shape': 'arrowUp' if str(p_type).upper() == 'LOW' else 'arrowDown',
        })
    cache.set(cache_key, annotations)
    logger.info('pivots.loaded', extra={'symbol': symbol, 'tf': tf_norm, 'count': len(annotations)})
    return annotations

