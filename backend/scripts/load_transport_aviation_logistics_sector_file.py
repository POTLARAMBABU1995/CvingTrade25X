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

REFERENCE_TABLE = 'NSE_NIFTY_AUTO_STAGING'

SECTORS = {
    'Aviation Air Transport': {
        'code': 'AVIATION_AIR_TRANSPORT',
        'table': 'NSE_NIFTY_AVIATION_AIR_TRANSPORT_STAGING',
        'index': 'NIFTY_AVIATION_AIR_TRANSPORT',
        'order': 51
    },
    'Logistics, Shipping': {
        'code': 'LOGISTICS_SHIPPING',
        'table': 'NSE_NIFTY_LOGISTICS_SHIPPING_STAGING',
        'index': 'NIFTY_LOGISTICS_SHIPPING',
        'order': 52
    },
    'Port & Port Services': {
        'code': 'PORT_AND_PORT_SERVICES',
        'table': 'NSE_NIFTY_PORT_AND_PORT_SERVICES_STAGING',
        'index': 'NIFTY_PORT_AND_PORT_SERVICES',
        'order': 53
    },
    'Road & Rail Transport': {
        'code': 'ROAD_RAIL_TRANSPORT',
        'table': 'NSE_NIFTY_ROAD_RAIL_TRANSPORT_STAGING',
        'index': 'NIFTY_ROAD_RAIL_TRANSPORT',
        'order': 54
    },
    'Transport Infrastructure': {
        'code': 'TRANSPORT_INFRASTRUCTURE',
        'table': 'NSE_NIFTY_TRANSPORT_INFRASTRUCTURE_STAGING',
        'index': 'NIFTY_TRANSPORT_INFRASTRUCTURE',
        'order': 55
    }
}

SYMBOL_NORMALIZE_RE = re.compile(r'\s+')
SQL_RAW_SYMBOLS = """
SELECT DISTINCT
    REPLACE(REPLACE(REPLACE(REPLACE(UPPER(TRIM(SYMBOL)), 'NSE:', ''), 'BSE:', ''), '-EQ', ''), ' ', '') AS SYMBOL
FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV
WHERE SYMBOL IS NOT NULL
"""
SQL_DISCOVER_OTHER_SECTOR_TABLES = r"""
SELECT DISTINCT utc.table_name
FROM user_tab_columns utc
WHERE utc.column_name = 'SYMBOL'
  AND utc.table_name LIKE 'NSE\_NIFTY\_%\_STAGING' ESCAPE '\'
  AND utc.table_name NOT IN (:table1, :table2, :table3, :table4, :table5)
ORDER BY utc.table_name
"""


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
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', required=True, help='Path to CSV file.')
    parser.add_argument('--dry-run', action='store_true')
    return parser


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
        for line_num, line in enumerate(handle, start=1):
            line = line.strip()
            if not line or line.startswith('S.NO,'):
                continue
            
            summary['rowsRead'] += 1
            parts = [p.strip('"\' ') for p in list(csv.reader([line]))[0]]
            if len(parts) >= 3:
                symbol = normalize_symbol(parts[1])
                sector_name = parts[2].replace('"', '').strip()
                if not symbol:
                    continue
                if symbol in seen_symbols:
                    summary['duplicateSymbols'] += 1
                    continue
                if sector_name not in SECTORS:
                    errors.append(f"Row {line_num}: Unknown sector '{sector_name}'")
                    summary['failedRows'] += 1
                    continue

                seen_symbols.add(symbol)
                rows.append({
                    'symbol': symbol,
                    'sectorName': sector_name,
                    'sectorCode': SECTORS[sector_name]['code'],
                    'stagingTable': SECTORS[sector_name]['table'],
                })
                summary['rowsParsed'] += 1
            else:
                summary['failedRows'] += 1
                errors.append(f"Row {line_num}: Malformed line")

    return rows, summary, errors


def _table_exists(cursor: Any, table_name: str) -> bool:
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM user_tables
        WHERE table_name = :table_name
        """,
        {'table_name': table_name},
    )
    row = cursor.fetchone()
    return bool(row and int(row[0] or 0) > 0)


def _index_exists(cursor: Any, index_name: str) -> bool:
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM user_indexes
        WHERE index_name = :index_name
        """,
        {'index_name': index_name},
    )
    row = cursor.fetchone()
    return bool(row and int(row[0] or 0) > 0)


def _ensure_tables(cursor: Any) -> None:
    for sector_name, conf in SECTORS.items():
        staging_table = conf['table']
        if not _table_exists(cursor, staging_table):
            cursor.execute(
                f'CREATE TABLE {staging_table} AS SELECT * FROM {REFERENCE_TABLE} WHERE 1 = 0'
            )
        idx_name = f"UK_NIFTY_{conf['code'][:10]}_SYM"
        if not _index_exists(cursor, idx_name):
            try:
                cursor.execute(
                    f'CREATE UNIQUE INDEX {idx_name} ON {staging_table} (SYMBOL)'
                )
            except Exception:
                pass


def _ensure_master_row(cursor: Any) -> None:
    for sector_name, conf in SECTORS.items():
        cursor.execute(
            """
            MERGE INTO nse_sector_master tgt
            USING (
                SELECT
                    :sector_code AS sector_code,
                    :sector_name AS sector_name,
                    :index_code AS index_code,
                    :display_order AS display_order
                FROM dual
            ) src
            ON (tgt.sector_code = src.sector_code)
            WHEN MATCHED THEN UPDATE SET
                tgt.sector_name = src.sector_name,
                tgt.index_code = src.index_code,
                tgt.display_order = src.display_order
            WHEN NOT MATCHED THEN
                INSERT (sector_code, sector_name, index_code, display_order)
                VALUES (src.sector_code, src.sector_name, src.index_code, src.display_order)
            """,
            {
                'sector_code': conf['code'],
                'sector_name': sector_name,
                'index_code': conf['index'],
                'display_order': conf['order'],
            },
        )


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
    # Group rows by table
    grouped = {}
    for row in rows:
        grouped.setdefault(row['stagingTable'], []).append(row)

    for table_name, table_rows in grouped.items():
        columns = _load_columns(cursor, table_name)
        insert_columns = ['SYMBOL']
        insert_values = ['src.symbol']
        update_sets: list[str] = []

        sector_name = table_rows[0]['sectorName']
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
        for row in table_rows:
            cursor.execute(merge_sql, {'symbol': row['symbol']})

    for row in rows:
        cursor.execute(
            """
            MERGE INTO NSE_SYMBOL_SECTOR_MAP tgt
            USING (
                SELECT :symbol AS symbol, :sector_code AS sector_code FROM dual
            ) src
            ON (UPPER(TRIM(tgt.SYMBOL)) = src.symbol)
            WHEN MATCHED THEN UPDATE SET
                tgt.SECTOR_CODE = src.sector_code
            WHERE NVL(UPPER(TRIM(tgt.SECTOR_CODE)), '~') <> src.sector_code
            WHEN NOT MATCHED THEN
                INSERT (SYMBOL, SECTOR_CODE)
                VALUES (src.symbol, src.sector_code)
            """,
            {'symbol': row['symbol'], 'sector_code': row['sectorCode']}
        )


def _read_raw_symbol_set(cursor: Any) -> set[str]:
    cursor.execute(SQL_RAW_SYMBOLS)
    return {str(row[0] or '').strip().upper() for row in cursor.fetchall() if row and row[0]}


def _discover_other_sector_tables(cursor: Any) -> list[str]:
    tables_to_exclude = [c['table'] for c in SECTORS.values()]
    cursor.execute(SQL_DISCOVER_OTHER_SECTOR_TABLES, {
        'table1': tables_to_exclude[0],
        'table2': tables_to_exclude[1],
        'table3': tables_to_exclude[2],
        'table4': tables_to_exclude[3],
        'table5': tables_to_exclude[4],
    })
    tables: list[str] = []
    for row in cursor.fetchall():
        table_name = str(row[0] or '').strip().upper()
        if table_name:
            tables.append(table_name)
    return tables


def _find_cross_sector_conflicts(cursor: Any, symbols: list[str]) -> list[dict[str, str]]:
    if not symbols:
        return []

    conflicts: list[dict[str, str]] = []
    binds = {f'symbol_{index}': symbol for index, symbol in enumerate(symbols)}
    bind_clause = ', '.join(f':symbol_{index}' for index in range(len(symbols)))
    for table_name in _discover_other_sector_tables(cursor):
        cursor.execute(
            f"""
            SELECT DISTINCT UPPER(TRIM(symbol)) AS symbol
            FROM {table_name}
            WHERE symbol IS NOT NULL
              AND UPPER(TRIM(symbol)) IN ({bind_clause})
            ORDER BY 1
            """,
            binds,
        )
        for row in cursor.fetchall():
            symbol = str(row[0] or '').strip().upper()
            if symbol:
                conflicts.append({'symbol': symbol, 'tableName': table_name})
    conflicts.sort(key=lambda item: (item['symbol'], item['tableName']))
    return conflicts


def run_load(csv_path: Path, *, dry_run: bool) -> dict[str, Any]:
    rows, parse_summary, parse_errors = _load_rows(csv_path)
    symbols = [str(row['symbol']).strip().upper() for row in rows if str(row.get('symbol') or '').strip()]
    summary: dict[str, Any] = {
        'ok': True,
        'dryRun': dry_run,
        **parse_summary,
        'parseErrors': parse_errors[:10],
    }
    conn = get_oracle_connection()
    try:
        with conn.cursor() as cursor:
            conflicts = _find_cross_sector_conflicts(cursor, symbols)
            
            if conflicts:
                for conflict in conflicts:
                    cursor.execute(f"DELETE FROM {conflict['tableName']} WHERE SYMBOL = :1", [conflict['symbol']])
                conn.commit()
                conflicts = _find_cross_sector_conflicts(cursor, symbols)
            summary['crossSectorConflicts'] = conflicts
            summary['crossSectorConflictCount'] = len(conflicts)
            if conflicts:
                summary['ok'] = False
                summary['error'] = 'Cross-sector duplicate symbols detected. Load aborted without changes.'
                summary['symbolsPreview'] = [row['symbol'] for row in rows[:10]]
                return summary
            if dry_run:
                summary['symbolsPreview'] = [row['symbol'] for row in rows[:10]]
                return summary

            _ensure_tables(cursor)
            _ensure_master_row(cursor)
            _merge_staging_rows(cursor, rows)
            raw_symbols = _read_raw_symbol_set(cursor)

        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

    matched_in_raw = sum(1 for row in rows if row['symbol'] in raw_symbols)
    summary.update(
        {
            'loadedRows': len(rows),
            'matchedRawSymbols': matched_in_raw,
            'missingRawSymbols': len(rows) - matched_in_raw,
        }
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    csv_path = Path(args.file).expanduser().resolve()
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
