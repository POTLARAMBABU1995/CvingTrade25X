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
    'Restaurants': {
        'table': 'NSE_NIFTY_RESTAURANTS_STAGING',
        'code': 'RESTAURANTS',
        'name': 'Restaurants'
    },
    'Hospitality Hotels & Resorts': {
        'table': 'NSE_NIFTY_HOSPITALITY_HOTELS_RESORTS_STAGING',
        'code': 'HOSPITALITY_HOTELS_RESORTS',
        'name': 'Hospitality Hotels & Resorts'
    },
    'Tourism & Travel': {
        'table': 'NSE_NIFTY_TOURISM_TRAVEL_STAGING',
        'code': 'TOURISM_TRAVEL',
        'name': 'Tourism & Travel'
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
        description='Load Restaurants, Hospitality Hotels & Resorts, Tourism & Travel sector CSV symbols.'
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
                sector_raw = str(raw.get(sector_key, '') or '').strip()
                
                if not symbol:
                    continue
                if symbol == 'SYMBOL' and sector_raw == 'SECTOR':
                    # Skip duplicate header rows if any
                    continue

                # Normalize sector for lookup
                sector_norm = sector_raw.lower().replace('&', 'and').replace(',', ' ').replace('  ', ' ')
                
                # Try to resolve to one of our mapped sectors
                resolved_sector = None
                for sm_key in SECTOR_MAP.keys():
                    sm_norm = sm_key.lower().replace('&', 'and').replace(',', ' ').replace('  ', ' ')
                    if sm_norm == sector_norm or sm_norm in sector_norm or sector_norm in sm_norm:
                        resolved_sector = sm_key
                        break
                
                if not resolved_sector:
                    # Fallback mappings just in case CSV differs slightly
                    if 'restaurant' in sector_norm:
                        resolved_sector = 'Restaurants'
                    elif 'hospitality' in sector_norm or 'hotel' in sector_norm or 'resort' in sector_norm:
                        resolved_sector = 'Hospitality Hotels & Resorts'
                    elif 'tour' in sector_norm or 'travel' in sector_norm:
                        resolved_sector = 'Tourism & Travel'
                    else:
                        raise ValueError(f"Row {row_number}: Sector '{sector_raw}' is not recognized.")

                if symbol in seen_symbols:
                    summary['duplicateSymbols'] += 1
                    continue
                seen_symbols.add(symbol)
                rows.append({
                    'symbol': symbol,
                    'sector': resolved_sector,
                    **SECTOR_MAP[resolved_sector]
                })
                summary['rowsParsed'] += 1
            except Exception as exc:
                summary['failedRows'] += 1
                errors.append(str(exc))

    rows.sort(key=lambda item: item['symbol'])
    return rows, summary, errors

def _load_columns(cursor: Any, table_name: str) -> set[str]:
    cursor.execute(
        r"""
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
            r"""
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

            _conflict_check(cursor, rows)
            
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

def _conflict_check(cursor: Any, rows: list[dict[str, Any]]) -> None:
    all_symbols = list(set([r['symbol'] for r in rows]))
    
    for i in range(0, len(all_symbols), 100):
        chunk = all_symbols[i:i+100]
        binds = {f'sym_{idx}': sym for idx, sym in enumerate(chunk)}
        bind_clause = ', '.join(f':sym_{idx}' for idx in range(len(chunk)))
        
        cursor.execute(f"SELECT SYMBOL, SECTOR_CODE FROM NSE_SYMBOL_SECTOR_MAP WHERE SYMBOL IN ({bind_clause})", binds)
        
        conflicts = cursor.fetchall()
        for sym, code in conflicts:
            # Check if code is in one of the three
            if code not in ['RESTAURANTS', 'HOSPITALITY_HOTELS_RESORTS', 'TOURISM_TRAVEL']:
                print(f"Warning: Conflict: Symbol '{sym}' already mapped to sector '{code}'. It will be moved to the new sector.", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    csv_file = args.source_file or args.file
    if not csv_file:
        print(json.dumps({'ok': False, 'message': 'Missing required argument: --source-file or --file'}), file=sys.stderr)
        return 1

    csv_path = Path(csv_file).expanduser().resolve()
    if not csv_path.exists():
        print(json.dumps({'ok': False, 'message': f'Path not found: {csv_path}'}), file=sys.stderr)
        return 1

    csv_files = []
    if csv_path.is_file():
        csv_files.append(csv_path)
    elif csv_path.is_dir():
        csv_files.extend(csv_path.glob('*.csv'))
        if not csv_files:
            print(json.dumps({'ok': False, 'message': f'No CSV files found in directory: {csv_path}'}), file=sys.stderr)
            return 1
    else:
        print(json.dumps({'ok': False, 'message': f'Invalid path: {csv_path}'}), file=sys.stderr)
        return 1

    try:
        all_results = []
        all_rows = []
        for cf in csv_files:
            rows, parse_summary, parse_errors = _load_rows(cf)
            all_results.append({
                'file': str(cf.name),
                'ok': True if rows else False,
                **parse_summary,
                'parseErrors': parse_errors[:10],
            })
            if rows:
                all_rows.extend(rows)

        if not all_rows:
            print(json.dumps({'ok': False, 'message': 'No valid rows parsed from any CSV files.'}), file=sys.stderr)
            return 1

        if not args.dry_run:
            conn = get_oracle_connection()
            try:
                with conn.cursor() as cursor:
                    _conflict_check(cursor, all_rows)
                    _merge_staging_rows(cursor, all_rows)
                conn.commit()
            except Exception as exc:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise
            finally:
                conn.close()

    except Exception as exc:
        print(json.dumps({'ok': False, 'message': str(exc)}), file=sys.stderr)
        return 1

    print(json.dumps({'ok': True, 'files_processed': len(csv_files), 'total_rows_loaded': len(all_rows), 'results': all_results}, indent=2, default=str))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
