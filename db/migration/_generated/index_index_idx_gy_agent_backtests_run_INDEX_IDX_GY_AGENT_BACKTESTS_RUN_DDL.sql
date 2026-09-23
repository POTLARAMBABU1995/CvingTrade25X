--------------------------------------------------------
--  Backup generated - 2026-03-29 15:37:05
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: IDX_GY_AGENT_BACKTESTS_RUN

CREATE INDEX "IDX_GY_AGENT_BACKTESTS_RUN" ON "CVING_STRATEGY_AGENT_BACKTESTS" ("RUN_ID", "ENTRY_DATE" DESC)
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
