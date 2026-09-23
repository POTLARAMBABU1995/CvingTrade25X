import datetime as dt
from pathlib import Path
import sys

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import services.marketdata_service as service


@pytest.fixture(autouse=True)
def _clear_failed_symbols_cache():
    service.invalidate_fyers_failed_symbols_cache("test_start")
    yield
    service.invalidate_fyers_failed_symbols_cache("test_end")


class _FakeCursor:
    def __init__(self, conn):
        self._conn = conn
        self.sql = ""
        self.binds = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, binds=None):
        self.sql = str(sql)
        self.binds = dict(binds or {})
        self._conn.executed.append((self.sql, self.binds))


class _FakeConnection:
    def __init__(self):
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return _FakeCursor(self)

    def commit(self):
        return None


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return self._conn


def _write_skipped_symbols_csv(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "skipped_symbols.csv").write_text(
        "\n".join([
            "SYMBOL,REASON,TIMESTAMP,ERROR,START_DATE,END_DATE,YEAR_SIG,SCOPE",
            "NSE:SBIN-EQ,fetch_failed,2026-05-24T09:10:00,Timeout while fetching,2026-05-24,2026-05-24,2026,CSV_BATCH",
            "NSE:RELIANCE-EQ,fetch_failed,2026-05-25T10:00:00,Timeout while fetching,2026-05-25,2026-05-25,2026,CSV_BATCH",
            "NSE:RELIANCE-EQ,fetch_failed,2026-05-26T18:00:00,Timeout while fetching,2026-05-26,2026-05-26,2026,CSV_BATCH",
            "NSE:TCS-EQ,fetch_failed,2026-05-26T18:01:00,ValueError: FYERS rejected symbol 'NSE:TCS-EQ'.,2026-05-26,2026-05-26,2026,CSV_BATCH",
        ]),
        encoding="utf-8",
    )


def test_failed_symbols_list_reads_failed_table_rows_even_when_dev_has_matches(monkeypatch):
    conn = _FakeConnection()
    monkeypatch.setattr(service, "pool", _FakePool(conn))
    monkeypatch.setattr(service, "_ensure_fyers_tracking_tables", lambda _conn: None)

    def fake_fetchall_dict(cur):
        normalized_sql = " ".join(cur.sql.upper().split())
        if "FROM FYERS_API_SKIPED_REJECTED_SYMBOLS T" in normalized_sql:
            return [{
                "row_id": 101,
                "symbol": "NSE:RELIANCE-EQ",
                "fyers_symbol": "NSE:RELIANCE-EQ",
                "trading_date": "2026-05-22",
                "from_date": "2026-05-22",
                "to_date": "2026-05-22",
                "status": "FAILED",
                "reason": "missing_from_fyers",
                "error_message": "no data returned",
                "rerun_status": "PENDING",
                "last_rerun_ts": None,
                "created_at": "2026-05-22T10:00:00",
                "updated_at": "2026-05-22T10:05:00",
            }]
        if "COUNT(DISTINCT TRUNC(D.TRADING_DATE))" in normalized_sql:
            return [{"month_key": "2026-05-01", "month_max_td_count": 17}]
        if "NSE_NIFTY500_DAILY_RAW_DATA_DEV" in normalized_sql:
            return []
        return [{
            "row_id": 101,
            "symbol": "RELIANCE",
            "trading_date": "2026-05-22",
            "reason_error_message": "missing_from_fyers - no data returned",
            "td_count": 5,
            "symbol_month_failed_td_count": 5,
            "month_max_td_count": 17,
            "td_flag": "NORMAL",
        }]

    monkeypatch.setattr(service, "fetchall_dict", fake_fetchall_dict)

    payload = service.list_fyers_failed_symbols({"limit": 25, "offset": 0, "symbol": "NSE:RELIANCE-EQ"})

    assert payload["totalCount"] == 1
    assert payload["rows"] == [{
        "rowId": 101,
        "symbol": "RELIANCE",
        "tradingDate": "2026-05-22",
        "reasonErrorMessage": "missing_from_fyers - no data returned",
        "tdCount": 1,
        "symbolMonthFailedTdCount": 1,
        "monthMaxTdCount": 17,
        "tdFlag": "NORMAL",
    }]
    row_keys = set(payload["rows"][0])
    assert "fyersSymbol" not in row_keys
    assert "sourceMode" not in row_keys
    assert "fromDate" not in row_keys
    assert "toDate" not in row_keys
    assert "rerunCount" not in row_keys

    executed_sql = "\n".join(sql for sql, _binds in conn.executed).upper()
    assert "NSE_NIFTY500_DAILY_RAW_DATA_DEV" in executed_sql
    assert "COUNT(DISTINCT TRUNC(D.TRADING_DATE))" in executed_sql
    assert "SYMBOL_KEY_LIKE" in executed_sql
    assert "DEV_DT_0" not in executed_sql


def test_failed_symbols_list_builds_dataset_once_and_derives_repeating(monkeypatch):
    conn = _FakeConnection()
    monkeypatch.setattr(service, "pool", _FakePool(conn))
    monkeypatch.setattr(service, "_ensure_fyers_tracking_tables", lambda _conn: None)

    call_counter = {"count": 0}

    def fake_build_rows(_conn, _filters, *, missing_in_dev_only=True):
        assert missing_in_dev_only is False
        call_counter["count"] += 1
        return [
            {
                "row_id": 11,
                "symbol": "RELIANCE",
                "trading_date": dt.date(2026, 5, 1),
                "status": "FAILED",
                "rerun_status": "PENDING",
                "reason_error_message": "fetch_failed - timeout",
                "td_count": 2,
                "symbol_month_failed_td_count": 2,
                "month_max_td_count": 20,
                "td_flag": "NORMAL",
            },
            {
                "row_id": 12,
                "symbol": "RELIANCE",
                "trading_date": dt.date(2026, 5, 2),
                "status": "API_ERROR",
                "rerun_status": "FAILED",
                "reason_error_message": "api_error - 429",
                "td_count": 2,
                "symbol_month_failed_td_count": 2,
                "month_max_td_count": 20,
                "td_flag": "NORMAL",
            },
            {
                "row_id": 13,
                "symbol": "TCS",
                "trading_date": dt.date(2026, 5, 1),
                "status": "SKIPPED",
                "rerun_status": "SUCCESS",
                "reason_error_message": "no_data",
                "td_count": 1,
                "symbol_month_failed_td_count": 1,
                "month_max_td_count": 20,
                "td_flag": "NORMAL",
            },
        ]

    monkeypatch.setattr(service, "_build_fyers_failed_symbols_read_rows", fake_build_rows)

    payload = service.list_fyers_failed_symbols({"limit": 25, "offset": 0})

    assert call_counter["count"] == 1
    assert payload["totalCount"] == 3
    assert payload["summary"]["totalFailed"] == 2
    assert payload["summary"]["totalSkipped"] == 1
    assert payload["summary"]["pendingRerun"] == 1
    assert payload["summary"]["rerunSuccess"] == 1
    assert payload["summary"]["rerunFailed"] == 1
    assert payload["repeatingSymbols"] == [
        {
            "symbol": "RELIANCE",
            "occurrences": 2,
            "from_date": "2026-05-01",
            "to_date": "2026-05-02",
            "failed_dates": "2026-05-01, 2026-05-02",
        }
    ]


def test_failed_symbols_list_reuses_cached_payload_without_mutation_leak(monkeypatch):
    conn = _FakeConnection()
    monkeypatch.setattr(service, "pool", _FakePool(conn))
    monkeypatch.setattr(service, "_ensure_fyers_tracking_tables", lambda _conn: None)

    call_counter = {"count": 0}

    def fake_build_rows(_conn, _filters, *, missing_in_dev_only=True):
        assert missing_in_dev_only is False
        call_counter["count"] += 1
        return [
            {
                "row_id": 21,
                "symbol": "TCS",
                "trading_date": dt.date(2026, 5, 27),
                "status": "FAILED",
                "rerun_status": "PENDING",
                "reason_error_message": "fetch_failed - timeout",
                "td_count": 1,
                "symbol_month_failed_td_count": 1,
                "month_max_td_count": 20,
                "td_flag": "NORMAL",
            }
        ]

    monkeypatch.setattr(service, "_build_fyers_failed_symbols_read_rows", fake_build_rows)

    first_payload = service.list_fyers_failed_symbols({"limit": 25, "offset": 0})
    first_payload["rows"].append({"symbol": "MUTATED"})
    second_payload = service.list_fyers_failed_symbols({"limit": 25, "offset": 0})

    assert call_counter["count"] == 1
    assert second_payload["totalCount"] == 1
    assert [row["symbol"] for row in second_payload["rows"]] == ["TCS"]


def test_failed_symbols_list_ignores_skipped_symbols_csv_and_uses_oracle(monkeypatch, tmp_path):
    project_dir = tmp_path / "fyers_api_integration"
    (project_dir / "src").mkdir(parents=True)
    data_dir = project_dir / "data"
    _write_skipped_symbols_csv(data_dir)
    conn = _FakeConnection()
    monkeypatch.setattr(service, "FYERS_PROJECT_DIR", str(project_dir))
    monkeypatch.setattr(service, "FYERS_DATA_DIR", str(data_dir))
    monkeypatch.setattr(service, "pool", _FakePool(conn))
    monkeypatch.setattr(service, "_ensure_fyers_tracking_tables", lambda _conn: None)

    def fake_build_rows(_conn, _filters, *, missing_in_dev_only=True):
        assert missing_in_dev_only is False
        return [{
            "row_id": 501,
            "symbol": "ORACLEONLY",
            "trading_date": dt.date(2026, 5, 26),
            "status": "FAILED",
            "rerun_status": "PENDING",
            "reason_error_message": "api_error",
            "td_count": 1,
            "symbol_month_failed_td_count": 1,
            "month_max_td_count": 20,
            "td_flag": "NORMAL",
        }]

    monkeypatch.setattr(service, "_build_fyers_failed_symbols_read_rows", fake_build_rows)

    payload = service.list_fyers_failed_symbols({"limit": 25, "offset": 0})

    assert payload["totalCount"] == 1
    assert payload["summary"]["totalFailed"] == 1
    assert payload["rows"][0]["rowId"] == 501
    assert payload["rows"][0]["symbol"] == "ORACLEONLY"
    assert payload["rows"][0]["tradingDate"] == "2026-05-26"


def test_rerun_all_filtered_does_not_fallback_to_skipped_symbols_csv(monkeypatch, tmp_path):
    project_dir = tmp_path / "fyers_api_integration"
    (project_dir / "src").mkdir(parents=True)
    data_dir = project_dir / "data"
    _write_skipped_symbols_csv(data_dir)
    conn = _FakeConnection()
    captured_runs = []

    monkeypatch.setattr(service, "FYERS_PROJECT_DIR", str(project_dir))
    monkeypatch.setattr(service, "FYERS_DATA_DIR", str(data_dir))
    monkeypatch.setattr(service, "pool", _FakePool(conn))
    monkeypatch.setattr(service, "_ensure_fyers_tracking_tables", lambda _conn: None)
    monkeypatch.setattr(service, "_load_failed_symbol_rows_by_filters", lambda _conn, _filters: [])
    monkeypatch.setattr(service, "_run_fyers_history_auth_probe", lambda **_kwargs: (False, {}))

    def fake_fyers_run_single(payload, line_logger=None, should_stop=None):
        captured_runs.append(payload)
        return {
            "ok": True,
            "results": [
                {"status": "SUCCESS", "input_symbol": symbol}
                for symbol in str(payload.get("symbol") or "").split(",")
                if symbol
            ],
        }

    monkeypatch.setattr(service, "fyers_run_single", fake_fyers_run_single)

    with pytest.raises(ValueError, match="No failed/skipped/rejected symbol rows found"):
        service.rerun_fyers_failed_symbols({"rerunAll": True, "filters": {}, "mode": "SINGLE_STOCK_RERUN_ALL"})

    assert captured_runs == []
