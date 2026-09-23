--------------------------------------------------------
--  Backup generated - 2026-03-29 15:11:18
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: VIEW
--  Source object name: VW_SECTOR_CHEM

CREATE OR REPLACE FORCE NONEDITIONABLE VIEW "VW_SECTOR_CHEM" ("S_NO", "SYMBOL", "SECTOR", "INDEX", "LTC_DATE", "CLOSE_PRICE", "RSI55_GT0", "RSI50_GT0", "SMA20", "SMA50", "SMA100") AS
  SELECT   ROW_NUMBER() OVER (ORDER BY SYMBOL) AS S_NO,   SYMBOL,   SECTOR,   INDEX_CODE AS "INDEX",   LTC_DATE,   CLOSE_PRICE,   RSI55_GT0,   RSI50_GT0,   SMA20,   SMA50,   SMA100 FROM MV_NSE_SECTOR_UI_SNAPSHOT WHERE SECTOR = 'CHEM';
