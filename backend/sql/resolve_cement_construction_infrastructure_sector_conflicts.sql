PROMPT Resolving conflicts for Cement, Construction and Infrastructure symbols
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
    -- Port and Port Services conflicts
    reclassify_symbol('ADANIPORTS', 'NSE_NIFTY_PORT_AND_PORT_SERVICES_STAGING');
    reclassify_symbol('JSWINFRA', 'NSE_NIFTY_PORT_AND_PORT_SERVICES_STAGING');

    -- Plastic Products conflicts
    reclassify_symbol('APOLLOPIPE', 'NSE_NIFTY_PLASTIC_PRODUCTS_STAGING');
    reclassify_symbol('ASTRAL', 'NSE_NIFTY_PLASTIC_PRODUCTS_STAGING');
    reclassify_symbol('FINPIPE', 'NSE_NIFTY_PLASTIC_PRODUCTS_STAGING');
    reclassify_symbol('PRINCEPIPE', 'NSE_NIFTY_PLASTIC_PRODUCTS_STAGING');
    reclassify_symbol('SUPREMEIND', 'NSE_NIFTY_PLASTIC_PRODUCTS_STAGING');

    -- Transport Infrastructure conflicts
    reclassify_symbol('ASHOKA', 'NSE_NIFTY_TRANSPORT_INFRASTRUCTURE_STAGING');
    reclassify_symbol('CEIGALL', 'NSE_NIFTY_TRANSPORT_INFRASTRUCTURE_STAGING');
    reclassify_symbol('DBL', 'NSE_NIFTY_TRANSPORT_INFRASTRUCTURE_STAGING');
    reclassify_symbol('GMRAIRPORT', 'NSE_NIFTY_TRANSPORT_INFRASTRUCTURE_STAGING');
    reclassify_symbol('GRINFRA', 'NSE_NIFTY_TRANSPORT_INFRASTRUCTURE_STAGING');
    reclassify_symbol('HGINFRA', 'NSE_NIFTY_TRANSPORT_INFRASTRUCTURE_STAGING');
    reclassify_symbol('IRB', 'NSE_NIFTY_TRANSPORT_INFRASTRUCTURE_STAGING');
    reclassify_symbol('IRCON', 'NSE_NIFTY_TRANSPORT_INFRASTRUCTURE_STAGING');
    reclassify_symbol('KNRCON', 'NSE_NIFTY_TRANSPORT_INFRASTRUCTURE_STAGING');
    reclassify_symbol('PNCINFRA', 'NSE_NIFTY_TRANSPORT_INFRASTRUCTURE_STAGING');
    reclassify_symbol('RITES', 'NSE_NIFTY_TRANSPORT_INFRASTRUCTURE_STAGING');
    reclassify_symbol('RVNL', 'NSE_NIFTY_TRANSPORT_INFRASTRUCTURE_STAGING');

    -- Consumer Durables conflicts
    reclassify_symbol('CENTURYPLY', 'NSE_NIFTY_CONSUMER_DURABLES_STAGING');
    reclassify_symbol('CERA', 'NSE_NIFTY_CONSUMER_DURABLES_STAGING');
    reclassify_symbol('KAJARIACER', 'NSE_NIFTY_CONSUMER_DURABLES_STAGING');

    -- Engineering / Capital Goods / Metal conflicts
    reclassify_symbol('ENGINERSIN', 'NSE_NIFTY_ENGINEERING_STAGING');
    reclassify_symbol('KEC', 'NSE_NIFTY_ENGINEERING_STAGING');
    reclassify_symbol('KPIL', 'NSE_NIFTY_ENGINEERING_STAGING');
    reclassify_symbol('LT', 'NSE_NIFTY_ENGINEERING_STAGING');
    reclassify_symbol('POWERMECH', 'NSE_NIFTY_ENGINEERING_STAGING');
    reclassify_symbol('TECHNOE', 'NSE_NIFTY_ENGINEERING_STAGING');

    COMMIT;
END;
/
