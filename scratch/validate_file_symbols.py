import os
import csv
from dotenv import load_dotenv

root_dir = r"c:\Users\admin\Documents\CvingTrade25X\CvingTrade25X"
load_dotenv(os.path.join(root_dir, '.env'))

import sys
sys.path.append(os.path.join(root_dir, 'backend'))
from db import get_oracle_connection

def read_symbols(filepath):
    symbols = []
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        sym_col_idx = -1
        for idx, col in enumerate(header):
            col_norm = col.strip().lower()
            if 'symbol' in col_norm or 'ticker' in col_norm:
                sym_col_idx = idx
                break
        if sym_col_idx == -1:
            sym_col_idx = 0
        for row in reader:
            if row:
                sym = row[sym_col_idx].strip()
                if sym:
                    symbols.append(sym)
    return symbols

files = {
    'alcohol_breweries': r"G:\SECTOR\alcohol_breweries_nse_symbols_final.csv",
    'automobile_ancillaries': r"G:\SECTOR\automobile_ancillaries_nse_stocks.csv",
    'auto_ancillaries_over_500cr': r"G:\SECTOR\AUTO ANCILLARIES\Auto_Ancillaries_Over_500Cr.csv"
}

conn = get_oracle_connection()
try:
    with conn.cursor() as cursor:
        for name, path in files.items():
            print(f"\n--- File: {name} ({os.path.basename(path)}) ---")
            raw_symbols = read_symbols(path)
            print("Total raw symbols:", len(raw_symbols))
            
            valid = []
            invalid = []
            for s in raw_symbols:
                cursor.execute("SELECT COUNT(*) FROM DIM_SYMBOLS WHERE UPPER(TRIM(symbol)) = :sym", {'sym': s})
                in_dim = cursor.fetchone()[0] > 0
                cursor.execute("SELECT COUNT(*) FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV WHERE UPPER(TRIM(symbol)) = :sym", {'sym': s})
                in_raw = cursor.fetchone()[0] > 0
                if in_dim or in_raw:
                    valid.append(s)
                else:
                    invalid.append(s)
            print("Valid in DB count:", len(valid))
            print("Valid:", valid)
            print("Invalid in DB count:", len(invalid))
            print("Invalid:", invalid)
finally:
    conn.close()
