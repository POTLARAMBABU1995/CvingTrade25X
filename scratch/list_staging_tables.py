import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from db import get_oracle_connection

conn = get_oracle_connection()
try:
    with conn.cursor() as cursor:
        cursor.execute("SELECT table_name FROM user_tables ORDER BY table_name")
        tables = [row[0] for row in cursor.fetchall()]
        print("Staging Tables:")
        for t in tables:
            if "STAGING" in t:
                print(t)
finally:
    conn.close()
