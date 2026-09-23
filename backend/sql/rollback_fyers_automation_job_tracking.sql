-- Rollback only the additive FYERS enterprise job columns.
-- Human review required. This script intentionally preserves both tracking tables,
-- their existing rows, legacy columns, primary keys, and indexes.

DECLARE
    PROCEDURE drop_column_if_present(
        p_table_name IN VARCHAR2,
        p_column_name IN VARCHAR2
    ) IS
        column_count NUMBER;
    BEGIN
        SELECT COUNT(*) INTO column_count
        FROM USER_TAB_COLUMNS
        WHERE TABLE_NAME = UPPER(p_table_name)
          AND COLUMN_NAME = UPPER(p_column_name);

        IF column_count > 0 THEN
            EXECUTE IMMEDIATE
                'ALTER TABLE ' || p_table_name ||
                ' DROP COLUMN ' || p_column_name;
        END IF;
    END;
BEGIN
    drop_column_if_present('FYERS_EXTRACTION_SYMBOL_STATUS', 'RETRY_COUNT');
    drop_column_if_present('FYERS_EXTRACTION_SYMBOL_STATUS', 'STATUS_REASON');

    drop_column_if_present('FYERS_EXTRACTION_RUNS', 'REQUESTED_STOP_FLAG');
    drop_column_if_present('FYERS_EXTRACTION_RUNS', 'ERROR_COUNT');
    drop_column_if_present('FYERS_EXTRACTION_RUNS', 'INVALID_COUNT');
    drop_column_if_present('FYERS_EXTRACTION_RUNS', 'INSERTED_SKIPPED_COUNT');
    drop_column_if_present('FYERS_EXTRACTION_RUNS', 'REMAINING_COUNT');
    drop_column_if_present('FYERS_EXTRACTION_RUNS', 'INSERTED_COUNT');
    drop_column_if_present('FYERS_EXTRACTION_RUNS', 'JOB_TYPE');
END;
/

COMMIT;
