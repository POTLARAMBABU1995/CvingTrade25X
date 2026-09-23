from services.sector_rotation_service import fetch_sector_rotation_rows
try:
    print("Fetching...")
    rows = fetch_sector_rotation_rows(None)
    print("Success, len:", len(rows))
except Exception as e:
    import traceback
    traceback.print_exc()
