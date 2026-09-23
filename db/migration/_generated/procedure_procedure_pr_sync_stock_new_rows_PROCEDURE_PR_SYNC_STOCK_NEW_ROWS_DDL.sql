--------------------------------------------------------
--  Backup generated - 2026-03-29 15:02:40
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: PROCEDURE
--  Source object name: PR_SYNC_STOCK_NEW_ROWS

CREATE OR REPLACE NONEDITIONABLE PROCEDURE "PR_SYNC_STOCK_NEW_ROWS"
IS
    ----------------------------------------------------------------------
    -- High-watermark based incremental sync:
    --	- Reads last_load_ts from STOCK_SYNC_CTRL for target 'DEV_ORACLE'
    --	- Finds new max(load_ts) in STOCK_EOD_HISTORY
    --	- Inserts only rows in that window into:
    --	    * NSE_NIFTY500_DAILY_RAW_DATA_DEV
    --	    * NSE_NIFTY500_DAILY_RAW_DATA_ORACLE
    --	  skipping rows that already exist (SYMBOL, TRADING_DATE)
    ----------------------------------------------------------------------

    c_target	   CONSTANT STOCK_SYNC_CTRL.target%TYPE := 'DEV_ORACLE';

    v_last_ts	   STOCK_SYNC_CTRL.last_load_ts%TYPE;
    v_new_ts	   STOCK_EOD_HISTORY.load_ts%TYPE;

    v_window_rows  PLS_INTEGER := 0;
    v_ins_dev	   PLS_INTEGER := 0;
    v_ins_oracle   PLS_INTEGER := 0;
BEGIN
    ------------------------------------------------------------------
    -- 1. Ensure control row exists + lock it
    ------------------------------------------------------------------
    BEGIN
	SELECT last_load_ts
	INTO   v_last_ts
	FROM   STOCK_SYNC_CTRL
	WHERE  target = c_target
	FOR UPDATE;
    EXCEPTION
	WHEN NO_DATA_FOUND THEN
	    -- First time run for this target
	    v_last_ts := TIMESTAMP '1990-01-01 00:00:00';

	    INSERT INTO STOCK_SYNC_CTRL (target, last_load_ts)
	    VALUES (c_target, v_last_ts);

	    -- row is locked in THIS transaction; no commit yet
    END;

    ------------------------------------------------------------------
    -- 2. Compute new high-watermark in STOCK_EOD_HISTORY
    ------------------------------------------------------------------
    SELECT NVL(MAX(load_ts), v_last_ts)
    INTO   v_new_ts
    FROM   STOCK_EOD_HISTORY
    WHERE  load_ts > v_last_ts;

    -- No new data window
    IF v_new_ts = v_last_ts THEN
	DBMS_OUTPUT.PUT_LINE('PR_SYNC_STOCK_NEW_ROWS: no new rows in STOCK_EOD_HISTORY for target ' || c_target);
	RETURN;
    END IF;

    ------------------------------------------------------------------
    -- 3. Count rows in the window (for logging)
    ------------------------------------------------------------------
    SELECT COUNT(*)
    INTO   v_window_rows
    FROM   STOCK_EOD_HISTORY
    WHERE  load_ts > v_last_ts
      AND  load_ts <= v_new_ts;

    DBMS_OUTPUT.PUT_LINE('PR_SYNC_STOCK_NEW_ROWS: processing window');
    DBMS_OUTPUT.PUT_LINE('  LOAD_TS : '
			 || TO_CHAR(v_last_ts, 'YYYY-MM-DD HH24:MI:SS.FF3')
			 || ' -> '
			 || TO_CHAR(v_new_ts, 'YYYY-MM-DD HH24:MI:SS.FF3'));
    DBMS_OUTPUT.PUT_LINE('  Rows in STOCK_EOD_HISTORY window : ' || v_window_rows);

    ------------------------------------------------------------------
    -- 4. DEV: insert only new rows (by LOAD_TS window + NOT EXISTS)
    ------------------------------------------------------------------
    INSERT /*+ APPEND */
    INTO NSE_NIFTY500_DAILY_RAW_DATA_DEV (
	symbol,
	open,
	high,
	low,
	previous_close,
	volume,
	trading_date
    )
    SELECT
	h.symbol,
	h.open_price,
	h.high_price,
	h.low_price,
	h.close_price,
	h.volume,
	h.trade_date
    FROM STOCK_EOD_HISTORY h
    WHERE h.load_ts > v_last_ts
      AND h.load_ts <= v_new_ts
      AND NOT EXISTS (
	    SELECT 1
	    FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV t
	    WHERE t.symbol	 = h.symbol
	      AND t.trading_date = h.trade_date
      );

    v_ins_dev := SQL%ROWCOUNT;

    ------------------------------------------------------------------
    -- 5. ORACLE: insert only new rows (same window)
    ------------------------------------------------------------------
    INSERT /*+ APPEND */
    INTO NSE_NIFTY500_DAILY_RAW_DATA_ORACLE (
	symbol,
	open,
	high,
	low,
	previous_close,
	volume,
	trading_date
    )
    SELECT
	h.symbol,
	h.open_price,
	h.high_price,
	h.low_price,
	h.close_price,
	h.volume,
	h.trade_date
    FROM STOCK_EOD_HISTORY h
    WHERE h.load_ts > v_last_ts
      AND h.load_ts <= v_new_ts
      AND NOT EXISTS (
	    SELECT 1
	    FROM NSE_NIFTY500_DAILY_RAW_DATA_ORACLE t
	    WHERE t.symbol	 = h.symbol
	      AND t.trading_date = h.trade_date
      );

    v_ins_oracle := SQL%ROWCOUNT;

    ------------------------------------------------------------------
    -- 6. Move high-watermark forward and commit
    ------------------------------------------------------------------
    UPDATE STOCK_SYNC_CTRL
    SET    last_load_ts = v_new_ts
    WHERE  target = c_target;

    COMMIT;

    DBMS_OUTPUT.PUT_LINE('PR_SYNC_STOCK_NEW_ROWS summary:');
    DBMS_OUTPUT.PUT_LINE('  DEV inserted    : ' || v_ins_dev);
    DBMS_OUTPUT.PUT_LINE('  ORACLE inserted : ' || v_ins_oracle);
    DBMS_OUTPUT.PUT_LINE('  High-watermark  : ' ||
			 TO_CHAR(v_new_ts, 'YYYY-MM-DD HH24:MI:SS.FF3'));

EXCEPTION
    WHEN OTHERS THEN
	ROLLBACK;
	DBMS_OUTPUT.PUT_LINE('Error in PR_SYNC_STOCK_NEW_ROWS: ' || SQLERRM);
	RAISE;
END;
/
