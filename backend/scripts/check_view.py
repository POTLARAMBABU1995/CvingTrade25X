import sys
from pathlib import Path
sys.path.insert(0, str(Path('backend').resolve()))
from db import get_oracle_connection

conn = get_oracle_connection()
cursor = conn.cursor()
cursor.execute("SELECT text FROM user_views WHERE view_name = 'VW_NSE_CANONICAL_SECTOR_STAGE'")
row = cursor.fetchone()
if row:
    print(row[0].read() if hasattr(row[0], 'read') else row[0])
else:
    print("View not found.")
