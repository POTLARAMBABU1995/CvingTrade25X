import os
from dotenv import load_dotenv

root_dir = r"c:\Users\admin\Documents\CvingTrade25X\CvingTrade25X"
load_dotenv(os.path.join(root_dir, '.env'))

import sys
sys.path.append(os.path.join(root_dir, 'backend'))

import importlib.machinery
import importlib.util

# Load app.py directly
loader = importlib.machinery.SourceFileLoader('app_module', os.path.join(root_dir, 'backend', 'app.py'))
spec = importlib.util.spec_from_loader('app_module', loader)
app_module = importlib.util.module_from_spec(spec)
sys.modules['app_module'] = app_module
loader.exec_module(app_module)

app = app_module.create_app()
client = app.test_client()

print("--- Testing GET /api/sectors/breadth ---")
res = client.get('/api/sectors/breadth')
print("Status Code:", res.status_code)
try:
    data = res.get_json()
    if isinstance(data, list):
        print("Total sectors returned:", len(data))
        for s in data:
            code = s.get('sectorCode')
            if code in ('ALCOHOL_BREWERIES', 'AUTO_ANCILLARIES', 'AUTO', 'FMCG'):
                print(f"  {code} | name={s.get('sectorName')} | symbols={s.get('totalSymbols')} | rsi50={s.get('rsi50Pct')}%")
    else:
        print("Response is not a list:", data)
except Exception as e:
    print("Error parsing JSON:", e)

print("\n--- Testing GET /api/sector/ALCOHOL_BREWERIES/stocks/sector-wise ---")
res = client.get('/api/sector/ALCOHOL_BREWERIES/stocks/sector-wise')
print("Status Code:", res.status_code)
try:
    data = res.get_json()
    stocks = data.get('stocks', [])
    print("Total stocks returned:", len(stocks))
    if stocks:
        print("First 3 stocks:")
        for s in stocks[:3]:
            print(f"  {s.get('stock')} | close={s.get('close')} | trend={s.get('trend')} | score={s.get('score')}")
except Exception as e:
    print("Error parsing JSON:", e)

print("\n--- Testing GET /api/sector/AUTO_ANCILLARIES/stocks/sector-wise ---")
res = client.get('/api/sector/AUTO_ANCILLARIES/stocks/sector-wise')
print("Status Code:", res.status_code)
try:
    data = res.get_json()
    stocks = data.get('stocks', [])
    print("Total stocks returned:", len(stocks))
    if stocks:
        print("First 3 stocks:")
        for s in stocks[:3]:
            print(f"  {s.get('stock')} | close={s.get('close')} | trend={s.get('trend')} | score={s.get('score')}")
except Exception as e:
    print("Error parsing JSON:", e)
