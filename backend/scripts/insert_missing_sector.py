import sys
from pathlib import Path
sys.path.insert(0, str(Path('backend').resolve()))
from db import get_oracle_connection

conn = get_oracle_connection()
cursor = conn.cursor()

sectors = [
    ('ELEC_SERVICES_CONS_DURABLES', 'Electronics & Services Consumer Durables', 'NIFTY_ELECTRONICS_SERVICES_CONSUMER_DURABLES'),
    ('CONSUMER_ELECTRONICS', 'Consumer Electronics', 'NIFTY_CONSUMER_ELECTRONICS'),
    ('CONSUMER_SERVICES', 'Consumer Services', 'NIFTY_CONSUMER_SERVICES')
]

for sc, sn, ic in sectors:
    cursor.execute("""
        MERGE INTO nse_sector_master tgt 
        USING (SELECT :1 AS sector_code, :2 AS sector_name, :3 AS index_code FROM dual) src 
        ON (tgt.sector_code = src.sector_code) 
        WHEN NOT MATCHED THEN INSERT (sector_code, sector_name, index_code, display_order) 
        VALUES (src.sector_code, src.sector_name, src.index_code, 60)
        WHEN MATCHED THEN UPDATE SET tgt.sector_name = src.sector_name, tgt.index_code = src.index_code
    """, (sc, sn, ic))

conn.commit()
conn.close()
print("Done")
