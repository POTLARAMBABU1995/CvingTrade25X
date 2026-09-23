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
        print("Refreshing MV_NSE_SECTOR_UI_SNAPSHOT...")
        cursor.execute("BEGIN DBMS_MVIEW.REFRESH('MV_NSE_SECTOR_UI_SNAPSHOT', 'C'); END;")
        print("Refreshing MV_NSE_SECTOR_BREADTH...")
        cursor.execute("BEGIN DBMS_MVIEW.REFRESH('MV_NSE_SECTOR_BREADTH', 'C'); END;")
        conn.commit()
        print("Materialized views refreshed successfully!")
except Exception as e:
    print("Error:", e)
finally:
    conn.close()
