--------------------------------------------------------
--  Backup generated - 2026-03-29 15:42:11
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: IDX_SR_SYMBOL_TF_LEVEL

CREATE INDEX "IDX_SR_SYMBOL_TF_LEVEL" ON "PRICE_ACTION_SR_LEVELS_MANUALLY" ("SYMBOL", "TF", "SR_LEVEL")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
