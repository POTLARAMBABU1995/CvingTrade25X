import os
from dotenv import load_dotenv
import sys

root_dir = r"c:\Users\admin\Documents\CvingTrade25X\CvingTrade25X"
load_dotenv(os.path.join(root_dir, '.env'))

sys.path.append(os.path.join(root_dir, 'backend'))
from db import get_oracle_connection

conn = get_oracle_connection()
try:
    with conn.cursor() as cursor:
        cursor.execute("SELECT object_type FROM user_objects WHERE object_name = 'MV_NSE_SECTOR_UI_SNAPSHOT_SRC'")
        row = cursor.fetchone()
        if not row:
            print("Object MV_NSE_SECTOR_UI_SNAPSHOT_SRC not found")
            sys.exit(0)
        obj_type = row[0]
        print("Object type:", obj_type)
        cursor.execute(f"SELECT dbms_metadata.get_ddl('{obj_type}', 'MV_NSE_SECTOR_UI_SNAPSHOT_SRC') FROM dual")
        ddl = cursor.fetchone()[0]
        print(ddl.read() if hasattr(ddl, 'read') else ddl)
except Exception as e:
    print("Error:", e)
finally:
    conn.close()
