import os
from dotenv import load_dotenv

root_dir = r"c:\Users\admin\Documents\CvingTrade25X\CvingTrade25X"
load_dotenv(os.path.join(root_dir, '.env'))

import sys
sys.path.append(os.path.join(root_dir, 'backend'))

# Mock background schedulers to prevent spawning infinite threads
import services.strategy_agent_runtime_service
services.strategy_agent_runtime_service.start_strategy_agent_scheduler = lambda *args, **kwargs: None

import services.marketdata_service
services.marketdata_service.start_fyers_data_cleanup_scheduler = lambda *args, **kwargs: None

try:
    import automation.nse_market_data_scheduler
    automation.nse_market_data_scheduler.start_nse_marketdata_auto_scheduler = lambda *args, **kwargs: None
except ImportError:
    pass

try:
    import automation.manual_sr_image_auto_ingest
    automation.manual_sr_image_auto_ingest.start_manual_sr_image_auto_ingest_scheduler = lambda *args, **kwargs: None
except ImportError:
    pass

import logging
logging.basicConfig(level=logging.INFO)

import importlib.machinery
import importlib.util

loader = importlib.machinery.SourceFileLoader('app_module', os.path.join(root_dir, 'backend', 'app.py'))
spec = importlib.util.spec_from_loader('app_module', loader)
app_module = importlib.util.module_from_spec(spec)
sys.modules['app_module'] = app_module
loader.exec_module(app_module)

app = app_module.create_app()
client = app.test_client()

print("--- Testing API client GET /api/sector/ALCOHOL_BREWERIES/stocks/sector-wise ---")
res = client.get('/api/sector/ALCOHOL_BREWERIES/stocks/sector-wise')
print("Status Code:", res.status_code)
data = res.get_json()
print("Total stocks returned:", len(data.get('rows', [])))
print("Response data keys:", data.keys())
