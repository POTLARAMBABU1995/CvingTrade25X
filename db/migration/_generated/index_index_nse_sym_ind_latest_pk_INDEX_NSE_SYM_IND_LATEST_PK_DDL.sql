--------------------------------------------------------
--  Backup generated - 2026-03-29 15:45:41
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: NSE_SYM_IND_LATEST_PK

CREATE UNIQUE INDEX "NSE_SYM_IND_LATEST_PK" ON "NSE_SYMBOL_INDICATORS_LATEST" ("SYMBOL")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
