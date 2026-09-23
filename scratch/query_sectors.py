import os
from dotenv import load_dotenv

root_dir = r"c:\Users\admin\Documents\CvingTrade25X\CvingTrade25X"
load_dotenv(os.path.join(root_dir, '.env'))

import sys
sys.path.append(os.path.join(root_dir, 'backend'))
from db import get_oracle_connection

conn = get_oracle_connection()
try:
    with conn.cursor() as cursor:
        print("--- 1. Discovering Staging Tables ---")
        cursor.execute("""
            SELECT DISTINCT utc.table_name
            FROM user_tab_columns utc
            JOIN user_tables ut ON ut.table_name = utc.table_name
            WHERE utc.column_name = 'SYMBOL'
              AND utc.table_name LIKE 'NSE_NIFTY%STAGING'
            ORDER BY utc.table_name
        """)
        tables = [r[0] for r in cursor.fetchall()]
        for table in tables:
            cursor.execute(f"SELECT COUNT(DISTINCT UPPER(TRIM(symbol))) FROM {table}")
            cnt = cursor.fetchone()[0]
            print(f"Table: {table} | Distinct Symbols: {cnt}")

        print("\n--- 2. Sector Mappings in NSE_SYMBOL_SECTOR_MAP ---")
        for sector in ('ALCOHOL_BREWERIES', 'AUTO_ANCILLARIES'):
            cursor.execute("""
                SELECT COUNT(*), MIN(symbol), MAX(symbol)
                FROM NSE_SYMBOL_SECTOR_MAP
                WHERE sector_code = :sec
            """, {'sec': sector})
            r = cursor.fetchone()
            print(f"Sector: {sector} | Total Mapped: {r[0]} | Sample: {r[1]} to {r[2]}")

        print("\n--- 3. Latest Date in NSE_NIFTY500_DAILY_RAW_DATA_DEV ---")
        cursor.execute("SELECT MAX(trading_date) FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV")
        latest_date = cursor.fetchone()[0]
        print("Latest date:", latest_date)

        print("\n--- 4. Pricing data in NSE_NIFTY500_DAILY_RAW_DATA_DEV for latest date ---")
        for sector in ('ALCOHOL_BREWERIES', 'AUTO_ANCILLARIES'):
            cursor.execute("""
                SELECT COUNT(*)
                FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV d
                JOIN NSE_SYMBOL_SECTOR_MAP m ON UPPER(TRIM(d.symbol)) = UPPER(TRIM(m.symbol))
                WHERE m.sector_code = :sec
                  AND d.trading_date = :dt
            """, {'sec': sector, 'dt': latest_date})
            count = cursor.fetchone()[0]
            print(f"Sector: {sector} | Pricing Rows on {latest_date}: {count}")

finally:
    conn.close()
