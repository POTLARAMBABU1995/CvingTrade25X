import sys
import os
import traceback

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from routes.sector_rotation import _load_sector_wise_payload
from services.sector_snapshot_service import get_latest_ltc_date_fast, write_sector_wise_snapshot

def test_load():
    latest_ltc_date = get_latest_ltc_date_fast()
    print(f"latest_ltc_date: {latest_ltc_date}")
    
    print("Loading sector PHARMA payload...")
    payload = _load_sector_wise_payload(
        sector_code="PHARMA",
        page=1,
        page_size=200,
        sort_key="STOCK",
        sort_dir="ASC",
        search_text="",
        force_refresh=True
    )
    rows = payload.get('rows', [])
    if rows:
        print(f"Number of rows: {len(rows)}")
        try:
            write_sector_wise_snapshot("PHARMA", latest_ltc_date, rows)
            print("Snapshot writing function completed.")
        except Exception as e:
            print("EXCEPTION raised during write_sector_wise_snapshot:")
            traceback.print_exc()

if __name__ == "__main__":
    test_load()
