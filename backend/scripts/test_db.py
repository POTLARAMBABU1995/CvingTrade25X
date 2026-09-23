import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from db import get_oracle_connection

conn = get_oracle_connection()
try:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = 'NSE_NIFTY_AGRICULTURE_STAGING'")
        print("Table count:", cur.fetchone()[0])
        
        cur.execute("SELECT COUNT(*) FROM NSE_NIFTY_AGRICULTURE_STAGING")
        print("Row count:", cur.fetchone()[0])
        
        cur.execute("SELECT COUNT(*) FROM mv_nse_sector_ui_snapshot_src WHERE sector='AGRICULTURE'")
        print("MVSrc count:", cur.fetchone()[0])
        
        cur.execute("SELECT COUNT(*) FROM mv_nse_sector_ui_snapshot WHERE sector='AGRICULTURE'")
        print("MV count:", cur.fetchone()[0])
except Exception as e:
    print("Error:", e)
