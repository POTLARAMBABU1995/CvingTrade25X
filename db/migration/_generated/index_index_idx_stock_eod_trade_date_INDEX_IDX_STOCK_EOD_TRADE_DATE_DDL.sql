--------------------------------------------------------
--  Backup generated - 2026-03-29 15:42:24
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: IDX_STOCK_EOD_TRADE_DATE

CREATE INDEX "IDX_STOCK_EOD_TRADE_DATE" ON "STOCK_EOD_HISTORY" ("TRADE_DATE")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
