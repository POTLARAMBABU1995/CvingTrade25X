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

import importlib.machinery
import importlib.util

loader = importlib.machinery.SourceFileLoader('app_module', os.path.join(root_dir, 'backend', 'app.py'))
spec = importlib.util.spec_from_loader('app_module', loader)
app_module = importlib.util.module_from_spec(spec)
sys.modules['app_module'] = app_module
loader.exec_module(app_module)

app = app_module.create_app()
client = app.test_client()

print("--- Testing GET /api/sectors/breadth ---", flush=True)
res = client.get('/api/sectors/breadth')
print("Status Code:", res.status_code, flush=True)
try:
    data = res.get_json()
    if isinstance(data, list):
        print("Total sectors returned:", len(data), flush=True)
        for s in data:
            code = s.get('sectorCode')
            if code in ('ALCOHOL_BREWERIES', 'AUTO_ANCILLARIES', 'AUTO', 'FMCG'):
                print(f"  {code} | name={s.get('sectorName')} | symbols={s.get('totalSymbols')} | rsi50={s.get('rsi50Pct')}%", flush=True)
    else:
        print("Response is not a list:", data, flush=True)
except Exception as e:
    print("Error parsing JSON:", e, flush=True)

print("\n--- Testing GET /api/sector/ALCOHOL_BREWERIES/stocks/sector-wise ---", flush=True)
res = client.get('/api/sector/ALCOHOL_BREWERIES/stocks/sector-wise')
print("Status Code:", res.status_code, flush=True)
try:
    data = res.get_json()
    stocks = data.get('stocks', [])
    print("Total stocks returned:", len(stocks), flush=True)
    if stocks:
        print("First 3 stocks:", flush=True)
        for s in stocks[:3]:
            print(f"  {s.get('stock')} | close={s.get('close')} | trend={s.get('trend')} | score={s.get('score')}", flush=True)
except Exception as e:
    print("Error parsing JSON:", e, flush=True)

print("\n--- Testing GET /api/sector/AUTO_ANCILLARIES/stocks/sector-wise ---", flush=True)
res = client.get('/api/sector/AUTO_ANCILLARIES/stocks/sector-wise')
print("Status Code:", res.status_code, flush=True)
try:
    data = res.get_json()
    stocks = data.get('stocks', [])
    print("Total stocks returned:", len(stocks), flush=True)
    if stocks:
        print("First 3 stocks:", flush=True)
        for s in stocks[:3]:
            print(f"  {s.get('stock')} | close={s.get('close')} | trend={s.get('trend')} | score={s.get('score')}", flush=True)
except Exception as e:
    print("Error parsing JSON:", e, flush=True)
