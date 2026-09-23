from db import get_oracle_connection

conn = get_oracle_connection()
cursor = conn.cursor()
try:
    cursor.execute("SELECT COUNT(*) FROM NSE_NIFTY_RESTAURANTS_STAGING")
    print("ROWS IN STAGING:", cursor.fetchone()[0])
except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()
