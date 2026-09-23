import sys
import os

backend_path = os.path.join(os.getcwd(), 'backend')
sys.path.insert(0, backend_path)

from app import app
from services.oracle_service import get_oracle_connection

with app.app_context():
    conn = get_oracle_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = 'NSE_NIFTY_AGRICULTURE_STAGING'")
            print("Table count:", cur.fetchone()[0])
            
            cur.execute("SELECT COUNT(*) FROM NSE_NIFTY_AGRICULTURE_STAGING")
            print("Row count:", cur.fetchone()[0])
            
            from routes.sector_rotation import _load_strict_sector_symbols
            print("Strict symbols:", _load_strict_sector_symbols('AGRICULTURE'))
            
            cur.execute("SELECT COUNT(*) FROM mv_nse_sector_ui_snapshot WHERE sector='AGRICULTURE'")
            print("MV count:", cur.fetchone()[0])
    except Exception as e:
        print("Error:", e)
