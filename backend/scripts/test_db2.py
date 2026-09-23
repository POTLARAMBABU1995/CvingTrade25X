import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from db import get_oracle_connection
from routes.sector_rotation import _load_strict_sector_symbols

try:
    print("Strict symbols:", _load_strict_sector_symbols('AGRICULTURE'))
except Exception as e:
    print("Error:", e)
