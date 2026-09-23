-- Idempotent Dairy & Milk Products seed. Run migration first.
SET DEFINE OFF;

DECLARE
  n NUMBER;
BEGIN
  SELECT COUNT(*) INTO n FROM user_tables WHERE table_name='NSE_NIFTY_DAIRY_MILK_PRODUCTS_STAGING';
  IF n=0 THEN
    EXECUTE IMMEDIATE 'CREATE TABLE NSE_NIFTY_DAIRY_MILK_PRODUCTS_STAGING AS SELECT * FROM NSE_NIFTY_FMCG_STAGING WHERE 1=0';
  END IF;
END;
/ 

INSERT INTO NSE_NIFTY_DAIRY_MILK_PRODUCTS_STAGING (symbol)
SELECT symbol FROM (
  SELECT 'HATSUN' symbol FROM dual UNION ALL SELECT 'DODLA' FROM dual UNION ALL SELECT 'HERITGFOOD' FROM dual
  UNION ALL SELECT 'PARAGMILK' FROM dual UNION ALL SELECT 'KWIL' FROM dual UNION ALL SELECT 'VADILALIND' FROM dual
) x
WHERE EXISTS (SELECT 1 FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV d WHERE UPPER(TRIM(d.symbol))=x.symbol)
  AND NOT EXISTS (SELECT 1 FROM NSE_NIFTY_DAIRY_MILK_PRODUCTS_STAGING s WHERE UPPER(TRIM(s.symbol))=x.symbol);

MERGE INTO nse_sector_master t USING (
  SELECT 'DAIRY_MILK_PRODUCTS' sector_code, 'DAIRY & MILK PRODUCTS' sector_name,
         'FMCG' parent_sector, 'FOOD PRODUCTS' industry, 999 display_order FROM dual
) s ON (t.sector_code = s.sector_code)
WHEN MATCHED THEN UPDATE SET t.sector_name=s.sector_name, t.parent_sector=s.parent_sector,
  t.industry=s.industry, t.is_active='Y', t.updated_at=CURRENT_TIMESTAMP
WHEN NOT MATCHED THEN INSERT (sector_code, sector_name, parent_sector, industry, display_order, is_active, created_at, updated_at)
  VALUES (s.sector_code, s.sector_name, s.parent_sector, s.industry, s.display_order, 'Y', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

MERGE INTO nse_symbol_sector_map t USING (
  SELECT symbol, sector_code, parent_sector, industry, business_classification FROM (
    SELECT 'HATSUN' symbol, 'Integrated Dairy & Ice Cream' business_classification FROM dual UNION ALL
    SELECT 'DODLA', 'Milk Processing & Dairy Products' FROM dual UNION ALL
    SELECT 'HERITGFOOD', 'Milk Processing & Value-Added Dairy' FROM dual UNION ALL
    SELECT 'PARAGMILK', 'Value-Added Dairy Products' FROM dual UNION ALL
    SELECT 'KWIL', 'Ice Cream & Frozen Desserts' FROM dual UNION ALL
    SELECT 'VADILALIND', 'Ice Cream & Frozen Foods' FROM dual
  ) x CROSS JOIN (SELECT 'DAIRY_MILK_PRODUCTS' sector_code, 'FMCG' parent_sector, 'FOOD PRODUCTS' industry FROM dual) h
  WHERE EXISTS (SELECT 1 FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV d WHERE UPPER(TRIM(d.symbol))=x.symbol)
) s ON (UPPER(TRIM(t.symbol))=s.symbol AND t.sector_code=s.sector_code)
WHEN MATCHED THEN UPDATE SET t.parent_sector=s.parent_sector, t.industry=s.industry,
  t.business_classification=s.business_classification, t.is_active='Y', t.source='MANUAL_SECTOR_ENHANCEMENT', t.updated_at=CURRENT_TIMESTAMP
WHEN NOT MATCHED THEN INSERT (symbol, sector_code, parent_sector, industry, business_classification, is_active, source, created_at, updated_at)
  VALUES (s.symbol, s.sector_code, s.parent_sector, s.industry, s.business_classification, 'Y', 'MANUAL_SECTOR_ENHANCEMENT', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

COMMIT;

-- Report requested symbols absent from the active raw NSE-backed universe.
SELECT symbol FROM (SELECT 'HATSUN' symbol FROM dual UNION ALL SELECT 'DODLA' FROM dual UNION ALL SELECT 'HERITGFOOD' FROM dual UNION ALL SELECT 'PARAGMILK' FROM dual UNION ALL SELECT 'KWIL' FROM dual UNION ALL SELECT 'VADILALIND' FROM dual)
WHERE NOT EXISTS (SELECT 1 FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV d WHERE UPPER(TRIM(d.symbol))=symbol);
