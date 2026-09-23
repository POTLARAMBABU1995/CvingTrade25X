--------------------------------------------------------
--  Backup generated - 2026-03-29 15:46:29
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: PK_DIM_INDEX_MEMBERSHIP

CREATE UNIQUE INDEX "PK_DIM_INDEX_MEMBERSHIP" ON "DIM_INDEX_MEMBERSHIP" ("INDEX_CODE", "SYMBOL_ID", "VALID_FROM")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
