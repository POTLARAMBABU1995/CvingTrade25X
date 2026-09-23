--------------------------------------------------------
--  Backup generated - 2026-03-29 15:40:47
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: IDX_NIFTY500_MASTER_SYMBOL

CREATE INDEX "IDX_NIFTY500_MASTER_SYMBOL" ON "NIFTY500_MASTER" ("SYMBOL")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
