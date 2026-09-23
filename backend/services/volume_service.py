from __future__ import annotations

from datetime import datetime
from statistics import fmean
from typing import Any, Dict, List, Tuple

from db import fetch_ohlc_series_from_oracle
from services.technical_utils import aggregate_ohlc_series_by_timeframe, indicator_lookback_months, normalize_timeframe

CUTOFF_MONTHS = 6


def _fmt_ddmmyyyy(dt: datetime | None) -> str:
  if not isinstance(dt, datetime):
    return ''
  try:
    return dt.strftime('%d-%m-%Y')
  except Exception:
    return ''


def _collect_close_series(raw: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Tuple[datetime, float]]]:
  series: Dict[str, List[Tuple[datetime, float]]] = {}
  for symbol, entries in raw.items():
    closes: List[Tuple[datetime, float]] = []
    for entry in entries:
      dt = entry.get('date')
      close_val = entry.get('close')
      if not isinstance(dt, datetime) or close_val is None:
        continue
      try:
        closes.append((dt, float(close_val)))
      except (TypeError, ValueError):
        continue
    if closes:
      closes.sort(key=lambda item: item[0])
      series[symbol] = closes
  return series


def _pct_change(latest: float, past: float) -> float | None:
  try:
    if past is None or past == 0 or latest is None:
      return None
    return (latest - past) / past * 100.0
  except Exception:
    return None


def _build_base_rows(series_by_symbol: Dict[str, List[Tuple[datetime, float]]]) -> Dict[str, Dict[str, Any]]:
  windows = {
    'd5': 5, 'd10': 10, 'd15': 15, 'd22': 22,
    'd44': 44, 'd66': 66, 'd88': 88, 'd132': 132, 'd198': 198,
    'y1': 252, 'y2': 504, 'y3': 756,
  }
  rows: Dict[str, Dict[str, Any]] = {}
  for symbol, series in series_by_symbol.items():
    if not symbol or not series:
      continue
    series_sorted = sorted(series, key=lambda item: item[0])
    closes = [float(value) for (_dt, value) in series_sorted if value is not None]
    if not closes:
      continue
    row: Dict[str, Any] = {
      'symbol': symbol,
      'price': closes[-1],
      'tradingDays': len(closes),
    }
    latest = closes[-1]
    for key, window in windows.items():
      if len(closes) > window:
        row[f'{key}Sort'] = _pct_change(latest, closes[-(window + 1)])
      else:
        row[f'{key}Sort'] = None
    rows[symbol] = row
  return rows


def compute_volume_rows(timeframe: str = 'daily') -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
  tf = normalize_timeframe(timeframe)
  months = indicator_lookback_months(tf, CUTOFF_MONTHS)
  raw_series = aggregate_ohlc_series_by_timeframe(fetch_ohlc_series_from_oracle(months=months), tf)
  close_series = _collect_close_series(raw_series)
  base_rows = _build_base_rows(close_series)
  market_dates = sorted({
    entry.get('date')
    for entries in raw_series.values()
    for entry in (entries or [])
    if isinstance(entry.get('date'), datetime)
  })
  latest_market_date = market_dates[-1] if market_dates else None
  prev_market_date = market_dates[-2] if len(market_dates) >= 2 else None

  rows: List[Dict[str, Any]] = []
  momentum_keys = [
    'd5Sort', 'd10Sort', 'd15Sort', 'd22Sort', 'd44Sort', 'd66Sort',
    'd88Sort', 'd132Sort', 'd198Sort', 'y1Sort', 'y2Sort', 'y3Sort'
  ]

  overall_first: datetime | None = None
  overall_last: datetime | None = None

  for symbol, entries in raw_series.items():
    base = base_rows.get(symbol) or {}
    filtered = []
    first_dt_all: datetime | None = None
    last_dt_all: datetime | None = None
    total_sessions = 0
    for entry in entries:
      dt = entry.get('date')
      vol = entry.get('volume')
      close_val = entry.get('close')
      if isinstance(dt, datetime):
        total_sessions += 1
        if first_dt_all is None or dt < first_dt_all:
          first_dt_all = dt
        if last_dt_all is None or dt > last_dt_all:
          last_dt_all = dt
        if overall_first is None or dt < overall_first:
          overall_first = dt
        if overall_last is None or dt > overall_last:
          overall_last = dt
      if not isinstance(dt, datetime) or vol is None or close_val is None:
        continue
      try:
        vol_num = float(vol)
        close_num = float(close_val)
      except (TypeError, ValueError):
        continue
      filtered.append({'date': dt, 'volume': vol_num, 'close': close_num})

    if not filtered:
      continue

    filtered.sort(key=lambda item: item['date'])
    volumes = [item['volume'] for item in filtered]
    if not volumes:
      continue

    latest = filtered[-1]
    if latest_market_date is not None and latest['date'] != latest_market_date:
      continue
    window = volumes[-20:] if len(volumes) >= 20 else volumes
    try:
      avg20 = fmean(window) if window else None
    except Exception:
      avg20 = None

    if avg20 is None or avg20 <= 0:
      continue

    ratio = latest['volume'] / avg20

    price = base.get('price')
    if price is None:
      price = latest['close']
    try:
      price_float = round(float(price), 2)
    except (TypeError, ValueError):
      price_float = None

    prev_close: float | None = None
    points: float | None = None
    percentage: float | None = None
    if prev_market_date is not None:
      prev_entry = next((item for item in filtered if item['date'] == prev_market_date), None)
      if prev_entry is not None:
        try:
          prev_close = float(prev_entry['close'])
        except (TypeError, ValueError):
          prev_close = None
    if prev_close is not None:
      try:
        latest_close = float(latest['close'])
        points = round(latest_close - prev_close, 2)
        if prev_close != 0:
          percentage = round((points / prev_close) * 100, 2)
      except (TypeError, ValueError):
        points = None
        percentage = None

    first_dt = first_dt_all or filtered[0]['date']
    last_dt = last_dt_all or filtered[-1]['date']
    first_date = _fmt_ddmmyyyy(first_dt)
    last_date = _fmt_ddmmyyyy(last_dt)
    first_date_sort = first_dt.timestamp()
    last_date_sort = last_dt.timestamp()

    trading_days = base.get('tradingDays')
    if not isinstance(trading_days, int):
      trading_days = total_sessions or len(filtered)
    if not isinstance(trading_days, int):
      trading_days = len(filtered)

    momentum_vals = [base.get(key) for key in momentum_keys if isinstance(base.get(key), (int, float))]
    avg_pct = fmean(momentum_vals) if momentum_vals else 0.0
    positive_share = 0.0
    if momentum_vals:
      positives = sum(1 for val in momentum_vals if val and val > 0)
      positive_share = positives / len(momentum_vals)

    score = ratio * (1 + positive_share * 0.5 + avg_pct / 100)

    row = {
      'symbol': symbol,
      'price': price_float,
      'priceSort': price_float,
      'tradingDate': first_date,
      'tradingDateSort': first_date_sort,
      'ltcDate': last_date,
      'ltcDateSort': last_date_sort,
      'td': trading_days,
      'tdSort': trading_days,
      'volume': latest['volume'],
      'volumeSort': latest['volume'],
      'volumeAvg20': round(avg20, 2),
      'volumeAvg20Sort': avg20,
      'volumeRatio': round(ratio, 2),
      'volumeRatioSort': ratio,
      'volumeScore': round(score, 2),
      'volumeScoreSort': score,
      'previousClose': round(prev_close, 2) if isinstance(prev_close, (int, float)) else None,
      'points': points,
      'change': points,
      'percentage': percentage,
      'percentChange': percentage,
    }
    rows.append(row)

  rows.sort(key=lambda item: item.get('volumeScoreSort') or 0, reverse=True)
  meta = {
    'cutoffMonths': months,
    'baseCutoffMonths': CUTOFF_MONTHS,
    'timeframe': tf,
    'startDate': overall_first.strftime('%Y-%m-%d') if isinstance(overall_first, datetime) else None,
    'endDate': overall_last.strftime('%Y-%m-%d') if isinstance(overall_last, datetime) else None,
    'latestTradingDate': latest_market_date.strftime('%Y-%m-%d') if isinstance(latest_market_date, datetime) else None,
    'previousTradingDate': prev_market_date.strftime('%Y-%m-%d') if isinstance(prev_market_date, datetime) else None,
  }
  return rows, meta
