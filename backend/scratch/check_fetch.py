from services.sector_rotation_service import fetch_sector_rotation_rows

rows = fetch_sector_rotation_rows(None)
sector_codes = [r['sectorCode'] for r in rows]
print("Returned sector count:", len(sector_codes))

missing = {'RESTAURANTS', 'HOSPITALITY_HOTELS_RESORTS', 'TOURISM_TRAVEL'} - set(sector_codes)
print("Missing in fetch:", missing)
