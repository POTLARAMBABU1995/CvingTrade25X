import os
import sys
import pandas as pd
from db import get_oracle_connection

def main():
    csv_path = r'G:\SECTOR\CHEMICALS METERIALS AND SPECIALITY PRODUCTS\chemicals_materials_specialty_products_combined_master_nse_validated.csv'
    df = pd.read_csv(csv_path)
    print("CSV loaded. Total rows:", len(df))
    
    conn = get_oracle_connection()
    try:
        cursor = conn.cursor()
        
        # Get all existing sector mappings
        cursor.execute("SELECT symbol, sector_code FROM NSE_SYMBOL_SECTOR_MAP")
        existing_mappings = {row[0].upper(): row[1] for row in cursor}
        
        # Check conflicts
        conflicts = []
        for idx, row in df.iterrows():
            sym = row['SYMBOL'].strip().upper()
            csv_sector = row['SECTOR'].strip()
            if sym in existing_mappings:
                existing_sector = existing_mappings[sym]
                conflicts.append((sym, csv_sector, existing_sector))
                
        print(f"Conflicts in NSE_SYMBOL_SECTOR_MAP: {len(conflicts)}")
        for c in conflicts[:20]:
            print(f"Symbol: {c[0]}, New Sector: {c[1]}, Existing Sector in map: {c[2]}")
            
    finally:
        conn.close()

if __name__ == '__main__':
    main()
