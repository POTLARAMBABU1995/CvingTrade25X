import sys
from pathlib import Path
sys.path.insert(0, str(Path('backend').resolve()))
from routes.sector_rotation import fetch_sector_rotation_rows

rows = fetch_sector_rotation_rows(trade_date=None, include_history=False)
sectors = [d.get('sectorName', d.get('sector_name', '')) for d in rows]
print([s for s in sectors if 'Consumer' in s or 'Electronics' in s])
print('Total sectors:', len(rows))
