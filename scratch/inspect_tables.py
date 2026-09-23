import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_BACKEND_ROOT = _HERE.parent / 'backend'
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from db import get_oracle_connection

def inspect():
    conn = get_oracle_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Inspect tables
            cursor.execute("SELECT table_name FROM user_tables WHERE table_name LIKE 'NSE_NIFTY%' ORDER BY table_name")
            print("=== NSE_NIFTY% Tables ===")
            for row in cursor.fetchall():
                print(row[0])
            
            # 2. Inspect sector master
            cursor.execute("SELECT sector_code, sector_name, index_code FROM nse_sector_master ORDER BY sector_code")
            print("\n=== Sector Master ===")
            for row in cursor.fetchall():
                print(row)
    finally:
        conn.close()

if __name__ == '__main__':
    inspect()
