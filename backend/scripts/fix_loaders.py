import glob

sql_vars = '''
SQL_RAW_SYMBOLS = """
SELECT DISTINCT
    REPLACE(REPLACE(REPLACE(REPLACE(UPPER(TRIM(SYMBOL)), 'NSE:', ''), 'BSE:', ''), '-EQ', ''), ' ', '') AS SYMBOL
FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV
WHERE SYMBOL IS NOT NULL
"""

SQL_DISCOVER_OTHER_SECTOR_TABLES = r"""
SELECT DISTINCT utc.table_name
FROM user_tab_columns utc
WHERE utc.column_name = 'SYMBOL'
  AND utc.table_name LIKE 'NSE\_NIFTY\_%\_STAGING' ESCAPE '\\'
  AND utc.table_name NOT IN (:staging_table)
ORDER BY utc.table_name
"""
'''

for f in glob.glob('backend/scripts/load_*_sector_file.py'):
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
    if 'SQL_RAW_SYMBOLS' not in content:
        content = content.replace('DISPLAY_ORDER = 50', 'DISPLAY_ORDER = 50\n' + sql_vars)
        with open(f, 'w', encoding='utf-8') as file:
            file.write(content)
