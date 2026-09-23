import sys
import json
sys.path.append('C:\\Users\\admin\\Documents\\CvingTrade25X\\CvingTrade25X')

from backend.db_pool import pool
from backend.services.marketdata_service import (
    _stock_eod_sync_card_summary, 
    _stock_eod_pending_dev_summary, 
    _stock_eod_eligible_date_predicate, 
    _detect_date_column,
    get_auto_merge_availability
)

def run_debug():
    try:
        con = pool.acquire()
        cur = con.cursor()
        
        table = 'STOCK_EOD_HISTORY'
        col = _detect_date_column(cur, table)
        print(f"Detected column for {table}: {col}")
        
        sql = f"SELECT COUNT(*) AS rc, COUNT(DISTINCT symbol) AS sc, COUNT(DISTINCT CASE WHEN {_stock_eod_eligible_date_predicate(col)} THEN TRUNC({col}) END) AS tc FROM {table}"
        print(f"Running basic stats query: {sql}")
        cur.execute(sql)
        print(f"Basic stats result: {cur.fetchone()}")
        
        print("Running _stock_eod_sync_card_summary...")
        try:
            print(_stock_eod_sync_card_summary(cur))
        except Exception as e:
            print(f"Error in _stock_eod_sync_card_summary: {e}")
            
        print("Running _stock_eod_pending_dev_summary...")
        try:
            print(_stock_eod_pending_dev_summary(cur))
        except Exception as e:
            print(f"Error in _stock_eod_pending_dev_summary: {e}")
            
        print("Running get_auto_merge_availability...")
        try:
            avail = get_auto_merge_availability()
            print(avail)
        except Exception as e:
            print(f"Error in get_auto_merge_availability: {e}")

        con.close()
    except Exception as e:
        print(f"Fatal error: {e}")

run_debug()
