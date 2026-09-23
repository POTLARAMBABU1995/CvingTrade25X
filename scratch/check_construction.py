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
            cursor.execute("SELECT count(*) FROM user_tables WHERE table_name = 'NSE_NIFTY_CONSTRUCTION_STAGING'")
            exists = cursor.fetchone()[0]
            if exists:
                cursor.execute("SELECT symbol FROM NSE_NIFTY_CONSTRUCTION_STAGING ORDER BY symbol")
                symbols = [r[0] for r in cursor.fetchall()]
                print(f"NSE_NIFTY_CONSTRUCTION_STAGING symbols ({len(symbols)}):")
                print(symbols)
            else:
                print("NSE_NIFTY_CONSTRUCTION_STAGING does not exist")
    finally:
        conn.close()

if __name__ == '__main__':
    inspect()
