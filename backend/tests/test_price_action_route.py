from pathlib import Path
import sys

from flask import Flask


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import routes.price_action as price_action_route
import services.strong_technicals_service as strong_technicals_service


class _DummyConnection:
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _DummyPool:
    def acquire(self):
        return _DummyConnection()


def _build_client():
    app = Flask(__name__)
    app.register_blueprint(price_action_route.bp)
    return app.test_client()


def test_manual_sr_route_returns_enriched_market_cap_rows(monkeypatch):
    grouped_rows = [
        {
            "s_no": 1,
            "symbol": "NSE:ABC-EQ",
            "td": "1D",
            "sr_level": "100,110",
            "level_count": 2,
            "levels": [{"level_id": "L1", "value": "100"}, {"level_id": "L2", "value": "110"}],
        }
    ]

    def fake_enrich(rows):
        assert rows is grouped_rows
        return [
            {
                **rows[0],
                "symbol": "ABC",
                "INDEX": "MID",
                "index": "MID",
                "MCAP": 12345.6,
                "mcap": 12345.6,
                "MCAP_RANK": 123,
                "mcapRank": 123,
            }
        ]

    monkeypatch.setattr(price_action_route, "pool", _DummyPool())
    monkeypatch.setattr(price_action_route, "_fetch_grouped_rows", lambda _conn, search=None: grouped_rows)
    monkeypatch.setattr(price_action_route.nse_mcap_service, "enrich_rows_with_marketcap_index", fake_enrich)

    response = _build_client().get("/api/price-action-sr-levels-manually")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["rows"][0]["symbol"] == "ABC"
    assert payload["rows"][0]["INDEX"] == "MID"
    assert payload["rows"][0]["MCAP"] == 12345.6
    assert payload["rows"][0]["MCAP_RANK"] == 123


def _price_action_payload():
    return {
        "rows": [
            {
                "symbol": "ABC",
                "price": 100.0,
                "priceSort": 100.0,
                "ltcDate": "15-05-2026",
                "ltcDateSort": 1789324200,
                "td": 252,
                "trendStructure": "Strong Uptrend",
                "priceActionLabels": ["Higher High", "Higher Low"],
                "lastSwingHigh": 110.0,
                "lastSwingLow": 95.0,
                "hhHlStatus": "Higher High, Higher Low",
                "support": 95.0,
                "resistance": 110.0,
                "nearestSupport": 95.0,
                "nearestResistance": 110.0,
                "priceActionScore": 100.0,
                "techStatus": "Very Strong Technicals",
                "riskLevel": "Low",
            }
        ],
        "meta": {
            "sourceTable": "NSE_NIFTY500_DAILY_RAW_DATA_DEV",
            "timeframe": "daily",
            "lookbackMonths": 24,
            "latestOnly": True,
            "latestTradingDate": "2026-05-15",
            "symbolsProcessed": 1,
            "rowsComputed": 1,
            "skippedSymbols": {},
            "calculationDurationMs": 12.5,
            "generatedAt": "2026-05-15T11:46:10Z",
            "computeProfile": "price_action",
        },
    }


def test_price_action_refresh_uses_cached_payload_without_full_recompute(monkeypatch, tmp_path):
    service = strong_technicals_service
    service._cache.clear()
    monkeypatch.setattr(service, "_SNAPSHOT_DIR", tmp_path)
    monkeypatch.setattr(service, "fetch_latest_trade_date_from_oracle", lambda: None)
    monkeypatch.setattr(service.nse_mcap_svc, "enrich_rows_with_marketcap_index", lambda rows: rows)
    monkeypatch.setattr(service, "_fetch_manual_sr_level_map_for_symbols", lambda _symbols: {})
    monkeypatch.setattr(
        service,
        "_compute_price_action_rows",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("refresh should not block on recompute")),
    )
    scheduled_keys = []
    monkeypatch.setattr(service, "background_refresh", lambda _cache, key, _compute: scheduled_keys.append(key))

    cache_key = service._cache_key_for_view("price_action", "daily", True)
    service._cache.set(cache_key, _price_action_payload())

    payload = service.fetch_strong_technicals_page(
        view="price_action",
        tf="daily",
        latest_only=True,
        refresh=True,
        page=1,
        page_size=15,
        sort_by="priceActionScore",
        sort_dir="desc",
    )

    assert payload["ok"] is True
    assert payload["cached"] is True
    assert payload["refreshing"] is True
    assert payload["rows"][0]["symbol"] == "ABC"
    assert payload["rows"][0]["sr_levels"] == "-"
    assert scheduled_keys == [cache_key]
    service._cache.clear()


def test_price_action_adds_manual_sr_levels_to_response_rows(monkeypatch, tmp_path):
    service = strong_technicals_service
    service._cache.clear()
    monkeypatch.setattr(service, "_SNAPSHOT_DIR", tmp_path)
    monkeypatch.setattr(service, "fetch_latest_trade_date_from_oracle", lambda: None)
    monkeypatch.setattr(service.nse_mcap_svc, "enrich_rows_with_marketcap_index", lambda rows: rows)
    monkeypatch.setattr(
        service,
        "_fetch_manual_sr_level_map_for_symbols",
        lambda _symbols: {
            "ABC": {
                "symbol": "ABC",
                "levels": [95.0, 110.0],
                "levelTexts": ["95", "110"],
            }
        },
    )
    monkeypatch.setattr(service, "_compute_price_action_rows", lambda _tf, _latest_only: _price_action_payload())

    payload = service.fetch_strong_technicals_page(
        view="price_action",
        tf="daily",
        latest_only=True,
        refresh=True,
        page=1,
        page_size=15,
        sort_by="priceActionScore",
        sort_dir="desc",
    )

    assert payload["ok"] is True
    assert payload["rows"][0]["sr_levels"] == "95, 110"
    assert payload["rows"][0]["SR_LEVELS"] == "95, 110"
    assert payload["rows"][0]["srLevels"] == "95, 110"
    assert payload["meta"]["srLevelsSource"] == "PRICE_ACTION_SR_LEVELS_MANUALLY"
    service._cache.clear()


def test_price_action_uses_optimized_compute_profile_and_snapshot(monkeypatch, tmp_path):
    service = strong_technicals_service
    service._cache.clear()
    monkeypatch.setattr(service, "_SNAPSHOT_DIR", tmp_path)
    monkeypatch.setattr(service, "fetch_latest_trade_date_from_oracle", lambda: None)
    monkeypatch.setattr(service.nse_mcap_svc, "enrich_rows_with_marketcap_index", lambda rows: rows)
    monkeypatch.setattr(service, "_fetch_manual_sr_level_map_for_symbols", lambda _symbols: {})
    monkeypatch.setattr(
        service,
        "_compute_base_rows",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("price action should not use full compute")),
    )
    monkeypatch.setattr(service, "_compute_price_action_rows", lambda _tf, _latest_only: _price_action_payload())

    payload = service.fetch_strong_technicals_page(
        view="price_action",
        tf="daily",
        latest_only=True,
        refresh=True,
        page=1,
        page_size=15,
        sort_by="priceActionScore",
        sort_dir="desc",
    )

    cache_key = service._cache_key_for_view("price_action", "daily", True)
    assert payload["ok"] is True
    assert payload["meta"]["computeProfile"] == "price_action"
    assert payload["rows"][0]["priceActionScore"] == 100.0
    assert Path(service._snapshot_path(cache_key)).exists()
    service._cache.clear()
