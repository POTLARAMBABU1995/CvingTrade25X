--------------------------------------------------------
--  Backup generated - 2026-03-29 15:07:29
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: VIEW
--  Source object name: V_NSE500_DAILY_6M

CREATE OR REPLACE FORCE NONEDITIONABLE VIEW "V_NSE500_DAILY_6M" ("SYMBOL", "TRADING_DATE", "PRICE", "OPEN", "HIGH", "LOW", "VOLUME") AS
  SELECT
    SYMBOL,
    TRADING_DATE,
    PREVIOUS_CLOSE AS PRICE,
    OPEN,
    HIGH,
    LOW,
    VOLUME
FROM
    NSE_NIFTY500_DAILY_RAW_DATA_DEV
WHERE
    TRADING_DATE >= ADD_MONTHS(TRUNC(SYSDATE), -6);
