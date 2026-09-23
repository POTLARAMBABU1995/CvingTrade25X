import urllib.request
import json
import sys

def check_url(url, description):
    print(f"\nQuerying: {description} ({url})")
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as res:
            data = json.loads(res.read().decode('utf-8'))
            print("Response loaded successfully.")
            return data
    except Exception as e:
        print(f"Error querying {description}: {e}")
        return None

# Warm cache / fetch breadth
breadth_data = check_url("http://127.0.0.1:5055/api/sectors/breadth?force_refresh=true", "Sectors Breadth")
if breadth_data:
    # Check if any new sectors exist in the response
    print("\nSectors found in API response:")
    found_sectors = []
    # Depending on response format, it might be a list or dict. Let's search keys or items
    if isinstance(breadth_data, list):
        for item in breadth_data:
            name = item.get('sectorName') or item.get('sector')
            if name:
                found_sectors.append(name)
    elif isinstance(breadth_data, dict):
        # Check standard breadth response formats
        rows = breadth_data.get('rows') or breadth_data.get('data') or []
        for item in rows:
            name = item.get('sectorName') or item.get('sector')
            if name:
                found_sectors.append(name)
        if not found_sectors:
            for k in breadth_data.keys():
                found_sectors.append(k)
                
    for s in sorted(found_sectors):
        if any(term in s for term in ["Engineering", "Electricals", "Industrial", "Capital Goods"]):
            print(f"-> {s}")

# Check sector-wise stocks for "engineering"
stocks_data = check_url("http://127.0.0.1:5055/api/sector/engineering/stocks/sector-wise", "Engineering Sector Wise Stocks")
if stocks_data:
    rows = stocks_data.get('rows') or stocks_data.get('data') or []
    print(f"Engineering stocks count: {len(rows)}")
    if rows:
        print("First stock sample:", rows[0])
