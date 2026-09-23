--------------------------------------------------------
--  Backup generated - 2026-03-29 15:40:04
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: IDX_N150_SYMBOL

CREATE INDEX "IDX_N150_SYMBOL" ON "NSE_NIFTY150_MIDCAP" ("SYMBOL")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
