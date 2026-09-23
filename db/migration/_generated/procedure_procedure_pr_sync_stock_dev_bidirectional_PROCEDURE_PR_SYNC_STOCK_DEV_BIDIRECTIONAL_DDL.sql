--------------------------------------------------------
--  Backup generated - 2026-03-29 15:02:32
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: PROCEDURE
--  Source object name: PR_SYNC_STOCK_DEV_BIDIRECTIONAL

CREATE OR REPLACE NONEDITIONABLE PROCEDURE "PR_SYNC_STOCK_DEV_BIDIRECTIONAL"
IS
    v_ins_stock_to_dev NUMBER := 0;
    v_ins_dev_to_stock NUMBER := 0;
BEGIN
    --------------------------------------------------------------------
    -- 1) INSERT NEW ROWS FROM STOCK_EOD_HISTORY � DEV TABLE
    --------------------------------------------------------------------
    INSERT INTO nse_nifty500_daily_raw_data_dev (
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
    FROM stock_eod_history h
    WHERE NOT EXISTS (
	SELECT 1
	FROM nse_nifty500_daily_raw_data_dev d
	WHERE d.trading_date = h.trade_date
	  AND REPLACE(REPLACE(d.symbol,'NSE:',''),'-EQ','') = h.symbol
    );

    v_ins_stock_to_dev := SQL%ROWCOUNT;

    --------------------------------------------------------------------
    -- 2) INSERT NEW ROWS FROM DEV � STOCK_EOD_HISTORY (WITH SYMBOL FIX)
    --------------------------------------------------------------------
    INSERT INTO stock_eod_history (
	symbol,
	trade_date,
	open_price,
	high_price,
	low_price,
	close_price,
	volume
    )
    SELECT
	REPLACE(REPLACE(d.symbol,'NSE:',''),'-EQ','') AS symbol,
	d.trading_date,
	d.open,
	d.high,
	d.low,
	d.previous_close,
	d.volume
    FROM nse_nifty500_daily_raw_data_dev d
    WHERE NOT EXISTS (
	SELECT 1
	FROM stock_eod_history h
	WHERE h.trade_date = d.trading_date
	  AND h.symbol = REPLACE(REPLACE(d.symbol,'NSE:',''),'-EQ','')
    );

    v_ins_dev_to_stock := SQL%ROWCOUNT;

    --------------------------------------------------------------------
    -- 3) COMMIT + OUTPUT
    --------------------------------------------------------------------
    COMMIT;

    DBMS_OUTPUT.PUT_LINE('Rows inserted STOCK � DEV: ' || v_ins_stock_to_dev);
    DBMS_OUTPUT.PUT_LINE('Rows inserted DEV � STOCK: ' || v_ins_dev_to_stock);

EXCEPTION
    WHEN OTHERS THEN
	ROLLBACK;
	DBMS_OUTPUT.PUT_LINE('Error in PR_SYNC_STOCK_DEV_BIDIRECTIONAL: ' || SQLERRM);
	RAISE;
END PR_SYNC_STOCK_DEV_BIDIRECTIONAL;
/
