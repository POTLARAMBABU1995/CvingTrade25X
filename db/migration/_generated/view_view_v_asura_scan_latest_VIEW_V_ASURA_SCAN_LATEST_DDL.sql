--------------------------------------------------------
--  Backup generated - 2026-03-29 15:04:59
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: VIEW
--  Source object name: V_ASURA_SCAN_LATEST

CREATE OR REPLACE FORCE NONEDITIONABLE VIEW "V_ASURA_SCAN_LATEST" ("RUN_DATE", "STOCK", "BUYING_DATE", "BUYING_PRICE", "CREATED_TS") AS
  SELECT "RUN_DATE","STOCK","BUYING_DATE","BUYING_PRICE","CREATED_TS"
FROM ASURA_SCAN_DAILY_FACT
WHERE RUN_DATE = (SELECT MAX(RUN_DATE) FROM ASURA_SCAN_DAILY_FACT);
