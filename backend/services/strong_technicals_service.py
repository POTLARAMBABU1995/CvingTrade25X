from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from math import isfinite
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from cache import TTLCache, background_refresh, load_json_snapshot, save_json_snapshot
from db import fetch_latest_trade_date_from_oracle, fetch_ohlc_series_from_oracle

try:
  from db import fetch_recent_ohlc_series_from_oracle
except Exception:  # pragma: no cover
  fetch_recent_ohlc_series_from_oracle = None  # type: ignore
from services.technical_utils import (
  aggregate_ohlc_series_by_timeframe,
  analysis_lookback_months,
  calculate_adx,
  calculate_atr,
  calculate_ema,
  calculate_macd,
  calculate_rsi,
  calculate_support_resistance,
  calculate_volume_ratio,
  classify_risk_level,
  classify_trend_structure,
  detect_resistance_breakout,
  detect_swing_pivots,
  normalize_timeframe,
)
from services import nse_mcap_service as nse_mcap_svc

try:
  from services.ath_service import get_all_time_high_for_symbols
except Exception:  # pragma: no cover
  get_all_time_high_for_symbols = None  # type: ignore

try:
  from services.delivery_service import fetch_latest_delivery_scores_for_symbols, normalize_delivery_symbol
except Exception:  # pragma: no cover
  fetch_latest_delivery_scores_for_symbols = None  # type: ignore
  normalize_delivery_symbol = None  # type: ignore


_logger = logging.getLogger(__name__)
_cache = TTLCache(ttl_seconds=int(os.getenv('STRONG_TECH_CACHE_TTL_SECONDS', '600')), max_items=64)
_SOURCE_TABLE = os.getenv('ORACLE_TABLE', 'NSE_NIFTY500_DAILY_RAW_DATA_DEV')
_SNAPSHOT_DIR = Path(__file__).resolve().parents[1] / 'data' / 'cache' / 'strong_technicals'
_TREND_SNAPSHOT_DIR = Path(__file__).resolve().parents[1] / 'data'
_TREND_TABLE_KEYS = ('ema20', 'ema50', 'ema200', 'ema200100', 'ema20010050', 'ema2001005020')


def _fmt_date(dt: Any) -> str:
  if isinstance(dt, datetime):
    return dt.strftime('%d-%m-%Y')
  return ''


def _safe_round(value: Any, digits: int = 2) -> Optional[float]:
  try:
    num = float(value)
  except (TypeError, ValueError):
    return None
  if not isfinite(num):
    return None
  return round(num, digits)


def _flag(value: Optional[bool]) -> Optional[str]:
  if value is None:
    return None
  return 'Y' if value else 'N'


def _flag_sort(value: Optional[str]) -> Optional[int]:
  if value == 'Y':
    return 1
  if value == 'N':
    return 0
  return None


def _normalize_symbol_for_ath_lookup(value: Any) -> str:
  token = str(value or '').strip().upper()
  if not token:
    return ''
  if ':' in token:
    token = token.split(':', 1)[1]
  token = token.replace('.NS', '')
  if token.endswith('-EQ'):
    token = token[:-3]
  return token.strip()


def _trend_snapshot_path(timeframe: str) -> str:
  return str(_TREND_SNAPSHOT_DIR / f'snapshot_trend_{normalize_timeframe(timeframe)}.json')


def _load_trend_ath_gap_map(timeframe: str) -> Dict[str, Dict[str, Any]]:
  snapshot = load_json_snapshot(_trend_snapshot_path(timeframe))
  if not isinstance(snapshot, dict):
    return {}
  records: Dict[str, Dict[str, Any]] = {}
  for table_key in _TREND_TABLE_KEYS:
    rows = snapshot.get(table_key)
    if not isinstance(rows, list):
      continue
    for row in rows:
      if not isinstance(row, dict):
        continue
      symbol_key = _normalize_symbol_for_ath_lookup(row.get('symbol') or row.get('stock'))
      if not symbol_key:
        continue
      ath = _safe_round(row.get('athSort') if row.get('athSort') is not None else row.get('ath'))
      gap_sort = _safe_round(row.get('gapSort'))
      if ath is None and gap_sort is None:
        continue
      records.setdefault(symbol_key, row)
  return records


def _apply_ath_gap_record(row: Dict[str, Any], record: Dict[str, Any]) -> bool:
  ath = _safe_round(record.get('athSort') if record.get('athSort') is not None else record.get('ath'))
  if ath is None:
    return False
  price = _safe_round(row.get('priceSort') if row.get('priceSort') is not None else row.get('price'))
  gap_sort = _safe_round(record.get('gapSort'))
  if gap_sort is None and price is not None and ath:
    gap_sort = ((float(price) - float(ath)) / float(ath)) * 100.0
  row['ath'] = ath
  row['ATH'] = ath
  row['athSort'] = ath
  row['ATH_SORT'] = ath
  row['athDate'] = record.get('athDate') or record.get('ath_date')
  row['ath_date'] = record.get('ath_date') or record.get('athDate')
  row['ATH_DATE'] = row['ath_date']
  row['gap'] = record.get('gap') if record.get('gap') not in (None, '') else (f"{gap_sort:+.2f}%" if gap_sort is not None else '-')
  row['GAP'] = row['gap']
  row['gapSort'] = float(gap_sort) if gap_sort is not None else None
  row['GAP_SORT'] = row['gapSort']
  row['distance_from_ath_percent'] = _safe_round(gap_sort)
  row['distanceFromAthPercent'] = _safe_round(gap_sort)
  return True


def _score_band(score: float) -> str:
  if score >= 85:
    return 'Very Strong Technicals'
  if score >= 70:
    return 'Strong Technicals'
  if score >= 55:
    return 'Watchlist / Improving'
  if score >= 40:
    return 'Weak / Range Bound'
  return 'Avoid'


def _ema_alignment_score(closes: List[float]) -> Tuple[float, str, Dict[str, Optional[float]]]:
  ema_values = {
    'ema20': calculate_ema(closes, 20),
    'ema50': calculate_ema(closes, 50),
    'ema100': calculate_ema(closes, 100),
    'ema200': calculate_ema(closes, 200),
  }
  price = closes[-1] if closes else None
  if price is None:
    return 0.0, 'Insufficient EMA', ema_values
  above_count = sum(1 for value in ema_values.values() if value is not None and price > value)
  ordered = (
    ema_values['ema20'] is not None and
    ema_values['ema50'] is not None and
    ema_values['ema100'] is not None and
    ema_values['ema200'] is not None and
    ema_values['ema20'] > ema_values['ema50'] > ema_values['ema100'] > ema_values['ema200']
  )
  score = min(100.0, (above_count * 18.0) + (28.0 if ordered else 0.0))
  if ordered and above_count == 4:
    label = 'Bullish EMA Stack'
  elif above_count >= 3:
    label = 'Bullish EMA Alignment'
  elif above_count >= 2:
    label = 'Mixed EMA Alignment'
  else:
    label = 'Weak EMA Alignment'
  return score, label, ema_values


def _derive_trend_direction(
  *,
  trend: Dict[str, Any],
  close: Optional[float],
  ema20: Optional[float],
  ema50: Optional[float],
  ema100: Optional[float] = None,
) -> str:
  if close is None:
    return '-'
  higher_high = bool(trend.get('higherHigh'))
  higher_low = bool(trend.get('higherLow'))
  lower_high = bool(trend.get('lowerHigh'))
  lower_low = bool(trend.get('lowerLow'))
  if higher_high and higher_low:
    return 'UPTREND'
  if lower_high and lower_low:
    return 'DOWNTREND'
  if ema20 is not None and ema50 is not None and ema100 is not None:
    if close > ema20 > ema50 > ema100:
      return 'UPTREND'
    if close < ema20 < ema50 < ema100:
      return 'DOWNTREND'
    return 'SIDEWAYS'
  if ema20 is not None and ema50 is not None:
    if close > ema20 > ema50:
      return 'UPTREND'
    if close < ema20 < ema50:
      return 'DOWNTREND'
    return 'SIDEWAYS'
  return 'SIDEWAYS'


def _technical_indicator_snapshot(
  candles: List[Dict[str, Any]],
  closes: List[float],
  atr: Optional[float],
) -> Dict[str, Any]:
  macd_payload = calculate_macd(closes)
  macd = macd_payload.get('macd')
  rsi = calculate_rsi(closes)
  adx_payload = calculate_adx(candles)
  adx = adx_payload.get('adx')
  macd_flag = _flag(None if macd is None else macd > 0)
  rsi_flag = _flag(None if rsi is None else rsi > 50)
  adx_flag = _flag(None if adx is None else adx > 25)
  atr_flag = _flag(None if atr is None else atr > 14)
  return {
    'macd': _safe_round(macd),
    'macdSignal': _safe_round(macd_payload.get('signal')),
    'macdHist': _safe_round(macd_payload.get('hist')),
    'macdGt0': macd_flag,
    'MACD_GT_0': macd_flag,
    'macdGt0Sort': _flag_sort(macd_flag),
    'rsi': _safe_round(rsi),
    'rsiGt50': rsi_flag,
    'RSI_GT_50': rsi_flag,
    'rsiGt50Sort': _flag_sort(rsi_flag),
    'adx14': _safe_round(adx),
    'adxGt25': adx_flag,
    'ADX_GT_25': adx_flag,
    'adxGt25Sort': _flag_sort(adx_flag),
    'atr14': _safe_round(atr),
    'atrGt14': atr_flag,
    'ATR_GT_14': atr_flag,
    'atrGt14Sort': _flag_sort(atr_flag),
  }


def _breakout_indicator_snapshot(closes: List[float], atr: Optional[float]) -> Dict[str, Any]:
  macd_payload = calculate_macd(closes)
  macd = macd_payload.get('macd')
  rsi = calculate_rsi(closes)
  macd_flag = _flag(None if macd is None else macd > 0)
  rsi_flag = _flag(None if rsi is None else rsi > 50)
  atr_flag = _flag(None if atr is None else atr > 14)
  return {
    'macd': _safe_round(macd),
    'macdSignal': _safe_round(macd_payload.get('signal')),
    'macdHist': _safe_round(macd_payload.get('hist')),
    'macdGt0': macd_flag,
    'MACD_GT_0': macd_flag,
    'macdGt0Sort': _flag_sort(macd_flag),
    'rsi': _safe_round(rsi),
    'rsiGt50': rsi_flag,
    'RSI_GT_50': rsi_flag,
    'rsiGt50Sort': _flag_sort(rsi_flag),
    'adx14': None,
    'adxGt25': None,
    'ADX_GT_25': None,
    'adxGt25Sort': None,
    'atr14': _safe_round(atr),
    'atrGt14': atr_flag,
    'ATR_GT_14': atr_flag,
    'atrGt14Sort': _flag_sort(atr_flag),
  }


def _trendline_value(p1: Dict[str, Any], p2: Dict[str, Any], index: int) -> Optional[float]:
  x1 = int(p1.get('index') or 0)
  x2 = int(p2.get('index') or 0)
  y1 = float(p1.get('price') or 0.0)
  y2 = float(p2.get('price') or 0.0)
  if x1 == x2:
    return None
  slope = (y2 - y1) / float(x2 - x1)
  return y1 + (slope * (index - x1))


def _analyze_trendline(candles: List[Dict[str, Any]], pivots: List[Dict[str, Any]], atr: Optional[float]) -> Dict[str, Any]:
  if len(candles) < 30 or len(pivots) < 4:
    return {'status': 'No Clean Trendline', 'score': 35.0, 'slope': None, 'touchCount': 0, 'distancePct': None}
  lows = [pivot for pivot in pivots if pivot.get('type') == 'low']
  highs = [pivot for pivot in pivots if pivot.get('type') == 'high']
  latest_close = float(candles[-1].get('close') or 0.0)
  tolerance = max((atr or latest_close * 0.015) * 0.8, latest_close * 0.005)

  def _line_status(points: List[Dict[str, Any]], bullish: bool) -> Dict[str, Any] | None:
    if len(points) < 2:
      return None
    p1, p2 = points[-2], points[-1]
    line_now = _trendline_value(p1, p2, len(candles) - 1)
    if line_now is None or line_now <= 0:
      return None
    slope = (float(p2['price']) - float(p1['price'])) / max(1, int(p2['index']) - int(p1['index']))
    slope_pct = (slope / line_now) * 100.0
    touch_count = 0
    for pivot in points[-5:]:
      value = _trendline_value(p1, p2, int(pivot.get('index') or 0))
      if value is not None and abs(float(pivot['price']) - value) <= tolerance:
        touch_count += 1
    distance_pct = ((latest_close - line_now) / latest_close * 100.0) if latest_close else None
    broken = latest_close < (line_now - tolerance) if bullish else latest_close > (line_now + tolerance)
    if broken:
      status = 'Trendline Broken'
      score = 12.0
    elif bullish and distance_pct is not None and 0 <= distance_pct <= 3.0:
      status = 'Near Trendline Support'
      score = 78.0
    elif bullish and touch_count >= 3 and slope_pct > 0:
      status = 'Strong Support Trendline'
      score = 92.0
    elif bullish and distance_pct is not None and distance_pct < 0.8:
      status = 'Trendline Break Risk'
      score = 42.0
    else:
      status = 'No Clean Trendline'
      score = 45.0
    return {
      'status': status,
      'score': score,
      'slope': slope_pct,
      'touchCount': touch_count,
      'distancePct': distance_pct,
      'lineValue': line_now,
    }

  bullish_points = lows[-5:]
  if len(bullish_points) >= 2 and bullish_points[-1]['price'] >= bullish_points[-2]['price']:
    return _line_status(bullish_points, True) or {'status': 'No Clean Trendline', 'score': 35.0, 'slope': None, 'touchCount': 0, 'distancePct': None}
  bearish_points = highs[-5:]
  if len(bearish_points) >= 2 and bearish_points[-1]['price'] <= bearish_points[-2]['price']:
    result = _line_status(bearish_points, False)
    if result:
      result['status'] = 'No Clean Trendline' if result['status'] != 'Trendline Broken' else 'Trendline Broken'
      result['score'] = min(float(result.get('score') or 35.0), 55.0)
      return result
  return {'status': 'No Clean Trendline', 'score': 35.0, 'slope': None, 'touchCount': 0, 'distancePct': None}


def _recent_range(candles: List[Dict[str, Any]], window: int) -> Dict[str, Optional[float]]:
  recent = candles[-window:] if len(candles) >= window else candles
  highs = [float(item.get('high')) for item in recent if item.get('high') is not None]
  lows = [float(item.get('low')) for item in recent if item.get('low') is not None]
  if not highs or not lows:
    return {'high': None, 'low': None, 'rangePct': None}
  high = max(highs)
  low = min(lows)
  close = float(candles[-1].get('close') or 0.0)
  return {'high': high, 'low': low, 'rangePct': ((high - low) / close * 100.0) if close else None}


_BREAKOUT_FLAG_DEFINITIONS = [
  ('weeklyBO', 'Weekly_BO', 5, 'high'),
  ('monthlyBO', 'Monthly_BO', 20, 'high'),
  ('threeMonthBO', '3M_BO', 63, 'high'),
  ('sixMonthBO', '6M_BO', 126, 'high'),
  ('nineMonthBO', '9M_BO', 189, 'high'),
  ('week52Low', '52WL', 252, 'low'),
  ('week52High', '52WH', 252, 'high'),
  ('twoYearBO', '2Y_BO', 504, 'high'),
  ('threeYearBO', '3Y_BO', 756, 'high'),
  ('fourYearBO', '4Y_BO', 1008, 'high'),
  ('fiveYearBO', '5Y_BO', 1260, 'high'),
  ('tenYearBO', '10Y_BO', 2520, 'high'),
]

_BREAKOUT_FLAG_ALIASES = {
  'weekly_bo': 'weeklyBO',
  'monthly_bo': 'monthlyBO',
  '3m_bo': 'threeMonthBO',
  '6m_bo': 'sixMonthBO',
  '9m_bo': 'nineMonthBO',
  '52wl': 'week52Low',
  '52wh': 'week52High',
  '2y_bo': 'twoYearBO',
  '3y_bo': 'threeYearBO',
  '4y_bo': 'fourYearBO',
  '5y_bo': 'fiveYearBO',
  '10y_bo': 'tenYearBO',
  'ath': 'athBreakout',
  'atl': 'atlBreakout',
}


def _breakout_flag_list(row: Dict[str, Any]) -> List[str]:
  flags = row.get('breakoutFlags') or []
  if isinstance(flags, list):
    return [str(flag or '').strip().lower() for flag in flags]
  return [str(flags or '').strip().lower()]


def _row_has_breakout_flag(row: Dict[str, Any], key: str) -> bool:
  if bool(row.get(key)) or str(row.get(key) or '').strip().upper() == 'Y':
    return True
  flags = _breakout_flag_list(row)
  if key == 'monthlyBO':
    return any('20-day high breakout' in flag for flag in flags)
  if key == 'week52High':
    return any('52-week high breakout' in flag or '52w' in flag for flag in flags)
  if key == 'athBreakout':
    return bool(row.get('athBreakout')) or str(row.get('breakoutStatus') or '').strip().lower() == 'ath breakout'
  return False


def _flag_bool(value: bool | None) -> str:
  if value is True:
    return 'Y'
  if value is False:
    return 'N'
  return '-'


def _breakout_window_flags(candles: List[Dict[str, Any]]) -> Dict[str, Any]:
  if not candles:
    return {}
  latest = candles[-1]
  close = latest.get('close')
  if not isinstance(close, (int, float)):
    return {}
  prior = candles[:-1]
  result: Dict[str, Any] = {}
  for key, label, window, direction in _BREAKOUT_FLAG_DEFINITIONS:
    source = prior[-window:] if len(prior) >= window else []
    values = [
      float(item.get(direction))
      for item in source
      if item.get(direction) is not None
    ]
    passed: bool | None = None
    level: Optional[float] = None
    if len(values) >= window:
      if direction == 'high':
        level = max(values)
        passed = float(close) > level
      else:
        level = min(values)
        passed = float(close) < level
    result[key] = passed is True
    result[label] = _flag_bool(passed)
    result[f'{key}Level'] = _safe_round(level)
  prior_lows = [
    float(item.get('low'))
    for item in prior
    if item.get('low') is not None
  ]
  atl_level = min(prior_lows) if prior_lows else None
  atl_passed = atl_level is not None and float(close) < atl_level
  result['atlBreakout'] = atl_passed
  result['ATL'] = _flag_bool(atl_passed if atl_level is not None else None)
  result['atlLevel'] = _safe_round(atl_level)
  return result


def _analyze_breakout(
  candles: List[Dict[str, Any]],
  resistance: Optional[float],
  volume_ratio: Optional[float],
  ema_values: Dict[str, Optional[float]],
) -> Dict[str, Any]:
  if len(candles) < 22:
    return {'status': 'No Breakout', 'score': 0.0, 'flags': []}
  close = float(candles[-1].get('close') or 0.0)
  prev_high_20 = max(float(item.get('high') or 0.0) for item in candles[-21:-1])
  high_52 = max(float(item.get('high') or 0.0) for item in candles[-253:-1]) if len(candles) >= 253 else None
  box = _recent_range(candles[:-1], 35)
  base = detect_resistance_breakout(
    candles,
    resistance=resistance,
    volume_ratio=volume_ratio,
    ema20=ema_values.get('ema20'),
    ema50=ema_values.get('ema50'),
  )
  flags: List[str] = []
  if resistance and close > resistance:
    flags.append('Resistance Breakout')
  if close > prev_high_20:
    flags.append('20-Day High Breakout')
  if high_52 and close > high_52:
    flags.append('52-Week High Breakout')
  if box['high'] and box['rangePct'] is not None and box['rangePct'] <= 12.0 and close > box['high']:
    flags.append('Box Breakout')
    flags.append('Consolidation Breakout')
  if volume_ratio is not None and volume_ratio >= 1.5 and flags:
    flags.append('Volume Confirmed Breakout')
  status = base.get('status') or 'No Breakout'
  score = float(base.get('score') or 0.0)
  if flags:
    status = 'Volume Confirmed Breakout' if 'Volume Confirmed Breakout' in flags else flags[0]
    score = max(score, 72.0 + min(20.0, len(flags) * 4.0))
  if status == 'Failed Breakout':
    score = 15.0
    flags.append('Failed Breakout')
  return {'status': status, 'score': min(100.0, score), 'flags': list(dict.fromkeys(flags))}


def _analyze_chart_pattern(
  candles: List[Dict[str, Any]],
  pivots: List[Dict[str, Any]],
  breakout: Dict[str, Any],
) -> Dict[str, Any]:
  if len(candles) < 45:
    return {'patternName': '-', 'score': 0.0}
  highs = [pivot for pivot in pivots if pivot.get('type') == 'high']
  lows = [pivot for pivot in pivots if pivot.get('type') == 'low']
  recent = _recent_range(candles, 45)
  close = float(candles[-1].get('close') or 0.0)
  volume_flags = set(breakout.get('flags') or [])

  if len(highs) >= 2 and len(lows) >= 2:
    h1, h2 = highs[-2], highs[-1]
    l1, l2 = lows[-2], lows[-1]
    flat_resistance = abs(float(h2['price']) - float(h1['price'])) / max(close, 1.0) * 100.0 <= 2.5
    higher_lows = float(l2['price']) > float(l1['price'])
    if flat_resistance and higher_lows and ('Resistance Breakout' in volume_flags or 'Volume Confirmed Breakout' in volume_flags):
      return {'patternName': 'Ascending Triangle', 'score': 92.0}
    if float(h2['price']) > float(h1['price']) and float(l2['price']) > float(l1['price']):
      return {'patternName': 'Uptrend Channel', 'score': 74.0}
    wedge_contracting = float(h2['price']) < float(h1['price']) and float(l2['price']) < float(l1['price']) and recent.get('rangePct') is not None and recent['rangePct'] <= 16.0
    if wedge_contracting and volume_flags:
      return {'patternName': 'Falling Wedge Breakout', 'score': 88.0}

  if recent.get('rangePct') is not None and recent['rangePct'] <= 10.0:
    if volume_flags:
      return {'patternName': 'Rectangle / Box Consolidation', 'score': 82.0}
    return {'patternName': 'Rectangle / Box Consolidation', 'score': 62.0}

  if len(candles) >= 65:
    prior = candles[-65:-25]
    flag = candles[-25:]
    prior_first = float(prior[0].get('close') or 0.0)
    prior_last = float(prior[-1].get('close') or 0.0)
    flag_range = _recent_range(flag, 25)
    prior_gain = ((prior_last - prior_first) / prior_first * 100.0) if prior_first else 0.0
    if prior_gain >= 15.0 and flag_range.get('rangePct') is not None and flag_range['rangePct'] <= 12.0:
      return {'patternName': 'Bullish Flag', 'score': 80.0}

  return {'patternName': '-', 'score': 0.0}


def _multi_timeframe_score(candles: List[Dict[str, Any]], current_tf: str) -> float:
  if current_tf != 'daily':
    closes = [float(item.get('close')) for item in candles if item.get('close') is not None]
    ema20 = calculate_ema(closes, 20)
    ema50 = calculate_ema(closes, 50)
    price = closes[-1] if closes else None
    return 78.0 if price and ema20 and price > ema20 and (ema50 is None or price > ema50) else 50.0
  weekly = aggregate_ohlc_series_by_timeframe({'_': candles}, 'weekly').get('_') or []
  monthly = aggregate_ohlc_series_by_timeframe({'_': candles}, 'monthly').get('_') or []
  score = 40.0
  for rows, weight in ((weekly, 35.0), (monthly, 25.0)):
    closes = [float(item.get('close')) for item in rows if item.get('close') is not None]
    if len(closes) < 20:
      continue
    ema20 = calculate_ema(closes, 20)
    ema50 = calculate_ema(closes, 50)
    price = closes[-1]
    if ema20 and price > ema20:
      score += weight * 0.6
    if ema50 and price > ema50:
      score += weight * 0.4
  return min(100.0, score)


def _compute_price_action_rows(timeframe: str, latest_only: bool) -> Dict[str, Any]:
  started = time.perf_counter()
  months = analysis_lookback_months(timeframe)
  raw = fetch_ohlc_series_from_oracle(months=months, cutoff_anchor='latest')
  series_by_symbol = aggregate_ohlc_series_by_timeframe(raw, timeframe)
  rows: List[Dict[str, Any]] = []
  skipped: Dict[str, int] = {}
  latest_dates = [
    candle.get('date')
    for candles in series_by_symbol.values()
    for candle in candles[-1:]
    if isinstance(candle.get('date'), datetime)
  ]
  latest_trading_date = max(latest_dates) if latest_dates else None

  for symbol, candles in series_by_symbol.items():
    if len(candles) < 35:
      skipped['insufficient_candles'] = skipped.get('insufficient_candles', 0) + 1
      continue
    closes = [float(item.get('close')) for item in candles if item.get('close') is not None]
    if len(closes) < 35:
      skipped['missing_close'] = skipped.get('missing_close', 0) + 1
      continue
    latest = candles[-1]
    price = closes[-1]
    atr = calculate_atr(candles)
    pivots = detect_swing_pivots(candles, min_atr_multiple=0.75)
    sr = calculate_support_resistance(candles, pivots)
    trend = classify_trend_structure(candles, pivots)
    _ema_score, ema_label, ema_values = _ema_alignment_score(closes)
    latest_high = trend.get('latestHigh') or {}
    latest_low = trend.get('latestLow') or {}
    latest_high_price = latest_high.get('price') if isinstance(latest_high, dict) else None
    latest_low_price = latest_low.get('price') if isinstance(latest_low, dict) else None
    risk = classify_risk_level(
      price=price,
      nearest_support=sr.get('nearestSupport'),
      nearest_resistance=sr.get('nearestResistance'),
      atr=atr,
      ema20=ema_values.get('ema20'),
    )
    price_action_score = float(trend.get('score') or 0.0)
    trend_direction = _derive_trend_direction(
      trend=trend,
      close=price,
      ema20=ema_values.get('ema20'),
      ema50=ema_values.get('ema50'),
      ema100=ema_values.get('ema100'),
    )
    indicator_snapshot = _technical_indicator_snapshot(candles, closes, atr)
    row = {
      'symbol': symbol,
      'price': _safe_round(price),
      'priceSort': price,
      'ltcDate': _fmt_date(latest.get('date')),
      'ltcDateSort': latest.get('date').timestamp() if isinstance(latest.get('date'), datetime) else None,
      'td': len(candles),
      'timeframe': timeframe,
      'techScore': _safe_round(price_action_score),
      'techScoreSort': price_action_score,
      'techStatus': _score_band(price_action_score),
      'trendStructure': trend.get('status'),
      'trendDirection': trend_direction,
      'trend_direction': trend_direction,
      'Trend_Direction': trend_direction,
      'trendStructureScore': _safe_round(trend.get('score')),
      'priceActionLabels': trend.get('labels') or [],
      'lastSwingHigh': _safe_round(latest_high_price),
      'lastSwingLow': _safe_round(latest_low_price),
      'hhHlStatus': ', '.join(trend.get('labels') or []) or trend.get('status'),
      'support': _safe_round(sr.get('nearestSupport')),
      'resistance': _safe_round(sr.get('nearestResistance')),
      'priceActionScore': _safe_round(price_action_score),
      'emaAlignment': ema_label,
      'nearestSupport': _safe_round(sr.get('nearestSupport')),
      'nearestResistance': _safe_round(sr.get('nearestResistance')),
      'riskLevel': risk.get('riskLevel'),
      'riskQualityScore': _safe_round(risk.get('riskScore')),
      'invalidationLevel': _safe_round(risk.get('invalidationLevel')),
      'atr14': _safe_round(atr),
      'ema20': _safe_round(ema_values.get('ema20')),
      'EMA20': _safe_round(ema_values.get('ema20')),
      'ema50': _safe_round(ema_values.get('ema50')),
      'EMA50': _safe_round(ema_values.get('ema50')),
      'ema100': _safe_round(ema_values.get('ema100')),
      'EMA100': _safe_round(ema_values.get('ema100')),
      'ema200': _safe_round(ema_values.get('ema200')),
      'EMA200': _safe_round(ema_values.get('ema200')),
    }
    row.update(indicator_snapshot)
    rows.append(row)

  ath_stats = _enrich_price_action_ath_gap(rows, timeframe=timeframe)
  rows.sort(key=lambda item: item.get('priceActionScore') or 0.0, reverse=True)
  for idx, row in enumerate(rows, 1):
    row['sNo'] = idx
  duration_ms = round((time.perf_counter() - started) * 1000, 2)
  return {
    'rows': rows,
    'meta': {
      'sourceTable': _SOURCE_TABLE,
      'timeframe': timeframe,
      'lookbackMonths': months,
      'latestOnly': latest_only,
      'latestTradingDate': latest_trading_date.strftime('%Y-%m-%d') if isinstance(latest_trading_date, datetime) else None,
      'symbolsProcessed': len(series_by_symbol),
      'rowsComputed': len(rows),
      'skippedSymbols': skipped,
      'calculationDurationMs': duration_ms,
      'generatedAt': datetime.utcnow().isoformat() + 'Z',
      'computeProfile': 'price_action',
      'athSource': 'NSE_NIFTY500_DAILY_RAW_DATA_DEV',
      'athStats': ath_stats,
    },
    'athSource': 'NSE_NIFTY500_DAILY_RAW_DATA_DEV',
  }


def _enrich_price_action_ath_gap(
  rows: List[Dict[str, Any]],
  *,
  timeframe: str = 'daily',
  endpoint: str = '/api/technicals/price-action',
) -> Dict[str, Any]:
  symbols = [
    _normalize_symbol_for_ath_lookup(row.get('symbol'))
    for row in rows
    if _normalize_symbol_for_ath_lookup(row.get('symbol'))
  ]
  if not symbols:
    return {'attempted': False, 'symbols': 0, 'updated': 0}

  def _needs_enrichment(row: Dict[str, Any]) -> bool:
    return (
      row.get('ath') is None
      or row.get('athSort') is None
      or row.get('gapSort') is None
      or row.get('gap') in (None, '', '-')
    )

  alias_updated = 0
  for row in rows:
    ath_date = row.get('athDate') or row.get('ath_date') or row.get('ATH_DATE')
    if ath_date and (not row.get('athDate') or not row.get('ath_date') or not row.get('ATH_DATE')):
      row['athDate'] = ath_date
      row['ath_date'] = ath_date
      row['ATH_DATE'] = ath_date
      alias_updated += 1

  pending_rows = [row for row in rows if _needs_enrichment(row)]
  if not pending_rows:
    return {
      'attempted': bool(alias_updated),
      'symbols': len(symbols),
      'updated': alias_updated,
      'aliasUpdated': alias_updated,
    }

  updated = alias_updated
  trend_snapshot_updated = 0
  trend_records = _load_trend_ath_gap_map(timeframe)
  if trend_records:
    for row in pending_rows:
      symbol_key = _normalize_symbol_for_ath_lookup(row.get('symbol'))
      record = trend_records.get(symbol_key)
      if record and _apply_ath_gap_record(row, record):
        updated += 1
        trend_snapshot_updated += 1

  pending_rows = [row for row in rows if _needs_enrichment(row)]
  pending_symbols = [
    _normalize_symbol_for_ath_lookup(row.get('symbol'))
    for row in pending_rows
    if _normalize_symbol_for_ath_lookup(row.get('symbol'))
  ]
  pending_symbols = list(dict.fromkeys(pending_symbols))

  if not pending_symbols or get_all_time_high_for_symbols is None:
    return {
      'attempted': True,
      'symbols': len(symbols),
      'updated': updated,
      'aliasUpdated': alias_updated,
      'trendSnapshotUpdated': trend_snapshot_updated,
      'oracleSymbols': len(pending_symbols),
    }

  try:
    ath_records = get_all_time_high_for_symbols(
      pending_symbols,
      include_date=True,
      endpoint=endpoint,
    )
    for row in pending_rows:
      symbol_key = _normalize_symbol_for_ath_lookup(row.get('symbol'))
      record = ath_records.get(symbol_key) or {}
      if _apply_ath_gap_record(row, {'ath': record.get('ath'), 'ath_date': record.get('ath_date')}):
        updated += 1
  except Exception:
    _logger.exception('ATH/GAP enrichment failed for price action rows')
    return {
      'attempted': True,
      'symbols': len(symbols),
      'updated': updated,
      'aliasUpdated': alias_updated,
      'trendSnapshotUpdated': trend_snapshot_updated,
      'oracleSymbols': len(pending_symbols),
      'error': True,
    }

  return {
    'attempted': True,
    'symbols': len(symbols),
    'updated': updated,
    'aliasUpdated': alias_updated,
    'trendSnapshotUpdated': trend_snapshot_updated,
    'oracleSymbols': len(pending_symbols),
  }


def _compute_base_rows(timeframe: str, latest_only: bool, *, view: str = 'strong') -> Dict[str, Any]:
  started = time.perf_counter()
  months = analysis_lookback_months(timeframe)
  raw = fetch_ohlc_series_from_oracle(months=months, cutoff_anchor='latest')
  series_by_symbol = aggregate_ohlc_series_by_timeframe(raw, timeframe)
  rows: List[Dict[str, Any]] = []
  skipped: Dict[str, int] = {}
  latest_dates = [
    candle.get('date')
    for candles in series_by_symbol.values()
    for candle in candles[-1:]
    if isinstance(candle.get('date'), datetime)
  ]
  latest_trading_date = max(latest_dates) if latest_dates else None

  for symbol, candles in series_by_symbol.items():
    if len(candles) < 35:
      skipped['insufficient_candles'] = skipped.get('insufficient_candles', 0) + 1
      continue
    closes = [float(item.get('close')) for item in candles if item.get('close') is not None]
    if len(closes) < 35:
      skipped['missing_close'] = skipped.get('missing_close', 0) + 1
      continue
    def period_return(periods: int) -> Optional[float]:
      if len(closes) <= periods:
        return None
      base = closes[-(periods + 1)]
      if not base:
        return None
      return ((closes[-1] / base) - 1.0) * 100.0

    latest = candles[-1]
    price = closes[-1]
    atr = calculate_atr(candles)
    pivots = detect_swing_pivots(candles, min_atr_multiple=0.75)
    sr = calculate_support_resistance(candles, pivots)
    trend = classify_trend_structure(candles, pivots)
    volume_ratio = calculate_volume_ratio(candles)
    ema_score, ema_label, ema_values = _ema_alignment_score(closes)
    indicator_snapshot = _technical_indicator_snapshot(candles, closes, atr)
    trend_direction = _derive_trend_direction(
      trend=trend,
      close=price,
      ema20=ema_values.get('ema20'),
      ema50=ema_values.get('ema50'),
      ema100=ema_values.get('ema100'),
    )
    trendline = _analyze_trendline(candles, pivots, atr)
    include_full_analytics = view != 'trendline'
    breakout = _analyze_breakout(candles, sr.get('nearestResistance'), volume_ratio, ema_values) if include_full_analytics else {
      'status': 'No Breakout',
      'score': 0.0,
      'flags': [],
    }
    breakout_window_flags = _breakout_window_flags(candles)
    pattern = _analyze_chart_pattern(candles, pivots, breakout) if include_full_analytics else {'patternName': '-', 'score': 0.0}
    latest_high = trend.get('latestHigh') or {}
    latest_low = trend.get('latestLow') or {}
    latest_high_price = latest_high.get('price') if isinstance(latest_high, dict) else None
    latest_low_price = latest_low.get('price') if isinstance(latest_low, dict) else None
    candle_high = latest.get('high')
    candle_low = latest.get('low')
    close_position_pct = None
    if isinstance(candle_high, (int, float)) and isinstance(candle_low, (int, float)) and candle_high > candle_low:
      close_position_pct = ((price - float(candle_low)) / (float(candle_high) - float(candle_low))) * 100.0
    breakout_flags = breakout.get('flags') or []
    breakout_type = breakout_flags[0] if breakout_flags else breakout.get('status')
    trendline_type = 'No Clean Trendline'
    if trendline.get('status') in ('Strong Support Trendline', 'Near Trendline Support', 'Trendline Break Risk', 'Trendline Broken'):
      trendline_type = 'Bullish Support Trendline'
    elif trendline.get('slope') is not None and float(trendline.get('slope') or 0.0) < 0:
      trendline_type = 'Bearish Resistance Trendline'
    pattern_name = pattern.get('patternName') or '-'
    pattern_status = 'Confirmed' if pattern_name != '-' and breakout.get('status') not in ('No Breakout', None, '-') else ('Detected' if pattern_name != '-' else '-')
    risk = classify_risk_level(
      price=price,
      nearest_support=sr.get('nearestSupport'),
      nearest_resistance=sr.get('nearestResistance'),
      atr=atr,
      ema20=ema_values.get('ema20'),
    )
    mtf_score = _multi_timeframe_score(candles, timeframe) if include_full_analytics else 0.0
    volume_score = 35.0
    if include_full_analytics and volume_ratio is not None:
      if volume_ratio >= 2.0:
        volume_score = 100.0
      elif volume_ratio >= 1.5:
        volume_score = 85.0
      elif volume_ratio >= 1.2:
        volume_score = 62.0
      else:
        volume_score = 42.0
    final_score = float(trendline.get('score') or 0.0) if view == 'trendline' else (
      0.20 * float(trend.get('score') or 0.0) +
      0.15 * ema_score +
      0.15 * float(trendline.get('score') or 0.0) +
      0.15 * float(breakout.get('score') or 0.0) +
      0.10 * float(pattern.get('score') or 0.0) +
      0.10 * volume_score +
      0.10 * mtf_score +
      0.05 * float(risk.get('riskScore') or 0.0)
    )
    row = {
      'symbol': symbol,
      'price': _safe_round(price),
      'priceSort': price,
      'ltcDate': _fmt_date(latest.get('date')),
      'ltcDateSort': latest.get('date').timestamp() if isinstance(latest.get('date'), datetime) else None,
      'td': len(candles),
      'timeframe': timeframe,
      # Shared EOD momentum horizons used by Sector Rotation V3. Keeping these
      # on the cached producer avoids any per-symbol route/database work.
      'return21': _safe_round(period_return(21)),
      'return63': _safe_round(period_return(63)),
      'return126': _safe_round(period_return(126)),
      'techScore': _safe_round(final_score),
      'techScoreSort': final_score,
      'score': _safe_round(final_score),
      'scoreSort': final_score,
      'SCORE': _safe_round(final_score),
      'techStatus': _score_band(final_score),
      'trendStructure': trend.get('status'),
      'trendDirection': trend_direction,
      'trend_direction': trend_direction,
      'Trend_Direction': trend_direction,
      'TREND_DIRECTION': trend_direction,
      'trendStructureScore': _safe_round(trend.get('score')),
      'priceActionLabels': trend.get('labels') or [],
      'lastSwingHigh': _safe_round(latest_high_price),
      'lastSwingLow': _safe_round(latest_low_price),
      'hhHlStatus': ', '.join(trend.get('labels') or []) or trend.get('status'),
      'support': _safe_round(sr.get('nearestSupport')),
      'resistance': _safe_round(sr.get('nearestResistance')),
      'priceActionScore': _safe_round(trend.get('score')),
      'emaAlignment': ema_label,
      'emaAlignmentScore': _safe_round(ema_score),
      'trendlineStatus': trendline.get('status'),
      'trendlineType': trendline_type,
      'trendlineScore': _safe_round(trendline.get('score')),
      'slope': _safe_round(trendline.get('slope'), 4),
      'touchCount': trendline.get('touchCount'),
      'trendlineSlope': _safe_round(trendline.get('slope'), 4),
      'trendlineTouchCount': trendline.get('touchCount'),
      'trendlineDistancePct': _safe_round(trendline.get('distancePct')),
      'distanceFromTrendlinePct': _safe_round(trendline.get('distancePct')),
      'patternName': pattern_name,
      'patternStatus': pattern_status,
      'confidenceScore': _safe_round(pattern.get('score')),
      'chartPatternScore': _safe_round(pattern.get('score')),
      'breakoutStatus': breakout.get('status') or 'No Breakout',
      'breakoutType': breakout_type,
      'breakoutLevel': _safe_round(sr.get('nearestResistance')),
      'breakoutScore': _safe_round(breakout.get('score')),
      'breakoutFlags': breakout_flags,
      'closePositionPct': _safe_round(close_position_pct),
      'volumeConfirmation': 'Confirmed' if volume_ratio is not None and volume_ratio >= 1.5 else 'Normal',
      'volumeRatio': _safe_round(volume_ratio),
      'volumeRatioSort': volume_ratio,
      'volumeConfirmationScore': _safe_round(volume_score),
      'multiTimeframeScore': _safe_round(mtf_score),
      'deliveryScore': None,
      'delivery_score': None,
      'DELIVERY_SCORE': None,
      'deliveryScoreSort': None,
      'deliveryLtcDate': None,
      'delivery_ltc_date': None,
      'riskLevel': risk.get('riskLevel'),
      'riskQualityScore': _safe_round(risk.get('riskScore')),
      'nearestSupport': _safe_round(sr.get('nearestSupport')),
      'SUPPORT': _safe_round(sr.get('nearestSupport')),
      'nearestResistance': _safe_round(sr.get('nearestResistance')),
      'RESISTANCE': _safe_round(sr.get('nearestResistance')),
      'invalidationLevel': _safe_round(risk.get('invalidationLevel')),
      'atr14': _safe_round(atr),
      'ema20': _safe_round(ema_values.get('ema20')),
      'EMA20': _safe_round(ema_values.get('ema20')),
      'ema50': _safe_round(ema_values.get('ema50')),
      'EMA50': _safe_round(ema_values.get('ema50')),
      'ema100': _safe_round(ema_values.get('ema100')),
      'EMA100': _safe_round(ema_values.get('ema100')),
      'ema200': _safe_round(ema_values.get('ema200')),
      'EMA200': _safe_round(ema_values.get('ema200')),
      'ath': None,
      'ATH': None,
      'athSort': None,
      'ATH_SORT': None,
      'athDate': None,
      'ath_date': None,
      'ATH_DATE': None,
      'athBreakout': False,
      'atlBreakout': False,
    }
    row.update(breakout_window_flags)
    row.update(indicator_snapshot)
    rows.append(row)

  symbols_for_ath = [
    _normalize_symbol_for_ath_lookup(row.get('symbol'))
    for row in rows
    if _normalize_symbol_for_ath_lookup(row.get('symbol'))
  ]
  if symbols_for_ath and get_all_time_high_for_symbols is not None:
    try:
      ath_records = get_all_time_high_for_symbols(
        symbols_for_ath,
        as_of_date=latest_trading_date,
        include_date=True,
        endpoint='/api/technicals/strong',
      )
      for row in rows:
        symbol_key = _normalize_symbol_for_ath_lookup(row.get('symbol'))
        record = ath_records.get(symbol_key) or ath_records.get(str(row.get('symbol') or '').strip().upper())
        if not record:
          continue
        ath = record.get('ath')
        row['ath'] = _safe_round(ath)
        row['ATH'] = _safe_round(ath)
        row['athSort'] = _safe_round(ath)
        row['ATH_SORT'] = _safe_round(ath)
        row['athDate'] = record.get('ath_date')
        row['ath_date'] = record.get('ath_date')
        row['ATH_DATE'] = record.get('ath_date')
        price_sort = row.get('priceSort')
        gap_pct = ((float(price_sort) - float(ath)) / float(ath) * 100.0) if ath and isinstance(price_sort, (int, float)) else None
        row['gap'] = f"{gap_pct:+.2f}%" if gap_pct is not None else '-'
        row['GAP'] = row['gap']
        row['gapSort'] = float(gap_pct) if gap_pct is not None else None
        row['GAP_SORT'] = row['gapSort']
        if ath and row.get('priceSort') and float(row['priceSort']) > float(ath):
          row['athBreakout'] = True
          row['breakoutStatus'] = 'ATH Breakout'
          row['breakoutType'] = 'ATH Breakout'
          row['breakoutLevel'] = _safe_round(ath)
          row['breakoutScore'] = max(float(row.get('breakoutScore') or 0.0), 96.0)
          row['techScoreSort'] = min(100.0, float(row['techScoreSort']) + 4.0)
          row['techScore'] = _safe_round(row['techScoreSort'])
          row['scoreSort'] = row['techScoreSort']
          row['score'] = row['techScore']
          row['SCORE'] = row['techScore']
          row['techStatus'] = _score_band(float(row['techScoreSort']))
    except Exception:
      _logger.exception('ATH enrichment failed for strong technicals')

  if view != 'trendline':
    _apply_delivery_scores(rows)

  rows.sort(key=lambda item: item.get('techScoreSort') or 0.0, reverse=True)
  for idx, row in enumerate(rows, 1):
    row['sNo'] = idx
  duration_ms = round((time.perf_counter() - started) * 1000, 2)
  return {
    'rows': rows,
    'meta': {
      'sourceTable': _SOURCE_TABLE,
      'timeframe': timeframe,
      'lookbackMonths': months,
      'latestOnly': latest_only,
      'latestTradingDate': latest_trading_date.strftime('%Y-%m-%d') if isinstance(latest_trading_date, datetime) else None,
      'symbolsProcessed': len(series_by_symbol),
      'rowsComputed': len(rows),
      'skippedSymbols': skipped,
      'calculationDurationMs': duration_ms,
      'generatedAt': datetime.utcnow().isoformat() + 'Z',
    },
  }


def _compute_breakout_rows(timeframe: str, latest_only: bool) -> Dict[str, Any]:
  started = time.perf_counter()
  months = analysis_lookback_months(timeframe)
  raw_started = time.perf_counter()
  if timeframe == 'daily' and fetch_recent_ohlc_series_from_oracle is not None:
    raw = fetch_recent_ohlc_series_from_oracle(trading_days=280)  # type: ignore[misc]
    source_window = 'recent_280_trading_days'
  else:
    raw = fetch_ohlc_series_from_oracle(months=months, cutoff_anchor='latest')
    source_window = f'{months}_months'
  raw_duration_ms = round((time.perf_counter() - raw_started) * 1000, 2)
  series_by_symbol = aggregate_ohlc_series_by_timeframe(raw, timeframe)
  rows: List[Dict[str, Any]] = []
  skipped: Dict[str, int] = {}
  latest_dates = [
    candle.get('date')
    for candles in series_by_symbol.values()
    for candle in candles[-1:]
    if isinstance(candle.get('date'), datetime)
  ]
  latest_trading_date = max(latest_dates) if latest_dates else None

  compute_started = time.perf_counter()
  for symbol, candles in series_by_symbol.items():
    if len(candles) < 35:
      skipped['insufficient_candles'] = skipped.get('insufficient_candles', 0) + 1
      continue
    closes = [float(item.get('close')) for item in candles if item.get('close') is not None]
    if len(closes) < 35:
      skipped['missing_close'] = skipped.get('missing_close', 0) + 1
      continue
    latest = candles[-1]
    price = closes[-1]
    atr = calculate_atr(candles)
    prior = candles[:-1]
    recent_support_window = prior[-35:] if len(prior) >= 35 else prior
    recent_resistance_window = prior[-35:] if len(prior) >= 35 else prior
    support_values = [float(item.get('low')) for item in recent_support_window if item.get('low') is not None]
    resistance_values = [float(item.get('high')) for item in recent_resistance_window if item.get('high') is not None]
    nearest_support = min(support_values) if support_values else None
    nearest_resistance = max(resistance_values) if resistance_values else None
    volume_ratio = calculate_volume_ratio(candles)
    ema_score, ema_label, ema_values = _ema_alignment_score(closes)
    indicator_snapshot = _breakout_indicator_snapshot(closes, atr)
    trend = {'status': ema_label, 'score': ema_score, 'labels': []}
    trend_direction = _derive_trend_direction(
      trend=trend,
      close=price,
      ema20=ema_values.get('ema20'),
      ema50=ema_values.get('ema50'),
      ema100=ema_values.get('ema100'),
    )
    breakout = _analyze_breakout(candles, nearest_resistance, volume_ratio, ema_values)
    breakout_window_flags = _breakout_window_flags(candles)
    latest_high_price = max(resistance_values) if resistance_values else None
    latest_low_price = min(support_values) if support_values else None
    candle_high = latest.get('high')
    candle_low = latest.get('low')
    close_position_pct = None
    if isinstance(candle_high, (int, float)) and isinstance(candle_low, (int, float)) and candle_high > candle_low:
      close_position_pct = ((price - float(candle_low)) / (float(candle_high) - float(candle_low))) * 100.0
    breakout_flags = breakout.get('flags') or []
    breakout_type = breakout_flags[0] if breakout_flags else breakout.get('status')
    risk = classify_risk_level(
      price=price,
      nearest_support=nearest_support,
      nearest_resistance=nearest_resistance,
      atr=atr,
      ema20=ema_values.get('ema20'),
    )
    breakout_score = float(breakout.get('score') or 0.0)
    row = {
      'symbol': symbol,
      'price': _safe_round(price),
      'priceSort': price,
      'ltcDate': _fmt_date(latest.get('date')),
      'ltcDateSort': latest.get('date').timestamp() if isinstance(latest.get('date'), datetime) else None,
      'td': len(candles),
      'timeframe': timeframe,
      'techScore': _safe_round(breakout_score),
      'techScoreSort': breakout_score,
      'score': _safe_round(breakout_score),
      'scoreSort': breakout_score,
      'SCORE': _safe_round(breakout_score),
      'techStatus': _score_band(breakout_score),
      'trendStructure': trend.get('status'),
      'trendDirection': trend_direction,
      'trend_direction': trend_direction,
      'Trend_Direction': trend_direction,
      'TREND_DIRECTION': trend_direction,
      'trendStructureScore': _safe_round(trend.get('score')),
      'priceActionLabels': trend.get('labels') or [],
      'lastSwingHigh': _safe_round(latest_high_price),
      'lastSwingLow': _safe_round(latest_low_price),
      'hhHlStatus': ', '.join(trend.get('labels') or []) or trend.get('status'),
      'support': _safe_round(nearest_support),
      'resistance': _safe_round(nearest_resistance),
      'priceActionScore': _safe_round(trend.get('score')),
      'emaAlignment': ema_label,
      'emaAlignmentScore': _safe_round(ema_score),
      'trendlineStatus': 'No Clean Trendline',
      'trendlineType': 'No Clean Trendline',
      'trendlineScore': 0.0,
      'slope': None,
      'touchCount': 0,
      'trendlineSlope': None,
      'trendlineTouchCount': 0,
      'trendlineDistancePct': None,
      'distanceFromTrendlinePct': None,
      'patternName': '-',
      'patternStatus': '-',
      'confidenceScore': 0.0,
      'chartPatternScore': 0.0,
      'breakoutStatus': breakout.get('status') or 'No Breakout',
      'breakoutType': breakout_type,
      'breakoutLevel': _safe_round(nearest_resistance),
      'breakoutScore': _safe_round(breakout_score),
      'breakoutFlags': breakout_flags,
      'closePositionPct': _safe_round(close_position_pct),
      'volumeConfirmation': 'Confirmed' if volume_ratio is not None and volume_ratio >= 1.5 else 'Normal',
      'volumeRatio': _safe_round(volume_ratio),
      'volumeRatioSort': volume_ratio,
      'volumeConfirmationScore': None,
      'multiTimeframeScore': None,
      'deliveryScore': None,
      'delivery_score': None,
      'DELIVERY_SCORE': None,
      'deliveryScoreSort': None,
      'deliveryLtcDate': None,
      'delivery_ltc_date': None,
      'riskLevel': risk.get('riskLevel'),
      'riskQualityScore': _safe_round(risk.get('riskScore')),
      'nearestSupport': _safe_round(nearest_support),
      'SUPPORT': _safe_round(nearest_support),
      'nearestResistance': _safe_round(nearest_resistance),
      'RESISTANCE': _safe_round(nearest_resistance),
      'invalidationLevel': _safe_round(risk.get('invalidationLevel')),
      'atr14': _safe_round(atr),
      'ema20': _safe_round(ema_values.get('ema20')),
      'EMA20': _safe_round(ema_values.get('ema20')),
      'ema50': _safe_round(ema_values.get('ema50')),
      'EMA50': _safe_round(ema_values.get('ema50')),
      'ema100': _safe_round(ema_values.get('ema100')),
      'EMA100': _safe_round(ema_values.get('ema100')),
      'ema200': _safe_round(ema_values.get('ema200')),
      'EMA200': _safe_round(ema_values.get('ema200')),
      'ath': None,
      'ATH': None,
      'athSort': None,
      'ATH_SORT': None,
      'athDate': None,
      'ath_date': None,
      'ATH_DATE': None,
      'athBreakout': False,
      'atlBreakout': False,
    }
    row.update(breakout_window_flags)
    row.update(indicator_snapshot)
    rows.append(row)
  compute_duration_ms = round((time.perf_counter() - compute_started) * 1000, 2)

  ath_started = time.perf_counter()
  ath_records = _load_trend_ath_gap_map(timeframe)
  updated = 0
  for row in rows:
    symbol_key = _normalize_symbol_for_ath_lookup(row.get('symbol'))
    record = ath_records.get(symbol_key) if symbol_key else None
    if not record:
      continue
    if _apply_ath_gap_record(row, record):
      updated += 1
    ath = row.get('athSort') if row.get('athSort') is not None else row.get('ath')
    if ath and row.get('priceSort') and float(row['priceSort']) > float(ath):
      row['athBreakout'] = True
      row['breakoutStatus'] = 'ATH Breakout'
      row['breakoutType'] = 'ATH Breakout'
      row['breakoutLevel'] = _safe_round(ath)
      row['breakoutScore'] = max(float(row.get('breakoutScore') or 0.0), 96.0)
      row['techScoreSort'] = min(100.0, float(row['techScoreSort']) + 4.0)
      row['techScore'] = _safe_round(row['techScoreSort'])
      row['scoreSort'] = row['techScoreSort']
      row['score'] = row['techScore']
      row['SCORE'] = row['techScore']
      row['techStatus'] = _score_band(float(row['techScoreSort']))
  ath_stats: Dict[str, Any] = {
    'attempted': bool(ath_records),
    'symbols': len(ath_records),
    'updated': updated,
    'source': 'snapshot_trend',
  }
  ath_duration_ms = round((time.perf_counter() - ath_started) * 1000, 2)

  rows.sort(key=lambda item: item.get('breakoutScore') or 0.0, reverse=True)
  for idx, row in enumerate(rows, 1):
    row['sNo'] = idx
  duration_ms = round((time.perf_counter() - started) * 1000, 2)
  return {
    'rows': rows,
    'meta': {
      'sourceTable': _SOURCE_TABLE,
      'timeframe': timeframe,
      'lookbackMonths': months,
      'sourceWindow': source_window,
      'latestOnly': latest_only,
      'latestTradingDate': latest_trading_date.strftime('%Y-%m-%d') if isinstance(latest_trading_date, datetime) else None,
      'symbolsProcessed': len(series_by_symbol),
      'rowsComputed': len(rows),
      'skippedSymbols': skipped,
      'calculationDurationMs': duration_ms,
      'rawLoadDurationMs': raw_duration_ms,
      'rowComputeDurationMs': compute_duration_ms,
      'athDurationMs': ath_duration_ms,
      'athStats': ath_stats,
      'computeProfile': 'breakout',
      'generatedAt': datetime.utcnow().isoformat() + 'Z',
    },
  }


def _delivery_lookup_key(value: Any) -> str:
  if normalize_delivery_symbol is not None:
    return normalize_delivery_symbol(value)  # type: ignore[misc]
  return str(value or '').strip().upper()


def _apply_delivery_scores(rows: List[Dict[str, Any]]) -> None:
  if not rows or fetch_latest_delivery_scores_for_symbols is None:
    return
  try:
    score_map = fetch_latest_delivery_scores_for_symbols(row.get('symbol') for row in rows)  # type: ignore[misc]
  except Exception:
    _logger.exception('Delivery score enrichment failed for strong technicals')
    return

  for row in rows:
    key = _delivery_lookup_key(row.get('symbol'))
    score_record = score_map.get(key) if key else None
    if not score_record:
      continue
    score = score_record.get('delivery_score')
    row['deliveryScore'] = score
    row['delivery_score'] = score
    row['DELIVERY_SCORE'] = score
    row['deliveryScoreSort'] = _numeric_value(score)
    row['deliveryStatus'] = score_record.get('delivery_status')
    row['delivery_status'] = score_record.get('delivery_status')
    row['deliveryLtcDate'] = score_record.get('ltc_date')
    row['delivery_ltc_date'] = score_record.get('ltc_date')


def _normalize_manual_sr_symbol(value: Any) -> str:
  token = str(value or '').strip().upper()
  for prefix in ('NSE:', 'BSE:'):
    if token.startswith(prefix):
      token = token[len(prefix):].strip()
      break
  for suffix in (':EQ', '-EQ', '.NS'):
    if token.endswith(suffix):
      token = token[:-len(suffix)].strip()
      break
  return token


def _fetch_manual_sr_level_map_for_symbols(symbols: List[str]) -> Dict[str, Dict[str, Any]]:
  from services.prudvi_strategy_service import _fetch_manual_sr_level_map  # type: ignore

  return _fetch_manual_sr_level_map(symbols)


def _manual_sr_text(record: Optional[Dict[str, Any]]) -> str:
  if not record:
    return '-'
  level_texts = record.get('levelTexts')
  if not isinstance(level_texts, list):
    return '-'
  values = [str(value or '').strip() for value in level_texts if str(value or '').strip()]
  return ', '.join(values) if values else '-'


def _apply_price_action_manual_sr_levels(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
  for row in rows:
    row['sr_levels'] = '-'
    row['SR_LEVELS'] = '-'
    row['srLevels'] = '-'
    row['supportResistance'] = '-'

  symbols = sorted({
    _normalize_manual_sr_symbol(row.get('symbol'))
    for row in rows
    if _normalize_manual_sr_symbol(row.get('symbol'))
  })
  if not symbols:
    return {'attempted': False, 'symbols': 0, 'updated': 0}

  try:
    manual_map = _fetch_manual_sr_level_map_for_symbols(symbols)
  except Exception:
    _logger.exception('Price action manual SR enrichment failed')
    return {'attempted': True, 'symbols': len(symbols), 'updated': 0, 'error': True}

  updated = 0
  for row in rows:
    symbol_key = _normalize_manual_sr_symbol(row.get('symbol'))
    text = _manual_sr_text(manual_map.get(symbol_key))
    row['sr_levels'] = text
    row['SR_LEVELS'] = text
    row['srLevels'] = text
    row['supportResistance'] = text
    if text != '-':
      updated += 1
  return {
    'attempted': True,
    'symbols': len(symbols),
    'updated': updated,
    'source': 'PRICE_ACTION_SR_LEVELS_MANUALLY',
  }


def _summary(rows: List[Dict[str, Any]]) -> Dict[str, int]:
  def _has_text(row: Dict[str, Any], key: str, token: str) -> bool:
    return token.lower() in str(row.get(key) or '').lower()

  def _labels_have(row: Dict[str, Any], token: str) -> bool:
    labels = row.get('priceActionLabels') or []
    if isinstance(labels, list):
      return any(token.lower() in str(label or '').lower() for label in labels)
    return token.lower() in str(labels or '').lower()

  def _near_support(row: Dict[str, Any]) -> bool:
    price = row.get('priceSort') or row.get('price')
    support = row.get('nearestSupport') or row.get('support')
    if not isinstance(price, (int, float)) or not isinstance(support, (int, float)) or price <= 0:
      return False
    return ((price - support) / price * 100.0) <= 3.0

  return {
    'totalSymbols': len(rows),
    'strongUptrend': sum(1 for row in rows if row.get('trendStructure') == 'Strong Uptrend'),
    'hhHlStructure': sum(1 for row in rows if _labels_have(row, 'Higher High') and _labels_have(row, 'Higher Low')),
    'accumulation': sum(1 for row in rows if row.get('trendStructure') == 'Accumulation'),
    'rangeBound': sum(1 for row in rows if row.get('trendStructure') == 'Range'),
    'downtrend': sum(1 for row in rows if row.get('trendStructure') == 'Downtrend'),
    'nearSupport': sum(1 for row in rows if _near_support(row)),
    'weakStructure': sum(1 for row in rows if row.get('techStatus') in ('Weak / Range Bound', 'Avoid') or row.get('trendStructure') in ('Downtrend', 'Range')),
    'strongSupportTrendline': sum(1 for row in rows if row.get('trendlineStatus') == 'Strong Support Trendline'),
    'nearTrendlineSupport': sum(1 for row in rows if row.get('trendlineStatus') == 'Near Trendline Support'),
    'trendlineBreakRisk': sum(1 for row in rows if row.get('trendlineStatus') == 'Trendline Break Risk'),
    'trendlineBroken': sum(1 for row in rows if row.get('trendlineStatus') == 'Trendline Broken'),
    'positiveSlope': sum(1 for row in rows if isinstance(row.get('trendlineSlope'), (int, float)) and row.get('trendlineSlope') > 0),
    'touch3Trendlines': sum(1 for row in rows if isinstance(row.get('trendlineTouchCount'), (int, float)) and row.get('trendlineTouchCount') >= 3),
    'noCleanTrendline': sum(1 for row in rows if row.get('trendlineStatus') == 'No Clean Trendline'),
    'confirmedBreakouts': sum(1 for row in rows if row.get('breakoutStatus') == 'Volume Confirmed Breakout'),
    'retestSuccess': sum(1 for row in rows if _has_text(row, 'breakoutStatus', 'Retest Success')),
    'nearBreakout': sum(1 for row in rows if _has_text(row, 'breakoutStatus', 'Near Breakout')),
    'week52Breakouts': sum(1 for row in rows if '52-Week High Breakout' in (row.get('breakoutFlags') or [])),
    'athBreakouts': sum(1 for row in rows if row.get('athBreakout') or row.get('breakoutStatus') == 'ATH Breakout'),
    'failedBreakouts': sum(1 for row in rows if row.get('breakoutStatus') == 'Failed Breakout'),
    'bullishPatterns': sum(1 for row in rows if row.get('patternName') not in (None, '', '-')),
    'ascendingTriangle': sum(1 for row in rows if row.get('patternName') == 'Ascending Triangle'),
    'rectangleBox': sum(1 for row in rows if row.get('patternName') == 'Rectangle / Box Consolidation'),
    'bullishFlag': sum(1 for row in rows if row.get('patternName') == 'Bullish Flag'),
    'uptrendChannel': sum(1 for row in rows if row.get('patternName') == 'Uptrend Channel'),
    'fallingWedge': sum(1 for row in rows if row.get('patternName') == 'Falling Wedge Breakout'),
    'breakoutPatterns': sum(1 for row in rows if row.get('patternName') not in (None, '', '-') and row.get('breakoutStatus') not in ('No Breakout', None, '-')),
    'strongTechnicals': sum(1 for row in rows if row.get('techStatus') == 'Strong Technicals'),
    'trendlineSupport': sum(1 for row in rows if row.get('trendlineStatus') in ('Strong Support Trendline', 'Near Trendline Support')),
    'volumeConfirmed': sum(1 for row in rows if row.get('breakoutStatus') == 'Volume Confirmed Breakout'),
    'highRiskAvoid': sum(1 for row in rows if row.get('riskLevel') in ('High', 'Avoid') or row.get('techStatus') == 'Avoid'),
    'totalStrongTechnicalStocks': sum(1 for row in rows if (row.get('techScoreSort') or 0) >= 70),
    'veryStrongTechnicals': sum(1 for row in rows if row.get('techStatus') == 'Very Strong Technicals'),
    'freshBreakouts': sum(1 for row in rows if row.get('breakoutStatus') not in ('No Breakout', None, '-')),
    'trendlineSupportStocks': sum(1 for row in rows if row.get('trendlineStatus') in ('Strong Support Trendline', 'Near Trendline Support')),
    'bullishChartPatterns': sum(1 for row in rows if row.get('patternName') not in (None, '', '-')),
    'nearAth52wHigh': sum(1 for row in rows if row.get('athBreakout') or '52-Week High Breakout' in (row.get('breakoutFlags') or [])),
    'volumeConfirmedBreakouts': sum(1 for row in rows if row.get('breakoutStatus') == 'Volume Confirmed Breakout'),
    'weakFailedBreakouts': sum(1 for row in rows if row.get('techStatus') in ('Weak / Range Bound', 'Avoid') or row.get('breakoutStatus') == 'Failed Breakout'),
    'weeklyBO': sum(1 for row in rows if _row_has_breakout_flag(row, 'weeklyBO')),
    'monthlyBO': sum(1 for row in rows if _row_has_breakout_flag(row, 'monthlyBO')),
    'threeMonthBO': sum(1 for row in rows if _row_has_breakout_flag(row, 'threeMonthBO')),
    'sixMonthBO': sum(1 for row in rows if _row_has_breakout_flag(row, 'sixMonthBO')),
    'nineMonthBO': sum(1 for row in rows if _row_has_breakout_flag(row, 'nineMonthBO')),
    'week52Low': sum(1 for row in rows if _row_has_breakout_flag(row, 'week52Low')),
    'week52High': sum(1 for row in rows if _row_has_breakout_flag(row, 'week52High')),
    'twoYearBO': sum(1 for row in rows if _row_has_breakout_flag(row, 'twoYearBO')),
    'threeYearBO': sum(1 for row in rows if _row_has_breakout_flag(row, 'threeYearBO')),
    'fourYearBO': sum(1 for row in rows if _row_has_breakout_flag(row, 'fourYearBO')),
    'fiveYearBO': sum(1 for row in rows if _row_has_breakout_flag(row, 'fiveYearBO')),
    'tenYearBO': sum(1 for row in rows if _row_has_breakout_flag(row, 'tenYearBO')),
    'ath': sum(1 for row in rows if _row_has_breakout_flag(row, 'athBreakout')),
    'atl': sum(1 for row in rows if _row_has_breakout_flag(row, 'atlBreakout')),
  }


def _matches(value: Any, expected: Any) -> bool:
  token = str(expected or '').strip().lower()
  if not token or token in {'all', 'any'}:
    return True
  return str(value or '').strip().lower() == token


def _score_field_for_view(view: str) -> str:
  if view == 'price_action':
    return 'priceActionScore'
  if view == 'trendline':
    return 'trendlineScore'
  if view == 'breakout':
    return 'breakoutScore'
  if view == 'chart_patterns':
    return 'chartPatternScore'
  return 'techScoreSort'


def _numeric_value(value: Any) -> float:
  try:
    parsed = float(value)
  except (TypeError, ValueError):
    return 0.0
  return parsed if isfinite(parsed) else 0.0


def _filter_rows(rows: List[Dict[str, Any]], params: Dict[str, Any], view: str) -> List[Dict[str, Any]]:
  symbol = str(params.get('symbol') or '').strip().upper()
  min_score = params.get('min_score')
  status = params.get('status')
  pattern = params.get('pattern')
  breakout_status = params.get('breakout_status')
  breakout_flag = str(params.get('breakout_flag') or '').strip().lower()
  trendline_status = params.get('trendline_status')
  risk_level = params.get('risk_level')
  score_field = _score_field_for_view(view)
  filtered: List[Dict[str, Any]] = []
  for row in rows:
    if symbol and symbol not in str(row.get('symbol') or '').upper():
      continue
    if min_score is not None and _numeric_value(row.get(score_field)) < float(min_score):
      continue
    if status and not _matches(row.get('techStatus'), status):
      continue
    if pattern and not _matches(row.get('patternName'), pattern):
      continue
    if breakout_status and not _matches(row.get('breakoutStatus'), breakout_status):
      continue
    if breakout_flag:
      flag_key = _BREAKOUT_FLAG_ALIASES.get(breakout_flag)
      if not flag_key or not _row_has_breakout_flag(row, flag_key):
        continue
    if trendline_status and not _matches(row.get('trendlineStatus'), trendline_status):
      continue
    if risk_level and not _matches(row.get('riskLevel'), risk_level):
      continue
    if view == 'breakout' and row.get('breakoutStatus') in ('No Breakout', None, '-'):
      continue
    if view == 'chart_patterns' and row.get('patternName') in (None, '', '-'):
      continue
    filtered.append(row)
  return filtered


def _sort_rows(rows: List[Dict[str, Any]], sort_by: str, sort_dir: str) -> List[Dict[str, Any]]:
  reverse = str(sort_dir or 'desc').lower() != 'asc'
  key_map = {
    'score': 'techScoreSort',
    'tech_score': 'techScoreSort',
    'price': 'priceSort',
    'ath': 'athSort',
    'gap': 'gapSort',
    'symbol': 'symbol',
    'index': 'INDEX',
    'mcap': 'mcapSort',
    'mcap_rank': 'mcapRankSort',
    'mcaprank': 'mcapRankSort',
    'mcapRank': 'mcapRankSort',
    'volume_ratio': 'volumeRatioSort',
    'ltc_date': 'ltcDateSort',
    'delivery_score': 'deliveryScoreSort',
    'deliveryscore': 'deliveryScoreSort',
  }
  field = key_map.get(str(sort_by or '').strip().lower(), sort_by or 'techScoreSort')

  def _key(row: Dict[str, Any]) -> Any:
    value = row.get(field)
    if value is None:
      value = row.get(str(field).replace('Sort', ''))
    return (value is None, value)

  return sorted(rows, key=_key, reverse=reverse)


def _cache_key_for_view(view: str, timeframe: str, latest_only: bool, latest_trading_date_key: str = '') -> str:
  suffix = f':ltc:{latest_trading_date_key}' if latest_trading_date_key else ''
  if view == 'price_action':
    return f'price_action:v1:{timeframe}:latest:{1 if latest_only else 0}{suffix}'
  return f'{view}:v1:{timeframe}:latest:{1 if latest_only else 0}{suffix}'


def _supports_snapshot(view: str) -> bool:
  return view in {'breakout', 'price_action', 'trendline'}


def _snapshot_path(cache_key: str) -> str:
  safe_key = cache_key.replace(':', '_').replace('/', '_').replace('\\', '_')
  return str(_SNAPSHOT_DIR / f'{safe_key}.json')


def _compute_payload_for_view(view: str, timeframe: str, latest_only: bool) -> Dict[str, Any]:
  if view == 'price_action':
    return _compute_price_action_rows(timeframe, latest_only)
  if view == 'breakout':
    return _compute_breakout_rows(timeframe, latest_only)
  return _compute_base_rows(timeframe, latest_only, view=view)


def _save_payload_snapshot(cache_key: str, payload: Dict[str, Any]) -> None:
  try:
    save_json_snapshot(_snapshot_path(cache_key), payload)
  except Exception:
    _logger.exception('Failed to save strong technicals snapshot key=%s', cache_key)


def _load_payload_snapshot(cache_key: str) -> Optional[Dict[str, Any]]:
  snapshot = load_json_snapshot(_snapshot_path(cache_key))
  return snapshot if isinstance(snapshot, dict) and isinstance(snapshot.get('rows'), list) else None


def _snapshot_matches_latest_date(payload: Dict[str, Any], latest_trading_date_key: str) -> bool:
  if not latest_trading_date_key:
    return True
  meta = payload.get('meta') or {}
  snapshot_date = str(meta.get('latestTradingDate') or '').strip()
  return bool(snapshot_date) and snapshot_date == latest_trading_date_key[:10]


def _load_compatible_payload_snapshot(
  cache_key: str,
  *,
  view: str,
  timeframe: str,
  latest_only: bool,
  latest_trading_date_key: str,
) -> Optional[Dict[str, Any]]:
  snapshot = _load_payload_snapshot(cache_key)
  if snapshot is not None:
    return snapshot

  if not latest_trading_date_key:
    return None

  legacy_key = _cache_key_for_view(view, timeframe, latest_only)
  if legacy_key == cache_key:
    return None
  legacy_snapshot = _load_payload_snapshot(legacy_key)
  if legacy_snapshot is None or not _snapshot_matches_latest_date(legacy_snapshot, latest_trading_date_key):
    return None

  _save_payload_snapshot(cache_key, legacy_snapshot)
  return legacy_snapshot


def _compute_and_persist_payload(view: str, timeframe: str, latest_only: bool, cache_key: str) -> Dict[str, Any]:
  payload = _compute_payload_for_view(view, timeframe, latest_only)
  if _supports_snapshot(view):
    _save_payload_snapshot(cache_key, payload)
  return payload


def _schedule_payload_refresh(view: str, timeframe: str, latest_only: bool, cache_key: str) -> None:
  background_refresh(
    _cache,
    cache_key,
    lambda: _compute_and_persist_payload(view, timeframe, latest_only, cache_key),
  )


def _repair_ath_gap_fields(rows: List[Dict[str, Any]], *, endpoint: str) -> Dict[str, Any]:
  if not rows or get_all_time_high_for_symbols is None:
    return {'attempted': False, 'symbols': 0, 'updated': 0}

  pending_symbols = []
  for row in rows:
    ath = row.get('athSort', row.get('ath'))
    gap = row.get('gapSort', row.get('gap'))
    if ath is None or gap in (None, '', '-'):
      symbol = str(row.get('symbol') or '').strip()
      if symbol:
        pending_symbols.append(symbol)

  if not pending_symbols:
    return {'attempted': False, 'symbols': 0, 'updated': 0}

  updated = 0
  try:
    ath_records = get_all_time_high_for_symbols(
      pending_symbols,
      include_date=True,
      endpoint=endpoint,
    )
    for row in rows:
      symbol_key = _normalize_symbol_for_ath_lookup(row.get('symbol'))
      if not symbol_key:
        continue
      record = ath_records.get(symbol_key) or {}
      ath = _safe_round(record.get('ath'))
      price_sort = row.get('priceSort')
      price = _safe_round(price_sort if isinstance(price_sort, (int, float)) else row.get('price'))
      if ath is None:
        continue
      gap_pct = ((float(price) - float(ath)) / float(ath) * 100.0) if price is not None and ath else None
      row['ath'] = ath
      row['ATH'] = ath
      row['athSort'] = ath
      row['ATH_SORT'] = ath
      row['athDate'] = record.get('ath_date')
      row['ath_date'] = record.get('ath_date')
      row['ATH_DATE'] = record.get('ath_date')
      row['gap'] = f"{gap_pct:+.2f}%" if gap_pct is not None else '-'
      row['GAP'] = row['gap']
      row['gapSort'] = float(gap_pct) if gap_pct is not None else None
      row['GAP_SORT'] = row['gapSort']
      updated += 1
  except Exception:
    _logger.exception('ATH/GAP repair failed endpoint=%s', endpoint)
    return {'attempted': True, 'symbols': len(pending_symbols), 'updated': updated, 'error': True}

  return {'attempted': True, 'symbols': len(pending_symbols), 'updated': updated}


def _ensure_ath_gap_snapshot_payload(
  payload: Dict[str, Any],
  cache_key: str,
  *,
  endpoint: str,
  repair_fn,
) -> Optional[Dict[str, Any]]:
  rows = payload.get('rows')
  if not isinstance(rows, list):
    return None
  ath_stats = repair_fn(rows, endpoint=endpoint)
  if ath_stats.get('attempted'):
    meta = dict(payload.get('meta') or {})
    meta['athSource'] = 'NSE_NIFTY500_DAILY_RAW_DATA_DEV'
    meta['athStats'] = ath_stats
    payload['meta'] = meta
    payload['athSource'] = 'NSE_NIFTY500_DAILY_RAW_DATA_DEV'
    if int(ath_stats.get('updated') or 0) > 0:
      _cache.set(cache_key, payload)
      _save_payload_snapshot(cache_key, payload)
  return ath_stats


def fetch_strong_technicals_page(
  *,
  tf: str = 'daily',
  page: int = 1,
  page_size: int = 50,
  symbol: str = '',
  min_score: Optional[float] = None,
  status: str = '',
  pattern: str = '',
  breakout_status: str = '',
  breakout_flag: str = '',
  trendline_status: str = '',
  risk_level: str = '',
  latest_only: bool = True,
  sort_by: str = 'techScoreSort',
  sort_dir: str = 'desc',
  refresh: bool = False,
  view: str = 'strong',
) -> Dict[str, Any]:
  timeframe = normalize_timeframe(tf)
  latest_trading_date_key = ''
  try:
    latest_dt = fetch_latest_trade_date_from_oracle()
    latest_trading_date_key = latest_dt.isoformat() if latest_dt else ''
  except Exception:
    latest_trading_date_key = ''
  cache_key = _cache_key_for_view(view, timeframe, latest_only, latest_trading_date_key)
  started = time.perf_counter()
  cached = _cache.get(cache_key)
  snapshot = None
  cache_state = 'HIT' if cached is not None else 'MISS'
  refreshing = False

  if isinstance(cached, dict) and not refresh:
    payload = cached
  elif _supports_snapshot(view) and isinstance(cached, dict):
    payload = cached
    cache_state = 'STALE_HIT'
    refreshing = True
    _schedule_payload_refresh(view, timeframe, latest_only, cache_key)
  else:
    if _supports_snapshot(view):
      snapshot = _load_compatible_payload_snapshot(
        cache_key,
        view=view,
        timeframe=timeframe,
        latest_only=latest_only,
        latest_trading_date_key=latest_trading_date_key,
      )
    if _supports_snapshot(view) and isinstance(snapshot, dict):
      payload = snapshot
      _cache.set(cache_key, payload)
      cache_state = 'SNAPSHOT'
      refreshing = True
      _schedule_payload_refresh(view, timeframe, latest_only, cache_key)
    else:
      payload = _compute_and_persist_payload(view, timeframe, latest_only, cache_key)
      _cache.set(cache_key, payload)
      cache_state = 'MISS'

  ath_stats = None
  if view == 'price_action':
    ath_stats = _ensure_ath_gap_snapshot_payload(
      payload,
      cache_key,
      endpoint='/api/technicals/price-action',
      repair_fn=lambda rows, endpoint: _enrich_price_action_ath_gap(rows, timeframe=timeframe, endpoint=endpoint),
    )
  elif view == 'trendline':
    ath_stats = _ensure_ath_gap_snapshot_payload(
      payload,
      cache_key,
      endpoint='/api/technicals/trendline',
      repair_fn=_repair_ath_gap_fields,
    )
  rows = nse_mcap_svc.enrich_rows_with_marketcap_index(payload.get('rows') or [])
  manual_sr_stats = _apply_price_action_manual_sr_levels(rows) if view == 'price_action' else None
  params = {
    'symbol': symbol,
    'min_score': min_score,
    'status': status,
    'pattern': pattern,
    'breakout_status': breakout_status,
    'breakout_flag': breakout_flag,
    'trendline_status': trendline_status,
    'risk_level': risk_level,
  }
  filtered = _filter_rows(list(rows), params, view)
  sorted_rows = _sort_rows(filtered, sort_by, sort_dir)
  page = max(1, int(page or 1))
  page_size = max(1, min(500, int(page_size or 50)))
  total = len(sorted_rows)
  start = (page - 1) * page_size
  end = start + page_size
  page_rows = [dict(row, sNo=index) for index, row in enumerate(sorted_rows[start:end], start + 1)]
  total_pages = (total + page_size - 1) // page_size if page_size else 1
  duration_ms = round((time.perf_counter() - started) * 1000, 2)
  meta = dict(payload.get('meta') or {})
  meta.update({
    'cacheState': cache_state,
    'rowsReturned': len(page_rows),
    'totalRowsAfterFilter': total,
    'requestDurationMs': duration_ms,
    'view': view,
    'refreshing': refreshing,
  })
  if ath_stats is not None:
    meta['athSource'] = 'NSE_NIFTY500_DAILY_RAW_DATA_DEV'
    meta['athStats'] = ath_stats
  if manual_sr_stats is not None:
    meta['srLevelsSource'] = 'PRICE_ACTION_SR_LEVELS_MANUALLY'
    meta['srLevelsStats'] = manual_sr_stats
  _logger.info(
    'strong_technicals view=%s source_table=%s latest_trading_date=%s tf=%s page=%s page_size=%s sort=%s:%s symbol=%s min_score=%s pattern=%s breakout_status=%s trendline_status=%s risk_level=%s symbols_processed=%s rows_returned=%s total_filtered=%s cache=%s refreshing=%s calc_ms=%s request_ms=%s skipped=%s',
    view,
    meta.get('sourceTable'),
    meta.get('latestTradingDate'),
    timeframe,
    page,
    page_size,
    sort_by,
    sort_dir,
    symbol,
    min_score,
    pattern,
    breakout_status,
    trendline_status,
    risk_level,
    meta.get('symbolsProcessed'),
    len(page_rows),
    total,
    cache_state,
    refreshing,
    meta.get('calculationDurationMs'),
    duration_ms,
    meta.get('skippedSymbols'),
  )
  response = {
    'ok': True,
    'rows': page_rows,
    'count': len(page_rows),
    'total': total,
    'page': page,
    'page_size': page_size,
    'total_pages': total_pages,
    'summary': _summary(filtered),
    'meta': meta,
    'cached': cache_state in {'HIT', 'STALE_HIT', 'SNAPSHOT'},
    'refreshing': refreshing,
  }
  if view == 'price_action':
    response['athSource'] = 'NSE_NIFTY500_DAILY_RAW_DATA_DEV'
  return response


def fetch_strong_technicals_universe(
  *,
  required_fields: Sequence[str] = (),
) -> Dict[str, Any]:
  """Return one complete cached daily Strong Technicals universe.

  V3 publication uses this producer once and then projects the rows into
  sectors. If an older compatible snapshot predates newly additive shared
  fields, it is rebuilt here before publication rather than repaired through
  per-symbol calls.
  """

  timeframe = 'daily'
  latest_only = True
  latest_trading_date_key = ''
  try:
    latest_dt = fetch_latest_trade_date_from_oracle()
    latest_trading_date_key = latest_dt.isoformat() if latest_dt else ''
  except Exception:
    latest_trading_date_key = ''
  cache_key = _cache_key_for_view('strong', timeframe, latest_only, latest_trading_date_key)
  payload = _cache.get(cache_key)
  if not isinstance(payload, dict):
    payload = _load_compatible_payload_snapshot(
      cache_key,
      view='strong',
      timeframe=timeframe,
      latest_only=latest_only,
      latest_trading_date_key=latest_trading_date_key,
    )
  rows = payload.get('rows') if isinstance(payload, dict) else None
  needs_rebuild = (
    not isinstance(rows, list)
    or not rows
    or any(any(field not in row for field in required_fields) for row in rows if isinstance(row, dict))
  )
  if needs_rebuild:
    payload = _compute_and_persist_payload('strong', timeframe, latest_only, cache_key)
    _cache.set(cache_key, payload)
    rows = payload.get('rows') or []
  # The current market-cap batch can omit otherwise valid Sector Wise members.
  # Preserve current-date values where available, then use each remaining
  # symbol's latest persisted MCAP record so V3 publication does not turn its
  # INDEX/MCAP/MCAP_RANK cells into blanks.
  enriched_rows = nse_mcap_svc.enrich_rows_with_marketcap_index(
    rows or [],
    allow_stale_per_symbol=True,
  )
  return {
    'rows': [dict(row) for row in enriched_rows],
    'meta': dict(payload.get('meta') or {}),
  }
