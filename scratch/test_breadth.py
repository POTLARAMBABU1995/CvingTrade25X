import os
from dotenv import load_dotenv

root_dir = r"c:\Users\admin\Documents\CvingTrade25X\CvingTrade25X"
load_dotenv(os.path.join(root_dir, '.env'))

import sys
sys.path.append(os.path.join(root_dir, 'backend'))

# Mock background schedulers to prevent spawning infinite threads
import services.strategy_agent_runtime_service
services.strategy_agent_runtime_service.start_strategy_agent_scheduler = lambda *args, **kwargs: None

import services.marketdata_service
services.marketdata_service.start_fyers_data_cleanup_scheduler = lambda *args, **kwargs: None

try:
    import automation.nse_market_data_scheduler
    automation.nse_market_data_scheduler.start_nse_marketdata_auto_scheduler = lambda *args, **kwargs: None
except ImportError:
    pass

try:
    import automation.manual_sr_image_auto_ingest
    automation.manual_sr_image_auto_ingest.start_manual_sr_image_auto_ingest_scheduler = lambda *args, **kwargs: None
except ImportError:
    pass

import logging
logging.basicConfig(level=logging.INFO)

from services.sector_rotation_service import fetch_sector_rotation_rows

try:
    print("Fetching sector rotation rows...")
    rows = fetch_sector_rotation_rows(None, include_history=False)
    print("Success! Total rows fetched:", len(rows))
except Exception as e:
    print("Failed with exception:")
    import traceback
    traceback.print_exc()
