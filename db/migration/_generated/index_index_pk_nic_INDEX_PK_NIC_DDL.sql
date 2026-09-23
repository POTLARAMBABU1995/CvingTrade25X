--------------------------------------------------------
--  Backup generated - 2026-03-29 15:47:24
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: PK_NIC

CREATE UNIQUE INDEX "PK_NIC" ON "NIFTY_INDEX_CONSTITUENTS" ("INDEX_NAME", "SYMBOL", "EFFECTIVE_FROM")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
