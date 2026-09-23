from db import get_oracle_connection

conn = get_oracle_connection()
cursor = conn.cursor()
cursor.execute("SELECT SECTOR_CODE, COUNT(*) FROM NSE_SYMBOL_SECTOR_MAP GROUP BY SECTOR_CODE")
rows = cursor.fetchall()
for row in rows:
    if row[0] in ('RESTAURANTS', 'HOSPITALITY_HOTELS_RESORTS', 'TOURISM_TRAVEL'):
        print(row)
conn.close()
