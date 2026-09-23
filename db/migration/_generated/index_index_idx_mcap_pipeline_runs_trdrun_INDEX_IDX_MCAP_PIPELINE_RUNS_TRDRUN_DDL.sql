--------------------------------------------------------
--  Backup generated - 2026-03-29 15:39:10
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: IDX_MCAP_PIPELINE_RUNS_TRDRUN

CREATE INDEX "IDX_MCAP_PIPELINE_RUNS_TRDRUN" ON "CVING_NSE_MCAP_PIPELINE_RUNS" ("TRADE_DATE", "RUN_TYPE", "STATUS")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
