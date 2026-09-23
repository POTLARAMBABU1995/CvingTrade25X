from typing import Dict, List, Optional


def ema(values: List[float], period: int) -> List[Optional[float]]:
    if period <= 0:
        return [None for _ in values]
    result: List[Optional[float]] = [None for _ in values]
    if len(values) < period:
        return result
    sma = sum(values[:period]) / period
    result[period - 1] = sma
    multiplier = 2 / (period + 1)
    ema_prev = sma
    for i in range(period, len(values)):
        ema_prev = (values[i] * multiplier) + (ema_prev * (1 - multiplier))
        result[i] = ema_prev
    return result


def rsi(values: List[float], period: int = 14) -> List[Optional[float]]:
    if len(values) < period + 1:
        return [None for _ in values]
    gains = [0.0]
    losses = [0.0]
    for i in range(1, len(values)):
        delta = values[i] - values[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(abs(min(delta, 0.0)))
    avg_gain = sum(gains[1:period + 1]) / period
    avg_loss = sum(losses[1:period + 1]) / period
    result: List[Optional[float]] = [None for _ in values]
    rs = avg_gain / avg_loss if avg_loss != 0 else 0
    result[period] = 100 - (100 / (1 + rs)) if avg_loss != 0 else 100
    for i in range(period + 1, len(values)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rs = avg_gain / avg_loss if avg_loss != 0 else 0
        result[i] = 100 - (100 / (1 + rs)) if avg_loss != 0 else 100
    return result


def atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[Optional[float]]:
    if len(highs) != len(lows) or len(highs) != len(closes):
        return [None for _ in highs]
    trs: List[float] = []
    for i in range(len(highs)):
        if i == 0:
            trs.append(highs[i] - lows[i])
        else:
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            trs.append(tr)
    result: List[Optional[float]] = [None for _ in highs]
    if len(trs) < period:
        return result
    atr_prev = sum(trs[:period]) / period
    result[period - 1] = atr_prev
    for i in range(period, len(trs)):
        atr_prev = (atr_prev * (period - 1) + trs[i]) / period
        result[i] = atr_prev
    return result


def macd(
    values: List[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Dict[str, List[Optional[float]]]:
    fast_ema = ema(values, fast)
    slow_ema = ema(values, slow)
    macd_line: List[Optional[float]] = [None for _ in values]
    for i in range(len(values)):
        if fast_ema[i] is None or slow_ema[i] is None:
            macd_line[i] = None
        else:
            macd_line[i] = fast_ema[i] - slow_ema[i]
    signal_line = ema([v or 0 for v in macd_line], signal)
    hist: List[Optional[float]] = [None for _ in values]
    for i in range(len(values)):
        if macd_line[i] is None or signal_line[i] is None:
            hist[i] = None
        else:
            hist[i] = macd_line[i] - signal_line[i]
    return {
        'macd': macd_line,
        'signal': signal_line,
        'hist': hist,
    }


def pivot_points(highs: List[float], lows: List[float], closes: List[float]) -> List[Optional[Dict[str, float]]]:
    if len(highs) != len(lows) or len(highs) != len(closes):
        return [None for _ in highs]
    result: List[Optional[Dict[str, float]]] = [None for _ in highs]
    for i in range(1, len(highs)):
        h = highs[i - 1]
        l = lows[i - 1]
        c = closes[i - 1]
        p = (h + l + c) / 3
        r1 = 2 * p - l
        s1 = 2 * p - h
        r2 = p + (h - l)
        s2 = p - (h - l)
        r3 = h + 2 * (p - l)
        s3 = l - 2 * (h - p)
        result[i] = {
            'p': p,
            'r1': r1,
            'r2': r2,
            'r3': r3,
            's1': s1,
            's2': s2,
            's3': s3,
        }
    return result


def detect_pivots(
    highs: List[float],
    lows: List[float],
    left: int = 2,
    right: int = 2,
) -> List[Dict[str, object]]:
    pivots: List[Dict[str, object]] = []
    if len(highs) != len(lows):
        return pivots
    total = len(highs)
    for i in range(left, total - right):
        high_window = highs[i - left:i + right + 1]
        low_window = lows[i - left:i + right + 1]
        high = highs[i]
        low = lows[i]
        if high == max(high_window):
            pivots.append({'index': i, 'type': 'HIGH', 'price': high})
        if low == min(low_window):
            pivots.append({'index': i, 'type': 'LOW', 'price': low})
    return pivots


def fib_retracement(low: float, high: float) -> Dict[str, float]:
    levels = {
        '0.236': high - (high - low) * 0.236,
        '0.382': high - (high - low) * 0.382,
        '0.5': high - (high - low) * 0.5,
        '0.618': high - (high - low) * 0.618,
        '0.786': high - (high - low) * 0.786,
    }
    return levels
