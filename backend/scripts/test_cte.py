import sys
from pathlib import Path
sys.path.insert(0, str(Path('backend').resolve()))
from db import get_oracle_connection

conn = get_oracle_connection()
cursor = conn.cursor()

sql = """
WITH anchor_date AS (
    SELECT MAX(TRADING_DATE) AS trade_date FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV
),
sector_master AS (
    SELECT sector_code, sector_name, index_code, display_order
    FROM (
        SELECT t.sector_code, t.sector_name, t.index_code, NVL(t.display_order, 9999) AS display_order, ROW_NUMBER() OVER (PARTITION BY t.sector_code ORDER BY NVL(t.display_order, 9999), t.sector_name) AS rn
        FROM nse_sector_master t
    ) WHERE rn = 1
),
symbol_universe AS (
    SELECT DISTINCT sm.sector_code, m.sector_name, m.index_code, m.display_order, UPPER(TRIM(sm.symbol)) AS symbol
    FROM nse_symbol_sector_map sm
    JOIN sector_master m ON m.sector_code = sm.sector_code
),
base_agg AS (
    SELECT u.sector_code, COUNT(DISTINCT u.symbol) AS total_symbols
    FROM symbol_universe u
    JOIN NSE_NIFTY500_DAILY_RAW_DATA_DEV ps ON ps.symbol = u.symbol AND ps.trading_date = (SELECT trade_date FROM anchor_date)
    GROUP BY u.sector_code
)
SELECT m.sector_code, m.sector_name, COALESCE(b.total_symbols, 0)
FROM sector_master m
LEFT JOIN base_agg b ON m.sector_code = b.sector_code
WHERE COALESCE(b.total_symbols, 0) > 0
ORDER BY m.sector_code
"""
cursor.execute(sql)
rows = cursor.fetchall()
print("ROWS RETURNED:", len(rows))
for row in rows:
    if 'CONSUMER' in row[1].upper() or 'ELEC' in row[1].upper() or 'DURABLES' in row[1].upper():
        print(row)
