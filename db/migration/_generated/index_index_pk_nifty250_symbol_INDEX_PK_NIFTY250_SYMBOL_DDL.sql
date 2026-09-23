--------------------------------------------------------
--  Backup generated - 2026-03-29 15:47:32
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: PK_NIFTY250_SYMBOL

CREATE UNIQUE INDEX "PK_NIFTY250_SYMBOL" ON "NSE_NIFTY250_SMALLCAP" ("SYMBOL")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
