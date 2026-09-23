import sys
from pathlib import Path
sys.path.insert(0, str(Path('backend').resolve()))
from db import get_oracle_connection

conn = get_oracle_connection()
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV WHERE SYMBOL='BAJAJELEC'")
print('BAJAJELEC in RAW_DATA_DEV:', cursor.fetchone()[0])
