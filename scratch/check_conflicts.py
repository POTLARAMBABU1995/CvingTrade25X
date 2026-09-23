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
        # Get list of all staging tables
        cursor.execute("SELECT table_name FROM user_tables WHERE table_name LIKE 'NSE_NIFTY%STAGING' ORDER BY table_name")
        staging_tables = [r[0] for r in cursor.fetchall()]
        print("Existing staging tables in DB:")
        for t in staging_tables:
            cursor.execute(f"SELECT COUNT(*) FROM {t}")
            cnt = cursor.fetchone()[0]
            print(f"  {t}: {cnt} rows")

        # Let's list symbols for Alcohol-Breweries
        alcohol_symbols = ['ABDL', 'ALCODIS', 'ASALCBR', 'BCLIND', 'COMFINTE', 'GLOBUSSPR', 'GMBREW', 'IFBAGRO', 'INDIAGLYCO', 'JAGAJITIND', 'PICCADIL', 'RADICO', 'RKDL', 'SDBL', 'SULA', 'TI', 'UBL', 'UNITDSPR']
        
        # Let's list symbols for Auto Ancillaries
        auto_anc_symbols = ['ACGL', 'ALICON', 'APOLLOTYRE', 'ARE&M', 'ASAHIINDIA', 'ASAL', 'ASKAUTOLTD', 'AUTOAXLES', 'BALKRISIND', 'BANCOINDIA', 'BHARATFORG', 'BOSCHLTD', 'CEATLTD', 'CIEINDIA', 'CRAFTSMAN', 'ENDURANCE', 'EXIDEIND', 'FIEMIND', 'GABRIEL', 'GNA', 'HBLENGINE', 'JAMNAAUTO', 'JBMA', 'JKTYRE', 'JTEKTINDIA']
        
        all_new_symbols = {
            'ALCOHOL_BREWERIES': alcohol_symbols,
            'AUTO_ANCILLARIES': auto_anc_symbols
        }

        # Check if they exist in other staging tables
        for sector_name, symbols in all_new_symbols.items():
            print(f"\nChecking conflicts for {sector_name}:")
            for t in staging_tables:
                # We can query each table
                cursor.execute(f"SELECT symbol FROM {t}")
                tbl_syms = [r[0].strip().upper() for r in cursor.fetchall() if r[0]]
                conflicts = set(symbols).intersection(tbl_syms)
                if conflicts:
                    print(f"  Conflict with staging table {t}: {conflicts}")
                    
            # Check NSE_SYMBOL_SECTOR_MAP
            placeholders = ', '.join([f"'{s}'" for s in symbols])
            cursor.execute(f"SELECT symbol, sector_code FROM NSE_SYMBOL_SECTOR_MAP WHERE UPPER(TRIM(symbol)) IN ({placeholders})")
            mappings = cursor.fetchall()
            if mappings:
                print("  Conflict / Mappings in NSE_SYMBOL_SECTOR_MAP:")
                for m in mappings:
                    print(f"    {m[0]} -> {m[1]}")
finally:
    conn.close()
