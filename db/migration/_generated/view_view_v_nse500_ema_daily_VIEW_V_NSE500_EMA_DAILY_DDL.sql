--------------------------------------------------------
--  Backup generated - 2026-03-29 15:07:53
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: VIEW
--  Source object name: V_NSE500_EMA_DAILY

CREATE OR REPLACE FORCE NONEDITIONABLE VIEW "V_NSE500_EMA_DAILY" ("SYMBOL", "TRADING_DATE", "PRICE_FOR_EMA", "OPEN", "HIGH", "LOW", "VOLUME") AS
  SELECT
    SYMBOL,
    TRADING_DATE,
    PREVIOUS_CLOSE    AS PRICE_FOR_EMA,
    OPEN,
    HIGH,
    LOW,
    VOLUME
FROM
    NSE_NIFTY500_DAILY_RAW_DATA_DEV;
