--------------------------------------------------------
--  Backup generated - 2026-03-29 15:43:33
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: IX_NIC_LOOKUP

CREATE INDEX "IX_NIC_LOOKUP" ON "NIFTY_INDEX_CONSTITUENTS" ("INDEX_NAME", "SYMBOL", "EFFECTIVE_TO")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
