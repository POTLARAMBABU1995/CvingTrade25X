--------------------------------------------------------
--  Backup generated - 2026-03-29 15:43:37
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: IX_RAW_DATE

CREATE INDEX "IX_RAW_DATE" ON "NSE_NIFTY500_DAILY_RAW_DATA_ORACLE" ("TRADING_DATE")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
