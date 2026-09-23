-- Optional performance indexes for DELIVERY technicals queries.
-- Safe to run multiple times; creates indexes only when a matching leading-column index is missing.

DECLARE
  v_table_name      VARCHAR2(128) := 'CVING_NSE_DELIVERY_HIST';
  v_date_col        VARCHAR2(128);
  v_has_symbol_idx  NUMBER := 0;
  v_has_date_idx    NUMBER := 0;
  v_has_pair_idx    NUMBER := 0;
BEGIN
  SELECT CASE
           WHEN EXISTS (
             SELECT 1 FROM USER_TAB_COLUMNS
             WHERE TABLE_NAME = v_table_name AND COLUMN_NAME = 'TRADING_DATE'
           ) THEN 'TRADING_DATE'
           WHEN EXISTS (
             SELECT 1 FROM USER_TAB_COLUMNS
             WHERE TABLE_NAME = v_table_name AND COLUMN_NAME = 'TRADE_DATE'
           ) THEN 'TRADE_DATE'
           ELSE NULL
         END
    INTO v_date_col
    FROM DUAL;

  IF v_date_col IS NULL THEN
    RAISE_APPLICATION_ERROR(-20001, 'Trading date column not found on CVING_NSE_DELIVERY_HIST.');
  END IF;

  SELECT COUNT(*)
    INTO v_has_symbol_idx
    FROM USER_INDEXES ui
   WHERE ui.TABLE_NAME = v_table_name
     AND EXISTS (
           SELECT 1
             FROM USER_IND_COLUMNS uic
            WHERE uic.INDEX_NAME = ui.INDEX_NAME
              AND uic.COLUMN_POSITION = 1
              AND uic.COLUMN_NAME = 'SYMBOL'
         );

  SELECT COUNT(*)
    INTO v_has_date_idx
    FROM USER_INDEXES ui
   WHERE ui.TABLE_NAME = v_table_name
     AND EXISTS (
           SELECT 1
             FROM USER_IND_COLUMNS uic
            WHERE uic.INDEX_NAME = ui.INDEX_NAME
              AND uic.COLUMN_POSITION = 1
              AND uic.COLUMN_NAME = v_date_col
         );

  SELECT COUNT(*)
    INTO v_has_pair_idx
    FROM USER_INDEXES ui
   WHERE ui.TABLE_NAME = v_table_name
     AND EXISTS (
           SELECT 1
             FROM USER_IND_COLUMNS c1
            WHERE c1.INDEX_NAME = ui.INDEX_NAME
              AND c1.COLUMN_POSITION = 1
              AND c1.COLUMN_NAME = 'SYMBOL'
         )
     AND EXISTS (
           SELECT 1
             FROM USER_IND_COLUMNS c2
            WHERE c2.INDEX_NAME = ui.INDEX_NAME
              AND c2.COLUMN_POSITION = 2
              AND c2.COLUMN_NAME = v_date_col
         );

  IF v_has_symbol_idx = 0 THEN
    EXECUTE IMMEDIATE 'CREATE INDEX IDX_NSE_DELIVERY_SYMBOL ON CVING_NSE_DELIVERY_HIST (SYMBOL)';
  END IF;

  IF v_has_date_idx = 0 THEN
    EXECUTE IMMEDIATE 'CREATE INDEX IDX_NSE_DELIVERY_TDATE ON CVING_NSE_DELIVERY_HIST (' || v_date_col || ')';
  END IF;

  IF v_has_pair_idx = 0 THEN
    EXECUTE IMMEDIATE 'CREATE INDEX IDX_NSE_DELIVERY_SYMBOL_TDATE ON CVING_NSE_DELIVERY_HIST (SYMBOL, ' || v_date_col || ')';
  END IF;
END;
/
