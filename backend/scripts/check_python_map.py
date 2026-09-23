import sys
from pathlib import Path
sys.path.insert(0, str(Path('backend').resolve()))
from db import get_oracle_connection
from routes.sector_rotation import _STRICT_SECTOR_TABLE_MAP

conn = get_oracle_connection()
cursor = conn.cursor()
cursor.execute("SELECT sector_code FROM nse_sector_master")
db_sectors = set(r[0] for r in cursor.fetchall())

print("Missing in python _STRICT_SECTOR_TABLE_MAP:")
for code in db_sectors:
    if code not in _STRICT_SECTOR_TABLE_MAP:
        print(code)
