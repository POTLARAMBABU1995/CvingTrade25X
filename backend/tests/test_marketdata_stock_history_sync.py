from pathlib import Path
import sys
import types


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

import services.marketdata_service as service
import routes.marketdata as marketdata_route


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
    def __init__(self):
        self.callprocs = []
        self.executed = []
        self._row = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def callproc(self, name, params=None):
        self.callprocs.append((name, params))

    def execute(self, sql, binds=None):
        self.executed.append((sql, dict(binds or {})))
        normalized = " ".join(str(sql).split()).upper()
        if "SELECT LAST_LOAD_TS FROM STOCK_SYNC_CTRL" in normalized:
            self._row = ("2026-06-22 10:15:59",)
            return
        self._row = None

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


def test_merge_latest_reconciles_both_targets_and_reports_validation(monkeypatch):
    fake_cursor = FakeCursor()
    fake_conn = FakeConn(fake_cursor)
    monkeypatch.setattr(service, "pool", FakePool(fake_conn))
    monkeypatch.setattr(service, "_read_dbms_output", lambda _cur: ["PR_SYNC_STOCK_NEW_ROWS summary:"])
    monkeypatch.setattr(service, "_parse_sync_output", lambda _lines: {"window_rows": 250869})
    monkeypatch.setattr(
        service,
        "_reconcile_stock_history_targets",
        lambda _cur: {
            "dev_inserted": 250869,
            "dev_updated": 12,
            "dev_skipped": 4,
            "oracle_inserted": 250869,
            "oracle_updated": 12,
            "oracle_skipped": 4,
            "stock_history_unique_key_count": 250885,
            "dev_total_row_count": 3230645,
            "oracle_total_row_count": 3230645,
            "dev_source_missing_count": 0,
            "oracle_source_missing_count": 0,
            "dev_source_changed_count": 0,
            "oracle_source_changed_count": 0,
            "oracle_missing_in_dev_count": 0,
            "dev_missing_in_oracle_count": 0,
            "dev_oracle_row_count_match": True,
            "targets_fully_synced": True,
        },
    )
    monkeypatch.setattr(
        service,
        "_cleanup_merged_stock_eod_history",
        lambda _cur, retention_days: {
            "cleanup_retention_days": retention_days,
            "cleanup_deleted_source_rows": 250869,
        },
    )

    payload = service.merge_latest()

    assert payload["ok"] is True
    assert payload["inserted_dev"] == 250869
    assert payload["updated_dev"] == 12
    assert payload["inserted_oracle"] == 250869
    assert payload["updated_oracle"] == 12
    assert payload["dev_oracle_row_count_match"] is True
    assert payload["targets_fully_synced"] is True
    assert payload["cleanup_deleted_source_rows"] == 250869
    assert fake_conn.commits == 1
    assert fake_conn.rollbacks == 0
    assert ("dbms_output.enable", None) in fake_cursor.callprocs
    assert any(name == service.SYNC_PROC for name, _params in fake_cursor.callprocs)


def test_stock_history_reconcile_merge_does_not_update_on_clause_symbol(monkeypatch):
    missing_counts = iter([1, 0])
    changed_counts = iter([1, 0])

    class MergeCursor:
        def __init__(self):
            self.executed = []
            self.rowcount = 0

        def execute(self, sql, binds=None):
            self.executed.append(str(sql))
            if str(sql).lstrip().upper().startswith("MERGE INTO"):
                self.rowcount = 2

    cursor = MergeCursor()
    monkeypatch.setattr(service, "_count_source_rows", lambda *_args, **_kwargs: 5)
    monkeypatch.setattr(service, "_count_source_missing_rows", lambda *_args, **_kwargs: next(missing_counts))
    monkeypatch.setattr(service, "_count_source_changed_rows", lambda *_args, **_kwargs: next(changed_counts))

    payload = service._reconcile_stock_history_target(
        cursor,
        source_table="STOCK_EOD_HISTORY",
        target_table="NSE_NIFTY500_DAILY_RAW_DATA_DEV",
        target_label="dev",
    )

    merge_sql = next(sql for sql in cursor.executed if sql.lstrip().upper().startswith("MERGE INTO"))
    normalized_merge_sql = " ".join(merge_sql.upper().split())
    assert "UPPER(TRIM(H.SYMBOL)) AS SYMBOL" in normalized_merge_sql
    assert "TRUNC(H.TRADE_DATE) AS TRADE_DATE" in normalized_merge_sql
    assert "TGT.SYMBOL = SRC.SYMBOL" in normalized_merge_sql
    assert "TGT.TRADING_DATE = SRC.TRADE_DATE" in normalized_merge_sql
    update_block = merge_sql.upper().split("WHEN MATCHED THEN UPDATE SET", 1)[1].split("WHERE", 1)[0]
    assert "TGT.SYMBOL" not in update_block
    assert payload["dev_inserted"] == 1
    assert payload["dev_updated"] == 1


def test_target_parity_sync_normalizes_symbol_and_trading_date(monkeypatch):
    missing_counts = iter([2, 0])

    class ParityCursor:
        def __init__(self):
            self.executed = []
            self.rowcount = 0

        def execute(self, sql, binds=None):
            self.executed.append(str(sql))
            if str(sql).lstrip().upper().startswith("INSERT INTO"):
                self.rowcount = 2

    cursor = ParityCursor()
    monkeypatch.setattr(service, "_count_target_missing_rows", lambda *_args, **_kwargs: next(missing_counts))

    payload = service._reconcile_target_pair_missing_rows(
        cursor,
        source_table="NSE_NIFTY500_DAILY_RAW_DATA_ORACLE",
        target_table="NSE_NIFTY500_DAILY_RAW_DATA_DEV",
        source_label="oracle",
        target_label="dev",
    )

    insert_sql = next(sql for sql in cursor.executed if sql.lstrip().upper().startswith("INSERT INTO"))
    normalized_insert_sql = " ".join(insert_sql.upper().split())
    assert "SELECT UPPER(TRIM(SRC.SYMBOL))" in normalized_insert_sql
    assert "TRUNC(SRC.TRADING_DATE)" in normalized_insert_sql
    assert "UPPER(TRIM(TGT.SYMBOL)) = UPPER(TRIM(SRC.SYMBOL))" in normalized_insert_sql
    assert "TRUNC(TGT.TRADING_DATE) = TRUNC(SRC.TRADING_DATE)" in normalized_insert_sql
    assert payload["dev_inserted_from_oracle"] == 2


def test_merge_status_treats_updated_rows_as_latest_data_available():
    assert marketdata_route._merge_has_new_rows({
        "inserted_dev": 0,
        "updated_dev": 3,
        "inserted_oracle": 0,
        "updated_oracle": 4,
    }) is True


def test_auto_merge_availability_uses_full_validation_not_only_latest_date(monkeypatch):
    class AvailabilityCursor:
        def __init__(self):
            self._row = None

        def execute(self, sql, binds=None):
            normalized = " ".join(str(sql).split()).upper()
            if "SELECT TO_CHAR(MAX(TRADE_DATE), 'YYYY-MM-DD')" in normalized:
                self._row = ("2026-06-22",)
                return
            if "SELECT COUNT(*) FROM STOCK_EOD_HISTORY WHERE TRUNC(TRADE_DATE) = TRUNC((SELECT MAX(TRADE_DATE)" in normalized:
                self._row = (54,)
                return
            if "SELECT TO_CHAR(MAX(TRADING_DATE), 'YYYY-MM-DD') FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV" in normalized:
                self._row = ("2026-06-22",)
                return
            if "SELECT TO_CHAR(MAX(TRADING_DATE), 'YYYY-MM-DD') FROM NSE_NIFTY500_DAILY_RAW_DATA_ORACLE" in normalized:
                self._row = ("2026-06-22",)
                return
            raise AssertionError(f"Unexpected SQL: {sql}")

        def fetchone(self):
            return self._row

    monkeypatch.setattr(service, "_resolve_stock_eod_table_name", lambda: "STOCK_EOD_HISTORY")
    monkeypatch.setattr(service, "_resolve_marketdata_oracle_sync_table", lambda: "NSE_NIFTY500_DAILY_RAW_DATA_ORACLE")
    monkeypatch.setattr(service, "_detect_date_column", lambda _cur, _table: "TRADING_DATE")
    monkeypatch.setattr(service, "_safe_latest_pending_rows", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(
        service,
        "_collect_stock_history_sync_validation",
        lambda _cur: {
            "dev_source_missing_count": 0,
            "oracle_source_missing_count": 0,
            "dev_source_changed_count": 0,
            "oracle_source_changed_count": 0,
            "oracle_missing_in_dev_count": 15939,
            "dev_missing_in_oracle_count": 0,
            "dev_oracle_row_count_match": False,
            "targets_fully_synced": False,
        },
    )

    payload = service._auto_merge_availability(AvailabilityCursor())

    assert payload["merge_required"] is True
    assert payload["pending_dev_rows"] == 15939
    assert payload["pending_oracle_rows"] == 0
    assert payload["dev_oracle_row_count_match"] is False
