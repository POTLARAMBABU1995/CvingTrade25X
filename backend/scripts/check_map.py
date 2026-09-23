import sys
from pathlib import Path
sys.path.insert(0, str(Path('backend').resolve()))
from db import get_oracle_connection

conn = get_oracle_connection()
cursor = conn.cursor()
cursor.execute("SELECT SECTOR_CODE, COUNT(*) FROM NSE_SYMBOL_SECTOR_MAP WHERE SECTOR_CODE IN ('CONSUMER_ELECTRONICS', 'CONSUMER_SERVICES', 'ELEC_SERVICES_CONS_DURABLES', 'CONS_DUR') GROUP BY SECTOR_CODE")
for row in cursor.fetchall():
    print(row)
