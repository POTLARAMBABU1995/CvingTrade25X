--------------------------------------------------------
--  Backup generated - 2026-03-29 15:43:12
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: IDX_VING_NSE_FFMC_HIST_TRDSRC

CREATE INDEX "IDX_VING_NSE_FFMC_HIST_TRDSRC" ON "CVING_NSE_FFMC_HIST" ("TRADE_DATE", "SOURCE_NAME", "FETCH_STATUS")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
