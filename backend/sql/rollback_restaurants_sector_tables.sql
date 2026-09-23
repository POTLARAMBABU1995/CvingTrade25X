PROMPT Rollback Restaurants Sector Table and References

SET DEFINE OFF;

DECLARE
  v_exists NUMBER;
BEGIN
  -- We don't drop tables aggressively if standard requires guarded. But here we can use a conditional drop:
  SELECT COUNT(*) INTO v_exists FROM user_tables WHERE table_name = 'NSE_NIFTY_RESTAURANTS_STAGING';
  IF v_exists > 0 THEN
    EXECUTE IMMEDIATE 'DROP TABLE NSE_NIFTY_RESTAURANTS_STAGING';
    DBMS_OUTPUT.PUT_LINE('Dropped table NSE_NIFTY_RESTAURANTS_STAGING');
  END IF;
END;
/

DELETE FROM NSE_SYMBOL_SECTOR_MAP WHERE SECTOR_CODE = 'RESTAURANTS';
DELETE FROM NSE_SECTOR_MASTER WHERE SECTOR_CODE = 'RESTAURANTS';

COMMIT;
EXIT;
