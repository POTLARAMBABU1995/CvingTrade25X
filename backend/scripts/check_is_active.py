import sys
from pathlib import Path
sys.path.insert(0, str(Path('backend').resolve()))
from db import get_oracle_connection

conn = get_oracle_connection()
cursor = conn.cursor()
cursor.execute("SELECT sector_code, is_active FROM nse_sector_master WHERE sector_code IN ('CONSUMER_ELECTRONICS', 'CONSUMER_SERVICES', 'ELEC_SERVICES_CONS_DURABLES', 'CONS_DUR', 'CONSUMER_DURABLES')")
rows = cursor.fetchall()
with open('is_active.txt', 'w') as f:
    for r in rows:
        f.write(str(r) + '\n')
