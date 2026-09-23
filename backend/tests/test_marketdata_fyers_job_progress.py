from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import services.marketdata_service as service


def test_fyers_job_progress_updates_from_direct_batch_logs():
    job = {
        "id": "job-1",
        "stage": "batch",
        "status": "running",
        "message": "Batch job started.",
        "started_at": "2026-06-02T00:00:00Z",
        "updated_at": "2026-06-02T00:00:00Z",
        "finished_at": None,
        "stats": {"inserted": 0, "skipped": 0, "failed": 0, "errors": 0},
        "logs": [],
    }

    service._update_fyers_job_progress_from_log(
        job,
        "[INFO] FYERS direct batch started. symbols=778 start=2026-06-02 end=2026-06-02 file_storage=disabled",
    )
    service._update_fyers_job_progress_from_log(job, "[INFO] Processing 7/778: NSE:AAVAS-EQ (resolution=1D)")
    service._update_fyers_job_progress_from_log(job, "Inserted 1 rows, Updated 0 rows for NSE:AAVAS-EQ into Oracle DB")

    assert job["currentSymbol"] == "NSE:AAVAS-EQ"
    assert job["stats"]["total"] == 778
    assert job["stats"]["nifty500_total"] == 778
    assert job["stats"]["processed"] == 7
    assert job["stats"]["completed"] == 7
    assert job["stats"]["inserted"] == 1
    assert job["stats"]["rows_loaded"] == 1
    assert "NSE:AAVAS-EQ" in job["message"]


def test_fyers_job_progress_counts_failed_symbol_logs():
    job = {
        "id": "job-1",
        "stage": "batch",
        "status": "running",
        "message": "Batch job started.",
        "started_at": "2026-06-02T00:00:00Z",
        "updated_at": "2026-06-02T00:00:00Z",
        "finished_at": None,
        "stats": {"inserted": 0, "skipped": 0, "failed": 0, "errors": 0},
        "logs": [],
    }

    service._update_fyers_job_progress_from_log(job, "[ERROR] NSE:BAD-EQ failed: invalid symbol")

    assert job["currentSymbol"] == "NSE:BAD-EQ"
    assert job["stats"]["failed"] == 1
    assert job["stats"]["errors"] == 1
    assert job["stats"]["completed"] == 1
    assert job["message"] == "FYERS symbol failed: NSE:BAD-EQ"


def test_fyers_job_progress_counts_skipped_symbol_logs():
    job = {
        "id": "job-1",
        "stage": "batch",
        "status": "running",
        "message": "Batch job started.",
        "started_at": "2026-06-02T00:00:00Z",
        "updated_at": "2026-06-02T00:00:00Z",
        "finished_at": None,
        "stats": {"inserted": 0, "skipped": 0, "failed": 0, "errors": 0},
        "logs": [],
    }

    service._update_fyers_job_progress_from_log(job, "[INFO] Processing 2/778: NSE:BAD-EQ (resolution=1D)")
    service._update_fyers_job_progress_from_log(job, "[WARN] NSE:BAD-EQ skipped: No candle data returned by FYERS")

    assert job["currentSymbol"] == "NSE:BAD-EQ"
    assert job["stats"]["completed"] == 2
    assert job["stats"]["skipped"] == 1
    assert job["message"] == "FYERS symbol skipped: NSE:BAD-EQ"


def test_fyers_job_progress_tracks_gap_aware_single_stock_logs():
    job = {
        "id": "job-1",
        "stage": "batch",
        "status": "running",
        "message": "Batch job started.",
        "started_at": "2026-06-02T00:00:00Z",
        "updated_at": "2026-06-02T00:00:00Z",
        "finished_at": None,
        "stats": {"inserted": 0, "skipped": 0, "failed": 0, "errors": 0},
        "logs": [],
    }

    service._update_fyers_job_progress_from_log(
        job,
        "[SINGLE_STOCK_SYNC] symbol=NSE:ITC-EQ status=COVERAGE_CHECK from=1998-01-01 to=2026-07-02 existing_rows=100 missing_ranges=2 missing_estimated_days=30",
    )
    service._update_fyers_job_progress_from_log(
        job,
        "[SINGLE_STOCK_SYNC] symbol=NSE:ITC-EQ fetched_rows=25 range=2026-06-01..2026-07-02",
    )
    service._update_fyers_job_progress_from_log(
        job,
        "[SINGLE_STOCK_SYNC] symbol=NSE:ITC-EQ failed_range=2026-01-01..2026-01-02 error=temporary timeout",
    )
    service._update_fyers_job_progress_from_log(
        job,
        "[SINGLE_STOCK_SYNC] db_merge symbol=NSE:ITC-EQ selected_start_date=1998-01-01 selected_end_date=2026-07-02 file_storage=disabled api_records_count=25 final_records_count=125 inserted=20 updated=3 skipped=102 failed_ranges=1",
    )

    assert job["currentSymbol"] == "NSE:ITC-EQ"
    assert job["stats"]["existing_rows"] == 100
    assert job["stats"]["missing_ranges_count"] == 2
    assert job["stats"]["missing_estimated_days"] == 30
    assert job["stats"]["fetched_rows"] == 25
    assert job["stats"]["inserted_rows"] == 20
    assert job["stats"]["updated_rows"] == 3
    assert job["stats"]["skipped_existing_rows"] == 102
    assert job["stats"]["failed_ranges_count"] == 1
    assert job["message"] == "Merged FYERS rows: NSE:ITC-EQ"


def test_fyers_batch_symbols_loader_accepts_extensionless_csv_config(monkeypatch, tmp_path):
    symbol_file = tmp_path / "symbols_nifty500.csv"
    symbol_file.write_text("symbol\nNSE:360ONE-EQ\nNSE:3MINDIA-EQ\n", encoding="utf-8")
    monkeypatch.setattr(
        service,
        "_load_fyers_direct_config",
        lambda _project_dir: {"SYMBOLS_CSV": str(tmp_path / "symbols_nifty500")},
    )

    symbols = service._load_fyers_batch_symbols(tmp_path)

    assert symbols == ["NSE:360ONE-EQ", "NSE:3MINDIA-EQ"]


def test_fyers_job_log_hides_bulk_symbol_lists_from_ui_tail():
    job = {
        "id": "job-1",
        "stage": "batch",
        "status": "running",
        "message": "Batch job started.",
        "started_at": "2026-06-02T00:00:00Z",
        "updated_at": "2026-06-02T00:00:00Z",
        "finished_at": None,
        "stats": {"inserted": 0, "skipped": 0, "failed": 0, "errors": 0},
        "logs": [],
    }

    service._append_job_log(job, "[INFO] Input symbols: NSE:TIMKEN-EQ, NSE:TIPSMUSIC-EQ")
    service._append_job_log(job, "[INFO] Normalized symbols: NSE:TIMKEN-EQ, NSE:TIPSMUSIC-EQ")
    service._append_job_log(job, "[INFO] Processing 1/778: NSE:TIMKEN-EQ (resolution=1D)")

    assert job["logs"] == ["[INFO] Processing 1/778: NSE:TIMKEN-EQ (resolution=1D)"]


def test_fyers_job_log_keeps_summary_lines_and_hides_backend_diagnostics():
    job = {"logs": []}

    service._append_job_log(job, "[FYERS_SYMBOL_RESOLVE] Input=ACI Clean=ACI Resolved=NSE:ACI-EQ Status=OK")
    service._append_job_log(
        job,
        "[SINGLE_STOCK_SYNC] symbol=NSE:ACI-EQ status=COVERAGE_CHECK from=2026-07-21 to=2026-07-21 existing_rows=0 missing_ranges=1 missing_estimated_days=1",
    )
    service._append_job_log(job, "[INFO] Processing 18/1188: NSE:ACI-EQ (resolution=1D)")
    service._append_job_log(job, "[INFO] ETA Timestamp: 21-07-2026 07:46:38 PM India Standard Time")
    service._append_job_log(job, "Inserted 1 rows, Updated 0 rows for NSE:ACI-EQ into Oracle DB")

    assert job["logs"] == [
        "[INFO] Processing 18/1188: NSE:ACI-EQ (resolution=1D)",
        "[INFO] ETA Timestamp: 21-07-2026 07:46:38 PM India Standard Time",
        "Inserted 1 rows, Updated 0 rows for NSE:ACI-EQ into Oracle DB",
    ]


def test_fyers_persisted_status_payload_maps_rich_counts_and_symbol_rows():
    payload = service._build_fyers_persisted_job_payload(
        {
            "job_id": "job-1",
            "job_type": "batch",
            "trading_date": "2026-06-17",
            "status": "RUNNING",
            "total_symbols": 8,
            "requested_stop_flag": "N",
            "started_at": "2026-06-17T09:00:00Z",
            "updated_at": "2026-06-17T09:02:00Z",
            "completed_at": None,
            "error_message": None,
        },
        [
            {"symbol": "NSE:A-EQ", "status": "SUCCESS", "status_reason": None, "retry_count": 1, "error_message": None},
            {"symbol": "NSE:B-EQ", "status": "SKIPPED", "status_reason": "Already inserted in target table.", "retry_count": 1, "error_message": None},
            {"symbol": "NSE:C-EQ", "status": "FAILED", "status_reason": "INVALID_SYMBOL", "retry_count": 2, "error_message": "invalid symbol"},
            {"symbol": "NSE:D-EQ", "status": "FAILED", "status_reason": "DB_ERROR", "retry_count": 1, "error_message": "ORA-00001"},
            {"symbol": "NSE:E-EQ", "status": "PENDING", "status_reason": None, "retry_count": 0, "error_message": None},
        ],
    )

    assert payload["tradingDate"] == "2026-06-17"
    assert payload["stats"] == {
        "total": 8,
        "tradingDate": "2026-06-17",
        "inserted": 1,
        "remaining": 4,
        "failed": 0,
        "skipped": 1,
        "insertedSkipped": 1,
        "invalid": 1,
        "errors": 1,
    }
    assert payload["symbols"][0]["Status"] == "INSERTED"
    assert payload["symbols"][1]["Status"] == "SKIPPED_ALREADY_INSERTED"
    assert payload["symbols"][2]["Status"] == "INVALID"
    assert payload["symbols"][3]["Status"] == "ERROR"
    assert payload["symbols"][4]["Status"] == "PENDING"
    assert payload["symbols"][2]["Last Error"] == "invalid symbol"


def test_fyers_status_mapping_keeps_no_data_rerunnable_as_failed():
    assert service._canonical_fyers_symbol_status(
        "FAILED_NO_DATA",
        "NO_DATA",
        "No candle data returned by FYERS",
    ) == "FAILED"


def test_fyers_skipped_symbols_include_only_actionable_non_inserted_rows(monkeypatch):
    monkeypatch.setattr(
        service,
        "_load_fyers_symbol_rows",
        lambda job_id, statuses=None, limit=2000: [
            {"symbol": "NSE:A-EQ", "status": "SUCCESS", "status_reason": None, "retry_count": 1, "error_message": None},
            {"symbol": "NSE:B-EQ", "status": "SKIPPED", "status_reason": "Already inserted in target table.", "retry_count": 1, "error_message": None},
            {"symbol": "NSE:C-EQ", "status": "FAILED", "status_reason": "INVALID_SYMBOL", "retry_count": 2, "error_message": "invalid symbol"},
        ],
        raising=False,
    )

    payload = service.fyers_get_skipped_symbols("job-1")

    assert payload["jobId"] == "job-1"
    assert payload["total"] == 2
    assert [row["Symbol"] for row in payload["symbols"]] == ["NSE:B-EQ", "NSE:C-EQ"]
