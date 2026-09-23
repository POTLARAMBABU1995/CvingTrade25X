from services.sector_rotation_service import _resolve_price_source, _render_sql

source = _resolve_price_source()
sql = _render_sql(source)
with open("scratch/sql_dump.sql", "w") as f:
    f.write(sql)
