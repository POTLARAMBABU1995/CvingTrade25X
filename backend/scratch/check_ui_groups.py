from services.sector_rotation_service import get_ui_sector_groups

groups = get_ui_sector_groups()
print("Total groups:", len(groups))

found = []
for sector_code, sector_name, source_codes in groups:
    if sector_code in ('RESTAURANTS', 'HOSPITALITY_HOTELS_RESORTS', 'TOURISM_TRAVEL'):
        found.append(sector_code)

print("Found target sectors:", found)
