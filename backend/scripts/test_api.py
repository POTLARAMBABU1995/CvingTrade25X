import urllib.request
import json

def test_api():
    try:
        url = 'http://127.0.0.1:5055/api/sectors/breadth?cutoff_anchor=latest&lookback_days=1'
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            sectors = [d['sector_name'] for d in data]
            consumer_sectors = [s for s in sectors if 'Consumer' in s or 'CONS_DUR' in s]
            print("Breadth Consumer Sectors:", consumer_sectors)
            
        slugs = ['ELEC_SERVICES_CONS_DURABLES', 'CONSUMER_ELECTRONICS', 'CONSUMER_SERVICES', 'CONSUMER_DURABLES']
        for slug in slugs:
            url = f'http://127.0.0.1:5055/api/sector/{slug}/stocks/sector-wise'
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode('utf-8'))
                if isinstance(data, dict):
                    data = data.get('data', [])
                print(f"{slug} API response count:", len(data))
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_api()
