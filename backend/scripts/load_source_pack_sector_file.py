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
SPACE_RE = re.compile(r'\s+')
SAFE_SQL_NAME_RE = re.compile(r'^[A-Z][A-Z0-9_$#]*$')


def _normalize_sector_key(value: str) -> str:
    token = str(value or '').strip().upper()
    token = token.replace('&', ' AND ')
    token = token.replace('(', ' ')
    token = token.replace(')', ' ')
    token = token.replace('/', ' ')
    token = token.replace('-', ' ')
    token = token.replace(',', ' ')
    token = SPACE_RE.sub(' ', token).strip()
    return token


SECTOR_MAP = {
    _normalize_sector_key('Household & Personal Products'): {
        'table': 'NSE_NIFTY_HOUSEHOLD_PERSONAL_PRODUCTS_STAGING',
        'code': 'HOUSEHOLD_PERSONAL_PRODUCTS',
        'name': 'Household & Personal Products',
        'index_code': 'NIFTY_HOUSEHOLD_PERSONAL_PRODUCTS',
        'display_order': 118,
    },
    _normalize_sector_key('Commodities & Trading'): {
        'table': 'NSE_NIFTY_COMMODITIES_TRADING_STAGING',
        'code': 'COMMODITIES_TRADING',
        'name': 'Commodities & Trading',
        'index_code': 'NIFTY_COMMODITIES_TRADING',
        'display_order': 119,
    },
    _normalize_sector_key('Defence Aerospace & Defense'): {
        'table': 'NSE_NIFTY_DEFENCE_AEROSPACE_DEFENSE_STAGING',
        'code': 'DEFENCE_AEROSPACE_DEFENSE',
        'name': 'Defence Aerospace & Defense',
        'index_code': 'NIFTY_DEFENCE_AEROSPACE_DEFENSE',
        'display_order': 120,
    },
    _normalize_sector_key('Diversified'): {
        'table': 'NSE_NIFTY_DIVERSIFIED_STAGING',
        'code': 'DIVERSIFIED',
        'name': 'Diversified',
        'index_code': 'NIFTY_DIVERSIFIED',
        'display_order': 121,
    },
    _normalize_sector_key('Biotechnology'): {
        'table': 'NSE_NIFTY_BIOTECHNOLOGY_STAGING',
        'code': 'BIOTECHNOLOGY',
        'name': 'Biotechnology',
        'index_code': 'NIFTY_BIOTECHNOLOGY',
        'display_order': 122,
    },
    _normalize_sector_key('Medical Equipment & Supplies'): {
        'table': 'NSE_NIFTY_MEDICAL_EQUIPMENT_SUPPLIES_STAGING',
        'code': 'MEDICAL_EQUIPMENT_SUPPLIES',
        'name': 'Medical Equipment & Supplies',
        'index_code': 'NIFTY_MEDICAL_EQUIPMENT_SUPPLIES',
        'display_order': 123,
    },
    _normalize_sector_key('IT Enabled Services'): {
        'table': 'NSE_NIFTY_IT_ENABLED_SERVICES_STAGING',
        'code': 'IT_ENABLED_SERVICES',
        'name': 'IT Enabled Services',
        'index_code': 'NIFTY_IT_ENABLED_SERVICES',
        'display_order': 124,
    },
    _normalize_sector_key('Software Products & Services'): {
        'table': 'NSE_NIFTY_SOFTWARE_PRODUCTS_SERVICES_STAGING',
        'code': 'SOFTWARE_PRODUCTS_SERVICES',
        'name': 'Software Products & Services',
        'index_code': 'NIFTY_SOFTWARE_PRODUCTS_SERVICES',
        'display_order': 125,
    },
    _normalize_sector_key('MEDIA & ENTERTAINMENT'): {
        'table': 'NSE_NIFTY_MEDIA_ENTERTAINMENT_STAGING',
        'code': 'MEDIA_ENTERTAINMENT',
        'name': 'Media & Entertainment',
        'index_code': 'NIFTY_MEDIA_ENTERTAINMENT',
        'display_order': 126,
    },
    _normalize_sector_key('PRINT MEDIA & PUBLISHING'): {
        'table': 'NSE_NIFTY_PRINT_MEDIA_PUBLISHING_STAGING',
        'code': 'PRINT_MEDIA_PUBLISHING',
        'name': 'Print Media & Publishing',
        'index_code': 'NIFTY_PRINT_MEDIA_PUBLISHING',
        'display_order': 127,
    },
    _normalize_sector_key('Metals & Mining'): {
        'table': 'NSE_NIFTY_METALS_MINING_STAGING',
        'code': 'METALS_MINING',
        'name': 'Metals & Mining',
        'index_code': 'NIFTY_METALS_MINING',
        'display_order': 128,
    },
    _normalize_sector_key('Iron & Steel'): {
        'table': 'NSE_NIFTY_IRON_STEEL_STAGING',
        'code': 'IRON_STEEL',
        'name': 'Iron & Steel',
        'index_code': 'NIFTY_IRON_STEEL',
        'display_order': 129,
    },
    _normalize_sector_key('Mining'): {
        'table': 'NSE_NIFTY_MINING_STAGING',
        'code': 'MINING',
        'name': 'Mining',
        'index_code': 'NIFTY_MINING',
        'display_order': 130,
    },
    _normalize_sector_key('Non-Ferrous Metals'): {
        'table': 'NSE_NIFTY_NON_FERROUS_METALS_STAGING',
        'code': 'NON_FERROUS_METALS',
        'name': 'Non-Ferrous Metals',
        'index_code': 'NIFTY_NON_FERROUS_METALS',
        'display_order': 131,
    },
    _normalize_sector_key('LPG CNG PNG LNG Supplier'): {
        'table': 'NSE_NIFTY_LPG_CNG_PNG_LNG_SUPPLIER_STAGING',
        'code': 'LPG_CNG_PNG_LNG_SUPPLIER',
        'name': 'LPG CNG PNG LNG Supplier',
        'index_code': 'NIFTY_LPG_CNG_PNG_LNG_SUPPLIER',
        'display_order': 132,
    },
    _normalize_sector_key('Lubricants'): {
        'table': 'NSE_NIFTY_LUBRICANTS_STAGING',
        'code': 'LUBRICANTS',
        'name': 'Lubricants',
        'index_code': 'NIFTY_LUBRICANTS',
        'display_order': 133,
    },
    _normalize_sector_key('Oil Equipment & Services'): {
        'table': 'NSE_NIFTY_OIL_EQUIPMENT_SERVICES_STAGING',
        'code': 'OIL_EQUIPMENT_SERVICES',
        'name': 'Oil Equipment & Services',
        'index_code': 'NIFTY_OIL_EQUIPMENT_SERVICES',
        'display_order': 134,
    },
    _normalize_sector_key('Petroleum Products & Refineries'): {
        'table': 'NSE_NIFTY_PETROLEUM_PRODUCTS_REFINERIES_STAGING',
        'code': 'PETROLEUM_PRODUCTS_REFINERIES',
        'name': 'Petroleum Products & Refineries',
        'index_code': 'NIFTY_PETROLEUM_PRODUCTS_REFINERIES',
        'display_order': 135,
    },
    _normalize_sector_key('Paper & Packaging'): {
        'table': 'NSE_NIFTY_PAPER_PACKAGING_STAGING',
        'code': 'PAPER_PACKAGING',
        'name': 'Paper & Packaging',
        'index_code': 'NIFTY_PAPER_PACKAGING',
        'display_order': 136,
    },
    _normalize_sector_key('WASTE & WATER MANAGEMENT'): {
        'table': 'NSE_NIFTY_WASTE_WATER_MANAGEMENT_STAGING',
        'code': 'WASTE_WATER_MANAGEMENT',
        'name': 'Waste & Water Management',
        'index_code': 'NIFTY_WASTE_WATER_MANAGEMENT',
        'display_order': 137,
    },
    _normalize_sector_key('Footwear'): {
        'table': 'NSE_NIFTY_FOOTWEAR_STAGING',
        'code': 'FOOTWEAR',
        'name': 'Footwear',
        'index_code': 'NIFTY_FOOTWEAR',
        'display_order': 138,
    },
    _normalize_sector_key('Gems'): {
        'table': 'NSE_NIFTY_GEMS_STAGING',
        'code': 'GEMS',
        'name': 'Gems',
        'index_code': 'NIFTY_GEMS',
        'display_order': 139,
    },
    _normalize_sector_key('Jewellery & Watches'): {
        'table': 'NSE_NIFTY_JEWELLERY_WATCHES_STAGING',
        'code': 'JEWELLERY_WATCHES',
        'name': 'Jewellery & Watches',
        'index_code': 'NIFTY_JEWELLERY_WATCHES',
        'display_order': 140,
    },
    _normalize_sector_key('Leather & Leather Products'): {
        'table': 'NSE_NIFTY_LEATHER_LEATHER_PRODUCTS_STAGING',
        'code': 'LEATHER_LEATHER_PRODUCTS',
        'name': 'Leather & Leather Products',
        'index_code': 'NIFTY_LEATHER_LEATHER_PRODUCTS',
        'display_order': 141,
    },
    _normalize_sector_key('Textiles & Apparels'): {
        'table': 'NSE_NIFTY_TEXTILES_APPARELS_STAGING',
        'code': 'TEXTILES_APPARELS',
        'name': 'Textiles & Apparels',
        'index_code': 'NIFTY_TEXTILES_APPARELS',
        'display_order': 142,
    },
}


def normalize_symbol(value: str) -> str:
    token = SPACE_RE.sub(' ', str(value or '').strip()).upper()
    if token.startswith('NSE:'):
        token = token[4:]
    if token.startswith('BSE:'):
        token = token[4:]
    if token.endswith('-EQ'):
        token = token[:-3]
    return token.replace(' ', '').strip()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Load source-pack unique sector CSV symbols into dedicated staging tables.',
    )
    parser.add_argument('--source-file', help='Path to CSV file.')
    parser.add_argument('--file', help='Path to CSV file.')
    parser.add_argument('--dry-run', action='store_true', help='Validate and report without writing to Oracle.')
    return parser


def _safe_oracle_name(value: str, *, label: str) -> str:
    token = str(value or '').strip().upper()
    if not token or not SAFE_SQL_NAME_RE.fullmatch(token):
        raise ValueError(f'Invalid {label}: {value}')
    return token


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
    seen_pairs: set[tuple[str, str]] = set()

    with csv_path.open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        _validate_columns(reader.fieldnames)
        symbol_key = _resolve_header_key(reader.fieldnames, 'symbol')
        sector_key = _resolve_header_key(reader.fieldnames, 'sector')

        for row_number, raw in enumerate(reader, start=2):
            summary['rowsRead'] += 1
            try:
                symbol = normalize_symbol(raw.get(symbol_key, ''))
                sector_label = str(raw.get(sector_key, '') or '').strip()
                if not symbol:
                    continue
                if symbol == 'SYMBOL' and _normalize_sector_key(sector_label) == 'SECTOR':
                    continue

                sector_info = SECTOR_MAP.get(_normalize_sector_key(sector_label))
                if sector_info is None:
                    raise ValueError(f"Row {row_number}: Sector '{sector_label}' is not recognized for unique-sector onboarding.")

                dedupe_key = (sector_info['table'], symbol)
                if dedupe_key in seen_pairs:
                    summary['duplicateSymbols'] += 1
                    continue

                seen_pairs.add(dedupe_key)
                rows.append({
                    'symbol': symbol,
                    **sector_info,
                })
                summary['rowsParsed'] += 1
            except Exception as exc:
                summary['failedRows'] += 1
                errors.append(str(exc))

    rows.sort(key=lambda item: (item['table'], item['symbol']))
    return rows, summary, errors


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


def _procedure_exists(cursor: Any, procedure_name: str) -> bool:
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM user_objects
        WHERE object_name = :object_name
          AND object_type = 'PROCEDURE'
        """,
        {'object_name': procedure_name.upper()},
    )
    row = cursor.fetchone()
    return bool(row and int(row[0] or 0) > 0)


def _load_columns(cursor: Any, table_name: str) -> set[str]:
    cursor.execute(
        """
        SELECT column_name
        FROM user_tab_columns
        WHERE table_name = :table_name
        """,
        {'table_name': table_name.upper()},
    )
    return {str(row[0] or '').strip().upper() for row in cursor.fetchall() if row and row[0]}


def _merge_sector_master(
    cursor: Any,
    *,
    sector_code: str,
    sector_name: str,
    index_code: str,
    display_order: int,
) -> None:
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
          tgt.SECTOR_NAME = src.sector_name,
          tgt.INDEX_CODE = src.index_code,
          tgt.DISPLAY_ORDER = COALESCE(tgt.DISPLAY_ORDER, src.display_order)
        WHEN NOT MATCHED THEN INSERT (
          SECTOR_CODE,
          SECTOR_NAME,
          INDEX_CODE,
          DISPLAY_ORDER
        ) VALUES (
          src.sector_code,
          src.sector_name,
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


def _truncate_target_tables(cursor: Any, tables: list[str]) -> None:
    for table_name in tables:
        safe_table = _safe_oracle_name(table_name, label='table name')
        if not _table_exists(cursor, safe_table):
            raise ValueError(f'Staging table does not exist: {safe_table}')
        cursor.execute(f'TRUNCATE TABLE {safe_table}')


def _insert_rows(cursor: Any, rows: list[dict[str, Any]]) -> dict[str, int]:
    table_columns: dict[str, set[str]] = {}
    inserted_rows = 0
    target_counts: dict[str, int] = {}

    for row in rows:
        table_name = _safe_oracle_name(row['table'], label='table name')
        columns = table_columns.setdefault(table_name, _load_columns(cursor, table_name))

        insert_columns = ['SYMBOL']
        insert_values = [':symbol']
        binds = {'symbol': row['symbol']}

        optional_values = {
            'SECTOR': row['name'],
            'INDUSTRY': row['name'],
            'COMPANY_NAME': row['symbol'],
            'ACTIVE_FLAG': 'Y',
        }
        for column_name, value in optional_values.items():
            if column_name not in columns:
                continue
            insert_columns.append(column_name)
            if column_name == 'ACTIVE_FLAG':
                insert_values.append("'Y'")
            else:
                bind_name = column_name.lower()
                insert_values.append(f':{bind_name}')
                binds[bind_name] = value

        if 'CREATED_DATE' in columns:
            insert_columns.append('CREATED_DATE')
            insert_values.append('SYSTIMESTAMP')
        if 'UPDATED_DATE' in columns:
            insert_columns.append('UPDATED_DATE')
            insert_values.append('SYSTIMESTAMP')

        cursor.execute(
            f"""
            INSERT INTO {table_name} ({', '.join(insert_columns)})
            VALUES ({', '.join(insert_values)})
            """,
            binds,
        )
        inserted_rows += 1
        target_counts[table_name] = target_counts.get(table_name, 0) + 1

    return {
        'inserted_rows': inserted_rows,
        'target_table_count': len(target_counts),
    }


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

    unique_sectors = sorted({row['code'] for row in rows})
    unique_tables = sorted({row['table'] for row in rows})

    if dry_run:
        summary.update({
            'sectorCodes': unique_sectors,
            'targetTables': unique_tables,
            'symbolsPreview': [f"{row['symbol']}: {row['code']}" for row in rows[:10]],
        })
        return summary

    conn = get_oracle_connection()
    try:
        with conn.cursor() as cursor:
            _truncate_target_tables(cursor, unique_tables)
            for row in rows:
                _merge_sector_master(
                    cursor,
                    sector_code=row['code'],
                    sector_name=row['name'],
                    index_code=row['index_code'],
                    display_order=row['display_order'],
                )
            insert_result = _insert_rows(cursor, rows)

            reference_sync_proc = 'PR_SYNC_SECTOR_REFERENCE_DATA'
            map_sync_proc = 'PR_SYNC_NSE_SYMBOL_SECTOR_MAP_FROM_STAGING'
            if _procedure_exists(cursor, reference_sync_proc):
                cursor.callproc(reference_sync_proc)
                summary['referenceDataSynced'] = True
                summary['syncProcedure'] = reference_sync_proc
            elif _procedure_exists(cursor, map_sync_proc):
                cursor.callproc(map_sync_proc)
                summary['referenceDataSynced'] = True
                summary['syncProcedure'] = map_sync_proc
            else:
                summary['referenceDataSynced'] = False
                summary['syncProcedure'] = ''

        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

    summary.update({
        'loadedRows': len(rows),
        'sectorCodes': unique_sectors,
        'targetTables': unique_tables,
        **insert_result,
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
        print(json.dumps({'ok': False, 'message': f'File not found: {csv_path}'}), file=sys.stderr)
        return 1

    try:
        result = run_load(csv_path, dry_run=args.dry_run)
    except Exception as exc:
        print(json.dumps({'ok': False, 'message': str(exc)}), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0 if result.get('ok') else 1


if __name__ == '__main__':
    raise SystemExit(main())
