from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

from db import get_oracle_connection

REQUIRED_COLUMNS = (
    'Parent Sector',
    'Industry / Sector',
    'Sub-Sector',
    'Ticker Symbol',
    'Exchange',
)

MERGE_SQL = """
MERGE INTO NSE_SECTOR_HIERARCHY_MASTER tgt
USING (
    SELECT
        :parent_sector AS parent_sector,
        :industry_sector AS industry_sector,
        :sub_sector AS sub_sector,
        :symbol AS symbol,
        :exchange AS exchange,
        :source_name AS source_name,
        :source_file AS source_file
    FROM dual
) src
ON (
    tgt.PARENT_SECTOR = src.parent_sector
    AND tgt.INDUSTRY_SECTOR = src.industry_sector
    AND tgt.SUB_SECTOR = src.sub_sector
    AND tgt.SYMBOL = src.symbol
    AND tgt.EXCHANGE = src.exchange
)
WHEN MATCHED THEN UPDATE SET
    tgt.SOURCE_NAME = src.source_name,
    tgt.SOURCE_FILE = src.source_file,
    tgt.IS_ACTIVE = 'Y',
    tgt.UPDATED_AT = SYSTIMESTAMP,
    tgt.UPDATED_BY = USER
WHEN NOT MATCHED THEN INSERT (
    PARENT_SECTOR,
    INDUSTRY_SECTOR,
    SUB_SECTOR,
    SYMBOL,
    EXCHANGE,
    SOURCE_NAME,
    SOURCE_FILE,
    IS_ACTIVE,
    CREATED_AT,
    CREATED_BY
) VALUES (
    src.parent_sector,
    src.industry_sector,
    src.sub_sector,
    src.symbol,
    src.exchange,
    src.source_name,
    src.source_file,
    'Y',
    SYSTIMESTAMP,
    USER
)
"""

EXISTS_SQL = """
SELECT 1
FROM NSE_SECTOR_HIERARCHY_MASTER
WHERE PARENT_SECTOR = :parent_sector
  AND INDUSTRY_SECTOR = :industry_sector
  AND SUB_SECTOR = :sub_sector
  AND SYMBOL = :symbol
  AND EXCHANGE = :exchange
FETCH FIRST 1 ROWS ONLY
"""


def _collapse_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def normalize_sector_name(value: str) -> str:
    return _collapse_spaces(value)


def normalize_symbol(value: str) -> str:
    token = _collapse_spaces(value).upper()
    if token.startswith('NSE:'):
        token = token[4:]
    if token.endswith('-EQ'):
        token = token[:-3]
    return token.strip()


def normalize_exchange(value: str) -> str:
    token = _collapse_spaces(value).upper()
    return token or 'NSE'


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Load sector hierarchy CSV into Oracle table NSE_SECTOR_HIERARCHY_MASTER')
    parser.add_argument('--file', required=True, help='Path to sector hierarchy CSV file')
    parser.add_argument('--source', default='Manual Sector Hierarchy CSV', help='Logical source label')
    return parser


def _assert_required_columns(fieldnames: list[str] | None) -> None:
    if not fieldnames:
        raise ValueError('CSV header is missing.')
    missing = [name for name in REQUIRED_COLUMNS if name not in fieldnames]
    if missing:
        raise ValueError(f"CSV missing required columns: {', '.join(missing)}")


def _parse_row(raw: dict[str, Any], row_number: int) -> dict[str, str]:
    parent_sector = normalize_sector_name(raw.get('Parent Sector', ''))
    industry_sector = normalize_sector_name(raw.get('Industry / Sector', ''))
    sub_sector = normalize_sector_name(raw.get('Sub-Sector', ''))
    symbol = normalize_symbol(raw.get('Ticker Symbol', ''))
    exchange = normalize_exchange(raw.get('Exchange', ''))

    missing_fields: list[str] = []
    if not parent_sector:
        missing_fields.append('Parent Sector')
    if not industry_sector:
        missing_fields.append('Industry / Sector')
    if not sub_sector:
        missing_fields.append('Sub-Sector')
    if not symbol:
        missing_fields.append('Ticker Symbol')
    if not exchange:
        missing_fields.append('Exchange')

    if missing_fields:
        raise ValueError(f"Row {row_number}: empty mandatory fields -> {', '.join(missing_fields)}")

    return {
        'parent_sector': parent_sector,
        'industry_sector': industry_sector,
        'sub_sector': sub_sector,
        'symbol': symbol,
        'exchange': exchange,
    }


def _load_rows(csv_path: Path) -> tuple[list[dict[str, str]], dict[str, int], list[str]]:
    rows: list[dict[str, str]] = []
    summary = {
        'rowsRead': 0,
        'rowsSkipped': 0,
        'duplicateRows': 0,
        'failedRows': 0,
    }
    errors: list[str] = []
    seen_keys: set[tuple[str, str, str, str, str]] = set()

    with csv_path.open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        _assert_required_columns(reader.fieldnames)
        for idx, raw in enumerate(reader, start=2):
            summary['rowsRead'] += 1
            try:
                parsed = _parse_row(raw, idx)
            except Exception as exc:
                summary['failedRows'] += 1
                errors.append(str(exc))
                continue

            key = (
                parsed['parent_sector'],
                parsed['industry_sector'],
                parsed['sub_sector'],
                parsed['symbol'],
                parsed['exchange'],
            )
            if key in seen_keys:
                summary['rowsSkipped'] += 1
                summary['duplicateRows'] += 1
                continue
            seen_keys.add(key)
            rows.append(parsed)

    return rows, summary, errors


def _upsert_rows(rows: list[dict[str, str]], source_name: str, source_file: str) -> tuple[dict[str, int], list[str]]:
    summary = {
        'rowsInserted': 0,
        'rowsUpdated': 0,
        'failedRows': 0,
    }
    errors: list[str] = []

    conn = get_oracle_connection()
    try:
        with conn.cursor() as cursor:
            for row in rows:
                binds = {
                    **row,
                    'source_name': source_name,
                    'source_file': source_file,
                }
                try:
                    cursor.execute(EXISTS_SQL, binds)
                    existed = cursor.fetchone() is not None
                    cursor.execute(MERGE_SQL, binds)
                    if existed:
                        summary['rowsUpdated'] += 1
                    else:
                        summary['rowsInserted'] += 1
                except Exception as exc:
                    summary['failedRows'] += 1
                    errors.append(
                        f"MERGE failed for {row['parent_sector']} -> {row['industry_sector']} -> {row['sub_sector']} -> {row['symbol']} ({row['exchange']}): {exc}"
                    )
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

    return summary, errors


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    csv_path = Path(args.file).expanduser().resolve()
    if not csv_path.exists() or not csv_path.is_file():
        print(json.dumps({'ok': False, 'message': f'CSV file not found: {csv_path}'}), file=sys.stderr)
        return 1

    source_name = _collapse_spaces(str(args.source or 'Manual Sector Hierarchy CSV'))
    source_file = csv_path.name

    try:
        normalized_rows, file_summary, file_errors = _load_rows(csv_path)
    except Exception as exc:
        print(json.dumps({'ok': False, 'message': str(exc)}), file=sys.stderr)
        return 1

    db_summary: dict[str, int] = {'rowsInserted': 0, 'rowsUpdated': 0, 'failedRows': 0}
    db_errors: list[str] = []
    if normalized_rows:
        try:
            db_summary, db_errors = _upsert_rows(normalized_rows, source_name=source_name, source_file=source_file)
        except Exception as exc:
            print(json.dumps({'ok': False, 'message': f'Database upsert failed: {exc}'}), file=sys.stderr)
            return 1

    total_failed = file_summary['failedRows'] + db_summary['failedRows']
    payload = {
        'ok': total_failed == 0,
        'source': source_name,
        'sourceFile': source_file,
        'rowsRead': file_summary['rowsRead'],
        'rowsInserted': db_summary['rowsInserted'],
        'rowsUpdated': db_summary['rowsUpdated'],
        'rowsSkipped': file_summary['rowsSkipped'],
        'duplicateRows': file_summary['duplicateRows'],
        'failedRows': total_failed,
        'errorSamples': [*file_errors[:5], *db_errors[:5]],
    }
    print(json.dumps(payload, indent=2, default=str))
    return 0 if payload['ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
