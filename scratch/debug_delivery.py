import datetime as dt
from backend.services import nse_delivery_service as nds

# force a print of the upsert exception
original_upsert = nds._upsert_records
def debug_upsert(records):
    print("Trying to upsert", len(records), "records")
    conn = nds.mcap.pool.acquire()
    try:
        cur = conn.cursor()
        for r in records[:5]: # just try first 5
            try:
                print("Trying record:", r['symbol'])
                update_sql = "UPDATE " + nds._TABLE_SQL + " SET prev_close = :prev_close WHERE trade_date = :trade_date AND symbol = :symbol AND source_name = :source_name"
                insert_sql = "INSERT INTO " + nds._TABLE_SQL + " (id, trade_date, symbol, source_name, fetch_status) VALUES (:id, :trade_date, :symbol, :source_name, :fetch_status)"
                
                # Use the actual queries
                cur.execute(update_sql, {'prev_close': r['prev_close'], 'trade_date': r['trade_date'], 'symbol': r['symbol'], 'source_name': r['source_name']})
                if not cur.rowcount:
                    # Let's see the actual insert sql error
                    full_insert_sql = """
    INSERT INTO CVING_NSE_DELIVERY_HIST (
      id, trade_date, symbol, source_name, series, security_name, prev_close, close_price,
      total_traded_qty, turnover_lacs, no_of_trades, delivery_qty, delivery_pct,
      response_payload, fetch_status, error_message, fetch_ts, created_by, updated_ts
    ) VALUES (
      :id, :trade_date, :symbol, :source_name, :series, :security_name, :prev_close, :close_price,
      :total_traded_qty, :turnover_lacs, :no_of_trades, :delivery_qty, :delivery_pct,
      TO_CLOB(:response_payload), :fetch_status, :error_message, :trade_date, :created_by, SYSTIMESTAMP
    )
  """
                    print("Executing full insert sql for", r['symbol'])
                    cur.execute(full_insert_sql, r)
            except Exception as e:
                print("EXCEPTION FOR", r['symbol'], "-->", e)
    finally:
        conn.close()

nds._upsert_records = debug_upsert

csv_path = nds._expected_csv_path(dt.date(2026, 6, 9))
print("Loading:", csv_path)
nds.load_delivery_csv(csv_path, dt.date(2026, 6, 9))
print("Done")
