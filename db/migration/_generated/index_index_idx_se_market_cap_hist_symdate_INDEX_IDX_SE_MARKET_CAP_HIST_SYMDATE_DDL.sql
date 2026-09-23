--------------------------------------------------------
--  Backup generated - 2026-03-29 15:41:38
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: IDX_SE_MARKET_CAP_HIST_SYMDATE

CREATE INDEX "IDX_SE_MARKET_CAP_HIST_SYMDATE" ON "CVING_NSE_MARKET_CAP_HIST" ("SYMBOL", "TRADE_DATE" DESC)
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
