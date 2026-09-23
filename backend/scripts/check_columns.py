import sys
from pathlib import Path
sys.path.insert(0, str(Path('backend').resolve()))
from db import get_oracle_connection

conn = get_oracle_connection()
cursor = conn.cursor()
cursor.execute("SELECT column_name, data_type, data_length FROM user_tab_columns WHERE table_name = 'NSE_SECTOR_MASTER'")
print(cursor.fetchall())

cursor.execute("SELECT sector_code FROM nse_sector_master WHERE sector_code LIKE 'ELEC%' OR sector_code LIKE 'CONS%'")
print(cursor.fetchall())
