--------------------------------------------------------
--  Backup generated - 2026-03-29 15:41:55
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: INDEX
--  Source object name: IDX_SE_MARKET_CAP_HIST_TRDSRC

CREATE INDEX "IDX_SE_MARKET_CAP_HIST_TRDSRC" ON "CVING_NSE_MARKET_CAP_HIST" ("TRADE_DATE", "SOURCE_NAME", "FETCH_STATUS")
  PCTFREE 10 INITRANS 2 MAXTRANS 255 COMPUTE STATISTICS
  TABLESPACE CVING_DATA ;
