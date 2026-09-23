import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from routes.sector_rotation import _build_strict_symbol_fallback_rows

try:
    strict_symbols = ['BSHSL', 'GODREJAGRO', 'KSCL', 'VENKEYS', 'VSTTILLERS']
    rows = _build_strict_symbol_fallback_rows(strict_symbols, search_token='')
    print("Fallback rows count:", len(rows))
    print("Fallback rows:", rows)
except Exception as e:
    print("Error:", e)
