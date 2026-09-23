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

EXPECTED_COLUMNS = ('symbol', 'sector')

SECTOR_MAP = {
    'Engineering': {
        'table': 'NSE_NIFTY_ENGINEERING_STAGING',
        'code': 'ENGINEERING',
        'name': 'Engineering'
    },
    'Electricals Heavy Electrical Equipment': {
        'table': 'NSE_NIFTY_ELEC_HEAVY_EQUIP_STAGING',
        'code': 'ELEC_HEAVY_EQUIPMENT',
        'name': 'Electricals Heavy Electrical Equipment'
    },
    'Industrial Manufacturing': {
        'table': 'NSE_NIFTY_INDUSTRIAL_MANUFACTURING_STAGING',
        'code': 'INDUSTRIAL_MANUFACTURING',
        'name': 'Industrial Manufacturing'
    },
    'Industrial Products': {
        'table': 'NSE_NIFTY_INDUSTRIAL_PRODUCTS_STAGING',
        'code': 'INDUSTRIAL_PRODUCTS',
        'name': 'Industrial Products'
    },
    'Industrial Gases & Fuels': {
        'table': 'NSE_NIFTY_INDUSTRIAL_GASES_FUELS_STAGING',
        'code': 'INDUSTRIAL_GASES_FUELS',
        'name': 'Industrial Gases & Fuels'
    },
    'Capital Goods': {
        'table': 'NSE_NIFTY_CAPITAL_GOODS_STAGING',
        'code': 'CAPITAL_GOODS',
        'name': 'Capital Goods'
    }
}

SYMBOL_NORMALIZE_RE = re.compile(r'\s+')

def _collapse_spaces(value: str) -> str:
    return SYMBOL_NORMALIZE_RE.sub(' ', str(value or '').strip())

def normalize_symbol(value: str) -> str:
    token = _collapse_spaces(value).upper()
    if token.startswith('NSE:'):
        token = token[4:]
    if token.startswith('BSE:'):
        token = token[4:]
    if token.endswith('-EQ'):
        token = token[:-3]
    return token.replace(' ', '').strip()

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Load Capital Goods, Engineering & Industrials sectors CSV symbols.'
    )
    parser.add_argument('--source-file', help='Path to CSV file.')
    parser.add_argument('--file', help='Path to CSV file.')
    parser.add_argument('--dry-run', action='store_true', help='Validate and report without writing to Oracle.')
    return parser

def _validate_columns(fieldnames: list[str] | None) -> None:
    if not fieldnames:
        raise ValueError('CSV header is missing.')
    normalized = [str(name or '').strip().lower() for name in fieldnames]
    missing = [name for name in EXPECTED_COLUMNS if name not in normalized]
    if missing:
        raise ValueError(f"CSV missing required columns: {', '.join(missing)}")

def _resolve_header_key(fieldnames: list[str] | None, target: str) -> str:
    normalized_target = str(target or '').strip().lower()
    for field in fieldnames or []:
        if str(field or '').strip().lower() == normalized_target:
            return field
    raise ValueError(f'CSV missing required column: {target}')

def _load_rows(csv_path: Path) -> tuple[list[dict[str, Any]], dict[str, int], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    summary = {
        'rowsRead': 0,
        'rowsParsed': 0,
        'duplicateSymbols': 0,
        'failedRows': 0,
    }
    seen_symbols: set[str] = set()

    with csv_path.open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        _validate_columns(reader.fieldnames)
        symbol_key = _resolve_header_key(reader.fieldnames, 'symbol')
        sector_key = _resolve_header_key(reader.fieldnames, 'sector')
        
        for row_number, raw in enumerate(reader, start=2):
            summary['rowsRead'] += 1
            try:
                symbol = normalize_symbol(raw.get(symbol_key, ''))
                sector = str(raw.get(sector_key, '') or '').strip()
                if not symbol:
                    continue
                if symbol == 'SYMBOL' and sector == 'SECTOR':
                    # Skip duplicate header rows if any
                    continue
                if sector not in SECTOR_MAP:
                    raise ValueError(f"Row {row_number}: Sector '{sector}' is not recognized.")
                if symbol in seen_symbols:
                    summary['duplicateSymbols'] += 1
                    continue
                seen_symbols.add(symbol)
                rows.append({
                    'symbol': symbol,
                    'sector': sector,
                    **SECTOR_MAP[sector]
                })
                summary['rowsParsed'] += 1
            except Exception as exc:
                summary['failedRows'] += 1
                errors.append(str(exc))

    rows.sort(key=lambda item: item['symbol'])
    return rows, summary, errors

def _load_columns(cursor: Any, table_name: str) -> set[str]:
    cursor.execute(
        """
        SELECT column_name
        FROM user_tab_columns
        WHERE table_name = :table_name
        """,
        {'table_name': table_name},
    )
    return {str(row[0] or '').strip().upper() for row in cursor.fetchall() if row and row[0]}

def _merge_staging_rows(cursor: Any, rows: list[dict[str, Any]]) -> None:
    # First, truncate target staging tables to ensure clean reload as requested:
    # "any symbols/sector are existing remove completely and create as new sectors"
    for sec_info in SECTOR_MAP.values():
        cursor.execute(f"TRUNCATE TABLE {sec_info['table']}")

    for row in rows:
        table_name = row['table']
        sector_name = row['name']
        sector_code = row['code']
        symbol = row['symbol']
        
        columns = _load_columns(cursor, table_name)
        insert_columns = ['SYMBOL']
        insert_values = ['src.symbol']
        update_sets: list[str] = []

        optional_values = {
            'SECTOR': f"'{sector_name}'",
            'INDUSTRY': f"'{sector_name}'",
            'COMPANY_NAME': 'src.symbol',
            'ACTIVE_FLAG': "'Y'",
            'UPDATED_DATE': 'SYSDATE',
            'CREATED_DATE': 'NVL(tgt.CREATED_DATE, SYSDATE)',
        }
        for column_name, source_expr in optional_values.items():
            if column_name not in columns:
                continue
            if column_name != 'CREATED_DATE':
                update_sets.append(f'tgt.{column_name} = {source_expr}')
            insert_columns.append(column_name)
            insert_values.append('SYSDATE' if column_name == 'CREATED_DATE' else source_expr)

        merge_sql = f"""
        MERGE INTO {table_name} tgt
        USING (
            SELECT :symbol AS symbol FROM dual
        ) src
        ON (UPPER(TRIM(tgt.SYMBOL)) = src.symbol)
        WHEN MATCHED THEN UPDATE SET
            {', '.join(update_sets) if update_sets else 'tgt.SYMBOL = tgt.SYMBOL'}
        WHEN NOT MATCHED THEN INSERT (
            {', '.join(insert_columns)}
        ) VALUES (
            {', '.join(insert_values)}
        )
        """
        cursor.execute(merge_sql, {'symbol': symbol})

    # Clear symbol sector map for these symbols before inserting new mappings
    all_symbols = [r['symbol'] for r in rows]
    for i in range(0, len(all_symbols), 100):
        chunk = all_symbols[i:i+100]
        binds = {f'sym_{idx}': sym for idx, sym in enumerate(chunk)}
        bind_clause = ', '.join(f':sym_{idx}' for idx in range(len(chunk)))
        cursor.execute(f"DELETE FROM NSE_SYMBOL_SECTOR_MAP WHERE SYMBOL IN ({bind_clause})", binds)

    # Insert into NSE_SYMBOL_SECTOR_MAP
    for row in rows:
        cursor.execute(
            """
            INSERT INTO NSE_SYMBOL_SECTOR_MAP (SYMBOL, SECTOR_CODE)
            VALUES (:symbol, :sector_code)
            """,
            {'symbol': row['symbol'], 'sector_code': row['code']}
        )

def run_load(csv_path: Path, *, dry_run: bool) -> dict[str, Any]:
    rows, parse_summary, parse_errors = _load_rows(csv_path)
    summary: dict[str, Any] = {
        'ok': True,
        'dryRun': dry_run,
        **parse_summary,
        'parseErrors': parse_errors[:10],
    }
    if not rows:
        summary['ok'] = False
        summary['error'] = 'No valid rows parsed from CSV.'
        return summary

    conn = get_oracle_connection()
    try:
        with conn.cursor() as cursor:
            if dry_run:
                summary['symbolsPreview'] = [f"{row['symbol']}: {row['sector']}" for row in rows[:10]]
                return summary

            _merge_staging_rows(cursor, rows)

        conn.commit()
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

    summary.update({
        'loadedRows': len(rows),
    })
    return summary

def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    csv_file = args.source_file or args.file
    if not csv_file:
        print(json.dumps({'ok': False, 'message': 'Missing required argument: --source-file or --file'}), file=sys.stderr)
        return 1

    csv_path = Path(csv_file).expanduser().resolve()
    if not csv_path.exists() or not csv_path.is_file():
        print(json.dumps({'ok': False, 'message': f'CSV file not found: {csv_path}'}), file=sys.stderr)
        return 1

    try:
        result = run_load(csv_path, dry_run=bool(args.dry_run))
    except Exception as exc:
        print(json.dumps({'ok': False, 'message': str(exc)}), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get('ok') else 2

if __name__ == '__main__':
    raise SystemExit(main())
