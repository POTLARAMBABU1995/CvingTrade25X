PROMPT Creating Cement, Construction and Infrastructure sector staging tables and master codes
SET DEFINE OFF;

DECLARE
    l_count NUMBER := 0;
BEGIN
    -- 1. Cement & Cement Products Staging Table
    SELECT COUNT(*) INTO l_count FROM user_tables WHERE table_name = 'NSE_NIFTY_CEMENT_CEMENT_PRODUCTS_STAGING';
    IF l_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE TABLE NSE_NIFTY_CEMENT_CEMENT_PRODUCTS_STAGING AS SELECT * FROM NSE_NIFTY_AUTO_STAGING WHERE 1 = 0';
    END IF;
    BEGIN
        EXECUTE IMMEDIATE 'CREATE UNIQUE INDEX UK_NIFTY_CEMENT_SYM ON NSE_NIFTY_CEMENT_CEMENT_PRODUCTS_STAGING (SYMBOL)';
    EXCEPTION WHEN OTHERS THEN
        NULL; -- Ignore if index or column list is already indexed
    END;

    -- 2. Construction Staging Table
    SELECT COUNT(*) INTO l_count FROM user_tables WHERE table_name = 'NSE_NIFTY_CONSTRUCTION_STAGING';
    IF l_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE TABLE NSE_NIFTY_CONSTRUCTION_STAGING AS SELECT * FROM NSE_NIFTY_AUTO_STAGING WHERE 1 = 0';
    END IF;
    BEGIN
        EXECUTE IMMEDIATE 'CREATE UNIQUE INDEX UK_NIFTY_CONSTRUCTION_SYM ON NSE_NIFTY_CONSTRUCTION_STAGING (SYMBOL)';
    EXCEPTION WHEN OTHERS THEN
        NULL; -- Ignore if index or column list is already indexed
    END;

    -- 3. Construction Materials Staging Table
    SELECT COUNT(*) INTO l_count FROM user_tables WHERE table_name = 'NSE_NIFTY_CONSTRUCTION_MATERIALS_STAGING';
    IF l_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE TABLE NSE_NIFTY_CONSTRUCTION_MATERIALS_STAGING AS SELECT * FROM NSE_NIFTY_AUTO_STAGING WHERE 1 = 0';
    END IF;
    BEGIN
        EXECUTE IMMEDIATE 'CREATE UNIQUE INDEX UK_NIFTY_CONST_MAT_SYM ON NSE_NIFTY_CONSTRUCTION_MATERIALS_STAGING (SYMBOL)';
    EXCEPTION WHEN OTHERS THEN
        NULL; -- Ignore if index or column list is already indexed
    END;

    -- 4. Infrastructure Staging Table
    SELECT COUNT(*) INTO l_count FROM user_tables WHERE table_name = 'NSE_NIFTY_INFRASTRUCTURE_STAGING';
    IF l_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE TABLE NSE_NIFTY_INFRASTRUCTURE_STAGING AS SELECT * FROM NSE_NIFTY_AUTO_STAGING WHERE 1 = 0';
    END IF;
    BEGIN
        EXECUTE IMMEDIATE 'CREATE UNIQUE INDEX UK_NIFTY_INFRA_SYM ON NSE_NIFTY_INFRASTRUCTURE_STAGING (SYMBOL)';
    EXCEPTION WHEN OTHERS THEN
        NULL; -- Ignore if index or column list is already indexed
    END;
END;
/

-- Merge sector master rows
MERGE INTO nse_sector_master tgt
USING (
    SELECT 'CEMENT_CEMENT_PRODUCTS' AS sector_code, 'Cement & Cement Products' AS sector_name, 'NIFTY_CEMENT_CEMENT_PRODUCTS' AS index_code, 56 AS display_order FROM dual
    UNION ALL
    SELECT 'CONSTRUCTION' AS sector_code, 'Construction' AS sector_name, 'NIFTY_CONSTRUCTION' AS index_code, 57 AS display_order FROM dual
    UNION ALL
    SELECT 'CONSTRUCTION_MATERIALS' AS sector_code, 'Construction Materials' AS sector_name, 'NIFTY_CONSTRUCTION_MATERIALS' AS index_code, 58 AS display_order FROM dual
    UNION ALL
    SELECT 'INFRASTRUCTURE' AS sector_code, 'Infrastructure' AS sector_name, 'NIFTY_INFRASTRUCTURE' AS index_code, 59 AS display_order FROM dual
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

PROMPT Cement, Construction and Infrastructure sector staging tables and master codes are ready.
