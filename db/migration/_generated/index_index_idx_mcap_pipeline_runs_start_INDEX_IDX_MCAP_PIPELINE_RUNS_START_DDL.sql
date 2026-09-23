--------------------------------------------------------
--  Backup generated - 2026-03-29 15:38:52
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: IDX_MCAP_PIPELINE_RUNS_START

CREATE INDEX "IDX_MCAP_PIPELINE_RUNS_START" ON "CVING_NSE_MCAP_PIPELINE_RUNS" ("STARTED_TS" DESC)
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
