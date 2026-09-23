--------------------------------------------------------
--  Backup generated - 2026-03-29 15:40:28
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: IDX_NIFTY500_MASTER_DATE

CREATE INDEX "IDX_NIFTY500_MASTER_DATE" ON "NIFTY500_MASTER" ("TRADE_DATE")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
