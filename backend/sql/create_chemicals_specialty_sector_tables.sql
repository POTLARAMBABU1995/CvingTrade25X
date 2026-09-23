PROMPT Creating Chemicals and Specialty Products sector staging tables and master codes
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
    create_staging_table('NSE_NIFTY_CHEMICALS_STAGING', 'UK_NIFTY_CHEMICALS_SYM');
    create_staging_table('NSE_NIFTY_SPECIALTY_CHEMICALS_STAGING', 'UK_NIFTY_SPEC_CHEM_SYM');
    create_staging_table('NSE_NIFTY_PETROCHEMICALS_STAGING', 'UK_NIFTY_PETROCHEM_SYM');
    create_staging_table('NSE_NIFTY_PAINTS_STAGING', 'UK_NIFTY_PAINTS_SYM');
    create_staging_table('NSE_NIFTY_PLASTIC_PRODUCTS_STAGING', 'UK_NIFTY_PLASTIC_PROD_SYM');
    create_staging_table('NSE_NIFTY_EXPLOSIVES_STAGING', 'UK_NIFTY_EXPLOSIVES_SYM');
    create_staging_table('NSE_NIFTY_ABRASIVES_STAGING', 'UK_NIFTY_ABRASIVES_SYM');
    create_staging_table('NSE_NIFTY_ELECTRODES_REFRACTORIES_STAGING', 'UK_NIFTY_ELECTRODES_SYM');
END;
/

-- Delete the old related sector 'CHEM' (Chemicals) from master
BEGIN
    DELETE FROM NSE_SYMBOL_SECTOR_MAP WHERE SECTOR_CODE = 'CHEM';
    DELETE FROM nse_sector_master WHERE sector_code = 'CHEM';
    COMMIT;
END;
/

-- Merge sectors into nse_sector_master using a PL/SQL block
BEGIN
    MERGE INTO nse_sector_master tgt
    USING (
        SELECT 'CHEMICALS' AS sector_code, 'Chemicals' AS sector_name, 'NIFTY_CHEMICALS' AS index_code, 110 AS display_order FROM dual UNION ALL
        SELECT 'SPECIALTY_CHEMICALS' AS sector_code, 'Specialty Chemicals' AS sector_name, 'NIFTY_SPECIALTY_CHEMICALS' AS index_code, 111 AS display_order FROM dual UNION ALL
        SELECT 'PETROCHEMICALS' AS sector_code, 'Petrochemicals' AS sector_name, 'NIFTY_PETROCHEMICALS' AS index_code, 112 AS display_order FROM dual UNION ALL
        SELECT 'PAINTS' AS sector_code, 'Paints' AS sector_name, 'NIFTY_PAINTS' AS index_code, 113 AS display_order FROM dual UNION ALL
        SELECT 'PLASTIC_PRODUCTS' AS sector_code, 'Plastic Products' AS sector_name, 'NIFTY_PLASTIC_PRODUCTS' AS index_code, 114 AS display_order FROM dual UNION ALL
        SELECT 'EXPLOSIVES' AS sector_code, 'Explosives' AS sector_name, 'NIFTY_EXPLOSIVES' AS index_code, 115 AS display_order FROM dual UNION ALL
        SELECT 'ABRASIVES' AS sector_code, 'Abrasives' AS sector_name, 'NIFTY_ABRASIVES' AS index_code, 116 AS display_order FROM dual UNION ALL
        SELECT 'ELECTRODES_REFRACTORIES' AS sector_code, 'Electrodes & Refractories' AS sector_name, 'NIFTY_ELECTRODES_REFRACTORIES' AS index_code, 117 AS display_order FROM dual
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

PROMPT Chemicals and Specialty Products sector tables and master codes are ready.
