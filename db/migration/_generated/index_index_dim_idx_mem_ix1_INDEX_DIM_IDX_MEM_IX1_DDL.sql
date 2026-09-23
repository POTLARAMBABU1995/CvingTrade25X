--------------------------------------------------------
--  Backup generated - 2026-03-29 15:31:52
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: DIM_IDX_MEM_IX1

CREATE INDEX "DIM_IDX_MEM_IX1" ON "DIM_INDEX_MEMBERSHIP" ("INDEX_CODE", "SYMBOL_ID", "VALID_FROM", "VALID_TO")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
