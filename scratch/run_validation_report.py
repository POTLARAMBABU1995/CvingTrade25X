import sys
from pathlib import Path
sys.path.insert(0, 'backend')
from db import get_oracle_connection

def run_query_and_print(cursor, title, sql):
    print(f"\n--- {title} ---")
    try:
        cursor.execute(sql)
        cols = [desc[0] for desc in cursor.description]
        print(" | ".join(cols))
        print("-" * 50)
        rows = cursor.fetchall()
        for r in rows:
            print(" | ".join(str(val) for val in r))
        print(f"Total rows: {len(rows)}")
    except Exception as e:
        print(f"Error: {e}")

conn = get_oracle_connection()
try:
    with conn.cursor() as cursor:
        run_query_and_print(
            cursor,
            "1. Table presence in user_tables",
            """
            SELECT table_name
            FROM user_tables
            WHERE table_name IN (
                'NSE_NIFTY_ENGINEERING_STAGING',
                'NSE_NIFTY_ELEC_HEAVY_EQUIP_STAGING',
                'NSE_NIFTY_INDUSTRIAL_MANUFACTURING_STAGING',
                'NSE_NIFTY_INDUSTRIAL_PRODUCTS_STAGING',
                'NSE_NIFTY_INDUSTRIAL_GASES_FUELS_STAGING',
                'NSE_NIFTY_CAPITAL_GOODS_STAGING'
            )
            ORDER BY table_name
            """
        )
        
        run_query_and_print(
            cursor,
            "2. Master codes in nse_sector_master",
            """
            SELECT sector_code, sector_name, index_code, display_order
            FROM nse_sector_master
            WHERE sector_code IN (
                'ENGINEERING',
                'ELEC_HEAVY_EQUIPMENT',
                'INDUSTRIAL_MANUFACTURING',
                'INDUSTRIAL_PRODUCTS',
                'INDUSTRIAL_GASES_FUELS',
                'CAPITAL_GOODS'
            )
            ORDER BY sector_code
            """
        )

        run_query_and_print(
            cursor,
            "3. Staging row counts",
            """
            SELECT 'NSE_NIFTY_ENGINEERING_STAGING' AS table_name, COUNT(*) AS row_count FROM NSE_NIFTY_ENGINEERING_STAGING UNION ALL
            SELECT 'NSE_NIFTY_ELEC_HEAVY_EQUIP_STAGING' AS table_name, COUNT(*) AS row_count FROM NSE_NIFTY_ELEC_HEAVY_EQUIP_STAGING UNION ALL
            SELECT 'NSE_NIFTY_INDUSTRIAL_MANUFACTURING_STAGING' AS table_name, COUNT(*) AS row_count FROM NSE_NIFTY_INDUSTRIAL_MANUFACTURING_STAGING UNION ALL
            SELECT 'NSE_NIFTY_INDUSTRIAL_PRODUCTS_STAGING' AS table_name, COUNT(*) AS row_count FROM NSE_NIFTY_INDUSTRIAL_PRODUCTS_STAGING UNION ALL
            SELECT 'NSE_NIFTY_INDUSTRIAL_GASES_FUELS_STAGING' AS table_name, COUNT(*) AS row_count FROM NSE_NIFTY_INDUSTRIAL_GASES_FUELS_STAGING UNION ALL
            SELECT 'NSE_NIFTY_CAPITAL_GOODS_STAGING' AS table_name, COUNT(*) AS row_count FROM NSE_NIFTY_CAPITAL_GOODS_STAGING
            """
        )

        run_query_and_print(
            cursor,
            "4. Duplicate symbols inside new staging tables",
            """
            SELECT 'ENGINEERING' as sec, symbol, COUNT(*) AS dups FROM NSE_NIFTY_ENGINEERING_STAGING GROUP BY symbol HAVING COUNT(*) > 1 UNION ALL
            SELECT 'ELEC_HEAVY' as sec, symbol, COUNT(*) AS dups FROM NSE_NIFTY_ELEC_HEAVY_EQUIP_STAGING GROUP BY symbol HAVING COUNT(*) > 1 UNION ALL
            SELECT 'IND_MFG' as sec, symbol, COUNT(*) AS dups FROM NSE_NIFTY_INDUSTRIAL_MANUFACTURING_STAGING GROUP BY symbol HAVING COUNT(*) > 1 UNION ALL
            SELECT 'IND_PROD' as sec, symbol, COUNT(*) AS dups FROM NSE_NIFTY_INDUSTRIAL_PRODUCTS_STAGING GROUP BY symbol HAVING COUNT(*) > 1 UNION ALL
            SELECT 'IND_GAS' as sec, symbol, COUNT(*) AS dups FROM NSE_NIFTY_INDUSTRIAL_GASES_FUELS_STAGING GROUP BY symbol HAVING COUNT(*) > 1 UNION ALL
            SELECT 'CAP_GOODS' as sec, symbol, COUNT(*) AS dups FROM NSE_NIFTY_CAPITAL_GOODS_STAGING GROUP BY symbol HAVING COUNT(*) > 1
            """
        )

        run_query_and_print(
            cursor,
            "5. Canonical source view registration check",
            """
            SELECT DISTINCT sector_code, source_table
            FROM VW_NSE_CANONICAL_SECTOR_STAGE
            WHERE sector_code IN (
                'ENGINEERING',
                'ELEC_HEAVY_EQUIPMENT',
                'INDUSTRIAL_MANUFACTURING',
                'INDUSTRIAL_PRODUCTS',
                'INDUSTRIAL_GASES_FUELS',
                'CAPITAL_GOODS'
            )
            ORDER BY sector_code
            """
        )

        run_query_and_print(
            cursor,
            "6. Symbol-sector map counts",
            """
            SELECT sector_code, COUNT(*) AS mapped_symbols
            FROM NSE_SYMBOL_SECTOR_MAP
            WHERE sector_code IN (
                'ENGINEERING',
                'ELEC_HEAVY_EQUIPMENT',
                'INDUSTRIAL_MANUFACTURING',
                'INDUSTRIAL_PRODUCTS',
                'INDUSTRIAL_GASES_FUELS',
                'CAPITAL_GOODS'
            )
            GROUP BY sector_code
            ORDER BY sector_code
            """
        )

        run_query_and_print(
            cursor,
            "7. DEV table to staging table join check",
            """
            SELECT s.sector_code, COUNT(d.symbol) AS active_price_rows
            FROM NSE_SYMBOL_SECTOR_MAP s
            JOIN NSE_NIFTY500_DAILY_RAW_DATA_DEV d ON UPPER(TRIM(d.symbol)) = UPPER(TRIM(s.symbol))
            WHERE s.sector_code IN (
                'ENGINEERING',
                'ELEC_HEAVY_EQUIPMENT',
                'INDUSTRIAL_MANUFACTURING',
                'INDUSTRIAL_PRODUCTS',
                'INDUSTRIAL_GASES_FUELS',
                'CAPITAL_GOODS'
            )
            GROUP BY s.sector_code
            ORDER BY s.sector_code
            """
        )
finally:
    conn.close()
