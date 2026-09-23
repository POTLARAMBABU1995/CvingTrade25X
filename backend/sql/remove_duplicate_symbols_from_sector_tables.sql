PROMPT Removing duplicate symbols from NSE_NIFTY*STAGING sector tables
SET DEFINE OFF;

DECLARE
    CURSOR c_tables IS
        SELECT t.table_name
          FROM user_tables t
         WHERE t.table_name LIKE 'NSE_NIFTY%STAGING'
         ORDER BY t.table_name;

    l_has_symbol NUMBER;
    l_dup_before NUMBER;
    l_deleted    NUMBER;
BEGIN
    FOR r IN c_tables LOOP
        SELECT COUNT(*)
          INTO l_has_symbol
          FROM user_tab_columns
         WHERE table_name = r.table_name
           AND column_name = 'SYMBOL';

        IF l_has_symbol = 0 THEN
            DBMS_OUTPUT.PUT_LINE('Skipped (no SYMBOL column): ' || r.table_name);
            CONTINUE;
        END IF;

        EXECUTE IMMEDIATE
            'SELECT COUNT(*) FROM (' ||
            'SELECT UPPER(TRIM(symbol)) AS s, COUNT(*) AS c ' ||
            'FROM ' || r.table_name || ' ' ||
            'WHERE symbol IS NOT NULL AND TRIM(symbol) IS NOT NULL ' ||
            'GROUP BY UPPER(TRIM(symbol)) HAVING COUNT(*) > 1)'
            INTO l_dup_before;

        EXECUTE IMMEDIATE
            'DELETE FROM ' || r.table_name || ' t ' ||
            'WHERE t.rowid IN (' ||
            'SELECT rid FROM (' ||
            'SELECT rowid AS rid, ' ||
            'ROW_NUMBER() OVER (PARTITION BY UPPER(TRIM(symbol)) ORDER BY rowid) rn ' ||
            'FROM ' || r.table_name || ' ' ||
            'WHERE symbol IS NOT NULL AND TRIM(symbol) IS NOT NULL' ||
            ') WHERE rn > 1)';

        l_deleted := SQL%ROWCOUNT;

        DBMS_OUTPUT.PUT_LINE(
            'Table=' || r.table_name ||
            ' | DuplicateSetsBefore=' || l_dup_before ||
            ' | RowsDeleted=' || l_deleted
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

PROMPT Dedup completed.
