from batch.common.math_indicators import atr, ema, macd, pivot_points, rsi


def test_ema_length():
    values = [1, 2, 3, 4, 5, 6, 7]
    result = ema(values, 3)
    assert len(result) == len(values)
    assert result[1] is None
    assert result[2] is not None


def test_rsi_constant():
    values = [100] * 20
    result = rsi(values, 14)
    assert result[-1] == 100


def test_atr_length():
    highs = [10, 11, 12, 13, 14]
    lows = [9, 9.5, 10, 11, 12]
    closes = [9.5, 10.5, 11, 12, 13]
    result = atr(highs, lows, closes, 3)
    assert len(result) == len(highs)


def test_macd_shapes():
    values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    result = macd(values)
    assert len(result['macd']) == len(values)
    assert len(result['signal']) == len(values)
    assert len(result['hist']) == len(values)


def test_pivot_points():
    highs = [10, 11, 12]
    lows = [9, 9.5, 10]
    closes = [9.5, 10.5, 11]
    pivots = pivot_points(highs, lows, closes)
    assert pivots[0] is None
    assert pivots[1] is not None
