import sys
from pathlib import Path
sys.path.insert(0, str(Path('backend').resolve()))
from db import get_oracle_connection

conn = get_oracle_connection()
cursor = conn.cursor()
cursor.execute("SELECT TRADING_DATE, PREVIOUS_CLOSE FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV WHERE SYMBOL='BAJAJELEC' ORDER BY TRADING_DATE DESC FETCH FIRST 5 ROWS ONLY")
print("RAW_DATA_DEV:")
for row in cursor.fetchall():
    print(row)
