import csv
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from db import get_oracle_connection

csv_path = Path(r"G:\SECTOR\CAPITAL GOODS, ENGINEERING & INDUSTRIALS\Capital Goods, Engineering & Industrials.csv")

def normalize_symbol(value: str) -> str:
    token = str(value or '').strip().upper()
    if token.startswith('NSE:'):
        token = token[4:]
    if token.startswith('BSE:'):
        token = token[4:]
    if token.endswith('-EQ'):
        token = token[:-3]
    return token.replace(' ', '').strip()

if not csv_path.exists():
    print("CSV does not exist!")
    sys.exit(1)

with csv_path.open('r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    csv_rows = list(reader)

csv_symbols = {}
for r in csv_rows:
    sym = normalize_symbol(r.get('SYMBOL', ''))
    sec = r.get('SECTOR', '').strip()
    if sym:
        if sym in csv_symbols:
            print(f"Duplicate symbol in CSV: {sym} in sector {sec} and {csv_symbols[sym]}")
        csv_symbols[sym] = sec

print("Total unique symbols in CSV:", len(csv_symbols))

# Now query other staging tables for conflicts
conn = get_oracle_connection()
try:
    with conn.cursor() as cursor:
        cursor.execute("SELECT table_name FROM user_tables WHERE table_name LIKE 'NSE_NIFTY_%_STAGING' ORDER BY table_name")
        tables = [row[0] for row in cursor.fetchall()]
        print("Checking conflicts in other tables...")
        for t in tables:
            # We skip our 6 tables if they exist
            skip_tables = [
                'NSE_NIFTY_ENGINEERING_STAGING',
                'NSE_NIFTY_ELECTRICALS_HEAVY_ELECTRICAL_EQUIPMENT_STAGING',
                'NSE_NIFTY_INDUSTRIAL_MANUFACTURING_STAGING',
                'NSE_NIFTY_INDUSTRIAL_PRODUCTS_STAGING',
                'NSE_NIFTY_INDUSTRIAL_GASES_FUELS_STAGING',
                'NSE_NIFTY_CAPITAL_GOODS_STAGING'
            ]
            if t in skip_tables:
                continue
            cursor.execute(f"SELECT DISTINCT symbol FROM {t} WHERE symbol IS NOT NULL")
            t_syms = [row[0] for row in cursor.fetchall()]
            overlap = set(csv_symbols.keys()).intersection(t_syms)
            if overlap:
                print(f"Overlap in table {t}: {overlap}")
finally:
    conn.close()
