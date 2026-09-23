--------------------------------------------------------
--  Backup generated - 2026-03-29 15:49:50
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: PROCEDURE
--  Source object name: PR_CLEAN_STOCK_DEV_DUPLICATES

CREATE OR REPLACE NONEDITIONABLE PROCEDURE "PR_CLEAN_STOCK_DEV_DUPLICATES"
IS
BEGIN
    --------------------------------------------------------------------
    -- 1) Remove duplicate keys in STOCK (symbol + date)
    --------------------------------------------------------------------
    DELETE FROM stock_eod_history h
    WHERE ROWID NOT IN (
	SELECT MIN(ROWID)
	FROM stock_eod_history
	GROUP BY symbol, trade_date
    );

    --------------------------------------------------------------------
    -- 2) Remove duplicates in DEV (after symbol normalization)
    --------------------------------------------------------------------
    DELETE FROM nse_nifty500_daily_raw_data_dev d
    WHERE ROWID NOT IN (
	SELECT MIN(ROWID)
	FROM (
	    SELECT
		REPLACE(REPLACE(symbol,'NSE:',''),'-EQ','') AS symbol_clean,
		trading_date,
		ROWID AS rid
	    FROM nse_nifty500_daily_raw_data_dev
	)
	GROUP BY symbol_clean, trading_date
    );

    COMMIT;

    DBMS_OUTPUT.PUT_LINE('Duplicate cleaning completed successfully.');

END PR_CLEAN_STOCK_DEV_DUPLICATES;
/
