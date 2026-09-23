PROMPT Creating source-pack unique sector staging tables and master codes
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
                            NULL;
                        ELSE
                            RAISE;
                        END IF;
                END;
            END IF;
        END IF;
    END;
BEGIN
    create_staging_table('NSE_NIFTY_HOUSEHOLD_PERSONAL_PRODUCTS_STAGING', 'UK_NFTY_HHPROD_SYM');
    create_staging_table('NSE_NIFTY_COMMODITIES_TRADING_STAGING', 'UK_NFTY_CMDTY_TRD_SYM');
    create_staging_table('NSE_NIFTY_DEFENCE_AEROSPACE_DEFENSE_STAGING', 'UK_NFTY_DEF_AERO_SYM');
    create_staging_table('NSE_NIFTY_DIVERSIFIED_STAGING', 'UK_NFTY_DIVERS_SYM');
    create_staging_table('NSE_NIFTY_BIOTECHNOLOGY_STAGING', 'UK_NFTY_BIOTECH_SYM');
    create_staging_table('NSE_NIFTY_MEDICAL_EQUIPMENT_SUPPLIES_STAGING', 'UK_NFTY_MEDSUP_SYM');
    create_staging_table('NSE_NIFTY_IT_ENABLED_SERVICES_STAGING', 'UK_NFTY_ITES_SYM');
    create_staging_table('NSE_NIFTY_SOFTWARE_PRODUCTS_SERVICES_STAGING', 'UK_NFTY_SWPROD_SYM');
    create_staging_table('NSE_NIFTY_MEDIA_ENTERTAINMENT_STAGING', 'UK_NFTY_MEDIAENT_SYM');
    create_staging_table('NSE_NIFTY_PRINT_MEDIA_PUBLISHING_STAGING', 'UK_NFTY_PRNTPUB_SYM');
    create_staging_table('NSE_NIFTY_METALS_MINING_STAGING', 'UK_NFTY_METMIN_SYM');
    create_staging_table('NSE_NIFTY_IRON_STEEL_STAGING', 'UK_NFTY_IRONSTL_SYM');
    create_staging_table('NSE_NIFTY_MINING_STAGING', 'UK_NFTY_MINING_SYM');
    create_staging_table('NSE_NIFTY_NON_FERROUS_METALS_STAGING', 'UK_NFTY_NFMET_SYM');
    create_staging_table('NSE_NIFTY_LPG_CNG_PNG_LNG_SUPPLIER_STAGING', 'UK_NFTY_LPGSUP_SYM');
    create_staging_table('NSE_NIFTY_LUBRICANTS_STAGING', 'UK_NFTY_LUBRIC_SYM');
    create_staging_table('NSE_NIFTY_OIL_EQUIPMENT_SERVICES_STAGING', 'UK_NFTY_OILEQP_SYM');
    create_staging_table('NSE_NIFTY_PETROLEUM_PRODUCTS_REFINERIES_STAGING', 'UK_NFTY_PETREF_SYM');
    create_staging_table('NSE_NIFTY_PAPER_PACKAGING_STAGING', 'UK_NFTY_PAPERPK_SYM');
    create_staging_table('NSE_NIFTY_WASTE_WATER_MANAGEMENT_STAGING', 'UK_NFTY_WSTWTR_SYM');
    create_staging_table('NSE_NIFTY_FOOTWEAR_STAGING', 'UK_NFTY_FOOTWR_SYM');
    create_staging_table('NSE_NIFTY_GEMS_STAGING', 'UK_NFTY_GEMS_SYM');
    create_staging_table('NSE_NIFTY_JEWELLERY_WATCHES_STAGING', 'UK_NFTY_JEWLWT_SYM');
    create_staging_table('NSE_NIFTY_LEATHER_LEATHER_PRODUCTS_STAGING', 'UK_NFTY_LEATHR_SYM');
    create_staging_table('NSE_NIFTY_TEXTILES_APPARELS_STAGING', 'UK_NFTY_TXTAPP_SYM');
END;
/

BEGIN
    MERGE INTO nse_sector_master tgt
    USING (
        SELECT 'HOUSEHOLD_PERSONAL_PRODUCTS' AS sector_code, 'Household & Personal Products' AS sector_name, 'NIFTY_HOUSEHOLD_PERSONAL_PRODUCTS' AS index_code, 118 AS display_order FROM dual UNION ALL
        SELECT 'COMMODITIES_TRADING', 'Commodities & Trading', 'NIFTY_COMMODITIES_TRADING', 119 FROM dual UNION ALL
        SELECT 'DEFENCE_AEROSPACE_DEFENSE', 'Defence Aerospace & Defense', 'NIFTY_DEFENCE_AEROSPACE_DEFENSE', 120 FROM dual UNION ALL
        SELECT 'DIVERSIFIED', 'Diversified', 'NIFTY_DIVERSIFIED', 121 FROM dual UNION ALL
        SELECT 'BIOTECHNOLOGY', 'Biotechnology', 'NIFTY_BIOTECHNOLOGY', 122 FROM dual UNION ALL
        SELECT 'MEDICAL_EQUIPMENT_SUPPLIES', 'Medical Equipment & Supplies', 'NIFTY_MEDICAL_EQUIPMENT_SUPPLIES', 123 FROM dual UNION ALL
        SELECT 'IT_ENABLED_SERVICES', 'IT Enabled Services', 'NIFTY_IT_ENABLED_SERVICES', 124 FROM dual UNION ALL
        SELECT 'SOFTWARE_PRODUCTS_SERVICES', 'Software Products & Services', 'NIFTY_SOFTWARE_PRODUCTS_SERVICES', 125 FROM dual UNION ALL
        SELECT 'MEDIA_ENTERTAINMENT', 'Media & Entertainment', 'NIFTY_MEDIA_ENTERTAINMENT', 126 FROM dual UNION ALL
        SELECT 'PRINT_MEDIA_PUBLISHING', 'Print Media & Publishing', 'NIFTY_PRINT_MEDIA_PUBLISHING', 127 FROM dual UNION ALL
        SELECT 'METALS_MINING', 'Metals & Mining', 'NIFTY_METALS_MINING', 128 FROM dual UNION ALL
        SELECT 'IRON_STEEL', 'Iron & Steel', 'NIFTY_IRON_STEEL', 129 FROM dual UNION ALL
        SELECT 'MINING', 'Mining', 'NIFTY_MINING', 130 FROM dual UNION ALL
        SELECT 'NON_FERROUS_METALS', 'Non-Ferrous Metals', 'NIFTY_NON_FERROUS_METALS', 131 FROM dual UNION ALL
        SELECT 'LPG_CNG_PNG_LNG_SUPPLIER', 'LPG CNG PNG LNG Supplier', 'NIFTY_LPG_CNG_PNG_LNG_SUPPLIER', 132 FROM dual UNION ALL
        SELECT 'LUBRICANTS', 'Lubricants', 'NIFTY_LUBRICANTS', 133 FROM dual UNION ALL
        SELECT 'OIL_EQUIPMENT_SERVICES', 'Oil Equipment & Services', 'NIFTY_OIL_EQUIPMENT_SERVICES', 134 FROM dual UNION ALL
        SELECT 'PETROLEUM_PRODUCTS_REFINERIES', 'Petroleum Products & Refineries', 'NIFTY_PETROLEUM_PRODUCTS_REFINERIES', 135 FROM dual UNION ALL
        SELECT 'PAPER_PACKAGING', 'Paper & Packaging', 'NIFTY_PAPER_PACKAGING', 136 FROM dual UNION ALL
        SELECT 'WASTE_WATER_MANAGEMENT', 'Waste & Water Management', 'NIFTY_WASTE_WATER_MANAGEMENT', 137 FROM dual UNION ALL
        SELECT 'FOOTWEAR', 'Footwear', 'NIFTY_FOOTWEAR', 138 FROM dual UNION ALL
        SELECT 'GEMS', 'Gems', 'NIFTY_GEMS', 139 FROM dual UNION ALL
        SELECT 'JEWELLERY_WATCHES', 'Jewellery & Watches', 'NIFTY_JEWELLERY_WATCHES', 140 FROM dual UNION ALL
        SELECT 'LEATHER_LEATHER_PRODUCTS', 'Leather & Leather Products', 'NIFTY_LEATHER_LEATHER_PRODUCTS', 141 FROM dual UNION ALL
        SELECT 'TEXTILES_APPARELS', 'Textiles & Apparels', 'NIFTY_TEXTILES_APPARELS', 142 FROM dual
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

PROMPT Source-pack unique sector staging tables and master codes are ready.
