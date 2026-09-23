from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from db import fetch_ohlc_series_from_oracle


@dataclass
class Candle:
    date: datetime
    high: Optional[float]
    low: Optional[float]
    close: Optional[float]


def _fmt_date(dt: Optional[datetime]) -> str:
    if isinstance(dt, datetime):
        try:
            return dt.strftime('%d-%m-%Y')
        except Exception:
            return ''
    return ''


def _safe_float(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _collect_candles(raw_entries: List[Dict[str, Any]]) -> List[Candle]:
    normalized: List[Candle] = []
    for entry in raw_entries:
        dt = entry.get('date')
        high_val = entry.get('high')
        low_val = entry.get('low')
        close_val = entry.get('close')
        if not isinstance(dt, datetime):
            continue
        normalized.append(Candle(
            date=dt,
            high=_safe_float(high_val),
            low=_safe_float(low_val),
            close=_safe_float(close_val),
        ))
    normalized.sort(key=lambda candle: candle.date)
    return normalized


def _pick_extreme(
    candles: List[Candle],
    *,
    cutoff: Optional[datetime],
    mode: str,
) -> Tuple[Optional[float], Optional[datetime]]:
    if not candles:
        return None, None

    if cutoff is not None:
        scoped = [c for c in candles if c.date >= cutoff]
    else:
        scoped = list(candles)

    if not scoped:
        return None, None

    best_value: Optional[float] = None
    best_date: Optional[datetime] = None

    for candle in scoped:
        if mode == 'low':
            value = candle.low if candle.low is not None else candle.close
        else:
            value = candle.high if candle.high is not None else candle.close
        if value is None:
            continue
        if best_value is None:
            best_value = value
            best_date = candle.date
            continue
        if mode == 'low':
            if value < best_value:
                best_value = value
                best_date = candle.date
        else:
            if value > best_value:
                best_value = value
                best_date = candle.date
    return best_value, best_date


def _latest_close(candles: List[Candle]) -> Tuple[Optional[float], Optional[datetime]]:
    for candle in reversed(candles):
        if candle.close is not None:
            return candle.close, candle.date
    return None, candles[-1].date if candles else None


def load_levels_payload() -> Dict[str, Any]:
    ohlc_by_symbol = fetch_ohlc_series_from_oracle()
    rows: List[Dict[str, Any]] = []

    for symbol, raw_entries in ohlc_by_symbol.items():
        candles = _collect_candles(raw_entries)
        if not candles:
            continue

        latest_close, latest_date = _latest_close(candles)
        if latest_date is None:
            latest_date = candles[-1].date

        if latest_close is None:
            fallback = candles[-1]
            latest_close = fallback.close or fallback.high or fallback.low

        high52, high52_date = _pick_extreme(
            candles,
            cutoff=latest_date - timedelta(days=365),
            mode='high',
        )
        low52, low52_date = _pick_extreme(
            candles,
            cutoff=latest_date - timedelta(days=365),
            mode='low',
        )
        high2y, high2y_date = _pick_extreme(
            candles,
            cutoff=latest_date - timedelta(days=730),
            mode='high',
        )
        high5y, high5y_date = _pick_extreme(
            candles,
            cutoff=latest_date - timedelta(days=1825),
            mode='high',
        )
        ath, ath_date = _pick_extreme(
            candles,
            cutoff=None,
            mode='high',
        )

        row: Dict[str, Any] = {
            'symbol': symbol,
            'price': _safe_float(latest_close),
            'priceDate': _fmt_date(latest_date),
            'ltcDate': _fmt_date(latest_date),
            'ltcDateSort': latest_date.timestamp() if isinstance(latest_date, datetime) else None,
            'high52': _safe_float(high52),
            'high52Date': _fmt_date(high52_date),
            'low52': _safe_float(low52),
            'low52Date': _fmt_date(low52_date),
            'high2y': _safe_float(high2y),
            'high2yDate': _fmt_date(high2y_date),
            'high5y': _safe_float(high5y),
            'high5yDate': _fmt_date(high5y_date),
            'ath': _safe_float(ath),
            'athDate': _fmt_date(ath_date),
        }
        rows.append(row)

    rows.sort(key=lambda item: item['symbol'])
    return {
        'rows': rows,
        'count': len(rows),
        'generatedAt': datetime.utcnow().isoformat() + 'Z',
    }

