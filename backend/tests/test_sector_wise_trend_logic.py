from pathlib import Path
import importlib
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

sector_rotation = importlib.import_module('routes.sector_rotation')


def _decision(**overrides):
    payload = {
        'sector_name': 'CAPITAL_GOODS',
        'symbol': 'TEST',
        'price': 100.0,
        'ath': 110.0,
        'high52w': 108.0,
        'low52w': 70.0,
        'gap_pct': -9.09,
        'ema20_flag': 'Y',
        'ema50_flag': 'Y',
        'ema100_flag': 'Y',
        'ema200_flag': 'Y',
        'support_price': 96.0,
        'resistance_price': 112.0,
        'sr_source': 'MANUAL',
        'sr_trend_direction': 'Uptrend',
    }
    payload.update(overrides)
    return sector_rotation.calculate_sector_stock_trend(**payload)


def test_aplapollo_near_ath_with_bullish_ema_is_not_downtrend():
    decision = _decision(
        symbol='APLAPOLLO',
        price=2198.0,
        ath=2207.10,
        high52w=2207.10,
        low52w=1375.0,
        gap_pct=-0.41,
        ema20_flag='Y',
        ema50_flag='Y',
        ema100_flag='Y',
        ema200_flag='Y',
        resistance_price=2207.10,
        support_price=2145.0,
    )
    assert decision['trend'] in {'Uptrend', 'Strong Uptrend'}


def test_jswsteel_near_ath_with_bullish_ema_is_not_downtrend():
    decision = _decision(
        symbol='JSWSTEEL',
        price=1236.20,
        ath=1245.0,
        high52w=1245.0,
        low52w=760.0,
        gap_pct=-0.71,
        ema20_flag='Y',
        ema50_flag='Y',
        ema100_flag='Y',
        ema200_flag='Y',
        resistance_price=1245.0,
        support_price=1210.0,
    )
    assert decision['trend'] in {'Uptrend', 'Strong Uptrend'}


def test_jindalstel_near_ath_with_bullish_ema_is_not_downtrend():
    decision = _decision(
        symbol='JINDALSTEL',
        price=1189.90,
        ath=1191.70,
        high52w=1191.70,
        low52w=640.0,
        gap_pct=-0.15,
        ema20_flag='Y',
        ema50_flag='Y',
        ema100_flag='Y',
        ema200_flag='Y',
        resistance_price=1191.70,
        support_price=1160.0,
    )
    assert decision['trend'] in {'Uptrend', 'Strong Uptrend'}


def test_hindalco_bullish_ema_far_below_ath_is_not_forced_downtrend():
    decision = _decision(
        symbol='HINDALCO',
        price=942.55,
        ath=1029.80,
        high52w=1029.80,
        low52w=512.0,
        gap_pct=-8.47,
        ema20_flag='Y',
        ema50_flag='Y',
        ema100_flag='Y',
        ema200_flag='Y',
        resistance_price=975.0,
        support_price=915.0,
    )
    assert decision['trend'] in {'Uptrend', 'Consolidation', 'Pullback in Uptrend'}


def test_near_52wl_with_bearish_ema_is_downtrend():
    decision = _decision(
        symbol='LOWCASE',
        price=73.0,
        ath=180.0,
        high52w=170.0,
        low52w=70.0,
        gap_pct=-57.0,
        ema20_flag='N',
        ema50_flag='N',
        ema100_flag='N',
        ema200_flag='N',
        support_price=72.5,
        resistance_price=82.0,
        sr_trend_direction='Downtrend',
    )
    assert decision['trend'] == 'Downtrend'


def test_near_52wl_bounce_with_mixed_ema_is_possible_reversal():
    decision = _decision(
        symbol='REVERSAL',
        price=73.2,
        ath=175.0,
        high52w=168.0,
        low52w=70.0,
        gap_pct=-58.17,
        ema20_flag='Y',
        ema50_flag='N',
        ema100_flag='Y',
        ema200_flag='N',
        support_price=73.0,
        resistance_price=80.0,
        sr_trend_direction='Consolidation',
    )
    assert decision['trend'] == 'Possible Reversal'


def test_between_support_and_resistance_with_mixed_ema_is_sideways():
    decision = _decision(
        symbol='RANGEBOUND',
        price=100.0,
        ath=130.0,
        high52w=126.0,
        low52w=82.0,
        ema20_flag='Y',
        ema50_flag='N',
        ema100_flag='Y',
        ema200_flag='N',
        support_price=96.0,
        resistance_price=104.0,
        sr_trend_direction='Consolidation',
    )
    assert decision['trend'] == 'Sideways'


def test_breakout_above_resistance_with_bullish_ema_is_uptrend():
    decision = _decision(
        symbol='BREAKOUT',
        price=118.0,
        ath=130.0,
        high52w=128.0,
        low52w=80.0,
        ema20_flag='Y',
        ema50_flag='Y',
        ema100_flag='Y',
        ema200_flag='N',
        support_price=110.0,
        resistance_price=116.0,
    )
    assert decision['trend'] == 'Uptrend'


def test_breakdown_below_support_with_bearish_ema_is_downtrend():
    decision = _decision(
        symbol='BREAKDOWN',
        price=88.0,
        ath=140.0,
        high52w=132.0,
        low52w=75.0,
        ema20_flag='N',
        ema50_flag='N',
        ema100_flag='N',
        ema200_flag='Y',
        support_price=90.0,
        resistance_price=101.0,
        sr_trend_direction='Downtrend',
    )
    assert decision['trend'] == 'Downtrend'


def test_missing_price_returns_unknown():
    decision = _decision(price=None, ath=None, high52w=None, low52w=None)
    assert decision['trend'] == 'Unknown / Insufficient Data'

