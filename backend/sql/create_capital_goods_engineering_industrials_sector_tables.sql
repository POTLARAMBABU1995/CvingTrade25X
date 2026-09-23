PROMPT Creating Capital Goods, Engineering & Industrials sector staging tables and master codes
SET DEFINE OFF;

DECLARE
    l_count NUMBER := 0;
    PROCEDURE create_staging_table(p_table VARCHAR2, p_idx VARCHAR2) IS
        l_col_exists NUMBER := 0;
    BEGIN
        SELECT COUNT(*) INTO l_count FROM user_tables WHERE table_name = p_table;
        IF l_count = 0 THEN
            EXECUTE IMMEDIATE 'CREATE TABLE ' || p_table || ' AS SELECT * FROM NSE_NIFTY_AUTO_STAGING WHERE 1 = 0';
        END IF;

        -- Check if column SYMBOL is already indexed on this table
        SELECT COUNT(*) INTO l_col_exists
        FROM user_ind_columns
        WHERE table_name = p_table AND column_name = 'SYMBOL';

        IF l_col_exists = 0 THEN
            SELECT COUNT(*) INTO l_count FROM user_indexes WHERE index_name = p_idx;
            IF l_count = 0 THEN
                BEGIN
                    EXECUTE IMMEDIATE 'CREATE UNIQUE INDEX ' || p_idx || ' ON ' || p_table || ' (SYMBOL)';
                EXCEPTION
                    WHEN OTHERS THEN
                        IF SQLCODE = -1408 OR SQLCODE = -955 THEN
                            NULL; -- Index or column list already indexed
                        ELSE
                            RAISE;
                        END IF;
                END;
            END IF;
        END IF;
    END;
BEGIN
    create_staging_table('NSE_NIFTY_ENGINEERING_STAGING', 'UK_NIFTY_ENGINEERING_SYM');
    create_staging_table('NSE_NIFTY_ELEC_HEAVY_EQUIP_STAGING', 'UK_NIFTY_ELEC_HEAVY_SYM');
    create_staging_table('NSE_NIFTY_INDUSTRIAL_MANUFACTURING_STAGING', 'UK_NIFTY_IND_MFG_SYM');
    create_staging_table('NSE_NIFTY_INDUSTRIAL_PRODUCTS_STAGING', 'UK_NIFTY_IND_PROD_SYM');
    create_staging_table('NSE_NIFTY_INDUSTRIAL_GASES_FUELS_STAGING', 'UK_NIFTY_IND_GAS_FUEL_SYM');
    create_staging_table('NSE_NIFTY_CAPITAL_GOODS_STAGING', 'UK_NIFTY_CAP_GOODS_SYM');
END;
/

-- Merge sectors into nse_sector_master using a PL/SQL block to handle semicolons cleanly
BEGIN
    MERGE INTO nse_sector_master tgt
    USING (
        SELECT 'ENGINEERING' AS sector_code, 'Engineering' AS sector_name, 'NIFTY_ENGINEERING' AS index_code, 70 AS display_order FROM dual UNION ALL
        SELECT 'ELEC_HEAVY_EQUIPMENT' AS sector_code, 'Electricals Heavy Electrical Equipment' AS sector_name, 'NIFTY_ELEC_HEAVY_EQUIPMENT' AS index_code, 71 AS display_order FROM dual UNION ALL
        SELECT 'INDUSTRIAL_MANUFACTURING' AS sector_code, 'Industrial Manufacturing' AS sector_name, 'NIFTY_INDUSTRIAL_MANUFACTURING' AS index_code, 72 AS display_order FROM dual UNION ALL
        SELECT 'INDUSTRIAL_PRODUCTS' AS sector_code, 'Industrial Products' AS sector_name, 'NIFTY_INDUSTRIAL_PRODUCTS' AS index_code, 73 AS display_order FROM dual UNION ALL
        SELECT 'INDUSTRIAL_GASES_FUELS' AS sector_code, 'Industrial Gases & Fuels' AS sector_name, 'NIFTY_INDUSTRIAL_GASES_FUELS' AS index_code, 74 AS display_order FROM dual UNION ALL
        SELECT 'CAPITAL_GOODS' AS sector_code, 'Capital Goods' AS sector_name, 'NIFTY_CAPITAL_GOODS' AS index_code, 75 AS display_order FROM dual
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
END;
/

PROMPT Capital Goods, Engineering & Industrials sector staging tables and master codes are ready.
