import os
from db import get_oracle_connection

conn = get_oracle_connection()
cursor = conn.cursor()

sql_path = r"C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X\backend\sql\create_sector_reference_sync_procedures.sql"
with open(sql_path, "r", encoding="utf-8") as f:
    content = f.read()

blocks = content.split("\n/\n")

for block in blocks:
    lines = [line for line in block.splitlines() if not line.strip().startswith("PROMPT") and not line.strip().startswith("SET ")]
    sql = "\n".join(lines).strip()
    if not sql:
        continue
    
    if sql.endswith("/"):
        sql = sql[:-1].strip()
        
    try:
        cursor.execute(sql)
        print("Executed block successfully")
    except Exception as e:
        print(f"Error executing block: {e}")
        # print("SQL was:", sql[:100], "...")

try:
    cursor.callproc("PR_SYNC_SECTOR_REFERENCE_DATA")
    conn.commit()
    print("Called PR_SYNC_SECTOR_REFERENCE_DATA successfully")
except Exception as e:
    print("Error calling PR_SYNC_SECTOR_REFERENCE_DATA:", e)

conn.close()
