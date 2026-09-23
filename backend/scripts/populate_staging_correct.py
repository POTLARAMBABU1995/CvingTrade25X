import sys
from pathlib import Path
import pandas as pd
import datetime

sys.path.insert(0, str(Path('backend').resolve()))
from db import get_oracle_connection

conn = get_oracle_connection()
cursor = conn.cursor()

csv_dir = Path(r"G:\SECTOR\CONSUMER_DURABLES_ELECTRONICS_SERVICES")
files = {
    'NSE_NIFTY_ELECTRONICS_SERVICES_CONSUMER_DURABLES_STAGING': 'ELECTRONICS_AND_SERVICES_CONSUMER_DURABLES.csv',
    'NSE_NIFTY_CONSUMER_ELECTRONICS_STAGING': 'CONSUMER_ELECTRONICS.csv',
    'NSE_NIFTY_CONSUMER_SERVICES_STAGING': 'CONSUMER_SERVICES.csv',
    'NSE_NIFTY_CONSUMER_DURABLES_STAGING': 'CONSUMER_DURABLES.csv'
}

for table_name, file_name in files.items():
    file_path = csv_dir / file_name
    if not file_path.exists():
        print(f"Skipping {file_name}")
        continue
    
    df = pd.read_csv(file_path)
    # the column is usually Symbol or SYMBOL
    col = 'Symbol' if 'Symbol' in df.columns else 'SYMBOL' if 'SYMBOL' in df.columns else df.columns[0]
    symbols = df[col].dropna().unique().tolist()
    
    # Delete existing rows
    cursor.execute(f"DELETE FROM {table_name}")
    
    # Insert new rows
    for sym in symbols:
        cursor.execute(f"INSERT INTO {table_name} (SYMBOL) VALUES (:sym)", {'sym': str(sym).strip()})
    
    print(f"Inserted {len(symbols)} symbols into {table_name}")

conn.commit()
