import sys
from pathlib import Path
sys.path.insert(0, str(Path('backend').resolve()))
from db import get_oracle_connection

conn = get_oracle_connection()
cursor = conn.cursor()
cursor.execute("BEGIN PR_SYNC_SECTOR_REFERENCE_DATA; END;")
conn.commit()
print("Synced successfully")
