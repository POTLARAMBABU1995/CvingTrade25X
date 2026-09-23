from db import get_oracle_connection

conn = get_oracle_connection()
cursor = conn.cursor()
try:
    cursor.execute("SELECT COUNT(*) FROM VW_NSE_CANONICAL_SECTOR_STAGE WHERE sector_code IN ('RESTAURANTS', 'HOSPITALITY_HOTELS_RESORTS', 'TOURISM_TRAVEL')")
    print("ROWS IN VIEW:", cursor.fetchone()[0])
except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()
