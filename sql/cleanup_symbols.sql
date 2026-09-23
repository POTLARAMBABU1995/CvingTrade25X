-- Oracle SQL Migration & Cleanup Script for Sector Staging & Mapping Tables
-- Date: 2026-06-11
-- Author: Senior Full Stack AI Engineer

DECLARE
  TYPE t_symbol_map IS TABLE OF VARCHAR2(100) INDEX BY VARCHAR2(100);
  l_replacements t_symbol_map;
  l_old_symbol VARCHAR2(100);
  l_new_symbol VARCHAR2(100);
  l_backup_table VARCHAR2(128);
  l_before_cnt NUMBER;
  l_after_cnt NUMBER;
  l_has_new NUMBER;
  l_row_cnt NUMBER;
BEGIN
  -- Setup obsolete-to-active symbol mapping
  l_replacements('APCOTEX')     := 'APCOTEXIND';
  l_replacements('GRP')         := 'GRPLTD';
  l_replacements('TVSSRICHAKRA') := 'TVSSRICHAK';
  l_replacements('SHANTHIGEA')   := 'SHANTIGEAR';
  l_replacements('TATAMOTORS')   := 'TMPV';
  l_replacements('AMARAJABAT')   := 'ARE&M';
  l_replacements('LGBROSLTD')   := 'LGBBROSLTD';
  l_replacements('SHREEVASU')   := 'SVLL';

  -- 1. Discover all sector staging tables containing a SYMBOL column
  FOR r_tab IN (
    SELECT DISTINCT TABLE_NAME 
    FROM USER_TAB_COLUMNS 
    WHERE COLUMN_NAME = 'SYMBOL' 
      AND (TABLE_NAME LIKE '%STAGING%' OR TABLE_NAME = 'NSE_SYMBOL_SECTOR_MAP')
  ) LOOP
    
    -- 2. Create backup tables before modification
    l_backup_table := SUBSTR('BACKUP_' || r_tab.TABLE_NAME || '_20260611', 1, 128);
    BEGIN
      EXECUTE IMMEDIATE 'DROP TABLE ' || l_backup_table;
    EXCEPTION
      WHEN OTHERS THEN NULL;
    END;
    
    EXECUTE IMMEDIATE 'CREATE TABLE ' || l_backup_table || ' AS SELECT * FROM ' || r_tab.TABLE_NAME;
    EXECUTE IMMEDIATE 'SELECT COUNT(*) FROM ' || r_tab.TABLE_NAME INTO l_before_cnt;
    DBMS_OUTPUT.PUT_LINE('Table: ' || r_tab.TABLE_NAME || ' | Backup: ' || l_backup_table || ' | Count before: ' || l_before_cnt);

    -- 3. Apply old-to-new symbol replacements
    l_old_symbol := l_replacements.FIRST;
    WHILE l_old_symbol IS NOT NULL LOOP
      l_new_symbol := l_replacements(l_old_symbol);
      
      -- Check if old symbol exists in current table
      EXECUTE IMMEDIATE 'SELECT COUNT(*) FROM ' || r_tab.TABLE_NAME || ' WHERE SYMBOL = :1' 
        INTO l_row_cnt USING l_old_symbol;
        
      IF l_row_cnt > 0 THEN
        -- Check if new symbol already exists in current table
        EXECUTE IMMEDIATE 'SELECT COUNT(*) FROM ' || r_tab.TABLE_NAME || ' WHERE SYMBOL = :1' 
          INTO l_has_new USING l_new_symbol;
          
        IF l_has_new > 0 THEN
          -- Delete old symbol (avoid duplicate constraint violation)
          EXECUTE IMMEDIATE 'DELETE FROM ' || r_tab.TABLE_NAME || ' WHERE SYMBOL = :1' 
            USING l_old_symbol;
          DBMS_OUTPUT.PUT_LINE('  REPLACE_SKIP_DUPLICATE: Deleted ' || l_old_symbol || ' (already has ' || l_new_symbol || ')');
        ELSE
          -- Update old to new symbol
          EXECUTE IMMEDIATE 'UPDATE ' || r_tab.TABLE_NAME || ' SET SYMBOL = :1 WHERE SYMBOL = :2' 
            USING l_new_symbol, l_old_symbol;
          DBMS_OUTPUT.PUT_LINE('  REPLACE_ADD: Replaced ' || l_old_symbol || ' with ' || l_new_symbol);
        END IF;
      END IF;
      
      l_old_symbol := l_replacements.NEXT(l_old_symbol);
    END LOOP;

    -- 4. Delete invalid, BSE-only, and below 500 Cr market-cap symbols
    -- We delete symbols explicitly defined in KNOWN_INVALID_OR_BSE or those that are verified to be below 500 Cr
    -- or not present in NSE universe.
    EXECUTE IMMEDIATE 'DELETE FROM ' || r_tab.TABLE_NAME || ' WHERE SYMBOL IN (' ||
      '''AGRITECH'', ''AGROPHOS'', ''ARIES'', ''HARRMALAYA'', ''NAGAFERT'', ''NARMADA'', ' ||
      '''NATHBIOGEN'', ''SHANTI'', ''MANDEEP'', ''OMAXAUTO'', ''PRITIKAUTO'', ''ELGIRUBCO'', ' ||
      '''ETML'', ''GRCL'', ''ITTL'', ''LRRPL'', ''VIAZ'', ''DIANATEA'', ''GOODRICKE'', ' ||
      '''JKAGRI'', ''KOTHARIFER'', ''VIKASPROP'', ''SYMBOL'', ''SHREEVASU''' ||
      ')';
    l_row_cnt := SQL%ROWCOUNT;
    IF l_row_cnt > 0 THEN
      DBMS_OUTPUT.PUT_LINE('  DELETED obsolete/invalid/below-threshold symbols: ' || l_row_cnt);
    END IF;

    EXECUTE IMMEDIATE 'SELECT COUNT(*) FROM ' || r_tab.TABLE_NAME INTO l_after_cnt;
    DBMS_OUTPUT.PUT_LINE('  Count after cleanup: ' || l_after_cnt);
  END LOOP;

  -- 5. Sync sector reference tables and clear/refresh materialized view
  DBMS_OUTPUT.PUT_LINE('Syncing sector reference mapping...');
  PR_SYNC_SECTOR_REFERENCE_DATA;
  
  DBMS_OUTPUT.PUT_LINE('Refreshing Materialized View...');
  DBMS_MVIEW.REFRESH('MV_NSE_SECTOR_UI_SNAPSHOT', 'C');
  
  COMMIT;
  DBMS_OUTPUT.PUT_LINE('Migration completed successfully.');
EXCEPTION
  WHEN OTHERS THEN
    ROLLBACK;
    DBMS_OUTPUT.PUT_LINE('Error occurred: ' || SQLERRM);
    RAISE;
END;
/
