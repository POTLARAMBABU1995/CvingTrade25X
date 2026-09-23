from services.sector_rotation_service import fetch_sector_rotation_rows, get_ui_sector_groups

rows = fetch_sector_rotation_rows(None)
returned_codes = {r['sectorCode'] for r in rows}

groups = get_ui_sector_groups()
ui_codes = {g[0] for g in groups}

missing = ui_codes - returned_codes
print("UI expected count:", len(ui_codes))
print("Returned count:", len(returned_codes))
print("Missing from UI groups:", missing)
