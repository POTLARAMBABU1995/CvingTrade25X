"""Idempotently install the Dairy & Milk Products sector reference data."""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db import get_oracle_connection

SYMBOLS = {
    "HATSUN": "Integrated Dairy & Ice Cream",
    "DODLA": "Milk Processing & Dairy Products",
    "HERITGFOOD": "Milk Processing & Value-Added Dairy",
    "PARAGMILK": "Value-Added Dairy Products",
    "KWIL": "Ice Cream & Frozen Desserts",
    "VADILALIND": "Ice Cream & Frozen Foods",
}


def add_column(cursor, table: str, column: str, definition: str) -> None:
    cursor.execute(
        "SELECT COUNT(*) FROM user_tab_columns WHERE table_name=:table_name AND column_name=:column_name",
        {"table_name": table, "column_name": column},
    )
    if int(cursor.fetchone()[0]) == 0:
        cursor.execute(f"ALTER TABLE {table} ADD ({column} {definition})")


def main() -> None:
    conn = get_oracle_connection()
    try:
        cur = conn.cursor()
        for column, definition in {
            "PARENT_SECTOR": "VARCHAR2(100)",
            "INDUSTRY": "VARCHAR2(150)",
            "IS_ACTIVE": "CHAR(1) DEFAULT 'Y'",
            "CREATED_AT": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "UPDATED_AT": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        }.items():
            add_column(cur, "NSE_SECTOR_MASTER", column, definition)
        for column, definition in {
            "PARENT_SECTOR": "VARCHAR2(100)",
            "INDUSTRY": "VARCHAR2(150)",
            "BUSINESS_CLASSIFICATION": "VARCHAR2(200)",
            "IS_ACTIVE": "CHAR(1) DEFAULT 'Y'",
            "SOURCE": "VARCHAR2(100)",
            "CREATED_AT": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "UPDATED_AT": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        }.items():
            add_column(cur, "NSE_SYMBOL_SECTOR_MAP", column, definition)

        cur.execute("""
            SELECT COUNT(*) FROM user_tables
            WHERE table_name='NSE_NIFTY_DAIRY_MILK_PRODUCTS_STAGING'
        """)
        if int(cur.fetchone()[0]) == 0:
            cur.execute(
                "CREATE TABLE NSE_NIFTY_DAIRY_MILK_PRODUCTS_STAGING "
                "AS SELECT * FROM NSE_NIFTY_FMCG_STAGING WHERE 1=0"
            )

        cur.execute("""
            MERGE INTO nse_sector_master t
            USING (SELECT 'DAIRY_MILK_PRODUCTS' code, 'DAIRY & MILK PRODUCTS' name, 'NIFTY_FMCG' index_code FROM dual) s
            ON (t.sector_code=s.code)
            WHEN MATCHED THEN UPDATE SET t.sector_name=s.name, t.parent_sector='FMCG',
              t.industry='FOOD PRODUCTS', t.is_active='Y', t.updated_at=CURRENT_TIMESTAMP
            WHEN NOT MATCHED THEN INSERT
              (sector_code, sector_name, index_code, parent_sector, industry, display_order, is_active, created_at, updated_at)
              VALUES (s.code, s.name, s.index_code, 'FMCG', 'FOOD PRODUCTS', 999, 'Y', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """)

        valid = []
        for symbol in SYMBOLS:
            cur.execute(
                "SELECT COUNT(*) FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV WHERE UPPER(TRIM(symbol))=:symbol",
                {"symbol": symbol},
            )
            if int(cur.fetchone()[0]):
                valid.append(symbol)
                cur.execute(
                    """MERGE INTO NSE_NIFTY_DAIRY_MILK_PRODUCTS_STAGING t
                    USING (SELECT :symbol symbol, 'DAIRY_MILK_PRODUCTS' sector FROM dual) s
                    ON (UPPER(TRIM(t.symbol))=s.symbol)
                    WHEN MATCHED THEN UPDATE SET t.sector=s.sector
                    WHEN NOT MATCHED THEN INSERT (symbol, sector) VALUES (s.symbol, s.sector)""",
                    {"symbol": symbol},
                )
                cur.execute(
                    """MERGE INTO nse_symbol_sector_map t
                    USING (SELECT :symbol symbol FROM dual) s
                    ON (UPPER(TRIM(t.symbol))=s.symbol)
                    WHEN MATCHED THEN UPDATE SET t.sector_code='DAIRY_MILK_PRODUCTS', t.parent_sector='FMCG', t.industry='FOOD PRODUCTS',
                      t.business_classification=:classification, t.is_active='Y',
                      t.source='MANUAL_SECTOR_ENHANCEMENT', t.updated_at=CURRENT_TIMESTAMP
                    WHEN NOT MATCHED THEN INSERT
                      (symbol, sector_code, parent_sector, industry, business_classification, is_active, source, created_at, updated_at)
                      VALUES (s.symbol, 'DAIRY_MILK_PRODUCTS', 'FMCG', 'FOOD PRODUCTS', :classification,
                        'Y', 'MANUAL_SECTOR_ENHANCEMENT', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
                    {"symbol": symbol, "classification": SYMBOLS[symbol]},
                )
        conn.commit()
        print({"sector": "DAIRY_MILK_PRODUCTS", "valid_symbols": valid, "missing_symbols": sorted(set(SYMBOLS) - set(valid))})
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
