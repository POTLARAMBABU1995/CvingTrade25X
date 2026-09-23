PROMPT Validating Alcohol Breweries sector staging table and reference mappings
SET DEFINE OFF;
SET SERVEROUTPUT ON;

PROMPT [1] Table and index presence
SELECT object_type, object_name
FROM user_objects
WHERE object_name IN (
    'NSE_NIFTY_ALCOHOL_BREWERIES_STAGING',
    'UK_NIFTY_ALCOBREW_SYM'
)
ORDER BY object_type, object_name;

PROMPT [2] Sector master row
SELECT sector_code, sector_name, index_code, display_order
FROM NSE_SECTOR_MASTER
WHERE sector_code = 'ALCOHOL_BREWERIES';

PROMPT [3] Staging row count
DECLARE
    l_exists    NUMBER := 0;
    l_row_count NUMBER := 0;
BEGIN
    SELECT COUNT(*)
      INTO l_exists
      FROM user_tables
     WHERE table_name = 'NSE_NIFTY_ALCOHOL_BREWERIES_STAGING';

    IF l_exists = 0 THEN
        DBMS_OUTPUT.PUT_LINE('MISSING table=NSE_NIFTY_ALCOHOL_BREWERIES_STAGING');
        RETURN;
    END IF;

    EXECUTE IMMEDIATE 'SELECT COUNT(*) FROM NSE_NIFTY_ALCOHOL_BREWERIES_STAGING'
        INTO l_row_count;
    DBMS_OUTPUT.PUT_LINE('ROW_COUNT table=NSE_NIFTY_ALCOHOL_BREWERIES_STAGING count=' || l_row_count);
END;
/

PROMPT [4] Staging rows
DECLARE
    l_exists NUMBER := 0;
    TYPE t_ref_cur IS REF CURSOR;
    l_cur    t_ref_cur;
    l_symbol VARCHAR2(4000);
    l_sector VARCHAR2(4000);
BEGIN
    SELECT COUNT(*)
      INTO l_exists
      FROM user_tables
     WHERE table_name = 'NSE_NIFTY_ALCOHOL_BREWERIES_STAGING';

    IF l_exists = 0 THEN
        DBMS_OUTPUT.PUT_LINE('SKIP staging rows because NSE_NIFTY_ALCOHOL_BREWERIES_STAGING does not exist');
        RETURN;
    END IF;

    OPEN l_cur FOR '
        SELECT UPPER(TRIM(SYMBOL)) AS symbol, SECTOR
        FROM NSE_NIFTY_ALCOHOL_BREWERIES_STAGING
        ORDER BY UPPER(TRIM(SYMBOL))
    ';

    LOOP
        FETCH l_cur INTO l_symbol, l_sector;
        EXIT WHEN l_cur%NOTFOUND;
        DBMS_OUTPUT.PUT_LINE('ROW symbol=' || NVL(l_symbol, '-') || ' sector=' || NVL(l_sector, '-'));
    END LOOP;

    CLOSE l_cur;
END;
/

PROMPT [5] Duplicate symbol check within Alcohol Breweries staging
DECLARE
    l_exists NUMBER := 0;
    TYPE t_ref_cur IS REF CURSOR;
    l_cur    t_ref_cur;
    l_symbol VARCHAR2(4000);
    l_count  NUMBER := 0;
BEGIN
    SELECT COUNT(*)
      INTO l_exists
      FROM user_tables
     WHERE table_name = 'NSE_NIFTY_ALCOHOL_BREWERIES_STAGING';

    IF l_exists = 0 THEN
        DBMS_OUTPUT.PUT_LINE('SKIP duplicate check because NSE_NIFTY_ALCOHOL_BREWERIES_STAGING does not exist');
        RETURN;
    END IF;

    OPEN l_cur FOR '
        SELECT UPPER(TRIM(SYMBOL)) AS symbol, COUNT(*) AS duplicate_count
        FROM NSE_NIFTY_ALCOHOL_BREWERIES_STAGING
        GROUP BY UPPER(TRIM(SYMBOL))
        HAVING COUNT(*) > 1
        ORDER BY UPPER(TRIM(SYMBOL))
    ';

    LOOP
        FETCH l_cur INTO l_symbol, l_count;
        EXIT WHEN l_cur%NOTFOUND;
        DBMS_OUTPUT.PUT_LINE('DUPLICATE symbol=' || NVL(l_symbol, '-') || ' count=' || l_count);
    END LOOP;

    CLOSE l_cur;
END;
/

PROMPT [6] Sector map rows
SELECT UPPER(TRIM(SYMBOL)) AS symbol, UPPER(TRIM(SECTOR_CODE)) AS sector_code
FROM NSE_SYMBOL_SECTOR_MAP
WHERE UPPER(TRIM(SYMBOL)) IN (
    'ABDL', 'ALCODIS', 'ASALCBR', 'BCLIND', 'COMFINTE', 'GLOBUSSPR', 'GMBREW', 'IFBAGRO', 'INDIAGLYCO',
    'JAGAJITIND', 'PICCADIL', 'RADICO', 'RKDL', 'SDBL', 'SULA', 'TI', 'UBL', 'UNITDSPR'
)
ORDER BY UPPER(TRIM(SYMBOL));

PROMPT [7] Existing staging-table ownership conflicts for the Alcohol Breweries symbols
DECLARE
    l_symbol_in_clause VARCHAR2(4000) := '''ABDL'',''ALCODIS'',''ASALCBR'',''BCLIND'',''COMFINTE'',''GLOBUSSPR'',''GMBREW'',''IFBAGRO'',''INDIAGLYCO'',''JAGAJITIND'',''PICCADIL'',''RADICO'',''RKDL'',''SDBL'',''SULA'',''TI'',''UBL'',''UNITDSPR''';
    l_match_count      NUMBER := 0;
    l_symbols          VARCHAR2(4000);
BEGIN
    FOR r IN (
        SELECT t.table_name
          FROM user_tables t
          JOIN user_tab_columns c
            ON c.table_name = t.table_name
           AND c.column_name = 'SYMBOL'
         WHERE t.table_name LIKE 'NSE_NIFTY%STAGING'
           AND t.table_name <> 'NSE_NIFTY_ALCOHOL_BREWERIES_STAGING'
         ORDER BY t.table_name
    ) LOOP
        EXECUTE IMMEDIATE
            'SELECT COUNT(*) FROM ' || r.table_name || ' WHERE UPPER(TRIM(symbol)) IN (' || l_symbol_in_clause || ')'
            INTO l_match_count;

        IF l_match_count > 0 THEN
            EXECUTE IMMEDIATE
                'SELECT LISTAGG(symbol, '', '') WITHIN GROUP (ORDER BY symbol) ' ||
                'FROM (SELECT DISTINCT UPPER(TRIM(symbol)) AS symbol ' ||
                '      FROM ' || r.table_name || ' ' ||
                '      WHERE UPPER(TRIM(symbol)) IN (' || l_symbol_in_clause || '))'
                INTO l_symbols;
            DBMS_OUTPUT.PUT_LINE('CONFLICT table=' || r.table_name || ' symbols=' || NVL(l_symbols, '-'));
        END IF;
    END LOOP;
END;
/

PROMPT [8] Existing NSE_SYMBOL_SECTOR_MAP conflicts for the Alcohol Breweries symbols
SELECT UPPER(TRIM(SYMBOL)) AS symbol,
       UPPER(TRIM(SECTOR_CODE)) AS sector_code
FROM NSE_SYMBOL_SECTOR_MAP
WHERE UPPER(TRIM(SYMBOL)) IN (
    'ABDL', 'ALCODIS', 'ASALCBR', 'BCLIND', 'COMFINTE', 'GLOBUSSPR', 'GMBREW', 'IFBAGRO', 'INDIAGLYCO',
    'JAGAJITIND', 'PICCADIL', 'RADICO', 'RKDL', 'SDBL', 'SULA', 'TI', 'UBL', 'UNITDSPR'
)
  AND NVL(UPPER(TRIM(SECTOR_CODE)), '~') NOT IN ('~', 'ALCOHOL_BREWERIES')
ORDER BY UPPER(TRIM(SYMBOL));

PROMPT [9] Global duplicate symbol scan across all canonical sector staging sources
DECLARE
    l_exists NUMBER := 0;
    l_status VARCHAR2(30) := NULL;
    TYPE t_ref_cur IS REF CURSOR;
    l_cur    t_ref_cur;
    l_symbol VARCHAR2(4000);
    l_source_table_count NUMBER := 0;
    l_source_tables VARCHAR2(4000);
BEGIN
    SELECT COUNT(*), MAX(status)
      INTO l_exists, l_status
      FROM user_objects
     WHERE object_name = 'VW_NSE_CANONICAL_SECTOR_STAGE'
       AND object_type = 'VIEW';

    IF l_exists = 0 THEN
        DBMS_OUTPUT.PUT_LINE('MISSING view=VW_NSE_CANONICAL_SECTOR_STAGE');
        RETURN;
    END IF;

    IF NVL(l_status, 'INVALID') <> 'VALID' THEN
        DBMS_OUTPUT.PUT_LINE('INVALID view=VW_NSE_CANONICAL_SECTOR_STAGE status=' || NVL(l_status, 'UNKNOWN'));
        RETURN;
    END IF;

    OPEN l_cur FOR '
        SELECT symbol,
               COUNT(DISTINCT source_table) AS source_table_count,
               LISTAGG(source_table, '', '') WITHIN GROUP (ORDER BY source_table) AS source_tables
        FROM VW_NSE_CANONICAL_SECTOR_STAGE
        GROUP BY symbol
        HAVING COUNT(DISTINCT source_table) > 1
        ORDER BY symbol
    ';

    LOOP
        FETCH l_cur INTO l_symbol, l_source_table_count, l_source_tables;
        EXIT WHEN l_cur%NOTFOUND;
        DBMS_OUTPUT.PUT_LINE(
            'CANONICAL_DUPLICATE symbol=' || NVL(l_symbol, '-')
            || ' source_table_count=' || l_source_table_count
            || ' source_tables=' || NVL(l_source_tables, '-')
        );
    END LOOP;

    CLOSE l_cur;
END;
/
