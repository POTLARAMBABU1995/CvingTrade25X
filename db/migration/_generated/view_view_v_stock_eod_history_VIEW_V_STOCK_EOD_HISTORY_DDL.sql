--------------------------------------------------------
--  Backup generated - 2026-03-29 15:09:02
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: VIEW
--  Source object name: V_STOCK_EOD_HISTORY

CREATE OR REPLACE FORCE NONEDITIONABLE VIEW "V_STOCK_EOD_HISTORY" ("SYMBOL", "TRADE_DATE", "OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE", "CLOSE_PRICE", "VOLUME") AS
  SELECT
    SYMBOL,
    TRADE_DATE,
    OPEN_PRICE,
    HIGH_PRICE,
    LOW_PRICE,
    CLOSE_PRICE,
    VOLUME
FROM STOCK_EOD_HISTORY
WHERE TRADE_DATE IS NOT NULL;
