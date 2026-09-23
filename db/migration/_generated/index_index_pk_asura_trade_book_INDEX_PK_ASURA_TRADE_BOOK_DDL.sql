--------------------------------------------------------
--  Backup generated - 2026-03-29 15:46:14
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: PK_ASURA_TRADE_BOOK

CREATE UNIQUE INDEX "PK_ASURA_TRADE_BOOK" ON "ASURA_TRADE_BOOK" ("SYMBOL")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
