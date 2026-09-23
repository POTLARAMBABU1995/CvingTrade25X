from services.sector_rotation_service import get_ui_sector_groups

sectors = get_ui_sector_groups()
print("TOTAL UI SECTORS:", len(sectors))
