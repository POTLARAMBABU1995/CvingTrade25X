import sys
import importlib.util
from pathlib import Path

_BACKEND_ROOT = Path(r"c:\Users\admin\Documents\CvingTrade25X\CvingTrade25X\backend")
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

# Load backend/app.py module directly to bypass package name shadowing
spec = importlib.util.spec_from_file_location('backend_app_module', str(_BACKEND_ROOT / 'app.py'))
app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_module)

# Create the flask app instance using the factory function
flask_app = app_module.create_app(
    enable_background_jobs=False,
    enable_warmup=False,
    enable_nse_marketdata_automation=False,
    enable_manual_sr_image_auto_ingest=False,
    enable_marketdata_auto_merge=False
)

client = flask_app.test_client()

print("[1] Requesting sectors without refresh...")
resp1 = client.get('/api/sector-rotation/sectors')
print("Status:", resp1.status_code)
data1 = resp1.get_json()
print("Sectors count:", data1.get('totalSectors'))
has_test = any(s['sectorCode'] == 'TEST_SECTOR' for s in data1.get('sectors', []))
print("Contains TEST_SECTOR:", has_test)

print("\n[2] Requesting sectors with refresh=1...")
resp2 = client.get('/api/sector-rotation/sectors?refresh=1')
print("Status:", resp2.status_code)
data2 = resp2.get_json()
print("Sectors count:", data2.get('totalSectors'))
has_test_refresh = any(s['sectorCode'] == 'TEST_SECTOR' for s in data2.get('sectors', []))
print("Contains TEST_SECTOR:", has_test_refresh)

print("\n[3] Requesting sectors debug endpoint...")
resp3 = client.get('/api/sector-rotation/sectors/debug')
print("Status:", resp3.status_code)
print("Debug response:", resp3.get_json())

# Cleanup: drop test table
from db import get_oracle_connection
conn = get_oracle_connection()
cur = conn.cursor()
try:
    cur.execute("DROP TABLE NSE_NIFTY_TEST_SECTOR_STAGING")
    conn.commit()
    print("\n[4] Cleaned up: Dropped NSE_NIFTY_TEST_SECTOR_STAGING")
except Exception as e:
    print("\n[4] Cleanup failed:", e)
finally:
    conn.close()
