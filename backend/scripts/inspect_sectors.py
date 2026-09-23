import os
import sys
from db import get_oracle_connection

def main():
    conn = get_oracle_connection()
    try:
        cursor = conn.cursor()
        print("--- Existing tables matching NIFTY_%_STAGING ---")
        cursor.execute("SELECT table_name FROM user_tables WHERE table_name LIKE '%STAGING%' ORDER BY table_name")
        for row in cursor:
            print(row[0])
            
        print("\n--- Sectors in nse_sector_master ---")
        cursor.execute("SELECT sector_code, sector_name, index_code, display_order FROM nse_sector_master ORDER BY display_order")
        for row in cursor:
            print(f"Code: {row[0]}, Name: {row[1]}, Index: {row[2]}, Order: {row[3]}")
            
    finally:
        conn.close()

if __name__ == '__main__':
    main()
