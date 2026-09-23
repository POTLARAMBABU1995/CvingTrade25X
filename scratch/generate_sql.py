import os

symbols = [
    'ACGL','ALICON','AMARAJABAT','APOLLOTYRE','ARE&M','ASAHIINDIA','ASAL','ASKAUTOLTD',
    'AUTOAXLES','BALKRISIND','BANCOINDIA','BELRISE','BHARATFORG','BHARATSE','BOSCHLTD',
    'CARRARO','CEATLTD','CIEINDIA','CRAFTSMAN','DIVGIITTS','ENDURANCE','ENKEIWHEL',
    'EXIDEIND','FIEMIND','FMGOETZE','FRONTSP','GABRIEL','GNA','GOODYEAR','HAPPYFORGE',
    'HINDCOMPOS','HITECHGEAR','IGARASHI','IMPAL','INDNIPPON','JAMNAAUTO','JAYBARMARU',
    'JBMA','JKTYRE','JTEKTINDIA','KINETICENG','KROSS','LGBBROSLTD','LGBROSLTD',
    'LUMAXIND','LUMAXTECH','MANDEEP','MENONBE','MINDACORP','MMFL','MOTHERSON','MRF',
    'MSUMI','MUNJALAU','MUNJALSHOW','NDRAUTO','NELCAST','NRBBEARING','OBSCP',
    'OMAXAUTO','PAVNAIND','PPAP','PRADPME','PRECAM','PRECISION','PRICOLLTD',
    'PRITIKAUTO','RACLGEAR','RAJRATAN','RBL','REMSONSIND','RICOAUTO','RKFORGE',
    'RML','ROLEXRINGS','SANDHAR','SANSERA','SCHAEFFLER','SEDEMAC','SEKURITIND',
    'SHARDAMOTR','SHRIPISTON','SJS','SKFINDIA','SONACOMS','SSWL','STERTOOLS',
    'STUDDS','SUBROS','SUNCLAY','SUNDRMBRAK','SUNDRMFAST','SUPRAJIT','TALBROAUTO',
    'TENNIND','TIINDIA','TIMKEN','TOLINS','TVSSRICHAK','UNIPARTS','UNOMINDA',
    'VARROC','VELJAN','WHEELS','ZFCVINDIA','ZFSTEERING'
]

in_clause_inner = ",".join(f"''{s}''" for s in symbols)
in_clause = f"'{in_clause_inner}'"

union_all_parts = []
for i, s in enumerate(symbols):
    union = f"    SELECT '{s}' AS symbol, 'Auto Components & Equipments' AS sector FROM dual" if i == 0 else f"    SELECT '{s}', 'Auto Components & Equipments' FROM dual"
    union_all_parts.append(union)
union_all_sql = " UNION ALL\n".join(union_all_parts)

union_all_parts_map = []
for i, s in enumerate(symbols):
    union = f"    SELECT '{s}' AS symbol, 'AUTO_COMPONENTS_EQUIPMENTS' AS sector_code FROM dual" if i == 0 else f"    SELECT '{s}', 'AUTO_COMPONENTS_EQUIPMENTS' FROM dual"
    union_all_parts_map.append(union)
union_all_map_sql = " UNION ALL\n".join(union_all_parts_map)

sql_content = f"""PROMPT Creating Auto Components & Equipments sector staging table
WHENEVER OSERROR EXIT FAILURE ROLLBACK
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK
SET DEFINE OFF;

PROMPT [1/3] Validate cross-sector ownership before any DML ...

DECLARE
    l_symbol_in_clause  VARCHAR2(4000) := {in_clause};
    l_table_conflicts      NUMBER := 0;
    l_sector_map_conflicts NUMBER := 0;
    l_conflict_symbols     VARCHAR2(4000);
BEGIN
    FOR r IN (
        SELECT t.table_name
          FROM user_tables t
          JOIN user_tab_columns c
            ON c.table_name = t.table_name
           AND c.column_name = 'SYMBOL'
         WHERE t.table_name LIKE 'NSE_NIFTY%STAGING'
           AND t.table_name NOT IN ('NSE_NIFTY_AUTO_COMPONENTS_EQUIPMENTS_STAGING')
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
                -20071,
                'Auto Components & Equipments symbols already exist in ' || r.table_name || ': ' || SUBSTR(NVL(l_conflict_symbols, 'UNKNOWN'), 1, 3000)
            );
        END IF;
    END LOOP;

    EXECUTE IMMEDIATE
        'SELECT COUNT(*) FROM NSE_SYMBOL_SECTOR_MAP WHERE UPPER(TRIM(SYMBOL)) IN (' || l_symbol_in_clause || ') AND NVL(UPPER(TRIM(SECTOR_CODE)), ''~'') NOT IN (''~'', ''AUTO_COMPONENTS_EQUIPMENTS'')'
        INTO l_sector_map_conflicts;

    IF l_sector_map_conflicts > 0 THEN
        EXECUTE IMMEDIATE
            'SELECT LISTAGG(symbol || '':'' || sector_code, '', '') WITHIN GROUP (ORDER BY symbol) ' ||
            'FROM (SELECT DISTINCT UPPER(TRIM(SYMBOL)) AS symbol, UPPER(TRIM(SECTOR_CODE)) AS sector_code ' ||
            '      FROM NSE_SYMBOL_SECTOR_MAP ' ||
            '      WHERE UPPER(TRIM(SYMBOL)) IN (' || l_symbol_in_clause || ') ' ||
            '        AND NVL(UPPER(TRIM(SECTOR_CODE)), ''~'') NOT IN (''~'', ''AUTO_COMPONENTS_EQUIPMENTS''))'
            INTO l_conflict_symbols;

        RAISE_APPLICATION_ERROR(
            -20072,
            'Auto Components & Equipments symbols already map to another sector in NSE_SYMBOL_SECTOR_MAP: ' || SUBSTR(NVL(l_conflict_symbols, 'UNKNOWN'), 1, 3000)
        );
    END IF;
END;
/

PROMPT [2/3] Create staging objects only after validation passes ...
DECLARE
    l_count NUMBER := 0;
BEGIN
    SELECT COUNT(*)
      INTO l_count
      FROM user_tables
     WHERE table_name = 'NSE_NIFTY_AUTO_COMPONENTS_EQUIPMENTS_STAGING';

    IF l_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE TABLE NSE_NIFTY_AUTO_COMPONENTS_EQUIPMENTS_STAGING AS SELECT * FROM NSE_NIFTY_AUTO_STAGING WHERE 1 = 0';
    END IF;

    SELECT COUNT(*)
      INTO l_count
      FROM user_indexes
     WHERE index_name = 'UK_NIFTY_AUTO_COMP_EQ_SYM';

    IF l_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE UNIQUE INDEX UK_NIFTY_AUTO_COMP_EQ_SYM ON NSE_NIFTY_AUTO_COMPONENTS_EQUIPMENTS_STAGING (SYMBOL)';
    END IF;
END;
/

PROMPT [3/3] Merge sector master and staging records ...

MERGE INTO NSE_SECTOR_MASTER tgt
USING (
    SELECT
        'AUTO_COMPONENTS_EQUIPMENTS' AS sector_code,
        'Auto Components & Equipments' AS sector_name,
        'NIFTY_AUTO_COMPONENTS_EQUIPMENTS' AS index_code,
        45 AS display_order
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

MERGE INTO NSE_NIFTY_AUTO_COMPONENTS_EQUIPMENTS_STAGING tgt
USING (
{union_all_sql}
) src
ON (UPPER(TRIM(tgt.SYMBOL)) = src.symbol)
WHEN MATCHED THEN UPDATE SET
    tgt.SECTOR = src.sector
WHERE NVL(UPPER(TRIM(tgt.SECTOR)), '~') <> UPPER(src.sector)
WHEN NOT MATCHED THEN
    INSERT (SYMBOL, SECTOR)
    VALUES (src.symbol, src.sector);

MERGE INTO NSE_SYMBOL_SECTOR_MAP tgt
USING (
{union_all_map_sql}
) src
ON (UPPER(TRIM(tgt.SYMBOL)) = src.symbol)
WHEN MATCHED THEN UPDATE SET
    tgt.SECTOR_CODE = src.sector_code
WHERE NVL(UPPER(TRIM(tgt.SECTOR_CODE)), '~') <> src.sector_code
WHEN NOT MATCHED THEN
    INSERT (SYMBOL, SECTOR_CODE)
    VALUES (src.symbol, src.sector_code);

COMMIT;

PROMPT Auto Components & Equipments sector staging is ready.
"""

with open('backend/sql/create_auto_components_equipments_sector_tables.sql', 'w', encoding='utf-8') as f:
    f.write(sql_content)

print("Created create_auto_components_equipments_sector_tables.sql")
