from db import get_oracle_connection
from services.sector_rotation_service import _resolve_price_source, _render_sql

source = _resolve_price_source()
sql = _render_sql(source)

# Extract CTEs
import re
ctes = []
current_cte = ""
for line in sql.split('\n'):
    if line.startswith('WITH') or line == '':
        continue
    current_cte += line + '\n'

# we will just replace the final SELECT with SELECT * FROM ... WHERE sector_code = 'RESTAURANTS'
ctes_to_test = [
    'price_source', 'sector_master', 'symbol_universe', 'mcap_ranked', 'mcap_latest',
    'ffmc_ranked', 'ffmc_latest', 'anchor_weights', 'price_ranked', 'price_history',
    'price_calc1', 'price_calc2', 'price_calc3', 'price_calc4', 'price_calc5', 'price_calc6',
    'benchmark_daily_returns', 'sector_daily_returns', 'sector_stats', 'stock_confirmation', 'breadth_ratio'
]

conn = get_oracle_connection()
cursor = conn.cursor()

def test_cte(target_cte):
    parts = sql.split(f"SELECT * FROM final_rotation")
    base_sql = parts[0]
    # Remove the comma at the end of the last CTE if present
    base_sql = re.sub(r',\s*$', '', base_sql, flags=re.MULTILINE)
    
    # We want to stop at target_cte
    test_sql = base_sql + f"\nSELECT COUNT(*) FROM {target_cte}"
    if 'sector_code' in sql:
        try:
            # try to filter by RESTAURANTS
            test_sql += " WHERE sector_code = 'RESTAURANTS'"
            cursor.execute(test_sql, {'requested_trade_date': None})
            print(f"{target_cte} (RESTAURANTS):", cursor.fetchone()[0])
            return
        except Exception as e:
            pass
            
    # if no sector_code
    try:
        cursor.execute(base_sql + f"\nSELECT COUNT(*) FROM {target_cte}", {'requested_trade_date': None})
        print(f"{target_cte}:", cursor.fetchone()[0])
    except Exception as e:
        print(f"{target_cte} failed:", e)

for cte in ctes_to_test:
    test_cte(cte)

conn.close()
