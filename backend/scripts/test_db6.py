import sys
import os
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from routes.sector_rotation import _load_sector_wise_payload

app = create_app()

with app.app_context():
    try:
        payload = _load_sector_wise_payload(
            sector_code='AGRICULTURE',
            page=1,
            page_size=15,
            sort_key='STOCK',
            sort_dir='DESC',
            search_text='',
            force_refresh=True
        )
        print("Total Count:", payload.get('totalCount'))
        print("Rows:", len(payload.get('rows', [])))
    except Exception as e:
        print("Error:", e)
