import sys
from backend.db import get_oracle_connection
conn = get_oracle_connection()
cursor = conn.cursor()
cursor.execute("SELECT table_name FROM user_tables WHERE table_name LIKE 'NSE_NIFTY%STAGING'")
rows = cursor.fetchall()
print([r[0] for r in rows])
conn.close()
