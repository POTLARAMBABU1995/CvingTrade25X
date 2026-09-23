--------------------------------------------------------
--  Backup generated - 2026-03-29 15:01:41
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: PROCEDURE
--  Source object name: PR_SYNC_DIM_SYMBOLS_FROM_DEV

CREATE OR REPLACE NONEDITIONABLE PROCEDURE "PR_SYNC_DIM_SYMBOLS_FROM_DEV" (
  p_default_sector	   IN VARCHAR2 DEFAULT 'UNASSIGNED',
  p_default_market_cap_seg IN VARCHAR2 DEFAULT NULL
) AS
BEGIN
  LOCK TABLE DIM_SYMBOLS IN SHARE ROW EXCLUSIVE MODE;

  UPDATE DIM_SYMBOLS s
     SET s.IS_ACTIVE = 'Y',
	 s.LAST_UPDATED = SYSTIMESTAMP
   WHERE NVL(s.IS_ACTIVE, 'N') <> 'Y'
     AND EXISTS (
       SELECT 1
       FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV d
       WHERE UPPER(TRIM(d.SYMBOL)) = UPPER(TRIM(s.SYMBOL))
     );

  INSERT INTO DIM_SYMBOLS (
    SYMBOL_ID,
    SYMBOL,
    SECTOR,
    MARKET_CAP_SEG,
    IS_ACTIVE,
    COMPANY_NAME,
    LAST_UPDATED
  )
  WITH new_symbols AS (
    SELECT DISTINCT UPPER(TRIM(d.SYMBOL)) AS symbol
    FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV d
    LEFT JOIN DIM_SYMBOLS s
      ON UPPER(TRIM(s.SYMBOL)) = UPPER(TRIM(d.SYMBOL))
    WHERE d.SYMBOL IS NOT NULL
      AND s.SYMBOL_ID IS NULL
  ),
  base_id AS (
    SELECT NVL(MAX(SYMBOL_ID), 0) AS max_symbol_id
    FROM DIM_SYMBOLS
  )
  SELECT
    base_id.max_symbol_id + ROW_NUMBER() OVER (ORDER BY ns.symbol) AS symbol_id,
    ns.symbol,
    p_default_sector,
    p_default_market_cap_seg,
    'Y',
    ns.symbol,
    SYSTIMESTAMP
  FROM new_symbols ns
  CROSS JOIN base_id;
END;
/
