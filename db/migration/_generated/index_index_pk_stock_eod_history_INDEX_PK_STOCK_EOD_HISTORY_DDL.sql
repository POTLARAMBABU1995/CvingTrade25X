--------------------------------------------------------
--  Backup generated - 2026-03-29 15:47:43
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: PK_STOCK_EOD_HISTORY

CREATE UNIQUE INDEX "PK_STOCK_EOD_HISTORY" ON "STOCK_EOD_HISTORY" ("SYMBOL", "TRADE_DATE")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
