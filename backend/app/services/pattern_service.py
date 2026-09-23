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


def _label(pattern_type: str) -> str:
    if not pattern_type:
        return 'Pattern'
    return pattern_type.replace('_', ' ').title()


def fetch_patterns(
    symbol: str,
    tf: str,
    from_date: Optional[str],
    to_date: Optional[str],
) -> List[Dict[str, object]]:
    tf_norm = normalize_tf(tf)
    cache_key = f'patterns:{symbol}:{tf_norm}:{from_date}:{to_date}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    sql = """
        SELECT PATTERN_ID, PATTERN_TYPE, T1_DATE, T2_DATE, BREAKOUT_DATE,
               PRICE_LOW, PRICE_HIGH, SCORE, CONFIDENCE, DETAILS_JSON
        FROM PATTERNS
        WHERE SYMBOL = :symbol
          AND TF = :tf
          AND (:from_date IS NULL OR NVL(T2_DATE, T1_DATE) >= :from_date)
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
        t2 = to_epoch_seconds(row.get('t2_date')) or t1
        p_low = row.get('price_low')
        p_high = row.get('price_high')
        pattern_id = row.get('pattern_id')
        p_type = row.get('pattern_type') or 'pattern'
        label = _label(p_type)
        if t1 and p_low is not None and p_high is not None:
            annotations.append({
                'type': 'rect',
                'id': pattern_id,
                'patternType': p_type,
                't1': t1,
                't2': t2,
                'p1': float(p_low),
                'p2': float(p_high),
                'score': float(row.get('score') or 0),
                'confidence': float(row.get('confidence') or 0),
                'label': label,
            })
        breakout = row.get('breakout_date')
        if breakout is not None:
            annotations.append({
                'type': 'vline',
                'id': f"{pattern_id}:breakout",
                'time': to_epoch_seconds(breakout),
                'label': f"{label} Breakout",
                'style': 'dashed',
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
                    'id': f"{pattern_id}:meta",
                    'data': parsed,
                })

    cache.set(cache_key, annotations)
    logger.info('patterns.loaded', extra={'symbol': symbol, 'tf': tf_norm, 'count': len(annotations)})
    return annotations
