from services.sector_rotation_service import _query_rows, _resolve_price_source, get_ui_sector_groups

source = _resolve_price_source()
rows = _query_rows(None, source)

sector_codes = [r['sectorCode'] for r in rows]
print("Returned sector count:", len(sector_codes))

missing = {'RESTAURANTS', 'HOSPITALITY_HOTELS_RESORTS', 'TOURISM_TRAVEL'} - set(sector_codes)
print("Missing:", missing)

print("Let's look at get_ui_sector_groups:")
groups = get_ui_sector_groups()
print("Groups count:", len(groups))

