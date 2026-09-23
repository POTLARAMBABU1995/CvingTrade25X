import sys
import os
sys.path.insert(0, os.path.abspath('backend'))
from db import get_oracle_connection
conn = get_oracle_connection()
cursor = conn.cursor()
cursor.execute("SELECT trigger_name, trigger_body FROM user_triggers")
for row in cursor.fetchall():
    print(row[0])
