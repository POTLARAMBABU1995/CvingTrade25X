--------------------------------------------------------
--  Backup generated - 2026-03-29 15:36:07
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: IDX_BHRAMHASTRA_BT_STATUS

CREATE INDEX "IDX_BHRAMHASTRA_BT_STATUS" ON "BHRAMHASTRA_BACKTESTING_DATA" ("STATUS")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
