SET DEFINE OFF;
SELECT sector_code, sector_name, parent_sector, industry, is_active FROM nse_sector_master WHERE sector_code='DAIRY_MILK_PRODUCTS';
SELECT symbol, sector_code, parent_sector, industry, business_classification, is_active FROM nse_symbol_sector_map WHERE sector_code='DAIRY_MILK_PRODUCTS' ORDER BY symbol;
SELECT UPPER(TRIM(symbol)) symbol, COUNT(*) duplicate_count FROM nse_symbol_sector_map WHERE sector_code='DAIRY_MILK_PRODUCTS' AND is_active='Y' GROUP BY UPPER(TRIM(symbol)) HAVING COUNT(*)>1;
SELECT m.symbol FROM nse_symbol_sector_map m WHERE m.sector_code='DAIRY_MILK_PRODUCTS' AND m.is_active='Y' AND NOT EXISTS (SELECT 1 FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV d WHERE UPPER(TRIM(d.symbol))=UPPER(TRIM(m.symbol)));
SELECT UPPER(TRIM(symbol)) symbol, MAX(trading_date) latest_trading_date FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV WHERE UPPER(TRIM(symbol)) IN ('HATSUN','DODLA','HERITGFOOD','PARAGMILK','KWIL','VADILALIND') GROUP BY UPPER(TRIM(symbol));
