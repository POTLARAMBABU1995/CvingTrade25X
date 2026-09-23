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
        alcohol_symbols = ['ABDL', 'ALCODIS', 'ASALCBR', 'BCLIND', 'COMFINTE', 'GLOBUSSPR', 'GMBREW', 'IFBAGRO', 'INDIAGLYCO', 'JAGAJITIND', 'PICCADIL', 'RADICO', 'RKDL', 'SDBL', 'SULA', 'TI', 'UBL', 'UNITDSPR']
        placeholders = ', '.join([f"'{s}'" for s in alcohol_symbols])
        cursor.execute(f"SELECT symbol, sector_code FROM NSE_SYMBOL_SECTOR_MAP WHERE UPPER(TRIM(symbol)) IN ({placeholders})")
        rows = cursor.fetchall()
        print("Alcohol symbols in NSE_SYMBOL_SECTOR_MAP:")
        for r in rows:
            print(f"  {r[0]} -> {r[1]}")
finally:
    conn.close()
