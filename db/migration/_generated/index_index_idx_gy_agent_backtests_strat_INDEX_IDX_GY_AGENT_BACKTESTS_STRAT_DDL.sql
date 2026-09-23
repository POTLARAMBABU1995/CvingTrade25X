--------------------------------------------------------
--  Backup generated - 2026-03-29 15:37:32
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: IDX_GY_AGENT_BACKTESTS_STRAT

CREATE INDEX "IDX_GY_AGENT_BACKTESTS_STRAT" ON "CVING_STRATEGY_AGENT_BACKTESTS" ("STRATEGY_NAME", "ENTRY_DATE" DESC)
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
