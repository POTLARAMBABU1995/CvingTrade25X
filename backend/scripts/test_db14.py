import sys
import os

backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, backend_path)

from flask import Flask
app = Flask(__name__)

from routes.sector_rotation import api_sector_stocks_sector_wise, _cache
from services.db_service import get_oracle_connection

with app.test_request_context('/?refresh=1'):
    try:
        conn = get_oracle_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM NSE_SECTOR_WISE_STOCKS_SNAPSHOT WHERE SECTOR = 'AGRICULTURE'")
        conn.commit()
        conn.close()
        _cache.clear()
        print("Cleared cache and snapshots")
        
        response = api_sector_stocks_sector_wise('AGRICULTURE')
        payload = response.get_json()
        
        print("Total count:", payload.get('totalCount'))
        print("Total pages:", payload.get('totalPages'))
        print("Stock count:", payload.get('stock_count'))
        for r in payload.get('rows', []):
            print("Stock:", r.get('stock'))
    except Exception as e:
        print("Error:", e)
