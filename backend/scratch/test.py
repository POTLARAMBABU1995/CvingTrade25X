from db import get_oracle_connection
conn=get_oracle_connection()
cursor=conn.cursor()
cursor.execute('SELECT count(*) FROM mv_nse_sector_ui_snapshot WHERE sector = ''AGRICULTURE''')
print(cursor.fetchone())
