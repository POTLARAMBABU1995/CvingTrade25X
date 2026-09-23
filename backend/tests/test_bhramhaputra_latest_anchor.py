from datetime import datetime
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import services.bhramhaputra_service as service


def test_bhramhaputra_uses_latest_anchor(monkeypatch):
    captured = {}

    def fake_fetch(months=None, cutoff_anchor="current"):
        captured["months"] = months
        captured["cutoff_anchor"] = cutoff_anchor
        return {}

    monkeypatch.setattr(service, "fetch_ohlc_series_from_oracle", fake_fetch)
    monkeypatch.setattr(service, "build_sr_levels_payload", lambda *_args, **_kwargs: {"rows": []})
    monkeypatch.setattr(service, "get_all_time_high_for_symbols", lambda *_args, **_kwargs: {})

    payload = service.compute_bhramhaputra_payload(timeframe="daily")

    assert captured["cutoff_anchor"] == "current"
    assert payload["meta"]["cutoffMonths"] >= 1


def test_cutoff_date_iso_latest_anchored(monkeypatch):
    latest_trade_date = datetime(2024, 1, 31)
    sample_series = {
        "TEST": [
            {
                "date": latest_trade_date,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 12345.0,
            }
        ]
    }

    monkeypatch.setattr(service, "CUTOFF_MONTHS", 24)
    monkeypatch.setattr(service, "fetch_ohlc_series_from_oracle", lambda **_kwargs: sample_series)
    monkeypatch.setattr(service, "build_sr_levels_payload", lambda *_args, **_kwargs: {"rows": []})
    monkeypatch.setattr(service, "get_all_time_high_for_symbols", lambda *_args, **_kwargs: {})

    payload = service.compute_bhramhaputra_payload(timeframe="daily")

    expected_cutoff = service._cutoff_date_iso(24)
    assert payload["cutoffDateIso"] == expected_cutoff
    assert payload["meta"]["cutoffDateIso"] == expected_cutoff
    assert payload["meta"]["endDate"] == "2024-01-31"


def test_manual_sr_display_formats_ranked_levels(monkeypatch):
    candles = [
        service.Candle(
            date=datetime(2026, 5, 30),
            open=100.0,
            high=105.0,
            low=99.0,
            close=102.0,
            volume=1000.0,
        )
    ]
    monkeypatch.setattr(
        service,
        "select_ranked_support_levels",
        lambda *_args, **_kwargs: [{"level": 123.0}, {"level": 143.0}, {"level": 122.0}],
    )
    monkeypatch.setattr(
        service,
        "select_ranked_resistance_levels",
        lambda *_args, **_kwargs: [{"level": 456.0}, {"level": 789.0}, {"level": 999.0}],
    )

    payload = service._resolve_manual_sr_display("TEST", 102.0, candles, {"levels": [122.0, 123.0, 143.0, 456.0, 789.0, 999.0]})

    assert payload["supportDisplay"] == "S1: 123, S2: 143, S3: 122"
    assert payload["resistanceDisplay"] == "R1: 456, R2: 789, R3: 999"


def test_manual_sr_display_uses_missing_message_without_manual_levels():
    payload = service._resolve_manual_sr_display("TEST", 102.0, [], None)

    assert payload["supportDisplay"] == service.NO_SR_LEVELS_TEXT
    assert payload["resistanceDisplay"] == service.NO_SR_LEVELS_TEXT


def test_backfill_manual_sr_display_rows_uses_selected_symbols(monkeypatch):
    captured = {}

    def fake_fetch(months=None, cutoff_anchor="current", symbols=None):
        captured["months"] = months
        captured["cutoff_anchor"] = cutoff_anchor
        captured["symbols"] = list(symbols or [])
        return {
            "ZEEL": [{
                "date": datetime(2026, 5, 30),
                "open": 100.0,
                "high": 105.0,
                "low": 99.0,
                "close": 102.0,
                "volume": 1000.0,
            }]
        }

    monkeypatch.setattr(service, "fetch_ohlc_series_from_oracle", fake_fetch)
    monkeypatch.setattr(
        service,
        "fetch_manual_sr_level_map",
        lambda symbols=None: {"ZEEL": {"levels": [88.0, 90.0, 92.0, 110.0, 120.0, 130.0]}},
    )
    monkeypatch.setattr(
        service,
        "select_ranked_support_levels",
        lambda *_args, **_kwargs: [{"level": 92.0}, {"level": 90.0}, {"level": 88.0}],
    )
    monkeypatch.setattr(
        service,
        "select_ranked_resistance_levels",
        lambda *_args, **_kwargs: [{"level": 110.0}, {"level": 120.0}, {"level": 130.0}],
    )

    rows = service.backfill_manual_sr_display_rows([{"symbol": "ZEEL", "price": 102.0}], timeframe="daily")

    assert captured["cutoff_anchor"] == "current"
    assert captured["symbols"] == ["ZEEL"]
    assert rows[0]["supportDisplay"] == "S1: 92, S2: 90, S3: 88"
    assert rows[0]["resistanceDisplay"] == "R1: 110, R2: 120, R3: 130"
