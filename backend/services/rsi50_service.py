from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import fmean
from typing import Any, Dict, List, Optional

from db import fetch_ohlc_series_from_oracle
from services.technical_utils import aggregate_ohlc_series_by_timeframe, indicator_lookback_months, normalize_timeframe

RSI_PERIOD = 14
VOL_WINDOW = 20
MFI_PERIOD = 14
CUTOFF_MONTHS = 6


@dataclass
class Candle:
    date: datetime
    close: float
    volume: Optional[float]
    high: Optional[float]
    low: Optional[float]


def _fmt_date(dt: Optional[datetime]) -> str:
    if isinstance(dt, datetime):
        try:
            return dt.strftime('%d-%m-%Y')
        except Exception:
            return ''
    return ''


def _compute_rsi_series(closes: List[float], period: int = RSI_PERIOD) -> List[Optional[float]]:
    if len(closes) < period + 1:
        return [None] * len(closes)

    rsi_values: List[Optional[float]] = [None] * len(closes)
    gains = []
    losses = []
    for i in range(1, period + 1):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    rs = (avg_gain / avg_loss) if avg_loss > 0 else None
    rsi_values[period] = 100.0 if rs is None else 100 - (100 / (1 + rs))

    for idx in range(period + 1, len(closes)):
        delta = closes[idx] - closes[idx - 1]
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
        if avg_loss == 0:
            rsi_values[idx] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi_values[idx] = 100 - (100 / (1 + rs))
    return rsi_values


def _compute_mfi(candles: List[Candle], period: int = MFI_PERIOD) -> Optional[float]:
    if len(candles) < period + 1:
        return None
    positive_flow = 0.0
    negative_flow = 0.0
    for idx in range(-period, 0):
        curr = candles[idx]
        prev = candles[idx - 1]
        if curr.volume is None or prev.high is None or prev.low is None or prev.close is None:
            continue
        if curr.high is None or curr.low is None:
            continue
        curr_tp = (curr.high + curr.low + curr.close) / 3
        prev_tp = (prev.high + prev.low + prev.close) / 3
        flow = curr_tp * (curr.volume or 0.0)
        if curr_tp >= prev_tp:
            positive_flow += flow
        else:
            negative_flow += flow
    if positive_flow == negative_flow == 0:
        return 50.0
    if negative_flow == 0:
        return 100.0
    money_ratio = positive_flow / negative_flow
    return 100 - (100 / (1 + money_ratio))


def _compute_volume_thrust(candles: List[Candle], window: int = VOL_WINDOW) -> Optional[float]:
    if len(candles) < window + 1:
        return None
    latest_volume = candles[-1].volume
    if latest_volume is None:
        return None
    window_slice = [c.volume for c in candles[-(window + 1):-1] if c.volume is not None and c.volume > 0]
    if not window_slice:
        return None
    avg_volume = fmean(window_slice)
    if avg_volume <= 0:
        return None
    ratio = latest_volume / avg_volume
    score = ratio * 50.0
    if score > 100:
        return 100.0
    if score < 0:
        return 0.0
    return score


def _compute_rsi_slope_score(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    if current is None or previous is None:
        return None
    delta = current - previous
    score = 50 + (delta * 2)
    if score > 100:
        return 100.0
    if score < 0:
        return 0.0
    return score


def _safe_round(value: Optional[float], digits: int = 2) -> Optional[float]:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except Exception:
        return None


def load_rsi50_payload(timeframe: str = 'daily') -> Dict[str, Any]:
    tf = normalize_timeframe(timeframe)
    months = indicator_lookback_months(tf, CUTOFF_MONTHS)
    raw_series = fetch_ohlc_series_from_oracle(months=months)
    series_by_symbol = aggregate_ohlc_series_by_timeframe(raw_series, tf)
    rows: List[Dict[str, Any]] = []
    overall_first: Optional[datetime] = None
    overall_last: Optional[datetime] = None

    for symbol, entries in series_by_symbol.items():
        valid: List[Candle] = []
        for candle in entries:
            dt = candle.get('date')
            close_val = candle.get('close')
            if not isinstance(dt, datetime) or not isinstance(close_val, (int, float)):
                continue
            volume_val = candle.get('volume')
            if isinstance(volume_val, (int, float)):
                volume_val = float(volume_val)
            else:
                volume_val = None
            high_val = candle.get('high')
            if not isinstance(high_val, (int, float)):
                high_val = None
            else:
                high_val = float(high_val)
            low_val = candle.get('low')
            if not isinstance(low_val, (int, float)):
                low_val = None
            else:
                low_val = float(low_val)
            valid.append(Candle(
                date=dt,
                close=float(close_val),
                volume=volume_val,
                high=high_val,
                low=low_val,
            ))
            if overall_first is None or dt < overall_first:
                overall_first = dt
            if overall_last is None or dt > overall_last:
                overall_last = dt
        if len(valid) < RSI_PERIOD + 1:
            continue
        valid.sort(key=lambda c: c.date)

        closes = [c.close for c in valid]
        rsi_series = _compute_rsi_series(closes, RSI_PERIOD)
        latest_rsi = rsi_series[-1]
        if latest_rsi is None or latest_rsi <= 50:
            continue

        previous_rsi = next((val for val in reversed(rsi_series[:-1]) if val is not None), None)
        latest_candle = valid[-1]
        earliest_candle = valid[0]

        volume_thrust = _compute_volume_thrust(valid, VOL_WINDOW)
        mfi_bias = _compute_mfi(valid, MFI_PERIOD)
        rsi_slope = _compute_rsi_slope_score(latest_rsi, previous_rsi)

        level = latest_rsi
        slope_component = rsi_slope if rsi_slope is not None else 50.0
        volume_component = volume_thrust if volume_thrust is not None else 50.0
        mf_component = mfi_bias if mfi_bias is not None else 50.0

        composite = (
            0.40 * level +
            0.20 * slope_component +
            0.30 * volume_component +
            0.10 * mf_component
        )

        row = {
            'symbol': symbol,
            'price': _safe_round(latest_candle.close),
            'tradingDate': _fmt_date(earliest_candle.date),
            'ltcDate': _fmt_date(latest_candle.date),
            'tradingDays': len(valid),
            'rsi': _safe_round(latest_rsi),
            'rsiSlope': _safe_round((latest_rsi - previous_rsi) if previous_rsi is not None else None),
            'volumeThrust': _safe_round(volume_thrust),
            'mfBias': _safe_round(mfi_bias),
            'rsiScore': _safe_round(composite),
        }
        rows.append(row)

    rows.sort(key=lambda item: item.get('rsiScore', 0), reverse=True)

    return {
        'rows': rows,
        'count': len(rows),
        'generatedAt': datetime.utcnow().isoformat() + 'Z',
        'filters': {
            'minRsi': 50,
            'period': RSI_PERIOD,
        },
        'meta': {
            'cutoffMonths': months,
            'baseCutoffMonths': CUTOFF_MONTHS,
            'timeframe': tf,
            'startDate': overall_first.strftime('%Y-%m-%d') if overall_first else None,
            'endDate': overall_last.strftime('%Y-%m-%d') if overall_last else None,
        },
    }
