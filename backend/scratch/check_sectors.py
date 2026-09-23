from db import get_oracle_connection

conn = get_oracle_connection()
cursor = conn.cursor()

try:
    cursor.execute("SELECT sector_code FROM nse_sector_master WHERE sector_code IN ('RESTAURANTS', 'HOSPITALITY_HOTELS_RESORTS', 'TOURISM_TRAVEL')")
    rows = cursor.fetchall()
    print("Sectors found:")
    for r in rows:
        print(r)
except Exception as e:
    print(f"Error querying table: {e}")
finally:
    conn.close()
