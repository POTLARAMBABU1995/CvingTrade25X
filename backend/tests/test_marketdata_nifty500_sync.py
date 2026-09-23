from io import BytesIO
from pathlib import Path
import sys

from openpyxl import Workbook


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import services.nifty500_sync_service as service


def _write_existing_csv(path: Path, rows: list[str]) -> None:
    payload = "symbol\n" + "\n".join(rows)
    path.write_text(payload + "\n", encoding="utf-8")


def _build_xlsx_bytes(rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    for row in rows:
        worksheet.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


def test_get_nifty500_sync_snapshot_aggregates_existing_counts(monkeypatch, tmp_path):
    csv_path = tmp_path / "symbols_nifty500.csv"
    _write_existing_csv(csv_path, ["NSE:ABC-EQ", "NSE:ABC-EQ", "NSE:XYZ-EQ"])
    monkeypatch.setattr(service, "FYERS_NIFTY500_EXISTING_CSV", str(csv_path))

    payload = service.get_nifty500_sync_snapshot()

    assert payload["existing"]["exists"] is True
    assert payload["existing"]["uniqueCount"] == 2
    assert payload["existing"]["totalCount"] == 2
    assert payload["existing"]["rows"][0]["symbol"] == "ABC"
    assert payload["existing"]["rows"][0]["symbolCount"] == 1
    assert payload["existing"]["rows"][0]["flag"] == "-"


def test_compare_nifty500_sync_marks_new_missing_symbols(monkeypatch, tmp_path):
    csv_path = tmp_path / "symbols_nifty500.csv"
    _write_existing_csv(csv_path, ["NSE:ABC-EQ", "NSE:XYZ-EQ"])
    monkeypatch.setattr(service, "FYERS_NIFTY500_EXISTING_CSV", str(csv_path))

    payload = service.compare_nifty500_sync(
        {
            "filename": "NIFTY500.csv",
            "newCsvContent": "SYMBOL\nABC\nNEWCO\nNEWCO\n",
        }
    )

    assert payload["summary"]["matchedCount"] == 1
    assert payload["summary"]["missingInExistingCount"] == 1
    assert payload["summary"]["existingOnlyCount"] == 1
    assert payload["actions"]["missingInExisting"] == ["NEWCO"]
    assert payload["new"]["rows"][1]["symbol"] == "NEWCO"
    assert payload["new"]["rows"][1]["flag"] == "N"
    assert payload["new"]["rows"][1]["symbolCount"] == 1
    assert payload["new"]["rows"][1]["recommendedAction"] == "Create"
    assert payload["new"]["totalCount"] == 2
    assert payload["new"]["uniqueCount"] == 2
    assert payload["existing"]["rows"][1]["symbol"] == "XYZ"
    assert payload["existing"]["rows"][1]["flag"] == "N"


def test_compare_nifty500_sync_reads_symbol_column_from_uploaded_csv(monkeypatch, tmp_path):
    csv_path = tmp_path / "symbols_nifty500.csv"
    _write_existing_csv(csv_path, ["NSE:ABC-EQ", "NSE:XYZ-EQ"])
    monkeypatch.setattr(service, "FYERS_NIFTY500_EXISTING_CSV", str(csv_path))

    payload = service.compare_nifty500_sync(
        {
            "uploadedFiles": [
                {
                    "filename": "agriculture_sector_symbols47.csv",
                    "content": b"s.no,symbol,MCAP,sector\n1,ABC,100,agriculture\n2,NEWCO,200,agriculture\n",
                }
            ]
        }
    )

    assert payload["summary"]["matchedCount"] == 1
    assert payload["summary"]["missingInExistingCount"] == 1
    assert payload["actions"]["missingInExisting"] == ["NEWCO"]
    assert payload["new"]["rows"][0]["symbol"] == "ABC"
    assert payload["new"]["rows"][1]["symbol"] == "NEWCO"


def test_compare_nifty500_sync_reads_symbol_column_when_header_is_not_first_csv_row(monkeypatch, tmp_path):
    csv_path = tmp_path / "symbols_nifty500.csv"
    _write_existing_csv(csv_path, ["NSE:ABC-EQ", "NSE:XYZ-EQ"])
    monkeypatch.setattr(service, "FYERS_NIFTY500_EXISTING_CSV", str(csv_path))

    payload = service.compare_nifty500_sync(
        {
            "uploadedFiles": [
                {
                    "filename": "sector_symbols_with_title.csv",
                    "content": (
                        b"NIFTY 500 Sector Extract\n"
                        b"S.NO,SYMBOL,MCAP,SECTOR\n"
                        b"1,ABC,100,Agriculture\n"
                        b"2,NEWCO,200,Agriculture\n"
                    ),
                }
            ]
        }
    )

    assert payload["summary"]["matchedCount"] == 1
    assert payload["summary"]["missingInExistingCount"] == 1
    assert payload["actions"]["missingInExisting"] == ["NEWCO"]


def test_compare_nifty500_sync_reads_common_symbol_header_alias_from_csv(monkeypatch, tmp_path):
    csv_path = tmp_path / "symbols_nifty500.csv"
    _write_existing_csv(csv_path, ["NSE:ABC-EQ", "NSE:XYZ-EQ"])
    monkeypatch.setattr(service, "FYERS_NIFTY500_EXISTING_CSV", str(csv_path))

    payload = service.compare_nifty500_sync(
        {
            "uploadedFiles": [
                {
                    "filename": "sector_symbols_with_nse_symbol_header.csv",
                    "content": b"S.NO,NSE Symbol,MCAP,SECTOR\n1,ABC,100,Agriculture\n2,NEWCO,200,Agriculture\n",
                }
            ]
        }
    )

    assert payload["summary"]["matchedCount"] == 1
    assert payload["summary"]["missingInExistingCount"] == 1
    assert payload["actions"]["missingInExisting"] == ["NEWCO"]
    assert [row["symbol"] for row in payload["new"]["rows"]] == ["ABC", "NEWCO"]


def test_compare_nifty500_sync_reads_symbol_column_from_uploaded_xlsx(monkeypatch, tmp_path):
    csv_path = tmp_path / "symbols_nifty500.csv"
    _write_existing_csv(csv_path, ["NSE:ABC-EQ"])
    monkeypatch.setattr(service, "FYERS_NIFTY500_EXISTING_CSV", str(csv_path))

    xlsx_bytes = _build_xlsx_bytes([
        ["S.NO", "SYMBOL", "SECTOR"],
        [1, "ABC", "Alcohol / Breweries"],
        [2, "UBL", "Alcohol / Breweries"],
    ])

    payload = service.compare_nifty500_sync(
        {
            "uploadedFiles": [
                {
                    "filename": "alcohol_breweries_nse_symbols_final.xlsx",
                    "content": xlsx_bytes,
                }
            ]
        }
    )

    assert payload["summary"]["matchedCount"] == 1
    assert payload["summary"]["missingInExistingCount"] == 1
    assert payload["actions"]["missingInExisting"] == ["UBL"]


def test_compare_nifty500_sync_reads_symbol_column_when_header_is_not_first_xlsx_row(monkeypatch, tmp_path):
    csv_path = tmp_path / "symbols_nifty500.csv"
    _write_existing_csv(csv_path, ["NSE:ABC-EQ"])
    monkeypatch.setattr(service, "FYERS_NIFTY500_EXISTING_CSV", str(csv_path))

    xlsx_bytes = _build_xlsx_bytes([
        ["NIFTY 500 Sector Extract"],
        ["S.NO", "SYMBOL", "SECTOR"],
        [1, "ABC", "Alcohol / Breweries"],
        [2, "UBL", "Alcohol / Breweries"],
    ])

    payload = service.compare_nifty500_sync(
        {
            "uploadedFiles": [
                {
                    "filename": "alcohol_breweries_offset_header.xlsx",
                    "content": xlsx_bytes,
                }
            ]
        }
    )

    assert payload["summary"]["matchedCount"] == 1
    assert payload["summary"]["missingInExistingCount"] == 1
    assert payload["actions"]["missingInExisting"] == ["UBL"]


def test_compare_nifty500_sync_reads_common_symbol_header_alias_from_xlsx(monkeypatch, tmp_path):
    csv_path = tmp_path / "symbols_nifty500.csv"
    _write_existing_csv(csv_path, ["NSE:ABC-EQ"])
    monkeypatch.setattr(service, "FYERS_NIFTY500_EXISTING_CSV", str(csv_path))

    xlsx_bytes = _build_xlsx_bytes([
        ["S.NO", "Stock Symbol", "SECTOR"],
        [1, "ABC", "Alcohol / Breweries"],
        [2, "UBL", "Alcohol / Breweries"],
    ])

    payload = service.compare_nifty500_sync(
        {
            "uploadedFiles": [
                {
                    "filename": "alcohol_breweries_stock_symbol_header.xlsx",
                    "content": xlsx_bytes,
                }
            ]
        }
    )

    assert payload["summary"]["matchedCount"] == 1
    assert payload["summary"]["missingInExistingCount"] == 1
    assert payload["actions"]["missingInExisting"] == ["UBL"]


def test_merge_missing_nifty500_symbols_appends_unique_new_rows(monkeypatch, tmp_path):
    csv_path = tmp_path / "symbols_nifty500.csv"
    _write_existing_csv(csv_path, ["NSE:ABC-EQ"])
    monkeypatch.setattr(service, "FYERS_NIFTY500_EXISTING_CSV", str(csv_path))

    payload = service.merge_missing_nifty500_symbols(
        {
            "filename": "NIFTY500.csv",
            "newCsvContent": "SYMBOL\nABC\nNEWCO\nNEWCO\n",
        }
    )

    saved = csv_path.read_text(encoding="utf-8")
    assert payload["summary"]["mergedCount"] == 1
    assert "NSE:NEWCO-EQ" in saved
    assert saved.count("NSE:NEWCO-EQ") == 1
    assert payload["new"]["rows"][1]["flag"] == "Y"


def test_update_and_delete_nifty500_symbol(monkeypatch, tmp_path):
    csv_path = tmp_path / "symbols_nifty500.csv"
    _write_existing_csv(csv_path, ["NSE:ABC-EQ", "NSE:XYZ-EQ"])
    monkeypatch.setattr(service, "FYERS_NIFTY500_EXISTING_CSV", str(csv_path))

    updated = service.update_nifty500_symbol({"originalSymbol": "ABC", "symbol": "ABCD"})
    deleted = service.delete_nifty500_symbol({"symbol": "XYZ"})
    saved = csv_path.read_text(encoding="utf-8")

    assert updated["existing"]["rows"][0]["symbol"] == "ABCD"
    assert deleted["existing"]["rows"][0]["symbol"] == "ABCD"
    assert "NSE:ABCD-EQ" in saved
    assert "NSE:XYZ-EQ" not in saved


def test_update_nifty500_symbol_accepts_updated_symbol_alias(monkeypatch, tmp_path):
    csv_path = tmp_path / "symbols_nifty500.csv"
    _write_existing_csv(csv_path, ["NSE:SCHNEIDER-BE-EQ", "NSE:XYZ-EQ"])
    monkeypatch.setattr(service, "FYERS_NIFTY500_EXISTING_CSV", str(csv_path))

    updated = service.update_nifty500_symbol({
        "originalSymbol": "SCHNEIDER-BE",
        "updatedSymbol": "SCHNEIDER",
    })
    saved = csv_path.read_text(encoding="utf-8")

    assert updated["existing"]["rows"][0]["symbol"] == "SCHNEIDER"
    assert "NSE:SCHNEIDER-EQ" in saved
    assert "NSE:SCHNEIDER-BE-EQ" not in saved


def test_update_nifty500_symbol_rejects_duplicate_target(monkeypatch, tmp_path):
    csv_path = tmp_path / "symbols_nifty500.csv"
    _write_existing_csv(csv_path, ["NSE:ABC-EQ", "NSE:XYZ-EQ"])
    monkeypatch.setattr(service, "FYERS_NIFTY500_EXISTING_CSV", str(csv_path))

    try:
        service.update_nifty500_symbol({"originalSymbol": "ABC", "symbol": "XYZ"})
    except ValueError as exc:
        assert str(exc) == "Symbol XYZ is already available in the existing FYERS CSV."
    else:
        raise AssertionError("Expected duplicate target symbol update to be rejected.")


def test_delete_nifty500_symbol_is_idempotent_for_a_stale_row(monkeypatch, tmp_path):
    csv_path = tmp_path / "symbols_nifty500.csv"
    _write_existing_csv(csv_path, ["NSE:ABC-EQ"])
    monkeypatch.setattr(service, "FYERS_NIFTY500_EXISTING_CSV", str(csv_path))

    result = service.delete_nifty500_symbol({"symbol": "MISSING"})

    assert result["deleted"] is False
    assert result["symbol"] == "MISSING"
    assert result["existing"]["rows"][0]["symbol"] == "ABC"
    assert csv_path.read_text(encoding="utf-8") == "symbol\nNSE:ABC-EQ\n"


def test_nifty500_sync_canonicalizes_obsolete_symbols_and_preserves_series(monkeypatch, tmp_path):
    csv_path = tmp_path / "symbols_nifty500.csv"
    _write_existing_csv(csv_path, ["NSE:MIRCELECTR-EQ", "NSE:SCHLOSS-EQ", "NSE:THELEELA-EQ", "NSE:AIMTRON-EQ"])
    monkeypatch.setattr(service, "FYERS_NIFTY500_EXISTING_CSV", str(csv_path))

    snapshot = service.get_nifty500_sync_snapshot()
    service._write_existing_symbols(csv_path, [row["symbol"] for row in snapshot["existing"]["rows"]])
    saved = csv_path.read_text(encoding="utf-8")

    assert "NSE:ONIDA-EQ" in saved
    assert "NSE:THELEELA-EQ" in saved
    assert saved.count("NSE:THELEELA-EQ") == 1
    assert "NSE:AIMTRON-SM" in saved
    assert "MIRCELECTR" not in saved
    assert "SCHLOSS" not in saved
