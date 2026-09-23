--------------------------------------------------------
--  Backup generated - 2026-03-29 15:45:22
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: NSE_SYM_IND_LATEST_IDX1

CREATE INDEX "NSE_SYM_IND_LATEST_IDX1" ON "NSE_SYMBOL_INDICATORS_LATEST" ("LTC_DATE", "SYMBOL")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
