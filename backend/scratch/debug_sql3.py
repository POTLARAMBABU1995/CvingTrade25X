import re
import oracledb
from db import get_oracle_connection
from services.sector_rotation_service import _resolve_price_source, _render_sql

source = _resolve_price_source()
sql = _render_sql(source)

# Split at the last SELECT
parts = sql.split('SELECT\n    sector_code AS "sectorCode",')
base_sql = parts[0].strip()

# wait, base_sql might end with `final_rows AS (\n...\n)` so we shouldn't strip trailing comma if there is none
if base_sql.endswith(','):
    base_sql = base_sql[:-1]

conn = get_oracle_connection()
cursor = conn.cursor()
cursor.setinputsizes(requested_trade_date=oracledb.DB_TYPE_DATE)

all_binds = {
    'requested_trade_date': None,
    'delivery_pct_floor': 0,
    'delivery_qty_multiplier': 0,
    'trade_qty_multiplier': 0,
    'trade_count_multiplier': 0,
    'stock_confirmation_min_score': 0,
    'stock_confirmation_strong_ratio': 0,
    'stock_confirmation_moderate_ratio': 0,
}

def check_cte(cte, condition):
    test_sql = base_sql + f"\nSELECT COUNT(*) FROM {cte} " + condition
    
    placeholders = set([p.lower() for p in re.findall(r':([A-Za-z_]+)', test_sql)])
    binds = {k: all_binds[k] for k in placeholders if k in all_binds}
    
    try:
        cursor.execute(test_sql, binds)
        print(f"{cte}: {cursor.fetchone()[0]}")
    except Exception as e:
        print(f"{cte} failed: {e}")

print("Checking RESTAURANTS count in each CTE:")
for cte in ['symbol_universe', 'anchor_weights', 'price_ranked', 'price_calc6', 'sector_daily_returns', 'sector_stats', 'stock_confirmation', 'breadth_ratio', 'final_rotation']:
    if cte == 'price_ranked' or cte == 'price_calc6':
        check_cte(cte, "WHERE symbol IN (SELECT symbol FROM symbol_universe WHERE sector_code = 'RESTAURANTS')")
    elif cte == 'final_rotation':
        check_cte(cte, "")
    else:
        check_cte(cte, "WHERE sector_code = 'RESTAURANTS'")

conn.close()
