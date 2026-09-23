--------------------------------------------------------
--  Backup generated - 2026-03-29 15:49:44
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: PROCEDURE
--  Source object name: MERGE_FROM_HISTORY_TO_RAW

CREATE OR REPLACE NONEDITIONABLE PROCEDURE "MERGE_FROM_HISTORY_TO_RAW" IS
  v_ins_dev    PLS_INTEGER := 0;
  v_ins_oracle PLS_INTEGER := 0;
BEGIN
  -------------------------------------------------------------------
  -- Merge into DEV table
  -------------------------------------------------------------------
  MERGE INTO nse_nifty500_daily_raw_data_dev t
  USING (
    SELECT DISTINCT
	   normalize_symbol(symbol)  AS symbol,
	   TRUNC(trade_date)	     AS trading_date,
	   open_price,
	   high_price,
	   low_price,
	   close_price,
	   volume
    FROM stock_eod_history
    WHERE symbol IS NOT NULL
      AND trade_date IS NOT NULL
  ) s
  ON (t.symbol = s.symbol AND t.trading_date = s.trading_date)
  WHEN NOT MATCHED THEN
    INSERT (
	symbol,
	trading_date,
	open,
	high,
	low,
	previous_close,
	volume
    )
    VALUES (
	s.symbol,
	s.trading_date,
	s.open_price,
	s.high_price,
	s.low_price,
	s.close_price,
	s.volume
    );

  v_ins_dev := SQL%ROWCOUNT;

  -------------------------------------------------------------------
  -- Merge into ORACLE table
  -------------------------------------------------------------------
  MERGE INTO nse_nifty500_daily_raw_data_oracle t
  USING (
    SELECT DISTINCT
	   normalize_symbol(symbol) AS symbol,
	   TRUNC(trade_date)	    AS trading_date,
	   open_price,
	   high_price,
	   low_price,
	   close_price,
	   volume
    FROM stock_eod_history
    WHERE symbol IS NOT NULL
      AND trade_date IS NOT NULL
  ) s
  ON (t.symbol = s.symbol AND t.trading_date = s.trading_date)
  WHEN NOT MATCHED THEN
    INSERT (
	symbol,
	trading_date,
	open,
	high,
	low,
	previous_close,
	volume
    )
    VALUES (
	s.symbol,
	s.trading_date,
	s.open_price,
	s.high_price,
	s.low_price,
	s.close_price,
	s.volume
    );

  v_ins_oracle := SQL%ROWCOUNT;

  COMMIT;

  DBMS_OUTPUT.PUT_LINE('merge_from_history_to_raw: DEV inserts=' || v_ins_dev);
  DBMS_OUTPUT.PUT_LINE('merge_from_history_to_raw: ORACLE inserts=' || v_ins_oracle);

EXCEPTION
  WHEN OTHERS THEN
    ROLLBACK;
    DBMS_OUTPUT.PUT_LINE('Error in merge_from_history_to_raw: ' || SQLERRM);
END;
/
