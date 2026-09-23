from datetime import datetime, timedelta
from pathlib import Path
import sys
import types


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

db_pool_stub = types.ModuleType("db_pool")
db_pool_stub.pool = None
db_pool_stub.fetchall_dict = lambda _cur: []
sys.modules["db_pool"] = db_pool_stub

import services.prudvi_strategy_service as prudvi_service


def _candles(days=60):
    start = datetime(2026, 3, 1)
    rows = []
    for index in range(days):
        close = 100 + index
        rows.append({
            "date": start + timedelta(days=index),
            "open": close - 1,
            "high": close + 2,
            "low": close - 2,
            "close": close,
            "volume": 1000 + index * 10,
        })
    rows[-6].update({"open": 170, "high": 172.5, "low": 166, "close": 168, "volume": 2100})
    rows[-5].update({"open": 168, "high": 169, "low": 162, "close": 164, "volume": 1800})
    rows[-1].update({"open": 160, "high": 161.5, "low": 156, "close": 161, "volume": 2000})
    return rows


def test_evaluate_symbol_maps_manual_sr_flags_and_score(monkeypatch):
    candles = _candles()
    latest_trade_date = candles[-1]["date"].date().isoformat()
    monkeypatch.setattr(prudvi_service, "_rsi_series", lambda _closes, _period=14: [55.0])
    monkeypatch.setattr(prudvi_service, "_macd_series", lambda _closes: {"macd": [1.25], "signal": [0.8], "hist": [0.45]})
    monkeypatch.setattr(prudvi_service, "_adx_series", lambda _candles, _period=14: {"adx": [31.0]})
    monkeypatch.setattr(prudvi_service, "_volume_sma20", lambda _candles: 1500.0)
    monkeypatch.setattr(prudvi_service, "classify_trend_structure", lambda _candles, _pivots=None: {"status": "Strong Uptrend"})
    monkeypatch.setattr(prudvi_service, "detect_swing_pivots", lambda *_args, **_kwargs: [])

    row = prudvi_service._evaluate_symbol(
        "RELIANCE",
        candles,
        {"levels": [156.0, 172.0]},
        latest_trade_date,
        {"delivery_pct": 64.5},
        {"ath": 180.0, "ath_date": "2026-05-10"},
    )

    assert row["ATH"] == 180.0
    assert row["PRICE"] == 161.0
    assert row["GAP"] == -10.56
    assert row["LTC_DATE"] == latest_trade_date
    assert row["SUPPORT"] == "156"
    assert row["RESISTANCE"] == "172"
    assert row["SUPPORT_REACTION"] == "BOUNCE"
    assert row["SUPPORT_CANDLE"] == "HAMMER"
    assert row["CANDLE_DIRECTION"] == "BULLISH"
    assert row["SUPPORT_REVERSAL"] == "Y"
    assert row["BULLISH_CANDLE"] == "Y"
    assert row["EMA_GT_20"] == "Y"
    assert row["EMA_GT_50"] == "Y"
    assert row["RSI_GT_50"] == "Y"
    assert row["ADX_GT_25"] == "Y"
    assert row["MACD_GT_0"] == "Y"
    assert row["VOLUME_GT_20"] == "Y"
    assert row["DELIVERY_GT_60"] == "Y"
    assert row["TREND"] == "UPTREND"
    assert row["TREND_SCORE"] == 100


def test_flags_and_trend_degrade_to_dash_for_missing_values():
    assert prudvi_service._flag_price_gt(None, 20) == "-"
    assert prudvi_service._flag_gt(None, 50) == "-"
    assert prudvi_service._flag_volume_gt(100, None) == "-"
    assert prudvi_service._normalize_trend("Unknown") == "-"
    assert prudvi_service._normalize_trend("Range") == "CONSOLIDATION"


def test_split_support_resistance_keeps_nearest_three_levels():
    support, resistance = prudvi_service._split_support_resistance(
        [100, 110, 120, 130, 150, 160, 170, 180, 190],
        155,
    )

    assert support == [150.0, 130.0, 120.0]
    assert resistance == [160.0, 170.0, 180.0]
    assert prudvi_service._format_levels(support, "S") == "S1 150, S2 130, S3 120"
    assert prudvi_service._format_levels(resistance, "R") == "R1 160, R2 170, R3 180"


def test_parse_manual_sr_levels_accepts_mixed_manual_text():
    levels = prudvi_service.parse_manual_sr_levels('S1: 2850, [2780|3025], {"next": 3150}, bad NSE:ABC 12%')

    assert levels == [2780.0, 2850.0, 3025.0, 3150.0]


def test_active_support_uses_historical_bounce_not_nearest_only():
    candles = [
        {"date": datetime(2026, 5, 1), "open": 200, "high": 202, "low": 179, "close": 181, "volume": 2000},
        {"date": datetime(2026, 5, 2), "open": 181, "high": 188, "low": 181, "close": 187, "volume": 2200},
        {"date": datetime(2026, 5, 3), "open": 199, "high": 202, "low": 199, "close": 200, "volume": 1000},
    ]
    active = prudvi_service.pick_active_support(
        "RELIANCE",
        200,
        [180, 195],
        candles,
        64.5,
    )

    assert active is not None
    assert active["level"] == 180.0


def test_active_resistance_uses_historical_rejection_not_nearest_only():
    candles = [
        {"date": datetime(2026, 5, 1), "open": 116, "high": 120, "low": 115, "close": 118, "volume": 2000},
        {"date": datetime(2026, 5, 2), "open": 118, "high": 119, "low": 109, "close": 110, "volume": 2200},
        {"date": datetime(2026, 5, 3), "open": 100, "high": 101, "low": 98, "close": 100, "volume": 1000},
    ]
    active = prudvi_service.pick_active_resistance(
        "RELIANCE",
        100,
        [105, 120],
        candles,
        64.5,
    )

    assert active is not None
    assert active["level"] == 120.0


def test_select_ranked_levels_keeps_strongest_first_and_fills_remaining_nearest():
    support_candles = [
        {"date": datetime(2026, 5, 1), "open": 200, "high": 202, "low": 179, "close": 181, "volume": 2000},
        {"date": datetime(2026, 5, 2), "open": 181, "high": 188, "low": 181, "close": 187, "volume": 2200},
        {"date": datetime(2026, 5, 3), "open": 199, "high": 202, "low": 199, "close": 200, "volume": 1000},
    ]
    resistance_candles = [
        {"date": datetime(2026, 5, 1), "open": 116, "high": 120, "low": 115, "close": 118, "volume": 2000},
        {"date": datetime(2026, 5, 2), "open": 118, "high": 119, "low": 109, "close": 110, "volume": 2200},
        {"date": datetime(2026, 5, 3), "open": 100, "high": 101, "low": 98, "close": 100, "volume": 1000},
    ]

    support_ranked = prudvi_service.select_ranked_support_levels(
        "RELIANCE",
        200,
        [170, 180, 195],
        support_candles,
        64.5,
        limit=3,
    )
    resistance_ranked = prudvi_service.select_ranked_resistance_levels(
        "RELIANCE",
        100,
        [105, 120, 130],
        resistance_candles,
        64.5,
        limit=3,
    )

    assert [item["level"] for item in support_ranked] == [180.0, 195.0, 170.0]
    assert [item["level"] for item in resistance_ranked] == [120.0, 105.0, 130.0]


def test_detect_candle_patterns_and_support_reactions():
    hammer = {"open": 160, "high": 161.5, "low": 156, "close": 161, "volume": 2000}
    assert prudvi_service.detect_candle_pattern(hammer, [])[0:2] == ("HAMMER", "BULLISH")

    previous = [{"open": 162, "high": 163, "low": 158, "close": 159, "volume": 1000}]
    engulfing = {"open": 158, "high": 164, "low": 157, "close": 163, "volume": 2000}
    assert prudvi_service.detect_candle_pattern(engulfing, previous)[0:2] == ("BULLISH_ENGULFING", "BULLISH")

    breakdown_rows = [
        {"open": 160, "high": 161, "low": 154, "close": 155, "volume": 2200},
        {"open": 155, "high": 156, "low": 150, "close": 152, "volume": 2300},
    ]
    assert prudvi_service.detect_support_reaction(156, breakdown_rows, 1500, 45) == ("BREAKDOWN", "N")


def test_fetch_scan_returns_current_snapshot_without_blocking_cold_build(monkeypatch):
    prudvi_service._CACHE.clear()
    refresh_calls = []
    snapshot = {
        "data": [{"S_NO": 1, "SYMBOL": "RELIANCE", "TREND_SCORE": 90}],
        "status": "success",
        "meta": {
            "cacheVersion": prudvi_service._CACHE_VERSION,
            "rows": 1,
            "tradingDate": "2026-05-15",
        },
    }

    monkeypatch.setattr(prudvi_service, "_fetch_latest_trade_date", lambda: "2026-05-15")
    monkeypatch.setattr(prudvi_service, "_load_snapshot_payload", lambda _latest_trade_date: snapshot)
    monkeypatch.setattr(prudvi_service, "_schedule_refresh", lambda *args: refresh_calls.append(args))
    monkeypatch.setattr(
        prudvi_service,
        "_build_prudvi_strategy_payload",
        lambda _latest_trade_date: (_ for _ in ()).throw(AssertionError("cold build must not block snapshot response")),
    )

    payload = prudvi_service.fetch_prudvi_strategy_scan()

    assert payload["cached"] is True
    assert payload["stale"] is True
    assert payload["meta"]["cacheState"] == "SNAPSHOT"
    assert payload["data"][0]["SYMBOL"] == "RELIANCE"
    assert refresh_calls == [(f"prudvi:{prudvi_service._CACHE_VERSION}:2026-05-15", "2026-05-15")]
    prudvi_service._CACHE.clear()


def test_fetch_scan_serves_legacy_snapshot_with_enhancement_defaults(monkeypatch):
    prudvi_service._CACHE.clear()
    refresh_calls = []
    snapshot = {
        "data": [{"S_NO": 1, "SYMBOL": "RELIANCE", "TREND_SCORE": 90}],
        "status": "success",
        "meta": {
            "cacheVersion": "v3",
            "rows": 1,
            "tradingDate": "2026-05-15",
        },
    }

    monkeypatch.setattr(prudvi_service, "_fetch_latest_trade_date", lambda: "2026-05-15")
    monkeypatch.setattr(prudvi_service, "_load_snapshot_payload", lambda _latest_trade_date: prudvi_service._with_prudvi_field_defaults(snapshot))
    monkeypatch.setattr(prudvi_service, "_schedule_refresh", lambda *args: refresh_calls.append(args))

    payload = prudvi_service.fetch_prudvi_strategy_scan()

    assert payload["data"][0]["SUPPORT_REACTION"] == "-"
    assert payload["data"][0]["SUPPORT_CANDLE"] == "-"
    assert payload["data"][0]["CANDLE_DIRECTION"] == "-"
    assert payload["data"][0]["SUPPORT_REVERSAL"] == "-"
    assert payload["meta"]["legacySnapshotUpgraded"] is True
    assert refresh_calls == [(f"prudvi:{prudvi_service._CACHE_VERSION}:2026-05-15", "2026-05-15")]
    prudvi_service._CACHE.clear()


def test_fetch_scan_cold_start_returns_refreshing_placeholder(monkeypatch):
    prudvi_service._CACHE.clear()
    refresh_calls = []

    monkeypatch.setattr(prudvi_service, "_fetch_latest_trade_date", lambda: "2026-05-15")
    monkeypatch.setattr(prudvi_service, "_load_snapshot_payload", lambda _latest_trade_date: None)
    monkeypatch.setattr(prudvi_service, "_schedule_refresh", lambda *args: refresh_calls.append(args))

    payload = prudvi_service.fetch_prudvi_strategy_scan()

    assert payload["data"] == []
    assert payload["cached"] is False
    assert payload["refreshing"] is True
    assert payload["stale"] is True
    assert payload["meta"]["cacheState"] == "COLD_START_REFRESHING"
    assert payload["meta"]["refreshScheduled"] is True
    assert refresh_calls == [(f"prudvi:{prudvi_service._CACHE_VERSION}:2026-05-15", "2026-05-15")]
    prudvi_service._CACHE.clear()
