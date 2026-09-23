from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_BACKEND_ROOT = _HERE.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from db import get_oracle_connection

REQUIRED_COLUMNS = (
    'Parent Sector',
    'Industry / Sector',
    'Ticker Symbol',
)

SYMBOL_NORMALIZE_RE = re.compile(r'\s+')

SQL_RAW_SYMBOLS = """
SELECT DISTINCT
    REPLACE(REPLACE(REPLACE(REPLACE(UPPER(TRIM(SYMBOL)), 'NSE:', ''), 'BSE:', ''), '-EQ', ''), ' ', '') AS SYMBOL
FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV
WHERE SYMBOL IS NOT NULL
"""

SQL_EXISTING_SYMBOLS = """
SELECT DISTINCT
    REPLACE(REPLACE(REPLACE(REPLACE(UPPER(TRIM(SYMBOL)), 'NSE:', ''), 'BSE:', ''), '-EQ', ''), ' ', '') AS SYMBOL
FROM {table_name}
WHERE SYMBOL IS NOT NULL
"""

MERGE_HEALTHCARE_SQL = """
MERGE INTO NSE_NIFTY500_HEALTHCARE_STAGING tgt
USING (
    SELECT :symbol AS symbol, :sector AS sector FROM dual
) src
ON (UPPER(TRIM(tgt.SYMBOL)) = src.symbol)
WHEN NOT MATCHED THEN INSERT (
    SYMBOL,
    SECTOR
) VALUES (
    src.symbol,
    src.sector
)
"""

MERGE_PHARMA_SQL = """
MERGE INTO NSE_NIFTY_PHARMA_STAGING tgt
USING (
    SELECT :symbol AS symbol, :sector AS sector FROM dual
) src
ON (UPPER(TRIM(tgt.SYMBOL)) = src.symbol)
WHEN NOT MATCHED THEN INSERT (
    SYMBOL,
    SECTOR
) VALUES (
    src.symbol,
    src.sector
)
"""


def _collapse_spaces(value: str) -> str:
    return SYMBOL_NORMALIZE_RE.sub(' ', str(value or '').strip())


def _normalize_symbol(value: str) -> str:
    token = _collapse_spaces(value).upper()
    if token.startswith('NSE:'):
        token = token[4:]
    if token.startswith('BSE:'):
        token = token[4:]
    if token.endswith('-EQ'):
        token = token[:-3]
    token = token.replace(' ', '')
    return token.strip()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Sync missing Healthcare/Pharma staging symbols from hierarchy CSV, constrained to OHLCV symbols.'
    )
    parser.add_argument('--file', required=True, help='Path to hierarchy reference CSV')
    parser.add_argument(
        '--insert-pharma',
        action='store_true',
        help='Also insert missing Pharmaceuticals symbols into NSE_NIFTY_PHARMA_STAGING.',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Report missing symbols without writing to DB.',
    )
    return parser


def _validate_columns(fieldnames: list[str] | None) -> None:
    if not fieldnames:
        raise ValueError('CSV header is missing.')
    missing = [name for name in REQUIRED_COLUMNS if name not in fieldnames]
    if missing:
        raise ValueError(f"CSV missing required columns: {', '.join(missing)}")


def _load_csv_rows(csv_path: Path) -> tuple[list[dict[str, str]], list[str]]:
    rows: list[dict[str, str]] = []
    errors: list[str] = []

    with csv_path.open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        _validate_columns(reader.fieldnames)
        for index, raw in enumerate(reader, start=2):
            parent = _collapse_spaces(raw.get('Parent Sector', ''))
            industry = _collapse_spaces(raw.get('Industry / Sector', ''))
            symbol = _normalize_symbol(raw.get('Ticker Symbol', ''))
            if not parent or not industry or not symbol:
                errors.append(f'Row {index}: required value missing (Parent/Industry/Symbol).')
                continue
            rows.append(
                {
                    'parent_sector': parent,
                    'industry_sector': industry,
                    'symbol': symbol,
                }
            )
    return rows, errors


def _read_symbol_set(cursor: Any, table_name: str) -> set[str]:
    cursor.execute(SQL_EXISTING_SYMBOLS.format(table_name=table_name))
    return {str(row[0] or '').strip().upper() for row in cursor.fetchall() if row and row[0]}


def _is_pharma_industry(value: str) -> bool:
    token = str(value or '').strip().upper()
    return 'PHARMA' in token or 'PHARMACEUTICAL' in token


def run_sync(csv_path: Path, *, insert_pharma: bool, dry_run: bool) -> dict[str, Any]:
    rows, parse_errors = _load_csv_rows(csv_path)
    seen_symbols: set[str] = set()
    deduped: list[dict[str, str]] = []
    duplicate_rows = 0

    for row in rows:
        key = f"{row['parent_sector']}|{row['industry_sector']}|{row['symbol']}"
        if key in seen_symbols:
            duplicate_rows += 1
            continue
        seen_symbols.add(key)
        deduped.append(row)

    conn = get_oracle_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(SQL_RAW_SYMBOLS)
            raw_symbols = {str(row[0] or '').strip().upper() for row in cursor.fetchall() if row and row[0]}
            healthcare_existing = _read_symbol_set(cursor, 'NSE_NIFTY500_HEALTHCARE_STAGING')
            pharma_existing = _read_symbol_set(cursor, 'NSE_NIFTY_PHARMA_STAGING')

            healthcare_candidates: list[str] = []
            pharma_candidates: list[str] = []
            skipped_not_healthcare = 0
            skipped_not_in_raw = 0

            for row in deduped:
                if row['parent_sector'].strip().upper() != 'HEALTHCARE':
                    skipped_not_healthcare += 1
                    continue
                symbol = row['symbol']
                if symbol not in raw_symbols:
                    skipped_not_in_raw += 1
                    continue
                if symbol not in healthcare_existing:
                    healthcare_candidates.append(symbol)
                if insert_pharma and _is_pharma_industry(row['industry_sector']) and symbol not in pharma_existing:
                    pharma_candidates.append(symbol)

            if dry_run:
                return {
                    'ok': True,
                    'dryRun': True,
                    'rowsRead': len(rows),
                    'rowsParsed': len(deduped),
                    'duplicateRows': duplicate_rows,
                    'parseErrors': parse_errors[:10],
                    'healthcareToInsert': sorted(set(healthcare_candidates)),
                    'pharmaToInsert': sorted(set(pharma_candidates)),
                    'skippedNotHealthcare': skipped_not_healthcare,
                    'skippedNotInRaw': skipped_not_in_raw,
                }

            inserted_healthcare = 0
            inserted_pharma = 0

            for symbol in sorted(set(healthcare_candidates)):
                cursor.execute(MERGE_HEALTHCARE_SQL, {'symbol': symbol, 'sector': 'Healthcare'})
                inserted_healthcare += int(cursor.rowcount or 0)

            for symbol in sorted(set(pharma_candidates)):
                cursor.execute(MERGE_PHARMA_SQL, {'symbol': symbol, 'sector': 'Pharma'})
                inserted_pharma += int(cursor.rowcount or 0)

        conn.commit()
        return {
            'ok': True,
            'dryRun': False,
            'rowsRead': len(rows),
            'rowsParsed': len(deduped),
            'duplicateRows': duplicate_rows,
            'parseErrors': parse_errors[:10],
            'healthcareInserted': inserted_healthcare,
            'pharmaInserted': inserted_pharma,
            'healthcareCandidates': len(set(healthcare_candidates)),
            'pharmaCandidates': len(set(pharma_candidates)),
            'skippedNotHealthcare': skipped_not_healthcare,
            'skippedNotInRaw': skipped_not_in_raw,
        }
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    csv_path = Path(args.file).expanduser().resolve()
    if not csv_path.exists() or not csv_path.is_file():
        print(json.dumps({'ok': False, 'message': f'CSV file not found: {csv_path}'}), file=sys.stderr)
        return 1

    try:
        result = run_sync(csv_path, insert_pharma=bool(args.insert_pharma), dry_run=bool(args.dry_run))
    except Exception as exc:
        print(json.dumps({'ok': False, 'message': str(exc)}), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get('ok') else 2


if __name__ == '__main__':
    raise SystemExit(main())
