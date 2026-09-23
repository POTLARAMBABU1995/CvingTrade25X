from db import get_oracle_connection

conn = get_oracle_connection()
cursor = conn.cursor()

cursor.execute("""
    SELECT COUNT(*) 
    FROM NSE_NIFTY_RESTAURANTS_STAGING r
    JOIN DIM_SYMBOLS ds ON REPLACE(REPLACE(REPLACE(REPLACE(UPPER(TRIM(ds.symbol)), 'NSE:', ''), 'BSE:', ''), '-EQ', ''), ' ', '') = r.SYMBOL
    JOIN FACT_OHLCV f ON ds.SYMBOL_ID = f.SYMBOL_ID
""")
print("Restaurants in FACT_OHLCV:", cursor.fetchone()[0])
conn.close()
