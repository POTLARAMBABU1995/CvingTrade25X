--------------------------------------------------------
--  Backup generated - 2026-03-29 15:37:48
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: IDX_HIST_LOAD_TS

CREATE INDEX "IDX_HIST_LOAD_TS" ON "STOCK_EOD_HISTORY" ("LOAD_TS")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
