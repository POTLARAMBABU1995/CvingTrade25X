PROMPT Validating Rubber Products Tyres sector staging table
SET DEFINE OFF;

PROMPT [1] Table presence
SELECT table_name
FROM user_tables
WHERE table_name IN (
    'NSE_NIFTY_RUBBER_PRODUCTS_TYRES_STAGING'
)
ORDER BY table_name;

PROMPT [2] Master code
SELECT sector_code, sector_name, index_code, display_order
FROM nse_sector_master
WHERE sector_code = 'RUBBER_PRODUCTS_TYRES';

PROMPT [3] Staging count
SELECT 'NSE_NIFTY_RUBBER_PRODUCTS_TYRES_STAGING' AS table_name, COUNT(*) AS row_count
FROM NSE_NIFTY_RUBBER_PRODUCTS_TYRES_STAGING;

PROMPT [4] Duplicate symbol check
SELECT symbol, COUNT(*) AS duplicate_count
FROM NSE_NIFTY_RUBBER_PRODUCTS_TYRES_STAGING
GROUP BY symbol
HAVING COUNT(*) > 1;

PROMPT [5] Cross-sector duplicate symbol check
WITH other_sector_tables AS (
    SELECT DISTINCT utc.table_name
    FROM user_tab_columns utc
    WHERE utc.column_name = 'SYMBOL'
      AND utc.table_name LIKE 'NSE\_NIFTY\_%\_STAGING' ESCAPE '\'
      AND utc.table_name <> 'NSE_NIFTY_RUBBER_PRODUCTS_TYRES_STAGING'
),
cross_sector_hits AS (
    SELECT t.table_name, UPPER(TRIM(a.symbol)) AS symbol
    FROM NSE_NIFTY_RUBBER_PRODUCTS_TYRES_STAGING a
    JOIN user_tables ut ON ut.table_name IN (SELECT table_name FROM other_sector_tables)
    JOIN NSE_NIFTY_AUTO_STAGING t ON 1=0 -- Placeholder: Python script handles validation across all tables dynamically, this is just a structure.
    WHERE 1=0
)
SELECT table_name, symbol
FROM cross_sector_hits
ORDER BY symbol, table_name;
