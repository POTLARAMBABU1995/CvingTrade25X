from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from db import fetch_ohlc_series_from_oracle
from services.technical_utils import aggregate_ohlc_series_by_timeframe, indicator_lookback_months, normalize_timeframe

ADX_PERIOD = 14
CUTOFF_MONTHS = 6
SCHEMA_VERSION = 2


@dataclass
class Candle:
  date: datetime
  high: float
  low: float
  close: float


def _fmt_date(dt: Optional[datetime]) -> str:
  if not isinstance(dt, datetime):
    return ''
  try:
    return dt.strftime('%d-%m-%Y')
  except Exception:
    return ''


def _safe_round(value: Optional[float], digits: int = 2) -> Optional[float]:
  if value is None:
    return None
  try:
    return round(float(value), digits)
  except Exception:
    return None


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
    candles.append(Candle(date=dt, high=high_val, low=low_val, close=close_val))
  candles.sort(key=lambda candle: candle.date)
  return candles


def _compute_dmi_snapshot(
  candles: List[Candle],
  period: int = ADX_PERIOD,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
  if len(candles) < (period * 2) + 1:
    return None, None, None

  tr_list: List[float] = []
  plus_dm_list: List[float] = []
  minus_dm_list: List[float] = []

  for idx in range(1, len(candles)):
    current = candles[idx]
    previous = candles[idx - 1]
    up_move = current.high - previous.high
    down_move = previous.low - current.low
    plus_dm = up_move if up_move > down_move and up_move > 0 else 0.0
    minus_dm = down_move if down_move > up_move and down_move > 0 else 0.0
    true_range = max(
      current.high - current.low,
      abs(current.high - previous.close),
      abs(current.low - previous.close),
    )
    tr_list.append(true_range)
    plus_dm_list.append(plus_dm)
    minus_dm_list.append(minus_dm)

  if len(tr_list) < period:
    return None, None, None

  tr_n = sum(tr_list[:period])
  plus_dm_n = sum(plus_dm_list[:period])
  minus_dm_n = sum(minus_dm_list[:period])

  def _di(dm_value: float, tr_value: float) -> float:
    return (100.0 * dm_value / tr_value) if tr_value else 0.0

  plus_di = _di(plus_dm_n, tr_n)
  minus_di = _di(minus_dm_n, tr_n)
  last_plus_di = plus_di
  last_minus_di = minus_di

  dx_list: List[float] = []
  denominator = plus_di + minus_di
  dx_list.append(100.0 * abs(plus_di - minus_di) / denominator if denominator else 0.0)

  for idx in range(period, len(tr_list)):
    tr_n = tr_n - (tr_n / period) + tr_list[idx]
    plus_dm_n = plus_dm_n - (plus_dm_n / period) + plus_dm_list[idx]
    minus_dm_n = minus_dm_n - (minus_dm_n / period) + minus_dm_list[idx]
    plus_di = _di(plus_dm_n, tr_n)
    minus_di = _di(minus_dm_n, tr_n)
    last_plus_di = plus_di
    last_minus_di = minus_di
    denominator = plus_di + minus_di
    dx_list.append(100.0 * abs(plus_di - minus_di) / denominator if denominator else 0.0)

  if len(dx_list) < period:
    return last_plus_di, last_minus_di, None

  adx = sum(dx_list[:period]) / period
  for dx in dx_list[period:]:
    adx = ((adx * (period - 1)) + dx) / period

  return last_plus_di, last_minus_di, adx


def compute_adx_rows(timeframe: str = 'daily') -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
  tf = normalize_timeframe(timeframe)
  months = indicator_lookback_months(tf, CUTOFF_MONTHS)
  raw_series = fetch_ohlc_series_from_oracle(months=months)
  series_by_symbol = aggregate_ohlc_series_by_timeframe(raw_series, tf)
  rows: List[Dict[str, Any]] = []
  overall_first: datetime | None = None
  overall_last: datetime | None = None

  for symbol, entries in series_by_symbol.items():
    candles = _build_candles(entries)
    if len(candles) < (ADX_PERIOD * 2) + 1:
      continue

    plus_di, minus_di, adx = _compute_dmi_snapshot(candles, ADX_PERIOD)
    if adx is None or adx < 20.0:
      continue

    first_date = candles[0].date
    last_date = candles[-1].date
    close_now = candles[-1].close
    adx_gt_20 = adx >= 20.0
    adx_gt_25 = adx >= 25.0
    dmi_spread = abs((plus_di or 0.0) - (minus_di or 0.0))
    adx_score = adx + dmi_spread

    rows.append({
      'symbol': symbol,
      'price': _safe_round(close_now),
      'priceSort': close_now,
      'tradingDate': _fmt_date(first_date),
      'tradingDateSort': first_date.timestamp() if isinstance(first_date, datetime) else None,
      'ltcDate': _fmt_date(last_date),
      'ltcDateSort': last_date.timestamp() if isinstance(last_date, datetime) else None,
      'td': len(candles),
      'tdSort': len(candles),
      'adxGt20': _safe_round(adx) if adx_gt_20 else None,
      'adxGt20Sort': adx if adx_gt_20 else None,
      'adxGt25': _safe_round(adx) if adx_gt_25 else None,
      'adxGt25Sort': adx if adx_gt_25 else None,
      'plusDm': _safe_round(plus_di),
      'plusDmSort': plus_di,
      'minusDm': _safe_round(minus_di),
      'minusDmSort': minus_di,
      'adxScore': _safe_round(adx_score),
      'adxScoreSort': adx_score,
      'adxValue': _safe_round(adx),
      'adxValueSort': adx,
    })

    if overall_first is None or first_date < overall_first:
      overall_first = first_date
    if overall_last is None or last_date > overall_last:
      overall_last = last_date

  rows.sort(key=lambda item: item.get('adxScoreSort') or 0.0, reverse=True)
  threshold_counts = {
    'adx20': len(rows),
    'adx25': sum(1 for row in rows if row.get('adxValueSort') is not None and row.get('adxValueSort') >= 25.0),
  }
  meta = {
    'cutoffMonths': months,
    'baseCutoffMonths': CUTOFF_MONTHS,
    'timeframe': tf,
    'startDate': overall_first.strftime('%Y-%m-%d') if isinstance(overall_first, datetime) else None,
    'endDate': overall_last.strftime('%Y-%m-%d') if isinstance(overall_last, datetime) else None,
    'thresholdCounts': threshold_counts,
    'schemaVersion': SCHEMA_VERSION,
  }
  return rows, meta
