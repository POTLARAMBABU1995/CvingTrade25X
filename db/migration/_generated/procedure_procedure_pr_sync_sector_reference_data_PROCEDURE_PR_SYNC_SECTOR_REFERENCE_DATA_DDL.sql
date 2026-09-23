--------------------------------------------------------
--  Backup generated - 2026-03-29 15:02:20
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: PROCEDURE
--  Source object name: PR_SYNC_SECTOR_REFERENCE_DATA

CREATE OR REPLACE NONEDITIONABLE PROCEDURE "PR_SYNC_SECTOR_REFERENCE_DATA" AS
BEGIN
  PR_SYNC_DIM_SYMBOLS_CAP_SEG_FROM_INDICES;
  PR_SYNC_NSE_SYMBOL_SECTOR_MAP_FROM_STAGING;
  COMMIT;
END;
/
