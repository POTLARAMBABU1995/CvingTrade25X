from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from db import fetch_ohlc_series_from_oracle
from services.technical_utils import aggregate_ohlc_series_by_timeframe, indicator_lookback_months, normalize_timeframe
from services.trend_service import ema

ATR_PERIOD = 14
EMA_PERIOD = 50
RSI_PERIOD = 14
EPSILON = 1e-9
CUTOFF_MONTHS = 6


@dataclass
class Candle:
  date: datetime
  high: float
  low: float
  close: float


def _fmt_date(dt: Optional[datetime]) -> str:
  if isinstance(dt, datetime):
    try:
      return dt.strftime('%d-%m-%Y')
    except Exception:
      return ''
  return ''


def _safe_round(value: Optional[float], digits: int = 2) -> Optional[float]:
  if value is None:
    return None
  try:
    return round(float(value), digits)
  except Exception:
    return None


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
  if value < lower:
    return lower
  if value > upper:
    return upper
  return value


def _true_ranges(candles: List[Candle]) -> List[float]:
  ranges: List[float] = []
  prev_close: Optional[float] = None
  for candle in candles:
    high = candle.high
    low = candle.low
    close = candle.close
    if prev_close is None:
      tr = high - low
    else:
      tr = max(
        high - low,
        abs(high - prev_close),
        abs(low - prev_close),
      )
    ranges.append(tr)
    prev_close = close
  return ranges


def _wilder_atr(trs: List[float], period: int) -> List[Optional[float]]:
  length = len(trs)
  if length < period:
    return [None] * length
  atrs: List[Optional[float]] = [None] * length
  first_avg = sum(trs[:period]) / period
  atrs[period - 1] = first_avg
  for idx in range(period, length):
    prev_atr = atrs[idx - 1]
    if prev_atr is None:
      prev_atr = first_avg
    atrs[idx] = ((prev_atr * (period - 1)) + trs[idx]) / period
  return atrs


def _compute_rsi(closes: List[float], period: int = RSI_PERIOD) -> List[Optional[float]]:
  length = len(closes)
  if length < period + 1:
    return [None] * length
  rsis: List[Optional[float]] = [None] * length
  gains = []
  losses = []
  for i in range(1, period + 1):
    change = closes[i] - closes[i - 1]
    gains.append(max(change, 0.0))
    losses.append(max(-change, 0.0))
  avg_gain = sum(gains) / period
  avg_loss = sum(losses) / period
  if avg_loss == 0:
    rs = None
  else:
    rs = avg_gain / avg_loss
  rsis[period] = 100.0 if rs is None else 100 - (100 / (1 + rs))

  for idx in range(period + 1, length):
    change = closes[idx] - closes[idx - 1]
    gain = max(change, 0.0)
    loss = max(-change, 0.0)
    avg_gain = ((avg_gain * (period - 1)) + gain) / period
    avg_loss = ((avg_loss * (period - 1)) + loss) / period
    if avg_loss == 0:
      rsis[idx] = 100.0
    else:
      rs = avg_gain / avg_loss
      rsis[idx] = 100 - (100 / (1 + rs))
  return rsis


def _build_candles(entries: List[Dict[str, Any]]) -> List[Candle]:
  candles: List[Candle] = []
  for entry in entries:
    dt = entry.get('date')
    high = entry.get('high')
    low = entry.get('low')
    close = entry.get('close')
    if not isinstance(dt, datetime):
      continue
    try:
      close_val = float(close)
    except (TypeError, ValueError):
      continue
    try:
      high_val = float(high) if high is not None else close_val
    except (TypeError, ValueError):
      high_val = close_val
    try:
      low_val = float(low) if low is not None else close_val
    except (TypeError, ValueError):
      low_val = close_val
    candle = Candle(
      date=dt,
      high=high_val,
      low=low_val,
      close=close_val,
    )
    candles.append(candle)
  candles.sort(key=lambda c: c.date)
  return candles


def compute_atr_rows(timeframe: str = 'daily') -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
  tf = normalize_timeframe(timeframe)
  months = indicator_lookback_months(tf, CUTOFF_MONTHS)
  raw_series = fetch_ohlc_series_from_oracle(months=months)
  series_by_symbol = aggregate_ohlc_series_by_timeframe(raw_series, tf)
  rows: List[Dict[str, Any]] = []
  overall_first: datetime | None = None
  overall_last: datetime | None = None

  for symbol, entries in series_by_symbol.items():
    candles = _build_candles(entries)
    if len(candles) < ATR_PERIOD + 6:
      continue

    closes = [c.close for c in candles]
    atr_input = _true_ranges(candles)
    atr_series = _wilder_atr(atr_input, ATR_PERIOD)
    atr_now = atr_series[-1]
    atr_5 = atr_series[-6] if len(atr_series) >= 6 else None
    if atr_now is None:
      continue

    close_now = closes[-1]
    first_date = candles[0].date
    last_date = candles[-1].date

    ema50_now = ema(closes, EMA_PERIOD) if len(closes) >= EMA_PERIOD else None
    rsi_series = _compute_rsi(closes, RSI_PERIOD)
    rsi_now = rsi_series[-1]

    atr_pct = (atr_now / close_now * 100.0) if close_now else None

    price_strength = 0.0
    if ema50_now and ema50_now > 0:
      price_strength = _clamp((close_now / ema50_now - 1.0) / 0.10) * 100.0

    vol_fit = 0.0
    if atr_pct is not None:
      v_opt = 2.5
      v_tol = 2.5
      vol_fit = max(0.0, 1 - abs(atr_pct - v_opt) / v_tol) * 100.0

    atr_fresh = 0.0
    if atr_5 is not None and atr_5 > 0:
      atr_fresh = _clamp(((atr_now - atr_5) / (atr_5 + EPSILON)) / 0.5) * 100.0

    gate = 1.0
    if (rsi_now is not None and rsi_now < 50.0) or (ema50_now and close_now < ema50_now):
      gate = 0.6

    atr_score = gate * (
      0.50 * price_strength +
      0.30 * vol_fit +
      0.20 * atr_fresh
    )

    row = {
      'symbol': symbol,
      'price': _safe_round(close_now),
      'priceSort': close_now,
      'tradingDate': _fmt_date(first_date),
      'tradingDateSort': first_date.timestamp() if isinstance(first_date, datetime) else None,
      'ltcDate': _fmt_date(last_date),
      'ltcDateSort': last_date.timestamp() if isinstance(last_date, datetime) else None,
      'td': len(candles),
      'tdSort': len(candles),
      'atr': _safe_round(atr_now),
      'atrSort': atr_now,
      'atrPct': _safe_round(atr_pct),
      'atrPctSort': atr_pct,
      'atrScore': _safe_round(atr_score),
      'atrScoreSort': atr_score,
    }
    rows.append(row)
    if first_date and (overall_first is None or first_date < overall_first):
      overall_first = first_date
    if last_date and (overall_last is None or last_date > overall_last):
      overall_last = last_date

  rows.sort(key=lambda item: item.get('atrScoreSort') or 0.0, reverse=True)
  meta = {
    'cutoffMonths': months,
    'baseCutoffMonths': CUTOFF_MONTHS,
    'timeframe': tf,
    'startDate': overall_first.strftime('%Y-%m-%d') if isinstance(overall_first, datetime) else None,
    'endDate': overall_last.strftime('%Y-%m-%d') if isinstance(overall_last, datetime) else None,
  }
  return rows, meta
