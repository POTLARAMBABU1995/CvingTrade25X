--------------------------------------------------------
--  Backup generated - 2026-03-29 15:40:19
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: IDX_NG_STRATEGY_PARAMS_UPD

CREATE INDEX "IDX_NG_STRATEGY_PARAMS_UPD" ON "CVING_STRATEGY_PARAMS" ("UPDATED_AT")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
