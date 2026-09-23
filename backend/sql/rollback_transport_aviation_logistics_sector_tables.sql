PROMPT Rolling back Transport, Aviation & Logistics sector staging
SET DEFINE OFF;

DECLARE
    l_count NUMBER := 0;
BEGIN
    SELECT COUNT(*)
      INTO l_count
      FROM user_tables
     WHERE table_name = 'NSE_NIFTY_TRANSPORT_AVIATION_LOGISTICS_STAGING';

    IF l_count > 0 THEN
        -- Guarded drop: the project avoids destructive drops but this is the rollback script
        EXECUTE IMMEDIATE 'DROP TABLE NSE_NIFTY_TRANSPORT_AVIATION_LOGISTICS_STAGING PURGE';
    END IF;
END;
/

DELETE FROM NSE_SYMBOL_SECTOR_MAP WHERE SECTOR_CODE = 'TRANSPORT_AVIATION_LOGISTICS';
DELETE FROM NSE_SECTOR_MASTER WHERE SECTOR_CODE = 'TRANSPORT_AVIATION_LOGISTICS';

COMMIT;

PROMPT Transport, Aviation & Logistics rollback complete.
