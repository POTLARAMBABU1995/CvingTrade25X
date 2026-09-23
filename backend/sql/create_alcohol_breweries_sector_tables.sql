PROMPT Creating Alcohol Breweries sector staging table and reference mappings
WHENEVER OSERROR EXIT FAILURE ROLLBACK
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK
SET DEFINE OFF;

PROMPT [1/3] Validate source list and cross-sector ownership before any DDL ...

DECLARE
    l_symbol_in_clause      VARCHAR2(4000) := '''ABDL'',''ASALCBR'',''BCLIND'',''COMFINTE'',''GLOBUSSPR'',''GMBREW'',''INDIAGLYCO'',''PICCADIL'',''RADICO'',''RKDL'',''SDBL'',''SULA'',''TI'',''UBL'',''UNITDSPR''';
    l_source_dup_count      NUMBER := 0;
    l_table_conflicts       NUMBER := 0;
    l_sector_map_conflicts  NUMBER := 0;
    l_conflict_symbols      VARCHAR2(4000);
BEGIN
    SELECT COUNT(*)
      INTO l_source_dup_count
      FROM (
        SELECT symbol, COUNT(*) AS dup_count
        FROM (
            SELECT 'ABDL' AS symbol FROM dual UNION ALL
            SELECT 'ASALCBR' FROM dual UNION ALL
            SELECT 'BCLIND' FROM dual UNION ALL
            SELECT 'COMFINTE' FROM dual UNION ALL
            SELECT 'GLOBUSSPR' FROM dual UNION ALL
            SELECT 'GMBREW' FROM dual UNION ALL
            SELECT 'INDIAGLYCO' FROM dual UNION ALL
            SELECT 'PICCADIL' FROM dual UNION ALL
            SELECT 'RADICO' FROM dual UNION ALL
            SELECT 'RKDL' FROM dual UNION ALL
            SELECT 'SDBL' FROM dual UNION ALL
            SELECT 'SULA' FROM dual UNION ALL
            SELECT 'TI' FROM dual UNION ALL
            SELECT 'UBL' FROM dual UNION ALL
            SELECT 'UNITDSPR' FROM dual
        )
        GROUP BY symbol
        HAVING COUNT(*) > 1
      );

    IF l_source_dup_count > 0 THEN
        RAISE_APPLICATION_ERROR(-20060, 'Alcohol Breweries source symbol list contains duplicates. Fix the source list before running this script.');
    END IF;

    FOR r IN (
        SELECT t.table_name
          FROM user_tables t
          JOIN user_tab_columns c
            ON c.table_name = t.table_name
           AND c.column_name = 'SYMBOL'
         WHERE t.table_name LIKE 'NSE_NIFTY%STAGING'
           AND t.table_name NOT IN ('NSE_NIFTY_ALCOHOL_BREWERIES_STAGING', 'NSE_NIFTY_FMCG_STAGING')
         ORDER BY t.table_name
    ) LOOP
        EXECUTE IMMEDIATE
            'SELECT COUNT(*) FROM ' || r.table_name || ' WHERE UPPER(TRIM(symbol)) IN (' || l_symbol_in_clause || ')'
            INTO l_table_conflicts;

        IF l_table_conflicts > 0 THEN
            EXECUTE IMMEDIATE
                'SELECT LISTAGG(symbol, '', '') WITHIN GROUP (ORDER BY symbol) ' ||
                'FROM (SELECT DISTINCT UPPER(TRIM(symbol)) AS symbol ' ||
                '      FROM ' || r.table_name || ' ' ||
                '      WHERE UPPER(TRIM(symbol)) IN (' || l_symbol_in_clause || '))'
                INTO l_conflict_symbols;

            RAISE_APPLICATION_ERROR(
                -20061,
                'Alcohol Breweries symbols already exist in ' || r.table_name || ': ' || SUBSTR(NVL(l_conflict_symbols, 'UNKNOWN'), 1, 3000)
            );
        END IF;
    END LOOP;

    SELECT COUNT(*)
      INTO l_sector_map_conflicts
      FROM NSE_SYMBOL_SECTOR_MAP
     WHERE UPPER(TRIM(SYMBOL)) IN (
        'ABDL', 'ASALCBR', 'BCLIND', 'COMFINTE', 'GLOBUSSPR', 'GMBREW', 'INDIAGLYCO',
        'PICCADIL', 'RADICO', 'RKDL', 'SDBL', 'SULA', 'TI', 'UBL', 'UNITDSPR'
     )
       AND NVL(UPPER(TRIM(SECTOR_CODE)), '~') NOT IN ('~', 'ALCOHOL_BREWERIES');

    IF l_sector_map_conflicts > 0 THEN
        SELECT LISTAGG(symbol || ':' || sector_code, ', ') WITHIN GROUP (ORDER BY symbol)
          INTO l_conflict_symbols
          FROM (
            SELECT DISTINCT UPPER(TRIM(SYMBOL)) AS symbol, UPPER(TRIM(SECTOR_CODE)) AS sector_code
              FROM NSE_SYMBOL_SECTOR_MAP
             WHERE UPPER(TRIM(SYMBOL)) IN (
                'ABDL', 'ASALCBR', 'BCLIND', 'COMFINTE', 'GLOBUSSPR', 'GMBREW', 'INDIAGLYCO',
                'PICCADIL', 'RADICO', 'RKDL', 'SDBL', 'SULA', 'TI', 'UBL', 'UNITDSPR'
             )
               AND NVL(UPPER(TRIM(SECTOR_CODE)), '~') NOT IN ('~', 'ALCOHOL_BREWERIES')
          );

        RAISE_APPLICATION_ERROR(
            -20062,
            'Alcohol Breweries symbols already map to another sector in NSE_SYMBOL_SECTOR_MAP: ' || SUBSTR(NVL(l_conflict_symbols, 'UNKNOWN'), 1, 3000)
        );
    END IF;
END;
/

PROMPT [2/3] Create Alcohol Breweries staging objects only after validation passes ...
DECLARE
    l_count NUMBER := 0;
BEGIN
    SELECT COUNT(*)
      INTO l_count
      FROM user_tables
     WHERE table_name = 'NSE_NIFTY_ALCOHOL_BREWERIES_STAGING';

    IF l_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE TABLE NSE_NIFTY_ALCOHOL_BREWERIES_STAGING AS SELECT * FROM NSE_NIFTY_AUTO_STAGING WHERE 1 = 0';
    END IF;

    SELECT COUNT(*)
      INTO l_count
      FROM user_indexes
     WHERE index_name = 'UK_NIFTY_ALCOBREW_SYM';

    IF l_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE UNIQUE INDEX UK_NIFTY_ALCOBREW_SYM ON NSE_NIFTY_ALCOHOL_BREWERIES_STAGING (SYMBOL)';
    END IF;
END;
/

PROMPT [3/3] Merge Alcohol Breweries staging rows and canonical references ...
MERGE INTO NSE_NIFTY_ALCOHOL_BREWERIES_STAGING tgt
USING (
    SELECT 'ABDL' AS symbol, 'Alcohol / Breweries' AS sector FROM dual UNION ALL
    SELECT 'ASALCBR', 'Alcohol / Breweries' FROM dual UNION ALL
    SELECT 'BCLIND', 'Alcohol / Breweries' FROM dual UNION ALL
    SELECT 'COMFINTE', 'Alcohol / Breweries' FROM dual UNION ALL
    SELECT 'GLOBUSSPR', 'Alcohol / Breweries' FROM dual UNION ALL
    SELECT 'GMBREW', 'Alcohol / Breweries' FROM dual UNION ALL
    SELECT 'INDIAGLYCO', 'Alcohol / Breweries' FROM dual UNION ALL
    SELECT 'PICCADIL', 'Alcohol / Breweries' FROM dual UNION ALL
    SELECT 'RADICO', 'Alcohol / Breweries' FROM dual UNION ALL
    SELECT 'RKDL', 'Alcohol / Breweries' FROM dual UNION ALL
    SELECT 'SDBL', 'Alcohol / Breweries' FROM dual UNION ALL
    SELECT 'SULA', 'Alcohol / Breweries' FROM dual UNION ALL
    SELECT 'TI', 'Alcohol / Breweries' FROM dual UNION ALL
    SELECT 'UBL', 'Alcohol / Breweries' FROM dual UNION ALL
    SELECT 'UNITDSPR', 'Alcohol / Breweries' FROM dual
) src
ON (UPPER(TRIM(tgt.SYMBOL)) = src.symbol)
WHEN MATCHED THEN UPDATE SET
    tgt.SECTOR = src.sector
WHERE NVL(UPPER(TRIM(tgt.SECTOR)), '~') <> UPPER(src.sector)
WHEN NOT MATCHED THEN
    INSERT (SYMBOL, SECTOR)
    VALUES (src.symbol, src.sector);

MERGE INTO NSE_SECTOR_MASTER tgt
USING (
    SELECT
        'ALCOHOL_BREWERIES' AS sector_code,
        'Alcohol Breweries' AS sector_name,
        'NIFTY_ALCOHOL_BREWERIES' AS index_code,
        29 AS display_order
    FROM dual
) src
ON (tgt.sector_code = src.sector_code)
WHEN MATCHED THEN UPDATE SET
    tgt.sector_name = src.sector_name,
    tgt.index_code = src.index_code,
    tgt.display_order = src.display_order
WHEN NOT MATCHED THEN
    INSERT (sector_code, sector_name, index_code, display_order)
    VALUES (src.sector_code, src.sector_name, src.index_code, src.display_order);

MERGE INTO NSE_SYMBOL_SECTOR_MAP tgt
USING (
    SELECT 'ABDL' AS symbol, 'ALCOHOL_BREWERIES' AS sector_code FROM dual UNION ALL
    SELECT 'ASALCBR', 'ALCOHOL_BREWERIES' FROM dual UNION ALL
    SELECT 'BCLIND', 'ALCOHOL_BREWERIES' FROM dual UNION ALL
    SELECT 'COMFINTE', 'ALCOHOL_BREWERIES' FROM dual UNION ALL
    SELECT 'GLOBUSSPR', 'ALCOHOL_BREWERIES' FROM dual UNION ALL
    SELECT 'GMBREW', 'ALCOHOL_BREWERIES' FROM dual UNION ALL
    SELECT 'INDIAGLYCO', 'ALCOHOL_BREWERIES' FROM dual UNION ALL
    SELECT 'PICCADIL', 'ALCOHOL_BREWERIES' FROM dual UNION ALL
    SELECT 'RADICO', 'ALCOHOL_BREWERIES' FROM dual UNION ALL
    SELECT 'RKDL', 'ALCOHOL_BREWERIES' FROM dual UNION ALL
    SELECT 'SDBL', 'ALCOHOL_BREWERIES' FROM dual UNION ALL
    SELECT 'SULA', 'ALCOHOL_BREWERIES' FROM dual UNION ALL
    SELECT 'TI', 'ALCOHOL_BREWERIES' FROM dual UNION ALL
    SELECT 'UBL', 'ALCOHOL_BREWERIES' FROM dual UNION ALL
    SELECT 'UNITDSPR', 'ALCOHOL_BREWERIES' FROM dual
) src
ON (UPPER(TRIM(tgt.SYMBOL)) = src.symbol)
WHEN MATCHED THEN UPDATE SET
    tgt.SECTOR_CODE = src.sector_code
WHERE NVL(UPPER(TRIM(tgt.SECTOR_CODE)), '~') <> src.sector_code
WHEN NOT MATCHED THEN
    INSERT (SYMBOL, SECTOR_CODE)
    VALUES (src.symbol, src.sector_code);

DELETE FROM NSE_NIFTY_FMCG_STAGING
WHERE UPPER(TRIM(SYMBOL)) IN (
    'ABDL', 'INDIAGLYCO', 'PICCADIL', 'RADICO', 'TI', 'UBL', 'UNITDSPR'
);

COMMIT;

PROMPT Alcohol Breweries sector staging table and reference mappings are ready.
