PROMPT Resolving conflicts for Hospitality Hotels & Resorts Sector symbols
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

DECLARE
    PROCEDURE reclassify_symbol(p_symbol VARCHAR2, p_table VARCHAR2) IS
        l_exists NUMBER := 0;
        l_table_exists NUMBER := 0;
    BEGIN
        SELECT COUNT(*) INTO l_table_exists FROM user_tables WHERE table_name = UPPER(p_table);
        IF l_table_exists > 0 THEN
            EXECUTE IMMEDIATE 'SELECT COUNT(*) FROM ' || p_table || ' WHERE UPPER(TRIM(SYMBOL)) = UPPER(TRIM(:sym))'
            INTO l_exists USING p_symbol;

            IF l_exists > 0 THEN
                INSERT INTO NSE_SYMBOL_RECLASS_BACKUP (SYMBOL, OLD_TABLE)
                VALUES (UPPER(TRIM(p_symbol)), UPPER(TRIM(p_table)));

                EXECUTE IMMEDIATE 'DELETE FROM ' || p_table || ' WHERE UPPER(TRIM(SYMBOL)) = UPPER(TRIM(:sym))'
                USING p_symbol;
                
                DELETE FROM NSE_SYMBOL_SECTOR_MAP WHERE UPPER(TRIM(SYMBOL)) = UPPER(TRIM(p_symbol));
            END IF;
        END IF;
    END;
BEGIN
    reclassify_symbol('CHALET', 'NSE_NIFTY_CONSUMER_SERVICES_STAGING');
    reclassify_symbol('EIHOTEL', 'NSE_NIFTY_CONSUMER_SERVICES_STAGING');
    reclassify_symbol('INDHOTEL', 'NSE_NIFTY_CONSUMER_SERVICES_STAGING');
    reclassify_symbol('ITCHOTELS', 'NSE_NIFTY_CONSUMER_SERVICES_STAGING');
    reclassify_symbol('LEMONTREE', 'NSE_NIFTY_CONSUMER_SERVICES_STAGING');
    reclassify_symbol('MHRIL', 'NSE_NIFTY_CONSUMER_SERVICES_STAGING');
    reclassify_symbol('VENTIVE', 'NSE_NIFTY_CONSUMER_SERVICES_STAGING');
END;
/

COMMIT;
EXIT;
