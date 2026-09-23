--------------------------------------------------------
--  Backup generated - 2026-03-29 15:37:55
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: IDX_HIST_SYM_MONTH

CREATE INDEX "IDX_HIST_SYM_MONTH" ON "STOCK_EOD_HISTORY" ("SYMBOL", "MONTH_BUCKET")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
