import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from routes.sector_rotation import _load_sector_wise_payload
import app as myapp

try:
    with myapp.app.app_context():
        payload = _load_sector_wise_payload('AGRICULTURE', page=1, page_size=15, sort='STOCK', dir='DESC', search_token='', force_refresh=True)
        print("Payload:", payload)
except Exception as e:
    print("Error:", e)
