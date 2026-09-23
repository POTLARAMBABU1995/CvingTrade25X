import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from db import get_oracle_connection

conn = get_oracle_connection()
try:
    with conn.cursor() as cur:
        cur.execute("SELECT sector_code FROM NSE_SECTOR_MASTER WHERE sector_code = 'AGRICULTURE'")
        row = cur.fetchone()
        print("NSE_SECTOR_MASTER entry:", row)
except Exception as e:
    print("Error:", e)
