PROMPT Creating procedure PRC_SYNC_SECTOR_ROTATION_MISSING_SYMBOLS (create only 6 missing tables + merge missing symbols)
SET DEFINE OFF;

CREATE OR REPLACE NONEDITIONABLE PROCEDURE PRC_SYNC_SECTOR_ROTATION_MISSING_SYMBOLS (
    p_source_table IN VARCHAR2 DEFAULT NULL
) AS
    TYPE t_sector_map_rec IS RECORD (
        sector_name     VARCHAR2(150),
        source_industry VARCHAR2(150),
        table_name      VARCHAR2(128),
        index_name      VARCHAR2(30),
        can_create      CHAR(1)
    );
    TYPE t_sector_map_tab IS TABLE OF t_sector_map_rec;

    l_mappings t_sector_map_tab := t_sector_map_tab(
        t_sector_map_rec('Auto', 'Automobile and Auto Components', 'NSE_NIFTY_AUTO_STAGING', NULL, 'N'),
        t_sector_map_rec('Bank', NULL, 'NSE_NIFTY_BANK_STAGING', NULL, 'N'),
        t_sector_map_rec('Chemicals', 'Chemicals', 'NSE_NIFTY_CHEMICALS_STAGING', NULL, 'N'),
        t_sector_map_rec('Financial Services', 'Financial Services', 'NSE_NIFTY_FINANCIAL_SERVICES_STAGING', NULL, 'N'),
        t_sector_map_rec('FMCG', 'Fast Moving Consumer Goods', 'NSE_NIFTY_FMCG_STAGING', NULL, 'N'),
        t_sector_map_rec('Healthcare', 'Healthcare', 'NSE_NIFTY_HEALTHCARE_INDEX_STAGING', NULL, 'N'),
        t_sector_map_rec('IT', 'Information Technology', 'NSE_NIFTY_IT_STAGING', NULL, 'N'),
        t_sector_map_rec('Media', 'Media Entertainment & Publication', 'NSE_NIFTY_MEDIA_STAGING', NULL, 'N'),
        t_sector_map_rec('Metal', 'Metals & Mining', 'NSE_NIFTY_METAL_STAGING', NULL, 'N'),
        t_sector_map_rec('Pharma', NULL, 'NSE_NIFTY_PHARMA_STAGING', NULL, 'N'),
        t_sector_map_rec('Private Bank', NULL, 'NSE_NIFTY_PRIVATE_BANK_STAGING', NULL, 'N'),
        t_sector_map_rec('PSU Bank', NULL, 'NSE_NIFTY_PSU_BANK_STAGING', NULL, 'N'),
        t_sector_map_rec('Realty', 'Realty', 'NSE_NIFTY_REALITY_STAGING', NULL, 'N'),
        t_sector_map_rec('Consumer Durables', 'Consumer Durables', 'NSE_NIFTY_CONSUMER_DURABLES_STAGING', NULL, 'N'),
        t_sector_map_rec('Oil & Gas', 'Oil Gas & Consumable Fuels', 'NSE_NIFTY_OIL_AND_GAS_STAGING', NULL, 'N'),
        t_sector_map_rec('Capital Goods', 'Capital Goods', 'NSE_NIFTY_CAPITAL_GOODS_STAGING', 'UK_NIFTY_CAP_GDS_SYM', 'Y'),
        t_sector_map_rec('Construction', 'Construction', 'NSE_NIFTY_CONSTRUCTION_STAGING', 'UK_NIFTY_CONSTR_SYM', 'Y'),
        t_sector_map_rec('Power', 'Power', 'NSE_NIFTY_POWER_STAGING', 'UK_NIFTY_POWER_SYM', 'Y'),
        t_sector_map_rec('Services', 'Services', 'NSE_NIFTY_SERVICES_STAGING', 'UK_NIFTY_SERVICES_SYM', 'Y'),
        t_sector_map_rec('Telecom', 'Telecommunication', 'NSE_NIFTY_TELECOMMUNICATION_STAGING', 'UK_NIFTY_TELECOM_SYM', 'Y'),
        t_sector_map_rec('Utilities', 'Utilities', 'NSE_NIFTY_UTILITIES_STAGING', 'UK_NIFTY_UTILITIES_SYM', 'Y'),
        t_sector_map_rec('NBFC', 'NBFC', 'NSE_NIFTY_NBFC_STAGING', 'UK_NIFTY_NBFC_SYM', 'Y'),
        t_sector_map_rec('Insurance', 'Insurance', 'NSE_NIFTY_INSURANCE_STAGING', 'UK_NIFTY_INSURANCE_SYM', 'Y'),
        t_sector_map_rec('Capital Markets', 'Capital Markets', 'NSE_NIFTY_CAPITAL_MARKETS_STAGING', 'UK_NIFTY_CAPMKT_SYM', 'Y'),
        t_sector_map_rec('Asset Management Company', 'Asset Management Company', 'NSE_NIFTY_ASSET_MANAGEMENT_COMPANY_STAGING', 'UK_NIFTY_AMC_SYM', 'Y'),
        t_sector_map_rec('Fintech', 'Fintech', 'NSE_NIFTY_FINTECH_STAGING', 'UK_NIFTY_FINTECH_SYM', 'Y'),
        t_sector_map_rec('Housing Finance Company', 'Housing Finance Company', 'NSE_NIFTY_HOUSING_FINANCE_COMPANY_STAGING', 'UK_NIFTY_HFC_SYM', 'Y'),
        t_sector_map_rec('Stockbroking & Allied', 'Stockbroking & Allied', 'NSE_NIFTY_STOCKBROKING_AND_ALLIED_STAGING', 'UK_NIFTY_BRK_SYM', 'Y')
    );

    l_reference_table     VARCHAR2(128) := 'NSE_NIFTY_AUTO_STAGING';
    l_source_table        VARCHAR2(128);
    l_symbol_col          VARCHAR2(128);
    l_company_name_col    VARCHAR2(128);
    l_industry_col        VARCHAR2(128);
    l_series_col          VARCHAR2(128);
    l_isin_col            VARCHAR2(128);

    l_merge_sql           CLOB;
    l_source_count_sql    CLOB;
    l_missing_sql         CLOB;

    l_source_total        NUMBER := 0;
    l_missing_before      NUMBER := 0;
    l_missing_after       NUMBER := 0;
    l_inserted            NUMBER := 0;
    l_skipped             NUMBER := 0;

    FUNCTION normalize_key(p_value IN VARCHAR2) RETURN VARCHAR2 IS
        l_key VARCHAR2(4000);
    BEGIN
        l_key := UPPER(TRIM(NVL(p_value, '')));
        l_key := REPLACE(l_key, '&', ' AND ');
        l_key := REPLACE(l_key, '-', ' ');
        l_key := REGEXP_REPLACE(l_key, '[[:space:]]+', ' ');
        RETURN l_key;
    END;

    FUNCTION is_safe_sql_name(p_name IN VARCHAR2) RETURN BOOLEAN IS
    BEGIN
        RETURN REGEXP_LIKE(UPPER(TRIM(p_name)), '^[A-Z][A-Z0-9_$#]*$');
    END;

    FUNCTION table_exists(p_table_name IN VARCHAR2) RETURN BOOLEAN IS
        l_cnt NUMBER;
    BEGIN
        SELECT COUNT(*)
          INTO l_cnt
          FROM USER_TABLES
         WHERE TABLE_NAME = UPPER(TRIM(p_table_name));
        RETURN l_cnt > 0;
    END;

    FUNCTION column_exists(p_table_name IN VARCHAR2, p_col_name IN VARCHAR2) RETURN BOOLEAN IS
        l_cnt NUMBER;
    BEGIN
        SELECT COUNT(*)
          INTO l_cnt
          FROM USER_TAB_COLUMNS
         WHERE TABLE_NAME = UPPER(TRIM(p_table_name))
           AND COLUMN_NAME = UPPER(TRIM(p_col_name));
        RETURN l_cnt > 0;
    END;

    FUNCTION choose_source_col(p_candidates IN SYS.ODCIVARCHAR2LIST) RETURN VARCHAR2 IS
        l_col VARCHAR2(128);
        l_cnt NUMBER;
    BEGIN
        FOR i IN 1 .. p_candidates.COUNT LOOP
            SELECT COUNT(*)
              INTO l_cnt
              FROM USER_TAB_COLUMNS
             WHERE TABLE_NAME = l_source_table
               AND COLUMN_NAME = UPPER(TRIM(p_candidates(i)));
            IF l_cnt > 0 THEN
                l_col := UPPER(TRIM(p_candidates(i)));
                RETURN l_col;
            END IF;
        END LOOP;
        RETURN NULL;
    END;

    PROCEDURE ensure_table_if_missing(
        p_table_name IN VARCHAR2,
        p_index_name IN VARCHAR2,
        p_can_create IN CHAR
    ) IS
        l_idx_count NUMBER;
    BEGIN
        DBMS_OUTPUT.PUT_LINE('Checking table: ' || p_table_name);
        IF table_exists(p_table_name) THEN
            RETURN;
        END IF;

        IF p_can_create <> 'Y' THEN
            DBMS_OUTPUT.PUT_LINE('Table missing but not in create-scope, skipped: ' || p_table_name);
            RETURN;
        END IF;

        EXECUTE IMMEDIATE
            'CREATE TABLE ' || p_table_name || ' AS SELECT * FROM ' || l_reference_table || ' WHERE 1 = 0';
        DBMS_OUTPUT.PUT_LINE('Created missing table: ' || p_table_name);

        BEGIN
            IF p_index_name IS NOT NULL THEN
                SELECT COUNT(*)
                  INTO l_idx_count
                  FROM USER_INDEXES
                 WHERE INDEX_NAME = UPPER(TRIM(p_index_name));
                IF l_idx_count = 0 THEN
                    EXECUTE IMMEDIATE 'CREATE UNIQUE INDEX ' || p_index_name || ' ON ' || p_table_name || '(SYMBOL)';
                    DBMS_OUTPUT.PUT_LINE('Created unique index: ' || p_index_name);
                END IF;
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF SQLCODE != -955 THEN
                    RAISE;
                END IF;
        END;
    END;

    FUNCTION build_source_subquery(
        p_sector_name IN VARCHAR2,
        p_source_industry IN VARCHAR2
    ) RETURN CLOB IS
        l_sql CLOB;
    BEGIN
        l_sql := 'SELECT DISTINCT UPPER(TRIM(s.' || l_symbol_col || ')) AS SYMBOL';

        IF l_company_name_col IS NOT NULL THEN
            l_sql := l_sql || ', TRIM(s.' || l_company_name_col || ') AS COMPANY_NAME';
        ELSE
            l_sql := l_sql || ', CAST(NULL AS VARCHAR2(300)) AS COMPANY_NAME';
        END IF;

        l_sql := l_sql || ', ''' || REPLACE(p_sector_name, '''', '''''') || ''' AS SECTOR';
        l_sql := l_sql || ', ''' || REPLACE(p_sector_name, '''', '''''') || ''' AS INDUSTRY';

        IF l_series_col IS NOT NULL THEN
            l_sql := l_sql || ', TRIM(s.' || l_series_col || ') AS SERIES';
        ELSE
            l_sql := l_sql || ', CAST(NULL AS VARCHAR2(20)) AS SERIES';
        END IF;

        IF l_isin_col IS NOT NULL THEN
            l_sql := l_sql || ', TRIM(s.' || l_isin_col || ') AS ISIN_CODE';
        ELSE
            l_sql := l_sql || ', CAST(NULL AS VARCHAR2(50)) AS ISIN_CODE';
        END IF;

        l_sql := l_sql || ', ''Y'' AS ACTIVE_FLAG, SYSDATE AS CREATED_DATE, SYSDATE AS UPDATED_DATE ' ||
                 'FROM ' || l_source_table || ' s ' ||
                 'WHERE s.' || l_symbol_col || ' IS NOT NULL ' ||
                 'AND TRIM(s.' || l_symbol_col || ') IS NOT NULL ' ||
                 'AND UPPER(REGEXP_REPLACE(REPLACE(REPLACE(TRIM(s.' || l_industry_col || '), ''&'', '' AND ''), ''-'', '' ''), ''[[:space:]]+'', '' '')) = :industry_key';

        RETURN l_sql;
    END;

BEGIN
    IF NOT table_exists(l_reference_table) THEN
        RAISE_APPLICATION_ERROR(-20001, 'Reference table not found: ' || l_reference_table);
    END IF;

    l_source_table := UPPER(TRIM(p_source_table));
    IF l_source_table IS NULL THEN
        IF table_exists('NSE_TOTAL_MARKET_SECTOR_SOURCE_STG') THEN
            l_source_table := 'NSE_TOTAL_MARKET_SECTOR_SOURCE_STG';
        ELSIF table_exists('NSE_TOTAL_MARKET_SECTOR_STG') THEN
            l_source_table := 'NSE_TOTAL_MARKET_SECTOR_STG';
        ELSE
            RAISE_APPLICATION_ERROR(-20002, 'Source table not found. Provide p_source_table.');
        END IF;
    END IF;

    IF NOT is_safe_sql_name(l_source_table) OR NOT table_exists(l_source_table) THEN
        RAISE_APPLICATION_ERROR(-20003, 'Invalid source table: ' || NVL(l_source_table, 'NULL'));
    END IF;

    l_symbol_col       := choose_source_col(SYS.ODCIVARCHAR2LIST('SYMBOL'));
    l_company_name_col := choose_source_col(SYS.ODCIVARCHAR2LIST('COMPANY_NAME', 'COMPANY'));
    l_industry_col     := choose_source_col(SYS.ODCIVARCHAR2LIST('INDUSTRY'));
    l_series_col       := choose_source_col(SYS.ODCIVARCHAR2LIST('SERIES'));
    l_isin_col         := choose_source_col(SYS.ODCIVARCHAR2LIST('ISIN_CODE', 'ISIN'));

    IF l_symbol_col IS NULL THEN
        RAISE_APPLICATION_ERROR(-20004, 'Source table must contain SYMBOL column.');
    END IF;
    IF l_industry_col IS NULL THEN
        RAISE_APPLICATION_ERROR(-20005, 'Source table must contain INDUSTRY column.');
    END IF;

    DBMS_OUTPUT.PUT_LINE('Using source table: ' || l_source_table);

    FOR i IN 1 .. l_mappings.COUNT LOOP
        IF NOT is_safe_sql_name(l_mappings(i).table_name) THEN
            RAISE_APPLICATION_ERROR(-20006, 'Unsafe table in mapping: ' || l_mappings(i).table_name);
        END IF;

        ensure_table_if_missing(l_mappings(i).table_name, l_mappings(i).index_name, l_mappings(i).can_create);

        IF NOT table_exists(l_mappings(i).table_name) THEN
            DBMS_OUTPUT.PUT_LINE('Skipped (table unavailable): ' || l_mappings(i).table_name);
            CONTINUE;
        END IF;

        IF l_mappings(i).source_industry IS NULL THEN
            DBMS_OUTPUT.PUT_LINE('Skipped (no source-industry mapping): ' || l_mappings(i).sector_name || ' -> ' || l_mappings(i).table_name);
            CONTINUE;
        END IF;

        l_source_count_sql :=
            'SELECT COUNT(*) FROM (' ||
            'SELECT DISTINCT UPPER(TRIM(s.' || l_symbol_col || ')) AS SYMBOL ' ||
            'FROM ' || l_source_table || ' s ' ||
            'WHERE s.' || l_symbol_col || ' IS NOT NULL ' ||
            'AND TRIM(s.' || l_symbol_col || ') IS NOT NULL ' ||
            'AND UPPER(REGEXP_REPLACE(REPLACE(REPLACE(TRIM(s.' || l_industry_col || '), ''&'', '' AND ''), ''-'', '' ''), ''[[:space:]]+'', '' '')) = :industry_key)';

        EXECUTE IMMEDIATE l_source_count_sql
            INTO l_source_total
            USING normalize_key(l_mappings(i).source_industry);

        l_missing_sql :=
            'SELECT COUNT(*) FROM (' ||
            'SELECT src.SYMBOL FROM (' || build_source_subquery(l_mappings(i).sector_name, l_mappings(i).source_industry) || ') src ' ||
            'WHERE NOT EXISTS (' ||
            'SELECT 1 FROM ' || l_mappings(i).table_name || ' t ' ||
            'WHERE UPPER(TRIM(t.SYMBOL)) = src.SYMBOL))';

        EXECUTE IMMEDIATE l_missing_sql
            INTO l_missing_before
            USING normalize_key(l_mappings(i).source_industry);

        l_merge_sql :=
            'MERGE INTO ' || l_mappings(i).table_name || ' t ' ||
            'USING (' || build_source_subquery(l_mappings(i).sector_name, l_mappings(i).source_industry) || ') src ' ||
            'ON (UPPER(TRIM(t.SYMBOL)) = src.SYMBOL) ' ||
            'WHEN NOT MATCHED THEN INSERT (SYMBOL';

        IF column_exists(l_mappings(i).table_name, 'COMPANY_NAME') THEN l_merge_sql := l_merge_sql || ', COMPANY_NAME'; END IF;
        IF column_exists(l_mappings(i).table_name, 'SECTOR') THEN l_merge_sql := l_merge_sql || ', SECTOR'; END IF;
        IF column_exists(l_mappings(i).table_name, 'INDUSTRY') THEN l_merge_sql := l_merge_sql || ', INDUSTRY'; END IF;
        IF column_exists(l_mappings(i).table_name, 'SERIES') THEN l_merge_sql := l_merge_sql || ', SERIES'; END IF;
        IF column_exists(l_mappings(i).table_name, 'ISIN_CODE') THEN l_merge_sql := l_merge_sql || ', ISIN_CODE'; END IF;
        IF column_exists(l_mappings(i).table_name, 'ACTIVE_FLAG') THEN l_merge_sql := l_merge_sql || ', ACTIVE_FLAG'; END IF;
        IF column_exists(l_mappings(i).table_name, 'CREATED_DATE') THEN l_merge_sql := l_merge_sql || ', CREATED_DATE'; END IF;
        IF column_exists(l_mappings(i).table_name, 'UPDATED_DATE') THEN l_merge_sql := l_merge_sql || ', UPDATED_DATE'; END IF;

        l_merge_sql := l_merge_sql || ') VALUES (src.SYMBOL';

        IF column_exists(l_mappings(i).table_name, 'COMPANY_NAME') THEN l_merge_sql := l_merge_sql || ', src.COMPANY_NAME'; END IF;
        IF column_exists(l_mappings(i).table_name, 'SECTOR') THEN l_merge_sql := l_merge_sql || ', src.SECTOR'; END IF;
        IF column_exists(l_mappings(i).table_name, 'INDUSTRY') THEN l_merge_sql := l_merge_sql || ', src.INDUSTRY'; END IF;
        IF column_exists(l_mappings(i).table_name, 'SERIES') THEN l_merge_sql := l_merge_sql || ', src.SERIES'; END IF;
        IF column_exists(l_mappings(i).table_name, 'ISIN_CODE') THEN l_merge_sql := l_merge_sql || ', src.ISIN_CODE'; END IF;
        IF column_exists(l_mappings(i).table_name, 'ACTIVE_FLAG') THEN l_merge_sql := l_merge_sql || ', src.ACTIVE_FLAG'; END IF;
        IF column_exists(l_mappings(i).table_name, 'CREATED_DATE') THEN l_merge_sql := l_merge_sql || ', src.CREATED_DATE'; END IF;
        IF column_exists(l_mappings(i).table_name, 'UPDATED_DATE') THEN l_merge_sql := l_merge_sql || ', src.UPDATED_DATE'; END IF;

        l_merge_sql := l_merge_sql || ')';

        EXECUTE IMMEDIATE l_merge_sql
            USING normalize_key(l_mappings(i).source_industry);

        EXECUTE IMMEDIATE l_missing_sql
            INTO l_missing_after
            USING normalize_key(l_mappings(i).source_industry);

        l_inserted := GREATEST(l_missing_before - l_missing_after, 0);
        l_skipped := GREATEST(l_source_total - l_inserted, 0);

        DBMS_OUTPUT.PUT_LINE(
            'Sector=' || l_mappings(i).sector_name ||
            ' | Table=' || l_mappings(i).table_name ||
            ' | SourceDistinct=' || l_source_total ||
            ' | Inserted=' || l_inserted ||
            ' | DuplicatesSkipped=' || l_skipped
        );
    END LOOP;

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        DBMS_OUTPUT.PUT_LINE('Error=' || SQLERRM);
        RAISE;
END;
/

PROMPT Procedure created.
PROMPT Example:
PROMPT SET SERVEROUTPUT ON;
PROMPT EXEC PRC_SYNC_SECTOR_ROTATION_MISSING_SYMBOLS('NSE_TOTAL_MARKET_SECTOR_SOURCE_STG');
