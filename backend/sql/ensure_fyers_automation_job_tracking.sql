-- FYERS automation enterprise job tracking (Oracle 19c)
-- Additive and rerunnable. Preserves existing tables, rows, keys, and statuses.

DECLARE
    table_count NUMBER;
BEGIN
    SELECT COUNT(*) INTO table_count
    FROM USER_TABLES
    WHERE TABLE_NAME = 'FYERS_EXTRACTION_RUNS';

    IF table_count = 0 THEN
        EXECUTE IMMEDIATE q'[
            CREATE TABLE FYERS_EXTRACTION_RUNS (
                JOB_ID VARCHAR2(100) PRIMARY KEY,
                JOB_TYPE VARCHAR2(40) DEFAULT 'batch',
                TRADING_DATE DATE,
                STATUS VARCHAR2(30),
                TOTAL_SYMBOLS NUMBER DEFAULT 0,
                COMPLETED_COUNT NUMBER DEFAULT 0,
                INSERTED_COUNT NUMBER DEFAULT 0,
                REMAINING_COUNT NUMBER DEFAULT 0,
                FAILED_COUNT NUMBER DEFAULT 0,
                SKIPPED_COUNT NUMBER DEFAULT 0,
                INSERTED_SKIPPED_COUNT NUMBER DEFAULT 0,
                INVALID_COUNT NUMBER DEFAULT 0,
                ERROR_COUNT NUMBER DEFAULT 0,
                STARTED_AT TIMESTAMP DEFAULT SYSTIMESTAMP,
                UPDATED_AT TIMESTAMP,
                COMPLETED_AT TIMESTAMP,
                REQUESTED_STOP_FLAG CHAR(1) DEFAULT 'N',
                ERROR_MESSAGE VARCHAR2(4000)
            )
        ]';
    END IF;
END;
/

DECLARE
    table_count NUMBER;
BEGIN
    SELECT COUNT(*) INTO table_count
    FROM USER_TABLES
    WHERE TABLE_NAME = 'FYERS_EXTRACTION_SYMBOL_STATUS';

    IF table_count = 0 THEN
        EXECUTE IMMEDIATE q'[
            CREATE TABLE FYERS_EXTRACTION_SYMBOL_STATUS (
                JOB_ID VARCHAR2(100) NOT NULL,
                TRADING_DATE DATE NOT NULL,
                SYMBOL VARCHAR2(100) NOT NULL,
                STATUS VARCHAR2(30) DEFAULT 'PENDING',
                STATUS_REASON VARCHAR2(500),
                ATTEMPT_COUNT NUMBER DEFAULT 0,
                RETRY_COUNT NUMBER DEFAULT 0,
                ERROR_MESSAGE VARCHAR2(4000),
                STARTED_AT TIMESTAMP DEFAULT SYSTIMESTAMP,
                UPDATED_AT TIMESTAMP,
                COMPLETED_AT TIMESTAMP,
                CONSTRAINT PK_FYERS_EXT_SYM_STATUS
                    PRIMARY KEY (JOB_ID, TRADING_DATE, SYMBOL)
            )
        ]';
    END IF;
END;
/

DECLARE
    PROCEDURE add_column_if_missing(
        p_table_name IN VARCHAR2,
        p_column_name IN VARCHAR2,
        p_definition IN VARCHAR2
    ) IS
        column_count NUMBER;
    BEGIN
        SELECT COUNT(*) INTO column_count
        FROM USER_TAB_COLUMNS
        WHERE TABLE_NAME = UPPER(p_table_name)
          AND COLUMN_NAME = UPPER(p_column_name);

        IF column_count = 0 THEN
            EXECUTE IMMEDIATE
                'ALTER TABLE ' || p_table_name ||
                ' ADD (' || p_column_name || ' ' || p_definition || ')';
        END IF;
    END;
BEGIN
    add_column_if_missing('FYERS_EXTRACTION_RUNS', 'JOB_TYPE', 'VARCHAR2(40) DEFAULT ''batch''');
    add_column_if_missing('FYERS_EXTRACTION_RUNS', 'INSERTED_COUNT', 'NUMBER DEFAULT 0');
    add_column_if_missing('FYERS_EXTRACTION_RUNS', 'REMAINING_COUNT', 'NUMBER DEFAULT 0');
    add_column_if_missing('FYERS_EXTRACTION_RUNS', 'INSERTED_SKIPPED_COUNT', 'NUMBER DEFAULT 0');
    add_column_if_missing('FYERS_EXTRACTION_RUNS', 'INVALID_COUNT', 'NUMBER DEFAULT 0');
    add_column_if_missing('FYERS_EXTRACTION_RUNS', 'ERROR_COUNT', 'NUMBER DEFAULT 0');
    add_column_if_missing('FYERS_EXTRACTION_RUNS', 'REQUESTED_STOP_FLAG', 'CHAR(1) DEFAULT ''N''');

    add_column_if_missing('FYERS_EXTRACTION_SYMBOL_STATUS', 'STATUS_REASON', 'VARCHAR2(500)');
    add_column_if_missing('FYERS_EXTRACTION_SYMBOL_STATUS', 'RETRY_COUNT', 'NUMBER DEFAULT 0');
END;
/

DECLARE
    index_count NUMBER;
BEGIN
    SELECT COUNT(*) INTO index_count
    FROM USER_INDEXES
    WHERE INDEX_NAME = 'IDX_FYERS_EXT_RUNS_01';
    IF index_count = 0 THEN
        EXECUTE IMMEDIATE
            'CREATE INDEX IDX_FYERS_EXT_RUNS_01 ON FYERS_EXTRACTION_RUNS (TRADING_DATE, STATUS)';
    END IF;

    SELECT COUNT(*) INTO index_count
    FROM USER_INDEXES
    WHERE INDEX_NAME = 'IDX_FYERS_EXT_SYM_01';
    IF index_count = 0 THEN
        EXECUTE IMMEDIATE
            'CREATE INDEX IDX_FYERS_EXT_SYM_01 ON FYERS_EXTRACTION_SYMBOL_STATUS (TRADING_DATE, SYMBOL, STATUS)';
    END IF;
END;
/

COMMIT;
