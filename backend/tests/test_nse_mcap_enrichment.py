from __future__ import annotations

import sys
import types
from datetime import date
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
SERVICES_ROOT = BACKEND_ROOT / "services"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(SERVICES_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICES_ROOT))

sys.modules.setdefault(
    "db_pool",
    types.SimpleNamespace(pool=types.SimpleNamespace(acquire=lambda: None)),
)

import services.nse_mcap_service as service


class _FakeCursor:
    def __init__(self):
        self.description = []
        self._result = []
        self._execute_count = 0

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, _sql, _binds=None):
        self._execute_count += 1
        if self._execute_count == 1:
            self.description = [("latest_trade_date",)]
            self._result = [(date(2026, 5, 8),)]
        elif self._execute_count == 2:
            self.description = [
                ("script",),
                ("symbol",),
                ("index_category",),
                ("mcap_rank",),
                ("market_cap_crores",),
                ("mcap_series",),
                ("security_name",),
            ]
            self._result = [("RELIANCE", "RELIANCE", "LARGE", 1, 1943272.56, "EQ", "RELIANCE INDUSTRIES LTD")]
        elif self._execute_count == 3:
            self.description = [("symbol_key",), ("mcap_series",), ("security_name",)]
            self._result = []
        else:
            self.description = [("symbol_key",), ("ltc_date",)]
            self._result = []

    def fetchone(self):
        return self._result[0] if self._result else None

    def fetchall(self):
        return list(self._result)


class _FakeConnection:
    def __init__(self):
        self.cursor_instance = _FakeCursor()
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def close(self):
        self.closed = True


class _FakePool:
    def __init__(self):
        self.connection = _FakeConnection()

    def acquire(self):
        return self.connection


def test_enrich_rows_with_marketcap_index_normalizes_symbols_and_preserves_rows(monkeypatch):
    lookup_calls = []

    def fake_lookup(symbols, **kwargs):
        lookup_calls.append((list(symbols), kwargs))
        return {
            "RELIANCE": {"index": "LARGE", "mcap": 1987654.25, "mcapRank": 1},
            "ASTRAZEN": {"INDEX": "MID", "MCAP": 12345.0, "MCAP_RANK": 222},
        }

    monkeypatch.setattr(service, "get_marketcap_index_lookup", fake_lookup, raising=False)

    rows = [
        {"symbol": "NSE:RELIANCE-EQ", "price": 100.0},
        {"SYMBOL": "NSE:ASTRAZEN-EQ", "price": 200.0},
        {"symbol": "NO_MCAP", "price": 300.0},
    ]

    enriched = service.enrich_rows_with_marketcap_index(rows)

    assert enriched is not rows
    assert rows[0] == {"symbol": "NSE:RELIANCE-EQ", "price": 100.0}
    assert lookup_calls == [
        (
            ["NSE:RELIANCE-EQ", "NSE:ASTRAZEN-EQ", "NO_MCAP"],
            {"allow_stale_per_symbol": False, "allow_base_table_fallback": True},
        )
    ]
    assert enriched[0]["INDEX"] == "LARGE"
    assert enriched[0]["MCAP"] == 1987654.25
    assert enriched[0]["MCAP_RANK"] == 1
    assert enriched[0]["index"] == "LARGE"
    assert enriched[0]["mcap"] == 1987654.25
    assert enriched[0]["mcapRank"] == 1
    assert enriched[1]["INDEX"] == "MID"
    assert enriched[1]["MCAP"] == 12345.0
    assert enriched[1]["MCAP_RANK"] == 222
    assert enriched[2]["INDEX"] == "-"
    assert enriched[2]["MCAP"] is None
    assert enriched[2]["MCAP_RANK"] is None


def test_enrich_payload_marketcap_index_handles_multiple_row_containers(monkeypatch):
    monkeypatch.setattr(
        service,
        "get_marketcap_index_lookup",
        lambda symbols, **_kwargs: {
            "ABC": {"index": "SMALL", "mcap": 456.7, "mcapRank": 333},
            "XYZ": {"index": "LARGE", "mcap": 999.0, "mcapRank": 9},
        },
        raising=False,
    )

    payload = {
        "rows": [{"symbol": "ABC"}],
        "items": [{"symbol": "XYZ"}],
        "meta": {"unchanged": True},
    }

    enriched = service.enrich_payload_marketcap_index(payload, row_keys=("rows", "items"))

    assert enriched is not payload
    assert enriched["meta"] == {"unchanged": True}
    assert enriched["rows"][0]["INDEX"] == "SMALL"
    assert enriched["rows"][0]["MCAP_RANK"] == 333
    assert enriched["items"][0]["INDEX"] == "LARGE"
    assert enriched["items"][0]["MCAP"] == 999.0


def test_marketcap_index_latest_emits_canonical_index_mcap_aliases(monkeypatch):
    fake_pool = _FakePool()
    monkeypatch.setattr(service, "pool", fake_pool, raising=False)

    payload = service.get_marketcap_index_latest()

    row = payload["data"][0]
    assert row["symbol"] == "RELIANCE"
    assert row["INDEX"] == "LARGE"
    assert row["MCAP"] == 1943272.56
    assert row["MCAP_RANK"] == 1
    assert row["index"] == "LARGE"
    assert row["marketCapCrores"] == 1943272.56
    assert row["mcapRank"] == 1


def test_get_marketcap_index_lookup_uses_latest_per_symbol_only_when_enabled(monkeypatch):
    service._MARKETCAP_LOOKUP_CACHE.clear()

    class FakeConnection:
        closed = False

        def cursor(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def close(self):
            self.closed = True

    class FakePool:
        def __init__(self):
            self.connection = FakeConnection()

        def acquire(self):
            return self.connection

    stale_calls = []

    monkeypatch.setattr(service, "pool", FakePool(), raising=False)
    monkeypatch.setattr(service, "_INDEX_VIEW_AVAILABLE", True, raising=False)
    monkeypatch.setattr(service, "_marketcap_lookup_from_view", lambda _cur, _symbols: {}, raising=False)
    monkeypatch.setattr(service, "_marketcap_lookup_from_base_table", lambda _cur, _symbols: {}, raising=False)

    def latest_per_symbol(_cur, symbols):
        stale_calls.append(list(symbols))
        return {"TVSSCS": {"index": "SMALL", "mcap": 4970.33, "mcapRank": 704}}

    monkeypatch.setattr(service, "_marketcap_lookup_from_latest_per_symbol", latest_per_symbol, raising=False)

    assert service.get_marketcap_index_lookup(["TVSSCS"]) == {}
    assert stale_calls == []

    service._MARKETCAP_LOOKUP_CACHE.clear()
    enriched = service.get_marketcap_index_lookup(["TVSSCS"], allow_stale_per_symbol=True)

    assert stale_calls == [["TVSSCS"]]
    assert enriched["TVSSCS"]["index"] == "SMALL"
    assert enriched["TVSSCS"]["mcap"] == 4970.33
    assert enriched["TVSSCS"]["mcapRank"] == 704


def test_get_marketcap_index_lookup_can_skip_base_table_fallback(monkeypatch):
    service._MARKETCAP_LOOKUP_CACHE.clear()

    class FakeConnection:
        closed = False

        def cursor(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def close(self):
            self.closed = True

    class FakePool:
        def __init__(self):
            self.connection = FakeConnection()

        def acquire(self):
            return self.connection

    base_calls = []
    fake_pool = FakePool()
    monkeypatch.setattr(service, "pool", fake_pool, raising=False)
    monkeypatch.setattr(service, "_INDEX_VIEW_AVAILABLE", True, raising=False)
    monkeypatch.setattr(service, "_marketcap_lookup_from_view", lambda _cur, _symbols: {}, raising=False)

    def base_lookup(_cur, symbols):
        base_calls.append(list(symbols))
        return {"TANLA": {"index": "MID", "mcap": 1000.0, "mcapRank": 150}}

    monkeypatch.setattr(service, "_marketcap_lookup_from_base_table", base_lookup, raising=False)

    result = service.get_marketcap_index_lookup(["TANLA"], allow_base_table_fallback=False)

    assert result == {}
    assert base_calls == []
    assert fake_pool.connection.closed is True
