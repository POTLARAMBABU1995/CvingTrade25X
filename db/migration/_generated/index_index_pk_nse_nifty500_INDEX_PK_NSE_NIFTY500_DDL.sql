--------------------------------------------------------
--  Backup generated - 2026-03-29 15:47:35
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: PK_NSE_NIFTY500

CREATE UNIQUE INDEX "PK_NSE_NIFTY500" ON "NSE_NIFTY500_DAILY_RAW_DATA_ORACLE" ("SYMBOL", "TRADING_DATE")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
