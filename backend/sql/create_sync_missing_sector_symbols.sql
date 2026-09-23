PROMPT Creating procedure PRC_SYNC_MISSING_SECTOR_SYMBOLS (missing tables + missing symbols only)
SET DEFINE OFF;

CREATE OR REPLACE NONEDITIONABLE PROCEDURE PRC_SYNC_MISSING_SECTOR_SYMBOLS (
    p_source_table IN VARCHAR2 DEFAULT NULL
) AS
    TYPE t_sector_map_rec IS RECORD (
        industry_name VARCHAR2(150),
        sector_name   VARCHAR2(150),
        table_name    VARCHAR2(128),
        index_name    VARCHAR2(30)
    );
    TYPE t_sector_map_tab IS TABLE OF t_sector_map_rec;

    l_mappings t_sector_map_tab := t_sector_map_tab(
        t_sector_map_rec('Automobile and Auto Components', 'Automobile and Auto Components', 'NSE_NIFTY_AUTO_STAGING', 'UK_NIFTY_AUTO_STG_SYM'),
        t_sector_map_rec('Capital Goods', 'Capital Goods', 'NSE_NIFTY_CAPITAL_GOODS_STAGING', 'UK_NIFTY_CAP_GOODS_SYM'),
        t_sector_map_rec('Chemicals', 'Chemicals', 'NSE_NIFTY_CHEMICALS_STAGING', 'UK_NIFTY_CHEM_STG_SYM'),
        t_sector_map_rec('Construction', 'Construction', 'NSE_NIFTY_CONSTRUCTION_STAGING', 'UK_NIFTY_CONST_STG_SYM'),
        t_sector_map_rec('Construction Materials', 'Construction Materials', 'NSE_NIFTY_CONSTRUCTION_MATERIALS_STAGING', 'UK_NIFTY_CONMAT_SYM'),
        t_sector_map_rec('Consumer Durables', 'Consumer Durables', 'NSE_NIFTY_CONSUMER_DURABLES_STAGING', 'UK_NIFTY_CONDUR_SYM'),
        t_sector_map_rec('Consumer Services', 'Consumer Services', 'NSE_NIFTY_CONSUMER_SERVICES_STAGING', 'UK_NIFTY_CONSRV_SYM'),
        t_sector_map_rec('Diversified', 'Diversified', 'NSE_NIFTY_DIVERSIFIED_STAGING', 'UK_NIFTY_DIVER_STG_SYM'),
        t_sector_map_rec('Fast Moving Consumer Goods', 'Fast Moving Consumer Goods', 'NSE_NIFTY_FMCG_STAGING', 'UK_NIFTY_FMCG_STG_SYM'),
        t_sector_map_rec('Financial Services', 'Financial Services', 'NSE_NIFTY_FINANCIAL_SERVICES_25_50_STAGING', 'UK_NIFTY_FIN2550_SYM'),
        t_sector_map_rec('Forest Materials', 'Forest Materials', 'NSE_NIFTY_FOREST_MATERIALS_STAGING', 'UK_NIFTY_FORMAT_SYM'),
        t_sector_map_rec('Healthcare', 'Healthcare', 'NSE_NIFTY_HEALTHCARE_INDEX_STAGING', 'UK_NIFTY_HEALTH_STG'),
        t_sector_map_rec('Information Technology', 'Information Technology', 'NSE_NIFTY_IT_STAGING', 'UK_NIFTY_IT_STG_SYM'),
        t_sector_map_rec('Media Entertainment & Publication', 'Media Entertainment & Publication', 'NSE_NIFTY_MEDIA_STAGING', 'UK_NIFTY_MEDIA_STG_SYM'),
        t_sector_map_rec('Metals & Mining', 'Metals & Mining', 'NSE_NIFTY_METAL_STAGING', 'UK_NIFTY_METAL_STG_SYM'),
        t_sector_map_rec('Oil Gas & Consumable Fuels', 'Oil Gas & Consumable Fuels', 'NSE_NIFTY_OIL_AND_GAS_STAGING', 'UK_NIFTY_OILGAS_SYM'),
        t_sector_map_rec('Power', 'Power', 'NSE_NIFTY_POWER_STAGING', 'UK_NIFTY_POWER_STG_SYM'),
        t_sector_map_rec('Realty', 'Realty', 'NSE_NIFTY_REALITY_STAGING', 'UK_NIFTY_REALITY_SYM'),
        t_sector_map_rec('Services', 'Services', 'NSE_NIFTY_SERVICES_STAGING', 'UK_NIFTY_SERVICE_SYM'),
        t_sector_map_rec('Telecommunication', 'Telecommunication', 'NSE_NIFTY_TELECOMMUNICATION_STAGING', 'UK_NIFTY_TELECOM_SYM'),
        t_sector_map_rec('Textiles', 'Textiles', 'NSE_NIFTY_TEXTILES_STAGING', 'UK_NIFTY_TEXTILE_SYM'),
        t_sector_map_rec('Utilities', 'Utilities', 'NSE_NIFTY_UTILITIES_STAGING', 'UK_NIFTY_UTIL_STG_SYM')
    );

    l_source_table        VARCHAR2(128);
    l_symbol_col          VARCHAR2(128);
    l_company_name_col    VARCHAR2(128);
    l_filter_col          VARCHAR2(128);
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

    FUNCTION normalize_sector_key(p_value IN VARCHAR2) RETURN VARCHAR2 IS
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

    FUNCTION get_col_if_exists(p_table_name IN VARCHAR2, p_col_name IN VARCHAR2) RETURN VARCHAR2 IS
        l_cnt NUMBER;
    BEGIN
        SELECT COUNT(*)
          INTO l_cnt
          FROM USER_TAB_COLUMNS
         WHERE TABLE_NAME = UPPER(TRIM(p_table_name))
           AND COLUMN_NAME = UPPER(TRIM(p_col_name));
        IF l_cnt > 0 THEN
            RETURN UPPER(TRIM(p_col_name));
        END IF;
        RETURN NULL;
    END;

    FUNCTION choose_source_col(p_table_name IN VARCHAR2, p_candidates IN SYS.ODCIVARCHAR2LIST) RETURN VARCHAR2 IS
        l_col VARCHAR2(128);
    BEGIN
        FOR i IN 1 .. p_candidates.COUNT LOOP
            l_col := get_col_if_exists(p_table_name, p_candidates(i));
            IF l_col IS NOT NULL THEN
                RETURN l_col;
            END IF;
        END LOOP;
        RETURN NULL;
    END;

    PROCEDURE ensure_new_table_if_missing(p_table_name IN VARCHAR2, p_index_name IN VARCHAR2) IS
    BEGIN
        IF NOT table_exists(p_table_name) THEN
            EXECUTE IMMEDIATE
                'CREATE TABLE ' || p_table_name || ' (' ||
                'SYMBOL VARCHAR2(50) NOT NULL,' ||
                'COMPANY_NAME VARCHAR2(300),' ||
                'SECTOR VARCHAR2(150),' ||
                'INDUSTRY VARCHAR2(150),' ||
                'SERIES VARCHAR2(20),' ||
                'ISIN_CODE VARCHAR2(50),' ||
                'ACTIVE_FLAG CHAR(1) DEFAULT ''Y'',' ||
                'CREATED_DATE DATE DEFAULT SYSDATE,' ||
                'UPDATED_DATE DATE' ||
                ')';

            BEGIN
                EXECUTE IMMEDIATE 'CREATE UNIQUE INDEX ' || p_index_name || ' ON ' || p_table_name || '(SYMBOL)';
            EXCEPTION
                WHEN OTHERS THEN
                    IF SQLCODE != -955 THEN
                        RAISE;
                    END IF;
            END;

            DBMS_OUTPUT.PUT_LINE('Created missing sector table: ' || p_table_name);
        END IF;
    END;

    FUNCTION build_source_subquery(
        p_sector_name IN VARCHAR2,
        p_industry_name IN VARCHAR2
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

        IF l_industry_col IS NOT NULL THEN
            l_sql := l_sql || ', TRIM(s.' || l_industry_col || ') AS INDUSTRY';
        ELSE
            l_sql := l_sql || ', CAST(NULL AS VARCHAR2(150)) AS INDUSTRY';
        END IF;

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
                 'AND UPPER(REGEXP_REPLACE(REPLACE(REPLACE(TRIM(s.' || l_filter_col || '), ''&'', '' AND ''), ''-'', '' ''), ''[[:space:]]+'', '' '')) = :industry_key';

        RETURN l_sql;
    END;

BEGIN
    l_source_table := UPPER(TRIM(p_source_table));

    IF l_source_table IS NULL THEN
        IF table_exists('NSE_TOTAL_MARKET_SECTOR_SOURCE_STG') THEN
            l_source_table := 'NSE_TOTAL_MARKET_SECTOR_SOURCE_STG';
        ELSIF table_exists('NSE_TOTAL_MARKET_SECTOR_STG') THEN
            l_source_table := 'NSE_TOTAL_MARKET_SECTOR_STG';
        ELSE
            RAISE_APPLICATION_ERROR(-20001, 'Source table not found. Provide p_source_table or create NSE_TOTAL_MARKET_SECTOR_SOURCE_STG.');
        END IF;
    END IF;

    IF NOT is_safe_sql_name(l_source_table) OR NOT table_exists(l_source_table) THEN
        RAISE_APPLICATION_ERROR(-20002, 'Invalid source table: ' || NVL(l_source_table, 'NULL'));
    END IF;

    l_symbol_col       := choose_source_col(l_source_table, SYS.ODCIVARCHAR2LIST('SYMBOL'));
    l_company_name_col := choose_source_col(l_source_table, SYS.ODCIVARCHAR2LIST('COMPANY_NAME', 'COMPANY'));
    l_industry_col     := choose_source_col(l_source_table, SYS.ODCIVARCHAR2LIST('INDUSTRY'));
    l_series_col       := choose_source_col(l_source_table, SYS.ODCIVARCHAR2LIST('SERIES'));
    l_isin_col         := choose_source_col(l_source_table, SYS.ODCIVARCHAR2LIST('ISIN_CODE', 'ISIN'));

    IF l_symbol_col IS NULL THEN
        RAISE_APPLICATION_ERROR(-20003, 'Source table must contain SYMBOL column.');
    END IF;

    l_filter_col := CASE WHEN l_industry_col IS NOT NULL THEN l_industry_col
                         ELSE choose_source_col(l_source_table, SYS.ODCIVARCHAR2LIST('SECTOR')) END;

    IF l_filter_col IS NULL THEN
        RAISE_APPLICATION_ERROR(-20004, 'Source table must contain INDUSTRY or SECTOR column for sector mapping.');
    END IF;

    DBMS_OUTPUT.PUT_LINE('Using source table: ' || l_source_table);

    FOR i IN 1 .. l_mappings.COUNT LOOP
        IF NOT is_safe_sql_name(l_mappings(i).table_name) THEN
            RAISE_APPLICATION_ERROR(-20005, 'Unsafe target table name in mapping: ' || l_mappings(i).table_name);
        END IF;

        ensure_new_table_if_missing(l_mappings(i).table_name, l_mappings(i).index_name);

        l_source_count_sql :=
            'SELECT COUNT(*) FROM (' ||
            'SELECT DISTINCT UPPER(TRIM(s.' || l_symbol_col || ')) AS SYMBOL ' ||
            'FROM ' || l_source_table || ' s ' ||
            'WHERE s.' || l_symbol_col || ' IS NOT NULL ' ||
            'AND TRIM(s.' || l_symbol_col || ') IS NOT NULL ' ||
            'AND UPPER(REGEXP_REPLACE(REPLACE(REPLACE(TRIM(s.' || l_filter_col || '), ''&'', '' AND ''), ''-'', '' ''), ''[[:space:]]+'', '' '')) = :industry_key)';

        EXECUTE IMMEDIATE l_source_count_sql
            INTO l_source_total
            USING normalize_sector_key(l_mappings(i).industry_name);

        l_missing_sql :=
            'SELECT COUNT(*) FROM (' ||
            'SELECT src.SYMBOL FROM (' || build_source_subquery(l_mappings(i).sector_name, l_mappings(i).industry_name) || ') src ' ||
            'WHERE NOT EXISTS (' ||
            'SELECT 1 FROM ' || l_mappings(i).table_name || ' t ' ||
            'WHERE UPPER(TRIM(t.SYMBOL)) = src.SYMBOL))';

        EXECUTE IMMEDIATE l_missing_sql
            INTO l_missing_before
            USING normalize_sector_key(l_mappings(i).industry_name);

        l_merge_sql :=
            'MERGE INTO ' || l_mappings(i).table_name || ' t ' ||
            'USING (' || build_source_subquery(l_mappings(i).sector_name, l_mappings(i).industry_name) || ') src ' ||
            'ON (UPPER(TRIM(t.SYMBOL)) = src.SYMBOL) ' ||
            'WHEN NOT MATCHED THEN INSERT (SYMBOL';

        IF get_col_if_exists(l_mappings(i).table_name, 'COMPANY_NAME') IS NOT NULL THEN
            l_merge_sql := l_merge_sql || ', COMPANY_NAME';
        END IF;
        IF get_col_if_exists(l_mappings(i).table_name, 'SECTOR') IS NOT NULL THEN
            l_merge_sql := l_merge_sql || ', SECTOR';
        END IF;
        IF get_col_if_exists(l_mappings(i).table_name, 'INDUSTRY') IS NOT NULL THEN
            l_merge_sql := l_merge_sql || ', INDUSTRY';
        END IF;
        IF get_col_if_exists(l_mappings(i).table_name, 'SERIES') IS NOT NULL THEN
            l_merge_sql := l_merge_sql || ', SERIES';
        END IF;
        IF get_col_if_exists(l_mappings(i).table_name, 'ISIN_CODE') IS NOT NULL THEN
            l_merge_sql := l_merge_sql || ', ISIN_CODE';
        END IF;
        IF get_col_if_exists(l_mappings(i).table_name, 'ACTIVE_FLAG') IS NOT NULL THEN
            l_merge_sql := l_merge_sql || ', ACTIVE_FLAG';
        END IF;
        IF get_col_if_exists(l_mappings(i).table_name, 'CREATED_DATE') IS NOT NULL THEN
            l_merge_sql := l_merge_sql || ', CREATED_DATE';
        END IF;
        IF get_col_if_exists(l_mappings(i).table_name, 'UPDATED_DATE') IS NOT NULL THEN
            l_merge_sql := l_merge_sql || ', UPDATED_DATE';
        END IF;

        l_merge_sql := l_merge_sql || ') VALUES (src.SYMBOL';

        IF get_col_if_exists(l_mappings(i).table_name, 'COMPANY_NAME') IS NOT NULL THEN
            l_merge_sql := l_merge_sql || ', src.COMPANY_NAME';
        END IF;
        IF get_col_if_exists(l_mappings(i).table_name, 'SECTOR') IS NOT NULL THEN
            l_merge_sql := l_merge_sql || ', src.SECTOR';
        END IF;
        IF get_col_if_exists(l_mappings(i).table_name, 'INDUSTRY') IS NOT NULL THEN
            l_merge_sql := l_merge_sql || ', src.INDUSTRY';
        END IF;
        IF get_col_if_exists(l_mappings(i).table_name, 'SERIES') IS NOT NULL THEN
            l_merge_sql := l_merge_sql || ', src.SERIES';
        END IF;
        IF get_col_if_exists(l_mappings(i).table_name, 'ISIN_CODE') IS NOT NULL THEN
            l_merge_sql := l_merge_sql || ', src.ISIN_CODE';
        END IF;
        IF get_col_if_exists(l_mappings(i).table_name, 'ACTIVE_FLAG') IS NOT NULL THEN
            l_merge_sql := l_merge_sql || ', src.ACTIVE_FLAG';
        END IF;
        IF get_col_if_exists(l_mappings(i).table_name, 'CREATED_DATE') IS NOT NULL THEN
            l_merge_sql := l_merge_sql || ', src.CREATED_DATE';
        END IF;
        IF get_col_if_exists(l_mappings(i).table_name, 'UPDATED_DATE') IS NOT NULL THEN
            l_merge_sql := l_merge_sql || ', src.UPDATED_DATE';
        END IF;

        l_merge_sql := l_merge_sql || ')';

        EXECUTE IMMEDIATE l_merge_sql
            USING normalize_sector_key(l_mappings(i).industry_name);

        EXECUTE IMMEDIATE l_missing_sql
            INTO l_missing_after
            USING normalize_sector_key(l_mappings(i).industry_name);

        l_inserted := GREATEST(l_missing_before - l_missing_after, 0);
        l_skipped := GREATEST(l_source_total - l_inserted, 0);

        DBMS_OUTPUT.PUT_LINE(
            'Sector=' || l_mappings(i).sector_name ||
            ' | Table=' || l_mappings(i).table_name ||
            ' | SourceDistinct=' || l_source_total ||
            ' | Inserted=' || l_inserted ||
            ' | Skipped=' || l_skipped
        );
    END LOOP;

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/

PROMPT Procedure created. Example run:
PROMPT EXEC PRC_SYNC_MISSING_SECTOR_SYMBOLS;
PROMPT EXEC PRC_SYNC_MISSING_SECTOR_SYMBOLS('NSE_TOTAL_MARKET_SECTOR_SOURCE_STG');
