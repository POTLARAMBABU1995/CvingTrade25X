import sys
from backend.db import get_oracle_connection

def run_script():
    conn = get_oracle_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT column_name FROM user_tab_columns WHERE table_name = 'NSE_SECTOR_MASTER'")
    rows = cursor.fetchall()
    print([r[0] for r in rows])
    conn.close()

if __name__ == '__main__':
    run_script()
