from __future__ import annotations

from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import routes.trend as trend_route


def _enriched_payload(payload, **kwargs):
    rows = [{**payload["ema20"][0], "INDEX": "LARGE", "MCAP": 1000.0, "MCAP_RANK": 10}]
    return {**payload, "ema20": rows, "_enrich_kwargs": kwargs}


def test_trend_marketcap_enriches_refreshing_snapshot_payload(monkeypatch):
    calls = []

    def fake_enrich(payload, **kwargs):
        calls.append(kwargs)
        return _enriched_payload(payload, **kwargs)

    monkeypatch.setattr(trend_route.nse_mcap_svc, "enrich_payload_marketcap_index", fake_enrich)

    payload = {
        "refreshing": True,
        "timeframe": "daily",
        "ema20": [{"symbol": "ABC", "price": 100.0}],
        "ema50": [],
        "ema200": [],
        "ema200100": [],
        "ema20010050": [],
        "ema2001005020": [],
    }

    result = trend_route._with_marketcap(payload)

    assert calls == [{"row_keys": trend_route._trend_marketcap_row_keys}]
    assert result["ema20"][0]["INDEX"] == "LARGE"
    assert result["ema20"][0]["MCAP_RANK"] == 10


def test_trend_marketcap_enriches_blank_existing_marketcap_keys(monkeypatch):
    calls = []

    def fake_enrich(payload, **kwargs):
        calls.append(kwargs)
        return _enriched_payload(payload, **kwargs)

    monkeypatch.setattr(trend_route.nse_mcap_svc, "enrich_payload_marketcap_index", fake_enrich)

    payload = {
        "timeframe": "daily",
        "ema20": [{"symbol": "ABC", "INDEX": "", "MCAP": None, "MCAP_RANK": ""}],
        "ema50": [],
        "ema200": [],
        "ema200100": [],
        "ema20010050": [],
        "ema2001005020": [],
    }

    result = trend_route._with_marketcap(payload)

    assert calls == [{"row_keys": trend_route._trend_marketcap_row_keys}]
    assert result["ema20"][0]["INDEX"] == "LARGE"
    assert result["ema20"][0]["MCAP"] == 1000.0


def test_trend_marketcap_skips_when_rows_already_have_values(monkeypatch):
    def unexpected_enrich(*_args, **_kwargs):
        raise AssertionError("market-cap enrichment should not run for complete rows")

    monkeypatch.setattr(trend_route.nse_mcap_svc, "enrich_payload_marketcap_index", unexpected_enrich)

    payload = {
        "timeframe": "daily",
        "ema20": [{"symbol": "ABC", "INDEX": "MID", "MCAP": 1000.0, "MCAP_RANK": 10}],
        "ema50": [],
        "ema200": [],
        "ema200100": [],
        "ema20010050": [],
        "ema2001005020": [],
    }

    assert trend_route._with_marketcap(payload) is payload


def test_compute_trend_payload_reports_dev_symbol_universe(monkeypatch):
    rows = [
        {"symbol": "ABC", "price": 100.0},
        {"symbol": "DEF", "price": 120.0},
        {"symbol": "GHI", "price": 90.0},
    ]

    monkeypatch.setattr(trend_route, "fetch_series", lambda timeframe: {"timeframe": timeframe})
    monkeypatch.setattr(trend_route, "return_column_metadata_for_series", lambda _series: [])
    monkeypatch.setattr(trend_route, "build_rows", lambda _series: rows)
    monkeypatch.setattr(
        trend_route,
        "_latest_source_symbol_count",
        lambda: {"totalSymbols": 778, "latestDate": "2026-05-27", "source": "CVING_NSE_MARKET_CAP_HIST"},
    )
    monkeypatch.setattr(
        trend_route,
        "categorize",
        lambda _rows: (
            rows[:1],
            rows[:2],
            [],
            [],
            rows,
            [],
            [],
            [],
        ),
    )

    payload = trend_route._compute_trend_payload("daily")

    assert payload["totalSymbols"] == 778
    assert payload["summary"]["totalSymbols"] == 778
    assert payload["technicalRows"] == 3
    assert payload["summary"]["technicalRows"] == 3
    assert payload["totalSymbolsSource"] == "CVING_NSE_MARKET_CAP_HIST"
    assert len(payload["ema20"]) == 1
    assert len(payload["ema50"]) == 2


def test_trading_days_payload_uses_lightweight_grouped_query(monkeypatch):
    executed_sql = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql):
            executed_sql.append(sql)

        def __iter__(self):
            return iter([("abc", 6), ("XYZ", 156)])

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return FakeCursor()

    monkeypatch.setattr(trend_route, "get_oracle_connection", lambda: FakeConnection())
    monkeypatch.setattr(
        trend_route,
        "_resolve_source_meta",
        lambda _conn: {
            "qualified_table": "NSE_NIFTY500_DAILY_RAW_DATA_DEV",
            "date_column": "TRADING_DATE",
            "columns": ["SYMBOL", "TRADING_DATE", "CLOSE_PRICE"],
        },
    )

    payload = trend_route._query_trading_days_payload("daily")

    assert payload["rows"] == [
        {"symbol": "ABC", "tradingDays": 6},
        {"symbol": "XYZ", "tradingDays": 156},
    ]
    assert payload["count"] == 2
    assert "COUNT(CLOSE_PRICE)" in executed_sql[0]


def test_legacy_trend_snapshot_remains_valid_without_all_rows():
    payload = {
        "timeframe": "daily",
        "ema20": [],
        "ema50": [],
        "ema200": [],
        "ema200100": [],
        "ema20010050": [],
        "ema2001005020": [],
    }

    assert trend_route._is_valid(payload) is True
