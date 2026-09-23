import sys
from pathlib import Path
sys.path.insert(0, str(Path('backend').resolve()))
from db import get_oracle_connection

conn = get_oracle_connection()
cursor = conn.cursor()

cursor.execute("SELECT sector_code, COUNT(DISTINCT symbol) FROM VW_NSE_CANONICAL_SECTOR_STAGE GROUP BY sector_code")
rows = cursor.fetchall()
for r in rows:
    if 'CONSUMER' in r[0] or 'ELEC' in r[0] or 'CONS_DUR' in r[0]:
        print(r)

cursor.execute("SELECT sector_code, COUNT(DISTINCT symbol) FROM NSE_SYMBOL_SECTOR_MAP GROUP BY sector_code")
rows = cursor.fetchall()
print("NSE_SYMBOL_SECTOR_MAP:")
for r in rows:
    if 'CONSUMER' in r[0] or 'ELEC' in r[0] or 'CONS_DUR' in r[0]:
        print(r)
