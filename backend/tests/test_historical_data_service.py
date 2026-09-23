from pathlib import Path
import datetime as dt
from decimal import Decimal
import io
import json
import re
import sys
import types
import zipfile

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
SERVICES_ROOT = BACKEND_ROOT / "services"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(SERVICES_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICES_ROOT))

sys.modules.setdefault(
    "db_pool",
    types.SimpleNamespace(pool=types.SimpleNamespace(acquire=lambda: None), fetchall_dict=lambda *_args, **_kwargs: []),
)

import services.historical_data_service as service


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
    def __init__(self, *, count_by_table=None, fail_on_delete_table=None):
        self.executed = []
        self._row = None
        self.rowcount = 0
        self.count_by_table = count_by_table or {
            "NSE_NIFTY500_DAILY_RAW_DATA_DEV": 3,
            "NSE_NIFTY500_DAILY_RAW_DATA_ORACLE": 3,
        }
        self.fail_on_delete_table = fail_on_delete_table

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, binds=None):
        self.executed.append((sql, dict(binds or {})))
        normalized = sql.strip().upper()
        target_table = next((table for table in self.count_by_table if table in normalized), None)
        if normalized.startswith("SELECT COUNT(*)"):
            self._row = (self.count_by_table.get(target_table or "", 0),)
            return
        if normalized.startswith("DELETE FROM"):
            if self.fail_on_delete_table and self.fail_on_delete_table in normalized:
                raise RuntimeError("delete failed")
            self.rowcount = self.count_by_table.get(target_table or "", 0)
            self._row = None
            return
        raise AssertionError(f"Unexpected SQL in FakeCursor: {sql}")

    def fetchone(self):
        return self._row


class FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_allowed_tables_and_default_table():
    assert service.DEFAULT_TABLE == "NSE_NIFTY500_DAILY_RAW_DATA_DEV"
    assert service.list_allowed_tables() == [
        "NSE_NIFTY500_DAILY_RAW_DATA_DEV",
        "NSE_NIFTY500_DAILY_RAW_DATA_ORACLE",
    ]


def test_validate_table_name_rejects_invalid_table():
    with pytest.raises(ValueError) as exc:
        service._validate_table_name("DROP_TABLE")
    assert "Invalid table selected" in str(exc.value)


def test_summary_sql_builder_respects_dev_and_oracle_mappings():
    dev_sql = service._build_summary_base_sql("NSE_NIFTY500_DAILY_RAW_DATA_DEV")
    oracle_sql = service._build_summary_base_sql("NSE_NIFTY500_DAILY_RAW_DATA_ORACLE")

    assert "FROM VW_HISTORICAL_DATA_DEV" in dev_sql
    assert "FROM VW_HISTORICAL_DATA_ORACLE" in oracle_sql
    assert "CLOSE_PRICE" in dev_sql
    assert "CLOSE_PRICE" in oracle_sql
    assert "LATEST_TRADING_DATE" in dev_sql
    assert "LATEST_TRADING_DATE" in oracle_sql


def test_summary_includes_trade_date_in_rows(monkeypatch):
    class SummaryCursor:
        def __init__(self):
            self.executed = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, binds=None):
            self.executed.append((sql, dict(binds or {})))

    cursor = SummaryCursor()
    conn = FakeConn(cursor)
    monkeypatch.setattr(service, "pool", FakePool(conn))
    monkeypatch.setattr(service, "fetchall_dict", lambda _cursor: [
        {
            "symbol": "GAEL",
            "trading_days": 100,
            "ipo_date": "2001-02-12",
            "ipo_price": Decimal("0.45"),
            "price": Decimal("150.00"),
            "trade_date": "2026-09-18",
            "latest_trading_date": "2026-09-18",
            "ath": Decimal("200.00"),
            "ath_date": "2026-01-15",
            "existing": Decimal("25.0"),
        },
    ])
    service._summary_cache_clear()

    summary = service.get_summary({
        "table_name": "NSE_NIFTY500_DAILY_RAW_DATA_DEV",
        "page": 1,
        "page_size": 25,
    })

    assert summary["ok"] is True
    assert len(summary["rows"]) == 1
    row = summary["rows"][0]
    assert row["symbol"] == "GAEL"
    assert row["price"] == 150.0
    assert row["trade_date"] == "2026-09-18"
    assert row["latest_trading_date"] == "2026-09-18"


def test_summary_in_memory_search_and_filters(monkeypatch):
    class MultiSummaryCursor:
        def __init__(self):
            self.executed = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, binds=None):
            self.executed.append((sql, dict(binds or {})))

    cursor = MultiSummaryCursor()
    conn = FakeConn(cursor)
    monkeypatch.setattr(service, "pool", FakePool(conn))
    monkeypatch.setattr(service, "fetchall_dict", lambda _cursor: [
        {
            "symbol": "GAEL",
            "trading_days": 100,
            "ipo_date": "2001-02-12",
            "ipo_price": Decimal("0.45"),
            "price": Decimal("150.00"),
            "trade_date": "2026-09-18",
            "latest_trading_date": "2026-09-18",
            "ath": Decimal("200.00"),
            "ath_date": "2026-01-15",
            "existing": Decimal("25.0"),
        },
        {
            "symbol": "RELIANCE",
            "trading_days": 7000,
            "ipo_date": "1998-01-01",
            "ipo_price": Decimal("16.98"),
            "price": Decimal("1226.40"),
            "trade_date": "2026-09-18",
            "latest_trading_date": "2026-09-18",
            "ath": Decimal("3029.00"),
            "ath_date": "2024-06-03",
            "existing": Decimal("28.71"),
        },
        {
            "symbol": "TCS",
            "trading_days": 5000,
            "ipo_date": "2004-08-25",
            "ipo_price": Decimal("120.00"),
            "price": Decimal("4200.00"),
            "trade_date": "2026-09-18",
            "latest_trading_date": "2026-09-18",
            "ath": Decimal("4500.00"),
            "ath_date": "2025-02-10",
            "existing": Decimal("22.0"),
        },
    ])
    service._summary_cache_clear()

    # Query 1: full summary
    res_all = service.get_summary({"table_name": "NSE_NIFTY500_DAILY_RAW_DATA_DEV"})
    assert res_all["total_count"] == 3
    assert len(cursor.executed) == 1

    # Query 2: symbol search in-memory - does NOT query database again!
    res_search = service.get_summary({
        "table_name": "NSE_NIFTY500_DAILY_RAW_DATA_DEV",
        "symbol": "eli",
    })
    assert res_search["total_count"] == 1
    assert res_search["rows"][0]["symbol"] == "RELIANCE"
    assert len(cursor.executed) == 1  # Verify database was NOT hit again!

    # Query 3: min_records filter in-memory
    res_records = service.get_summary({
        "table_name": "NSE_NIFTY500_DAILY_RAW_DATA_DEV",
        "min_records": 5000,
    })
    assert res_records["total_count"] == 2
    assert {r["symbol"] for r in res_records["rows"]} == {"RELIANCE", "TCS"}
    assert len(cursor.executed) == 1  # Still in memory!

    # Query 4: refresh forces database reload
    res_refresh = service.get_summary({
        "table_name": "NSE_NIFTY500_DAILY_RAW_DATA_DEV",
        "refresh": "true",
    })
    assert res_refresh["total_count"] == 3
    assert len(cursor.executed) == 2  # Verify database WAS hit on refresh!



def test_symbol_csv_uses_exact_headers_and_all_rows_in_ascending_date_order(monkeypatch):
    class CsvCursor:
        def __init__(self):
            self.executed = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, binds=None):
            self.executed.append((sql, dict(binds or {})))

    cursor = CsvCursor()
    conn = FakeConn(cursor)
    monkeypatch.setattr(service, "pool", FakePool(conn))
    monkeypatch.setattr(service, "fetchall_dict", lambda _cursor: [
        {
            "symbol": "RELIANCE",
            "trading_date": dt.date(2026, 9, 15),
            "open": Decimal("100.50"),
            "high": Decimal("110.25"),
            "low": Decimal("99.75"),
            "close_price": Decimal("108.00"),
            "volume": Decimal("50000"),
        },
        {
            "symbol": "RELIANCE",
            "trading_date": dt.date(2026, 9, 16),
            "open": Decimal("108.00"),
            "high": Decimal("112.00"),
            "low": Decimal("106.00"),
            "close_price": Decimal("111.50"),
            "volume": Decimal("65000"),
        },
    ])

    filename, csv_content = service.get_symbol_csv(
        "reliance",
        {"table_name": "NSE_NIFTY500_DAILY_RAW_DATA_DEV"},
    )

    assert re.match(r"^RELIANCE_16-09-2026_\d{6}\.csv$", filename)
    assert csv_content.splitlines() == [
        "s.no,symbol,trade_date,open,high,low,close,volume",
        "1,RELIANCE,2026-09-15,100.50,110.25,99.75,108.00,50000",
        "2,RELIANCE,2026-09-16,108.00,112.00,106.00,111.50,65000",
    ]
    sql, binds = cursor.executed[0]
    assert "VW_HISTORICAL_DATA_DEV" in sql
    assert "ORDER BY d.TRADING_DATE ASC" in sql
    assert binds == {"symbol": "RELIANCE"}

    archive_name, archive_content = service.get_symbol_export_bundle(
        "reliance",
        {"table_name": "NSE_NIFTY500_DAILY_RAW_DATA_DEV"},
    )
    assert re.match(r"^RELIANCE_16-09-2026_\d{6}\.zip$", archive_name)
    stem = archive_name[:-4]
    with zipfile.ZipFile(io.BytesIO(archive_content)) as archive:
        assert archive.namelist() == [
            f"{stem}.csv",
            f"{stem}.json",
            f"{stem}.txt",
        ]
        assert archive.read(f"{stem}.csv").decode("utf-8").splitlines()[0] == (
            "s.no,symbol,trade_date,open,high,low,close,volume"
        )
        json_rows = json.loads(archive.read(f"{stem}.json").decode("utf-8"))
        assert json_rows[0] == {
            "s.no": 1,
            "symbol": "RELIANCE",
            "trade_date": "2026-09-15",
            "open": "100.50",
            "high": "110.25",
            "low": "99.75",
            "close": "108.00",
            "volume": "50000",
        }
        assert archive.read(f"{stem}.txt").decode("utf-8").splitlines()[0] == (
            "s.no\tsymbol\ttrade_date\topen\thigh\tlow\tclose\tvolume"
        )


def test_delete_symbols_deletes_from_dev_and_oracle_in_one_transaction(monkeypatch):
    fake_cursor = FakeCursor()
    fake_conn = FakeConn(fake_cursor)
    monkeypatch.setattr(service, "pool", FakePool(fake_conn))

    result = service.delete_symbols({
        "table_name": "NSE_NIFTY500_DAILY_RAW_DATA_DEV",
        "symbols": ["NAUKRI", "BSE"],
        "confirm_text": "DELETE",
    })

    assert result["ok"] is True
    assert result["success"] is True
    assert result["deleted_symbols"] == 2
    assert result["matched_rows"] == 6
    assert result["deleted_rows"] == 6
    assert result["dev_deleted_rows"] == 3
    assert result["oracle_deleted_rows"] == 3
    assert fake_conn.commits == 1
    delete_sql = [sql for sql, _binds in fake_cursor.executed if sql.strip().upper().startswith("DELETE FROM")]
    assert len(delete_sql) == 2
    assert any("NSE_NIFTY500_DAILY_RAW_DATA_DEV" in sql for sql in delete_sql)
    assert any("NSE_NIFTY500_DAILY_RAW_DATA_ORACLE" in sql for sql in delete_sql)
    dev_delete_sql = next(sql for sql in delete_sql if "NSE_NIFTY500_DAILY_RAW_DATA_DEV" in sql)
    delete_binds = [binds for sql, binds in fake_cursor.executed if "NSE_NIFTY500_DAILY_RAW_DATA_DEV" in sql and sql.strip().upper().startswith("DELETE FROM")][0]
    assert "UPPER(TRIM(SYMBOL)) IN (" in dev_delete_sql
    assert ":sym_0" in dev_delete_sql and ":sym_1" in dev_delete_sql
    assert delete_binds["sym_0"] == "NAUKRI"
    assert delete_binds["sym_1"] == "BSE"


def test_delete_symbols_rolls_back_when_second_table_delete_fails(monkeypatch):
    fake_cursor = FakeCursor(fail_on_delete_table="NSE_NIFTY500_DAILY_RAW_DATA_ORACLE")
    fake_conn = FakeConn(fake_cursor)
    monkeypatch.setattr(service, "pool", FakePool(fake_conn))

    with pytest.raises(RuntimeError) as exc:
        service.delete_symbols({
            "table_name": "NSE_NIFTY500_DAILY_RAW_DATA_DEV",
            "symbols": ["NAUKRI"],
            "confirm_text": "DELETE",
        })

    assert "Backend error while deleting data" in str(exc.value)
    assert fake_conn.commits == 0
    assert fake_conn.rollbacks == 1


def test_delete_rows_uses_oracle_symb_column_and_date_binds(monkeypatch):
    fake_cursor = FakeCursor()
    fake_conn = FakeConn(fake_cursor)
    monkeypatch.setattr(service, "pool", FakePool(fake_conn))

    result = service.delete_rows({
        "table_name": "NSE_NIFTY500_DAILY_RAW_DATA_ORACLE",
        "symbol": "NAUKRI",
        "trading_dates": ["2025-04-01", "2025-04-02"],
        "confirm_text": "DELETE",
    })

    assert result["ok"] is True
    assert result["matched_rows"] == 3
    assert result["deleted_rows"] == 3
    assert fake_conn.commits == 1
    delete_sql = [sql for sql, _binds in fake_cursor.executed if sql.strip().upper().startswith("DELETE FROM")][0]
    delete_binds = [binds for sql, binds in fake_cursor.executed if sql.strip().upper().startswith("DELETE FROM")][0]
    assert "NSE_NIFTY500_DAILY_RAW_DATA_ORACLE" in delete_sql
    assert "UPPER(TRIM(SYMBOL)) = :symbol" in delete_sql
    assert "TRADING_DATE IN (" in delete_sql
    assert ":dt_0" in delete_sql and ":dt_1" in delete_sql
    assert delete_binds["symbol"] == "NAUKRI"


def test_delete_confirmation_text_required():
    with pytest.raises(ValueError) as exc:
        service.delete_symbols({
            "table_name": "NSE_NIFTY500_DAILY_RAW_DATA_DEV",
            "symbols": ["NAUKRI"],
            "confirm_text": "NO",
        })
    assert "Delete confirmation failed" in str(exc.value)
