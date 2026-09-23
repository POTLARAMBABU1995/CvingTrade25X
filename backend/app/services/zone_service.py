import json
import logging
from typing import Dict, List, Optional

from ..cache import SimpleCache
from ..config import get_settings
from ..db import fetch_all
from ..utils.time import normalize_tf, parse_date, to_epoch_seconds

logger = logging.getLogger(__name__)
settings = get_settings()
cache = SimpleCache(max_items=settings.cache_max_items, ttl_seconds=settings.cache_ttl_seconds)


def fetch_zones(
    symbol: str,
    tf: str,
    from_date: Optional[str],
    to_date: Optional[str],
) -> List[Dict[str, object]]:
    tf_norm = normalize_tf(tf)
    cache_key = f'zones:{symbol}:{tf_norm}:{from_date}:{to_date}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    sql = """
        SELECT ZONE_ID, ZONE_TYPE, T1_DATE, T2_DATE, PRICE_LOW, PRICE_HIGH,
               SCORE, CONFIDENCE, DETAILS_JSON
        FROM ZONES
        WHERE SYMBOL = :symbol
          AND TF = :tf
          AND (:from_date IS NULL OR T2_DATE >= :from_date)
          AND (:to_date IS NULL OR T1_DATE <= :to_date)
        ORDER BY T1_DATE
    """
    rows = fetch_all(sql, {
        'symbol': symbol,
        'tf': tf_norm,
        'from_date': parse_date(from_date),
        'to_date': parse_date(to_date),
    })

    annotations: List[Dict[str, object]] = []
    for row in rows:
        t1 = to_epoch_seconds(row.get('t1_date'))
        t2 = to_epoch_seconds(row.get('t2_date'))
        if t1 is None or t2 is None:
            continue
        zone_type = row.get('zone_type') or 'ZONE'
        score = float(row.get('score') or 0)
        label = 'Buy Zone' if zone_type.upper() == 'DEMAND' else 'Sell Zone'
        annotations.append({
            'type': 'rect',
            'id': row.get('zone_id'),
            'zoneType': zone_type,
            't1': t1,
            't2': t2,
            'p1': float(row.get('price_low') or 0),
            'p2': float(row.get('price_high') or 0),
            'score': score,
            'confidence': float(row.get('confidence') or 0),
            'label': label,
        })
        details = row.get('details_json')
        if details:
            try:
                parsed = json.loads(details.read() if hasattr(details, 'read') else details)
            except (ValueError, TypeError):
                parsed = None
            if parsed:
                annotations.append({
                    'type': 'meta',
                    'id': f"{row.get('zone_id')}:meta",
                    'data': parsed,
                })

    cache.set(cache_key, annotations)
    logger.info('zones.loaded', extra={'symbol': symbol, 'tf': tf_norm, 'count': len(annotations)})
    return annotations
