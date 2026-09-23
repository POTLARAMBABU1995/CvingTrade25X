PROMPT Rolling back Capital Goods, Engineering & Industrials sector staging
SET DEFINE OFF;

-- Revert reclassified symbols from backup
DECLARE
    l_exists NUMBER := 0;
BEGIN
    SELECT COUNT(*) INTO l_exists FROM user_tables WHERE table_name = 'NSE_SYMBOL_RECLASS_BACKUP';
    IF l_exists > 0 THEN
        FOR r IN (SELECT DISTINCT symbol, old_table FROM NSE_SYMBOL_RECLASS_BACKUP) LOOP
            -- Check if old table exists
            SELECT COUNT(*) INTO l_exists FROM user_tables WHERE table_name = r.old_table;
            IF l_exists > 0 THEN
                -- Insert symbol back into its old staging table if not already present
                EXECUTE IMMEDIATE '
                    MERGE INTO ' || r.old_table || ' tgt
                    USING (SELECT :sym AS symbol FROM dual) src
                    ON (UPPER(TRIM(tgt.SYMBOL)) = src.symbol)
                    WHEN NOT MATCHED THEN INSERT (SYMBOL, SECTOR, ACTIVE_FLAG, CREATED_DATE)
                    VALUES (src.symbol, src.symbol, ''Y'', SYSDATE)
                ' USING r.symbol;
            END IF;
        END LOOP;
        
        -- Drop backup table
        EXECUTE IMMEDIATE 'DROP TABLE NSE_SYMBOL_RECLASS_BACKUP PURGE';
    END IF;
END;
/

-- Delete master registration and mappings for the new sectors
BEGIN
    DELETE FROM NSE_SYMBOL_SECTOR_MAP WHERE SECTOR_CODE IN (
        'ENGINEERING', 'ELEC_HEAVY_EQUIPMENT', 'INDUSTRIAL_MANUFACTURING', 
        'INDUSTRIAL_PRODUCTS', 'INDUSTRIAL_GASES_FUELS'
    );
    DELETE FROM nse_sector_master WHERE sector_code IN (
        'ENGINEERING', 'ELEC_HEAVY_EQUIPMENT', 'INDUSTRIAL_MANUFACTURING', 
        'INDUSTRIAL_PRODUCTS', 'INDUSTRIAL_GASES_FUELS'
    );
    COMMIT;
END;
/

-- Drop the staging tables (guarded/commented out for safety as per project standard, but available)
DECLARE
    PROCEDURE drop_staging(p_table VARCHAR2) IS
        l_exists NUMBER := 0;
    BEGIN
        SELECT COUNT(*) INTO l_exists FROM user_tables WHERE table_name = p_table;
        IF l_exists > 0 THEN
            EXECUTE IMMEDIATE 'DROP TABLE ' || p_table || ' PURGE';
        END IF;
    END;
BEGIN
    drop_staging('NSE_NIFTY_ENGINEERING_STAGING');
    drop_staging('NSE_NIFTY_ELEC_HEAVY_EQUIP_STAGING');
    drop_staging('NSE_NIFTY_INDUSTRIAL_MANUFACTURING_STAGING');
    drop_staging('NSE_NIFTY_INDUSTRIAL_PRODUCTS_STAGING');
    drop_staging('NSE_NIFTY_INDUSTRIAL_GASES_FUELS_STAGING');
    -- We do not drop CAPITAL_GOODS staging table as it existed before
END;
/

COMMIT;

PROMPT Rollback complete.
