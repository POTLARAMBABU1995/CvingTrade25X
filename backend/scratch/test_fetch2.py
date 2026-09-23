from services.sector_rotation_service import get_ui_sector_groups, _query_rows, _get_source_config

groups = get_ui_sector_groups()
for sector_code, sector_name, source_codes in groups:
    source = _get_source_config(sector_code)
    try:
        raw_rows = _query_rows(None, source)
    except Exception as e:
        print(f"FAILED on {sector_code}: {source['table']} -> {e}")
        break
