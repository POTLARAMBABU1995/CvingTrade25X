import sys
import os

backend_path = os.path.join(os.getcwd(), 'backend')
sys.path.insert(0, backend_path)

from services.oracle_service import get_oracle_connection
from routes.sector_rotation import _load_strict_sector_symbols

print("Strict symbols for AGRICULTURE:")
print(_load_strict_sector_symbols('AGRICULTURE'))
