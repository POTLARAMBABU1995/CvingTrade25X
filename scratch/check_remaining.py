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
        cursor.execute("SELECT table_name FROM user_tables WHERE table_name LIKE 'NSE_NIFTY%STAGING' ORDER BY table_name")
        staging_tables = [r[0] for r in cursor.fetchall()]

        extra_syms = ['LUMAXIND', 'LUMAXTECH', 'MINDACORP', 'MOTHERSON', 'MRF', 'MSUMI', 'PRICOLLTD', 'RKFORGE', 'SANDHAR', 'SCHAEFFLER', 'SONACOMS', 'SUBROS', 'SUNDRMFAST', 'SUPRAJIT', 'TALBROAUTO', 'TIINDIA', 'UNOMINDA', 'VARROC', 'ZFCVINDIA']
        
        for s in extra_syms:
            found_tables = []
            for t in staging_tables:
                cursor.execute(f"SELECT COUNT(*) FROM {t} WHERE UPPER(TRIM(symbol)) = :sym", {'sym': s})
                if cursor.fetchone()[0] > 0:
                    found_tables.append(t)
            
            cursor.execute("SELECT sector_code FROM NSE_SYMBOL_SECTOR_MAP WHERE UPPER(TRIM(symbol)) = :sym", {'sym': s})
            sec_map = cursor.fetchone()
            sec_map_code = sec_map[0] if sec_map else 'None'
            
            print(f"{s}: tables={found_tables}, mapped={sec_map_code}")
finally:
    conn.close()
