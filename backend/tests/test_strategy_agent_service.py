from datetime import date
from pathlib import Path
import importlib
import sys
import types


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _load_service_module():
    original_db = sys.modules.get('db')
    original_db_pool = sys.modules.get('db_pool')

    fake_db_pool = types.ModuleType('db_pool')

    class _DummyPool:
        def acquire(self):
            raise AssertionError('Database access is not expected in strategy agent unit tests.')

    fake_db_pool.pool = _DummyPool()

    fake_db = types.ModuleType('db')
    fake_db.fetch_ohlc_series_from_oracle = lambda *args, **kwargs: {}

    sys.modules['db_pool'] = fake_db_pool
    sys.modules['db'] = fake_db
    try:
        return importlib.import_module('services.strategy_agent_service')
    finally:
        if original_db_pool is not None:
            sys.modules['db_pool'] = original_db_pool
        else:
            sys.modules.pop('db_pool', None)
        if original_db is not None:
            sys.modules['db'] = original_db
        else:
            sys.modules.pop('db', None)


service = _load_service_module()


def _build_params():
    return {
        'stop_mode': 'PCT',
        'stop_pct': 0.05,
        'target1_rr': 2.0,
        'target2_rr': 3.0,
        'max_holding_days': 10,
    }


def test_simulate_trade_hits_target2_after_target1():
    signal = service.TradeSignal(
        strategy_name='asura',
        source_name='ASURA',
        symbol='ITC',
        direction='LONG',
        entry_date=date(2026, 1, 1),
        entry_price=100.0,
    )
    bars = [
        service.DailyBar(date(2026, 1, 2), 100.0, 111.0, 99.0, 110.0, 1000.0),
        service.DailyBar(date(2026, 1, 3), 112.0, 116.0, 111.0, 115.0, 1200.0),
    ]

    result = service.simulate_trade(signal, bars, _build_params(), atr_lookup={}, volume_ratio_lookup={})

    assert result is not None
    assert result['exit_reason'] == 'TARGET2_HIT'
    assert result['success_flag'] == 1
    assert result['fail_flag'] == 0
    assert result['days_to_t1'] == 1
    assert result['days_to_t2'] == 2


def test_simulate_trade_trails_after_target1_lock():
    signal = service.TradeSignal(
        strategy_name='yamuna',
        source_name='VOLUME',
        symbol='ITC',
        direction='LONG',
        entry_date=date(2026, 1, 1),
        entry_price=100.0,
    )
    bars = [
        service.DailyBar(date(2026, 1, 2), 100.0, 111.0, 99.0, 110.0, 1000.0),
        service.DailyBar(date(2026, 1, 3), 110.0, 112.0, 109.0, 110.5, 900.0),
    ]

    result = service.simulate_trade(signal, bars, _build_params(), atr_lookup={}, volume_ratio_lookup={})

    assert result is not None
    assert result['exit_reason'] == 'TRAIL_STOP_T1'
    assert result['success_flag'] == 1
    assert result['fail_flag'] == 0
    assert result['days_to_t1'] == 1
    assert result['days_to_t2'] is None


def test_summarize_backtests_counts_targets_and_locks():
    signal = service.TradeSignal(
        strategy_name='asura',
        source_name='ASURA',
        symbol='ITC',
        direction='LONG',
        entry_date=date(2026, 1, 1),
        entry_price=100.0,
    )
    params = _build_params()
    result_target2 = service.simulate_trade(
        signal,
        [
            service.DailyBar(date(2026, 1, 2), 100.0, 111.0, 99.0, 110.0, 1000.0),
            service.DailyBar(date(2026, 1, 3), 112.0, 116.0, 111.0, 115.0, 1200.0),
        ],
        params,
        atr_lookup={},
        volume_ratio_lookup={},
    )
    result_lock = service.simulate_trade(
        signal,
        [
            service.DailyBar(date(2026, 1, 2), 100.0, 111.0, 99.0, 110.0, 1000.0),
            service.DailyBar(date(2026, 1, 3), 110.0, 112.0, 109.0, 110.5, 900.0),
        ],
        params,
        atr_lookup={},
        volume_ratio_lookup={},
    )

    summary = service.summarize_backtests([result_target2, result_lock])

    assert summary['total_trades'] == 2
    assert summary['target2_hits'] == 1
    assert summary['target1_locks'] == 1
    assert summary['success_rate'] == 100.0


def test_backtest_nifty50_keeps_requested_fixed_params():
    params = dict(service.DEFAULT_STRATEGY_PARAMS['backtestnifty50'])

    candidates = service._generate_candidate_param_sets('backtestnifty50', params)

    assert len(candidates) == 1
    assert candidates[0]['stop_pct'] == 0.05
    assert candidates[0]['atr_buffer_mult'] == 1.0
    assert candidates[0]['target1_rr'] == 2.0
    assert candidates[0]['target2_rr'] == 3.0




def test_backtest_nifty50_builds_long_signals_from_rule_stack():
    params = dict(service.DEFAULT_STRATEGY_PARAMS['backtestnifty50'])
    bars = []
    atr_lookup = {'RELIANCE': {}}
    close_price = 100.0

    for offset in range(80):
        trade_day = date(2000, 1, 1).toordinal() + offset
        trade_date = date.fromordinal(trade_day)
        close_price += 1.2
        bars.append(service.DailyBar(trade_date, close_price - 0.8, close_price + 1.5, close_price - 1.0, close_price, 1000000 + offset))
        atr_lookup['RELIANCE'][trade_date] = 2.5

    signals = service._build_backtestnifty50_signals({'RELIANCE': bars}, params, atr_lookup)

    assert signals
    assert signals[0].strategy_name == 'backtestnifty50'
    assert signals[0].source_name == 'BACKTESTNIFTY50'
    assert signals[0].entry_price > 0


def test_backtest_nifty50_v2_generates_candidate_grid():
    params = dict(service.DEFAULT_STRATEGY_PARAMS['backtestnifty50v2'])

    candidates = service._generate_candidate_param_sets('backtestnifty50v2', params)

    assert len(candidates) > 1
    assert any(candidate['adx_threshold'] == 30.0 for candidate in candidates)
    assert any(candidate['breakout_lookback'] == 20 for candidate in candidates)
    assert any(candidate['rsi_threshold'] == 58.0 for candidate in candidates)


def test_backtest_nifty50_v2_builds_structural_breakout_signals():
    params = dict(service.DEFAULT_STRATEGY_PARAMS['backtestnifty50v2'])
    bars = []
    atr_lookup = {'RELIANCE': {}}
    close_price = 100.0

    for offset in range(90):
        trade_day = date(2001, 1, 1).toordinal() + offset
        trade_date = date.fromordinal(trade_day)
        if offset < 70:
            close_price += 0.9
            open_price = close_price - 0.3
            high_price = close_price + 1.1
            low_price = close_price - 0.8
        else:
            close_price += 1.7
            open_price = close_price - 1.0
            high_price = close_price + 0.05
            low_price = open_price - 0.20
        bars.append(service.DailyBar(trade_date, open_price, high_price, low_price, close_price, 1500000 + offset * 1000))
        atr_lookup['RELIANCE'][trade_date] = 2.0

    signals = service._build_backtestnifty50_v2_signals({'RELIANCE': bars}, params, atr_lookup)

    assert signals
    assert signals[0].strategy_name == 'backtestnifty50v2'
    assert signals[0].source_name == 'BACKTESTNIFTY50V2'
    assert signals[0].breakout_flag == 'STRUCTURE_BREAKOUT'


def test_normalize_run_source_for_storage_truncates_long_values():
    value = service._normalize_run_source_for_storage('bhramhastra_auto_insert')

    assert value == 'bhramhastra_auto_ins'
    assert len(value) == 20
