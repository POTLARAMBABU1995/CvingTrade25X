from db import get_oracle_connection

conn = get_oracle_connection()
cursor = conn.cursor()
cursor.execute("SELECT column_name FROM user_tab_columns WHERE table_name = 'FACT_OHLCV'")
print([r[0] for r in cursor.fetchall()])
conn.close()
