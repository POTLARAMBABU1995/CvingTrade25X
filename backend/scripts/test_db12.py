import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from routes.sector_rotation import _STRICT_SECTOR_TABLE_MAP

try:
    print("Is AGRICULTURE in _STRICT_SECTOR_TABLE_MAP?", 'AGRICULTURE' in _STRICT_SECTOR_TABLE_MAP)
except Exception as e:
    print("Error:", e)
