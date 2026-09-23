from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

from db import fetch_ohlc_series_from_oracle

try:
    from services.ath_service import (
        compute_distance_from_ath_percent,
        get_all_time_high_for_symbols,
        warn_if_ath_below_current,
    )
except Exception:  # pragma: no cover
    from .ath_service import (  # type: ignore
        compute_distance_from_ath_percent,
        get_all_time_high_for_symbols,
        warn_if_ath_below_current,
    )
TIMEFRAMES = ('daily', 'weekly', 'monthly', 'yearly')
_logger = logging.getLogger(__name__)
RETURN_SCHEMA_VERSION = 3
TRADING_DAYS_PER_YEAR = 252
MIN_YEAR_RETURN_COLUMNS = 27
LEGACY_YEAR_FLAG_YEARS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 20, 25)
DAY_RETURN_WINDOWS = {
    'd5': 5,
    'd10': 10,
    'd15': 15,
    'd22': 22,
    'd44': 44,
    'd66': 66,
    'd88': 88,
    'd132': 132,
    'd198': 198,
}
BREAKOUT_CLOSE_FLAG_DEFINITIONS = (
    ('weeklyBO', 'Weekly_BO', 5, 'high'),
    ('monthlyBO', 'Monthly_BO', 22, 'high'),
    ('threeMonthBO', '3M_BO', 66, 'high'),
    ('sixMonthBO', '6M_BO', 132, 'high'),
    ('nineMonthBO', '9M_BO', 198, 'high'),
    ('week52Low', '52WL', 252, 'low'),
    ('week52High', '52WH', 252, 'high'),
    ('twoYearBO', '2Y_BO', 504, 'high'),
    ('threeYearBO', '3Y_BO', 756, 'high'),
    ('fourYearBO', '4Y_BO', 1008, 'high'),
    ('fiveYearBO', '5Y_BO', 1260, 'high'),
    ('tenYearBO', '10Y_BO', 2520, 'high'),
)


def ema(values: List[float], period: int) -> float | None:
    if not values:
        return None
    k = 2 / (period + 1)
    prev = values[0]
    for v in values[1:]:
        prev = v * k + prev * (1 - k)
    return float(prev)


def _fmt_ddmmyyyy(dt: datetime) -> str:
    try:
        return dt.strftime('%d-%m-%Y')
    except Exception:
        return ''


def _fmt_iso_to_ddmmyyyy(value: str | None) -> str:
    if not value:
        return ''
    text = str(value).strip()
    if not text:
        return ''
    token = text[:10]
    try:
        dt = datetime.strptime(token, '%Y-%m-%d')
        return dt.strftime('%d-%m-%Y')
    except Exception:
        return token


def _pct_change(latest: float, past: float) -> float | None:
    try:
        if past is None or past == 0 or latest is None:
            return None
        return (latest - past) / past * 100.0
    except Exception:
        return None


def _flag_bool(value: bool | None) -> str:
    if value is True:
        return 'Y'
    if value is False:
        return 'N'
    return '-'


def _safe_round(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 2)
    except Exception:
        return None


def _breakout_close_flags(closes: List[float]) -> Dict[str, Any]:
    if not closes:
        return {}
    close = float(closes[-1])
    prior = closes[:-1]
    result: Dict[str, Any] = {}
    for key, label, window, direction in BREAKOUT_CLOSE_FLAG_DEFINITIONS:
        source = prior[-window:] if len(prior) >= window else []
        passed: bool | None = None
        level: float | None = None
        if len(source) >= window:
            level = max(source) if direction == 'high' else min(source)
            passed = close > level if direction == 'high' else close < level
        result[key] = passed is True
        result[label] = _flag_bool(passed)
        result[f'{key}Level'] = _safe_round(level)
    atl_level = min(prior) if prior else None
    atl_passed = atl_level is not None and close < atl_level
    result['atlBreakout'] = atl_passed
    result['ATL'] = _flag_bool(atl_passed if atl_level is not None else None)
    result['atlLevel'] = _safe_round(atl_level)
    return result


def _valid_close_count(series: List[Tuple[datetime, float]]) -> int:
    return sum(1 for _dt, value in series if value is not None)


def _year_return_years_for_series(series_by_symbol: Dict[str, List[Tuple[datetime, float]]]) -> Tuple[int, ...]:
    max_points = max((_valid_close_count(series) for series in series_by_symbol.values()), default=0)
    max_year_from_data = (max_points - 1) // TRADING_DAYS_PER_YEAR if max_points > 1 else 0
    max_year = max(MIN_YEAR_RETURN_COLUMNS, max_year_from_data)
    return tuple(range(1, max_year + 1))


def _build_return_windows(series_by_symbol: Dict[str, List[Tuple[datetime, float]]]) -> Dict[str, int]:
    windows: Dict[str, int] = dict(DAY_RETURN_WINDOWS)
    for year in _year_return_years_for_series(series_by_symbol):
        windows[f'y{year}'] = year * TRADING_DAYS_PER_YEAR
    return windows


def _build_legacy_flag_windows() -> Dict[str, int]:
    windows: Dict[str, int] = dict(DAY_RETURN_WINDOWS)
    for year in LEGACY_YEAR_FLAG_YEARS:
        windows[f'y{year}'] = year * TRADING_DAYS_PER_YEAR
    return windows


def _return_column_metadata(windows: Dict[str, int]) -> List[Dict[str, Any]]:
    columns: List[Dict[str, Any]] = []
    for key, days in windows.items():
        if key.startswith('d'):
            columns.append({'key': key, 'label': f'{days}D', 'days': days, 'kind': 'day'})
        elif key.startswith('y'):
            try:
                years = int(key[1:])
            except ValueError:
                continue
            columns.append({'key': key, 'label': f'{years}Y', 'days': days, 'years': years, 'kind': 'year'})
    return columns


def return_column_metadata_for_series(series_by_symbol: Dict[str, List[Tuple[datetime, float]]]) -> List[Dict[str, Any]]:
    return _return_column_metadata(_build_return_windows(series_by_symbol))


def _bucket_for(timeframe: str, dt: datetime) -> datetime:
    if timeframe == 'weekly':
        # Align to Monday (ISO week start) to mirror TRUNC(TRADING_DATE,'IW')
        start = dt.date() - timedelta(days=dt.weekday())
        return datetime(start.year, start.month, start.day)
    if timeframe == 'monthly':
        return datetime(dt.year, dt.month, 1)
    if timeframe == 'yearly':
        return datetime(dt.year, 1, 1)
    return dt


def _normalize_timeframe(timeframe: str) -> str:
    tf = (timeframe or 'daily').strip().lower()
    if tf not in TIMEFRAMES:
        raise ValueError('Invalid timeframe')
    return tf


def _group_by_timeframe(
    series_by_symbol: Dict[str, List[Tuple[datetime, float]]],
    timeframe: str,
) -> Dict[str, List[Tuple[datetime, float]]]:
    """Collapse daily closes into weekly/monthly/yearly buckets using last close per bucket."""
    if timeframe == 'daily':
        return series_by_symbol

    grouped: Dict[str, List[Tuple[datetime, float]]] = {}
    for symbol, entries in series_by_symbol.items():
        buckets: Dict[datetime, Tuple[datetime, float]] = {}
        for dt, close_val in entries:
            if not isinstance(dt, datetime) or close_val is None:
                continue
            bucket = _bucket_for(timeframe, dt)
            prev = buckets.get(bucket)
            # Keep the latest close in the bucket (by actual trading date)
            if prev is None or dt > prev[0]:
                buckets[bucket] = (dt, close_val)
        if not buckets:
            continue
        grouped[symbol] = [(bucket, close_val) for bucket, (_dt, close_val) in sorted(buckets.items(), key=lambda pair: pair[0])]
    return grouped


def fetch_series(
    timeframe: str = 'daily',
    *,
    months: int | None = None,
    force_refresh: bool = False,
) -> Dict[str, List[Tuple[datetime, float]]]:
    tf = _normalize_timeframe(timeframe)
    ohlc_series = fetch_ohlc_series_from_oracle(months=months)
    series: Dict[str, List[Tuple[datetime, float]]] = {}
    for symbol, candles in ohlc_series.items():
        entries: List[Tuple[datetime, float]] = []
        for candle in candles:
            dt = candle.get('date')
            close_val = candle.get('close')
            if dt is None or close_val is None:
                continue
            entries.append((dt, float(close_val)))
        if entries:
            series[symbol] = entries
    return _group_by_timeframe(series, tf)


def build_rows(series_by_symbol: Dict[str, List[Tuple[datetime, float]]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    symbols = [symbol for symbol in series_by_symbol.keys() if str(symbol or '').strip()]
    ath_records: Dict[str, Dict[str, Any]] = {}
    try:
        ath_records = get_all_time_high_for_symbols(
            symbols,
            include_date=True,
            endpoint='/api/trend',
        )
    except Exception as exc:
        _logger.exception('[ATH] Failed to resolve ATH map for trend rows: %s', exc)
        ath_records = {}

    ath_map: Dict[str, float | None] = {}
    current_price_map: Dict[str, float | None] = {}
    windows = _build_return_windows(series_by_symbol)
    flag_windows = _build_legacy_flag_windows()
    ema_periods = {20, 50, 100, 200}
    ema_periods.update(flag_windows.values())

    for symbol, series in series_by_symbol.items():
        if not series:
            continue
        series_sorted = sorted(series, key=lambda x: x[0])
        closes = [float(v) for (_d, v) in series_sorted if v is not None]
        dates = [d for (d, _v) in series_sorted]
        if not closes:
            continue
        breakout_flags = _breakout_close_flags(closes)
        symbol_key = str(symbol or '').strip().upper()
        price = float(closes[-1])
        ath_record = ath_records.get(symbol_key) or {}
        ath = ath_record.get('ath')
        ath_date_iso = ath_record.get('ath_date')
        distance_from_ath_percent = compute_distance_from_ath_percent(price, ath)
        gap_pct = None
        if ath not in (None, 0) and price is not None:
            gap_pct = ((price - ath) / ath) * 100.0
        last_date = next((d for d in reversed(dates) if isinstance(d, datetime)), None)
        first_date = next((d for d in dates if isinstance(d, datetime)), None)
        trading_days = len(closes)
        calendar_days = (last_date - first_date).days if isinstance(last_date, datetime) and isinstance(first_date, datetime) else None

        ath_map[symbol_key] = ath if isinstance(ath, (int, float)) else None
        current_price_map[symbol_key] = price

        ema_cache = {period: ema(closes, period) for period in ema_periods}
        e20 = ema_cache.get(20)
        e50 = ema_cache.get(50)
        e100 = ema_cache.get(100)
        e200 = ema_cache.get(200)

        def flag(period: int) -> str:
            value = ema_cache.get(period)
            if value is None:
                return '-'
            return 'Y' if price > value else 'N'

        pct_fields: Dict[str, Any] = {}
        for key, n in windows.items():
            if len(closes) > n:
                past = closes[-(n + 1)]
                pct = _pct_change(price, past)
            else:
                pct = None
            pct_fields[key + 'Sort'] = float(pct) if (pct is not None) else None
            pct_fields[key] = (f"{pct:.2f}%" if pct is not None else '-')

        row: Dict[str, Any] = {
            'symbol': symbol,
            'stock': symbol,
            'ath': ath,
            'athSort': ath,
            'ath_date': ath_date_iso,
            'athDate': _fmt_iso_to_ddmmyyyy(ath_date_iso),
            'price': price,
            'priceSort': price,
            'current_price': price,
            'distance_from_ath_percent': distance_from_ath_percent,
            'distanceFromAthPercent': distance_from_ath_percent,
            'gap': f"{gap_pct:+.2f}%" if gap_pct is not None else '-',
            'gapSort': float(gap_pct) if gap_pct is not None else None,
            'tradingDate': _fmt_ddmmyyyy(first_date) if first_date else '',
            'tradingDateSort': first_date.timestamp() if isinstance(first_date, datetime) else None,
            'firstTradeDate': _fmt_ddmmyyyy(first_date) if first_date else '',
            'firstTradeDateSort': first_date.timestamp() if isinstance(first_date, datetime) else None,
            'tradingDays': trading_days if trading_days else None,
            'tradingDaysSort': trading_days if trading_days else None,
            'calendarDays': calendar_days,
            'ltcDate': _fmt_ddmmyyyy(last_date) if last_date else '',
            'ltcDateSort': last_date.timestamp() if isinstance(last_date, datetime) else None,
            'ema20': _safe_round(e20),
            'ema50': _safe_round(e50),
            'ema100': _safe_round(e100),
            'ema200': _safe_round(e200),
            'ema20Flag': 'Y' if e20 is not None and price > e20 else 'N',
            'ema50Flag': 'Y' if e50 is not None and price > e50 else 'N',
            'ema100Flag': 'Y' if e100 is not None and price > e100 else 'N',
            'ema200Flag': 'Y' if e200 is not None and price > e200 else 'N',
            **{f'{key}Flag': flag(period) for key, period in flag_windows.items()},
            '_e20': e20, '_e50': e50, '_e100': e100, '_e200': e200,
        }
        if ath not in (None, 0) and price is not None:
            ath_breakout = price > float(ath)
            breakout_flags['athBreakout'] = ath_breakout
            breakout_flags['ATH_BREAKOUT'] = _flag_bool(ath_breakout)
        row.update(breakout_flags)
        row.update(pct_fields)
        rows.append(row)
    try:
        warn_if_ath_below_current(ath_map, current_price_map, endpoint='/api/trend')
    except Exception:
        _logger.exception('[ATH] Failed ATH/current-price validation for trend rows')
    return rows


def categorize(rows: List[Dict[str, Any]]):
    ema20_rows, ema50_rows, ema5020_rows, ema100_rows, ema200_rows, ema200100_rows, ema20010050_rows, ema2001005020_rows = [], [], [], [], [], [], [], []
    for r in rows:
        price = r['price']
        e20, e50, e100, e200 = r.get('_e20'), r.get('_e50'), r.get('_e100'), r.get('_e200')
        if e20 is not None and price > e20:
            ema20_rows.append(r)
        if e50 is not None and price > e50:
            ema50_rows.append(r)
            if e20 is not None and price > e20:
                ema5020_rows.append(r)
        if e100 is not None and price > e100:
            ema100_rows.append(r)
        if e200 is not None and price > e200:
            ema200_rows.append(r)
            if e100 is not None and price > e100:
                ema200100_rows.append(r)
                if e50 is not None and price > e50:
                    ema20010050_rows.append(r)
                    if e20 is not None and price > e20:
                        ema2001005020_rows.append(r)
    def strip(arr):
        out = []
        for i, item in enumerate(arr, 1):
            d = {k: v for k, v in item.items() if not k.startswith('_')}
            d['sNo'] = i
            out.append(d)
        return out
    return (
        strip(ema20_rows),
        strip(ema50_rows),
        strip(ema5020_rows),
        strip(ema100_rows),
        strip(ema200_rows),
        strip(ema200100_rows),
        strip(ema20010050_rows),
        strip(ema2001005020_rows),
    )
