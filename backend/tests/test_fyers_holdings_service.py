from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import services.fyers_holdings_service as service


CSV_SAMPLE = """Report Title,Holding_statements Report,,,,,,,,
Date,10/3/2026,,,,,,,,
Client Name,POTLA CHOUDAMMA,,,,,,,,
Client ID,XP24006,,,,,,,,
PAN,BWSPC5680F,,,,,,,,
Download Timestamp,11/03/2026 17:09:30 IST,,,,,,,,
,,,,,,,,
Total Invested,\"2,18,210.31\",,,,,,,,
Total Current,\"1,60,313.54\",,,,,,,,
Profit & loss,\"-57,896.77\",,,,,,,,
Unrealised P&L %,-26.53,,,,,,,,
,,,,,,,,
Name,Qty,Buy price,Invested value,Current value,Unrealised P&L,Unrealised P&L %,Previous close,ISIN
NSE:TANLA-EQ,72,551.58,\"39,713.76\",\"31,539.60\",\"-8,174.16\",-20.58,438.05,INE483C01032
NSE:IOC-EQ,1,159.48,159.48,159.94,0.46,0.29,159.94,INE242A01010
"""


def test_parse_holdings_csv_extracts_metadata_and_rows():
    payload = service.parse_holdings_csv_text(
        CSV_SAMPLE,
        source_filename="FYERS_holding_statements_XP24006_2026-03-10.csv",
        source_path=r"C:\\Users\\admin\\Downloads\\FYERS_holding_statements_XP24006_2026-03-10.csv",
    )

    assert payload["metadata"]["clientId"] == "XP24006"
    assert payload["metadata"]["clientName"] == "POTLA CHOUDAMMA"
    assert payload["metadata"]["reportDate"].isoformat() == "2026-03-10"
    assert payload["metadata"]["downloadTimestamp"].isoformat(sep=" ", timespec="seconds") == "2026-03-11 17:09:30"
    assert float(payload["metadata"]["totalInvested"]) == 218210.31
    assert payload["rowCount"] == 2
    assert payload["rows"][0]["symbolCode"] == "TANLA"
    assert payload["rows"][0]["seriesCode"] == "EQ"
    assert float(payload["rows"][0]["currentValue"]) == 31539.60
    assert payload["stableFieldKeys"] == list(service.STATIC_REPORT_FIELDS)


def test_decimal_parser_accepts_broker_currency_and_percentage_text():
    assert service._decimal_or_none("₹1,23,456.78") == service.Decimal("123456.78")
    assert service._decimal_or_none("-₹399.94") == service.Decimal("-399.94")
    assert service._decimal_or_none("+₹62.54") == service.Decimal("62.54")
    assert service._decimal_or_none("-17.63%") == service.Decimal("-17.63")
    assert service._decimal_or_none("(+0.13%)") == service.Decimal("0.13")
    assert service._decimal_or_none("(399.94)") == service.Decimal("-399.94")


def test_recalculate_holding_pnl_uses_ltp_for_total_and_previous_close_for_day():
    row = {
        "symbolCode": "BALKRISIND",
        "quantity": service.Decimal("12"),
        "buyPrice": service.Decimal("2790.83"),
        "investedValue": service.Decimal("33489.96"),
        "currentValue": service.Decimal("26514.60"),
        "unrealisedPnl": service.Decimal("-6975.36"),
        "unrealisedPnlPct": service.Decimal("-20.83"),
        "price": service.Decimal("2208.30"),
        "previousClose": service.Decimal("2205.40"),
        "tradingDate": "2026-05-22",
    }

    result = service.recalculate_holding_pnl(row)

    assert result["investedValueRecalculated"] == 33489.96
    assert result["currentValueRecalculated"] == 26499.6
    assert result["totalPnlRecalculated"] == -6990.36
    assert result["totalPnlPercentRecalculated"] == -20.87
    assert result["dayPnlRecalculated"] == 34.8
    assert result["dayPnlPercentRecalculated"] == 0.13
    assert result["differenceAmount"] == -15.0
    assert result["status"] == "MISMATCH"


def test_recalculate_holding_pnl_handles_missing_previous_close_neutrally():
    row = {
        "symbolCode": "TANLA",
        "quantity": service.Decimal("72"),
        "buyPrice": service.Decimal("551.58"),
        "currentValue": service.Decimal("37339.20"),
        "unrealisedPnl": service.Decimal("-2374.56"),
        "unrealisedPnlPct": service.Decimal("-5.98"),
        "price": service.Decimal("518.60"),
    }

    result = service.recalculate_holding_pnl(row)

    assert result["dayPnlRecalculated"] is None
    assert result["dayPnlPercentRecalculated"] is None
    assert result["status"] == "MISSING_PREVIOUS_CLOSE"


def test_recalculate_holding_pnl_positive_sample_uses_avg_price_denominator():
    row = {
        "symbolCode": "GAEL",
        "quantity": service.Decimal("118"),
        "buyPrice": service.Decimal("161.87"),
        "investedValue": service.Decimal("19100.66"),
        "currentValue": service.Decimal("19285.92"),
        "unrealisedPnl": service.Decimal("185.26"),
        "unrealisedPnlPct": service.Decimal("0.97"),
        "price": service.Decimal("162.40"),
    }

    result = service.recalculate_holding_pnl(row)

    assert result["investedValueRecalculated"] == 19100.66
    assert result["currentValueRecalculated"] == 19163.2
    assert result["totalPnlRecalculated"] == 62.54
    assert result["totalPnlPercentRecalculated"] == 0.33


def test_reconcile_holdings_returns_symbol_report_and_summary(monkeypatch):
    class _Conn:
        def close(self):
            return None

    raw_rows = [
        {
            "holdingId": 1,
            "importId": 10,
            "clientId": "XP24006",
            "symbolRaw": "NSE:BALKRISIND-EQ",
            "symbolCode": "BALKRISIND",
            "quantity": service.Decimal("12"),
            "buyPrice": service.Decimal("2790.83"),
            "investedValue": service.Decimal("33489.96"),
            "currentValue": service.Decimal("26514.60"),
            "unrealisedPnl": service.Decimal("-6975.36"),
            "unrealisedPnlPct": service.Decimal("-20.83"),
            "previousClose": service.Decimal("2205.40"),
        }
    ]

    def hydrate_prices(conn, rows, **kwargs):
        rows[0]["price"] = service.Decimal("2208.30")
        rows[0]["priceSource"] = "TEST_LTP"
        rows[0]["previousCloseSource"] = "CSV_PRICE"
        return (0, 1, 0)

    monkeypatch.setattr(service, '_require_oracledb', lambda: None)
    monkeypatch.setattr(service, 'get_oracle_connection', lambda: _Conn())
    monkeypatch.setattr(service, '_ensure_tables_exist', lambda conn: None)
    monkeypatch.setattr(service, '_resolve_client_id', lambda conn, client_id: "XP24006")
    monkeypatch.setattr(service, '_fetch_current_rows', lambda conn, client_id: raw_rows)
    monkeypatch.setattr(service, '_apply_previous_close_priority', hydrate_prices)

    result = service.reconcile_holdings({"clientId": "XP24006"})

    assert result["summary"]["totalSymbolsChecked"] == 1
    assert result["summary"]["mismatchedSymbolsCount"] == 1
    assert result["summary"]["missingPreviousCloseCount"] == 0
    assert result["summary"]["totalInvestedValue"] == 33489.96
    assert result["summary"]["totalCurrentValue"] == 26499.6
    assert result["rows"][0]["serialNumber"] == 1
    assert result["rows"][0]["symbol"] == "BALKRISIND"
    assert result["rows"][0]["status"] == "MISMATCH"


def test_reconcile_holdings_uses_portfolio_pnl_percent_not_average(monkeypatch):
    class _Conn:
        def close(self):
            return None

    raw_rows = [
        {
            "holdingId": 1,
            "importId": 10,
            "clientId": "XP24006",
            "symbolRaw": "NSE:BIG-EQ",
            "symbolCode": "BIG",
            "quantity": service.Decimal("10"),
            "buyPrice": service.Decimal("1000"),
            "investedValue": service.Decimal("10000"),
            "currentValue": service.Decimal("9000"),
            "unrealisedPnl": service.Decimal("-1000"),
            "unrealisedPnlPct": service.Decimal("-10"),
        },
        {
            "holdingId": 2,
            "importId": 10,
            "clientId": "XP24006",
            "symbolRaw": "NSE:SMALL-EQ",
            "symbolCode": "SMALL",
            "quantity": service.Decimal("1"),
            "buyPrice": service.Decimal("100"),
            "investedValue": service.Decimal("100"),
            "currentValue": service.Decimal("150"),
            "unrealisedPnl": service.Decimal("50"),
            "unrealisedPnlPct": service.Decimal("50"),
        },
    ]

    def hydrate_prices(conn, rows, **kwargs):
        rows[0]["price"] = service.Decimal("900")
        rows[0]["priceSource"] = "TEST_LTP"
        rows[1]["price"] = service.Decimal("150")
        rows[1]["priceSource"] = "TEST_LTP"
        return (0, 0, 0)

    monkeypatch.setattr(service, '_require_oracledb', lambda: None)
    monkeypatch.setattr(service, 'get_oracle_connection', lambda: _Conn())
    monkeypatch.setattr(service, '_ensure_tables_exist', lambda conn: None)
    monkeypatch.setattr(service, '_resolve_client_id', lambda conn, client_id: "XP24006")
    monkeypatch.setattr(service, '_fetch_current_rows', lambda conn, client_id: raw_rows)
    monkeypatch.setattr(service, '_apply_previous_close_priority', hydrate_prices)

    result = service.reconcile_holdings({"clientId": "XP24006"})

    assert result["summary"]["totalPnl"] == -950.0
    assert result["summary"]["totalPnlPercent"] == -9.41


def test_get_holdings_summary_uses_live_totals_as_authoritative_values(monkeypatch):
    class _Conn:
        def close(self):
            return None

    latest_import = {
        "importId": 121,
        "reportTitle": "Holding statements report",
        "reportDate": service.date(2026, 5, 22),
        "clientName": "POTLA CHOUDAMMA",
        "clientId": "XP24006",
        "pan": "BWSPC5680F",
        "downloadTimestamp": service.datetime(2026, 5, 24, 6, 55, 6),
        "totalInvested": service.Decimal("237173.48"),
        "totalCurrent": service.Decimal("195601.60"),
        "profitLoss": service.Decimal("-41571.88"),
        "unrealisedPnlPct": service.Decimal("-17.53"),
    }
    live_totals = {
        "rowCount": 10,
        "totalInvested": 237173.48,
        "totalCurrent": 195472.27,
        "profitLoss": -41701.21,
        "unrealisedPnlPct": -17.58,
    }

    monkeypatch.setattr(service, '_require_oracledb', lambda: None)
    monkeypatch.setattr(service, '_ensure_tables_exist', lambda conn: None)
    monkeypatch.setattr(service, '_resolve_client_id', lambda conn, client_id: "XP24006")
    monkeypatch.setattr(service, '_fetch_latest_import_row', lambda conn, client_id=None: latest_import)
    monkeypatch.setattr(service, '_fetch_live_totals', lambda conn, client_id: live_totals)

    result = service.get_holdings_summary({"clientId": "XP24006"}, connection=_Conn())
    summary = result["summary"]
    stable_fields = {item["key"]: item["value"] for item in summary["stableFields"]}

    assert summary["totalInvested"] == 237173.48
    assert summary["totalCurrent"] == 195472.27
    assert summary["profitLoss"] == -41701.21
    assert summary["unrealisedPnlPct"] == -17.58
    assert stable_fields["totalInvested"] == 237173.48
    assert stable_fields["totalCurrent"] == 195472.27
    assert stable_fields["profitLoss"] == -41701.21
    assert stable_fields["unrealisedPnlPct"] == -17.58


def test_fetch_live_totals_uses_current_table_aggregate_query():
    class _Cursor:
        def __init__(self):
            self.executed = []

        def execute(self, sql, params):
            self.executed.append((sql, params))

        def fetchone(self):
            return (
                2,
                service.Decimal("10100"),
                service.Decimal("9200"),
                service.Decimal("-900"),
                service.Decimal("9100"),
                service.Decimal("100"),
                2,
            )

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Conn:
        def __init__(self):
            self.cursor_instance = _Cursor()

        def cursor(self):
            return self.cursor_instance

    conn = _Conn()

    result = service._fetch_live_totals(conn, "XP24006")

    assert result == {
        "rowCount": 2,
        "totalInvested": 10100.0,
        "totalCurrent": 9200.0,
        "profitLoss": -900.0,
        "unrealisedPnlPct": -8.91,
        "dayPnl": 100.0,
        "dayPnlPct": 1.1,
    }
    assert conn.cursor_instance.executed
    sql, params = conn.cursor_instance.executed[0]
    assert service.FYERS_HOLDINGS_CURRENT_TABLE in sql
    assert params == {"client_id": "XP24006"}


def test_plan_current_holding_changes_splits_insert_update_unchanged_delete():
    existing_rows = [
        {
            "holdingId": 1,
            "clientId": "XP24006",
            "clientName": "POTLA CHOUDAMMA",
            "pan": "BWSPC5680F",
            "symbolRaw": "NSE:TANLA-EQ",
            "exchangeCode": "NSE",
            "symbolCode": "TANLA",
            "seriesCode": "EQ",
            "quantity": service.Decimal("72"),
            "buyPrice": service.Decimal("551.58"),
            "investedValue": service.Decimal("39713.76"),
            "currentValue": service.Decimal("31539.60"),
            "unrealisedPnl": service.Decimal("-8174.16"),
            "unrealisedPnlPct": service.Decimal("-20.58"),
            "previousClose": service.Decimal("438.05"),
            "isin": "INE483C01032",
        },
        {
            "holdingId": 2,
            "clientId": "XP24006",
            "clientName": "POTLA CHOUDAMMA",
            "pan": "BWSPC5680F",
            "symbolRaw": "NSE:OLD-EQ",
            "exchangeCode": "NSE",
            "symbolCode": "OLD",
            "seriesCode": "EQ",
            "quantity": service.Decimal("1"),
            "buyPrice": service.Decimal("100"),
            "investedValue": service.Decimal("100"),
            "currentValue": service.Decimal("110"),
            "unrealisedPnl": service.Decimal("10"),
            "unrealisedPnlPct": service.Decimal("10"),
            "previousClose": service.Decimal("110"),
            "isin": "OLDISIN",
        },
    ]
    imported_rows = [
        {
            "symbolRaw": "NSE:TANLA-EQ",
            "exchangeCode": "NSE",
            "symbolCode": "TANLA",
            "seriesCode": "EQ",
            "quantity": service.Decimal("72"),
            "buyPrice": service.Decimal("551.58"),
            "investedValue": service.Decimal("39713.76"),
            "currentValue": service.Decimal("31539.60"),
            "unrealisedPnl": service.Decimal("-8174.16"),
            "unrealisedPnlPct": service.Decimal("-20.58"),
            "previousClose": service.Decimal("438.05"),
            "isin": "INE483C01032",
            "clientId": "XP24006",
            "clientName": "POTLA CHOUDAMMA",
            "pan": "BWSPC5680F",
        },
        {
            "symbolRaw": "NSE:IOC-EQ",
            "exchangeCode": "NSE",
            "symbolCode": "IOC",
            "seriesCode": "EQ",
            "quantity": service.Decimal("1"),
            "buyPrice": service.Decimal("159.48"),
            "investedValue": service.Decimal("159.48"),
            "currentValue": service.Decimal("159.94"),
            "unrealisedPnl": service.Decimal("0.46"),
            "unrealisedPnlPct": service.Decimal("0.29"),
            "previousClose": service.Decimal("159.94"),
            "isin": "INE242A01010",
            "clientId": "XP24006",
            "clientName": "POTLA CHOUDAMMA",
            "pan": "BWSPC5680F",
        },
    ]

    plan = service.plan_current_holding_changes(existing_rows, imported_rows, replace_missing=True)

    assert plan["stats"] == {
        "inserted": 1,
        "updated": 0,
        "unchanged": 1,
        "deleted": 1,
        "errors": 0,
        "rows": 2,
    }
    assert plan["insert"][0]["after"]["symbolCode"] == "IOC"
    assert plan["unchanged"][0]["before"]["symbolCode"] == "TANLA"
    assert plan["delete"][0]["before"]["symbolCode"] == "OLD"


def test_plan_current_holding_changes_ignores_immutable_import_fields():
    existing_rows = [
        {
            "holdingId": 1,
            "symbolRaw": "NSE:TANLA-EQ",
            "exchangeCode": "NSE",
            "symbolCode": "TANLA",
            "seriesCode": "EQ",
            "quantity": service.Decimal("72"),
            "buyPrice": service.Decimal("551.58"),
            "investedValue": service.Decimal("39713.76"),
            "currentValue": service.Decimal("31539.60"),
            "unrealisedPnl": service.Decimal("-8174.16"),
            "unrealisedPnlPct": service.Decimal("-20.58"),
            "previousClose": service.Decimal("438.05"),
            "isin": "INE483C01032",
        }
    ]
    imported_rows = [
        {
            "symbolRaw": "NSE:TANLA-BE",
            "exchangeCode": "NSE",
            "symbolCode": "TANLA",
            "seriesCode": "BE",
            "quantity": service.Decimal("72"),
            "buyPrice": service.Decimal("551.58"),
            "investedValue": service.Decimal("39713.76"),
            "currentValue": service.Decimal("31539.60"),
            "unrealisedPnl": service.Decimal("-8174.16"),
            "unrealisedPnlPct": service.Decimal("-20.58"),
            "previousClose": service.Decimal("438.05"),
            "isin": "DIFFERENTISIN",
        }
    ]

    plan = service.plan_current_holding_changes(existing_rows, imported_rows, replace_missing=True)

    assert plan["stats"]["updated"] == 0
    assert plan["stats"]["unchanged"] == 1


def test_plan_current_holding_changes_normalizes_numeric_types():
    existing_rows = [
        {
            "holdingId": 1,
            "symbolCode": "TANLA",
            "quantity": 72.0,
            "buyPrice": 551.58,
            "investedValue": 39713.76,
            "currentValue": 34236.0,
            "unrealisedPnl": -5477.76,
            "unrealisedPnlPct": -13.79,
            "previousClose": 475.5,
        }
    ]
    imported_rows = [
        {
            "symbolCode": "TANLA",
            "quantity": service.Decimal("72"),
            "buyPrice": service.Decimal("551.58"),
            "investedValue": service.Decimal("39713.76"),
            "currentValue": service.Decimal("34236.00"),
            "unrealisedPnl": service.Decimal("-5477.76"),
            "unrealisedPnlPct": service.Decimal("-13.79"),
            "previousClose": service.Decimal("475.50"),
        }
    ]

    plan = service.plan_current_holding_changes(existing_rows, imported_rows, replace_missing=True)

    assert plan["stats"]["updated"] == 0
    assert plan["stats"]["unchanged"] == 1


def test_import_holdings_skips_duplicate_existing_data(monkeypatch):
    class _Conn:
        def commit(self):
            raise AssertionError('commit should not be called for duplicate skips')

        def rollback(self):
            return None

        def close(self):
            return None

    parsed = {
        "metadata": {
            "clientId": "XP24006",
            "reportDate": service.date(2026, 5, 18),
            "downloadTimestamp": service.datetime(2026, 5, 19, 6, 54, 13),
        },
        "rows": [{"symbolCode": "TANLA"}],
        "stableFieldKeys": list(service.STATIC_REPORT_FIELDS),
        "stableFields": [],
        "file": {"sourceFilename": "holdings.csv", "sourceHash": "hash-1"},
    }

    monkeypatch.setattr(service, '_require_oracledb', lambda: None)
    monkeypatch.setattr(service, '_read_csv_payload', lambda payload: ('csv', 'holdings.csv', ''))
    monkeypatch.setattr(service, 'parse_holdings_csv_text', lambda *args, **kwargs: parsed)
    monkeypatch.setattr(service, 'get_oracle_connection', lambda: _Conn())
    monkeypatch.setattr(service, '_ensure_tables_exist', lambda conn: None)
    monkeypatch.setattr(
        service,
        '_fetch_current_rows',
        lambda conn, client_id: [{
            "holdingId": 1,
            "symbolCode": "TANLA",
            "reportDate": service.date(2026, 5, 18),
            "downloadTimestamp": service.datetime(2026, 5, 19, 6, 54, 13),
            "sourceFilename": "holdings.csv",
            "sourceHash": "hash-1",
        }],
    )
    monkeypatch.setattr(
        service,
        'plan_current_holding_changes',
        lambda existing_rows, imported_rows, replace_missing=True: {
            "insert": [],
            "update": [],
            "unchanged": [{"before": existing_rows[0], "after": imported_rows[0]}],
            "delete": [],
            "stats": {"inserted": 0, "updated": 0, "unchanged": 1, "deleted": 0, "errors": 0, "rows": 1},
        },
    )
    monkeypatch.setattr(service, '_fetch_latest_import_row', lambda conn, client_id=None: {"importId": 42})
    monkeypatch.setattr(service, 'get_holdings_summary', lambda payload, connection=None: {"summary": {"clientId": "XP24006"}})
    monkeypatch.setattr(
        service,
        '_insert_import_row',
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('duplicate import should not insert import rows')),
    )

    result = service.import_holdings({"csvText": "dummy", "filename": "holdings.csv"})

    assert result["duplicateSkipped"] is True
    assert result["message"] == "Already existing data, skipped"
    assert result["importId"] == 42
    assert result["stats"]["rows"] == 1


def test_current_rows_match_import_metadata_rejects_stale_download_timestamp():
    metadata = {
        "reportDate": service.date(2026, 5, 18),
        "downloadTimestamp": service.datetime(2026, 5, 19, 6, 54, 13),
    }
    file_info = {"sourceFilename": "holdings.csv", "sourceHash": "hash-1"}
    rows = [{
        "reportDate": service.date(2026, 5, 18),
        "downloadTimestamp": service.datetime(2026, 4, 13, 6, 53, 24),
        "sourceFilename": "holdings.csv",
        "sourceHash": "hash-1",
    }]

    assert service._current_rows_match_import_metadata(rows, metadata, file_info) is False


def test_apply_previous_close_priority_hydrates_holdings_enrichment(monkeypatch):
    class _Conn:
        def cursor(self):
            raise AssertionError('patched enrichment helpers should not use this cursor')

    rows = [
        {
            "symbolRaw": "NSE:TANLA-EQ",
            "symbolCode": "TANLA",
            "buyPrice": service.Decimal("551.58"),
            "previousClose": service.Decimal("498.05"),
        }
    ]

    monkeypatch.setattr(service, '_fetch_sector_snapshot_map', lambda conn, symbols: {})
    monkeypatch.setattr(service, '_fetch_latest_raw_ltp_map', lambda conn, symbols, **kwargs: {})
    monkeypatch.setattr(
        service,
        '_fetch_raw_technical_range_map',
        lambda conn, symbols: {
            "TANLA": {
                "volumeAbove20": False,
                "volume": 396772,
                "volumeRatio20": 0.21,
                "avgVolume20": 1865203,
                "fiftyTwoWeekLow": 365.9,
                "fiftyTwoWeekHigh": 766.0,
                "ath": 2096.75,
                "athDate": service.date(2022, 1, 17),
            }
        },
    )
    monkeypatch.setattr(
        service,
        '_fetch_asura_signal_map',
        lambda conn, symbols: {
            "TANLA": {
                "score": 80,
                "scoreSort": 80,
                "ema20": 450,
                "ema50": 430,
                "ema100": 410,
                "ema200": 390,
                "macdAboveZero": True,
                "rsiAbove50": True,
                "adxAbove25": False,
                "atrAbove14": True,
                "supportDisplay": None,
                "resistanceDisplay": None,
                "trendDirection": "UPTREND",
            }
        },
    )
    monkeypatch.setattr(service, '_fetch_latest_ema_previous_close_map', lambda conn, symbols: {"TANLA": 494.8})
    monkeypatch.setattr(service, '_fetch_computed_technical_map', lambda conn, symbols: {})
    monkeypatch.setattr(
        service,
        '_fetch_manual_sr_display_map',
        lambda conn, symbols, price_by_symbol: {
            "TANLA": {"supportDisplay": "S1:462.8", "resistanceDisplay": "R1:521.2"}
        },
    )

    ema_matches, csv_matches, missing = service._apply_previous_close_priority(_Conn(), rows)

    assert (ema_matches, csv_matches, missing) == (0, 1, 0)
    assert rows[0]["previousClose"] == service.Decimal("498.05")
    assert rows[0]["previousCloseSource"] == "CSV_PRICE"
    assert rows[0]["price"] == 494.8
    assert rows[0]["volumeAbove20"] is False
    assert rows[0]["fiftyTwoWeekLow"] == 365.9
    assert rows[0]["fiftyTwoWeekHigh"] == 766.0
    assert rows[0]["ath"] == 2096.75
    assert rows[0]["athDate"] == service.date(2022, 1, 17)
    assert rows[0]["score"] == 80
    assert rows[0]["ema20Flag"] == "Y"
    assert rows[0]["macdAboveZero"] is True
    assert rows[0]["adxAbove25"] is False
    assert rows[0]["supportDisplay"] == "S1:462.8"
    assert rows[0]["resistanceDisplay"] == "R1:521.2"
    assert rows[0]["trendDirection"] == "UPTREND"


def test_apply_previous_close_priority_uses_computed_technical_fallback(monkeypatch):
    class _Conn:
        def cursor(self):
            raise AssertionError('patched enrichment helpers should not use this cursor')

    rows = [
        {
            "symbolRaw": "NSE:BALKRISIND-EQ",
            "symbolCode": "BALKRISIND",
            "buyPrice": service.Decimal("2400"),
            "previousClose": service.Decimal("2148.90"),
        }
    ]

    monkeypatch.setattr(service, '_fetch_sector_snapshot_map', lambda conn, symbols: {})
    monkeypatch.setattr(service, '_fetch_latest_raw_ltp_map', lambda conn, symbols, **kwargs: {})
    monkeypatch.setattr(service, '_fetch_raw_technical_range_map', lambda conn, symbols: {})
    monkeypatch.setattr(service, '_fetch_asura_signal_map', lambda conn, symbols: {})
    monkeypatch.setattr(service, '_fetch_latest_ema_previous_close_map', lambda conn, symbols: {"BALKRISIND": 2148.9})
    monkeypatch.setattr(
        service,
        '_fetch_computed_technical_map',
        lambda conn, symbols: {
            "BALKRISIND": {
                "price": 2148.9,
                "ema20": 2100.0,
                "ema50": 2050.0,
                "ema100": 2000.0,
                "ema200": 1900.0,
                "ema20Flag": "Y",
                "ema50Flag": "Y",
                "ema100Flag": "Y",
                "ema200Flag": "Y",
                "macdAboveZero": True,
                "rsiAbove50": True,
                "adxAbove25": False,
                "atrAbove14": True,
                "volumeAbove20": True,
                "rsi": 58.4,
                "macdHist": 1.2,
                "adx14": 22.0,
                "atr14": 45.0,
            }
        },
    )
    monkeypatch.setattr(service, '_fetch_manual_sr_display_map', lambda conn, symbols, price_by_symbol: {})

    def fake_master_score(row, **kwargs):
        row["score"] = 42
        row["scoreSort"] = 42
        row["trendDirection"] = "Uptrend"
        return row

    monkeypatch.setattr(service, 'enrich_row_with_master_score_fields', fake_master_score)

    service._apply_previous_close_priority(_Conn(), rows)

    assert rows[0]["ema20"] == 2100.0
    assert rows[0]["ema20Flag"] == "Y"
    assert rows[0]["macdAboveZero"] is True
    assert rows[0]["rsiAbove50"] is True
    assert rows[0]["atrAbove14"] is True
    assert rows[0]["score"] == 42
    assert rows[0]["trendDirection"] == "Uptrend"


def test_apply_previous_close_priority_prefers_raw_ltp_over_computed_close(monkeypatch):
    class _Conn:
        def cursor(self):
            raise AssertionError('patched enrichment helpers should not use this cursor')

    rows = [
        {
            "symbolRaw": "NSE:GAEL-EQ",
            "symbolCode": "GAEL",
            "buyPrice": service.Decimal("161.87"),
            "previousClose": service.Decimal("165.32"),
            "reportDate": "2026-05-22",
        }
    ]

    monkeypatch.setattr(service, '_fetch_fyers_live_quote_map', lambda symbols: {})
    monkeypatch.setattr(service, '_fetch_sector_snapshot_map', lambda conn, symbols: {})
    monkeypatch.setattr(service, '_fetch_raw_technical_range_map', lambda conn, symbols: {})
    monkeypatch.setattr(service, '_fetch_asura_signal_map', lambda conn, symbols: {})
    monkeypatch.setattr(service, '_fetch_latest_ema_previous_close_map', lambda conn, symbols: {})
    monkeypatch.setattr(
        service,
        '_fetch_latest_raw_ltp_map',
        lambda conn, symbols, **kwargs: (
            {
                "GAEL": {
                    "price": service.Decimal("162.40"),
                    "tradingDate": "2026-05-22",
                    "priceSource": "NSE_RAW_LTP",
                }
            }
            if kwargs.get("min_trading_date") == service.date(2026, 5, 22)
            else {}
        ),
    )
    monkeypatch.setattr(
        service,
        '_fetch_computed_technical_map',
        lambda conn, symbols: {
            "GAEL": {
                "price": 163.44,
                "tradingDate": "2026-05-22",
                "ema20": 150.0,
            }
        },
    )
    monkeypatch.setattr(service, '_fetch_manual_sr_display_map', lambda conn, symbols, price_by_symbol: {})

    service._apply_previous_close_priority(_Conn(), rows, include_live_quotes=True)

    assert rows[0]["price"] == service.Decimal("162.40")
    assert rows[0]["priceSource"] == "NSE_RAW_LTP"
    assert rows[0]["tradingDate"] == "2026-05-22"


def test_update_current_row_refreshes_import_metadata_and_isin():
    captured = {}

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params):
            captured["sql"] = sql
            captured["params"] = params

    class _Conn:
        def cursor(self):
            return _Cursor()

    metadata = {
        "clientName": "POTLA CHOUDAMMA",
        "pan": "BWSPC5680F",
        "reportDate": service.date(2026, 5, 18),
        "downloadTimestamp": service.datetime(2026, 5, 19, 6, 54, 13),
    }
    row = {
        "symbolRaw": "NSE:TANLA-EQ",
        "exchangeCode": "NSE",
        "seriesCode": "EQ",
        "quantity": service.Decimal("72"),
        "buyPrice": service.Decimal("551.58"),
        "investedValue": service.Decimal("39713.76"),
        "currentValue": service.Decimal("35859.60"),
        "unrealisedPnl": service.Decimal("-3854.16"),
        "unrealisedPnlPct": service.Decimal("-9.70"),
        "previousClose": service.Decimal("494.80"),
        "isin": "INE483C01032",
    }

    service._update_current_row(
        _Conn(),
        1,
        row,
        import_id=101,
        metadata=metadata,
        file_info={"sourceFilename": "holdings.csv", "sourcePath": "", "sourceHash": "hash"},
    )

    assert "DOWNLOAD_TIMESTAMP = :download_ts" in captured["sql"]
    assert "ISIN = :isin" in captured["sql"]
    assert captured["params"]["client_name"] == "POTLA CHOUDAMMA"
    assert captured["params"]["download_ts"] == service.datetime(2026, 5, 19, 6, 54, 13)
    assert captured["params"]["symbol_raw"] == "NSE:TANLA-EQ"
    assert captured["params"]["isin"] == "INE483C01032"
