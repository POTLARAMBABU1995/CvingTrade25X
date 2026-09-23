import sys
import logging
from db import get_oracle_connection

logging.basicConfig(level=logging.INFO)

def run():
    conn = get_oracle_connection()
    try:
        with conn.cursor() as cursor:
            # Create table if not exists
            cursor.execute("""
            DECLARE
                v_count NUMBER;
            BEGIN
                SELECT COUNT(*) INTO v_count FROM user_tables WHERE table_name = 'NSE_SECTOR_ALIAS_MAP';
                IF v_count = 0 THEN
                    EXECUTE IMMEDIATE '
                    CREATE TABLE NSE_SECTOR_ALIAS_MAP (
                        alias_key VARCHAR2(100) PRIMARY KEY,
                        canonical_sector_id VARCHAR2(100),
                        canonical_sector_name VARCHAR2(255) NOT NULL,
                        active_flag NUMBER(1) DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )';
                END IF;
            END;
            """)
            
            # Insert data
            cursor.execute("""
            MERGE INTO NSE_SECTOR_ALIAS_MAP tgt
            USING (
                SELECT 'alcohol-breweries' AS alias_key, NULL AS canonical_sector_id, 'Alcohol Breweries' AS canonical_sector_name FROM dual UNION ALL
                SELECT 'alcohol breweries', NULL, 'Alcohol Breweries' FROM dual UNION ALL
                SELECT 'alcohol / breweries', NULL, 'Alcohol Breweries' FROM dual UNION ALL
                SELECT 'ALCOHOL BREWERIES', NULL, 'Alcohol Breweries' FROM dual UNION ALL
                SELECT 'ALCOHOL_BREWERIES', NULL, 'Alcohol Breweries' FROM dual UNION ALL
                SELECT 'restaurants-hospitality-travel', NULL, 'Restaurants, Hospitality & Travel' FROM dual UNION ALL
                SELECT 'restaurants hospitality travel', NULL, 'Restaurants, Hospitality & Travel' FROM dual
            ) src
            ON (tgt.alias_key = src.alias_key)
            WHEN NOT MATCHED THEN
                INSERT (alias_key, canonical_sector_id, canonical_sector_name)
                VALUES (src.alias_key, src.canonical_sector_id, src.canonical_sector_name)
            """)
            conn.commit()
            print("Successfully migrated NSE_SECTOR_ALIAS_MAP.")
    except Exception as e:
        print(f"Failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    run()
