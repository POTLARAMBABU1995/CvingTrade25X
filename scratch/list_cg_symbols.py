import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from db import get_oracle_connection

conn = get_oracle_connection()
try:
    with conn.cursor() as cursor:
        cursor.execute("SELECT symbol FROM NSE_NIFTY_CAPITAL_GOODS_STAGING ORDER BY symbol")
        symbols = [row[0] for row in cursor.fetchall()]
        print("Existing CAPITAL_GOODS symbols:", symbols)
finally:
    conn.close()
