import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from routes.sector_rotation import _map_sector_codes, SECTOR_CODE_ALIASES

try:
    available = _map_sector_codes()
    print("Is AGRICULTURE in available?", 'AGRICULTURE' in available)
    print("Is AGRICULTURE in aliases?", 'AGRICULTURE' in SECTOR_CODE_ALIASES)
    if 'AGRICULTURE' in SECTOR_CODE_ALIASES:
        print("Aliases for AGRICULTURE:", SECTOR_CODE_ALIASES['AGRICULTURE'])
    print("Available count:", len(available))
except Exception as e:
    print("Error:", e)
