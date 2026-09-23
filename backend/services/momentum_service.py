from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Tuple

from services.technical_utils import indicator_lookback_months, normalize_timeframe
from services.trend_service import ema, build_rows, fetch_series

CUTOFF_MONTHS = 6

def _series_span(series: Dict[str, List[Tuple[datetime, float]]]) -> Tuple[datetime | None, datetime | None]:
    first: datetime | None = None
    last: datetime | None = None
    for entries in series.values():
        if not entries:
            continue
        start_dt = entries[0][0]
        end_dt = entries[-1][0]
        if isinstance(start_dt, datetime):
            if first is None or start_dt < first:
                first = start_dt
        if isinstance(end_dt, datetime):
            if last is None or end_dt > last:
                last = end_dt
    return first, last


def macd_rows(timeframe: str = 'daily') -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    tf = normalize_timeframe(timeframe)
    months = indicator_lookback_months(tf, CUTOFF_MONTHS)
    series = fetch_series(timeframe=tf, months=months)
    base_rows = build_rows(series)
    out = []
    for br in base_rows:
        sym = br.get('symbol')
        ser = series.get(sym) or []
        closes = [float(v) for (_d, v) in sorted(ser, key=lambda x: x[0]) if v is not None]
        if not closes:
            continue
        macd_now = (ema(closes, 12) or 0.0) - (ema(closes, 26) or 0.0)
        if macd_now > 0:
            out.append(br)

    rows: List[Dict[str, Any]] = []
    for i, r in enumerate(out, 1):
        win_sort_keys = ['d5Sort','d10Sort','d15Sort','d22Sort','d44Sort','d66Sort','d88Sort','d132Sort','d198Sort','y1Sort','y2Sort','y3Sort','y4Sort','y5Sort','y6Sort','y7Sort','y8Sort','y9Sort','y10Sort','y15Sort','y20Sort','y25Sort']
        score = sum(1 for k in win_sort_keys if (r.get(k) is not None and r.get(k) > 0))
        rows.append({
            'sNo': i,
            'symbol': r.get('symbol'),
            'price': r.get('price'),
            'priceSort': r.get('priceSort'),
            'tradingDate': r.get('tradingDate'),
            'tradingDateSort': r.get('tradingDateSort'),
            'tradingDays': r.get('tradingDays'),
            'tradingDaysSort': r.get('tradingDaysSort'),
            'ltcDate': r.get('ltcDate'),
            'macdScore': score,
            'macdScoreSort': score,
            'd5': r.get('d5'), 'd10': r.get('d10'), 'd15': r.get('d15'), 'd22': r.get('d22'),
            'd44': r.get('d44'), 'd66': r.get('d66'), 'd88': r.get('d88'), 'd132': r.get('d132'), 'd198': r.get('d198'),
            'y1': r.get('y1'), 'y2': r.get('y2'), 'y3': r.get('y3'), 'y4': r.get('y4'), 'y5': r.get('y5'), 'y6': r.get('y6'), 'y7': r.get('y7'), 'y8': r.get('y8'), 'y9': r.get('y9'), 'y10': r.get('y10'), 'y15': r.get('y15'), 'y20': r.get('y20'), 'y25': r.get('y25'),
            'd5Sort': r.get('d5Sort'), 'd10Sort': r.get('d10Sort'), 'd15Sort': r.get('d15Sort'), 'd22Sort': r.get('d22Sort'),
            'd44Sort': r.get('d44Sort'), 'd66Sort': r.get('d66Sort'), 'd88Sort': r.get('d88Sort'), 'd132Sort': r.get('d132Sort'), 'd198Sort': r.get('d198Sort'),
            'y1Sort': r.get('y1Sort'), 'y2Sort': r.get('y2Sort'), 'y3Sort': r.get('y3Sort'), 'y4Sort': r.get('y4Sort'), 'y5Sort': r.get('y5Sort'), 'y6Sort': r.get('y6Sort'), 'y7Sort': r.get('y7Sort'), 'y8Sort': r.get('y8Sort'), 'y9Sort': r.get('y9Sort'), 'y10Sort': r.get('y10Sort'), 'y15Sort': r.get('y15Sort'), 'y20Sort': r.get('y20Sort'), 'y25Sort': r.get('y25Sort'),
        })
    first_dt, last_dt = _series_span(series)
    meta = {
        'cutoffMonths': months,
        'baseCutoffMonths': CUTOFF_MONTHS,
        'timeframe': tf,
        'startDate': first_dt.strftime('%Y-%m-%d') if isinstance(first_dt, datetime) else None,
        'endDate': last_dt.strftime('%Y-%m-%d') if isinstance(last_dt, datetime) else None,
    }
    return rows, meta
