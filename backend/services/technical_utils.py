from __future__ import annotations

from datetime import datetime, timedelta
from statistics import fmean
from typing import Any, Dict, Iterable, List, Optional, Tuple

TIMEFRAMES = ('daily', 'weekly', 'monthly', 'yearly')


def normalize_timeframe(value: Any) -> str:
  tf = str(value or 'daily').strip().lower()
  if tf not in TIMEFRAMES:
    raise ValueError('Invalid timeframe')
  return tf


def indicator_lookback_months(timeframe: str, daily_months: int = 6) -> int:
  tf = normalize_timeframe(timeframe)
  if tf == 'daily':
    return int(daily_months)
  if tf == 'weekly':
    return max(int(daily_months), 36)
  if tf == 'monthly':
    return max(int(daily_months), 120)
  return max(int(daily_months), 240)


def analysis_lookback_months(timeframe: str) -> int:
  tf = normalize_timeframe(timeframe)
  if tf == 'daily':
    return 24
  if tf == 'weekly':
    return 60
  if tf == 'monthly':
    return 132
  return 300


def _safe_float(value: Any) -> Optional[float]:
  if value is None:
    return None
  try:
    out = float(value)
  except (TypeError, ValueError):
    return None
  return out


def _bucket_for_timeframe(timeframe: str, dt: datetime) -> datetime:
  if timeframe == 'weekly':
    start = dt.date() - timedelta(days=dt.weekday())
    return datetime(start.year, start.month, start.day)
  if timeframe == 'monthly':
    return datetime(dt.year, dt.month, 1)
  if timeframe == 'yearly':
    return datetime(dt.year, 1, 1)
  return dt


def normalize_ohlc_candles(entries: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
  candles: List[Dict[str, Any]] = []
  for entry in entries or []:
    dt = entry.get('date') if isinstance(entry, dict) else None
    close_val = _safe_float(entry.get('close')) if isinstance(entry, dict) else None
    if not isinstance(dt, datetime) or close_val is None:
      continue
    open_val = _safe_float(entry.get('open')) if isinstance(entry, dict) else None
    high_val = _safe_float(entry.get('high')) if isinstance(entry, dict) else None
    low_val = _safe_float(entry.get('low')) if isinstance(entry, dict) else None
    volume_val = _safe_float(entry.get('volume')) if isinstance(entry, dict) else None
    candles.append({
      'date': dt,
      'open': open_val if open_val is not None else close_val,
      'high': high_val if high_val is not None else close_val,
      'low': low_val if low_val is not None else close_val,
      'close': close_val,
      'volume': volume_val,
    })
  candles.sort(key=lambda item: item['date'])
  return candles


def aggregate_ohlc_series_by_timeframe(
  series_by_symbol: Dict[str, List[Dict[str, Any]]],
  timeframe: str,
) -> Dict[str, List[Dict[str, Any]]]:
  tf = normalize_timeframe(timeframe)
  normalized = {
    str(symbol or '').strip().upper(): normalize_ohlc_candles(entries)
    for symbol, entries in (series_by_symbol or {}).items()
    if str(symbol or '').strip()
  }
  if tf == 'daily':
    return {symbol: candles for symbol, candles in normalized.items() if candles}

  output: Dict[str, List[Dict[str, Any]]] = {}
  for symbol, candles in normalized.items():
    buckets: Dict[datetime, Dict[str, Any]] = {}
    for candle in candles:
      dt = candle['date']
      bucket_key = _bucket_for_timeframe(tf, dt)
      bucket = buckets.get(bucket_key)
      if bucket is None:
        buckets[bucket_key] = {
          'bucketDate': bucket_key,
          'date': dt,
          'open': candle['open'],
          'high': candle['high'],
          'low': candle['low'],
          'close': candle['close'],
          'volume': candle.get('volume') or 0.0,
        }
        continue
      if dt < bucket['date'] and bucket.get('open') is None:
        bucket['open'] = candle['open']
      if dt > bucket['date']:
        bucket['date'] = dt
        bucket['close'] = candle['close']
      if candle.get('high') is not None:
        bucket['high'] = max(bucket.get('high') or candle['high'], candle['high'])
      if candle.get('low') is not None:
        bucket['low'] = min(bucket.get('low') or candle['low'], candle['low'])
      if candle.get('volume') is not None:
        bucket['volume'] = (bucket.get('volume') or 0.0) + float(candle['volume'])
    output[symbol] = [
      {
        'date': row['date'],
        'bucketDate': row.get('bucketDate'),
        'open': row.get('open') if row.get('open') is not None else row.get('close'),
        'high': row.get('high') if row.get('high') is not None else row.get('close'),
        'low': row.get('low') if row.get('low') is not None else row.get('close'),
        'close': row.get('close'),
        'volume': row.get('volume'),
      }
      for _bucket, row in sorted(buckets.items(), key=lambda item: item[0])
      if row.get('close') is not None
    ]
  return {symbol: candles for symbol, candles in output.items() if candles}


def calculate_ema(values: List[float], period: int) -> Optional[float]:
  clean = [float(value) for value in values or [] if value is not None]
  if not clean:
    return None
  k = 2.0 / (float(period) + 1.0)
  ema_value = clean[0]
  for value in clean[1:]:
    ema_value = (value * k) + (ema_value * (1.0 - k))
  return float(ema_value)


def calculate_rsi(values: List[float], period: int = 14) -> Optional[float]:
  clean = [float(value) for value in values or [] if value is not None]
  if len(clean) < period + 1:
    return None
  gains: List[float] = []
  losses: List[float] = []
  for idx in range(1, period + 1):
    delta = clean[idx] - clean[idx - 1]
    gains.append(max(delta, 0.0))
    losses.append(max(-delta, 0.0))
  avg_gain = sum(gains) / float(period)
  avg_loss = sum(losses) / float(period)
  rsi = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + (avg_gain / avg_loss)))
  for idx in range(period + 1, len(clean)):
    delta = clean[idx] - clean[idx - 1]
    gain = max(delta, 0.0)
    loss = max(-delta, 0.0)
    avg_gain = ((avg_gain * (period - 1)) + gain) / float(period)
    avg_loss = ((avg_loss * (period - 1)) + loss) / float(period)
    rsi = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + (avg_gain / avg_loss)))
  return float(rsi)


def _ema_series_values(values: List[float], period: int) -> List[float]:
  clean = [float(value) for value in values or [] if value is not None]
  if not clean:
    return []
  k = 2.0 / (float(period) + 1.0)
  out: List[float] = []
  previous: Optional[float] = None
  for value in clean:
    previous = value if previous is None else (value * k) + (previous * (1.0 - k))
    out.append(float(previous))
  return out


def calculate_macd(
  values: List[float],
  *,
  fast_period: int = 12,
  slow_period: int = 26,
  signal_period: int = 9,
) -> Dict[str, Optional[float]]:
  clean = [float(value) for value in values or [] if value is not None]
  if len(clean) < slow_period + 1:
    return {'macd': None, 'signal': None, 'hist': None}
  fast = _ema_series_values(clean, fast_period)
  slow = _ema_series_values(clean, slow_period)
  macd_values = [fast_value - slow_value for fast_value, slow_value in zip(fast, slow)]
  signal_values = _ema_series_values(macd_values, signal_period)
  if not macd_values or not signal_values:
    return {'macd': None, 'signal': None, 'hist': None}
  macd = macd_values[-1]
  signal = signal_values[-1]
  return {'macd': float(macd), 'signal': float(signal), 'hist': float(macd - signal)}


def _true_ranges(candles: List[Dict[str, Any]]) -> List[float]:
  ranges: List[float] = []
  previous_close: Optional[float] = None
  for candle in candles:
    high = _safe_float(candle.get('high'))
    low = _safe_float(candle.get('low'))
    close = _safe_float(candle.get('close'))
    if high is None or low is None or close is None:
      continue
    if previous_close is None:
      tr = high - low
    else:
      tr = max(high - low, abs(high - previous_close), abs(low - previous_close))
    ranges.append(max(float(tr), 0.0))
    previous_close = close
  return ranges


def calculate_atr(candles: List[Dict[str, Any]], period: int = 14) -> Optional[float]:
  trs = _true_ranges(candles)
  if len(trs) < period:
    return None
  atr = sum(trs[:period]) / float(period)
  for value in trs[period:]:
    atr = ((atr * (period - 1)) + value) / float(period)
  return float(atr)


def calculate_adx(candles: List[Dict[str, Any]], period: int = 14) -> Dict[str, Optional[float]]:
  normalized = normalize_ohlc_candles(candles)
  if len(normalized) < period + 1:
    return {'adx': None, 'plusDi': None, 'minusDi': None, 'atr': calculate_atr(normalized, period)}

  tr_values: List[float] = []
  plus_dm_values: List[float] = []
  minus_dm_values: List[float] = []
  for idx in range(1, len(normalized)):
    current = normalized[idx]
    previous = normalized[idx - 1]
    high = _safe_float(current.get('high'))
    low = _safe_float(current.get('low'))
    close_prev = _safe_float(previous.get('close'))
    high_prev = _safe_float(previous.get('high'))
    low_prev = _safe_float(previous.get('low'))
    if high is None or low is None or close_prev is None or high_prev is None or low_prev is None:
      continue
    up_move = high - high_prev
    down_move = low_prev - low
    plus_dm_values.append(up_move if up_move > down_move and up_move > 0 else 0.0)
    minus_dm_values.append(down_move if down_move > up_move and down_move > 0 else 0.0)
    tr_values.append(max(high - low, abs(high - close_prev), abs(low - close_prev)))

  if len(tr_values) < period:
    return {'adx': None, 'plusDi': None, 'minusDi': None, 'atr': calculate_atr(normalized, period)}

  tr_sum = sum(tr_values[:period])
  plus_dm_sum = sum(plus_dm_values[:period])
  minus_dm_sum = sum(minus_dm_values[:period])

  def _di(dm_value: float, tr_value: float) -> float:
    return 100.0 * dm_value / tr_value if tr_value else 0.0

  plus_di = _di(plus_dm_sum, tr_sum)
  minus_di = _di(minus_dm_sum, tr_sum)
  denom = plus_di + minus_di
  dx_values: List[float] = [100.0 * abs(plus_di - minus_di) / denom if denom else 0.0]

  for idx in range(period, len(tr_values)):
    tr_sum = tr_sum - (tr_sum / period) + tr_values[idx]
    plus_dm_sum = plus_dm_sum - (plus_dm_sum / period) + plus_dm_values[idx]
    minus_dm_sum = minus_dm_sum - (minus_dm_sum / period) + minus_dm_values[idx]
    plus_di = _di(plus_dm_sum, tr_sum)
    minus_di = _di(minus_dm_sum, tr_sum)
    denom = plus_di + minus_di
    dx_values.append(100.0 * abs(plus_di - minus_di) / denom if denom else 0.0)

  if len(dx_values) < period:
    return {'adx': None, 'plusDi': plus_di, 'minusDi': minus_di, 'atr': calculate_atr(normalized, period)}

  adx = sum(dx_values[:period]) / float(period)
  for value in dx_values[period:]:
    adx = ((adx * (period - 1)) + value) / float(period)
  return {'adx': float(adx), 'plusDi': float(plus_di), 'minusDi': float(minus_di), 'atr': calculate_atr(normalized, period)}


def detect_swing_pivots(
  candles: List[Dict[str, Any]],
  *,
  window: int = 3,
  atr_period: int = 14,
  min_atr_multiple: float = 0.75,
) -> List[Dict[str, Any]]:
  if len(candles) < (window * 2) + 1:
    return []
  atr = calculate_atr(candles, atr_period)
  latest_close = _safe_float(candles[-1].get('close')) or 0.0
  min_distance = (atr or (latest_close * 0.01)) * float(min_atr_multiple)

  candidates: List[Dict[str, Any]] = []
  for idx in range(window, len(candles) - window):
    candle = candles[idx]
    high = _safe_float(candle.get('high'))
    low = _safe_float(candle.get('low'))
    if high is None or low is None:
      continue
    left = candles[idx - window:idx]
    right = candles[idx + 1:idx + window + 1]
    local_highs = [_safe_float(item.get('high')) for item in [*left, *right]]
    local_lows = [_safe_float(item.get('low')) for item in [*left, *right]]
    high_values = [value for value in local_highs if value is not None]
    low_values = [value for value in local_lows if value is not None]
    if high_values and high >= max(high_values):
      candidates.append({'index': idx, 'date': candle.get('date'), 'type': 'high', 'price': high})
    if low_values and low <= min(low_values):
      candidates.append({'index': idx, 'date': candle.get('date'), 'type': 'low', 'price': low})

  accepted: List[Dict[str, Any]] = []
  for pivot in sorted(candidates, key=lambda item: item['index']):
    if not accepted:
      accepted.append(pivot)
      continue
    last = accepted[-1]
    if pivot['type'] == last['type']:
      if pivot['type'] == 'high' and pivot['price'] > last['price']:
        accepted[-1] = pivot
      elif pivot['type'] == 'low' and pivot['price'] < last['price']:
        accepted[-1] = pivot
      continue
    if abs(float(pivot['price']) - float(last['price'])) >= min_distance:
      accepted.append(pivot)
  return accepted


def detect_higher_high_higher_low(pivots: List[Dict[str, Any]]) -> Dict[str, Any]:
  highs = [pivot for pivot in pivots if pivot.get('type') == 'high']
  lows = [pivot for pivot in pivots if pivot.get('type') == 'low']
  latest_high = highs[-1] if highs else None
  previous_high = highs[-2] if len(highs) >= 2 else None
  latest_low = lows[-1] if lows else None
  previous_low = lows[-2] if len(lows) >= 2 else None
  higher_high = bool(latest_high and previous_high and latest_high['price'] > previous_high['price'])
  lower_high = bool(latest_high and previous_high and latest_high['price'] < previous_high['price'])
  higher_low = bool(latest_low and previous_low and latest_low['price'] > previous_low['price'])
  lower_low = bool(latest_low and previous_low and latest_low['price'] < previous_low['price'])
  labels: List[str] = []
  if higher_high:
    labels.append('Higher High')
  if higher_low:
    labels.append('Higher Low')
  if lower_high:
    labels.append('Lower High')
  if lower_low:
    labels.append('Lower Low')
  return {
    'higherHigh': higher_high,
    'higherLow': higher_low,
    'lowerHigh': lower_high,
    'lowerLow': lower_low,
    'labels': labels,
    'latestHigh': latest_high,
    'previousHigh': previous_high,
    'latestLow': latest_low,
    'previousLow': previous_low,
  }


def calculate_support_resistance(
  candles: List[Dict[str, Any]],
  pivots: List[Dict[str, Any]] | None = None,
  *,
  lookback: int = 120,
) -> Dict[str, Any]:
  if not candles:
    return {'nearestSupport': None, 'nearestResistance': None, 'supportLevels': [], 'resistanceLevels': []}
  latest_close = _safe_float(candles[-1].get('close'))
  if latest_close is None:
    return {'nearestSupport': None, 'nearestResistance': None, 'supportLevels': [], 'resistanceLevels': []}

  recent_candles = candles[-lookback:]
  pivot_rows = pivots or detect_swing_pivots(recent_candles)
  support_levels = sorted({
    round(float(pivot['price']), 4)
    for pivot in pivot_rows
    if pivot.get('type') == 'low' and _safe_float(pivot.get('price')) is not None and float(pivot['price']) <= latest_close
  })
  resistance_levels = sorted({
    round(float(pivot['price']), 4)
    for pivot in pivot_rows
    if pivot.get('type') == 'high' and _safe_float(pivot.get('price')) is not None and float(pivot['price']) >= latest_close
  })
  if not support_levels:
    lows = [_safe_float(candle.get('low')) for candle in recent_candles]
    support_levels = [round(float(min(value for value in lows if value is not None)), 4)] if any(value is not None for value in lows) else []
  if not resistance_levels:
    highs = [_safe_float(candle.get('high')) for candle in recent_candles]
    resistance_levels = [round(float(max(value for value in highs if value is not None)), 4)] if any(value is not None for value in highs) else []
  nearest_support = max((level for level in support_levels if level <= latest_close), default=None)
  nearest_resistance = min((level for level in resistance_levels if level >= latest_close), default=None)
  return {
    'nearestSupport': nearest_support,
    'nearestResistance': nearest_resistance,
    'supportLevels': support_levels[-5:],
    'resistanceLevels': resistance_levels[:5],
  }


def classify_trend_structure(
  candles: List[Dict[str, Any]],
  pivots: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
  pivot_rows = pivots or detect_swing_pivots(candles)
  structure = detect_higher_high_higher_low(pivot_rows)
  closes = [_safe_float(candle.get('close')) for candle in candles[-40:]]
  clean_closes = [value for value in closes if value is not None]
  range_pct = None
  if len(clean_closes) >= 10:
    low = min(clean_closes)
    high = max(clean_closes)
    latest = clean_closes[-1]
    range_pct = ((high - low) / latest * 100.0) if latest else None

  if structure['higherHigh'] and structure['higherLow']:
    status = 'Strong Uptrend'
    score = 100.0
  elif structure['higherLow'] and not structure['lowerLow']:
    status = 'Uptrend'
    score = 78.0
  elif structure['lowerHigh'] and structure['lowerLow']:
    status = 'Downtrend'
    score = 25.0
  elif range_pct is not None and range_pct <= 8.0 and structure['higherLow']:
    status = 'Accumulation'
    score = 64.0
  else:
    status = 'Range'
    score = 48.0
  return {
    'status': status,
    'score': score,
    'rangePct': range_pct,
    **structure,
  }


def calculate_volume_ratio(candles: List[Dict[str, Any]], window: int = 20) -> Optional[float]:
  if len(candles) < window + 1:
    return None
  latest_volume = _safe_float(candles[-1].get('volume'))
  if latest_volume is None or latest_volume <= 0:
    return None
  prior = [
    _safe_float(candle.get('volume'))
    for candle in candles[-(window + 1):-1]
  ]
  prior_clean = [value for value in prior if value is not None and value > 0]
  if not prior_clean:
    return None
  avg_volume = fmean(prior_clean)
  if avg_volume <= 0:
    return None
  return float(latest_volume / avg_volume)


def detect_resistance_breakout(
  candles: List[Dict[str, Any]],
  *,
  resistance: Optional[float] = None,
  volume_ratio: Optional[float] = None,
  ema20: Optional[float] = None,
  ema50: Optional[float] = None,
) -> Dict[str, Any]:
  if len(candles) < 2:
    return {'status': 'No Breakout', 'score': 0.0, 'confirmed': False}
  latest = candles[-1]
  previous = candles[-2]
  close = _safe_float(latest.get('close'))
  high = _safe_float(latest.get('high'))
  low = _safe_float(latest.get('low'))
  prev_close = _safe_float(previous.get('close'))
  if close is None or high is None or low is None or resistance is None:
    return {'status': 'No Breakout', 'score': 0.0, 'confirmed': False}

  candle_range = max(high - low, 0.000001)
  close_near_high = ((high - close) / candle_range) <= 0.25
  has_volume = volume_ratio is not None and volume_ratio >= 1.5
  not_overextended = True
  if ema20 and ema20 > 0 and close > ema20 * 1.12:
    not_overextended = False
  if ema50 and ema50 > 0 and close > ema50 * 1.20:
    not_overextended = False
  broke = close > resistance
  failed = bool(prev_close and prev_close > resistance and close < resistance)

  if broke and has_volume and close_near_high and not_overextended:
    return {'status': 'Volume Confirmed Breakout', 'score': 100.0, 'confirmed': True}
  if broke and close_near_high and not_overextended:
    return {'status': 'Resistance Breakout', 'score': 72.0, 'confirmed': False}
  if failed:
    return {'status': 'Failed Breakout', 'score': 15.0, 'confirmed': False}
  return {'status': 'No Breakout', 'score': 0.0, 'confirmed': False}


def classify_risk_level(
  *,
  price: Optional[float],
  nearest_support: Optional[float],
  nearest_resistance: Optional[float],
  atr: Optional[float],
  ema20: Optional[float] = None,
) -> Dict[str, Any]:
  if price is None or price <= 0:
    return {'riskLevel': 'Unknown', 'riskScore': 40.0, 'invalidationLevel': nearest_support}
  support_gap = ((price - nearest_support) / price * 100.0) if nearest_support else None
  resistance_gap = ((nearest_resistance - price) / price * 100.0) if nearest_resistance else None
  atr_pct = (atr / price * 100.0) if atr else None
  over_ema = ((price - ema20) / ema20 * 100.0) if ema20 else None

  score = 70.0
  if support_gap is not None:
    if support_gap <= 4.0:
      score += 15.0
    elif support_gap > 10.0:
      score -= 18.0
  if resistance_gap is not None and resistance_gap < 3.0:
    score -= 8.0
  if atr_pct is not None and atr_pct > 6.0:
    score -= 14.0
  if over_ema is not None and over_ema > 12.0:
    score -= 16.0
  score = max(0.0, min(100.0, score))
  if score >= 72.0:
    level = 'Low'
  elif score >= 50.0:
    level = 'Medium'
  else:
    level = 'High'
  invalidation = nearest_support
  if nearest_support and atr:
    invalidation = nearest_support - (atr * 0.25)
  return {'riskLevel': level, 'riskScore': score, 'invalidationLevel': invalidation}
