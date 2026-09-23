from __future__ import annotations

import csv
import datetime as dt
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

try:
    from . import nifty500_sync_service as nifty500_svc
except ImportError:  # pragma: no cover
    from services import nifty500_sync_service as nifty500_svc  # type: ignore


logger = logging.getLogger(__name__)

_SYMBOL_SPLIT_RE = re.compile(r"[\s,;]+")
_SYMBOL_SANITIZE_RE = re.compile(r"[^A-Z0-9&._-]+")
_NON_ALNUM_RE = re.compile(r"[^A-Z0-9]+")
_HEADER_KEY_RE = re.compile(r"[^a-z0-9]+")
_SYMBOL_HEADER_KEYS = {"symbol", "symbols", "ticker", "tradingsymbol"}
_SAFE_TABLE_NAME_RE = re.compile(r"^[A-Za-z0-9_.$#]+$")

_DEFAULT_SYMBOL_FILE_PATH = (
    os.getenv("SYMBOL_FILE_PATH")
    or os.getenv("FYERS_NIFTY500_EXISTING_CSV")
    or str(nifty500_svc.resolve_existing_csv_path())
).strip()


@dataclass(frozen=True)
class ExistingCsvDatasetConfig:
    dataset_type: str
    download_dir: Path
    parse_trade_date: Callable[[Path], Optional[dt.date]]
    inspect_csv: Optional[Callable[..., Dict[str, Any]]]
    load_csv: Callable[..., Dict[str, Any]]
    use_load_result_for_matching: bool = False


def normalize_symbol(symbol: Any) -> str:
    text = str(symbol or "").strip().strip('"').strip("'").upper()
    if not text:
        return ""
    if ":" in text:
        text = text.split(":", 1)[1]
    text = text.replace(" ", "")
    if text.endswith("-EQ"):
        text = text[:-3]
    if text.endswith(".NS"):
        text = text[:-3]
    cleaned = _SYMBOL_SANITIZE_RE.sub("", text)
    canonical = _NON_ALNUM_RE.sub("", cleaned)
    if canonical == "NIFTY500":
        return ""
    return cleaned


def parse_requested_symbols(input_text: Any) -> List[str]:
    tokens: List[str] = []
    if isinstance(input_text, (list, tuple, set)):
        for item in input_text:
            if isinstance(item, str):
                tokens.extend(_SYMBOL_SPLIT_RE.split(item))
            else:
                tokens.append(str(item or ""))
    else:
        tokens.extend(_SYMBOL_SPLIT_RE.split(str(input_text or "")))

    ordered: List[str] = []
    seen: set[str] = set()
    for token in tokens:
        normalized = normalize_symbol(token)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _header_key(value: str) -> str:
    return _HEADER_KEY_RE.sub("", str(value or "").strip().lower())


def _resolve_symbol_column(fieldnames: Sequence[str]) -> Optional[str]:
    for field in fieldnames:
        if _header_key(field) in _SYMBOL_HEADER_KEYS:
            return field
    return fieldnames[0] if fieldnames else None


def _candidate_symbol_file_paths(symbol_file_path: Optional[str]) -> List[Path]:
    candidates: List[Path] = []
    seen: set[str] = set()

    for raw in (symbol_file_path, _DEFAULT_SYMBOL_FILE_PATH, str(nifty500_svc.resolve_existing_csv_path())):
        text = str(raw or "").strip()
        if not text:
            continue
        base = Path(text).expanduser()
        variants = [base]
        if not base.suffix:
            variants.append(base.with_suffix(".csv"))
        for path in variants:
            key = str(path).lower()
            if key in seen:
                continue
            seen.add(key)
            candidates.append(path)
    return candidates


def resolve_symbol_file_path(symbol_file_path: Optional[str] = None) -> Path:
    candidates = _candidate_symbol_file_paths(symbol_file_path)
    for path in candidates:
        if path.exists() and path.is_file():
            return path
    return candidates[0] if candidates else Path(_DEFAULT_SYMBOL_FILE_PATH).expanduser()


def load_valid_symbols(symbol_file_path: Optional[str] = None) -> set[str]:
    path = resolve_symbol_file_path(symbol_file_path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Valid-symbol file is missing: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames:
            symbol_col = _resolve_symbol_column(reader.fieldnames or [])
            symbols = {
                normalized
                for row in reader
                for normalized in [normalize_symbol((row or {}).get(symbol_col or "", ""))]
                if normalized
            }
            if symbols:
                return symbols

    # Fallback: first-column CSV without a header.
    symbols: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        plain_reader = csv.reader(handle, skipinitialspace=True)
        for row in plain_reader:
            if not row:
                continue
            normalized = normalize_symbol(row[0])
            if normalized:
                symbols.add(normalized)
    return symbols


def find_csv_files(download_dir: Path | str) -> List[Path]:
    root = Path(download_dir).expanduser()
    if not root.exists() or not root.is_dir():
        return []
    files = [path for path in root.rglob("*.csv") if path.is_file()]
    files.sort(key=lambda item: item.name.lower())
    return files


def filter_csv_rows_by_symbols(csv_file: Path | str, symbols: Sequence[str]) -> Dict[str, Any]:
    csv_path = Path(csv_file).expanduser()
    target_symbols = {normalize_symbol(item) for item in symbols if normalize_symbol(item)}
    if not target_symbols:
        return {"matchedRows": [], "foundSymbols": [], "headers": []}

    matched_rows: List[Dict[str, Any]] = []
    found_symbols: set[str] = set()
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = list(reader.fieldnames or [])
        symbol_col = _resolve_symbol_column(headers)
        if not symbol_col:
            return {"matchedRows": [], "foundSymbols": [], "headers": headers}
        for row in reader:
            symbol = normalize_symbol((row or {}).get(symbol_col))
            if not symbol or symbol not in target_symbols:
                continue
            matched_rows.append(row or {})
            found_symbols.add(symbol)
    return {
        "matchedRows": matched_rows,
        "foundSymbols": sorted(found_symbols),
        "headers": headers,
    }


def check_record_exists(
    symbol: str,
    trade_date: dt.date,
    table_name: str,
    connection_factory: Callable[[], Any],
    *,
    source_name: Optional[str] = None,
) -> bool:
    if not _SAFE_TABLE_NAME_RE.match(str(table_name or "").strip()):
        raise ValueError(f"Unsafe table name: {table_name!r}")
    conn = connection_factory()
    try:
        with conn.cursor() as cur:
            if source_name:
                cur.execute(
                    f"""
                    SELECT 1
                      FROM {table_name}
                     WHERE trade_date = :trade_date
                       AND symbol = :symbol
                       AND source_name = :source_name
                    FETCH FIRST 1 ROWS ONLY
                    """,
                    {
                        "trade_date": trade_date,
                        "symbol": normalize_symbol(symbol),
                        "source_name": str(source_name).strip().upper(),
                    },
                )
            else:
                cur.execute(
                    f"""
                    SELECT 1
                      FROM {table_name}
                     WHERE trade_date = :trade_date
                       AND symbol = :symbol
                    FETCH FIRST 1 ROWS ONLY
                    """,
                    {"trade_date": trade_date, "symbol": normalize_symbol(symbol)},
                )
            return cur.fetchone() is not None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def insert_missing_records(
    rows: Sequence[Dict[str, Any]],
    table_name: str,
    *,
    exists_checker: Callable[[str, dt.date, str], bool],
    insert_row: Callable[[Dict[str, Any]], None],
) -> Dict[str, Any]:
    inserted = 0
    skipped_existing = 0
    errors: List[str] = []
    for row in rows:
        symbol = normalize_symbol(row.get("symbol"))
        trade_date = row.get("trade_date")
        if not symbol or not isinstance(trade_date, dt.date):
            errors.append(f"Invalid row shape for insert_missing_records: {row!r}")
            continue
        try:
            if exists_checker(symbol, trade_date, table_name):
                skipped_existing += 1
                continue
            insert_row(row)
            inserted += 1
        except Exception as exc:  # pragma: no cover - caller controls DB implementation
            errors.append(f"{symbol} {trade_date.isoformat()}: {exc}")
    return {
        "records_inserted": inserted,
        "records_skipped_existing": skipped_existing,
        "errors": errors,
    }


def process_existing_csv_for_symbols(
    symbols_input: Any,
    config: ExistingCsvDatasetConfig,
    *,
    symbol_file_path: Optional[str] = None,
    eq_only: bool = True,
    line_logger: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    requested_symbols = parse_requested_symbols(symbols_input)
    if not requested_symbols:
        raise ValueError("At least one symbol is required.")

    valid_symbol_set = load_valid_symbols(symbol_file_path)
    valid_symbols = [item for item in requested_symbols if item in valid_symbol_set]
    invalid_symbols = [item for item in requested_symbols if item not in valid_symbol_set]

    symbol_path = resolve_symbol_file_path(symbol_file_path)
    csv_files = find_csv_files(config.download_dir)
    symbols_found_in_csv: set[str] = set()
    records_inserted = 0
    records_skipped_existing = 0
    errors: List[str] = []
    csv_files_scanned = 0
    csv_files_processed = 0
    rows_matched = 0

    logger.info(
        "NSE existing-csv process started dataset=%s requested=%s valid=%s invalid=%s symbolPath=%s csvDir=%s csvFiles=%s",
        config.dataset_type,
        len(requested_symbols),
        len(valid_symbols),
        len(invalid_symbols),
        symbol_path,
        config.download_dir,
        len(csv_files),
    )
    if line_logger:
        line_logger(
            f"[INFO] Existing CSV process dataset={config.dataset_type} "
            f"requested={len(requested_symbols)} valid={len(valid_symbols)} invalid={len(invalid_symbols)} "
            f"csvFiles={len(csv_files)}"
        )

    if valid_symbols:
        valid_set = set(valid_symbols)
        for csv_path in csv_files:
            trade_date = config.parse_trade_date(csv_path)
            if trade_date is None:
                continue
            csv_files_scanned += 1
            if config.use_load_result_for_matching:
                try:
                    load_summary = config.load_csv(
                        csv_path,
                        trade_date,
                        eq_only=eq_only,
                        allowed_symbols=valid_set,
                        line_logger=line_logger,
                    )
                except Exception as exc:
                    message = f"{csv_path.name}: load failed: {exc}"
                    errors.append(message)
                    logger.exception(
                        "NSE existing-csv load failed dataset=%s file=%s",
                        config.dataset_type,
                        csv_path,
                    )
                    continue

                matched_symbols = [
                    normalize_symbol(item)
                    for item in (load_summary.get("matchedSymbols") or [])
                    if normalize_symbol(item)
                ]
                symbols_found_in_csv.update(matched_symbols)
                matched_rows = int(load_summary.get("matchedRows") or 0)
                rows_matched += matched_rows
                if matched_rows > 0:
                    csv_files_processed += 1
                records_inserted += int(load_summary.get("loadedCount") or 0)
                records_skipped_existing += int(load_summary.get("alreadyLoadedCount") or 0)
                continue

            if config.inspect_csv is None:
                message = f"{csv_path.name}: inspect_csv is not configured"
                errors.append(message)
                logger.error(
                    "NSE existing-csv inspect missing dataset=%s file=%s",
                    config.dataset_type,
                    csv_path,
                )
                continue

            try:
                inspection = config.inspect_csv(
                    csv_path,
                    trade_date,
                    eq_only=eq_only,
                    allowed_symbols=valid_set,
                )
            except Exception as exc:
                message = f"{csv_path.name}: inspect failed: {exc}"
                errors.append(message)
                logger.exception(
                    "NSE existing-csv inspect failed dataset=%s file=%s",
                    config.dataset_type,
                    csv_path,
                )
                continue

            matched_symbols = [
                normalize_symbol(item)
                for item in (inspection.get("matchedSymbols") or [])
                if normalize_symbol(item)
            ]
            symbols_found_in_csv.update(matched_symbols)
            matched_rows = int(inspection.get("matchedRows") or 0)
            rows_matched += matched_rows
            if matched_rows <= 0:
                continue

            try:
                load_summary = config.load_csv(
                    csv_path,
                    trade_date,
                    eq_only=eq_only,
                    allowed_symbols=valid_set,
                    line_logger=line_logger,
                )
            except Exception as exc:
                message = f"{csv_path.name}: load failed: {exc}"
                errors.append(message)
                logger.exception(
                    "NSE existing-csv load failed dataset=%s file=%s",
                    config.dataset_type,
                    csv_path,
                )
                continue

            csv_files_processed += 1
            records_inserted += int(load_summary.get("loadedCount") or 0)
            records_skipped_existing += int(load_summary.get("alreadyLoadedCount") or 0)

    found_ordered = [item for item in valid_symbols if item in symbols_found_in_csv]
    symbols_not_found = [item for item in valid_symbols if item not in symbols_found_in_csv]

    logger.info(
        "NSE existing-csv process complete dataset=%s scanned=%s processed=%s inserted=%s skippedExisting=%s matchedRows=%s errors=%s",
        config.dataset_type,
        csv_files_scanned,
        csv_files_processed,
        records_inserted,
        records_skipped_existing,
        rows_matched,
        len(errors),
    )

    return {
        "ok": True,
        "status": "success",
        "dataset_type": config.dataset_type,
        "requested_count": len(requested_symbols),
        "requested_symbols": requested_symbols,
        "valid_symbols": valid_symbols,
        "invalid_symbols": invalid_symbols,
        "symbols_found_in_csv": found_ordered,
        "symbols_not_found_in_csv": symbols_not_found,
        "records_inserted": records_inserted,
        "records_skipped_existing": records_skipped_existing,
        "errors": errors,
        "csv_files_scanned": csv_files_scanned,
        "csv_files_processed": csv_files_processed,
        "rows_matched": rows_matched,
        "symbol_file_path": str(symbol_path),
        "download_dir": str(config.download_dir),
    }
