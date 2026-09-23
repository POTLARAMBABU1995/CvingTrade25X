from batch.common.pattern_rules import (
    detect_breakout_from_consolidation,
    detect_double_bottom,
    detect_zones,
)


def test_breakout_from_consolidation():
    n = 25
    dates = list(range(n))
    highs = [102] * 20 + [103, 104, 106, 108, 110]
    lows = [100] * 20 + [101, 101, 103, 104, 105]
    closes = [101] * 20 + [102, 103, 105, 107, 112]
    volumes = [100] * 24 + [300]
    atr_values = [1.0] * n
    patterns = detect_breakout_from_consolidation(dates, highs, lows, closes, volumes, atr_values)
    assert patterns


def test_double_bottom():
    dates = list(range(20))
    highs = [105] * 20
    lows = [95, 92, 90, 92, 95, 97, 93, 90, 92, 95, 100, 103, 105, 106, 107, 108, 109, 110, 111, 112]
    closes = [100] * 20
    volumes = [100] * 19 + [200]
    patterns = detect_double_bottom(dates, highs, lows, closes, volumes)
    assert patterns


def test_detect_zones():
    dates = list(range(15))
    highs = [100, 101, 100, 99, 100, 101, 100, 100, 102, 104, 106, 107, 108, 110, 112]
    lows = [98, 98, 98, 97, 98, 98, 98, 98, 99, 100, 102, 104, 105, 107, 109]
    closes = [99, 100, 99, 98, 99, 100, 99, 99, 101, 103, 105, 106, 107, 109, 111]
    volumes = [100] * 15
    atr_values = [1.0] * 15
    zones = detect_zones(dates, highs, lows, closes, volumes, atr_values)
    assert zones
