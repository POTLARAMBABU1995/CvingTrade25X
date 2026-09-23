--------------------------------------------------------
--  Backup generated - 2026-03-29 15:43:21
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: IX_ASURA_TRADE_BOOK_BUY_DT

CREATE INDEX "IX_ASURA_TRADE_BOOK_BUY_DT" ON "ASURA_TRADE_BOOK" ("BUYING_DATE" DESC)
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
