PROMPT Rolling back Rubber Products Tyres sector staging
SET DEFINE OFF;

DECLARE
    l_count NUMBER := 0;
BEGIN
    SELECT COUNT(*)
      INTO l_count
      FROM user_tables
     WHERE table_name = 'NSE_NIFTY_RUBBER_PRODUCTS_TYRES_STAGING';

    IF l_count > 0 THEN
        -- Guarded drop: the project avoids destructive drops but this is the rollback script
        EXECUTE IMMEDIATE 'DROP TABLE NSE_NIFTY_RUBBER_PRODUCTS_TYRES_STAGING PURGE';
    END IF;
END;
/

DELETE FROM NSE_SYMBOL_SECTOR_MAP WHERE SECTOR_CODE = 'RUBBER_PRODUCTS_TYRES';
DELETE FROM NSE_SECTOR_MASTER WHERE SECTOR_CODE = 'RUBBER_PRODUCTS_TYRES';

COMMIT;

PROMPT Rubber Products Tyres rollback complete.
