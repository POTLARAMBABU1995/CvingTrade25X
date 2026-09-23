--------------------------------------------------------
--  Backup generated - 2026-03-29 15:38:00
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: IDX_HIST_SYM_WEEK

CREATE INDEX "IDX_HIST_SYM_WEEK" ON "STOCK_EOD_HISTORY" ("SYMBOL", "WEEK_BUCKET")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
