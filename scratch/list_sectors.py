import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from db import get_oracle_connection

conn = get_oracle_connection()
try:
    with conn.cursor() as cursor:
        cursor.execute("SELECT sector_code, sector_name, index_code FROM nse_sector_master ORDER BY sector_code")
        for row in cursor.fetchall():
            print(f"Code: {row[0]}, Name: {row[1]}, Index: {row[2]}")
finally:
    conn.close()
