--------------------------------------------------------
--  Backup generated - 2026-03-29 15:47:38
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: PK_SR_LEVELS

CREATE UNIQUE INDEX "PK_SR_LEVELS" ON "PRICE_ACTION_SR_LEVELS_MANUALLY" ("LEVEL_ID")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
