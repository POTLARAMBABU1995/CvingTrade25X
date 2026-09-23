--------------------------------------------------------
--  Backup generated - 2026-03-29 15:02:02
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: PROCEDURE
--  Source object name: PR_SYNC_NSE_SYMBOL_SECTOR_MAP_FROM_STAGING

CREATE OR REPLACE NONEDITIONABLE PROCEDURE "PR_SYNC_NSE_SYMBOL_SECTOR_MAP_FROM_STAGING" AS
BEGIN
  MERGE INTO NSE_SYMBOL_SECTOR_MAP tgt
  USING (
    WITH ranked AS (
      SELECT
	symbol,
	sector_code,
	source_table,
	ROW_NUMBER() OVER (
	  PARTITION BY symbol
	  ORDER BY sector_priority DESC, sector_code, source_table
	) AS rn
      FROM VW_NSE_CANONICAL_SECTOR_STAGE
    )
    SELECT symbol, sector_code
    FROM ranked
    WHERE rn = 1
  ) src
    ON (UPPER(TRIM(tgt.SYMBOL)) = src.SYMBOL)
  WHEN MATCHED THEN UPDATE SET
    tgt.SECTOR_CODE = src.SECTOR_CODE
  WHERE NVL(tgt.SECTOR_CODE, '~') <> NVL(src.SECTOR_CODE, '~')
  WHEN NOT MATCHED THEN INSERT (SYMBOL, SECTOR_CODE)
  VALUES (src.SYMBOL, src.SECTOR_CODE);

  DELETE FROM NSE_SYMBOL_SECTOR_MAP tgt
   WHERE NOT EXISTS (
     WITH ranked AS (
       SELECT
	 symbol,
	 sector_code,
	 source_table,
	 ROW_NUMBER() OVER (
	   PARTITION BY symbol
	   ORDER BY sector_priority DESC, sector_code, source_table
	 ) AS rn
       FROM VW_NSE_CANONICAL_SECTOR_STAGE
     )
     SELECT 1
     FROM ranked src
     WHERE src.rn = 1
       AND src.symbol = UPPER(TRIM(tgt.SYMBOL))
   );
END;
/
