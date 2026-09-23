--------------------------------------------------------
--  Backup generated - 2026-03-29 15:41:02
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: IDX_NSE500_SYM_MONTH

CREATE INDEX "IDX_NSE500_SYM_MONTH" ON "NSE_NIFTY500_DAILY_RAW_DATA_DEV" ("SYMBOL", "MONTH_BUCKET")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
