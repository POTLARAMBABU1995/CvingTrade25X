--------------------------------------------------------
--  Backup generated - 2026-03-29 15:41:26
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: IDX_NSE500_SYM_YEAR

CREATE INDEX "IDX_NSE500_SYM_YEAR" ON "NSE_NIFTY500_DAILY_RAW_DATA_DEV" ("SYMBOL", "YEAR_BUCKET")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
