PROMPT Validating Education & E-Learning sector staging table
SET DEFINE OFF;

PROMPT [1] Table presence
SELECT table_name
FROM user_tables
WHERE table_name IN ('NSE_NIFTY_EDUCATION_E_LEARNING_STAGING')
ORDER BY table_name;

PROMPT [2] Master code
SELECT sector_code, sector_name, index_code, display_order
FROM nse_sector_master
WHERE sector_code = 'EDUCATION_E_LEARNING';

PROMPT [3] Staging count
SELECT 'NSE_NIFTY_EDUCATION_E_LEARNING_STAGING' AS table_name, COUNT(*) AS row_count
FROM NSE_NIFTY_EDUCATION_E_LEARNING_STAGING;

PROMPT [4] Duplicate symbol check
SELECT symbol, COUNT(*) AS duplicate_count
FROM NSE_NIFTY_EDUCATION_E_LEARNING_STAGING
GROUP BY symbol
HAVING COUNT(*) > 1;

PROMPT [5] Cross-sector duplicate symbol check
SELECT symbol, sector_code
FROM NSE_SYMBOL_SECTOR_MAP
WHERE symbol IN (SELECT symbol FROM NSE_NIFTY_EDUCATION_E_LEARNING_STAGING)
  AND sector_code <> 'EDUCATION_E_LEARNING';

PROMPT [6] Join to DEV raw table
SELECT COUNT(DISTINCT r.symbol) AS joined_symbols_count
FROM NSE_NIFTY_EDUCATION_E_LEARNING_STAGING r
JOIN NSE_NIFTY500_DAILY_RAW_DATA_DEV d
  ON REPLACE(REPLACE(REPLACE(REPLACE(UPPER(TRIM(d.symbol)), 'NSE:', ''), 'BSE:', ''), '-EQ', ''), ' ', '') = 
     REPLACE(REPLACE(REPLACE(REPLACE(UPPER(TRIM(r.symbol)), 'NSE:', ''), 'BSE:', ''), '-EQ', ''), ' ', '');

EXIT;
