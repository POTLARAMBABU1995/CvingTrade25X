--------------------------------------------------------
--  Backup generated - 2026-03-29 15:03:08
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: PROCEDURE
--  Source object name: THREE_MASTER_TABLES_DAILY_DATA_INSERTION

CREATE OR REPLACE NONEDITIONABLE PROCEDURE "THREE_MASTER_TABLES_DAILY_DATA_INSERTION" IS
    v_missing_dev     NUMBER := 0;
    v_missing_oracle  NUMBER := 0;
BEGIN
    ------------------------------------------------------------------
    -- 1. Missing count DEV
    ------------------------------------------------------------------
    SELECT COUNT(*)
    INTO  v_missing_dev
    FROM  STOCK_EOD_HISTORY h
    WHERE NOT EXISTS (
	SELECT 1
	FROM   NSE_NIFTY500_DAILY_RAW_DATA_DEV t
	WHERE  t.symbol       = h.symbol
	AND    t.trading_date = h.trade_date
    );

    ------------------------------------------------------------------
    -- 2. Missing count ORACLE
    ------------------------------------------------------------------
    SELECT COUNT(*)
    INTO  v_missing_oracle
    FROM  STOCK_EOD_HISTORY h
    WHERE NOT EXISTS (
	SELECT 1
	FROM   NSE_NIFTY500_DAILY_RAW_DATA_ORACLE t
	WHERE  t.symbol       = h.symbol
	AND    t.trading_date = h.trade_date
    );

    ------------------------------------------------------------------
    -- 3. MERGE INTO DEV
    ------------------------------------------------------------------
    MERGE INTO NSE_NIFTY500_DAILY_RAW_DATA_DEV t
    USING (
	SELECT
	    h.symbol,
	    h.trade_date,
	    h.open_price,
	    h.high_price,
	    h.low_price,
	    h.close_price,
	    h.volume
	FROM STOCK_EOD_HISTORY h
    ) s
    ON (t.symbol = s.symbol AND t.trading_date = s.trade_date)
    WHEN MATCHED THEN
	UPDATE SET
	    t.open	     = s.open_price,
	    t.high	     = s.high_price,
	    t.low	     = s.low_price,
	    t.previous_close = s.close_price,
	    t.volume	     = s.volume
    WHEN NOT MATCHED THEN
	INSERT (symbol, open, high, low, previous_close, volume, trading_date)
	VALUES (s.symbol, s.open_price, s.high_price, s.low_price,
		s.close_price, s.volume, s.trade_date);

    ------------------------------------------------------------------
    -- 4. MERGE INTO ORACLE
    ------------------------------------------------------------------
    MERGE INTO NSE_NIFTY500_DAILY_RAW_DATA_ORACLE t
    USING (
	SELECT
	    h.symbol,
	    h.trade_date,
	    h.open_price,
	    h.high_price,
	    h.low_price,
	    h.close_price,
	    h.volume
	FROM STOCK_EOD_HISTORY h
    ) s
    ON (t.symbol = s.symbol AND t.trading_date = s.trade_date)
    WHEN MATCHED THEN
	UPDATE SET
	    t.open	     = s.open_price,
	    t.high	     = s.high_price,
	    t.low	     = s.low_price,
	    t.previous_close = s.close_price,
	    t.volume	     = s.volume
    WHEN NOT MATCHED THEN
	INSERT (symbol, open, high, low, previous_close, volume, trading_date)
	VALUES (s.symbol, s.open_price, s.high_price, s.low_price,
		s.close_price, s.volume, s.trade_date);

    COMMIT;

    DBMS_OUTPUT.PUT_LINE('DEV inserted rows    : ' || v_missing_dev);
    DBMS_OUTPUT.PUT_LINE('ORACLE inserted rows : ' || v_missing_oracle);

EXCEPTION
    WHEN OTHERS THEN
	ROLLBACK;
	DBMS_OUTPUT.PUT_LINE(
	    'Error in THREE_MASTER_TABLES_DAILY_DATA_INSERTION: ' || SQLERRM);
	RAISE;
END;
/
