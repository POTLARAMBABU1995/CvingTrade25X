import os
import csv

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
            sym_col_idx = 0  # fallback to first column
        
        for row in reader:
            if row:
                sym = row[sym_col_idx].strip()
                if sym:
                    symbols.append(sym)
    return symbols

print("Auto_Ancillaries_Over_500Cr.csv:")
auto_anc_syms = read_symbols(r"G:\SECTOR\AUTO ANCILLARIES\Auto_Ancillaries_Over_500Cr.csv")
print(auto_anc_syms)
print("Count:", len(auto_anc_syms))

print("\nautomobile_sector_web_verified_updated.csv:")
automobile_syms = read_symbols(r"G:\SECTOR\AUTOMOBILE\automobile_sector_web_verified_updated.csv")
print(automobile_syms)
print("Count:", len(automobile_syms))
