--------------------------------------------------------
--  Backup generated - 2026-03-29 15:41:30
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: IDX_RAW_SYM_DATE

CREATE INDEX "IDX_RAW_SYM_DATE" ON "NSE_NIFTY500_DAILY_RAW_DATA_DEV" ("SYMBOL", "TRADING_DATE")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
