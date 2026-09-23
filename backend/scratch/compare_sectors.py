import os
from routes.sector_rotation import _STRICT_SECTOR_TABLE_MAP
from db import get_oracle_connection

conn = get_oracle_connection()
c = conn.cursor()
c.execute("SELECT sector_code FROM nse_sector_master")
db_sectors = {r[0] for r in c.fetchall()}

defined = set(_STRICT_SECTOR_TABLE_MAP.keys())

missing_in_db = defined - db_sectors
missing_in_code = db_sectors - defined

print("Missing in DB:", missing_in_db)
print("Missing in code:", missing_in_code)
