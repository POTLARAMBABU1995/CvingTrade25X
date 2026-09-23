import logging
from typing import Dict, List, Optional, Tuple

from ..cache import SimpleCache
from ..config import get_settings
from ..db import fetch_all
from ..utils.time import TF_TABLES, normalize_tf, parse_date, to_epoch_seconds

logger = logging.getLogger(__name__)
settings = get_settings()
cache = SimpleCache(max_items=settings.cache_max_items, ttl_seconds=settings.cache_ttl_seconds)


def fetch_bars(
    symbol: str,
    tf: str,
    from_date: Optional[str],
    to_date: Optional[str],
    limit: int,
    cursor: Optional[str],
) -> Tuple[List[Dict[str, float]], Optional[str]]:
    tf_norm = normalize_tf(tf)
    table = TF_TABLES[tf_norm]
    page_limit = min(limit, settings.max_limit)
    fetch_limit = page_limit + 1

    from_dt = parse_date(from_date)
    to_dt = parse_date(to_date)
    cursor_dt = parse_date(cursor)

    cache_key = f'bars:{symbol}:{tf_norm}:{from_date}:{to_date}:{cursor}:{page_limit}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    sql = f"""
        SELECT * FROM (
            SELECT BAR_DATE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, CLOSE_PRICE, VOLUME
            FROM {table}
            WHERE SYMBOL = :symbol
              AND (:from_date IS NULL OR BAR_DATE >= :from_date)
              AND (:to_date IS NULL OR BAR_DATE <= :to_date)
              AND (:cursor_date IS NULL OR BAR_DATE < :cursor_date)
            ORDER BY BAR_DATE DESC
        )
        WHERE ROWNUM <= :limit
    """
    params = {
        'symbol': symbol,
        'from_date': from_dt,
        'to_date': to_dt,
        'cursor_date': cursor_dt,
        'limit': fetch_limit,
    }
    rows = fetch_all(sql, params)

    has_more = len(rows) > page_limit
    rows = rows[:page_limit]
    rows.reverse()

    bars: List[Dict[str, float]] = []
    for row in rows:
        ts = to_epoch_seconds(row.get('bar_date'))
        if ts is None:
            continue
        bars.append({
            't': ts,
            'o': float(row.get('open_price')),
            'h': float(row.get('high_price')),
            'l': float(row.get('low_price')),
            'c': float(row.get('close_price')),
            'v': float(row.get('volume')),
        })

    next_cursor = None
    if has_more and rows:
        earliest = rows[0].get('bar_date')
        if earliest is not None:
            next_cursor = earliest.strftime('%Y-%m-%d')

    cache.set(cache_key, (bars, next_cursor))
    logger.info('bars.loaded', extra={'symbol': symbol, 'tf': tf_norm, 'count': len(bars)})
    return bars, next_cursor
