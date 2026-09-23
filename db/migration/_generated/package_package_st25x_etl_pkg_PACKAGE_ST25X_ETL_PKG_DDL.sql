--------------------------------------------------------
--  Backup generated - 2026-03-29 15:49:11
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: PACKAGE
--  Source object name: ST25X_ETL_PKG

CREATE OR REPLACE NONEDITIONABLE PACKAGE "ST25X_ETL_PKG" AS

    --------------------------------------------------------------------
    -- Utility: Normalize SYMBOL (ôNSE:TCS-EQö ┐ ôTCSö)
    --------------------------------------------------------------------
    FUNCTION normalize_symbol(p_symbol VARCHAR2)
	RETURN VARCHAR2;

    --------------------------------------------------------------------
    -- Sync STOCK_EOD_HISTORY ┐ RAW_DEV
    --------------------------------------------------------------------
    PROCEDURE sync_stock_to_dev(
	o_inserted OUT NUMBER,
	o_updated  OUT NUMBER
    );

    --------------------------------------------------------------------
    -- Sync STOCK_EOD_HISTORY ┐ RAW_ORACLE
    --------------------------------------------------------------------
    PROCEDURE sync_stock_to_oracle(
	o_inserted OUT NUMBER,
	o_updated  OUT NUMBER
    );

    --------------------------------------------------------------------
    -- Sync RAW_DEV ┐ STOCK_EOD_HISTORY  (Safe bidirectional)
    --------------------------------------------------------------------
    PROCEDURE sync_dev_to_stock(
	o_inserted OUT NUMBER,
	o_updated  OUT NUMBER
    );

    --------------------------------------------------------------------
    -- Master procedure (orchestrates all sync operations)
    --------------------------------------------------------------------
    PROCEDURE master_sync_all;

END ST25X_ETL_PKG;
/

CREATE OR REPLACE NONEDITIONABLE PACKAGE BODY "ST25X_ETL_PKG" AS

    --------------------------------------------------------------------
    -- Utility: Normalize SYMBOL (ôNSE:TCS-EQö ┐ ôTCSö)
    --------------------------------------------------------------------
    FUNCTION normalize_symbol(p_symbol VARCHAR2)
	RETURN VARCHAR2
    IS
    BEGIN
	RETURN UPPER(
		   REPLACE(
		       REPLACE(p_symbol, 'NSE:', ''),
		       '-EQ',
		       ''
		   )
	       );
    END normalize_symbol;



    --------------------------------------------------------------------
    -- 1. STOCK ┐ RAW_DEV
    --------------------------------------------------------------------
    PROCEDURE sync_stock_to_dev(
	o_inserted OUT NUMBER,
	o_updated  OUT NUMBER
    )
    IS
	v_before NUMBER := 0;
    BEGIN
	o_inserted := 0;
	o_updated  := 0;

	MERGE INTO NSE_NIFTY500_DAILY_RAW_DATA_DEV d
	USING (
	    SELECT
		normalize_symbol(symbol) AS symbol,
		trade_date,
		open_price,
		high_price,
		low_price,
		close_price,
		volume
	    FROM STOCK_EOD_HISTORY
	) s
	ON (
	    d.trading_date = s.trade_date
	    AND normalize_symbol(d.symbol) = s.symbol
	)
	WHEN MATCHED THEN
	    UPDATE SET
		d.open		 = s.open_price,
		d.high		 = s.high_price,
		d.low		 = s.low_price,
		d.previous_close = s.close_price,
		d.volume	 = s.volume
	    WHERE (
		    d.open	     != s.open_price
		OR  d.high	     != s.high_price
		OR  d.low	     != s.low_price
		OR  d.previous_close != s.close_price
		OR  d.volume	     != s.volume
	    )
	WHEN NOT MATCHED THEN
	    INSERT (
		symbol, open, high, low,
		previous_close, volume, trading_date
	    ) VALUES (
		s.symbol, s.open_price, s.high_price,
		s.low_price, s.close_price, s.volume, s.trade_date
	    );

	o_inserted := SQL%ROWCOUNT;

	COMMIT;
    END sync_stock_to_dev;



    --------------------------------------------------------------------
    -- 2. STOCK ┐ RAW_ORACLE
    --------------------------------------------------------------------
    PROCEDURE sync_stock_to_oracle(
	o_inserted OUT NUMBER,
	o_updated  OUT NUMBER
    )
    IS
    BEGIN
	o_inserted := 0;
	o_updated  := 0;

	MERGE INTO NSE_NIFTY500_DAILY_RAW_DATA_ORACLE t
	USING (
	    SELECT
		normalize_symbol(symbol) AS symbol,
		trade_date,
		open_price,
		high_price,
		low_price,
		close_price,
		volume
	    FROM STOCK_EOD_HISTORY
	) s
	ON (t.symbol = s.symbol AND t.trading_date = s.trade_date)
	WHEN MATCHED THEN
	    UPDATE SET
		t.open		 = s.open_price,
		t.high		 = s.high_price,
		t.low		 = s.low_price,
		t.previous_close = s.close_price,
		t.volume	 = s.volume
	WHEN NOT MATCHED THEN
	    INSERT (
		symbol, open, high, low,
		previous_close, volume, trading_date
	    ) VALUES (
		s.symbol, s.open_price, s.high_price,
		s.low_price, s.close_price, s.volume, s.trade_date
	    );

	o_inserted := SQL%ROWCOUNT;

	COMMIT;
    END sync_stock_to_oracle;



    --------------------------------------------------------------------
    -- 3. RAW_DEV ┐ STOCK_EOD_HISTORY
    --------------------------------------------------------------------
    PROCEDURE sync_dev_to_stock(
	o_inserted OUT NUMBER,
	o_updated  OUT NUMBER
    )
    IS
    BEGIN
	o_inserted := 0;
	o_updated  := 0;

	MERGE INTO STOCK_EOD_HISTORY h
	USING (
	    SELECT
		normalize_symbol(symbol) AS symbol_clean,
		trading_date,
		open,
		high,
		low,
		previous_close,
		volume
	    FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV
	) d
	ON (h.symbol = d.symbol_clean AND h.trade_date = d.trading_date)
	WHEN MATCHED THEN
	    UPDATE SET
		h.open_price  = d.open,
		h.high_price  = d.high,
		h.low_price   = d.low,
		h.close_price = d.previous_close,
		h.volume      = d.volume
	WHEN NOT MATCHED THEN
	    INSERT (
		symbol, trade_date, open_price, high_price,
		low_price, close_price, volume
	    ) VALUES (
		d.symbol_clean, d.trading_date, d.open, d.high,
		d.low, d.previous_close, d.volume
	    );

	o_inserted := SQL%ROWCOUNT;

	COMMIT;
    END sync_dev_to_stock;



    --------------------------------------------------------------------
    -- 4. MASTER SYNC ORCHESTRATOR
    --------------------------------------------------------------------
    PROCEDURE master_sync_all
    IS
	v1_insert NUMBER := 0;
	v1_update NUMBER := 0;

	v2_insert NUMBER := 0;
	v2_update NUMBER := 0;

	v3_insert NUMBER := 0;
	v3_update NUMBER := 0;
    BEGIN
	DBMS_OUTPUT.PUT_LINE('Starting Master Sync...');

	sync_stock_to_dev(v1_insert, v1_update);
	sync_stock_to_oracle(v2_insert, v2_update);
	sync_dev_to_stock(v3_insert, v3_update);

	DBMS_OUTPUT.PUT_LINE('STOCK ┐ DEV      inserted: ' || v1_insert);
	DBMS_OUTPUT.PUT_LINE('STOCK ┐ ORACLE   inserted: ' || v2_insert);
	DBMS_OUTPUT.PUT_LINE('DEV ┐ STOCK      inserted: ' || v3_insert);

	COMMIT;
    END master_sync_all;

END ST25X_ETL_PKG;
/
