--------------------------------------------------------
--  Backup generated - 2026-03-29 15:40:13
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: IDX_N500_TDATE

CREATE INDEX "IDX_N500_TDATE" ON "NSE_NIFTY500_DAILY_RAW_DATA_DEV" ("TRADING_DATE")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
