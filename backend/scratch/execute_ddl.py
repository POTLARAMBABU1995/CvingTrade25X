from db import get_oracle_connection

conn = get_oracle_connection()
cursor = conn.cursor()

tables = [
    ("NSE_NIFTY_RESTAURANTS_STAGING", "PK_NIFTY_RESTAURANTS_STG"),
    ("NSE_NIFTY_HOSPITALITY_HOTELS_RESORTS_STAGING", "PK_NIFTY_HOSPITALITY_STG"),
    ("NSE_NIFTY_TOURISM_TRAVEL_STAGING", "PK_NIFTY_TOURISM_TRAVEL_STG")
]

for tbl, pk in tables:
    try:
        cursor.execute(f"SELECT COUNT(*) FROM user_tables WHERE table_name = '{tbl}'")
        if cursor.fetchone()[0] == 0:
            cursor.execute(f"""
                CREATE TABLE {tbl}
                (
                  SYMBOL VARCHAR2(64 BYTE) NOT NULL,
                  COMPANY_NAME VARCHAR2(255 BYTE),
                  INDUSTRY VARCHAR2(128 BYTE),
                  SECTOR VARCHAR2(128 BYTE),
                  ACTIVE_FLAG VARCHAR2(1 BYTE) DEFAULT 'Y',
                  CREATED_DATE TIMESTAMP (6) DEFAULT SYSTIMESTAMP,
                  UPDATED_DATE TIMESTAMP (6) DEFAULT SYSTIMESTAMP,
                  CONSTRAINT {pk} PRIMARY KEY (SYMBOL)
                )
            """)
            print(f"Created {tbl}")
        else:
            print(f"{tbl} already exists")
    except Exception as e:
        print(f"Error for {tbl}: {e}")

conn.close()
