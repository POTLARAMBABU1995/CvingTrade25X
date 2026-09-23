--------------------------------------------------------
--  Backup generated - 2026-03-29 15:01:50
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: PROCEDURE
--  Source object name: PR_SYNC_FACT_OHLCV_FROM_DEV

CREATE OR REPLACE NONEDITIONABLE PROCEDURE "PR_SYNC_FACT_OHLCV_FROM_DEV" (
  p_from_date IN DATE DEFAULT NULL,
  p_to_date   IN DATE DEFAULT NULL
) AS
BEGIN
  PR_SYNC_DIM_SYMBOLS_FROM_DEV;
  PR_MERGE_FACT_OHLCV_FROM_DEV(p_from_date => p_from_date, p_to_date => p_to_date);
  COMMIT;
END;
/
