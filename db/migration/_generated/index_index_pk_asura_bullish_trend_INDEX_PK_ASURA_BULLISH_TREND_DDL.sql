--------------------------------------------------------
--  Backup generated - 2026-03-29 15:46:07
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: PK_ASURA_BULLISH_TREND

CREATE UNIQUE INDEX "PK_ASURA_BULLISH_TREND" ON "ASURA_BULLISH_TREND_STRATEGY_TESTING" ("STOCK", "BUYING_DATE")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
