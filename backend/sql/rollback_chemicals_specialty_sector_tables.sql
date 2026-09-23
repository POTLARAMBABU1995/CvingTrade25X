PROMPT Rolling back Chemicals & Specialty Products sector staging tables
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
        'CHEMICALS', 'SPECIALTY_CHEMICALS', 'PETROCHEMICALS', 'PAINTS',
        'PLASTIC_PRODUCTS', 'EXPLOSIVES', 'ABRASIVES', 'ELECTRODES_REFRACTORIES'
    );
    DELETE FROM nse_sector_master WHERE sector_code IN (
        'CHEMICALS', 'SPECIALTY_CHEMICALS', 'PETROCHEMICALS', 'PAINTS',
        'PLASTIC_PRODUCTS', 'EXPLOSIVES', 'ABRASIVES', 'ELECTRODES_REFRACTORIES'
    );
    
    -- Restore old CHEM sector if needed (was display_order 3)
    INSERT INTO nse_sector_master(sector_code, sector_name, index_code, display_order)
    VALUES ('CHEM', 'Chemicals', 'NIFTY_CHEMICALS', 3);
    
    COMMIT;
END;
/

-- Drop the staging tables
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
    drop_staging('NSE_NIFTY_CHEMICALS_STAGING');
    drop_staging('NSE_NIFTY_SPECIALTY_CHEMICALS_STAGING');
    drop_staging('NSE_NIFTY_PETROCHEMICALS_STAGING');
    drop_staging('NSE_NIFTY_PAINTS_STAGING');
    drop_staging('NSE_NIFTY_PLASTIC_PRODUCTS_STAGING');
    drop_staging('NSE_NIFTY_EXPLOSIVES_STAGING');
    drop_staging('NSE_NIFTY_ABRASIVES_STAGING');
    drop_staging('NSE_NIFTY_ELECTRODES_REFRACTORIES_STAGING');
END;
/

COMMIT;
PROMPT Rollback complete.
