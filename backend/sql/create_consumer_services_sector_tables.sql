PROMPT Creating Consumer Services sector staging table and master code
SET DEFINE OFF;

DECLARE
    l_count NUMBER := 0;
BEGIN
    SELECT COUNT(*)
      INTO l_count
      FROM user_tables
     WHERE table_name = 'NSE_NIFTY_CONSUMER_SERVICES_STAGING';

    IF l_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE TABLE NSE_NIFTY_CONSUMER_SERVICES_STAGING AS SELECT * FROM NSE_NIFTY_AUTO_STAGING WHERE 1 = 0';
    END IF;

    SELECT COUNT(*)
      INTO l_count
      FROM user_indexes
     WHERE index_name = 'UK_NIFTY_CONS_SERV_SYM';

    IF l_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE UNIQUE INDEX UK_NIFTY_CONS_SERV_SYM ON NSE_NIFTY_CONSUMER_SERVICES_STAGING (SYMBOL)';
    END IF;
END;
/

MERGE INTO nse_sector_master tgt
USING (
    SELECT
        'CONSUMER_SERVICES' AS sector_code,
        'Consumer Services' AS sector_name,
        'NIFTY_CONSUMER_SERVICES' AS index_code,
        50 AS display_order
    FROM dual
) src
ON (tgt.sector_code = src.sector_code)
WHEN MATCHED THEN UPDATE SET
    tgt.sector_name = src.sector_name,
    tgt.index_code = src.index_code,
    tgt.display_order = NVL(tgt.display_order, src.display_order)
WHEN NOT MATCHED THEN
    INSERT (sector_code, sector_name, index_code, display_order)
    VALUES (src.sector_code, src.sector_name, src.index_code, src.display_order);

COMMIT;

PROMPT Consumer Services sector staging table and master code are ready.
