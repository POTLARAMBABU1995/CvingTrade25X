import sys
from pathlib import Path
sys.path.insert(0, str(Path('backend').resolve()))
from db import get_oracle_connection

conn = get_oracle_connection()
cursor = conn.cursor()
cursor.execute("SELECT MAX(TRADE_DATE) FROM STOCK_EOD_HISTORY")
print('Max Date Overall:', cursor.fetchone()[0])
cursor.execute("SELECT MAX(TRADE_DATE) FROM STOCK_EOD_HISTORY WHERE SYMBOL='BAJAJELEC'")
print('Max Date BAJAJELEC:', cursor.fetchone()[0])

cursor.execute("SELECT MAX(TRADE_DATE) FROM STOCK_EOD_HISTORY WHERE SYMBOL='RELIANCE'")
print('Max Date RELIANCE:', cursor.fetchone()[0])
