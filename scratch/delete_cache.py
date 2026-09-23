import os
from pathlib import Path

root = Path(r"c:\Users\admin\Documents\CvingTrade25X\CvingTrade25X")
cache_dir = root / 'backend' / 'cache'

for name in ['sector_tables_latest.json', 'sector_rotation_latest.json']:
    p = cache_dir / name
    if p.exists():
        print(f"Deleting {p}...")
        p.unlink()
        print("Deleted.")
    else:
        print(f"{p} does not exist.")
