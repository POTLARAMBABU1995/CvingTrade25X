from __future__ import annotations

from collections import OrderedDict, deque
from datetime import datetime
import math
from statistics import mean
from typing import Any, Dict, List, Optional, Tuple

try:
    from services.technical_score_engine import enrich_row_with_master_score_fields
except Exception:  # pragma: no cover
    try:
        from .services.technical_score_engine import enrich_row_with_master_score_fields  # type: ignore
    except Exception:  # pragma: no cover
        enrich_row_with_master_score_fields = None  # type: ignore

SR_TOLERANCE_OPTIONS = [0.05, 0.10, 0.15, 0.20]
INTERNAL_TOLERANCE_MIN = 0.05
INTERNAL_TOLERANCE_MAX = 0.15
MIN_LEVELS_PER_SIDE = 2
MAX_LEVELS_PER_SIDE = 5
DEFAULT_LOOKBACK_DAYS = 504
MIN_LOOKBACK_DAYS = 66
MAX_LOOKBACK_DAYS = 504
ATR_PERIOD = 14
EMA_PERIOD = 20
ADX_PERIOD = 14
MANUAL_LEVEL_EQUIVALENCE_PCT = 0.005
MAX_MERGED_LEVELS_PER_SIDE = 10
PRICE_ACTION_FILTER_OPTIONS = {
    'all',
    'neutral',
    'range',
    'breakout',
    'breakdown',
    'bullish_rejection',
    'bearish_rejection',
    'bullish_engulfing',
    'bearish_engulfing',
    'inside_bar',
}
MONTH_WINDOWS = {
    '1M': 21,
    '2M': 42,
    '3M': 63,
    '4M': 84,
    '5M': 105,
    '6M': 126,
}
TREND_ANALYSIS_CONFIG = {
    'swing_window': 3,
    'consolidation_tolerance_pct': 0.03,
    'consolidation_max_days': 35,
    'rolling_lookback_days': 252,
}
MASTER_SCORE_ENABLED = True

Candle = Dict[str, Any]


def normalize_symbol(symbol: str) -> str:
    if symbol is None:
        return ''
    sym = str(symbol).strip()
    if not sym:
        return ''
    sym_upper = sym.upper()
    if sym_upper.startswith('NSE:'):
        sym = sym[4:]
        sym_upper = sym.upper()
    if sym_upper.endswith('-EQ'):
        sym = sym[:-3]
    return sym.strip().upper()


def _apply_master_score_fields(row: Dict[str, Any], sr_context: Dict[str, Any]) -> Dict[str, Any]:
    if not MASTER_SCORE_ENABLED or enrich_row_with_master_score_fields is None:
        return row
    try:
        return enrich_row_with_master_score_fields(
            row,
            sr_context=sr_context,
            replace_existing=False,
        )
    except Exception:
        return row


def _prepare_series(ohlc_series: Dict[str, List[Candle]]) -> Tuple[Dict[str, List[Candle]], Dict[str, List[str]]]:
    merged: Dict[str, List[Candle]] = {}
    aliases: Dict[str, set[str]] = {}
    for raw_symbol, candles in ohlc_series.items():
        normalized = normalize_symbol(raw_symbol)
        if not normalized:
            continue
        merged.setdefault(normalized, []).extend(candles)
        aliases.setdefault(normalized, set()).add(str(raw_symbol))
    alias_lists = {key: sorted(values) for key, values in aliases.items()}
    return merged, alias_lists


def _format_date(dt: Optional[datetime], default: str = '') -> str:
    if isinstance(dt, datetime):
        return dt.strftime('%d-%m-%Y')
    return default


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if isinstance(dt, datetime):
        return dt.isoformat()
    return None


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    token = str(value).strip()
    if not token:
        return None
    if token.endswith('Z'):
        token = token[:-1] + '+00:00'
    try:
        parsed = datetime.fromisoformat(token)
    except ValueError:
        return None
    return parsed.replace(tzinfo=None) if parsed.tzinfo is not None else parsed


def _clamp_int(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


def _safe_round(value: Optional[float], digits: int = 2) -> Optional[float]:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(numeric) or math.isinf(numeric):
        return None
    return round(numeric, digits)


def _close_values(candles: List[Candle]) -> List[float]:
    closes: List[float] = []
    for candle in candles:
        close = candle.get('close')
        if close is None:
            continue
        try:
            closes.append(float(close))
        except (TypeError, ValueError):
            continue
    return closes


def _resolve_requested_lookback_days(lookback_days: Any) -> Optional[int]:
    if lookback_days is None:
        return None
    if isinstance(lookback_days, str) and lookback_days.strip().lower() in {'auto', 'max', 'all', 'full'}:
        return None
    try:
        numeric = int(lookback_days)
    except (TypeError, ValueError):
        return None
    return _clamp_int(numeric, MIN_LOOKBACK_DAYS, MAX_LOOKBACK_DAYS)


def _is_max_lookback(lookback_days: Any) -> bool:
    return isinstance(lookback_days, str) and lookback_days.strip().lower() in {'max', 'all', 'full'}


def _estimate_dynamic_lookback(candles: List[Candle], base_lookback: int = DEFAULT_LOOKBACK_DAYS) -> int:
    available = len(candles)
    if available <= 0:
        return 0
    base = _clamp_int(base_lookback, MIN_LOOKBACK_DAYS, MAX_LOOKBACK_DAYS)
    closes = _close_values(candles)
    if len(closes) < 20:
        return min(available, base)
    returns: List[float] = []
    for idx in range(1, len(closes)):
        prev = closes[idx - 1]
        curr = closes[idx]
        if not prev:
            continue
        returns.append(abs((curr - prev) / prev))
    if not returns:
        return min(available, base)
    sampled = returns[-63:] if len(returns) >= 63 else returns
    avg_move = mean(sampled)
    scale = 0.8 + min(0.55, avg_move * 12.0)
    lookback = int(round(base * max(0.8, min(1.35, scale))))
    return min(available, _clamp_int(lookback, MIN_LOOKBACK_DAYS, MAX_LOOKBACK_DAYS))


def _slice_candles_for_lookback(candles: List[Candle], lookback_days: Any) -> Tuple[List[Candle], int]:
    if not candles:
        return [], 0
    if _is_max_lookback(lookback_days):
        return candles, len(candles)
    requested = _resolve_requested_lookback_days(lookback_days)
    effective = requested if requested is not None else _estimate_dynamic_lookback(candles)
    effective = max(1, min(len(candles), effective))
    return candles[-effective:], effective


def _average_true_range(candles: List[Candle], period: int = ATR_PERIOD) -> Optional[float]:
    prepared = [c for c in candles if c.get('high') is not None and c.get('low') is not None and c.get('close') is not None]
    if len(prepared) < max(2, period):
        return None
    trs: List[float] = []
    prev_close: Optional[float] = None
    for candle in prepared:
        high = float(candle.get('high'))
        low = float(candle.get('low'))
        close = float(candle.get('close'))
        if prev_close is None:
            tr = high - low
        else:
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
        prev_close = close
    if len(trs) < period:
        return mean(trs) if trs else None
    return mean(trs[-period:])


def _ema(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    smoothing = 2.0 / (period + 1.0)
    ema_values: List[float] = []
    current = values[0]
    for value in values:
        current = (value - current) * smoothing + current
        ema_values.append(current)
    return ema_values


def _ema_slope_pct(values: List[float], period: int = EMA_PERIOD, window: int = 10) -> Optional[float]:
    ema_values = _ema(values, period)
    if len(ema_values) < max(2, window):
        return None
    segment = ema_values[-window:]
    start = segment[0]
    end = segment[-1]
    if not start:
        return None
    return ((end - start) / abs(start)) * 100.0


def _compute_adx(candles: List[Candle], period: int = ADX_PERIOD) -> Optional[float]:
    prepared = [c for c in candles if c.get('high') is not None and c.get('low') is not None and c.get('close') is not None]
    if len(prepared) < (period * 2):
        return None
    trs: List[float] = []
    plus_dm: List[float] = []
    minus_dm: List[float] = []
    for idx in range(1, len(prepared)):
        prev = prepared[idx - 1]
        curr = prepared[idx]
        prev_high = float(prev.get('high'))
        prev_low = float(prev.get('low'))
        prev_close = float(prev.get('close'))
        high = float(curr.get('high'))
        low = float(curr.get('low'))
        up_move = high - prev_high
        down_move = prev_low - low
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    if len(trs) < period:
        return None
    tr_sum = sum(trs[:period])
    plus_sum = sum(plus_dm[:period])
    minus_sum = sum(minus_dm[:period])
    dx_values: List[float] = []
    plus_di = (plus_sum / tr_sum) * 100.0 if tr_sum else 0.0
    minus_di = (minus_sum / tr_sum) * 100.0 if tr_sum else 0.0
    denom = plus_di + minus_di
    dx_values.append((abs(plus_di - minus_di) / denom) * 100.0 if denom else 0.0)
    for idx in range(period, len(trs)):
        tr_sum = tr_sum - (tr_sum / period) + trs[idx]
        plus_sum = plus_sum - (plus_sum / period) + plus_dm[idx]
        minus_sum = minus_sum - (minus_sum / period) + minus_dm[idx]
        plus_di = (plus_sum / tr_sum) * 100.0 if tr_sum else 0.0
        minus_di = (minus_sum / tr_sum) * 100.0 if tr_sum else 0.0
        denom = plus_di + minus_di
        dx_values.append((abs(plus_di - minus_di) / denom) * 100.0 if denom else 0.0)
    if len(dx_values) < period:
        return mean(dx_values) if dx_values else None
    adx = mean(dx_values[:period])
    for dx in dx_values[period:]:
        adx = ((adx * (period - 1)) + dx) / period
    return round(adx, 2)


def _volume_ratio(candles: List[Candle], window: int = 20) -> Optional[float]:
    volumes: List[float] = []
    for candle in candles:
        volume = candle.get('volume')
        if volume is None:
            continue
        try:
            volumes.append(float(volume))
        except (TypeError, ValueError):
            continue
    if len(volumes) < 2:
        return None
    latest = volumes[-1]
    history = volumes[-(window + 1):-1] if len(volumes) > 1 else []
    if not history:
        return None
    baseline = mean(history)
    if baseline <= 0:
        return None
    return latest / baseline


def _hh_hl_state(candles: List[Candle], window: int = 20) -> Dict[str, bool]:
    prepared = [c for c in candles if c.get('high') is not None and c.get('low') is not None]
    if len(prepared) < window * 2:
        return {
            'higherHighHigherLow': False,
            'lowerHighLowerLow': False,
        }
    previous = prepared[-window * 2:-window]
    recent = prepared[-window:]
    prev_high = max(float(c.get('high')) for c in previous)
    prev_low = min(float(c.get('low')) for c in previous)
    recent_high = max(float(c.get('high')) for c in recent)
    recent_low = min(float(c.get('low')) for c in recent)
    return {
        'higherHighHigherLow': recent_high > prev_high and recent_low > prev_low,
        'lowerHighLowerLow': recent_high < prev_high and recent_low < prev_low,
    }


def _event_summary(from_idx: Optional[int], to_idx: Optional[int], dates: List[datetime]) -> Optional[Dict[str, Any]]:
    if from_idx is None or to_idx is None or from_idx >= to_idx:
        return None
    start = dates[from_idx] if from_idx < len(dates) else None
    end = dates[to_idx] if to_idx < len(dates) else None
    trading_days = to_idx - from_idx
    calendar_days = None
    months = None
    if isinstance(start, datetime) and isinstance(end, datetime):
        calendar_days = (end - start).days
        months = round(calendar_days / 30.0, 2) if calendar_days is not None else None
    return {
        'fromDate': _iso(start),
        'toDate': _iso(end),
        'tradingDays': trading_days,
        'calendarDays': calendar_days,
        'months': months,
    }


def _months_between(start: Optional[datetime], end: Optional[datetime]) -> Optional[float]:
    if not (isinstance(start, datetime) and isinstance(end, datetime)):
        return None
    months = (end.year - start.year) * 12 + (end.month - start.month)
    months += (end.day - start.day) / 30.0
    return round(months, 2)


def _serialize_pivot(pivot: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not pivot:
        return None
    return {
        'type': pivot.get('type'),
        'price': pivot.get('price'),
        'index': pivot.get('idx'),
        'date': _iso(pivot.get('date')),
    }


def _prepare_trend_candles(candles: List[Candle]) -> List[Dict[str, Any]]:
    prepared: List[Dict[str, Any]] = []
    for idx, candle in enumerate(candles):
        date = candle.get('date')
        high = candle.get('high')
        low = candle.get('low')
        close = candle.get('close')
        if not isinstance(date, datetime):
            continue
        if high is None or low is None or close is None:
            continue
        try:
            prepared.append({
                'idx': idx,
                'date': date,
                'high': float(high),
                'low': float(low),
                'close': float(close),
            })
        except (TypeError, ValueError):
            continue
    return prepared


def _detect_swings(candles: List[Dict[str, Any]], window: int) -> List[Dict[str, Any]]:
    swings: List[Dict[str, Any]] = []
    length = len(candles)
    if length < window * 2 + 1:
        return swings
    for idx in range(window, length - window):
        center = candles[idx]
        is_high = True
        is_low = True
        for offset in range(1, window + 1):
            left = candles[idx - offset]
            right = candles[idx + offset]
            if left['high'] >= center['high'] or right['high'] >= center['high']:
                is_high = False
            if left['low'] <= center['low'] or right['low'] <= center['low']:
                is_low = False
            if not is_high and not is_low:
                break
        if is_high:
            swings.append({'type': 'swingHigh', 'price': center['high'], 'idx': center['idx'], 'date': center['date']})
        elif is_low:
            swings.append({'type': 'swingLow', 'price': center['low'], 'idx': center['idx'], 'date': center['date']})
    return swings


def _compute_extremes(candles: List[Dict[str, Any]], rolling_days: int) -> Dict[str, Dict[str, Any]]:
    ath = {'price': float('-inf'), 'idx': None, 'date': None}
    atl = {'price': float('inf'), 'idx': None, 'date': None}
    high_deque: deque = deque()
    low_deque: deque = deque()
    high52 = {'price': None, 'idx': None, 'date': None}
    low52 = {'price': None, 'idx': None, 'date': None}
    for candle in candles:
        idx = candle['idx']
        high = candle['high']
        low = candle['low']
        date = candle['date']
        if high > ath['price']:
            ath = {'price': high, 'idx': idx, 'date': date}
        if low < atl['price']:
            atl = {'price': low, 'idx': idx, 'date': date}
        while high_deque and high_deque[0]['idx'] <= idx - rolling_days:
            high_deque.popleft()
        while high_deque and high_deque[-1]['price'] <= high:
            high_deque.pop()
        high_deque.append({'price': high, 'idx': idx, 'date': date})
        high52 = dict(high_deque[0])
        while low_deque and low_deque[0]['idx'] <= idx - rolling_days:
            low_deque.popleft()
        while low_deque and low_deque[-1]['price'] >= low:
            low_deque.pop()
        low_deque.append({'price': low, 'idx': idx, 'date': date})
        low52 = dict(low_deque[0])
    return {'ath': ath, 'atl': atl, 'high52w': high52, 'low52w': low52}


def _build_pivot_moves(swings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    moves: List[Dict[str, Any]] = []
    for idx in range(1, len(swings)):
        source = swings[idx - 1]
        target = swings[idx]
        trading_days = target['idx'] - source['idx']
        months = _months_between(source.get('date'), target.get('date'))
        change_pct = None
        if source.get('price'):
            change_pct = round(((target['price'] - source['price']) / source['price']) * 100, 2)
        moves.append({
            'from': source,
            'to': target,
            'tradingDays': trading_days,
            'months': months,
            'changePct': change_pct,
        })
    return moves


def _detect_break_events(swings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    last_high: Optional[Dict[str, Any]] = None
    last_low: Optional[Dict[str, Any]] = None
    for swing in swings:
        if swing['type'] == 'swingHigh':
            if last_high and swing['price'] > last_high['price']:
                events.append({
                    'kind': 'UPTREND',
                    'ref': last_high,
                    'pivot': swing,
                    'tradingDays': swing['idx'] - last_high['idx'],
                    'months': _months_between(last_high.get('date'), swing.get('date')),
                })
            last_high = swing
        elif swing['type'] == 'swingLow':
            if last_low and swing['price'] < last_low['price']:
                events.append({
                    'kind': 'DOWNTREND',
                    'ref': last_low,
                    'pivot': swing,
                    'tradingDays': swing['idx'] - last_low['idx'],
                    'months': _months_between(last_low.get('date'), swing.get('date')),
                })
            last_low = swing
    events.sort(key=lambda evt: evt['pivot']['idx'])
    return events


def _detect_consolidations(
    swings: List[Dict[str, Any]],
    tolerance_pct: float,
    max_days: int,
) -> List[Dict[str, Any]]:
    zones: List[Dict[str, Any]] = []
    last_high: Optional[Dict[str, Any]] = None
    last_low: Optional[Dict[str, Any]] = None
    for swing in swings:
        if swing['type'] == 'swingHigh':
            last_high = swing
        else:
            last_low = swing
        if not last_high or not last_low:
            continue
        high_idx = last_high['idx']
        low_idx = last_low['idx']
        start_idx = min(high_idx, low_idx)
        end_idx = max(high_idx, low_idx)
        trading_days = end_idx - start_idx
        if trading_days <= 0 or trading_days > max_days:
            continue
        high_price = last_high['price']
        low_price = last_low['price']
        if low_price <= 0 or high_price <= 0:
            continue
        mid = (high_price + low_price) / 2.0
        if mid <= 0:
            continue
        range_ratio = abs(high_price - low_price) / mid
        if range_ratio > tolerance_pct * 2:
            continue
        start_date = last_high['date'] if high_idx <= low_idx else last_low['date']
        end_date = last_low['date'] if low_idx >= high_idx else last_high['date']
        zones.append({
            'start_idx': start_idx,
            'end_idx': end_idx,
            'start_date': start_date,
            'end_date': end_date,
            'trading_days': trading_days,
            'months': _months_between(start_date, end_date),
            'high_level': high_price,
            'low_level': low_price,
        })
    return zones


def _summarize_trend_events(events: List[Dict[str, Any]]) -> Dict[str, int]:
    up_to_down = 0
    down_to_up = 0
    total = 0
    last_kind: Optional[str] = None
    for event in events:
        kind = event['kind']
        if last_kind and kind != last_kind:
            total += 1
            if last_kind == 'UPTREND' and kind == 'DOWNTREND':
                up_to_down += 1
            elif last_kind == 'DOWNTREND' and kind == 'UPTREND':
                down_to_up += 1
        last_kind = kind
    return {'total': total, 'upToDown': up_to_down, 'downToUp': down_to_up}


def _resolve_trend_direction(events: List[Dict[str, Any]], zones: List[Dict[str, Any]]) -> str:
    latest_idx = -1
    direction = 'Consolidation'
    if zones:
        latest_zone = max(zones, key=lambda zone: zone['end_idx'])
        latest_idx = latest_zone['end_idx']
        direction = 'Consolidation'
    if events:
        latest_event = max(events, key=lambda evt: evt['pivot']['idx'])
        if latest_event['pivot']['idx'] >= latest_idx:
            direction = 'Uptrend' if latest_event['kind'] == 'UPTREND' else 'Downtrend'
    return direction


def _serialize_pivot_move(move: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'from': _serialize_pivot(move.get('from')),
        'to': _serialize_pivot(move.get('to')),
        'tradingDays': move.get('tradingDays'),
        'months': move.get('months'),
        'changePct': move.get('changePct'),
    }


def _serialize_break_event(event: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'kind': event.get('kind'),
        'ref': _serialize_pivot(event.get('ref')),
        'pivot': _serialize_pivot(event.get('pivot')),
        'tradingDays': event.get('tradingDays'),
        'months': event.get('months'),
    }


def _serialize_consolidation(zone: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'kind': 'CONSOLIDATION',
        'start': _iso(zone.get('start_date')),
        'end': _iso(zone.get('end_date')),
        'tradingDays': zone.get('trading_days'),
        'months': zone.get('months'),
        'highLevel': zone.get('high_level'),
        'lowLevel': zone.get('low_level'),
    }


def _default_trend_analysis() -> Dict[str, Any]:
    return {
        'direction': 'Consolidation',
        'transitions': {'total': 0, 'upToDown': 0, 'downToUp': 0},
        'reversalCount': 0,
        'meta': {
            'swingCount': 0,
            'pivotMoveCount': 0,
            'breakEventCount': 0,
            'consolidationCount': 0,
            'latestBreak': None,
            'latestConsolidation': None,
            'extremes': {},
        },
    }


def _analyze_structural_trend(candles: List[Candle]) -> Dict[str, Any]:
    prepared = _prepare_trend_candles(candles)
    if len(prepared) < 5:
        return _default_trend_analysis()
    config = TREND_ANALYSIS_CONFIG
    swings = _detect_swings(prepared, config['swing_window'])
    extremes = _compute_extremes(prepared, config['rolling_lookback_days'])
    pivot_moves = _build_pivot_moves(swings)
    events = _detect_break_events(swings)
    zones = _detect_consolidations(swings, config['consolidation_tolerance_pct'], config['consolidation_max_days'])
    transitions = _summarize_trend_events(events)
    direction = _resolve_trend_direction(events, zones)
    meta = {
        'swingCount': len(swings),
        'pivotMoveCount': len(pivot_moves),
        'breakEventCount': len(events),
        'consolidationCount': len(zones),
        'latestBreak': _serialize_break_event(events[-1]) if events else None,
        'latestConsolidation': _serialize_consolidation(zones[-1]) if zones else None,
        'extremes': {
            'ath': _serialize_pivot(extremes.get('ath')),
            'atl': _serialize_pivot(extremes.get('atl')),
            'high52w': _serialize_pivot(extremes.get('high52w')),
            'low52w': _serialize_pivot(extremes.get('low52w')),
        },
    }
    return {
        'direction': direction,
        'transitions': transitions,
        'reversalCount': transitions.get('total', 0),
        'meta': meta,
    }


def _count_touches(price: float, candles: List[Candle], tolerance_pct: float, kind: str) -> Tuple[int, int, List[datetime]]:
    tolerance = price * tolerance_pct
    touches = 0
    breaches = 0
    touch_dates: List[datetime] = []
    for candle in candles:
        low = candle.get('low')
        high = candle.get('high')
        date = candle.get('date') if isinstance(candle.get('date'), datetime) else None
        if kind == 'support':
            if low is None:
                continue
            if abs(float(low) - price) <= tolerance:
                touches += 1
                if date:
                    touch_dates.append(date)
            if low < price - tolerance:
                breaches += 1
        else:
            if high is None:
                continue
            if abs(float(high) - price) <= tolerance:
                touches += 1
                if date:
                    touch_dates.append(date)
            if high > price + tolerance:
                breaches += 1
    touch_dates.sort()
    return touches, breaches, touch_dates


def _find_extreme_candidates(candles: List[Candle], key: str) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    if len(candles) < 3:
        return candidates
    for idx in range(1, len(candles) - 1):
        center = candles[idx].get(key)
        prev_val = candles[idx - 1].get(key)
        next_val = candles[idx + 1].get(key)
        if center is None or prev_val is None or next_val is None:
            continue
        c = float(center)
        prev = float(prev_val)
        nxt = float(next_val)
        if key == 'low':
            if c <= prev and c <= nxt:
                candidates.append({'price': c, 'index': idx})
        else:
            if c >= prev and c >= nxt:
                candidates.append({'price': c, 'index': idx})
    return candidates


def _cluster_candidates(candidates: List[Dict[str, Any]], tolerance_pct: float) -> List[Dict[str, Any]]:
    clusters: List[Dict[str, Any]] = []
    for cand in candidates:
        price = cand['price']
        assigned = False
        for cluster in clusters:
            ref = cluster['price']
            if ref == 0:
                continue
            if abs(price - ref) / ref <= tolerance_pct:
                cluster['members'].append(cand)
                cluster['price'] = sum(m['price'] for m in cluster['members']) / len(cluster['members'])
                assigned = True
                break
        if not assigned:
            clusters.append({'price': price, 'members': [cand]})
    return clusters


def _select_spaced_levels(levels: List[Dict[str, Any]], min_gap_pct: float, kind: str) -> List[Dict[str, Any]]:
    """
    Pick levels ensuring a minimum percentage gap between any selected levels.
    Levels are assumed pre-sorted by strength/priority.
    """
    selected: List[Dict[str, Any]] = []
    for lvl in levels:
        price = lvl.get('price')
        if price is None or price <= 0:
            continue
        too_close = False
        for chosen in selected:
            ref = chosen.get('price')
            if not ref or ref <= 0:
                continue
            gap = (ref - price) / ref if kind == 'support' else (price - ref) / ref
            if gap < min_gap_pct:
                too_close = True
                break
        if not too_close:
            selected.append(lvl)
        if len(selected) >= MAX_LEVELS_PER_SIDE:
            break
    return selected


def _anchor_price(candles: List[Candle], price: Optional[float], kind: str) -> Optional[float]:
    """
    Resolve a reference price used to filter candidate levels.
    Preference order:
      1) Explicit `price` argument (latest close supplied by caller)
      2) Most recent close in candle list
      3) Latest high/low depending on requested kind
    """
    if price is not None:
        try:
            return float(price)
        except (TypeError, ValueError):
            pass
    for candle in reversed(candles):
        close_val = candle.get('close')
        if close_val is None:
            continue
        try:
            return float(close_val)
        except (TypeError, ValueError):
            continue
    key = 'low' if kind == 'support' else 'high'
    for candle in reversed(candles):
        value = candle.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _fallback_levels(candles: List[Candle], price: Optional[float], kind: str) -> List[Dict[str, Any]]:
    """
    Provide deterministic fallback levels from raw highs/lows when swings are insufficient.
    Ensures we always have concrete numeric S/R levels.
    """
    anchor = _anchor_price(candles, price, kind)
    key = 'low' if kind == 'support' else 'high'
    values: List[float] = []
    for candle in candles:
        val = candle.get(key)
        if val is None:
            continue
        try:
            val_f = float(val)
        except (TypeError, ValueError):
            continue
        if anchor is not None:
            if kind == 'support' and val_f >= anchor:
                continue
            if kind == 'resistance' and val_f <= anchor:
                continue
        values.append(val_f)
    if anchor is None and values:
        anchor = float(values[0])
    if anchor is not None and not values:
        step = anchor * INTERNAL_TOLERANCE_MIN
        base = anchor - step if kind == 'support' else anchor + step
        values = [base, base - step] if kind == 'support' else [base, base + step]
    values = sorted(set(values), reverse=(kind == 'support'))
    fallback_levels: List[Dict[str, Any]] = []
    for idx, val in enumerate(values[:MIN_LEVELS_PER_SIDE], start=1):
        fallback_levels.append({
            'type': kind,
            'label': '',
            'price': val,
            'touchesSupport': 0 if kind == 'resistance' else 1,
            'touchesResistance': 0 if kind == 'support' else 1,
            'touchesTotal': 1,
            'breaches': 0,
            'firstTouch': None,
            'lastTouch': None,
            'timeframe': '',
        })
    return fallback_levels


def _build_levels(
    candles: List[Candle],
    tolerance_pct: float,
    price: Optional[float],
    kind: str,
    timeframe: str,
    min_touches: int = 1,
) -> List[Dict[str, Any]]:
    effective_gap_pct = min(max(tolerance_pct, INTERNAL_TOLERANCE_MIN), INTERNAL_TOLERANCE_MAX)
    anchor = _anchor_price(candles, price, kind)
    key = 'low' if kind == 'support' else 'high'
    candidates = _find_extreme_candidates(candles, key)
    clusters = _cluster_candidates(candidates, effective_gap_pct)
    levels: List[Dict[str, Any]] = []
    for cluster in clusters:
        level_price = cluster['price']
        if anchor is not None:
            if kind == 'support' and level_price >= anchor:
                continue
            if kind == 'resistance' and level_price <= anchor:
                continue
        touches, breaches, touch_dates = _count_touches(level_price, candles, effective_gap_pct, kind)
        if touches < max(1, int(min_touches or 1)):
            continue
        first_touch = touch_dates[0] if touch_dates else None
        last_touch = touch_dates[-1] if touch_dates else None
        levels.append({
            'type': kind,
            'label': '',
            'price': level_price,
            'touchesSupport': touches if kind == 'support' else 0,
            'touchesResistance': touches if kind == 'resistance' else 0,
            'touchesTotal': touches,
            'breaches': breaches,
            'firstTouch': _iso(first_touch),
            'lastTouch': _iso(last_touch),
            'timeframe': timeframe,
        })
    # Sort by strength (touch count) then proximity to current price.
    if kind == 'support':
        levels.sort(key=lambda lvl: (-lvl.get('touchesTotal', 0), -lvl.get('price', 0)))
    else:
        levels.sort(key=lambda lvl: (-lvl.get('touchesTotal', 0), lvl.get('price', 0)))

    spaced = _select_spaced_levels(levels, effective_gap_pct, kind)

    if len(spaced) < MIN_LEVELS_PER_SIDE:
        fallback = _fallback_levels(candles, price, kind)
        for fb in fallback:
            existing_ok = True
            for s in spaced:
                if not s.get('price'):
                    continue
                ref = s['price']
                gap = (ref - fb['price']) / ref if kind == 'support' else (fb['price'] - ref) / ref
                if gap < effective_gap_pct:
                    existing_ok = False
                    break
            if existing_ok:
                spaced.append(fb)
            if len(spaced) >= MIN_LEVELS_PER_SIDE:
                break

    # If still insufficient, synthesize levels off current price anchor to guarantee non-null.
    if len(spaced) < MIN_LEVELS_PER_SIDE and price:
        step = price * effective_gap_pct
        synthetic = [price - step, price - step * 2] if kind == 'support' else [price + step, price + step * 2]
        for val in synthetic:
          if any(abs((val - s.get('price', val)) / s.get('price', val)) < effective_gap_pct for s in spaced if s.get('price')):
              continue
          spaced.append({
              'type': kind,
              'label': '',
              'price': val,
              'touchesSupport': 1 if kind == 'support' else 0,
              'touchesResistance': 1 if kind == 'resistance' else 0,
              'touchesTotal': 1,
              'breaches': 0,
              'firstTouch': None,
              'lastTouch': None,
              'timeframe': timeframe,
          })
          if len(spaced) >= MIN_LEVELS_PER_SIDE:
              break

    spaced = spaced[:MAX_LEVELS_PER_SIDE]
    spaced.sort(key=lambda lvl: lvl['price'], reverse=(kind == 'support'))
    for idx, level in enumerate(spaced, start=1):
        level['label'] = f"{'S' if kind == 'support' else 'R'}{idx}"
    return spaced


def _ensure_min_levels(
    levels: List[Dict[str, Any]],
    candles: List[Candle],
    price: Optional[float],
    tolerance_pct: float,
    kind: str,
    timeframe: str,
) -> List[Dict[str, Any]]:
    """
    Guarantee at least MIN_LEVELS_PER_SIDE concrete levels per side,
    preserving spacing constraints where possible.
    """
    anchor = _anchor_price(candles, price, kind)
    if len(levels) >= MIN_LEVELS_PER_SIDE:
        return levels
    effective_gap_pct = min(max(tolerance_pct, INTERNAL_TOLERANCE_MIN), INTERNAL_TOLERANCE_MAX)
    padded = levels[:]
    if len(padded) < MIN_LEVELS_PER_SIDE:
        fallback = _fallback_levels(candles, anchor, kind)
        for fb in fallback:
            if any(
                s.get('price') and abs((fb['price'] - s['price']) / s['price']) < effective_gap_pct
                for s in padded if s.get('price')
            ):
                continue
            padded.append(fb)
            if len(padded) >= MIN_LEVELS_PER_SIDE:
                break
    if len(padded) < MIN_LEVELS_PER_SIDE and anchor:
        step = anchor * effective_gap_pct
        synthetic = [anchor - step, anchor - step * 2] if kind == 'support' else [anchor + step, anchor + step * 2]
        for val in synthetic:
            if any(
                s.get('price') and abs((val - s['price']) / s['price']) < effective_gap_pct
                for s in padded if s.get('price')
            ):
                continue
            padded.append({
                'type': kind,
                'label': '',
                'price': val,
                'touchesSupport': 1 if kind == 'support' else 0,
                'touchesResistance': 1 if kind == 'resistance' else 0,
                'touchesTotal': 1,
                'breaches': 0,
                'firstTouch': None,
                'lastTouch': None,
                'timeframe': timeframe,
            })
            if len(padded) >= MIN_LEVELS_PER_SIDE:
                break
    padded = padded[:MAX_LEVELS_PER_SIDE]
    padded.sort(key=lambda lvl: lvl['price'], reverse=(kind == 'support'))
    for idx, level in enumerate(padded, start=1):
        level['label'] = f"{'S' if kind == 'support' else 'R'}{idx}"
    return padded


def _aggregate_candles(candles: List[Candle], timeframe: str) -> List[Candle]:
    if timeframe == 'daily':
        return candles

    buckets: OrderedDict = OrderedDict()

    for candle in candles:
        dt = candle.get('date')
        if not isinstance(dt, datetime):
            continue
        if timeframe == 'weekly':
            iso = dt.isocalendar()
            bucket_key = (iso[0], iso[1])
        elif timeframe == 'monthly':
            bucket_key = (dt.year, dt.month)
        elif timeframe == 'yearly':
            bucket_key = (dt.year,)
        else:
            return candles

        bucket = buckets.get(bucket_key)
        high = candle.get('high')
        low = candle.get('low')
        close = candle.get('close')
        open_price = candle.get('open')
        volume = candle.get('volume')

        if bucket is None:
            bucket = {
                'open': float(open_price) if open_price is not None else (float(close) if close is not None else None),
                'high': float(high) if high is not None else (float(close) if close is not None else None),
                'low': float(low) if low is not None else (float(close) if close is not None else None),
                'close': float(close) if close is not None else None,
                'volume': float(volume) if volume is not None else None,
                'date': dt,
            }
            buckets[bucket_key] = bucket
            continue

        if high is not None:
            high_val = float(high)
            bucket['high'] = high_val if bucket['high'] is None else max(bucket['high'], high_val)
        if low is not None:
            low_val = float(low)
            bucket['low'] = low_val if bucket['low'] is None else min(bucket['low'], low_val)
        if close is not None:
            bucket['close'] = float(close)
        if open_price is not None and bucket['open'] is None:
            bucket['open'] = float(open_price)
        if volume is not None:
            bucket['volume'] = (bucket['volume'] or 0.0) + float(volume)
        bucket['date'] = dt

    aggregated: List[Candle] = []
    for bucket in buckets.values():
        high = bucket.get('high')
        low = bucket.get('low')
        close = bucket.get('close')
        if high is None and close is not None:
            bucket['high'] = close
        if low is None and close is not None:
            bucket['low'] = close
        aggregated.append(bucket)
    return aggregated


def _latest_close(candles: List[Candle]) -> Optional[float]:
    for candle in reversed(candles):
        close = candle.get('close')
        if close is not None:
            try:
                return float(close)
            except (TypeError, ValueError):
                continue
    return None


def _empty_timeframe_payload() -> Dict[str, Any]:
    return {
        'supports': [],
        'resistances': [],
        'supportDisplay': '-',
        'resistanceDisplay': '-',
        'supportTouchCount': 0,
        'resistanceTouchCount': 0,
        'primarySupport': None,
        'nextSupport': None,
        'primaryResistance': None,
        'nextResistance': None,
    }


def _format_level_brief(primary: Optional[Dict[str, Any]], secondary: Optional[Dict[str, Any]]) -> str:
    if not primary or primary.get('price') is None:
        # If primary is missing, try secondary
        if secondary and secondary.get('price') is not None:
            primary = secondary
            secondary = None
        else:
            return '-'
    def fmt(level: Dict[str, Any]) -> str:
        price = level.get('price')
        touches = level.get('touchesSupport') if level.get('type') == 'support' else level.get('touchesResistance')
        touches = touches if touches else level.get('touchesTotal')
        parts: List[str] = []
        if price is not None:
            parts.append(f"{price:.2f}")
        if touches:
            parts.append(f"{touches} touches")
        return ' '.join(parts)
    text = f"{primary.get('label', '')} {fmt(primary)}".strip()
    if secondary and secondary.get('price') is not None:
        text += f" -> {secondary.get('label', '')} {fmt(secondary)}"
    return text or '-'


def _levels_payload(levels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    payload: List[Dict[str, Any]] = []
    for level in levels:
        payload.append({
            'label': level.get('label'),
            'type': level.get('type'),
            'price': level.get('price'),
            'touchesSupport': level.get('touchesSupport'),
            'touchesResistance': level.get('touchesResistance'),
            'touchesTotal': level.get('touchesTotal'),
            'breaches': level.get('breaches'),
            'firstTouch': level.get('firstTouch'),
            'lastTouch': level.get('lastTouch'),
            'timeframe': level.get('timeframe'),
            'source': level.get('source') or ('manual' if level.get('manual') else 'generated'),
            'manual': bool(level.get('manual')),
            'dynamic': bool(level.get('dynamic')),
            'confluence': bool(level.get('confluence')),
        })
    return payload


def _manual_level_kind(level_type: Any, price: Optional[float], anchor_price: Optional[float]) -> Optional[str]:
    token = ''.join(ch for ch in str(level_type or '').strip().upper() if ch.isalpha())
    if token.startswith('SUP') or token == 'S':
        return 'support'
    if token.startswith('RES') or token == 'R':
        return 'resistance'
    if price is None or anchor_price is None:
        return None
    return 'support' if price <= anchor_price else 'resistance'


def _build_manual_level(record: Dict[str, Any], kind: str, timeframe_label: str) -> Optional[Dict[str, Any]]:
    price = _safe_round(record.get('price'), 6)
    if price is None:
        return None
    updated_at = (
        record.get('updatedAt')
        or record.get('updated_at')
        or record.get('createdAt')
        or record.get('created_at')
    )
    touch_key = 'touchesSupport' if kind == 'support' else 'touchesResistance'
    return {
        'label': '',
        'type': kind,
        'price': price,
        'touchesSupport': 0,
        'touchesResistance': 0,
        'touchesTotal': 0,
        'breaches': 0,
        'firstTouch': _iso(_parse_iso_datetime(updated_at)),
        'lastTouch': _iso(_parse_iso_datetime(updated_at)),
        'timeframe': timeframe_label,
        'source': 'manual',
        'manual': True,
        touch_key: 0,
    }


def _levels_are_equivalent(level_a: Dict[str, Any], level_b: Dict[str, Any], tolerance_pct: float = MANUAL_LEVEL_EQUIVALENCE_PCT) -> bool:
    price_a = _safe_round(level_a.get('price'), 6)
    price_b = _safe_round(level_b.get('price'), 6)
    if price_a is None or price_b is None:
        return False
    reference = max(abs(price_a), abs(price_b), 1.0)
    return abs(price_a - price_b) / reference <= tolerance_pct


def _merge_prioritized_levels(
    generated_levels: List[Dict[str, Any]],
    manual_levels: List[Dict[str, Any]],
    anchor_price: Optional[float],
    kind: str,
    timeframe_label: str,
    candles: Optional[List[Candle]] = None,
    tolerance_pct: float = MANUAL_LEVEL_EQUIVALENCE_PCT,
) -> List[Dict[str, Any]]:
    prioritized: List[Dict[str, Any]] = []
    manual_candidates: List[Dict[str, Any]] = []
    for manual in manual_levels or []:
        price = _safe_round(manual.get('price'), 6)
        resolved_kind = _manual_level_kind(manual.get('level_type'), price, anchor_price)
        if resolved_kind != kind:
            continue
        manual_level = _build_manual_level(manual, kind, timeframe_label)
        if not manual_level:
            continue
        if candles:
            touches, breaches, touch_dates = _count_touches(
                float(manual_level['price']),
                candles,
                max(INTERNAL_TOLERANCE_MIN, min(tolerance_pct, INTERNAL_TOLERANCE_MAX)),
                kind,
            )
            manual_level['touchesSupport'] = touches if kind == 'support' else 0
            manual_level['touchesResistance'] = touches if kind == 'resistance' else 0
            manual_level['touchesTotal'] = touches
            manual_level['breaches'] = breaches
            if touch_dates:
                manual_level['firstTouch'] = _iso(touch_dates[0])
                manual_level['lastTouch'] = _iso(touch_dates[-1])
        manual_candidates.append(manual_level)

    manual_candidates.sort(key=lambda lvl: lvl.get('price') or 0.0, reverse=(kind == 'support'))
    for manual_level in manual_candidates:
        if any(_levels_are_equivalent(manual_level, existing) for existing in prioritized):
            continue
        prioritized.append(manual_level)

    for generated in generated_levels or []:
        generated_copy = dict(generated)
        generated_copy['source'] = generated_copy.get('source') or 'generated'
        generated_copy['manual'] = bool(generated_copy.get('manual'))
        equivalent = next(
            (existing for existing in prioritized if _levels_are_equivalent(generated_copy, existing)),
            None,
        )
        if equivalent is not None:
            # Keep the existing manual-first display contract, but retain the
            # generated OHLCV evidence when both sources identify one zone.
            if equivalent.get('manual'):
                equivalent['dynamic'] = True
                equivalent['confluence'] = True
            for key in ('touchesSupport', 'touchesResistance', 'touchesTotal', 'breaches'):
                equivalent[key] = max(int(equivalent.get(key) or 0), int(generated_copy.get(key) or 0))
            if not equivalent.get('firstTouch'):
                equivalent['firstTouch'] = generated_copy.get('firstTouch')
            if generated_copy.get('lastTouch'):
                equivalent['lastTouch'] = generated_copy.get('lastTouch')
            continue
        prioritized.append(generated_copy)

    prioritized.sort(
        key=lambda lvl: (
            0 if lvl.get('manual') else 1,
            -(lvl.get('price') or 0.0) if kind == 'support' else (lvl.get('price') or 0.0),
            -int(lvl.get('touchesTotal') or 0),
        )
    )
    trimmed = prioritized[:MAX_MERGED_LEVELS_PER_SIDE]
    prefix = 'S' if kind == 'support' else 'R'
    for idx, level in enumerate(trimmed, start=1):
        level['label'] = f'{prefix}{idx}'
    return trimmed


def _strongest_level(
    levels: List[Dict[str, Any]],
    anchor_price: Optional[float],
) -> Optional[Dict[str, Any]]:
    """Select the best evidenced level without changing its display order."""
    candidates = [level for level in levels if _safe_round(level.get('price'), 6) is not None]
    if not candidates:
        return None

    def strength_key(level: Dict[str, Any]) -> tuple[int, int, int, float, int]:
        touches = int(level.get('touchesTotal') or 0)
        confluence = 1 if level.get('manual') and (level.get('confluence') or level.get('dynamic')) else 0
        breaches = int(level.get('breaches') or 0)
        price = float(level.get('price') or 0.0)
        distance = abs(price - anchor_price) if anchor_price is not None else 0.0
        return touches, confluence, -breaches, -distance, 1 if level.get('manual') else 0

    return dict(max(candidates, key=strength_key))


def _monthly_durations(closes: List[float], dates: List[datetime]) -> Dict[str, Dict[str, Any]]:
    metrics = {'uptrend': {}, 'downtrend': {}, 'consolidation': {}}
    if not closes or not dates:
        return metrics
    for label, window in MONTH_WINDOWS.items():
        if len(closes) <= window:
            metrics['uptrend'][label] = None
            metrics['downtrend'][label] = None
            metrics['consolidation'][label] = None
            continue
        slice_start = len(closes) - window
        window_closes = closes[slice_start:]
        high_value = max(window_closes)
        low_value = min(window_closes)
        high_idx = slice_start + window_closes.index(high_value)
        low_idx = slice_start + window_closes.index(low_value)
        up_summary = _event_summary(high_idx, len(closes) - 1, dates)
        down_summary = _event_summary(low_idx, len(closes) - 1, dates)
        metrics['uptrend'][label] = up_summary
        metrics['downtrend'][label] = down_summary
        if high_idx is not None and low_idx is not None and high_idx != low_idx:
            start = min(high_idx, low_idx)
            end = max(high_idx, low_idx)
            metrics['consolidation'][label] = _event_summary(start, end, dates)
        else:
            metrics['consolidation'][label] = None
    metrics['uptrendCount'] = sum(1 for v in metrics['uptrend'].values() if v)
    metrics['downtrendCount'] = sum(1 for v in metrics['downtrend'].values() if v)
    metrics['consolidationCount'] = sum(1 for v in metrics['consolidation'].values() if v)
    return metrics


def _momentum_signal(candles: List[Candle], closes: List[float]) -> Dict[str, Any]:
    if len(candles) < 4 or len(closes) < 4:
        return {'active': False, 'score': 0, 'conditions': {}, 'reasons': []}
    highs = [float(c.get('high')) for c in candles if c.get('high') is not None]
    lows = [float(c.get('low')) for c in candles if c.get('low') is not None]
    volumes = [float(c.get('volume')) for c in candles if c.get('volume') is not None]
    conditions: Dict[str, bool] = {}
    reasons: List[str] = []
    higher_high = False
    higher_low = False
    volume_expansion = False
    if len(highs) >= 3:
        higher_high = highs[-1] > highs[-2] >= highs[-3]
        conditions['higherHigh'] = higher_high
        if higher_high:
            reasons.append('Breaking higher highs')
    if len(lows) >= 3:
        higher_low = lows[-1] >= lows[-2] >= lows[-3]
        conditions['higherLow'] = higher_low
        if higher_low:
            reasons.append('Higher lows forming')
    if len(volumes) >= 5:
        avg_vol = mean(volumes[-5:-1]) if len(volumes) > 5 else mean(volumes)
        volume_expansion = volumes[-1] > avg_vol
        conditions['volumeExpansion'] = volume_expansion
        if volume_expansion:
            reasons.append('Volume expansion on latest move')
    score = sum(1 for val in conditions.values() if val)
    active = score >= 2
    return {
        'active': active,
        'score': score,
        'conditions': conditions,
        'reasons': reasons,
    }


def _nearest_level_snapshot(price: float, support_levels: List[Dict[str, Any]], resistance_levels: List[Dict[str, Any]]) -> Dict[str, Any]:
    best: Optional[Dict[str, Any]] = None
    for kind, levels in (('support', support_levels), ('resistance', resistance_levels)):
        for level in levels:
            level_price = level.get('price')
            if level_price is None:
                continue
            try:
                numeric_price = float(level_price)
            except (TypeError, ValueError):
                continue
            distance_pct = abs((price - numeric_price) / price) * 100.0 if price else None
            candidate = {
                'type': kind,
                'label': level.get('label') or ('S1' if kind == 'support' else 'R1'),
                'price': numeric_price,
                'distancePct': distance_pct,
                'touchesTotal': int(level.get('touchesTotal') or 0),
                'lastTouch': level.get('lastTouch'),
            }
            if best is None:
                best = candidate
                continue
            best_distance = best.get('distancePct')
            candidate_distance = candidate.get('distancePct')
            if best_distance is None or (candidate_distance is not None and candidate_distance < best_distance):
                best = candidate
    return best or {
        'type': '',
        'label': '',
        'price': None,
        'distancePct': None,
        'touchesTotal': 0,
        'lastTouch': None,
    }


def _trend_context(
    candles: List[Candle],
    structural_direction: str,
    support_levels: List[Dict[str, Any]],
    resistance_levels: List[Dict[str, Any]],
) -> Dict[str, Any]:
    closes = _close_values(candles)
    if not closes:
        return {
            'direction': structural_direction,
            'strength': None,
            'ema20SlopePct': None,
            'state': 'ranging',
            'conditions': {},
        }
    latest_price = closes[-1]
    atr_value = _average_true_range(candles, ATR_PERIOD)
    atr_pct = ((atr_value / latest_price) * 100.0) if atr_value and latest_price else None
    adx_value = _compute_adx(candles, ADX_PERIOD)
    ema_slope_pct = _ema_slope_pct(closes, EMA_PERIOD, 10)
    structure = _hh_hl_state(candles, 20)
    nearest_level = _nearest_level_snapshot(latest_price, support_levels, resistance_levels)
    near_support = nearest_level.get('type') == 'support' and (nearest_level.get('distancePct') or 99.0) <= max(1.4, (atr_pct or 0.8) * 1.4)
    near_resistance = nearest_level.get('type') == 'resistance' and (nearest_level.get('distancePct') or 99.0) <= max(1.4, (atr_pct or 0.8) * 1.4)

    direction = structural_direction
    if adx_value is not None and adx_value < 18 and abs(ema_slope_pct or 0.0) < 1.0:
        direction = 'Consolidation'
    elif structure.get('higherHighHigherLow') and (ema_slope_pct or 0.0) > 0:
        direction = 'Uptrend'
    elif structure.get('lowerHighLowerLow') and (ema_slope_pct or 0.0) < 0:
        direction = 'Downtrend'

    state = 'ranging'
    if direction == 'Uptrend' and (adx_value or 0.0) >= 25:
        state = 'impulsive'
    elif direction == 'Downtrend' and (adx_value or 0.0) >= 25:
        state = 'impulsive'
    elif near_support or near_resistance:
        state = 'breakout_watch'

    return {
        'direction': direction,
        'strength': _safe_round(adx_value, 2),
        'ema20SlopePct': _safe_round(ema_slope_pct, 3),
        'atr': _safe_round(atr_value, 2),
        'atrPct': _safe_round(atr_pct, 3),
        'state': state,
        'conditions': {
            'higherHighHigherLow': bool(structure.get('higherHighHigherLow')),
            'lowerHighLowerLow': bool(structure.get('lowerHighLowerLow')),
            'nearSupport': near_support,
            'nearResistance': near_resistance,
        },
        'nearestLevel': nearest_level,
    }


def _detect_price_action(
    candles: List[Candle],
    price: float,
    support_levels: List[Dict[str, Any]],
    resistance_levels: List[Dict[str, Any]],
    trend_context: Dict[str, Any],
) -> Dict[str, Any]:
    nearest = _nearest_level_snapshot(price, support_levels, resistance_levels)
    volume_ratio = _volume_ratio(candles, 20)
    volume_spike = bool(volume_ratio and volume_ratio >= 1.2)
    default = {
        'state': 'neutral',
        'pattern': 'none',
        'label': 'Neutral',
        'lastTouch': nearest.get('type') or '',
        'distancePct': _safe_round(nearest.get('distancePct'), 2),
        'volumeSpike': volume_spike,
        'volumeRatio': _safe_round(volume_ratio, 2),
        'bias': 'neutral',
        'summary': 'No decisive price-action signal.',
    }
    if len(candles) < 2:
        return default

    last = candles[-1]
    prev = candles[-2]
    if last.get('high') is None or last.get('low') is None or last.get('close') is None or prev.get('close') is None:
        return default

    last_open = float(last.get('open')) if last.get('open') is not None else float(prev.get('close'))
    last_close = float(last.get('close'))
    last_high = float(last.get('high'))
    last_low = float(last.get('low'))
    prev_open = float(prev.get('open')) if prev.get('open') is not None else float(prev.get('close'))
    prev_close = float(prev.get('close'))

    candle_range = max(last_high - last_low, 0.0001)
    body = abs(last_close - last_open)
    upper_wick = max(last_high - max(last_open, last_close), 0.0)
    lower_wick = max(min(last_open, last_close) - last_low, 0.0)
    distance_pct = nearest.get('distancePct') or 99.0
    atr_pct = trend_context.get('atrPct') or 0.75
    proximity_limit = max(1.4, atr_pct * 1.5)
    near_support = nearest.get('type') == 'support' and distance_pct <= proximity_limit
    near_resistance = nearest.get('type') == 'resistance' and distance_pct <= proximity_limit

    bullish_engulfing = last_close > last_open and prev_close < prev_open and last_close >= prev_open and last_open <= prev_close
    bearish_engulfing = last_close < last_open and prev_close > prev_open and last_open >= prev_close and last_close <= prev_open
    inside_bar = last_high <= float(prev.get('high') or last_high) and last_low >= float(prev.get('low') or last_low)
    bullish_pinbar = lower_wick >= body * 2 and lower_wick >= candle_range * 0.45 and last_close >= last_open
    bearish_pinbar = upper_wick >= body * 2 and upper_wick >= candle_range * 0.45 and last_close <= last_open

    primary_support = support_levels[0] if support_levels else None
    primary_resistance = resistance_levels[0] if resistance_levels else None
    breakout = bool(
        primary_resistance
        and primary_resistance.get('price') is not None
        and last_close > float(primary_resistance.get('price'))
        and prev_close <= float(primary_resistance.get('price'))
        and volume_spike
    )
    breakdown = bool(
        primary_support
        and primary_support.get('price') is not None
        and last_close < float(primary_support.get('price'))
        and prev_close >= float(primary_support.get('price'))
        and volume_spike
    )

    if breakout:
        return {
            **default,
            'state': 'breakout',
            'pattern': 'breakout_above_resistance',
            'label': 'Breakout',
            'bias': 'bullish',
            'summary': 'Close pushed above resistance with volume expansion.',
        }
    if breakdown:
        return {
            **default,
            'state': 'breakdown',
            'pattern': 'breakdown_below_support',
            'label': 'Breakdown',
            'bias': 'bearish',
            'summary': 'Close slipped below support with volume expansion.',
        }
    if bullish_pinbar and near_support:
        return {
            **default,
            'state': 'bullish_rejection',
            'pattern': 'pinbar_at_support',
            'label': 'Bullish Rejection',
            'bias': 'bullish',
            'summary': 'Lower-wick rejection formed near support.',
        }
    if bearish_pinbar and near_resistance:
        return {
            **default,
            'state': 'bearish_rejection',
            'pattern': 'pinbar_at_resistance',
            'label': 'Bearish Rejection',
            'bias': 'bearish',
            'summary': 'Upper-wick rejection formed near resistance.',
        }
    if bullish_engulfing and near_support:
        return {
            **default,
            'state': 'bullish_engulfing',
            'pattern': 'bullish_engulfing_at_support',
            'label': 'Bullish Engulfing',
            'bias': 'bullish',
            'summary': 'Bullish engulfing candle printed close to support.',
        }
    if bearish_engulfing and near_resistance:
        return {
            **default,
            'state': 'bearish_engulfing',
            'pattern': 'bearish_engulfing_at_resistance',
            'label': 'Bearish Engulfing',
            'bias': 'bearish',
            'summary': 'Bearish engulfing candle printed close to resistance.',
        }
    if inside_bar:
        return {
            **default,
            'state': 'inside_bar',
            'pattern': 'inside_bar',
            'label': 'Inside Bar',
            'bias': 'neutral',
            'summary': 'Inside bar suggests compression before expansion.',
        }
    if trend_context.get('direction') == 'Consolidation':
        return {
            **default,
            'state': 'range',
            'pattern': 'range_rotation',
            'label': 'Range',
            'bias': 'neutral',
            'summary': 'Price remains range-bound without a decisive break.',
        }
    return default


def _compute_score(
    *,
    price: float,
    support_levels: List[Dict[str, Any]],
    resistance_levels: List[Dict[str, Any]],
    touch_counts: Tuple[int, int],
    momentum: Dict[str, Any],
    trend_context: Dict[str, Any],
    price_action: Dict[str, Any],
) -> Tuple[int, Dict[str, Any]]:
    support_touches, resistance_touches = touch_counts
    total_touches = max(0, support_touches + resistance_touches)
    touch_component = min(18, int(round(math.log1p(total_touches) * 3.0))) if total_touches else 0

    nearest = trend_context.get('nearestLevel') or _nearest_level_snapshot(price, support_levels, resistance_levels)
    distance_pct = nearest.get('distancePct')
    atr_pct = trend_context.get('atrPct') or 0.75
    proximity_limit = max(1.5, atr_pct * 1.75)
    if distance_pct is None:
        proximity_component = 0
    else:
        proximity_ratio = min(distance_pct / proximity_limit, 1.5)
        proximity_component = int(round(max(0.0, 22.0 * (1.0 - (proximity_ratio / 1.5)))))

    last_touch_dt = _parse_iso_datetime(nearest.get('lastTouch'))
    recency_component = 0
    if last_touch_dt is not None:
        days_since = max(0, (datetime.utcnow() - last_touch_dt).days)
        if days_since <= 10:
            recency_component = 12
        elif days_since <= 20:
            recency_component = 9
        elif days_since <= 40:
            recency_component = 6
        elif days_since <= 90:
            recency_component = 3

    direction = trend_context.get('direction') or 'Consolidation'
    trend_base = {
        'Uptrend': 12,
        'Consolidation': 8,
        'Downtrend': 8,
    }.get(direction, 8)
    trend_strength_bonus = min(8, int(round((trend_context.get('strength') or 0.0) / 5.0)))
    if direction == 'Downtrend' and price_action.get('state') != 'breakdown':
        trend_base = 6
    trend_component = trend_base + trend_strength_bonus

    momentum_component = min(12, int(momentum.get('score', 0) or 0) * 4)
    volume_ratio = price_action.get('volumeRatio')
    volume_component = 0
    if volume_ratio is not None:
        if volume_ratio >= 1.5:
            volume_component = 8
        elif volume_ratio >= 1.2:
            volume_component = 6
        elif volume_ratio >= 1.0:
            volume_component = 4
        else:
            volume_component = 2

    price_action_component = {
        'breakout': 10,
        'breakdown': 10,
        'bullish_rejection': 8,
        'bearish_rejection': 8,
        'bullish_engulfing': 7,
        'bearish_engulfing': 7,
        'inside_bar': 4,
        'range': 3,
        'neutral': 0,
    }.get(str(price_action.get('state') or 'neutral').strip().lower(), 0)

    total = touch_component + proximity_component + recency_component + trend_component + momentum_component + volume_component + price_action_component
    score = max(0, min(100, int(round(total))))
    breakdown = {
        'touches': touch_component,
        'proximity': proximity_component,
        'recency': recency_component,
        'trend': trend_component,
        'momentum': momentum_component,
        'volume': volume_component,
        'priceAction': price_action_component,
        'total': score,
        'nearestLevel': {
            'label': nearest.get('label'),
            'type': nearest.get('type'),
            'price': _safe_round(nearest.get('price'), 2),
            'distancePct': _safe_round(distance_pct, 2),
        },
    }
    return score, breakdown


def _level_value_map(levels: List[Dict[str, Any]], prefix: str) -> Dict[str, Optional[float]]:
    mapped: Dict[str, Optional[float]] = {}
    for idx, level in enumerate(levels[:10], start=1):
        mapped[f'{prefix}{idx}'] = level.get('price')
    return mapped


def _build_symbol_row(
    symbol: str,
    candles: List[Candle],
    base_row: Optional[Dict[str, Any]],
    tolerance_pct: float,
    aliases: List[str],
    selected_timeframe: str,
    lookback_days: Any = None,
    min_touches: int = 1,
    manual_levels_by_timeframe: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> Optional[Dict[str, Any]]:
    if not candles:
        return None
    candles_sorted = sorted(candles, key=lambda c: c.get('date') or datetime.min)
    scoped_candles, effective_lookback = _slice_candles_for_lookback(candles_sorted, lookback_days)
    closes = [float(c.get('close')) for c in scoped_candles if c.get('close') is not None]
    if not closes:
        return None
    latest_candle = next((c for c in reversed(scoped_candles) if c.get('close') is not None), None)
    price = float(latest_candle.get('close')) if latest_candle else closes[-1]
    last_date = latest_candle.get('date') if latest_candle else None
    first_candle = next((c for c in scoped_candles if c.get('date') is not None), None)
    first_date = first_candle.get('date') if first_candle else None

    timeframe_sets = {
        'daily': scoped_candles,
        'weekly': _aggregate_candles(scoped_candles, 'weekly'),
        'monthly': _aggregate_candles(scoped_candles, 'monthly'),
        'yearly': _aggregate_candles(scoped_candles, 'yearly'),
    }

    timeframe_payloads: Dict[str, Dict[str, Any]] = {}
    manual_payloads = manual_levels_by_timeframe if isinstance(manual_levels_by_timeframe, dict) else {}
    for label, tf_candles in timeframe_sets.items():
        if not tf_candles:
            timeframe_payloads[label] = _empty_timeframe_payload()
            continue
        tf_price = _latest_close(tf_candles) or price
        tf_support_levels_generated = _ensure_min_levels(
            _build_levels(tf_candles, tolerance_pct, tf_price, 'support', label, min_touches=min_touches),
            tf_candles,
            tf_price,
            tolerance_pct,
            'support',
            label,
        )
        tf_resistance_levels_generated = _ensure_min_levels(
            _build_levels(tf_candles, tolerance_pct, tf_price, 'resistance', label, min_touches=min_touches),
            tf_candles,
            tf_price,
            tolerance_pct,
            'resistance',
            label,
        )
        manual_levels = manual_payloads.get(label, [])
        tf_support_levels = _merge_prioritized_levels(
            tf_support_levels_generated,
            manual_levels,
            tf_price,
            'support',
            label,
            candles=tf_candles,
            tolerance_pct=tolerance_pct,
        )
        tf_resistance_levels = _merge_prioritized_levels(
            tf_resistance_levels_generated,
            manual_levels,
            tf_price,
            'resistance',
            label,
            candles=tf_candles,
            tolerance_pct=tolerance_pct,
        )
        # Ensure display strings are not '-'
        support_display = _format_level_brief(
            tf_support_levels[0] if tf_support_levels else None,
            tf_support_levels[1] if len(tf_support_levels) > 1 else None,
        )
        if support_display == '-' and tf_support_levels:
            primary = tf_support_levels[0]
            support_display = f"{primary.get('label') or 'S1'} {primary.get('price'):.2f}"
        resistance_display = _format_level_brief(
            tf_resistance_levels[0] if tf_resistance_levels else None,
            tf_resistance_levels[1] if len(tf_resistance_levels) > 1 else None,
        )
        if resistance_display == '-' and tf_resistance_levels:
            primary_r = tf_resistance_levels[0]
            resistance_display = f"{primary_r.get('label') or 'R1'} {primary_r.get('price'):.2f}"
        support_serialized = _levels_payload(tf_support_levels)
        resistance_serialized = _levels_payload(tf_resistance_levels)
        support_touch_count = sum(level.get('touchesSupport', 0) for level in tf_support_levels)
        resistance_touch_count = sum(level.get('touchesResistance', 0) for level in tf_resistance_levels)
        timeframe_payloads[label] = {
            'supports': support_serialized,
            'resistances': resistance_serialized,
            'supportDisplay': support_display,
            'resistanceDisplay': resistance_display,
            'supportTouchCount': support_touch_count,
            'resistanceTouchCount': resistance_touch_count,
            'primarySupport': support_serialized[0] if support_serialized else None,
            'nextSupport': support_serialized[1] if len(support_serialized) > 1 else None,
            'primaryResistance': resistance_serialized[0] if resistance_serialized else None,
            'nextResistance': resistance_serialized[1] if len(resistance_serialized) > 1 else None,
        }

    selected_label = str(selected_timeframe or 'daily').lower()
    selected_payload = timeframe_payloads.get(selected_label) or timeframe_payloads.get('daily') or _empty_timeframe_payload()
    selected_candles = timeframe_sets.get(selected_label) or timeframe_sets.get('daily') or scoped_candles
    selected_closes = [float(c.get('close')) for c in selected_candles if c.get('close') is not None]
    trend_analysis = _analyze_structural_trend(selected_candles)
    transitions = trend_analysis['transitions']
    reversal_count = trend_analysis['reversalCount']
    month_metrics = _monthly_durations(selected_closes, [c.get('date') for c in selected_candles])
    momentum = _momentum_signal(selected_candles, selected_closes)
    trading_days = len(selected_candles)

    support_touches = selected_payload['supportTouchCount']
    resistance_touches = selected_payload['resistanceTouchCount']

    support_display = selected_payload['supportDisplay']
    resistance_display = selected_payload['resistanceDisplay']
    support_levels_serialized = selected_payload['supports']
    resistance_levels_serialized = selected_payload['resistances']
    primary_support_payload = selected_payload['primarySupport']
    secondary_support_payload = selected_payload['nextSupport']
    primary_resistance_payload = selected_payload['primaryResistance']
    secondary_resistance_payload = selected_payload['nextResistance']
    strongest_support_payload = _strongest_level(support_levels_serialized, price)
    strongest_resistance_payload = _strongest_level(resistance_levels_serialized, price)
    trend_context = _trend_context(
        selected_candles,
        trend_analysis['direction'],
        support_levels_serialized,
        resistance_levels_serialized,
    )
    trend_direction = trend_context['direction']
    price_action = _detect_price_action(
        selected_candles,
        price,
        support_levels_serialized,
        resistance_levels_serialized,
        trend_context,
    )
    score, score_breakdown = _compute_score(
        price=price,
        support_levels=support_levels_serialized,
        resistance_levels=resistance_levels_serialized,
        touch_counts=(support_touches, resistance_touches),
        momentum=momentum,
        trend_context=trend_context,
        price_action=price_action,
    )
    row: Dict[str, Any] = {
        'symbol': symbol,
        'aliases': aliases,
        'price': price,
        'priceSort': price,
        'tradingDate': _format_date(first_date),
        'tradingDateSort': first_date.timestamp() if isinstance(first_date, datetime) else None,
        'ltcDate': _format_date(last_date),
        'ltcDateSort': last_date.timestamp() if isinstance(last_date, datetime) else None,
        'tradingDays': trading_days,
        'tradingDaysSort': trading_days,
        'T_D': trading_days,
        'supportDisplay': support_display,
        'resistanceDisplay': resistance_display,
        'support': support_display,
        'resistance': resistance_display,
        'supportLevels': support_levels_serialized,
        'resistanceLevels': resistance_levels_serialized,
        'primarySupport': primary_support_payload,
        'nextSupport': secondary_support_payload,
        'primaryResistance': primary_resistance_payload,
        'nextResistance': secondary_resistance_payload,
        'dominantSupport': primary_support_payload,
        'dominantResistance': primary_resistance_payload,
        'strongestSupport': strongest_support_payload,
        'strongestResistance': strongest_resistance_payload,
        'supportSummary': support_display,
        'resistanceSummary': resistance_display,
        'supportTouchCount': support_touches,
        'resistanceTouchCount': resistance_touches,
        'touchCounts': {
            'support': support_touches,
            'resistance': resistance_touches,
        },
        'timeframes': timeframe_payloads,
        'selectedTimeframe': selected_label,
        'trendDirection': trend_direction,
        'trendDirectionSort': {'Uptrend': 0, 'Downtrend': 1, 'Consolidation': 2}.get(trend_direction, 2),
        'trendStrength': trend_context.get('strength'),
        'trendState': trend_context.get('state'),
        'trendMetrics': trend_context,
        'trendTransitions': transitions,
        'trendWindows': month_metrics,
        'momentumSignal': momentum,
        'priceAction': price_action,
        'priceActionSummary': price_action.get('summary'),
        'score': score,
        'scoreSort': score,
        'scoreBreakdown': score_breakdown,
        'reversalCount': reversal_count,
        'lookbackMode': (
            'max'
            if _is_max_lookback(lookback_days)
            else ('fixed' if _resolve_requested_lookback_days(lookback_days) is not None else 'auto')
        ),
        'lookbackDays': effective_lookback,
    }

    for idx in range(1, 11):
        key_support = f'S{idx}'
        key_resistance = f'R{idx}'
        row[key_support] = support_levels_serialized[idx - 1]['price'] if len(support_levels_serialized) >= idx else (
            support_levels_serialized[-1]['price'] if support_levels_serialized else price
        )
        row[key_resistance] = resistance_levels_serialized[idx - 1]['price'] if len(resistance_levels_serialized) >= idx else (
            resistance_levels_serialized[-1]['price'] if resistance_levels_serialized else price
        )

    if base_row:
        for key, value in base_row.items():
            if key.startswith('_'):
                continue
            row.setdefault(key, value)

    row = _apply_master_score_fields(row, {
        'supportPrice': (primary_support_payload or {}).get('price') if isinstance(primary_support_payload, dict) else None,
        'resistancePrice': (primary_resistance_payload or {}).get('price') if isinstance(primary_resistance_payload, dict) else None,
        'trendDirection': trend_direction,
        'adx14': trend_context.get('strength'),
        'ema20SlopePct': trend_context.get('ema20SlopePct'),
        'atr14': trend_context.get('atr'),
        'distanceToSupportPct': (
            (trend_context.get('nearestLevel') or {}).get('distancePct')
            if (trend_context.get('nearestLevel') or {}).get('type') == 'support'
            else None
        ),
        'distanceToResistancePct': (
            (trend_context.get('nearestLevel') or {}).get('distancePct')
            if (trend_context.get('nearestLevel') or {}).get('type') == 'resistance'
            else None
        ),
        'breakoutFlag': 'BREAKOUT' if price_action.get('state') == 'breakout' else '',
        'breakdownFlag': 'BREAKDOWN' if price_action.get('state') == 'breakdown' else '',
    })
    return row


def build_sr_levels_payload(
    ohlc_series: Dict[str, List[Candle]],
    base_rows: List[Dict[str, Any]],
    tolerance_pct: float,
    selected_timeframe: str,
    lookback_days: Any = None,
    min_touches: int = 1,
    price_action_filter: Optional[str] = None,
    manual_levels_by_symbol: Optional[Dict[str, Dict[str, List[Dict[str, Any]]]]] = None,
) -> Dict[str, Any]:
    tolerance_pct = max(0.005, min(tolerance_pct, 0.25))
    normalized_timeframe = str(selected_timeframe or 'daily').lower()
    normalized_price_action = str(price_action_filter or 'all').strip().lower() or 'all'
    if normalized_price_action not in PRICE_ACTION_FILTER_OPTIONS:
        normalized_price_action = 'all'
    series_by_symbol, alias_map = _prepare_series(ohlc_series)
    base_map = {normalize_symbol(row.get('symbol')): row for row in (base_rows or []) if row.get('symbol')}
    rows: List[Dict[str, Any]] = []

    for symbol, candles in series_by_symbol.items():
        base_row = base_map.get(symbol)
        row = _build_symbol_row(
            symbol,
            candles,
            base_row,
            tolerance_pct,
            alias_map.get(symbol, []),
            normalized_timeframe,
            lookback_days=lookback_days,
            min_touches=min_touches,
            manual_levels_by_timeframe=(manual_levels_by_symbol or {}).get(symbol),
        )
        if row:
            if normalized_price_action != 'all':
                state = str((row.get('priceAction') or {}).get('state') or '').strip().lower()
                if state != normalized_price_action:
                    continue
            rows.append(row)

    rows.sort(key=lambda r: r.get('symbol', ''))
    for idx, row in enumerate(rows, start=1):
        row['sNo'] = idx

    payload = {
        'rows': rows,
        'count': len(rows),
        'generatedAt': datetime.utcnow().isoformat(timespec='seconds') + 'Z',
        'tolerance': tolerance_pct,
        'toleranceOptions': SR_TOLERANCE_OPTIONS,
        'timeframe': normalized_timeframe,
        'lookbackDays': 'max' if _is_max_lookback(lookback_days) else (_resolve_requested_lookback_days(lookback_days) or 'auto'),
        'minTouches': max(1, int(min_touches or 1)),
        'priceActionFilter': normalized_price_action,
    }
    return payload
