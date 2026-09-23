--------------------------------------------------------
--  Backup generated - 2026-03-29 15:38:08
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: IDX_HIST_SYM_YEAR

CREATE INDEX "IDX_HIST_SYM_YEAR" ON "STOCK_EOD_HISTORY" ("SYMBOL", "YEAR_BUCKET")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
