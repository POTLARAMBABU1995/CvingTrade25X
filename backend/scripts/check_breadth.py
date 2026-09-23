import urllib.request
import json
try:
    data = json.loads(urllib.request.urlopen('http://127.0.0.1:5055/api/sectors/breadth?cutoff_anchor=latest&lookback_days=1').read().decode('utf-8'))
    print(f"Number of items: {len(data)}")
    if data:
        print("Keys of first item:", data[0].keys())
        sectors = [d.get('sectorName') or d.get('sector_name') or d.get('sector') or d.get('SECTOR') for d in data]
        print([s for s in sectors if s and ('Consumer' in s or 'Durables' in s or 'Consumer' in str(s))])
except Exception as e:
    import traceback
    traceback.print_exc()
