-- Additive, reviewed migration for reusable sector hierarchy metadata.
-- This script does not drop, rename, or delete any existing object.
SET DEFINE OFF;

DECLARE
  PROCEDURE add_column_if_missing(p_table VARCHAR2, p_column VARCHAR2, p_type VARCHAR2) IS
    n NUMBER;
  BEGIN
    SELECT COUNT(*) INTO n FROM user_tab_columns WHERE table_name = UPPER(p_table) AND column_name = UPPER(p_column);
    IF n = 0 THEN EXECUTE IMMEDIATE 'ALTER TABLE ' || p_table || ' ADD (' || p_column || ' ' || p_type || ')'; END IF;
  END;
BEGIN
  add_column_if_missing('NSE_SECTOR_MASTER', 'PARENT_SECTOR', 'VARCHAR2(100)');
  add_column_if_missing('NSE_SECTOR_MASTER', 'INDUSTRY', 'VARCHAR2(150)');
  add_column_if_missing('NSE_SECTOR_MASTER', 'IS_ACTIVE', 'CHAR(1) DEFAULT ''Y''');
  add_column_if_missing('NSE_SECTOR_MASTER', 'CREATED_AT', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP');
  add_column_if_missing('NSE_SECTOR_MASTER', 'UPDATED_AT', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP');
  add_column_if_missing('NSE_SYMBOL_SECTOR_MAP', 'PARENT_SECTOR', 'VARCHAR2(100)');
  add_column_if_missing('NSE_SYMBOL_SECTOR_MAP', 'INDUSTRY', 'VARCHAR2(150)');
  add_column_if_missing('NSE_SYMBOL_SECTOR_MAP', 'BUSINESS_CLASSIFICATION', 'VARCHAR2(200)');
  add_column_if_missing('NSE_SYMBOL_SECTOR_MAP', 'IS_ACTIVE', 'CHAR(1) DEFAULT ''Y''');
  add_column_if_missing('NSE_SYMBOL_SECTOR_MAP', 'SOURCE', 'VARCHAR2(100)');
  add_column_if_missing('NSE_SYMBOL_SECTOR_MAP', 'CREATED_AT', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP');
  add_column_if_missing('NSE_SYMBOL_SECTOR_MAP', 'UPDATED_AT', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP');
END;
/

UPDATE nse_sector_master SET is_active = NVL(is_active, 'Y'), updated_at = NVL(updated_at, CURRENT_TIMESTAMP);
UPDATE nse_symbol_sector_map SET is_active = NVL(is_active, 'Y'), updated_at = NVL(updated_at, CURRENT_TIMESTAMP);
COMMIT;

DECLARE
  PROCEDURE create_index_if_missing(p_name VARCHAR2, p_sql VARCHAR2) IS n NUMBER;
  BEGIN
    SELECT COUNT(*) INTO n FROM user_indexes WHERE index_name=UPPER(p_name);
    IF n=0 THEN EXECUTE IMMEDIATE p_sql; END IF;
  END;
BEGIN
  create_index_if_missing('IX_NSE_SECTOR_MASTER_HIER', 'CREATE INDEX IX_NSE_SECTOR_MASTER_HIER ON NSE_SECTOR_MASTER (SECTOR_CODE, PARENT_SECTOR, INDUSTRY, IS_ACTIVE)');
  create_index_if_missing('IX_NSE_SYMBOL_SECTOR_HIER', 'CREATE INDEX IX_NSE_SYMBOL_SECTOR_HIER ON NSE_SYMBOL_SECTOR_MAP (SYMBOL, SECTOR_CODE, IS_ACTIVE)');
END;
/
