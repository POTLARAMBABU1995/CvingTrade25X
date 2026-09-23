from db import get_oracle_connection

conn = get_oracle_connection()
cursor = conn.cursor()
cursor.execute("SELECT MAX(TRADING_DATE) FROM FACT_OHLCV")
max_all = cursor.fetchone()[0]

cursor.execute("""
    SELECT MAX(f.TRADING_DATE)
    FROM NSE_NIFTY_RESTAURANTS_STAGING r
    JOIN DIM_SYMBOLS ds ON REPLACE(REPLACE(REPLACE(REPLACE(UPPER(TRIM(ds.symbol)), 'NSE:', ''), 'BSE:', ''), '-EQ', ''), ' ', '') = r.SYMBOL
    JOIN FACT_OHLCV f ON ds.SYMBOL_ID = f.SYMBOL_ID
""")
max_rest = cursor.fetchone()[0]

print("Max Date overall:", max_all)
print("Max Date for Restaurants:", max_rest)
conn.close()
