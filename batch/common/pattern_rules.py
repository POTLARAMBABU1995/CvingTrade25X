from typing import Dict, List, Optional

# Consolidation breakout thresholds
CONSOLIDATION_LOOKBACK = 20  # bars to define a base
CONSOLIDATION_ATR_MULT = 1.0  # base range <= ATR * multiplier
BREAKOUT_VOLUME_MULT = 1.5  # breakout volume >= avg volume * multiplier
BREAKOUT_ATR_MULT = 0.5  # breakout close above base by ATR * multiplier

# Bull flag thresholds
FLAG_IMPULSE_BARS = 10  # impulse lookback
FLAG_IMPULSE_PCT = 0.08  # minimum impulse move
FLAG_CONSOLIDATION_BARS = 8  # consolidation length after impulse
FLAG_MAX_RETRACE = 0.5  # max retrace of impulse

# Double bottom thresholds
DOUBLE_BOTTOM_TOL_PCT = 0.02  # lows within 2%
NECKLINE_BREAK_PCT = 0.01  # neckline break percent
MIN_SEPARATION_BARS = 8  # separation between lows

# Zone thresholds
ZONE_CONSOLIDATION_BARS = 8  # bars for zone base
ZONE_ATR_MULT = 0.8  # consolidation range vs ATR
ZONE_IMPULSE_ATR_MULT = 1.5  # impulse move vs ATR


def _avg(values: List[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def detect_breakout_from_consolidation(
    dates: List[object],
    highs: List[float],
    lows: List[float],
    closes: List[float],
    volumes: List[float],
    atr_values: List[Optional[float]],
    volume_window: int = 20,
) -> List[Dict[str, object]]:
    patterns: List[Dict[str, object]] = []
    for i in range(CONSOLIDATION_LOOKBACK, len(closes)):
        atr = atr_values[i]
        if atr is None or atr == 0:
            continue
        base_start = i - CONSOLIDATION_LOOKBACK
        base_high = max(highs[base_start:i])
        base_low = min(lows[base_start:i])
        base_range = base_high - base_low
        if base_range > atr * CONSOLIDATION_ATR_MULT:
            continue
        avg_volume = _avg(volumes[max(0, i - volume_window):i])
        breakout_level = base_high + (atr * BREAKOUT_ATR_MULT)
        if closes[i] > breakout_level and volumes[i] >= avg_volume * BREAKOUT_VOLUME_MULT:
            score = min(1.0, (volumes[i] / max(avg_volume, 1)) / (BREAKOUT_VOLUME_MULT * 2))
            patterns.append({
                'pattern_type': 'BREAKOUT',
                't1_index': base_start,
                't2_index': i,
                'breakout_index': i,
                'price_low': base_low,
                'price_high': base_high,
                'score': score,
                'confidence': score,
            })
    return patterns


def detect_bull_flag(
    dates: List[object],
    highs: List[float],
    lows: List[float],
    closes: List[float],
    volumes: List[float],
    atr_values: List[Optional[float]],
) -> List[Dict[str, object]]:
    patterns: List[Dict[str, object]] = []
    for i in range(FLAG_IMPULSE_BARS + FLAG_CONSOLIDATION_BARS, len(closes)):
        impulse_start = i - (FLAG_IMPULSE_BARS + FLAG_CONSOLIDATION_BARS)
        impulse_end = i - FLAG_CONSOLIDATION_BARS
        impulse_move = (closes[impulse_end] - closes[impulse_start]) / max(closes[impulse_start], 1)
        if impulse_move < FLAG_IMPULSE_PCT:
            continue
        cons_start = impulse_end
        cons_end = i
        cons_high = max(highs[cons_start:cons_end])
        cons_low = min(lows[cons_start:cons_end])
        retrace = (closes[impulse_end] - cons_low) / max(closes[impulse_end] - closes[impulse_start], 1e-6)
        if retrace > FLAG_MAX_RETRACE:
            continue
        atr = atr_values[i] or 0
        if atr and (cons_high - cons_low) > atr * 1.2:
            continue
        breakout_level = cons_high + (atr * 0.3)
        if closes[i] > breakout_level:
            patterns.append({
                'pattern_type': 'BULL_FLAG',
                't1_index': cons_start,
                't2_index': cons_end,
                'breakout_index': i,
                'price_low': cons_low,
                'price_high': cons_high,
                'score': min(1.0, impulse_move / (FLAG_IMPULSE_PCT * 2)),
                'confidence': min(1.0, impulse_move / (FLAG_IMPULSE_PCT * 2)),
            })
    return patterns


def detect_double_bottom(
    dates: List[object],
    highs: List[float],
    lows: List[float],
    closes: List[float],
    volumes: List[float],
    volume_window: int = 20,
) -> List[Dict[str, object]]:
    patterns: List[Dict[str, object]] = []
    for i in range(MIN_SEPARATION_BARS, len(lows)):
        first_low_idx = i - MIN_SEPARATION_BARS
        second_low_idx = i
        low1 = lows[first_low_idx]
        low2 = lows[second_low_idx]
        if abs(low2 - low1) / max(low1, 1) > DOUBLE_BOTTOM_TOL_PCT:
            continue
        neckline = max(highs[first_low_idx:second_low_idx + 1])
        breakout_level = neckline * (1 + NECKLINE_BREAK_PCT)
        avg_volume = _avg(volumes[max(0, i - volume_window):i])
        if closes[i] > breakout_level and volumes[i] >= avg_volume * BREAKOUT_VOLUME_MULT:
            patterns.append({
                'pattern_type': 'DOUBLE_BOTTOM',
                't1_index': first_low_idx,
                't2_index': second_low_idx,
                'breakout_index': i,
                'price_low': min(low1, low2),
                'price_high': neckline,
                'score': min(1.0, (volumes[i] / max(avg_volume, 1)) / (BREAKOUT_VOLUME_MULT * 2)),
                'confidence': min(1.0, (volumes[i] / max(avg_volume, 1)) / (BREAKOUT_VOLUME_MULT * 2)),
            })
    return patterns


def detect_zones(
    dates: List[object],
    highs: List[float],
    lows: List[float],
    closes: List[float],
    volumes: List[float],
    atr_values: List[Optional[float]],
) -> List[Dict[str, object]]:
    zones: List[Dict[str, object]] = []
    for i in range(ZONE_CONSOLIDATION_BARS, len(closes) - 1):
        atr = atr_values[i] or 0
        if atr == 0:
            continue
        base_start = i - ZONE_CONSOLIDATION_BARS
        base_end = i
        base_high = max(highs[base_start:base_end])
        base_low = min(lows[base_start:base_end])
        base_range = base_high - base_low
        if base_range > atr * ZONE_ATR_MULT:
            continue
        next_close = closes[i + 1]
        if next_close > base_high + atr * ZONE_IMPULSE_ATR_MULT:
            zones.append({
                'zone_type': 'DEMAND',
                't1_index': base_start,
                't2_index': base_end,
                'price_low': base_low,
                'price_high': base_high,
                'score': min(1.0, (next_close - base_high) / (atr * ZONE_IMPULSE_ATR_MULT)),
                'confidence': min(1.0, (next_close - base_high) / (atr * ZONE_IMPULSE_ATR_MULT)),
            })
        elif next_close < base_low - atr * ZONE_IMPULSE_ATR_MULT:
            zones.append({
                'zone_type': 'SUPPLY',
                't1_index': base_start,
                't2_index': base_end,
                'price_low': base_low,
                'price_high': base_high,
                'score': min(1.0, (base_low - next_close) / (atr * ZONE_IMPULSE_ATR_MULT)),
                'confidence': min(1.0, (base_low - next_close) / (atr * ZONE_IMPULSE_ATR_MULT)),
            })
    return zones
