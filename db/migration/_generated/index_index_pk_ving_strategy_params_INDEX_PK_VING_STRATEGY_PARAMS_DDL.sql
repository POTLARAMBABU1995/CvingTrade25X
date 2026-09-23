--------------------------------------------------------
--  Backup generated - 2026-03-29 15:48:14
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: PK_VING_STRATEGY_PARAMS

CREATE UNIQUE INDEX "PK_VING_STRATEGY_PARAMS" ON "CVING_STRATEGY_PARAMS" ("STRATEGY_NAME", "PARAM_NAME")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
