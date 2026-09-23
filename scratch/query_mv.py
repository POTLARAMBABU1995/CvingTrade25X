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
        cursor.execute("SELECT COLUMN_NAME, DATA_TYPE FROM USER_TAB_COLUMNS WHERE TABLE_NAME = 'MV_NSE_SECTOR_UI_SNAPSHOT'")
        print("Columns:")
        for r in cursor.fetchall():
            print(r)
        
        cursor.execute("SELECT COUNT(*), COUNT(DISTINCT sector) FROM MV_NSE_SECTOR_UI_SNAPSHOT")
        cnt, sectors = cursor.fetchone()
        print(f"Total Rows: {cnt}, Distinct Sectors: {sectors}")

        cursor.execute("SELECT DISTINCT sector FROM MV_NSE_SECTOR_UI_SNAPSHOT ORDER BY sector")
        print("Sectors in MV:")
        for r in cursor.fetchall():
            print(r[0])
except Exception as e:
    print("Error:", e)
finally:
    conn.close()
