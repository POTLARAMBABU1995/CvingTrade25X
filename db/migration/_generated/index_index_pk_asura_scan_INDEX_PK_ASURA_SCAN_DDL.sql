--------------------------------------------------------
--  Backup generated - 2026-03-29 15:46:10
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: PK_ASURA_SCAN

CREATE UNIQUE INDEX "PK_ASURA_SCAN" ON "ASURA_SCAN_DAILY_FACT" ("RUN_DATE", "STOCK")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
