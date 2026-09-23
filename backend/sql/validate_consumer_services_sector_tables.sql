PROMPT Validating Consumer Services sector staging table and master code
SET DEFINE OFF;

DECLARE
    l_count NUMBER := 0;
BEGIN
    SELECT COUNT(*)
      INTO l_count
      FROM user_tables
     WHERE table_name = 'NSE_NIFTY_CONSUMER_SERVICES_STAGING';
    
    IF l_count = 0 THEN
        RAISE_APPLICATION_ERROR(-20001, 'Table NSE_NIFTY_CONSUMER_SERVICES_STAGING does not exist');
    END IF;

    SELECT COUNT(*)
      INTO l_count
      FROM nse_sector_master
     WHERE sector_code = 'CONSUMER_SERVICES';
     
    IF l_count = 0 THEN
        RAISE_APPLICATION_ERROR(-20002, 'Sector master row CONSUMER_SERVICES does not exist');
    END IF;
    
    DBMS_OUTPUT.PUT_LINE('Validation passed for Consumer Services.');
END;
/
