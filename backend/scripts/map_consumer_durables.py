import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path('backend').resolve()))
from db import get_oracle_connection

conn = get_oracle_connection()
c = conn.cursor()

file_path = Path(r"G:\SECTOR\CONSUMER_DURABLES_ELECTRONICS_SERVICES\CONSUMER_DURABLES.csv")
df = pd.read_csv(file_path)
col = 'Symbol' if 'Symbol' in df.columns else 'SYMBOL' if 'SYMBOL' in df.columns else df.columns[0]
symbols = df[col].dropna().unique().tolist()

c.execute("DELETE FROM NSE_SYMBOL_SECTOR_MAP WHERE SECTOR_CODE = 'CONSUMER_DURABLES'")

for sym in symbols:
    try:
        c.execute(
            "INSERT INTO NSE_SYMBOL_SECTOR_MAP (SYMBOL, SECTOR_CODE, IS_ACTIVE) VALUES (:1, :2, 1)",
            (str(sym).strip(), 'CONSUMER_DURABLES')
        )
    except Exception as e:
        pass
        
print(f"Inserted {len(symbols)} into NSE_SYMBOL_SECTOR_MAP for CONSUMER_DURABLES")
conn.commit()
