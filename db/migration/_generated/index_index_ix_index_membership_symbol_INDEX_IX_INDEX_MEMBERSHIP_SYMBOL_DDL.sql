--------------------------------------------------------
--  Backup generated - 2026-03-29 15:43:26
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: IX_INDEX_MEMBERSHIP_SYMBOL

CREATE INDEX "IX_INDEX_MEMBERSHIP_SYMBOL" ON "DIM_INDEX_MEMBERSHIP" ("SYMBOL_ID")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
