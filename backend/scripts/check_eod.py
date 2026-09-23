import sys
from pathlib import Path
sys.path.insert(0, str(Path('backend').resolve()))
from db import get_oracle_connection

conn = get_oracle_connection()
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM STOCK_EOD_HISTORY WHERE SYMBOL='BAJAJELEC'")
print("BAJAJELEC count:", cursor.fetchone()[0])
