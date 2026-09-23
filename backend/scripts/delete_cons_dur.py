import sys
from pathlib import Path
sys.path.insert(0, str(Path('backend').resolve()))
from db import get_oracle_connection

conn = get_oracle_connection()
c = conn.cursor()
c.execute("DELETE FROM NSE_SYMBOL_SECTOR_MAP WHERE SECTOR_CODE = 'CONS_DUR'")
c.execute("DELETE FROM NSE_SECTOR_MASTER WHERE SECTOR_CODE = 'CONS_DUR'")
conn.commit()
print("Deleted CONS_DUR")
