from datetime import datetime, timedelta
import importlib
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import sr_levels as service

sr_route = importlib.import_module('routes.sr')


def _build_candles(days: int, *, start_price: float = 100.0, volatility: float = 1.0, volume_base: float = 1000.0):
    candles = []
    current = start_price
    started = datetime(2025, 1, 1)
    for idx in range(days):
        move = volatility if idx % 2 == 0 else -(volatility * 0.7)
        open_price = current
        close_price = max(1.0, current + move)
        high_price = max(open_price, close_price) + (volatility * 0.4)
        low_price = min(open_price, close_price) - (volatility * 0.4)
        candles.append({
            'date': started + timedelta(days=idx),
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'close': close_price,
            'volume': volume_base + (idx * 10),
        })
        current = close_price
    return candles


def test_estimate_dynamic_lookback_expands_for_higher_volatility():
    low_vol = _build_candles(220, volatility=0.6)
    high_vol = _build_candles(220, volatility=4.0)

    low_lookback = service._estimate_dynamic_lookback(low_vol)
    high_lookback = service._estimate_dynamic_lookback(high_vol)

    assert high_lookback >= low_lookback
    assert low_lookback <= len(low_vol)
    assert high_lookback <= len(high_vol)


def test_detect_price_action_breakout_uses_resistance_and_volume():
    candles = [
        {'date': datetime(2026, 3, 1), 'open': 96.0, 'high': 98.0, 'low': 95.5, 'close': 97.5, 'volume': 1000.0},
        {'date': datetime(2026, 3, 2), 'open': 97.0, 'high': 99.0, 'low': 96.5, 'close': 98.5, 'volume': 1100.0},
        {'date': datetime(2026, 3, 3), 'open': 98.0, 'high': 100.5, 'low': 97.8, 'close': 99.5, 'volume': 1150.0},
        {'date': datetime(2026, 3, 4), 'open': 99.4, 'high': 104.5, 'low': 99.0, 'close': 103.8, 'volume': 2200.0},
    ]
    supports = [{'label': 'S1', 'type': 'support', 'price': 95.0, 'touchesTotal': 5, 'lastTouch': '2026-03-02T00:00:00'}]
    resistances = [{'label': 'R1', 'type': 'resistance', 'price': 100.0, 'touchesTotal': 4, 'lastTouch': '2026-03-03T00:00:00'}]
    trend_context = {
        'direction': 'Uptrend',
        'atrPct': 1.1,
        'nearestLevel': {'label': 'R1', 'type': 'resistance', 'price': 100.0, 'distancePct': 0.4, 'lastTouch': '2026-03-03T00:00:00'},
    }

    action = service._detect_price_action(candles, 103.8, supports, resistances, trend_context)

    assert action['state'] == 'breakout'
    assert action['bias'] == 'bullish'
    assert action['volumeSpike'] is True


def test_compute_score_returns_breakdown_with_expected_components():
    now_touch = datetime.utcnow().replace(microsecond=0).isoformat()
    supports = [{'label': 'S1', 'type': 'support', 'price': 98.0, 'touchesTotal': 5, 'lastTouch': now_touch}]
    resistances = [{'label': 'R1', 'type': 'resistance', 'price': 102.0, 'touchesTotal': 4, 'lastTouch': now_touch}]
    trend_context = {
        'direction': 'Uptrend',
        'strength': 27.5,
        'atrPct': 1.2,
        'nearestLevel': {'label': 'R1', 'type': 'resistance', 'price': 102.0, 'distancePct': 0.8, 'lastTouch': now_touch},
    }
    momentum = {'score': 3}
    price_action = {'state': 'breakout', 'volumeRatio': 1.45}

    score, breakdown = service._compute_score(
        price=102.8,
        support_levels=supports,
        resistance_levels=resistances,
        touch_counts=(5, 4),
        momentum=momentum,
        trend_context=trend_context,
        price_action=price_action,
    )

    assert 0 <= score <= 100
    assert breakdown['total'] == score
    assert set(['touches', 'proximity', 'recency', 'trend', 'momentum', 'volume', 'priceAction']).issubset(breakdown.keys())


def test_build_sr_levels_payload_filters_by_price_action_state(monkeypatch):
    candles = _build_candles(120)
    ohlc_series = {'AAA': candles, 'BBB': candles}

    def fake_build_symbol_row(symbol, *_args, **_kwargs):
        state = 'breakout' if symbol == 'AAA' else 'range'
        return {
            'symbol': symbol,
            'priceAction': {'state': state, 'label': state.title()},
        }

    monkeypatch.setattr(service, '_build_symbol_row', fake_build_symbol_row)

    payload = service.build_sr_levels_payload(
        ohlc_series,
        [],
        0.05,
        'daily',
        price_action_filter='breakout',
    )

    assert [row['symbol'] for row in payload['rows']] == ['AAA']
    assert payload['priceActionFilter'] == 'breakout'


def test_build_symbol_row_caps_trading_days_at_504():
    candles = _build_candles(620, start_price=150.0, volatility=2.0)

    row = service._build_symbol_row(
        'AAA',
        candles,
        None,
        0.05,
        ['AAA'],
        'daily',
        lookback_days=900,
        min_touches=1,
    )

    assert row is not None
    assert row['tradingDays'] == 504
    assert row['tradingDaysSort'] == 504
    assert row['lookbackDays'] == 504


def test_build_symbol_row_max_lookback_uses_full_history():
    candles = _build_candles(620, start_price=150.0, volatility=2.0)

    row = service._build_symbol_row(
        'AAA',
        candles,
        None,
        0.05,
        ['AAA'],
        'daily',
        lookback_days='max',
        min_touches=1,
    )

    assert row is not None
    assert row['tradingDays'] == 620
    assert row['tradingDaysSort'] == 620
    assert row['lookbackDays'] == 620
    assert row['lookbackMode'] == 'max'


def test_parse_lookback_days_accepts_max_token():
    assert sr_route._parse_lookback_days('MAX') == 'max'
    assert sr_route._fetch_month_span('max') is None


def test_manual_levels_are_merged_first_and_deduped():
    candles = _build_candles(180, start_price=100.0, volatility=1.2)
    manual_levels = {
        'AAA': {
            'daily': [
                {'level_type': 'SR', 'price': 98.95, 'updated_at': '2026-04-01T00:00:00'},
                {'level_type': 'RESISTANCE', 'price': 102.10, 'updated_at': '2026-04-01T00:00:00'},
                {'level_type': 'SR', 'price': 105.00, 'updated_at': '2026-04-02T00:00:00'},
            ]
        }
    }

    payload = service.build_sr_levels_payload(
        {'AAA': candles},
        [],
        0.05,
        'daily',
        lookback_days=180,
        manual_levels_by_symbol=manual_levels,
    )

    row = payload['rows'][0]
    support_levels = row['supportLevels']
    resistance_levels = row['resistanceLevels']

    assert support_levels[0]['manual'] is True
    assert support_levels[0]['source'] == 'manual'
    assert support_levels[0]['price'] == 105.0
    assert support_levels[1]['price'] == 98.95
    assert resistance_levels[0]['manual'] is True
    assert resistance_levels[0]['source'] == 'manual'
    assert resistance_levels[0]['price'] == 102.1
    assert len([level for level in support_levels if abs(level['price'] - 98.95) < 1e-9]) == 1


def test_strongest_level_uses_combined_manual_and_generated_evidence():
    merged = service._merge_prioritized_levels(
        [
            {
                'price': 100.4,
                'touchesSupport': 3,
                'touchesResistance': 0,
                'touchesTotal': 3,
                'breaches': 0,
                'source': 'generated',
            },
            {
                'price': 90.0,
                'touchesSupport': 5,
                'touchesResistance': 0,
                'touchesTotal': 5,
                'breaches': 1,
                'source': 'generated',
            },
        ],
        [{'level_type': 'SUPPORT', 'price': 100.0}],
        110.0,
        'support',
        'daily',
    )

    combined = next(level for level in merged if level['manual'])
    strongest = service._strongest_level(merged, 110.0)

    assert combined['source'] == 'manual'
    assert combined['confluence'] is True
    assert combined['touchesTotal'] == 3
    assert strongest is not None
    assert strongest['price'] == 90.0
    assert strongest['touchesTotal'] == 5


def test_manual_level_strength_is_measured_against_ohlcv():
    candles = [
        {'date': datetime(2026, 1, 1), 'low': 100.0, 'high': 111.0, 'close': 108.0},
        {'date': datetime(2026, 1, 2), 'low': 101.0, 'high': 112.0, 'close': 109.0},
        {'date': datetime(2026, 1, 3), 'low': 99.0, 'high': 110.0, 'close': 107.0},
    ]
    merged = service._merge_prioritized_levels(
        [{'price': 80.0, 'touchesTotal': 2, 'breaches': 0, 'source': 'generated'}],
        [{'level_type': 'SUPPORT', 'price': 100.0}],
        108.0,
        'support',
        'daily',
        candles=candles,
        tolerance_pct=0.05,
    )

    manual = next(level for level in merged if level['manual'])
    strongest = service._strongest_level(merged, 108.0)

    assert manual['touchesTotal'] == 3
    assert manual['firstTouch'] == '2026-01-01T00:00:00'
    assert strongest is not None
    assert strongest['price'] == 100.0


def test_normalize_trend_direction_filter_accepts_expected_aliases():
    assert sr_route._normalize_trend_direction_filter('Up') == 'uptrend'
    assert sr_route._normalize_trend_direction_filter('DOWNTREND') == 'downtrend'
    assert sr_route._normalize_trend_direction_filter('Range') == 'consolidation'
    assert sr_route._normalize_trend_direction_filter('total') == 'all'


def test_apply_trend_direction_filter_keeps_only_requested_bucket():
    rows = [
        {'symbol': 'AAA', 'trendDirection': 'Uptrend'},
        {'symbol': 'BBB', 'trendDirection': 'Downtrend'},
        {'symbol': 'CCC', 'trendDirection': 'Consolidation'},
    ]

    filtered = sr_route._apply_trend_direction_filter(rows, 'downtrend')

    assert [row['symbol'] for row in filtered] == ['BBB']
    assert sr_route._apply_trend_direction_filter(rows, 'all') == rows
