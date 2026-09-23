--------------------------------------------------------
--  Backup generated - 2026-03-29 15:42:57
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: IDX_VING_NSE_FFMC_HIST_SYMDATE

CREATE INDEX "IDX_VING_NSE_FFMC_HIST_SYMDATE" ON "CVING_NSE_FFMC_HIST" ("SYMBOL", "TRADE_DATE" DESC)
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
