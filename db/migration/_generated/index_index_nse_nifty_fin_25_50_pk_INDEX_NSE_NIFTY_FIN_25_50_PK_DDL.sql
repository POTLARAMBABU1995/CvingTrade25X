--------------------------------------------------------
--  Backup generated - 2026-03-29 15:44:02
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: NSE_NIFTY_FIN_25_50_PK

CREATE UNIQUE INDEX "NSE_NIFTY_FIN_25_50_PK" ON "NSE_NIFTY_FINANCIAL_SERVICES_25_50_STAGING" ("SYMBOL")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
