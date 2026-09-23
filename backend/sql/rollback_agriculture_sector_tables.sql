PROMPT Rolling back Agriculture sector staging table and master code
SET DEFINE OFF;

DECLARE
    l_count NUMBER := 0;
BEGIN
    SELECT COUNT(*)
      INTO l_count
      FROM user_indexes
     WHERE index_name = 'UK_NIFTY_AGRI_SYMBOL';

    IF l_count > 0 THEN
        EXECUTE IMMEDIATE 'DROP INDEX UK_NIFTY_AGRI_SYMBOL';
    END IF;
END;
/

DECLARE
    l_count NUMBER := 0;
BEGIN
    SELECT COUNT(*)
      INTO l_count
      FROM user_tables
     WHERE table_name = 'NSE_NIFTY_AGRICULTURE_STAGING';

    IF l_count > 0 THEN
        EXECUTE IMMEDIATE 'DROP TABLE NSE_NIFTY_AGRICULTURE_STAGING';
    END IF;
END;
/

DELETE FROM nse_sector_master
WHERE sector_code = 'AGRICULTURE';

COMMIT;

PROMPT Agriculture sector staging table and master code rollback completed.
