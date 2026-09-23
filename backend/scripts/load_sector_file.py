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
from services.symbol_validation_service import symbol_validation_service, normalize_symbol, replace_old_symbol

_SAFE_ORACLE_NAME_RE = re.compile(r'^[A-Z][A-Z0-9_$#]*$')


def _collapse_spaces(value: str) -> str:
    return re.sub(r'\s+', ' ', str(value or '').strip())


def _safe_oracle_name(value: str, *, label: str) -> str:
    token = _collapse_spaces(value).upper()
    if not _SAFE_ORACLE_NAME_RE.fullmatch(token):
        raise ValueError(f'Unsafe Oracle {label}: {value!r}')
    return token


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Generic Sector CSV Symbol Loader'
    )
    parser.add_argument('--sector-code', required=True, help='Sector Code (e.g. RESTAURANTS)')
    parser.add_argument('--staging-table', required=True, help='Staging Table Name (e.g. NSE_NIFTY_RESTAURANTS_STAGING)')
    parser.add_argument('--source-file', help='Path to CSV file.')
    parser.add_argument('--file', help='Path to CSV file.')
    parser.add_argument('--sector-name', help='Optional display name to merge into NSE_SECTOR_MASTER.')
    parser.add_argument('--index-code', help='Optional index code to merge into NSE_SECTOR_MASTER.')
    parser.add_argument('--display-order', type=int, help='Optional display order for NSE_SECTOR_MASTER.')
    parser.add_argument('--dry-run', action='store_true', help='Validate and report without writing to Oracle.')
    parser.add_argument(
        '--allow-existing-cross-sector-membership',
        action='store_true',
        help=(
            'Add symbols to the requested staging table while preserving an existing '
            'canonical NSE_SYMBOL_SECTOR_MAP owner. Default behavior remains to abort '
            'when cross-sector membership is detected.'
        ),
    )
    return parser

def _load_rows(csv_path: Path) -> tuple[list[str], dict[str, int], list[str]]:
    raw_symbols: list[str] = []
    errors: list[str] = []
    summary = {
        'rowsRead': 0,
        'rowsParsed': 0,
        'duplicateSymbols': 0,
        'failedRows': 0,
    }
    seen_symbols: set[str] = set()

    symbol_validation_service.initialize_if_needed()

    with csv_path.open('r', encoding='utf-8-sig', newline='') as handle:
        # Check if first line has header, else read lines
        first_line = handle.readline()
        handle.seek(0)
        
        has_header = False
        symbol_col = None
        
        if first_line and ',' in first_line:
            # Try parsing header
            header_reader = csv.reader([first_line])
            headers = next(header_reader, [])
            normalized_headers = [str(h or '').strip().lower() for h in headers]
            if 'symbol' in normalized_headers:
                has_header = True
                symbol_col = headers[normalized_headers.index('symbol')]

        if has_header and symbol_col:
            reader = csv.DictReader(handle)
            for row_number, raw in enumerate(reader, start=2):
                summary['rowsRead'] += 1
                raw_val = raw.get(symbol_col, '')
                if not raw_val:
                    continue
                
                # Normalize symbol
                norm = normalize_symbol(raw_val)
                if not norm or norm == 'SYMBOL':
                    continue
                
                # Replaced handling
                classif = symbol_validation_service.classify_symbol(norm)
                if classif == 'REPLACED':
                    norm = replace_old_symbol(norm)
                    classif = symbol_validation_service.classify_symbol(norm)

                if classif in ('INVALID', 'BSE_ONLY'):
                    summary['failedRows'] += 1
                    errors.append(f"Row {row_number}: Symbol '{raw_val}' is invalid/BSE_ONLY ({classif})")
                    continue
                
                if norm in seen_symbols:
                    summary['duplicateSymbols'] += 1
                    continue
                
                seen_symbols.add(norm)
                raw_symbols.append(norm)
                summary['rowsParsed'] += 1
        else:
            # Just read line by line, treat first token as symbol
            reader = csv.reader(handle)
            for row_number, raw in enumerate(reader, start=1):
                summary['rowsRead'] += 1
                if not raw or not raw[0]:
                    continue
                raw_val = raw[0]
                norm = normalize_symbol(raw_val)
                if not norm or norm == 'SYMBOL':
                    continue
                
                classif = symbol_validation_service.classify_symbol(norm)
                if classif == 'REPLACED':
                    norm = replace_old_symbol(norm)
                    classif = symbol_validation_service.classify_symbol(norm)

                if classif in ('INVALID', 'BSE_ONLY'):
                    summary['failedRows'] += 1
                    errors.append(f"Row {row_number}: Symbol '{raw_val}' is invalid/BSE_ONLY ({classif})")
                    continue
                
                if norm in seen_symbols:
                    summary['duplicateSymbols'] += 1
                    continue
                
                seen_symbols.add(norm)
                raw_symbols.append(norm)
                summary['rowsParsed'] += 1

    return raw_symbols, summary, errors

def _get_other_staging_tables(cursor: Any, current_table: str) -> list[str]:
    cursor.execute("""
        SELECT DISTINCT utc.table_name
        FROM user_tab_columns utc
        JOIN user_tables ut ON ut.table_name = utc.table_name
        WHERE utc.column_name = 'SYMBOL'
          AND utc.table_name LIKE 'NSE_NIFTY%STAGING'
          AND utc.table_name <> :current_table
    """, {'current_table': current_table.upper()})
    return [str(row[0]).strip().upper() for row in cursor.fetchall() if row]

def _check_cross_sector_conflicts(cursor: Any, sector_code: str, staging_table: str, symbols: list[str]) -> list[dict[str, str]]:
    conflicts: list[dict[str, str]] = []
    if not symbols:
        return conflicts
    
    # 1. Check NSE_SYMBOL_SECTOR_MAP
    # Query in batches
    batch_size = 100
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i+batch_size]
        binds = {f'sym_{idx}': sym for idx, sym in enumerate(batch)}
        bind_clause = ', '.join(f':sym_{idx}' for idx in range(len(batch)))
        query = f"""
            SELECT SYMBOL, SECTOR_CODE 
            FROM NSE_SYMBOL_SECTOR_MAP 
            WHERE SYMBOL IN ({bind_clause}) AND SECTOR_CODE <> :sec_code
        """
        cursor.execute(query, {**binds, 'sec_code': sector_code.upper()})
        for sym, sec in cursor.fetchall():
            conflicts.append({
                'symbol': str(sym or '').strip().upper(),
                'requested_sector': sector_code.upper(),
                'existing_sector': str(sec or '').strip().upper(),
                'existing_sector_code': str(sec or '').strip().upper(),
                'existing_staging_table': '',
                'source': 'NSE_SYMBOL_SECTOR_MAP'
            })

    # 2. Check other staging tables
    other_tables = _get_other_staging_tables(cursor, staging_table)
    for other_table in other_tables:
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i+batch_size]
            binds = {f'sym_{idx}': sym for idx, sym in enumerate(batch)}
            bind_clause = ', '.join(f':sym_{idx}' for idx in range(len(batch)))
            query = f"SELECT SYMBOL FROM {other_table} WHERE SYMBOL IN ({bind_clause})"
            cursor.execute(query, binds)
            for (sym,) in cursor.fetchall():
                existing_sector_code = other_table[10:-8] if (other_table.startswith('NSE_NIFTY_') and other_table.endswith('_STAGING')) else other_table
                conflicts.append({
                    'symbol': str(sym or '').strip().upper(),
                    'requested_sector': sector_code.upper(),
                    'existing_sector': existing_sector_code,
                    'existing_sector_code': existing_sector_code,
                    'existing_staging_table': other_table,
                    'source': other_table
                })
                
    return conflicts

def _table_exists(cursor: Any, table_name: str) -> bool:
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM user_tables
        WHERE table_name = :table_name
        """,
        {'table_name': table_name.upper()},
    )
    row = cursor.fetchone()
    return bool(row and int(row[0] or 0) > 0)


def _load_columns(cursor: Any, table_name: str) -> set[str]:
    cursor.execute(
        r"""
        SELECT column_name
        FROM user_tab_columns
        WHERE table_name = :table_name
        """,
        {'table_name': table_name.upper()},
    )
    return {str(row[0] or '').strip().upper() for row in cursor.fetchall() if row and row[0]}

def _load_existing_symbols(cursor: Any, table_name: str, symbols: list[str]) -> set[str]:
    existing: set[str] = set()
    if not symbols:
        return existing
    safe_table = _safe_oracle_name(table_name, label='table name')
    for i in range(0, len(symbols), 100):
        batch = symbols[i:i + 100]
        binds = {f'sym_{idx}': sym for idx, sym in enumerate(batch)}
        bind_clause = ', '.join(f':sym_{idx}' for idx in range(len(batch)))
        cursor.execute(
            f"""
            SELECT UPPER(TRIM(SYMBOL))
            FROM {safe_table}
            WHERE UPPER(TRIM(SYMBOL)) IN ({bind_clause})
            """,
            binds,
        )
        existing.update(str(row[0] or '').strip().upper() for row in cursor.fetchall() if row and row[0])
    return existing


def _load_existing_sector_map_symbols(cursor: Any, sector_code: str, symbols: list[str]) -> set[str]:
    existing: set[str] = set()
    if not symbols:
        return existing
    for i in range(0, len(symbols), 100):
        batch = symbols[i:i + 100]
        binds = {f'sym_{idx}': sym for idx, sym in enumerate(batch)}
        bind_clause = ', '.join(f':sym_{idx}' for idx in range(len(batch)))
        cursor.execute(
            f"""
            SELECT UPPER(TRIM(SYMBOL))
            FROM NSE_SYMBOL_SECTOR_MAP
            WHERE SECTOR_CODE = :sector_code
              AND UPPER(TRIM(SYMBOL)) IN ({bind_clause})
            """,
            {**binds, 'sector_code': sector_code.upper()},
        )
        existing.update(str(row[0] or '').strip().upper() for row in cursor.fetchall() if row and row[0])
    return existing


def _load_symbols_with_any_sector_map(cursor: Any, symbols: list[str]) -> set[str]:
    existing: set[str] = set()
    if not symbols:
        return existing
    for i in range(0, len(symbols), 100):
        batch = symbols[i:i + 100]
        binds = {f'sym_{idx}': sym for idx, sym in enumerate(batch)}
        bind_clause = ', '.join(f':sym_{idx}' for idx in range(len(batch)))
        cursor.execute(
            f"""
            SELECT UPPER(TRIM(SYMBOL))
            FROM NSE_SYMBOL_SECTOR_MAP
            WHERE UPPER(TRIM(SYMBOL)) IN ({bind_clause})
            """,
            binds,
        )
        existing.update(str(row[0] or '').strip().upper() for row in cursor.fetchall() if row and row[0])
    return existing


def _count_stage_rows(cursor: Any, table_name: str) -> int:
    safe_table = _safe_oracle_name(table_name, label='table name')
    cursor.execute(f"SELECT COUNT(DISTINCT UPPER(TRIM(SYMBOL))) FROM {safe_table}")
    row = cursor.fetchone()
    return int(row[0] or 0) if row else 0


def _merge_sector_master(
    cursor: Any,
    *,
    sector_code: str,
    sector_name: str | None,
    index_code: str | None,
    display_order: int | None,
) -> None:
    if not sector_name and not index_code and display_order is None:
        return
    cursor.execute(
        """
        MERGE INTO NSE_SECTOR_MASTER tgt
        USING (
          SELECT
            :sector_code AS sector_code,
            :sector_name AS sector_name,
            :index_code AS index_code,
            :display_order AS display_order
          FROM dual
        ) src
        ON (tgt.SECTOR_CODE = src.sector_code)
        WHEN MATCHED THEN UPDATE SET
          tgt.SECTOR_NAME = COALESCE(src.sector_name, tgt.SECTOR_NAME),
          tgt.INDEX_CODE = COALESCE(src.index_code, tgt.INDEX_CODE),
          tgt.DISPLAY_ORDER = COALESCE(src.display_order, tgt.DISPLAY_ORDER)
        WHEN NOT MATCHED THEN INSERT (
          SECTOR_CODE,
          SECTOR_NAME,
          INDEX_CODE,
          DISPLAY_ORDER
        ) VALUES (
          src.sector_code,
          COALESCE(src.sector_name, src.sector_code),
          src.index_code,
          src.display_order
        )
        """,
        {
            'sector_code': sector_code.upper(),
            'sector_name': sector_name,
            'index_code': index_code,
            'display_order': display_order,
        },
    )


def _insert_rows(
    cursor: Any,
    sector_code: str,
    staging_table: str,
    symbols: list[str],
    *,
    preserve_existing_sector_map_owners: bool = False,
) -> dict[str, int]:
    staging_table = staging_table.upper()
    sector_code = sector_code.upper()

    safe_table = _safe_oracle_name(staging_table, label='table name')
    if not _table_exists(cursor, safe_table):
        raise ValueError(f'Staging table does not exist: {safe_table}')
    
    columns = _load_columns(cursor, staging_table)
    existing_stage_symbols = _load_existing_symbols(cursor, safe_table, symbols)
    existing_map_symbols = _load_existing_sector_map_symbols(cursor, sector_code, symbols)
    existing_any_map_symbols = (
        _load_symbols_with_any_sector_map(cursor, symbols)
        if preserve_existing_sector_map_owners
        else set()
    )
    inserted_stage_rows = 0
    skipped_existing_stage_rows = 0
    inserted_map_rows = 0
    skipped_existing_map_rows = 0
    skipped_preserved_map_rows = 0
    
    for symbol in symbols:
        if symbol in existing_stage_symbols:
            skipped_existing_stage_rows += 1
        else:
            insert_cols = ['SYMBOL']
            insert_vals = [':symbol']
            binds = {'symbol': symbol}
            
            if 'SECTOR' in columns:
                insert_cols.append('SECTOR')
                insert_vals.append(':sector')
                binds['sector'] = sector_code
            if 'ACTIVE_FLAG' in columns:
                insert_cols.append('ACTIVE_FLAG')
                insert_vals.append("'Y'")
            if 'CREATED_DATE' in columns:
                insert_cols.append('CREATED_DATE')
                insert_vals.append('SYSTIMESTAMP')
            if 'UPDATED_DATE' in columns:
                insert_cols.append('UPDATED_DATE')
                insert_vals.append('SYSTIMESTAMP')
                
            cursor.execute(
                f"""
                INSERT INTO {safe_table} ({', '.join(insert_cols)})
                VALUES ({', '.join(insert_vals)})
                """,
                binds,
            )
            inserted_stage_rows += 1

        if symbol in existing_map_symbols:
            skipped_existing_map_rows += 1
            continue

        if symbol in existing_any_map_symbols:
            skipped_preserved_map_rows += 1
            continue

        cursor.execute(
            """
            MERGE INTO NSE_SYMBOL_SECTOR_MAP tgt
            USING (
              SELECT :symbol AS symbol, :sector_code AS sector_code
              FROM dual
            ) src
            ON (
              UPPER(TRIM(tgt.SYMBOL)) = src.symbol
              AND tgt.SECTOR_CODE = src.sector_code
            )
            WHEN NOT MATCHED THEN INSERT (SYMBOL, SECTOR_CODE)
            VALUES (src.symbol, src.sector_code)
            """,
            {'symbol': symbol, 'sector_code': sector_code},
        )
        inserted_map_rows += 1

    return {
        'inserted_stage_rows': inserted_stage_rows,
        'skipped_existing_stage_rows': skipped_existing_stage_rows,
        'inserted_map_rows': inserted_map_rows,
        'skipped_existing_map_rows': skipped_existing_map_rows,
        'skipped_preserved_map_rows': skipped_preserved_map_rows,
        'final_staging_count': _count_stage_rows(cursor, safe_table),
    }

def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    csv_file = args.source_file or args.file
    if not csv_file:
        print(json.dumps({'ok': False, 'message': 'Missing required argument: --source-file or --file'}), file=sys.stderr)
        return 1

    csv_path = Path(csv_file).expanduser().resolve()
    if not csv_path.exists() or not csv_path.is_file():
        print(json.dumps({'ok': False, 'message': f'File not found: {csv_path}'}), file=sys.stderr)
        return 1

    symbols, summary, errors = _load_rows(csv_path)
    if not symbols:
        print(json.dumps({'ok': False, 'message': 'No valid symbols parsed from CSV file.', 'errors': errors[:10]}), file=sys.stderr)
        return 1

    try:
        sector_code = _safe_oracle_name(args.sector_code, label='sector code')
        staging_table = _safe_oracle_name(args.staging_table, label='staging table')
    except ValueError as exc:
        print(json.dumps({'ok': False, 'message': str(exc)}), file=sys.stderr)
        return 1

    conn = get_oracle_connection()
    try:
        with conn.cursor() as cursor:
            # Check for conflicts
            conflicts = _check_cross_sector_conflicts(cursor, sector_code, staging_table, symbols)
            if conflicts and not args.allow_existing_cross_sector_membership:
                print(json.dumps({
                    'ok': False,
                    'message': f'Aborted due to {len(conflicts)} cross-sector duplicate symbols.',
                    'conflicts': conflicts
                }, indent=2), file=sys.stderr)
                return 1

            if args.dry_run:
                print(json.dumps({
                    'ok': True,
                    'dry_run': True,
                    'sector_code': sector_code,
                    'staging_table': staging_table,
                    'symbols_count': len(symbols),
                    'symbols_preview': symbols[:10],
                    'cross_sector_membership_count': len(conflicts),
                    'preserve_existing_sector_map_owners': bool(args.allow_existing_cross_sector_membership),
                    'summary': summary
                }, indent=2))
                return 0

            _merge_sector_master(
                cursor,
                sector_code=sector_code,
                sector_name=_collapse_spaces(args.sector_name) or None,
                index_code=_collapse_spaces(args.index_code).upper() or None if args.index_code else None,
                display_order=args.display_order,
            )
            write_summary = _insert_rows(
                cursor,
                sector_code,
                staging_table,
                symbols,
                preserve_existing_sector_map_owners=bool(args.allow_existing_cross_sector_membership),
            )
            
        conn.commit()
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        print(json.dumps({'ok': False, 'message': str(exc)}), file=sys.stderr)
        return 1
    finally:
        conn.close()

    print(json.dumps({
        'ok': True,
        'sector_code': sector_code,
        'staging_table': staging_table,
        'source_rows': summary['rowsRead'],
        'normalized_rows': len(symbols),
        'inserted_rows': write_summary['inserted_stage_rows'],
        'skipped_duplicates': summary['duplicateSymbols'],
        'rejected_invalid': summary['failedRows'],
        'skipped_existing_stage_rows': write_summary['skipped_existing_stage_rows'],
        'inserted_map_rows': write_summary['inserted_map_rows'],
        'skipped_existing_map_rows': write_summary['skipped_existing_map_rows'],
        'skipped_preserved_map_rows': write_summary['skipped_preserved_map_rows'],
        'conflict_count': len(conflicts),
        'preserved_existing_sector_map_owners': bool(args.allow_existing_cross_sector_membership),
        'final_staging_count': write_summary['final_staging_count']
    }, indent=2))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
