from services.sector_rotation_service import fetch_sector_rotation_rows

rows = fetch_sector_rotation_rows(None)
if rows:
    print("Keys:", rows[0].keys())
    print("Example sector:", rows[0].get('sector') or rows[0].get('group'))
    
    fetched_sectors = {r.get('sector') or r.get('group') for r in rows}
    all_sectors = {'RESTAURANTS', 'HOSPITALITY_HOTELS_RESORTS', 'TOURISM_TRAVEL'}

    missing = all_sectors - fetched_sectors
    print("Missing:", missing)

    if not missing:
        print("THEY ARE THERE!")
