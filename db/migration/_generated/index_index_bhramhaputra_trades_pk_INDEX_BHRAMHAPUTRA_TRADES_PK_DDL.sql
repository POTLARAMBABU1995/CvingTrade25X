--------------------------------------------------------
--  Backup generated - 2026-03-29 15:31:23
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: BHRAMHAPUTRA_TRADES_PK

CREATE UNIQUE INDEX "BHRAMHAPUTRA_TRADES_PK" ON "BHRAMHAPUTRA_TRADES" ("SYMBOL", "TRADE_DATE")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
