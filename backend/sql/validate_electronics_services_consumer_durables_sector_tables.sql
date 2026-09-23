PROMPT Validating Electronics and Services Consumer Durables sector staging table and master code
SET DEFINE OFF;

DECLARE
    l_count NUMBER := 0;
BEGIN
    SELECT COUNT(*)
      INTO l_count
      FROM user_tables
     WHERE table_name = 'NSE_NIFTY_ELECTRONICS_SERVICES_CONSUMER_DURABLES_STAGING';
    
    IF l_count = 0 THEN
        RAISE_APPLICATION_ERROR(-20001, 'Table NSE_NIFTY_ELECTRONICS_SERVICES_CONSUMER_DURABLES_STAGING does not exist');
    END IF;

    SELECT COUNT(*)
      INTO l_count
      FROM nse_sector_master
     WHERE sector_code = 'ELECTRONICS_SERVICES_CONSUMER_DURABLES';
     
    IF l_count = 0 THEN
        RAISE_APPLICATION_ERROR(-20002, 'Sector master row ELECTRONICS_SERVICES_CONSUMER_DURABLES does not exist');
    END IF;
    
    DBMS_OUTPUT.PUT_LINE('Validation passed for Electronics and Services Consumer Durables.');
END;
/
