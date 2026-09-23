--------------------------------------------------------
--  Backup generated - 2026-03-29 15:00:41
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: PROCEDURE
--  Source object name: PR_DAILY_INCREMENTAL_LOAD

CREATE OR REPLACE NONEDITIONABLE PROCEDURE "PR_DAILY_INCREMENTAL_LOAD"
IS
    v_ins_dev NUMBER := 0;
    v_ins_stock NUMBER := 0;
BEGIN
    --------------------------------------------------------------------
    -- 1) NEW ROWS STOCK � DEV
    --------------------------------------------------------------------
    INSERT INTO nse_nifty500_daily_raw_data_dev (
	symbol, open, high, low, previous_close, volume, trading_date
    )
    SELECT
	h.symbol, h.open_price, h.high_price, h.low_price,
	h.close_price, h.volume, h.trade_date
    FROM stock_eod_history h
    WHERE NOT EXISTS (
	SELECT 1
	FROM nse_nifty500_daily_raw_data_dev d
	WHERE d.trading_date = h.trade_date
	  AND REPLACE(REPLACE(d.symbol,'NSE:',''),'-EQ','') = h.symbol
    );

    v_ins_dev := SQL%ROWCOUNT;

    --------------------------------------------------------------------
    -- 2) NEW ROWS DEV � STOCK	(only if new data entered manually)
    --------------------------------------------------------------------
    INSERT INTO stock_eod_history (
	symbol, trade_date, open_price, high_price,
	low_price, close_price, volume
    )
    SELECT
	REPLACE(REPLACE(symbol,'NSE:',''),'-EQ',''),
	trading_date,
	open, high, low,
	previous_close,
	volume
    FROM nse_nifty500_daily_raw_data_dev d
    WHERE NOT EXISTS (
	SELECT 1
	FROM stock_eod_history h
	WHERE h.symbol = REPLACE(REPLACE(d.symbol,'NSE:',''),'-EQ','')
	  AND h.trade_date = d.trading_date
    );

    v_ins_stock := SQL%ROWCOUNT;

    --------------------------------------------------------------------
    COMMIT;

    DBMS_OUTPUT.PUT_LINE('Daily Load STOCK � DEV  : ' || v_ins_dev);
    DBMS_OUTPUT.PUT_LINE('Daily Load DEV � STOCK  : ' || v_ins_stock);

END PR_DAILY_INCREMENTAL_LOAD;
/
