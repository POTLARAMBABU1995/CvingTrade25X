PROMPT Resolving conflicts for Chemicals & Specialty Products symbols
SET DEFINE OFF;

DECLARE
    l_count NUMBER := 0;
BEGIN
    SELECT COUNT(*) INTO l_count FROM user_tables WHERE table_name = 'NSE_SYMBOL_RECLASS_BACKUP';
    IF l_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE TABLE NSE_SYMBOL_RECLASS_BACKUP (
            SYMBOL VARCHAR2(64),
            OLD_TABLE VARCHAR2(128),
            BACKUP_DATE TIMESTAMP DEFAULT SYSTIMESTAMP
        )';
    END IF;
END;
/

-- Helper procedure to safely reclassify a symbol
DECLARE
    PROCEDURE reclassify_symbol(p_symbol VARCHAR2, p_table VARCHAR2) IS
        l_exists NUMBER := 0;
        l_table_exists NUMBER := 0;
    BEGIN
        SELECT COUNT(*) INTO l_table_exists FROM user_tables WHERE table_name = UPPER(p_table);
        IF l_table_exists > 0 THEN
            -- Check if symbol exists in the old table
            EXECUTE IMMEDIATE 'SELECT COUNT(*) FROM ' || p_table || ' WHERE UPPER(TRIM(SYMBOL)) = UPPER(TRIM(:sym))'
            INTO l_exists USING p_symbol;

            IF l_exists > 0 THEN
                -- Insert into backup
                INSERT INTO NSE_SYMBOL_RECLASS_BACKUP (SYMBOL, OLD_TABLE)
                VALUES (UPPER(TRIM(p_symbol)), UPPER(TRIM(p_table)));

                -- Delete from old table
                EXECUTE IMMEDIATE 'DELETE FROM ' || p_table || ' WHERE UPPER(TRIM(SYMBOL)) = UPPER(TRIM(:sym))'
                USING p_symbol;
                
                -- Delete from general symbol-sector mapping (so reference sync updates it cleanly)
                DELETE FROM NSE_SYMBOL_SECTOR_MAP WHERE UPPER(TRIM(SYMBOL)) = UPPER(TRIM(p_symbol));
            END IF;
        END IF;
    END;
BEGIN
    -- [1] Abrasives conflicts
    reclassify_symbol('CARBORUNIV', 'NSE_NIFTY_INDUSTRIAL_PRODUCTS_STAGING');
    reclassify_symbol('GRINDWELL', 'NSE_NIFTY_INDUSTRIAL_PRODUCTS_STAGING');
    reclassify_symbol('WENDT', 'NSE_NIFTY_INDUSTRIAL_PRODUCTS_STAGING');

    -- [2] Electrodes & Refractories conflicts
    reclassify_symbol('GRAPHITE', 'NSE_NIFTY_INDUSTRIAL_PRODUCTS_STAGING');
    reclassify_symbol('IFGLEXPOR', 'NSE_NIFTY_INDUSTRIAL_PRODUCTS_STAGING');
    reclassify_symbol('RHIM', 'NSE_NIFTY_INDUSTRIAL_PRODUCTS_STAGING');
    reclassify_symbol('VESUVIUS', 'NSE_NIFTY_INDUSTRIAL_PRODUCTS_STAGING');

    -- [3] Paints conflicts
    reclassify_symbol('ASIANPAINT', 'NSE_NIFTY_CONSUMER_DURABLES_STAGING');
    reclassify_symbol('BERGEPAINT', 'NSE_NIFTY_CONSUMER_DURABLES_STAGING');
    reclassify_symbol('INDIGOPNTS', 'NSE_NIFTY_CONSUMER_DURABLES_STAGING');
    reclassify_symbol('JSWDULUX', 'NSE_NIFTY_CONSUMER_DURABLES_STAGING');
    reclassify_symbol('KANSAINER', 'NSE_NIFTY_CONSUMER_DURABLES_STAGING');

    -- [4] Petrochemicals conflicts
    reclassify_symbol('CASTROLIND', 'NSE_NIFTY_OIL_AND_GAS_STAGING');
    reclassify_symbol('RAIN', 'NSE_NIFTY_CHEMICALS_STAGING');
    reclassify_symbol('SPLPETRO', 'NSE_NIFTY_CHEMICALS_STAGING');
    reclassify_symbol('STYRENIX', 'NSE_NIFTY_CHEMICALS_STAGING');

    -- [5] Plastic Products conflicts
    reclassify_symbol('FINPIPE', 'NSE_NIFTY_INDUSTRIAL_PRODUCTS_STAGING');
    reclassify_symbol('JISLJALEQS', 'NSE_NIFTY_AGRICULTURE_STAGING');
    reclassify_symbol('SHAILY', 'NSE_NIFTY_INDUSTRIAL_PRODUCTS_STAGING');
    reclassify_symbol('SUPREMEIND', 'NSE_NIFTY_INDUSTRIAL_PRODUCTS_STAGING');

    -- [6] Specialty Chemicals conflicts
    reclassify_symbol('APCOTEXIND', 'NSE_NIFTY_RUBBER_PRODUCTS_TYRES_STAGING');
    reclassify_symbol('EXCELINDUS', 'NSE_NIFTY_PESTICIDES_AGROCHEMICALS_STAGING');
    reclassify_symbol('TATVA', 'NSE_NIFTY_PHARMA_STAGING');

    -- [7] Explosives conflicts
    reclassify_symbol('SOLARINDS', 'NSE_NIFTY_CHEMICALS_STAGING');

    COMMIT;
END;
/
