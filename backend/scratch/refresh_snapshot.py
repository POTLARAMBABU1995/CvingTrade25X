import os
os.environ['PYTHONPATH'] = '.'
from routes.sector_rotation import _discover_sector_staging_tables
import json

print("Refreshing sector staging tables snapshot...")
sectors = _discover_sector_staging_tables(force_refresh=True)
print(f"Total sectors discovered: {len(sectors)}")

found = [s['sectorCode'] for s in sectors if s['sectorCode'] in ('RESTAURANTS', 'HOSPITALITY_HOTELS_RESORTS', 'TOURISM_TRAVEL')]
print(f"New sectors found in snapshot: {found}")
