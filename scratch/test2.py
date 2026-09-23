import sys
import os

backend_path = os.path.join(os.getcwd(), 'backend')
sys.path.insert(0, backend_path)

from app import app
with app.app_context():
    from routes.sector_rotation import _load_strict_sector_symbols
    print("Strict symbols for AGRICULTURE:")
    print(_load_strict_sector_symbols('AGRICULTURE'))
