from db import get_oracle_connection

conn = get_oracle_connection()
cursor = conn.cursor()

try:
    merge_sql = """
    MERGE INTO NSE_SECTOR_MASTER tgt
    USING (
      SELECT 'RESTAURANTS' AS SECTOR_CODE, 'Restaurants' AS SECTOR_NAME, 'NIFTY_RESTAURANTS' AS INDEX_CODE, 60 AS DISPLAY_ORDER FROM DUAL UNION ALL
      SELECT 'HOSPITALITY_HOTELS_RESORTS' AS SECTOR_CODE, 'Hospitality Hotels & Resorts' AS SECTOR_NAME, 'NIFTY_HOSPITALITY_HOTELS_RESORTS' AS INDEX_CODE, 60 AS DISPLAY_ORDER FROM DUAL UNION ALL
      SELECT 'TOURISM_TRAVEL' AS SECTOR_CODE, 'Tourism & Travel' AS SECTOR_NAME, 'NIFTY_TOURISM_TRAVEL' AS INDEX_CODE, 60 AS DISPLAY_ORDER FROM DUAL
    ) src
    ON (tgt.SECTOR_CODE = src.SECTOR_CODE)
    WHEN MATCHED THEN UPDATE SET
      tgt.SECTOR_NAME = src.SECTOR_NAME,
      tgt.INDEX_CODE = src.INDEX_CODE,
      tgt.DISPLAY_ORDER = src.DISPLAY_ORDER
    WHEN NOT MATCHED THEN INSERT (SECTOR_CODE, SECTOR_NAME, INDEX_CODE, DISPLAY_ORDER)
    VALUES (src.SECTOR_CODE, src.SECTOR_NAME, src.INDEX_CODE, src.DISPLAY_ORDER)
    """
    cursor.execute(merge_sql)
    conn.commit()
    print("Merged 3 sectors successfully.")
except Exception as e:
    print(f"Error: {e}")
    conn.rollback()
finally:
    conn.close()
