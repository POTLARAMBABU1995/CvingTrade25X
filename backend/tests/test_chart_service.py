from pathlib import Path
import sys
import types

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

sys.modules.setdefault(
    "db_pool",
    types.SimpleNamespace(pool=types.SimpleNamespace(acquire=lambda: None), fetchall_dict=lambda *_args, **_kwargs: []),
)

import services.chart_service as service


class _AcquireCtx:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, exc_type, exc, tb):
        return False


class FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _AcquireCtx(self._conn)


class FakeCursor:
    def __init__(self, conn):
        self._conn = conn
        self.description = []
        self.arraysize = 0
        self.prefetchrows = 0
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, binds=None):
        self._conn.executed.append((sql, dict(binds or {})))
        if "ROWNUM = 0" in sql.upper():
            self.description = [(name,) for name in self._conn.columns]
            self._rows = []
            return
        self.description = [
            ("TIME",),
            ("OPEN_VAL",),
            ("HIGH_VAL",),
            ("LOW_VAL",),
            ("CLOSE_VAL",),
            ("VOLUME_VAL",),
        ]
        self._rows = list(self._conn.rows)

    def __iter__(self):
        return iter(self._rows)


class FakeConn:
    def __init__(self, columns, rows):
        self.columns = columns
        self.rows = rows
        self.executed = []

    def cursor(self):
        return FakeCursor(self)


def _install_pool(monkeypatch, columns, rows):
    conn = FakeConn(columns, rows)
    monkeypatch.setattr(service, "pool", FakePool(conn))
    return conn


def test_normalize_chart_symbol_strips_common_tradingview_forms():
    assert service.normalize_chart_symbol("RELIANCE") == "RELIANCE"
    assert service.normalize_chart_symbol("NSE:RELIANCE-EQ") == "RELIANCE"
    assert service.normalize_chart_symbol(" reliance-eq ") == "RELIANCE"
    assert service.normalize_chart_symbol("NSE:ASTRAZEN:EQ") == "ASTRAZEN"


def test_daily_payload_uses_dev_table_and_builds_candle_volume_colors(monkeypatch):
    conn = _install_pool(
        monkeypatch,
        ["SYMBOL", "OPEN", "HIGH", "LOW", "PREVIOUS_CLOSE", "VOLUME", "TRADING_DATE", "WEEK_BUCKET", "MONTH_BUCKET"],
        [
            ("2026-05-06", 100, 105, 98, 103, 1234567),
            ("2026-05-07", 104, 106, 99, 101, 2345678),
        ],
    )

    payload = service.fetch_ohlcv_payload("NSE:RELIANCE-EQ", "daily")

    assert payload["symbol"] == "RELIANCE"
    assert payload["timeframe"] == "daily"
    assert payload["latest_date"] == "2026-05-07"
    assert payload["total_candles"] == 2
    assert payload["candles"][0] == {
        "time": "2026-05-06",
        "open": 100.0,
        "high": 105.0,
        "low": 98.0,
        "close": 103.0,
    }
    assert payload["volume"][0]["color"] == "rgba(34,197,94,0.45)"
    assert payload["volume"][1]["color"] == "rgba(239,68,68,0.45)"

    query_sql, binds = conn.executed[-1]
    assert "NSE_NIFTY500_DAILY_RAW_DATA_DEV" in query_sql
    assert "STOCK_EOD_HISTORY" not in query_sql
    assert "ORDER BY TRADING_DATE ASC" in query_sql
    assert binds == {"symbol": "RELIANCE"}


def test_weekly_sql_prefers_existing_week_bucket(monkeypatch):
    conn = _install_pool(
        monkeypatch,
        ["SYMBOL", "OPEN", "HIGH", "LOW", "PREVIOUS_CLOSE", "VOLUME", "TRADING_DATE", "WEEK_BUCKET", "MONTH_BUCKET"],
        [("2026-05-04", 100, 108, 96, 106, 5000000)],
    )

    service.fetch_ohlcv_payload("TCS", "weekly")

    query_sql = conn.executed[-1][0]
    assert "WEEK_BUCKET AS PERIOD_START" in query_sql
    assert "TRUNC(TRADING_DATE, 'IW')" not in query_sql
    assert "KEEP (DENSE_RANK FIRST ORDER BY TRADING_DATE ASC)" in query_sql
    assert "KEEP (DENSE_RANK LAST ORDER BY TRADING_DATE ASC)" in query_sql
    assert "SUM(NVL(VOLUME, 0))" in query_sql


def test_monthly_sql_falls_back_to_trunc_when_bucket_missing(monkeypatch):
    conn = _install_pool(
        monkeypatch,
        ["SYMBOL", "OPEN", "HIGH", "LOW", "PREVIOUS_CLOSE", "VOLUME", "TRADING_DATE"],
        [("2026-05-01", 100, 110, 90, 105, 7000000)],
    )

    service.fetch_ohlcv_payload("INFY", "monthly")

    query_sql = conn.executed[-1][0]
    assert "TRUNC(TRADING_DATE, 'MM') AS PERIOD_START" in query_sql
    assert "GROUP BY TRUNC(TRADING_DATE, 'MM')" in query_sql


def test_watchlist_payload_uses_latest_and_previous_rows_from_dev_table(monkeypatch):
    conn = _install_pool(
        monkeypatch,
        ["SYMBOL", "OPEN", "HIGH", "LOW", "PREVIOUS_CLOSE", "VOLUME", "TRADING_DATE"],
        [
            ("RELIANCE", "2026-05-07", 1435.2, 1436.2, -1.0, -0.07, 8123456, "2026-05-07"),
            ("TCS", "2026-05-07", 3900.0, 3800.0, 100.0, 2.63, 1234567, "2026-05-07"),
        ],
    )

    payload = service.fetch_watchlist_payload()

    assert payload["total_symbols"] == 2
    assert payload["latest_trade_date"] == "2026-05-07"
    assert payload["rows"][0] == {
        "symbol": "RELIANCE",
        "last": 1435.2,
        "change": -1.0,
        "change_percent": -0.07,
        "volume": 8123456,
        "trading_date": "2026-05-07",
    }

    query_sql = "\n".join(sql for sql, _binds in conn.executed)
    binds = conn.executed[-1][1]
    assert "NSE_NIFTY500_DAILY_RAW_DATA_DEV" in query_sql
    assert "SELECT DISTINCT" in query_sql
    assert "WITH market_dates AS" in query_sql
    assert "PREVIOUS_DATE" in query_sql
    assert "ORDER BY latest.SYMBOL_VAL" in query_sql
    assert binds == {}


def test_invalid_timeframe_is_rejected():
    with pytest.raises(service.InvalidChartParameter):
        service.normalize_timeframe("intraday")
