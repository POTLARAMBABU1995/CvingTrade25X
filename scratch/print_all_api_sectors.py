import urllib.request
import json

url = "http://127.0.0.1:5055/api/sectors/breadth?force_refresh=true"
try:
    with urllib.request.urlopen(url) as res:
        data = json.loads(res.read().decode('utf-8'))
        print("Sectors in response:")
        if isinstance(data, list):
            for item in data:
                print(item.get('sectorName') or item.get('sector'))
        elif isinstance(data, dict):
            rows = data.get('rows') or data.get('data') or []
            for item in rows:
                print(item.get('sectorName') or item.get('sector'))
except Exception as e:
    print("Error:", e)
