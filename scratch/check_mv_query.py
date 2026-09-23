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
        cursor.execute("SELECT dbms_metadata.get_ddl('MATERIALIZED_VIEW', 'MV_NSE_SECTOR_UI_SNAPSHOT') FROM dual")
        ddl = cursor.fetchone()[0]
        print("DDL of MV_NSE_SECTOR_UI_SNAPSHOT:")
        print(ddl.read() if hasattr(ddl, 'read') else ddl)
except Exception as e:
    print("Error:", e)
finally:
    conn.close()
