from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import services.bhramhastra_service as service


class _FakeCursor:
    def __init__(self, conn):
        self._conn = conn
        self.description = []
        self.rowcount = 0
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, binds=None):
        text = " ".join(str(sql).split()).upper()
        if "SELECT SYMBOL, LTC_DATE, TARGET1, TARGET2, STOP_LOSS" in text:
            self.description = [("symbol",), ("ltc_date",), ("target1",), ("target2",), ("stop_loss",)]
            self._rows = []
            return
        self.description = []
        self._rows = []

    def executemany(self, sql, rows):
        self._conn.executemany_calls.append((sql, list(rows)))
        self.rowcount = len(rows)

    def fetchall(self):
        return list(self._rows)


class _FakeConn:
    def __init__(self):
        self.executemany_calls = []
        self.commits = 0

    def cursor(self):
        return _FakeCursor(self)

    def commit(self):
        self.commits += 1


class _FakeAcquire:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _FakeAcquire(self._conn)


def test_compute_scan_emits_display_only_indicator_fields(monkeypatch):
    start = datetime(2026, 1, 1)
    entries = []
    for index in range(70):
        close = 100.0 + (index * 0.1) + (0.05 if index % 2 else 0.0)
        entries.append(
            {
                "date": start + timedelta(days=index),
                "open": close - 0.25,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1000 + index,
            }
        )

    monkeypatch.setattr(service, "fetch_ohlc_series_from_oracle", lambda months=None: {"ABC": entries})
    monkeypatch.setattr(service, "get_all_time_high_for_symbols", lambda *args, **kwargs: {})
    monkeypatch.setattr(service, "_compute_rsi_series", lambda closes, period=14: [None] * (len(closes) - 1) + [52.0])
    monkeypatch.setattr(service, "_compute_macd", lambda closes: (1.2, 0.8, 0.4))
    monkeypatch.setattr(service, "_wilder_atr", lambda trs, period: [None] * (len(trs) - 1) + [3.0])
    monkeypatch.setattr(service, "_compute_adx_last", lambda candles, period=14: 27.5)
    monkeypatch.setattr(
        service,
        "calculate_master_trend",
        lambda row: {
            "trend": "UPTREND",
            "trendSort": 2,
            "trendDecisionReason": "TEST_TREND",
            "trendSource": "MASTER_TECHNICAL_SCORE_ENGINE",
        },
    )

    payload, _latest_snapshot = service.compute_bhramhastra_scan(timeframe="daily")

    assert payload["count"] == 1
    row = payload["rows"][0]
    assert row["symbol"] == "ABC"
    assert row["ema20"] is not None
    assert row["ema50"] == row["emaDays"]
    assert row["ema100"] is not None
    assert row["ema200"] is not None
    assert row["adx14"] == 27.5
    assert row["trendDirection"] == "UPTREND"
    assert row["trendSource"] == "MASTER_TECHNICAL_SCORE_ENGINE"
    assert row["gap"] is not None
    assert row["gapSort"] is not None
    assert row["setupType"] == service.BHRAMHASTRA_SETUP_TYPE
    assert row["setup_type"] == service.BHRAMHASTRA_SETUP_TYPE


def test_repair_display_fields_backfills_existing_snapshot_rows(monkeypatch):
    start = datetime(2026, 1, 1)
    entries = []
    for index in range(70):
        close = 100.0 + index
        entries.append(
            {
                "date": start + timedelta(days=index),
                "open": close - 0.25,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1000 + index,
            }
        )

    monkeypatch.setattr(service, "fetch_ohlc_series_from_oracle", lambda months=None: {"ABC": entries})
    monkeypatch.setattr(service, "_compute_adx_last", lambda candles, period=14: 31.25)
    monkeypatch.setattr(
        service,
        "calculate_master_trend",
        lambda row: {
            "trend": "UPTREND",
            "trendSort": 2,
            "trendDecisionReason": "TEST_TREND",
            "trendSource": "MASTER_TECHNICAL_SCORE_ENGINE",
        },
    )

    payload = {
        "rows": [{
            "symbol": "ABC",
            "entryPrice": 169.0,
            "emaDays": 155.0,
            "ath": 200.0,
            "target1": 180.0,
        }],
        "count": 1,
        "timeframe": "daily",
        "athSource": "NSE_NIFTY500_DAILY_RAW_DATA_DEV",
    }

    repaired, repaired_count = service.repair_bhramhastra_display_fields(payload, timeframe="daily")

    assert repaired_count == 1
    row = repaired["rows"][0]
    assert row["target1"] == 180.0
    assert row["ema20"] is not None
    assert row["ema100"] is not None
    assert row["ema200"] is not None
    assert row["adx14"] == 31.25
    assert row["trendDirection"] == "UPTREND"
    assert row["gap"] == -15.5
    assert row["gapSort"] == -15.5
    assert row["setupType"] == service.BHRAMHASTRA_SETUP_TYPE


def test_repair_setup_type_does_not_fetch_history_when_only_setup_type_missing(monkeypatch):
    monkeypatch.setattr(
        service,
        "fetch_ohlc_series_from_oracle",
        lambda months=None: (_ for _ in ()).throw(AssertionError("OHLC history should not be fetched")),
    )

    payload = {
        "rows": [{
            "symbol": "ABC",
            "ema20": 100,
            "ema100": 95,
            "ema200": 90,
            "adx14": 28,
            "trendDirection": "UPTREND",
            "gap": -10.0,
        }],
        "count": 1,
        "timeframe": "daily",
        "athSource": "NSE_NIFTY500_DAILY_RAW_DATA_DEV",
    }

    repaired, repaired_count = service.repair_bhramhastra_display_fields(payload, timeframe="daily")

    assert repaired_count == 1
    assert repaired["rows"][0]["setupType"] == service.BHRAMHASTRA_SETUP_TYPE
    assert repaired["rows"][0]["setup_type"] == service.BHRAMHASTRA_SETUP_TYPE


def test_upsert_freezes_backtest_date_from_existing_symbol_anchor(monkeypatch):
    fake_conn = _FakeConn()
    fake_pool = _FakePool(fake_conn)

    monkeypatch.setattr(service, "pool", fake_pool)
    monkeypatch.setattr(service, "_ensure_bhramhastra_objects", lambda conn: None)
    monkeypatch.setattr(service, "_fetch_existing_signal_keys", lambda conn, rows: set())
    monkeypatch.setattr(service, "_fetch_symbol_backtest_anchor", lambda conn, symbols: {"ABC": date(2026, 1, 1)})
    monkeypatch.setattr(service, "_id_is_identity", lambda conn: True)

    payload_rows = [
        {
            "symbol": "ABC",
            "ltcDate": "2026-05-05",
            "tradeDate": "2026-05-05",
            "backtestDate": "2026-05-04",  # incoming value must be ignored in favor of anchor
            "entryPrice": 100.0,
            "target1": 110.0,
            "target2": 120.0,
            "stopLoss": 95.0,
            "rsi": 52.0,
            "macd": 0.4,
            "atr": 3.0,
            "volume": 100000,
        }
    ]

    result = service.upsert_bhramhastra_rows(payload_rows, latest_snapshot={})

    assert result["inserted"] == 1
    assert fake_conn.executemany_calls, "Expected MERGE executemany call"
    _, merged_rows = fake_conn.executemany_calls[-1]
    assert len(merged_rows) == 1
    assert merged_rows[0]["backtest_date"] == date(2026, 1, 1)
