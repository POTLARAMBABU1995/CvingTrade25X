import logging
from typing import Dict, Iterable, List, Optional, Set

from ..cache import SimpleCache
from ..config import get_settings
from ..db import fetch_all
from ..utils.time import IND_TABLES, normalize_tf, parse_date, to_epoch_seconds

logger = logging.getLogger(__name__)
settings = get_settings()
cache = SimpleCache(max_items=settings.cache_max_items, ttl_seconds=settings.cache_ttl_seconds)

INDICATOR_MAP = {
    'rsi14': 'RSI14',
    'ema20': 'EMA20',
    'ema50': 'EMA50',
    'ema200': 'EMA200',
    'atr14': 'ATR14',
    'macd': 'MACD_LINE',
    'macdSignal': 'MACD_SIGNAL',
    'macdHist': 'MACD_HIST',
    'pivotP': 'PIVOT_P',
    'pivotR1': 'PIVOT_R1',
    'pivotR2': 'PIVOT_R2',
    'pivotR3': 'PIVOT_R3',
    'pivotS1': 'PIVOT_S1',
    'pivotS2': 'PIVOT_S2',
    'pivotS3': 'PIVOT_S3',
}

PIVOT_KEYS = {'pivotP', 'pivotR1', 'pivotR2', 'pivotR3', 'pivotS1', 'pivotS2', 'pivotS3'}
NAME_ALIASES = {
    'rsi14': 'rsi14',
    'ema20': 'ema20',
    'ema50': 'ema50',
    'ema200': 'ema200',
    'atr14': 'atr14',
    'macd': 'macd',
    'macdsignal': 'macdSignal',
    'macdhist': 'macdHist',
    'pivotp': 'pivotP',
    'pivotr1': 'pivotR1',
    'pivotr2': 'pivotR2',
    'pivotr3': 'pivotR3',
    'pivots1': 'pivotS1',
    'pivots2': 'pivotS2',
    'pivots3': 'pivotS3',
}


def _normalize_names(names: Optional[Iterable[str]]) -> Set[str]:
    if not names:
        return {'rsi14', 'macd', 'ema20', 'ema50', 'ema200', 'atr14'}
    result: Set[str] = set()
    for name in names:
        cleaned = name.strip()
        if not cleaned:
            continue
        lower = cleaned.lower()
        if lower == 'pivot':
            result.update(PIVOT_KEYS)
            continue
        result.add(NAME_ALIASES.get(lower, cleaned))
    return result


def fetch_indicators(
    symbol: str,
    tf: str,
    names: Optional[Iterable[str]],
    from_date: Optional[str],
    to_date: Optional[str],
) -> Dict[str, List[Dict[str, float]]]:
    tf_norm = normalize_tf(tf)
    table = IND_TABLES[tf_norm]
    name_set = _normalize_names(names)
    columns = []
    for key in name_set:
        if key == 'macd':
            columns.extend(['MACD_LINE', 'MACD_SIGNAL', 'MACD_HIST'])
        elif key in INDICATOR_MAP:
            columns.append(INDICATOR_MAP[key])

    if not columns:
        return {}

    unique_columns = sorted(set(columns))
    cache_key = f'indicators:{symbol}:{tf_norm}:{from_date}:{to_date}:{"|".join(unique_columns)}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    sql = f"""
        SELECT BAR_DATE, {', '.join(unique_columns)}
        FROM {table}
        WHERE SYMBOL = :symbol
          AND (:from_date IS NULL OR BAR_DATE >= :from_date)
          AND (:to_date IS NULL OR BAR_DATE <= :to_date)
        ORDER BY BAR_DATE
    """
    params = {
        'symbol': symbol,
        'from_date': parse_date(from_date),
        'to_date': parse_date(to_date),
    }
    rows = fetch_all(sql, params)

    series: Dict[str, List[Dict[str, float]]] = {}
    for key in name_set:
        if key == 'macd':
            series.setdefault('macd', [])
            series.setdefault('macdSignal', [])
            series.setdefault('macdHist', [])
        else:
            series.setdefault(key, [])

    for row in rows:
        ts = to_epoch_seconds(row.get('bar_date'))
        if ts is None:
            continue
        for key in name_set:
            if key == 'macd':
                macd_line = row.get('macd_line')
                macd_signal = row.get('macd_signal')
                macd_hist = row.get('macd_hist')
                if macd_line is not None:
                    series['macd'].append({'t': ts, 'v': float(macd_line)})
                if macd_signal is not None:
                    series['macdSignal'].append({'t': ts, 'v': float(macd_signal)})
                if macd_hist is not None:
                    series['macdHist'].append({'t': ts, 'v': float(macd_hist)})
                continue
            column = INDICATOR_MAP.get(key)
            if not column:
                continue
            value = row.get(column.lower())
            if value is None:
                continue
            series[key].append({'t': ts, 'v': float(value)})

    cache.set(cache_key, series)
    logger.info('indicators.loaded', extra={'symbol': symbol, 'tf': tf_norm, 'series': list(series.keys())})
    return series
