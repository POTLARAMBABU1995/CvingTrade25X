from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_BACKEND_ROOT = _HERE.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from db import get_oracle_connection

SECTOR_MAP = {
    'FINANCE FINANCIAL SERVICES': 'NSE_NIFTY_FINANCIAL_SERVICES_STAGING',
    'NBFC': 'NSE_NIFTY_NBFC_STAGING',
    'INSURANCE': 'NSE_NIFTY_INSURANCE_STAGING',
    'CAPITAL MARKETS': 'NSE_NIFTY_CAPITAL_MARKETS_STAGING',
    'ASSET MANAGEMENT COMPANY': 'NSE_NIFTY_ASSET_MANAGEMENT_COMPANY_STAGING',
    'FINTECH': 'NSE_NIFTY_FINTECH_STAGING',
    'HOUSING FINANCE COMPANY': 'NSE_NIFTY_HOUSING_FINANCE_COMPANY_STAGING',
    'STOCKBROKING & ALLIED': 'NSE_NIFTY_STOCKBROKING_AND_ALLIED_STAGING',
}

REFERENCE_TABLE = 'NSE_NIFTY_AUTO_STAGING'


def _ensure_table(cursor, table_name: str, index_name: str) -> None:
    cursor.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = :1", [table_name])
    if cursor.fetchone()[0] == 0:
        print(f"Creating table {table_name}")
        cursor.execute(f"CREATE TABLE {table_name} AS SELECT * FROM {REFERENCE_TABLE} WHERE 1=0")
        cursor.execute(f"CREATE UNIQUE INDEX {index_name} ON {table_name} (SYMBOL)")


def _load_columns(cursor, table_name: str) -> set[str]:
    cursor.execute("SELECT column_name FROM user_tab_columns WHERE table_name = :1", [table_name])
    return {row[0].upper() for row in cursor.fetchall() if row and row[0]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Load the 8 financial sub-sectors")
    parser.add_argument('--file', required=True, help="Path to the CSV file")
    args = parser.parse_args()

    conn = get_oracle_connection()
    try:
        cursor = conn.cursor()

        # Ensure staging tables exist
        for sector, table in SECTOR_MAP.items():
            if table == 'NSE_NIFTY_FINANCIAL_SERVICES_STAGING':
                continue
            index_name = 'UK_' + table.replace('NSE_NIFTY_', '')[:20]
            _ensure_table(cursor, table, index_name)

        from services.symbol_validation_service import symbol_validation_service
        symbol_validation_service.initialize_if_needed()

        loaded_count = 0
        skipped_count = 0
        replaced_count = 0
        
        with open(args.file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                raw_sym = row.get('SYMBOL', '').strip()
                sector_raw = row.get('SECTOR', '').strip().upper()
                table_name = SECTOR_MAP.get(sector_raw)

                if not raw_sym or not table_name:
                    continue

                norm = symbol_validation_service.normalize_symbol(raw_sym)
                if norm == 'SYMBOL':
                    continue

                classification = symbol_validation_service.classify_symbol(norm)
                if classification in ('INVALID', 'BSE_ONLY', 'BELOW_500CR', 'NO_TRADING'):
                    print(f"Skipping invalid/excluded symbol: {raw_sym} ({classification})")
                    skipped_count += 1
                    continue

                symbol = symbol_validation_service.replace_old_symbol(norm)
                if symbol != norm:
                    replaced_count += 1

                cols = _load_columns(cursor, table_name)

                merge_sql = f"""
                MERGE INTO {table_name} t
                USING (SELECT :symbol AS symbol FROM dual) s
                ON (t.symbol = s.symbol)
                WHEN NOT MATCHED THEN INSERT (symbol
                """
                vals_sql = ") VALUES (s.symbol"
                binds = {'symbol': symbol}

                if 'SECTOR' in cols:
                    merge_sql += ", sector"
                    vals_sql += ", :sector"
                    binds['sector'] = sector_raw.title()
                if 'ACTIVE_FLAG' in cols:
                    merge_sql += ", active_flag"
                    vals_sql += ", 'Y'"

                merge_sql += vals_sql + ")"

                cursor.execute(merge_sql, binds)
                loaded_count += 1

        conn.commit()
        print(f"Successfully processed and merged {loaded_count} symbols into their respective staging tables.")

    finally:
        conn.close()


if __name__ == '__main__':
    main()
