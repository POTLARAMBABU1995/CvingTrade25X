import re
from db import get_oracle_connection
from services.sector_rotation_service import _resolve_price_source, _render_sql

source = _resolve_price_source()
sql = _render_sql(source)

# find SELECT * FROM final_rotation and replace it
base_sql = sql.replace("SELECT * FROM final_rotation", "")
base_sql = re.sub(r',\s*$', '', base_sql) # remove trailing comma

conn = get_oracle_connection()
cursor = conn.cursor()

def check_cte(cte, condition):
    test_sql = base_sql + f"\nSELECT COUNT(*) FROM {cte} " + condition
    try:
        cursor.execute(test_sql, {'requested_trade_date': None})
        print(f"{cte}: {cursor.fetchone()[0]}")
    except Exception as e:
        print(f"{cte} failed: {e}")

print("Checking RESTAURANTS count in each CTE:")
for cte in ['symbol_universe', 'anchor_weights', 'price_ranked', 'price_calc6', 'sector_daily_returns', 'sector_stats', 'stock_confirmation', 'breadth_ratio', 'final_rotation']:
    if cte == 'price_ranked' or cte == 'price_calc6':
        check_cte(cte, "WHERE symbol IN (SELECT symbol FROM symbol_universe WHERE sector_code = 'RESTAURANTS')")
    elif cte == 'final_rotation':
        check_cte(cte, "WHERE sectorCode = 'RESTAURANTS'")
    else:
        check_cte(cte, "WHERE sector_code = 'RESTAURANTS'")

conn.close()
