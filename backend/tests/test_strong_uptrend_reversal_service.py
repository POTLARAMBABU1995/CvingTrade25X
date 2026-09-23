from datetime import date, timedelta
from pathlib import Path
import sys
import types


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

db_pool_stub = types.ModuleType('db_pool')
db_pool_stub.pool = None
db_pool_stub.fetchall_dict = lambda _cur: []
sys.modules['db_pool'] = db_pool_stub

cache_stub = types.ModuleType('cache')


class _DummyTTLCache:
    def __init__(self, *args, **kwargs):
        self._store = {}

    def get(self, key):
        return self._store.get(key)

    def set(self, key, value):
        self._store[key] = value


cache_stub.TTLCache = _DummyTTLCache
sys.modules['cache'] = cache_stub

import services.strong_uptrend_reversal_service as service
sys.modules.pop('cache', None)


def _build_candles():
    start = date(2026, 3, 16)
    candles = []
    for index in range(60):
        trading_date = start + timedelta(days=index)
        base = 96 + index * 0.45
        candles.append({
            'date': trading_date,
            'open': round(base - 0.8, 2),
            'high': round(base + 1.0, 2),
            'low': round(base - 1.2, 2),
            'close': round(base + 0.2, 2),
            'volume': 1200 + index * 5,
        })
    candles[-2].update({'open': 121.0, 'high': 121.4, 'low': 119.1, 'close': 119.8, 'volume': 1400})
    candles[-1].update({'open': 120.2, 'high': 124.0, 'low': 119.2, 'close': 123.0, 'volume': 2200})
    return candles


def _patch_positive_indicators(monkeypatch, *, bullish_reversal=True):
    monkeypatch.setattr(
        service,
        'calculate_ema',
        lambda values, period: {20: 120.0, 50: 112.0, 100: 101.0, 200: 92.0}[period] - (1.0 if len(values) < 60 else 0.0),
    )
    monkeypatch.setattr(service, '_rsi_series', lambda values, period=14: [None] * (len(values) - 1) + [61.8])
    monkeypatch.setattr(
        service,
        '_macd_series',
        lambda values: {
            'macd': [0.0] * (len(values) - 1) + [22.45],
            'signal': [0.0] * len(values),
            'hist': [0.0] * (len(values) - 2) + [3.2, 4.6],
        },
    )
    monkeypatch.setattr(
        service,
        '_adx_series',
        lambda candles, period=14: {
            'adx': [None] * (len(candles) - 1) + [29.4],
            'plus_di': [None] * (len(candles) - 1) + [31.2],
            'minus_di': [None] * (len(candles) - 1) + [16.9],
            'atr': [None] * (len(candles) - 1) + [20.0],
        },
    )
    monkeypatch.setattr(service, '_volume_sma20', lambda candles: 1000.0)
    monkeypatch.setattr(service, 'detect_swing_pivots', lambda candles, **kwargs: [{'kind': 'high', 'price': 121.0}, {'kind': 'low', 'price': 118.0}])
    monkeypatch.setattr(
        service,
        'detect_higher_high_higher_low',
        lambda pivots: {
            'higherHigh': True,
            'higherLow': True,
            'previousHigh': {'price': 121.0},
            'latestLow': {'price': 118.0},
        },
    )
    monkeypatch.setattr(
        service,
        'calculate_support_resistance',
        lambda candles, pivots: {
            'nearestSupport': 120.0,
            'nearestResistance': 121.0,
            'resistanceLevels': [130.0, 140.0],
        },
    )
    monkeypatch.setattr(service, 'detect_resistance_breakout', lambda candles, **kwargs: {'confirmed': True})
    monkeypatch.setattr(service, '_is_bullish_reversal_candle', lambda candles: bullish_reversal)


def test_evaluate_symbol_missing_delivery_is_safe(monkeypatch):
    _patch_positive_indicators(monkeypatch)

    row = service._evaluate_symbol('RELIANCE', _build_candles(), '2026-05-14', None)

    assert row is not None
    assert row['DELIVERY_PCT'] is None
    assert row['SIGNAL'] == 'STRONG_BUY_SETUP'
    assert row['SCORE'] == 90
    assert row['ENTRY_TRIGGER'] is True


def test_evaluate_symbol_disables_entry_trigger_when_bullish_candle_missing(monkeypatch):
    _patch_positive_indicators(monkeypatch, bullish_reversal=False)

    row = service._evaluate_symbol('TCS', _build_candles(), '2026-05-14', {'delivery_pct': 47.8})

    assert row is not None
    assert row['SCORE'] == 95
    assert row['SIGNAL'] == 'STRONG_BUY_SETUP'
    assert row['ENTRY_TRIGGER'] is False
    assert 'Bullish reversal candle missing' in row['REJECT_REASON']


def test_fetch_scan_returns_success_shape(monkeypatch):
    monkeypatch.setattr(service, '_CACHE', _DummyTTLCache())
    monkeypatch.setattr(service, '_fetch_latest_trade_date', lambda: '2026-05-14')
    monkeypatch.setattr(service, 'fetch_recent_ohlc_series_from_oracle', lambda trading_days=504: {'RELIANCE': _build_candles()})
    monkeypatch.setattr(service, 'aggregate_ohlc_series_by_timeframe', lambda rows, timeframe='daily': rows)
    monkeypatch.setattr(service, '_fetch_latest_delivery_pct_map', lambda symbols: {'RELIANCE': {'delivery_pct': 47.8}})
    monkeypatch.setattr(
        service,
        '_evaluate_symbol',
        lambda symbol, candles, latest_trade_date, delivery_row: {
            'SYMBOL': symbol,
            'TRADING_DATE': latest_trade_date,
            'CLOSE': 2948.65,
            'EMA20': 2876.2,
            'EMA50': 2764.8,
            'EMA100': 2641.4,
            'EMA200': 2508.75,
            'RSI14': 61.8,
            'MACD': 22.45,
            'MACD_HIST': 4.6,
            'ADX14': 29.4,
            'PLUS_DI': 31.2,
            'MINUS_DI': 16.9,
            'VOLUME': 7854200,
            'VOLUME_SMA20': 6123000,
            'DELIVERY_PCT': 47.8,
            'HH_HL_STRUCTURE': True,
            'SUPPORT_CONFIRMED': True,
            'BULLISH_REVERSAL_CANDLE': True,
            'BREAKOUT_OK': True,
            'SCORE': 90,
            'SIGNAL': 'STRONG_BUY_SETUP',
            'ENTRY_TRIGGER': True,
            'ENTRY_PRICE': 2951.6,
            'STOP_LOSS': 2844.2,
            'TARGET_1': 3025.0,
            'TARGET_2': 3166.4,
            'REJECT_REASON': '',
        },
    )

    payload = service.fetch_strong_uptrend_reversal_scan(refresh=True)

    assert payload['status'] == 'SUCCESS'
    assert payload['data'][0]['SYMBOL'] == 'RELIANCE'
    assert payload['meta']['tradingDate'] == '2026-05-14'
    assert payload['meta']['rows'] == 1
    assert payload['meta']['cacheState'] == 'MISS'
