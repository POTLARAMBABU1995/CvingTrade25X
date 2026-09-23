from __future__ import annotations

import json

import pytest

from services.sector_rotation_v3_stock_service import (
    build_sector_rotation_v3_stock_snapshot,
    evaluate_sector_v3_eligibility,
    get_sector_rotation_v3_stock_page,
)
from services import sector_rotation_v3_stock_service as service


@pytest.fixture(autouse=True)
def _clear_stock_lookup_caches():
    service._clear_stock_lookup_caches()
    yield
    service._clear_stock_lookup_caches()


def _parent(**overrides):
    row = {
        "sectorCode": "AUTO",
        "sectorName": "Auto",
        "finalRotationScore": 82,
        "rotationBand": "STRONG",
        "rotationPhase": "LEADING",
        "confidence": "HIGH",
        "coveragePercent": 92,
        "dataQualityScore": 90,
        "riskScore": 75,
        "latestDataDate": "2026-07-22",
        "moneyFlowScore": 68,
        "riskWarnings": [],
    }
    row.update(overrides)
    return row


def _technical(symbol: str, **overrides):
    row = {
        "symbol": symbol,
        "price": 125,
        "ltcDate": "2026-07-22",
        "td": 260,
        "return21": 12,
        "return63": 24,
        "return126": 35,
        "ema20": 120,
        "ema50": 110,
        "ema100": 100,
        "ema200": 90,
        "rsi": 64,
        "macd": 4,
        "macdHist": 1,
        "adx14": 32,
        "priceActionScore": 90,
        "breakoutScore": 92,
        "trendlineScore": 84,
        "chartPatternScore": 74,
        "atr14": 4,
        "atrGt14": "Y",
        "mcap": 10000,
        "volumeRatio": 1.6,
        "deliveryScore": 72,
        "multiTimeframeScore": 90,
        "riskQualityScore": 88,
        "riskLevel": "LOW",
        "support": 105,
        "techScore": 85,
        "techStatus": "Strong Technicals",
    }
    row.update(overrides)
    return row


def test_best_sector_rejects_high_score_when_stale_or_low_coverage():
    stale = evaluate_sector_v3_eligibility(
        _parent(finalRotationScore=95, latestDataDate="2026-07-21"),
        "2026-07-22",
    )
    low_coverage = evaluate_sector_v3_eligibility(
        _parent(finalRotationScore=95, coveragePercent=84.99),
        "2026-07-22",
    )

    assert stale["eligible"] is False
    assert "currentDate" in stale["failedGates"]
    assert low_coverage["eligible"] is False
    assert "coverage" in low_coverage["failedGates"]


def test_strong_sector_does_not_promote_weak_constituent():
    payload = build_sector_rotation_v3_stock_snapshot(
        {
            "runId": "run-1",
            "asOfDate": "2026-07-22",
            "rows": [_parent()],
        },
        [
            _technical("LEADER"),
            _technical(
                "WEAK",
                price=80,
                return21=-15,
                return63=-20,
                return126=-28,
                ema20=90,
                ema50=95,
                ema100=100,
                ema200=110,
                rsi=35,
                macd=-3,
                macdHist=-1,
                adx14=27,
                support=85,
                priceActionScore=20,
                breakoutScore=10,
                trendlineScore=15,
                volumeRatio=0.7,
                deliveryScore=35,
                multiTimeframeScore=20,
                riskQualityScore=35,
                riskLevel="HIGH",
            ),
        ],
        {"LEADER": ["AUTO"], "WEAK": ["AUTO"]},
        technical_source_date="2026-07-22",
    )

    rows = {row["symbol"]: row for row in payload["sectors"]["AUTO"]["rows"]}
    assert rows["LEADER"]["trendState"] == "STRONG_UPTREND"
    assert rows["LEADER"]["trend"] == "Strong Uptrend"
    assert rows["WEAK"]["trendState"] == "DOWNTREND"
    assert rows["WEAK"]["trend"] == "Downtrend"


def test_ema20_pullback_cannot_be_strong_uptrend():
    payload = build_sector_rotation_v3_stock_snapshot(
        {
            "runId": "run-2",
            "asOfDate": "2026-07-22",
            "rows": [_parent()],
        },
        [
            _technical(
                "PULLBACK",
                price=115,
                ema20=118,
                ema50=110,
                ema100=100,
                ema200=90,
            ),
            _technical("PEER", return21=2, return63=3, return126=4),
        ],
        {"PULLBACK": ["AUTO"], "PEER": ["AUTO"]},
        technical_source_date="2026-07-22",
    )

    row = next(item for item in payload["sectors"]["AUTO"]["rows"] if item["symbol"] == "PULLBACK")
    assert row["trendState"] == "UPTREND"
    assert "EMA20_PULLBACK" in row["warnings"]


def test_complete_ema_alignment_prevents_contradictory_v3_trends():
    payload = build_sector_rotation_v3_stock_snapshot(
        {
            "runId": "run-ema-alignment",
            "asOfDate": "2026-07-22",
            "rows": [_parent(latestDataDate="2026-07-21", rotationPhase="DATA_WEAK")],
        },
        [
            _technical("ALL_Y"),
            _technical("THREE_Y", price=115, ema20=120),
            _technical("TWO_Y", price=105, ema20=120, ema50=110),
            _technical("ONE_Y", price=85, ema20=80, ema50=90, ema100=100, ema200=110),
            _technical("ALL_N", price=75, ema20=80, ema50=90, ema100=100, ema200=110, td=172),
        ],
        {
            "ALL_Y": ["AUTO"],
            "THREE_Y": ["AUTO"],
            "TWO_Y": ["AUTO"],
            "ONE_Y": ["AUTO"],
            "ALL_N": ["AUTO"],
        },
        technical_source_date="2026-07-22",
    )

    rows = {row["symbol"]: row for row in payload["sectors"]["AUTO"]["rows"]}
    assert rows["ALL_Y"]["trendState"] == "STRONG_UPTREND"
    assert rows["THREE_Y"]["trendState"] == "UPTREND"
    assert rows["TWO_Y"]["trendState"] == "SIDEWAYS"
    assert rows["ONE_Y"]["trendState"] == "DOWNTREND"
    assert rows["ALL_N"]["trendState"] == "DOWNTREND"


def test_later_technical_candles_are_rejected():
    try:
        build_sector_rotation_v3_stock_snapshot(
            {
                "runId": "run-3",
                "asOfDate": "2026-07-22",
                "rows": [_parent()],
            },
            [_technical("LEADER", ltcDate="2026-07-23")],
            {"LEADER": ["AUTO"]},
            technical_source_date="2026-07-23",
        )
    except ValueError as exc:
        assert "later than the parent" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("future technical candles must be rejected")


def test_page_rejects_sector_and_stock_run_date_mismatch(monkeypatch):
    monkeypatch.setattr(
        service,
        "read_sector_rotation_v3_stock_snapshot",
        lambda: {
            "runId": "stock-run",
            "asOfDate": "2026-07-21",
            "sectors": {"AUTO": {"rows": []}},
        },
    )
    monkeypatch.setattr(
        service,
        "read_latest_published_v3_snapshot",
        lambda: {
            "runId": "sector-run",
            "asOfDate": "2026-07-22",
            "rows": [{"sectorCode": "AUTO"}],
        },
    )

    payload, status = get_sector_rotation_v3_stock_page("AUTO", page=1, page_size=25)

    assert status == 503
    assert payload["reason"] == "V3_RUN_DATE_MISMATCH"


def test_exact_symbol_lookup_reuses_published_sector_page(monkeypatch):
    monkeypatch.setattr(
        service,
        "read_sector_rotation_v3_stock_snapshot",
        lambda: {
            "runId": "run-symbol",
            "asOfDate": "2026-07-22",
            "sectors": {
                "IT": {
                    "sectorName": "IT",
                    "rows": [{"symbol": "TCS"}],
                },
            },
        },
    )
    monkeypatch.setattr(
        service,
        "read_latest_published_v3_snapshot",
        lambda: {"runId": "run-symbol", "asOfDate": "2026-07-22"},
    )
    monkeypatch.setattr(service, "_overview_rows_by_symbol", lambda: {})
    monkeypatch.setattr(
        service,
        "_supplement_memberships_from_staging",
        lambda memberships, **_kwargs: memberships,
    )

    payload, status = service.get_sector_rotation_v3_stock_symbol("NSE:TCS-EQ")

    assert status == 200
    assert payload["symbol"] == "TCS"
    assert payload["sectorCodes"] == ["IT"]
    assert payload["row"]["sectorName"] == "IT"


def test_exact_symbol_lookup_uses_stale_identity_with_current_parent_trend(monkeypatch):
    monkeypatch.setattr(
        service,
        "read_sector_rotation_v3_stock_snapshot",
        lambda: {
            "runId": "stock-run-old",
            "asOfDate": "2026-07-21",
            "sectors": {
                "RESTAURANTS": {
                    "sectorName": "Restaurants",
                    "parent": {"phase": "LAGGING", "confidence": "MEDIUM"},
                    "rows": [{
                        "symbol": "WESTLIFE",
                        "parentSectorPhase": "LAGGING",
                        "parentSectorConfidence": "MEDIUM",
                    }],
                },
            },
        },
    )
    monkeypatch.setattr(
        service,
        "read_latest_published_v3_snapshot",
        lambda: {
            "runId": "parent-run-current",
            "asOfDate": "2026-07-22",
            "rows": [{
                "sectorCode": "RESTAURANTS",
                "sectorName": "Restaurants",
                "finalRotationScore": 79.61,
                "rotationBand": "STRONG",
                "rotationPhase": "DATA_WEAK",
            }],
        },
    )
    monkeypatch.setattr(
        service,
        "_get_stock_symbol_index",
        lambda *_args: (_ for _ in ()).throw(AssertionError("stale fallback must not query supplements")),
    )

    payload, status = service.get_sector_rotation_v3_stock_symbol("WESTLIFE")

    assert status == 200
    assert payload["source"] == "V3_STALE_IDENTITY_FALLBACK"
    assert payload["isStale"] is True
    assert payload["asOfDate"] == "2026-07-21"
    assert payload["parentAsOfDate"] == "2026-07-22"
    assert payload["row"]["sectorName"] == "Restaurants"
    assert payload["row"]["parentSectorPhase"] == "DATA_WEAK"
    assert payload["row"]["parent"]["phase"] == "DATA_WEAK"
    assert payload["row"]["parentSectorConfidence"] == "MEDIUM"
    assert payload["row"]["parent"]["confidence"] == "MEDIUM"


def test_exact_symbol_lookup_includes_staging_overview_supplement(monkeypatch):
    monkeypatch.setattr(
        service,
        "read_sector_rotation_v3_stock_snapshot",
        lambda: {
            "runId": "run-symbol-supplement",
            "asOfDate": "2026-07-22",
            "sectors": {
                "AUTO": {
                    "sectorName": "Auto",
                    "rows": [{"symbol": "LEADER", "trendState": "UPTREND"}],
                },
            },
        },
    )
    monkeypatch.setattr(
        service,
        "read_latest_published_v3_snapshot",
        lambda: {"runId": "run-symbol-supplement", "asOfDate": "2026-07-22"},
    )

    def supplement(memberships, *, sector_codes=None):
        assert memberships == {}
        assert sector_codes == ["AUTO"]
        return {"LEADER": ["AUTO"], "PEER": ["AUTO"]}

    monkeypatch.setattr(service, "_supplement_memberships_from_staging", supplement)
    monkeypatch.setattr(
        service,
        "_overview_rows_by_symbol",
        lambda: {
            "PEER": {
                "stock": "PEER",
                "price": 250.0,
                "ltc_date": "22-07-2026",
                "trend": "Uptrend",
            },
        },
    )

    payload, status = service.get_sector_rotation_v3_stock_symbol("PEER")

    assert status == 200
    assert payload["symbol"] == "PEER"
    assert payload["sectorCodes"] == ["AUTO"]
    assert payload["row"]["sectorName"] == "Auto"
    assert payload["row"]["trend"] == "Uptrend"
    assert payload["row"]["trendState"] == "UPTREND"
    assert "OVERVIEW_TREND_FALLBACK" in payload["row"]["warnings"]


def test_exact_symbol_lookup_reuses_snapshot_parse_and_symbol_index(monkeypatch, tmp_path):
    snapshot_path = tmp_path / "sector_rotation_v3_stocks_latest.json"
    snapshot_path.write_text(
        json.dumps({
            "runId": "run-cache-1",
            "asOfDate": "2026-07-22",
            "sectors": {
                "IT": {
                    "sectorName": "IT",
                    "rows": [{"symbol": "TCS"}, {"symbol": "INFY"}],
                },
            },
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(service, "SNAPSHOT_PATH", snapshot_path)
    parent_state = {"runId": "run-cache-1", "asOfDate": "2026-07-22"}
    monkeypatch.setattr(
        service,
        "read_latest_published_v3_snapshot",
        lambda: dict(parent_state),
    )

    calls = {"loads": 0, "overview": 0, "supplement": 0}
    original_loads = json.loads

    def counted_loads(value):
        calls["loads"] += 1
        return original_loads(value)

    def overview():
        calls["overview"] += 1
        return {}

    def supplement(memberships, **_kwargs):
        calls["supplement"] += 1
        return memberships

    monkeypatch.setattr(service.json, "loads", counted_loads)
    monkeypatch.setattr(service, "_overview_rows_by_symbol", overview)
    monkeypatch.setattr(service, "_supplement_memberships_from_staging", supplement)

    first, first_status = service.get_sector_rotation_v3_stock_symbol("TCS")
    second, second_status = service.get_sector_rotation_v3_stock_symbol("INFY")

    assert first_status == 200
    assert second_status == 200
    assert first["row"]["symbol"] == "TCS"
    assert second["row"]["symbol"] == "INFY"
    assert calls == {"loads": 1, "overview": 1, "supplement": 1}

    snapshot_path.write_text(
        json.dumps({
            "runId": "run-cache-2",
            "asOfDate": "2026-07-23",
            "generation": "second-snapshot-with-a-different-size",
            "sectors": {
                "IT": {
                    "sectorName": "IT",
                    "rows": [{"symbol": "WIPRO"}],
                },
            },
        }),
        encoding="utf-8",
    )
    parent_state.update({"runId": "run-cache-2", "asOfDate": "2026-07-23"})

    refreshed, refreshed_status = service.get_sector_rotation_v3_stock_symbol("WIPRO")

    assert refreshed_status == 200
    assert refreshed["row"]["symbol"] == "WIPRO"
    assert calls == {"loads": 2, "overview": 2, "supplement": 2}


def test_page_uses_v3_trend_state_for_the_legacy_trend_field(monkeypatch):
    monkeypatch.setattr(
        service,
        "read_sector_rotation_v3_stock_snapshot",
        lambda: {
            "runId": "run-4",
            "asOfDate": "2026-07-22",
            "sectors": {
                "AUTO": {
                    "rows": [{"symbol": "MIXED", "trend": "Uptrend", "trendState": "SIDEWAYS"}],
                }
            },
        },
    )
    monkeypatch.setattr(
        service,
        "read_latest_published_v3_snapshot",
        lambda: {"runId": "run-4", "asOfDate": "2026-07-22", "rows": [{"sectorCode": "AUTO"}]},
    )
    monkeypatch.setattr(service, "_load_memberships", lambda: {"MIXED": ["AUTO"]})
    monkeypatch.setattr(
        service,
        "_supplement_memberships_from_staging",
        lambda memberships, **_kwargs: memberships,
    )

    payload, status = get_sector_rotation_v3_stock_page("AUTO", page=1, page_size=25)

    assert status == 200
    assert payload["rows"][0]["trend"] == "Sideways"
    assert payload["rows"][0]["trendDirection"] == "Sideways"


def test_page_corrects_a_published_all_n_row_before_the_overview_fallback(monkeypatch):
    monkeypatch.setattr(
        service,
        "read_sector_rotation_v3_stock_snapshot",
        lambda: {
            "runId": "run-ema-page",
            "asOfDate": "2026-07-22",
            "sectors": {
                "AUTO": {
                    "rows": [{
                        "symbol": "ALL_N",
                        "trendState": "DATA_WEAK",
                        "price": 75,
                        "ema20": 80,
                        "ema50": 90,
                        "ema100": 100,
                        "ema200": 110,
                        "stockEdgeScore": 10,
                        "coverage": 40,
                        "confidence": "LOW",
                    }],
                }
            },
        },
    )
    monkeypatch.setattr(
        service,
        "read_latest_published_v3_snapshot",
        lambda: {"runId": "run-ema-page", "asOfDate": "2026-07-22", "rows": [{"sectorCode": "AUTO"}]},
    )
    monkeypatch.setattr(service, "_overview_rows_by_symbol", lambda: {"ALL_N": {"trend": "Uptrend"}})
    monkeypatch.setattr(service, "_supplement_memberships_from_staging", lambda memberships, **_kwargs: memberships)

    payload, status = get_sector_rotation_v3_stock_page("AUTO", page=1, page_size=25)

    assert status == 200
    assert payload["rows"][0]["trendState"] == "DOWNTREND"
    assert payload["rows"][0]["trend"] == "Downtrend"


def test_page_backfills_current_sector_members_when_snapshot_run_is_stale(monkeypatch):
    monkeypatch.setattr(
        service,
        "read_sector_rotation_v3_stock_snapshot",
        lambda: {
            "runId": "old-run",
            "asOfDate": "2026-07-22",
            "sectors": {"AUTO": {"sectorName": "Auto", "rows": [{"symbol": "LEADER"}]}},
        },
    )
    monkeypatch.setattr(
        service,
        "read_latest_published_v3_snapshot",
        lambda: {"runId": "new-run", "asOfDate": "2026-07-22", "rows": [{"sectorCode": "AUTO"}]},
    )
    monkeypatch.setattr(
        service,
        "_supplement_memberships_from_staging",
        lambda memberships, **_kwargs: {"LEADER": ["AUTO"], "PEER": ["AUTO"]},
    )
    monkeypatch.setattr(service, "_load_memberships", lambda: {"LEADER": ["AUTO"]})
    monkeypatch.setattr(
        service,
        "_overview_rows_by_symbol",
        lambda: {"PEER": {"stock": "PEER", "price": 250.0, "ltc_date": "22-07-2026", "trend": "Uptrend"}},
    )

    payload, status = get_sector_rotation_v3_stock_page("AUTO", page=1, page_size=25)

    assert status == 200
    assert payload["runId"] == "new-run"
    assert payload["totalCount"] == 2
    assert payload["isStale"] is True
    assert {row["symbol"] for row in payload["rows"]} == {"LEADER", "PEER"}
    peer = next(row for row in payload["rows"] if row["symbol"] == "PEER")
    assert peer["trend"] == "Uptrend"
    assert peer["trendState"] == "UPTREND"


def test_staging_snapshot_backfills_incomplete_reference_map(monkeypatch, tmp_path):
    snapshot_path = tmp_path / "sector_rotation_tables.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "tables": [
                    {
                        "tableName": "NSE_NIFTY_PAPER_PACKAGING_STAGING",
                        "sectorCode": "PAPER_PACKAGING",
                        "stockCount": 3,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    class FakeCursor:
        arraysize = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query):
            assert "NSE_NIFTY_PAPER_PACKAGING_STAGING" in query

        def fetchall(self):
            return [("JKPAPER",), ("WESTCOAST",), ("RUCHIRA",)]

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

        def close(self):
            return None

    monkeypatch.setattr(service, "SECTOR_TABLES_SNAPSHOT_PATH", snapshot_path)
    monkeypatch.setattr(service, "get_oracle_connection", lambda: FakeConnection())

    memberships = service._supplement_memberships_from_staging(
        {"JKPAPER": ["PAPER_PACKAGING"]}
    )

    assert memberships == {
        "JKPAPER": ["PAPER_PACKAGING"],
        "WESTCOAST": ["PAPER_PACKAGING"],
        "RUCHIRA": ["PAPER_PACKAGING"],
    }
