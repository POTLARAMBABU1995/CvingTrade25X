PROMPT Creating Auto Ancillaries sector staging table and Auto Mobile display rename
WHENEVER OSERROR EXIT FAILURE ROLLBACK
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK
SET DEFINE OFF;

PROMPT [1/4] Validate source lists and cross-sector ownership before any DML ...

DECLARE
    l_anc_symbol_in_clause  VARCHAR2(4000) := '''APOLLOTYRE'',''ARE&M'',''ASAHIINDIA'',''ASKAUTOLTD'',''BALKRISIND'',''BANCOINDIA'',''BHARATFORG'',''BOSCHLTD'',''CEATLTD'',''CIEINDIA'',''CRAFTSMAN'',''ENDURANCE'',''EXIDEIND'',''FIEMIND'',''GABRIEL'',''HBLENGINE'',''JAMNAAUTO'',''JBMA'',''JKTYRE'',''JTEKTINDIA'',''LUMAXIND'',''LUMAXTECH'',''MINDACORP'',''MOTHERSON'',''MRF'',''MSUMI'',''PRICOLLTD'',''RKFORGE'',''SANDHAR'',''SCHAEFFLER'',''SONACOMS'',''SUBROS'',''SUNDRMFAST'',''SUPRAJIT'',''TALBROAUTO'',''TIINDIA'',''UNOMINDA'',''VARROC'',''ZFCVINDIA''';
    l_source_dup_count     NUMBER := 0;
    l_table_conflicts      NUMBER := 0;
    l_sector_map_conflicts NUMBER := 0;
    l_conflict_symbols     VARCHAR2(4000);
BEGIN
    SELECT COUNT(*)
      INTO l_source_dup_count
      FROM (
        SELECT symbol, COUNT(*) AS dup_count
        FROM (
            SELECT 'APOLLOTYRE' AS symbol FROM dual UNION ALL
            SELECT 'ARE&M' FROM dual UNION ALL
            SELECT 'ASAHIINDIA' FROM dual UNION ALL
            SELECT 'ASKAUTOLTD' FROM dual UNION ALL
            SELECT 'BALKRISIND' FROM dual UNION ALL
            SELECT 'BANCOINDIA' FROM dual UNION ALL
            SELECT 'BHARATFORG' FROM dual UNION ALL
            SELECT 'BOSCHLTD' FROM dual UNION ALL
            SELECT 'CEATLTD' FROM dual UNION ALL
            SELECT 'CIEINDIA' FROM dual UNION ALL
            SELECT 'CRAFTSMAN' FROM dual UNION ALL
            SELECT 'ENDURANCE' FROM dual UNION ALL
            SELECT 'EXIDEIND' FROM dual UNION ALL
            SELECT 'FIEMIND' FROM dual UNION ALL
            SELECT 'GABRIEL' FROM dual UNION ALL
            SELECT 'HBLENGINE' FROM dual UNION ALL
            SELECT 'JAMNAAUTO' FROM dual UNION ALL
            SELECT 'JBMA' FROM dual UNION ALL
            SELECT 'JKTYRE' FROM dual UNION ALL
            SELECT 'JTEKTINDIA' FROM dual UNION ALL
            SELECT 'LUMAXIND' FROM dual UNION ALL
            SELECT 'LUMAXTECH' FROM dual UNION ALL
            SELECT 'MINDACORP' FROM dual UNION ALL
            SELECT 'MOTHERSON' FROM dual UNION ALL
            SELECT 'MRF' FROM dual UNION ALL
            SELECT 'MSUMI' FROM dual UNION ALL
            SELECT 'PRICOLLTD' FROM dual UNION ALL
            SELECT 'RKFORGE' FROM dual UNION ALL
            SELECT 'SANDHAR' FROM dual UNION ALL
            SELECT 'SCHAEFFLER' FROM dual UNION ALL
            SELECT 'SONACOMS' FROM dual UNION ALL
            SELECT 'SUBROS' FROM dual UNION ALL
            SELECT 'SUNDRMFAST' FROM dual UNION ALL
            SELECT 'SUPRAJIT' FROM dual UNION ALL
            SELECT 'TALBROAUTO' FROM dual UNION ALL
            SELECT 'TIINDIA' FROM dual UNION ALL
            SELECT 'UNOMINDA' FROM dual UNION ALL
            SELECT 'VARROC' FROM dual UNION ALL
            SELECT 'ZFCVINDIA' FROM dual
        )
        GROUP BY symbol
        HAVING COUNT(*) > 1
      );

    IF l_source_dup_count > 0 THEN
        RAISE_APPLICATION_ERROR(-20070, 'Auto Ancillaries source symbol list contains duplicates. Fix the source list before running this script.');
    END IF;

    FOR r IN (
        SELECT t.table_name
          FROM user_tables t
          JOIN user_tab_columns c
            ON c.table_name = t.table_name
           AND c.column_name = 'SYMBOL'
         WHERE t.table_name LIKE 'NSE_NIFTY%STAGING'
           AND t.table_name NOT IN ('NSE_NIFTY_AUTO_STAGING', 'NSE_NIFTY_AUTO_ANCILLARIES_STAGING', 'NSE_NIFTY_CAPITAL_GOODS_STAGING')
         ORDER BY t.table_name
    ) LOOP
        EXECUTE IMMEDIATE
            'SELECT COUNT(*) FROM ' || r.table_name || ' WHERE UPPER(TRIM(symbol)) IN (' || l_anc_symbol_in_clause || ')'
            INTO l_table_conflicts;

        IF l_table_conflicts > 0 THEN
            EXECUTE IMMEDIATE
                'SELECT LISTAGG(symbol, '', '') WITHIN GROUP (ORDER BY symbol) ' ||
                'FROM (SELECT DISTINCT UPPER(TRIM(symbol)) AS symbol ' ||
                '      FROM ' || r.table_name || ' ' ||
                '      WHERE UPPER(TRIM(symbol)) IN (' || l_anc_symbol_in_clause || '))'
                INTO l_conflict_symbols;

            RAISE_APPLICATION_ERROR(
                -20071,
                'Auto Ancillaries symbols already exist in ' || r.table_name || ': ' || SUBSTR(NVL(l_conflict_symbols, 'UNKNOWN'), 1, 3000)
            );
        END IF;
    END LOOP;

    SELECT COUNT(*)
      INTO l_sector_map_conflicts
      FROM NSE_SYMBOL_SECTOR_MAP
     WHERE UPPER(TRIM(SYMBOL)) IN (
        'APOLLOTYRE', 'ARE&M', 'ASAHIINDIA', 'ASKAUTOLTD', 'BALKRISIND', 'BANCOINDIA', 'BHARATFORG', 'BOSCHLTD',
        'CEATLTD', 'CIEINDIA', 'CRAFTSMAN', 'ENDURANCE', 'EXIDEIND', 'FIEMIND', 'GABRIEL', 'HBLENGINE', 'JAMNAAUTO',
        'JBMA', 'JKTYRE', 'JTEKTINDIA', 'LUMAXIND', 'LUMAXTECH', 'MINDACORP', 'MOTHERSON', 'MRF', 'MSUMI',
        'PRICOLLTD', 'RKFORGE', 'SANDHAR', 'SCHAEFFLER', 'SONACOMS', 'SUBROS', 'SUNDRMFAST', 'SUPRAJIT',
        'TALBROAUTO', 'TIINDIA', 'UNOMINDA', 'VARROC', 'ZFCVINDIA'
     )
       AND NVL(UPPER(TRIM(SECTOR_CODE)), '~') NOT IN ('~', 'AUTO', 'AUTO_ANCILLARIES', 'CAPITAL_GOODS');

    IF l_sector_map_conflicts > 0 THEN
        SELECT LISTAGG(symbol || ':' || sector_code, ', ') WITHIN GROUP (ORDER BY symbol)
          INTO l_conflict_symbols
          FROM (
            SELECT DISTINCT UPPER(TRIM(SYMBOL)) AS symbol, UPPER(TRIM(SECTOR_CODE)) AS sector_code
              FROM NSE_SYMBOL_SECTOR_MAP
             WHERE UPPER(TRIM(SYMBOL)) IN (
                'APOLLOTYRE', 'ARE&M', 'ASAHIINDIA', 'ASKAUTOLTD', 'BALKRISIND', 'BANCOINDIA', 'BHARATFORG', 'BOSCHLTD',
                'CEATLTD', 'CIEINDIA', 'CRAFTSMAN', 'ENDURANCE', 'EXIDEIND', 'FIEMIND', 'GABRIEL', 'HBLENGINE', 'JAMNAAUTO',
                'JBMA', 'JKTYRE', 'JTEKTINDIA', 'LUMAXIND', 'LUMAXTECH', 'MINDACORP', 'MOTHERSON', 'MRF', 'MSUMI',
                'PRICOLLTD', 'RKFORGE', 'SANDHAR', 'SCHAEFFLER', 'SONACOMS', 'SUBROS', 'SUNDRMFAST', 'SUPRAJIT',
                'TALBROAUTO', 'TIINDIA', 'UNOMINDA', 'VARROC', 'ZFCVINDIA'
             )
               AND NVL(UPPER(TRIM(SECTOR_CODE)), '~') NOT IN ('~', 'AUTO', 'AUTO_ANCILLARIES', 'CAPITAL_GOODS')
          );

        RAISE_APPLICATION_ERROR(
            -20072,
            'Auto Ancillaries symbols already map to another sector in NSE_SYMBOL_SECTOR_MAP: ' || SUBSTR(NVL(l_conflict_symbols, 'UNKNOWN'), 1, 3000)
        );
    END IF;
END;
/

PROMPT [2/4] Create Auto Ancillaries staging objects only after validation passes ...
DECLARE
    l_count NUMBER := 0;
BEGIN
    SELECT COUNT(*)
      INTO l_count
      FROM user_tables
     WHERE table_name = 'NSE_NIFTY_AUTO_ANCILLARIES_STAGING';

    IF l_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE TABLE NSE_NIFTY_AUTO_ANCILLARIES_STAGING AS SELECT * FROM NSE_NIFTY_AUTO_STAGING WHERE 1 = 0';
    END IF;

    SELECT COUNT(*)
      INTO l_count
      FROM user_indexes
     WHERE index_name = 'UK_NIFTY_AUTO_ANC_SYM';

    IF l_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE UNIQUE INDEX UK_NIFTY_AUTO_ANC_SYM ON NSE_NIFTY_AUTO_ANCILLARIES_STAGING (SYMBOL)';
    END IF;
END;
/

PROMPT [3/4] Rename existing Auto sector display to Auto Mobile ...
MERGE INTO NSE_SECTOR_MASTER tgt
USING (
    SELECT
        'AUTO' AS sector_code,
        'Auto Mobile' AS sector_name,
        'NIFTY_AUTO' AS index_code,
        10 AS display_order
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

MERGE INTO NSE_NIFTY_AUTO_STAGING tgt
USING (
    SELECT 'ASHOKLEY' AS symbol, 'Auto Mobile' AS sector FROM dual UNION ALL
    SELECT 'ATHERENERG', 'Auto Mobile' FROM dual UNION ALL
    SELECT 'ATULAUTO', 'Auto Mobile' FROM dual UNION ALL
    SELECT 'BAJAJ-AUTO', 'Auto Mobile' FROM dual UNION ALL
    SELECT 'EICHERMOT', 'Auto Mobile' FROM dual UNION ALL
    SELECT 'ESCORTS', 'Auto Mobile' FROM dual UNION ALL
    SELECT 'FORCEMOT', 'Auto Mobile' FROM dual UNION ALL
    SELECT 'HEROMOTOCO', 'Auto Mobile' FROM dual UNION ALL
    SELECT 'HINDMOTORS', 'Auto Mobile' FROM dual UNION ALL
    SELECT 'HYUNDAI', 'Auto Mobile' FROM dual UNION ALL
    SELECT 'M&M', 'Auto Mobile' FROM dual UNION ALL
    SELECT 'MARUTI', 'Auto Mobile' FROM dual UNION ALL
    SELECT 'OLAELEC', 'Auto Mobile' FROM dual UNION ALL
    SELECT 'OLECTRA', 'Auto Mobile' FROM dual UNION ALL
    SELECT 'SMLMAH', 'Auto Mobile' FROM dual UNION ALL
    SELECT 'TMCV', 'Auto Mobile' FROM dual UNION ALL
    SELECT 'TMPV', 'Auto Mobile' FROM dual UNION ALL
    SELECT 'TVSMOTOR', 'Auto Mobile' FROM dual
) src
ON (UPPER(TRIM(tgt.SYMBOL)) = src.symbol)
WHEN MATCHED THEN UPDATE SET
    tgt.SECTOR = src.sector
WHERE NVL(UPPER(TRIM(tgt.SECTOR)), '~') <> UPPER(src.sector)
WHEN NOT MATCHED THEN
    INSERT (SYMBOL, SECTOR)
    VALUES (src.symbol, src.sector);

PROMPT [4/4] Move Auto Ancillaries symbols from Auto/Capital Goods staging into the new sector ...
MERGE INTO NSE_NIFTY_AUTO_ANCILLARIES_STAGING tgt
USING (
    SELECT 'APOLLOTYRE' AS symbol, 'Auto Ancillaries' AS sector FROM dual UNION ALL
    SELECT 'ARE&M', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'ASAHIINDIA', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'ASKAUTOLTD', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'BALKRISIND', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'BANCOINDIA', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'BHARATFORG', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'BOSCHLTD', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'CEATLTD', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'CIEINDIA', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'CRAFTSMAN', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'ENDURANCE', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'EXIDEIND', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'FIEMIND', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'GABRIEL', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'HBLENGINE', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'JAMNAAUTO', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'JBMA', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'JKTYRE', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'JTEKTINDIA', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'LUMAXIND', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'LUMAXTECH', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'MINDACORP', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'MOTHERSON', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'MRF', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'MSUMI', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'PRICOLLTD', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'RKFORGE', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'SANDHAR', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'SCHAEFFLER', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'SONACOMS', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'SUBROS', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'SUNDRMFAST', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'SUPRAJIT', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'TALBROAUTO', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'TIINDIA', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'UNOMINDA', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'VARROC', 'Auto Ancillaries' FROM dual UNION ALL
    SELECT 'ZFCVINDIA', 'Auto Ancillaries' FROM dual
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
        'AUTO_ANCILLARIES' AS sector_code,
        'Auto Ancillaries' AS sector_name,
        'NIFTY_AUTO_ANCILLARIES' AS index_code,
        30 AS display_order
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
    SELECT 'APOLLOTYRE' AS symbol, 'AUTO_ANCILLARIES' AS sector_code FROM dual UNION ALL
    SELECT 'ARE&M', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'ASAHIINDIA', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'ASKAUTOLTD', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'BALKRISIND', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'BANCOINDIA', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'BHARATFORG', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'BOSCHLTD', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'CEATLTD', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'CIEINDIA', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'CRAFTSMAN', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'ENDURANCE', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'EXIDEIND', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'FIEMIND', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'GABRIEL', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'HBLENGINE', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'JAMNAAUTO', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'JBMA', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'JKTYRE', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'JTEKTINDIA', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'LUMAXIND', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'LUMAXTECH', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'MINDACORP', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'MOTHERSON', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'MRF', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'MSUMI', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'PRICOLLTD', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'RKFORGE', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'SANDHAR', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'SCHAEFFLER', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'SONACOMS', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'SUBROS', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'SUNDRMFAST', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'SUPRAJIT', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'TALBROAUTO', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'TIINDIA', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'UNOMINDA', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'VARROC', 'AUTO_ANCILLARIES' FROM dual UNION ALL
    SELECT 'ZFCVINDIA', 'AUTO_ANCILLARIES' FROM dual
) src
ON (UPPER(TRIM(tgt.SYMBOL)) = src.symbol)
WHEN MATCHED THEN UPDATE SET
    tgt.SECTOR_CODE = src.sector_code
WHERE NVL(UPPER(TRIM(tgt.SECTOR_CODE)), '~') <> src.sector_code
WHEN NOT MATCHED THEN
    INSERT (SYMBOL, SECTOR_CODE)
    VALUES (src.symbol, src.sector_code);

DELETE FROM NSE_NIFTY_AUTO_STAGING
WHERE UPPER(TRIM(SYMBOL)) IN (
    'APOLLOTYRE', 'ARE&M', 'ASAHIINDIA', 'ASKAUTOLTD', 'BALKRISIND', 'BANCOINDIA', 'BHARATFORG', 'BOSCHLTD', 'CEATLTD',
    'CIEINDIA', 'CRAFTSMAN', 'ENDURANCE', 'EXIDEIND', 'FIEMIND', 'GABRIEL', 'JAMNAAUTO', 'JBMA',
    'JKTYRE', 'LUMAXTECH', 'MINDACORP', 'MOTHERSON', 'MRF', 'MSUMI', 'PRICOLLTD', 'RKFORGE',
    'SCHAEFFLER', 'SONACOMS', 'TIINDIA', 'UNOMINDA', 'VARROC', 'ZFCVINDIA'
);

DELETE FROM NSE_NIFTY_CAPITAL_GOODS_STAGING
WHERE UPPER(TRIM(SYMBOL)) IN (
    'HBLENGINE', 'SUBROS'
);

COMMIT;

PROMPT Auto Mobile display rename and Auto Ancillaries sector staging are ready.
