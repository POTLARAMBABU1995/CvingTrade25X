from db import get_oracle_connection
import oracledb

conn = get_oracle_connection()
cursor = conn.cursor()
try:
    cursor.setinputsizes(requested_trade_date=oracledb.DB_TYPE_DATE)
    cursor.execute("""
        SELECT * FROM DUAL WHERE :requested_trade_date IS NULL
    """, {'requested_trade_date': None})
    print(cursor.fetchall())
except Exception as e:
    print("Error:", e)
finally:
    conn.close()
