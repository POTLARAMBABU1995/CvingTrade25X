PROMPT Resolving cross-sector symbol conflicts for Capital Goods, Engineering & Industrials
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

-- Procedure to back up and delete a symbol from a specific staging table
DECLARE
    PROCEDURE reclassify_symbol(p_symbol VARCHAR2, p_table VARCHAR2) IS
        l_exists NUMBER := 0;
    BEGIN
        -- Check if table exists
        SELECT COUNT(*) INTO l_exists FROM user_tables WHERE table_name = UPPER(p_table);
        IF l_exists > 0 THEN
            -- Check if symbol exists in table
            EXECUTE IMMEDIATE 'SELECT COUNT(*) FROM ' || p_table || ' WHERE UPPER(TRIM(SYMBOL)) = UPPER(TRIM(:sym))' INTO l_exists USING p_symbol;
            IF l_exists > 0 THEN
                -- Back up the reclassified symbol mapping
                INSERT INTO NSE_SYMBOL_RECLASS_BACKUP (SYMBOL, OLD_TABLE)
                VALUES (UPPER(TRIM(p_symbol)), UPPER(TRIM(p_table)));
                
                -- Delete from old staging table
                EXECUTE IMMEDIATE 'DELETE FROM ' || p_table || ' WHERE UPPER(TRIM(SYMBOL)) = UPPER(TRIM(:sym))' USING p_symbol;
                
                -- Delete from general symbol-sector mapping (so reference sync updates it cleanly)
                DELETE FROM NSE_SYMBOL_SECTOR_MAP WHERE UPPER(TRIM(SYMBOL)) = UPPER(TRIM(p_symbol));
            END IF;
        END IF;
    END;
BEGIN
    reclassify_symbol('HBLENGINE', 'NSE_NIFTY_AUTO_ANCILLARIES_STAGING');
    
    reclassify_symbol('UNIPARTS', 'NSE_NIFTY_AUTO_COMPONENTS_EQUIPMENTS_STAGING');
    reclassify_symbol('TIMKEN', 'NSE_NIFTY_AUTO_COMPONENTS_EQUIPMENTS_STAGING');
    reclassify_symbol('SKFINDIA', 'NSE_NIFTY_AUTO_COMPONENTS_EQUIPMENTS_STAGING');
    reclassify_symbol('NRBBEARING', 'NSE_NIFTY_AUTO_COMPONENTS_EQUIPMENTS_STAGING');
    
    reclassify_symbol('SKFINDIA', 'NSE_NIFTY_AUTO_STAGING');
    
    reclassify_symbol('REFEX', 'NSE_NIFTY_CHEMICALS_STAGING');
    reclassify_symbol('ELLEN', 'NSE_NIFTY_CHEMICALS_STAGING');
    reclassify_symbol('LINDEINDIA', 'NSE_NIFTY_CHEMICALS_STAGING');
    
    reclassify_symbol('ENGINERSIN', 'NSE_NIFTY_CONSTRUCTION_STAGING');
    reclassify_symbol('KPIL', 'NSE_NIFTY_CONSTRUCTION_STAGING');
    reclassify_symbol('LT', 'NSE_NIFTY_CONSTRUCTION_STAGING');
    reclassify_symbol('POWERMECH', 'NSE_NIFTY_CONSTRUCTION_STAGING');
    reclassify_symbol('TECHNOE', 'NSE_NIFTY_CONSTRUCTION_STAGING');
    reclassify_symbol('KEC', 'NSE_NIFTY_CONSTRUCTION_STAGING');
    
    reclassify_symbol('DIXON', 'NSE_NIFTY_CONSUMER_DURABLES_STAGING');
    reclassify_symbol('VGUARD', 'NSE_NIFTY_CONSUMER_DURABLES_STAGING');
    reclassify_symbol('PGEL', 'NSE_NIFTY_CONSUMER_DURABLES_STAGING');
    reclassify_symbol('SHAILY', 'NSE_NIFTY_CONSUMER_DURABLES_STAGING');
    reclassify_symbol('HAVELLS', 'NSE_NIFTY_CONSUMER_DURABLES_STAGING');
    
    reclassify_symbol('APLAPOLLO', 'NSE_NIFTY_METAL_STAGING');
    reclassify_symbol('WELCORP', 'NSE_NIFTY_METAL_STAGING');
    
    reclassify_symbol('PETRONET', 'NSE_NIFTY_OIL_AND_GAS_STAGING');
    
    reclassify_symbol('TEXRAIL', 'NSE_NIFTY_ROAD_RAIL_TRANSPORT_STAGING');
    reclassify_symbol('TITAGARH', 'NSE_NIFTY_ROAD_RAIL_TRANSPORT_STAGING');
    reclassify_symbol('JWL', 'NSE_NIFTY_ROAD_RAIL_TRANSPORT_STAGING');
    reclassify_symbol('BEML', 'NSE_NIFTY_ROAD_RAIL_TRANSPORT_STAGING');
    
    reclassify_symbol('INOXGREEN', 'NSE_NIFTY_SERVICES_STAGING');
    
    reclassify_symbol('WABAG', 'NSE_NIFTY_UTILITIES_STAGING');
END;
/

COMMIT;

PROMPT Cross-sector conflicts resolved and backed up.
