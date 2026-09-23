from __future__ import annotations

from datetime import date

from services import strong_technicals_service as service


class _FakeCache:
    def __init__(self):
        self.payload = {"rows": [{"symbol": "OLD"}], "meta": {"latestTradingDate": "2026-07-22"}}

    def get(self, _key):
        return self.payload

    def set(self, _key, value):
        self.payload = value


def test_universe_rebuilds_an_older_snapshot_missing_additive_returns(monkeypatch):
    fake_cache = _FakeCache()
    monkeypatch.setattr(service, "_cache", fake_cache)
    monkeypatch.setattr(service, "fetch_latest_trade_date_from_oracle", lambda: date(2026, 7, 22))
    monkeypatch.setattr(
        service,
        "_compute_and_persist_payload",
        lambda *_args: {
            "rows": [{
                "symbol": "AUTOLEAD",
                "return21": 3.0,
                "return63": 8.0,
                "return126": 14.0,
            }],
            "meta": {"latestTradingDate": "2026-07-22"},
        },
    )
    enrichment_calls = []

    def fake_enrich(rows, **kwargs):
        enrichment_calls.append(kwargs)
        return rows

    monkeypatch.setattr(
        service.nse_mcap_svc,
        "enrich_rows_with_marketcap_index",
        fake_enrich,
    )

    payload = service.fetch_strong_technicals_universe(
        required_fields=("return21", "return63", "return126"),
    )

    assert payload["rows"] == [{
        "symbol": "AUTOLEAD",
        "return21": 3.0,
        "return63": 8.0,
        "return126": 14.0,
    }]
    assert enrichment_calls == [{"allow_stale_per_symbol": True}]
