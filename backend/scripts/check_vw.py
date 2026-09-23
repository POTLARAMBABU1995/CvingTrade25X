import sys
from pathlib import Path
sys.path.insert(0, str(Path('backend').resolve()))
from db import get_oracle_connection

conn = get_oracle_connection()
cursor = conn.cursor()
cursor.execute("SELECT text FROM user_views WHERE view_name = 'VW_SECTOR_BREADTH'")
rows = cursor.fetchall()
with open('vw.txt', 'w') as f:
    for r in rows:
        f.write(str(r[0].read()) if hasattr(r[0], 'read') else str(r[0]))
