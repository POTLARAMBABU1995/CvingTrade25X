PROMPT Validate sector reference sync procedures and alias-safe views.

SELECT object_name, object_type, status
FROM user_objects
WHERE object_name IN (
  'VW_SYMBOL_CAP_BUCKET',
  'VW_NSE_CANONICAL_SECTOR_STAGE',
  'PR_SYNC_DIM_SYMBOLS_CAP_SEG_FROM_INDICES',
  'PR_SYNC_NSE_SYMBOL_SECTOR_MAP_FROM_STAGING',
  'PR_SYNC_SECTOR_REFERENCE_DATA'
)
ORDER BY object_type, object_name;

SELECT cap_bucket, COUNT(*) AS symbol_count
FROM VW_SYMBOL_CAP_BUCKET
GROUP BY cap_bucket
ORDER BY cap_bucket;

SELECT source_table, sector_code, COUNT(*) AS symbol_count
FROM VW_NSE_CANONICAL_SECTOR_STAGE
GROUP BY source_table, sector_code
ORDER BY source_table, sector_code;

SELECT sector_code, COUNT(*) AS symbol_count
FROM NSE_SYMBOL_SECTOR_MAP
GROUP BY sector_code
ORDER BY sector_code;

SELECT COUNT(*) AS null_market_cap_seg_count
FROM DIM_SYMBOLS
WHERE SYMBOL IN (SELECT symbol FROM VW_SYMBOL_CAP_BUCKET)
  AND MARKET_CAP_SEG IS NULL;

SELECT *
FROM (
  SELECT symbol, sector_code
  FROM NSE_SYMBOL_SECTOR_MAP
  ORDER BY sector_code, symbol
)
WHERE ROWNUM <= 50;
