import re
import oracledb
from db import get_oracle_connection
from services.sector_rotation_service import _resolve_price_source, _render_sql

source = _resolve_price_source()
sql = _render_sql(source)

# Split at the last SELECT
parts = sql.split('SELECT\n    sector_code AS "sectorCode",')
base_sql = parts[0].strip()

if base_sql.endswith(','):
    base_sql = base_sql[:-1]

conn = get_oracle_connection()
cursor = conn.cursor()
cursor.setinputsizes(requested_trade_date=oracledb.DB_TYPE_DATE)

all_binds = {
    'requested_trade_date': None,
    'delivery_pct_floor': 0,
    'turnover_cr_floor': 0,
    'volume_floor': 0,
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

ctes_to_test = [
    'stock_anchor_metrics', 'breadth_by_sector', 'breadth_scored', 
    'delivery_recent', 'delivery_stats', 'delivery_scored', 'delivery_sector', 
    'sector_series', 'sector_series_feat', 'sector_series_feat2', 'sector_anchor', 
    'sector_factors', 'cross_stats', 'scored', 'rotations', 'final_rows'
]

print("Checking RESTAURANTS count in remaining CTEs:")
for cte in ctes_to_test:
    if cte in ('delivery_recent', 'delivery_stats', 'stock_anchor_metrics'):
        check_cte(cte, "WHERE sector_code = 'RESTAURANTS'")
    else:
        check_cte(cte, "WHERE sector_code = 'RESTAURANTS'")

conn.close()
