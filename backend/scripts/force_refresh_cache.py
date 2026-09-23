import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path('backend').resolve()))
from routes.sector_rotation import _load_sector_rotation_summary_from_sector_tables

print("Starting force refresh of sector summaries...")
start = time.time()
summary = _load_sector_rotation_summary_from_sector_tables(force_refresh=True)
print(f"Finished in {time.time() - start:.2f} seconds.")
print(f"Summary keys: {len(summary)}")
