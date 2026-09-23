--------------------------------------------------------
--  Backup generated - 2026-03-29 15:06:40
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: VIEW
--  Source object name: V_NSE_NIFTY50_LARGECAP_OHLCV

CREATE OR REPLACE FORCE NONEDITIONABLE VIEW "V_NSE_NIFTY50_LARGECAP_OHLCV" ("SYMBOL", "OPEN", "HIGH", "LOW", "PREVIOUS_CLOSE", "VOLUME", "TRADING_DATE") AS
  SELECT r."SYMBOL",r."OPEN",r."HIGH",r."LOW",r."PREVIOUS_CLOSE",r."VOLUME",r."TRADING_DATE"
FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV r
INNER JOIN NSE_NIFTY50_LARGECAP l
    ON r.SYMBOL = l.SYMBOL;
