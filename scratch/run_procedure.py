import sys
from pathlib import Path
sys.path.insert(0, 'backend')
from db import get_oracle_connection

conn = get_oracle_connection()
try:
    with conn.cursor() as cursor:
        print("Executing PR_SYNC_SECTOR_REFERENCE_DATA...")
        cursor.execute("BEGIN PR_SYNC_SECTOR_REFERENCE_DATA; END;")
        conn.commit()
        print("Success.")
finally:
    conn.close()
