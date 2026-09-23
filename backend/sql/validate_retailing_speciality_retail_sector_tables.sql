PROMPT Validating Retailing Speciality Retail sector tables

SET SERVEROUTPUT ON;

DECLARE
    v_count NUMBER;
    v_symbol_count NUMBER;
    v_duplicate_count NUMBER;
    v_join_count NUMBER;
BEGIN
    SELECT COUNT(*) INTO v_count FROM user_tables WHERE table_name = 'NSE_NIFTY_RETAILING_SPECIALITY_RETAIL_STAGING';
    IF v_count = 0 THEN
        DBMS_OUTPUT.PUT_LINE('FAIL: Staging table does not exist.');
    ELSE
        DBMS_OUTPUT.PUT_LINE('PASS: Staging table exists.');
    END IF;

    EXECUTE IMMEDIATE 'SELECT COUNT(*) FROM NSE_NIFTY_RETAILING_SPECIALITY_RETAIL_STAGING' INTO v_symbol_count;
    DBMS_OUTPUT.PUT_LINE('INFO: Staging table has ' || v_symbol_count || ' rows.');

    EXECUTE IMMEDIATE 'SELECT COUNT(*) FROM (SELECT SYMBOL FROM NSE_NIFTY_RETAILING_SPECIALITY_RETAIL_STAGING GROUP BY SYMBOL HAVING COUNT(*) > 1)' INTO v_duplicate_count;
    IF v_duplicate_count > 0 THEN
        DBMS_OUTPUT.PUT_LINE('FAIL: Duplicate symbols found in staging table.');
    ELSE
        DBMS_OUTPUT.PUT_LINE('PASS: No duplicate symbols inside staging table.');
    END IF;

    SELECT COUNT(*) INTO v_count FROM NSE_SECTOR_MASTER WHERE sector_code = 'RETAILING_SPECIALITY_RETAIL';
    IF v_count = 0 THEN
        DBMS_OUTPUT.PUT_LINE('FAIL: Sector master row missing.');
    ELSE
        DBMS_OUTPUT.PUT_LINE('PASS: Sector master row exists.');
    END IF;

    SELECT COUNT(*) INTO v_count FROM VW_NSE_CANONICAL_SECTOR_STAGE WHERE source_table = 'NSE_NIFTY_RETAILING_SPECIALITY_RETAIL_STAGING';
    IF v_count = 0 THEN
        DBMS_OUTPUT.PUT_LINE('FAIL: Canonical source view does NOT include the new staging table.');
    ELSE
        DBMS_OUTPUT.PUT_LINE('PASS: Canonical source view includes the staging table.');
    END IF;

    EXECUTE IMMEDIATE 'SELECT COUNT(*) FROM NSE_NIFTY_RETAILING_SPECIALITY_RETAIL_STAGING s JOIN NSE_NIFTY500_DAILY_RAW_DATA_DEV d ON s.SYMBOL = d.SYMBOL' INTO v_join_count;
    IF v_join_count = 0 THEN
        DBMS_OUTPUT.PUT_LINE('FAIL: DEV table to staging table join returned 0 rows.');
    ELSE
        DBMS_OUTPUT.PUT_LINE('PASS: DEV table to staging table join returns ' || v_join_count || ' rows.');
    END IF;
END;
/
