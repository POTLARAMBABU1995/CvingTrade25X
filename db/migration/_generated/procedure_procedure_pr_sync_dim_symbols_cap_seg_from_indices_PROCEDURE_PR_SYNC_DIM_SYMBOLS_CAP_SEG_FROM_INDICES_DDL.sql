--------------------------------------------------------
--  Backup generated - 2026-03-29 15:01:34
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: PROCEDURE
--  Source object name: PR_SYNC_DIM_SYMBOLS_CAP_SEG_FROM_INDICES

CREATE OR REPLACE NONEDITIONABLE PROCEDURE "PR_SYNC_DIM_SYMBOLS_CAP_SEG_FROM_INDICES" AS
BEGIN
  MERGE INTO DIM_SYMBOLS tgt
  USING VW_SYMBOL_CAP_BUCKET src
    ON (UPPER(TRIM(tgt.SYMBOL)) = src.SYMBOL)
  WHEN MATCHED THEN UPDATE SET
    tgt.MARKET_CAP_SEG = src.CAP_BUCKET,
    tgt.IS_ACTIVE = 'Y',
    tgt.LAST_UPDATED = SYSTIMESTAMP
  WHERE NVL(tgt.MARKET_CAP_SEG, '~') <> NVL(src.CAP_BUCKET, '~')
     OR NVL(tgt.IS_ACTIVE, 'N') <> 'Y';
END;
/
