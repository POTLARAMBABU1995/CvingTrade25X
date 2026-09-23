from pathlib import Path

file_path = Path(r"c:\\Users\\admin\\Documents\\CvingTrade25X\\CvingTrade25X\\backend\\routes\\sector_rotation.py")
content = file_path.read_text(encoding='utf-8')

target = """def _map_sector_codes() -> set[str]:
    cached = _cache.get(_MAP_SECTOR_CACHE_KEY)
    if isinstance(cached, set):
        return cached
    try:
        rows = _query_rows('SELECT DISTINCT sector AS "sectorCode" FROM mv_nse_sector_ui_snapshot')
        codes = {str(row.get('sectorCode') or '').upper() for row in rows if row.get('sectorCode')}
    except Exception:
        codes = set()
    _cache.set(_MAP_SECTOR_CACHE_KEY, codes)
    return codes"""

replacement = """def _map_sector_codes() -> set[str]:
    cached = _cache.get(_MAP_SECTOR_CACHE_KEY)
    if isinstance(cached, set):
        return cached
    try:
        rows = _query_rows('SELECT DISTINCT sector AS "sectorCode" FROM mv_nse_sector_ui_snapshot')
        codes = {str(row.get('sectorCode') or '').upper() for row in rows if row.get('sectorCode')}
    except Exception:
        codes = set()
    try:
        for item in _discover_sector_staging_tables():
            table_sector_code = str(item.get('sectorCode') or '').strip().upper()
            if table_sector_code:
                codes.add(table_sector_code)
    except Exception:
        pass
    _cache.set(_MAP_SECTOR_CACHE_KEY, codes)
    return codes"""

normalized_content = content.replace('\r\n', '\n')
normalized_target = target.replace('\r\n', '\n')
normalized_replacement = replacement.replace('\r\n', '\n')

if normalized_target in normalized_content:
    print("Target found. Replacing...")
    new_content = normalized_content.replace(normalized_target, normalized_replacement)
    new_content = new_content.replace('\n', '\r\n')
    file_path.write_text(new_content, encoding='utf-8')
    print("Success!")
else:
    print("Error: Target not found in file content!")
