import os
import sys
import csv
from datetime import datetime

# Setup path for backend imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import db
from services.symbol_validation_service import symbol_validation_service, SYMBOL_REPLACEMENT_MAP, KNOWN_INVALID_OR_BSE

def main():
    print("Initializing Symbol Validation Service...")
    symbol_validation_service.initialize_if_needed()
    
    conn = db.get_oracle_connection()
    cur = conn.cursor()
    
    # 1. Discover all sector staging tables containing a SYMBOL column
    cur.execute("SELECT TABLE_NAME FROM USER_TAB_COLUMNS WHERE COLUMN_NAME = 'SYMBOL' AND TABLE_NAME LIKE '%STAGING%'")
    staging_tables = [row[0] for row in cur.fetchall()]
    print(f"Discovered {len(staging_tables)} staging tables.")

    backup_date = datetime.now().strftime("%Y%m%d")
    report_rows = []
    
    # We will backup and clean nse_symbol_sector_map too
    staging_tables.append('NSE_SYMBOL_SECTOR_MAP')
    
    for table in staging_tables:
        print(f"\nProcessing table: {table}")
        
        # Determine table type and columns
        cur.execute(f"SELECT COLUMN_NAME FROM USER_TAB_COLUMNS WHERE TABLE_NAME = '{table}'")
        cols = [r[0] for r in cur.fetchall()]
        
        # 2. Create backup table
        backup_table = f"BACKUP_{table}_{backup_date}"
        if len(backup_table) > 30:
            # Oracle 12c/19c table name limit is 128, but let's be safe
            backup_table = backup_table[:128]
            
        try:
            cur.execute(f"DROP TABLE {backup_table}")
        except Exception:
            pass
            
        print(f"Creating backup table: {backup_table}")
        cur.execute(f"CREATE TABLE {backup_table} AS SELECT * FROM {table}")
        
        # Before count
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        before_count = cur.fetchone()[0]
        print(f"Before count: {before_count}")
        
        # 3. Perform old-to-new symbol replacements
        replaced_count = 0
        duplicate_skipped_count = 0
        
        for old_sym, new_sym in SYMBOL_REPLACEMENT_MAP.items():
            # Check if old symbol exists
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE SYMBOL = :old_sym", {'old_sym': old_sym})
            old_exists = cur.fetchone()[0] > 0
            
            if old_exists:
                # Check if new symbol already exists
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE SYMBOL = :new_sym", {'new_sym': new_sym})
                new_exists = cur.fetchone()[0] > 0
                
                if new_exists:
                    # Duplicate conflict: delete the old one
                    cur.execute(f"DELETE FROM {table} WHERE SYMBOL = :old_sym", {'old_sym': old_sym})
                    duplicate_skipped_count += cur.rowcount
                    print(f"Duplicate replacement: Deleted {old_sym} (already has {new_sym})")
                    report_rows.append({
                        'TABLE_NAME': table,
                        'OLD_SYMBOL': old_sym,
                        'NEW_SYMBOL': new_sym,
                        'ACTION': 'REPLACE_SKIP_DUPLICATE',
                        'REASON': 'New symbol already present',
                        'BEFORE_COUNT': before_count,
                        'AFTER_COUNT': before_count - duplicate_skipped_count
                    })
                else:
                    # Update old to new
                    cur.execute(f"UPDATE {table} SET SYMBOL = :new_sym WHERE SYMBOL = :old_sym", {'new_sym': new_sym, 'old_sym': old_sym})
                    replaced_count += cur.rowcount
                    print(f"Replaced {old_sym} with {new_sym}")
                    report_rows.append({
                        'TABLE_NAME': table,
                        'OLD_SYMBOL': old_sym,
                        'NEW_SYMBOL': new_sym,
                        'ACTION': 'REPLACE_ADD',
                        'REASON': 'Updated obsolete symbol',
                        'BEFORE_COUNT': before_count,
                        'AFTER_COUNT': before_count
                    })

        # 4. Remove invalid, BSE-only, no-trading, and below 500 Cr market-cap symbols
        cur.execute(f"SELECT DISTINCT SYMBOL FROM {table}")
        symbols_in_table = [r[0] for r in cur.fetchall() if r[0]]
        
        deleted_invalid = 0
        deleted_bse = 0
        deleted_low_mcap = 0
        
        for sym in symbols_in_table:
            classification = symbol_validation_service.classify_symbol(sym)
            if classification == "INVALID" or sym in KNOWN_INVALID_OR_BSE:
                cur.execute(f"DELETE FROM {table} WHERE SYMBOL = :sym", {'sym': sym})
                deleted_invalid += cur.rowcount
                print(f"Deleted INVALID symbol: {sym}")
                report_rows.append({
                    'TABLE_NAME': table,
                    'OLD_SYMBOL': sym,
                    'NEW_SYMBOL': '',
                    'ACTION': 'REMOVE_INVALID',
                    'REASON': 'Invalid symbol name',
                    'BEFORE_COUNT': before_count,
                    'AFTER_COUNT': before_count - deleted_invalid
                })
            elif classification == "BSE_ONLY":
                cur.execute(f"DELETE FROM {table} WHERE SYMBOL = :sym", {'sym': sym})
                deleted_bse += cur.rowcount
                print(f"Deleted BSE_ONLY symbol: {sym}")
                report_rows.append({
                    'TABLE_NAME': table,
                    'OLD_SYMBOL': sym,
                    'NEW_SYMBOL': '',
                    'ACTION': 'REMOVE_BSE_ONLY',
                    'REASON': 'BSE-only symbol',
                    'BEFORE_COUNT': before_count,
                    'AFTER_COUNT': before_count - deleted_bse
                })
            elif classification == "BELOW_500CR":
                cur.execute(f"DELETE FROM {table} WHERE SYMBOL = :sym", {'sym': sym})
                deleted_low_mcap += cur.rowcount
                print(f"Deleted BELOW_500CR symbol: {sym}")
                report_rows.append({
                    'TABLE_NAME': table,
                    'OLD_SYMBOL': sym,
                    'NEW_SYMBOL': '',
                    'ACTION': 'REMOVE_BELOW_500CR',
                    'REASON': 'Market cap below ₹500 Cr',
                    'BEFORE_COUNT': before_count,
                    'AFTER_COUNT': before_count - deleted_low_mcap
                })
                
        # After count
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        after_count = cur.fetchone()[0]
        print(f"After count: {after_count}")
        
    print("\nApplying database sync and reference updates...")
    # 5. Run reference sync PR_SYNC_SECTOR_REFERENCE_DATA
    try:
        cur.execute("BEGIN PR_SYNC_SECTOR_REFERENCE_DATA; END;")
        print("PR_SYNC_SECTOR_REFERENCE_DATA executed successfully.")
    except Exception as e:
        print(f"Error during PR_SYNC_SECTOR_REFERENCE_DATA: {e}")

    # 6. Refresh Materialized Views
    try:
        cur.execute("BEGIN DBMS_MVIEW.REFRESH('MV_NSE_SECTOR_UI_SNAPSHOT', 'C'); END;")
        print("MV_NSE_SECTOR_UI_SNAPSHOT refreshed successfully.")
    except Exception as e:
        print(f"Error during MV refresh: {e}")
        
    conn.commit()
    conn.close()
    
    # Save Cleanup Report CSV
    report_file = os.path.join(os.path.dirname(__file__), '..', 'cleanup_report.csv')
    with open(report_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['TABLE_NAME', 'OLD_SYMBOL', 'NEW_SYMBOL', 'ACTION', 'REASON', 'BEFORE_COUNT', 'AFTER_COUNT'])
        writer.writeheader()
        writer.writerows(report_rows)
    print(f"\nCleanup report saved to: {report_file}")

if __name__ == '__main__':
    main()
