--------------------------------------------------------
--  Backup generated - 2026-03-29 15:05:28
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: VIEW
--  Source object name: V_MISSING_DATES

CREATE OR REPLACE FORCE NONEDITIONABLE VIEW "V_MISSING_DATES" ("MISSING_IN_DEV", "MISSING_IN_STOCK") AS
  SELECT DISTINCT h.trade_date AS missing_in_dev, NULL AS missing_in_stock
FROM stock_eod_history h
WHERE NOT EXISTS (
    SELECT 1
    FROM nse_nifty500_daily_raw_data_dev d
    WHERE d.trading_date = h.trade_date
)
UNION ALL
SELECT NULL, d.trading_date
FROM nse_nifty500_daily_raw_data_dev d
WHERE NOT EXISTS (
    SELECT 1
    FROM stock_eod_history h
    WHERE h.trade_date = d.trading_date
)
ORDER BY 1, 2;
