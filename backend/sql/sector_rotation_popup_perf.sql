-- Sector rotation popup performance objects (Oracle 19c, idempotent).
-- Creates/updates VW_SYMBOL_CAP_BUCKET and critical indexes for fast popup queries.

SET DEFINE OFF;

PROMPT [1/2] Create or replace VW_SYMBOL_CAP_BUCKET ...
DECLARE
  v_union_sql CLOB := '';
  v_exists    NUMBER := 0;

  PROCEDURE append_source(p_table VARCHAR2, p_bucket VARCHAR2, p_rank NUMBER) IS
  BEGIN
    SELECT COUNT(*)
      INTO v_exists
      FROM user_tables
     WHERE table_name = UPPER(p_table);

    IF v_exists > 0 THEN
      IF NVL(LENGTH(v_union_sql), 0) > 0 THEN
        v_union_sql := v_union_sql || ' UNION ALL ';
      END IF;

      v_union_sql := v_union_sql
        || 'SELECT DISTINCT UPPER(TRIM(symbol)) AS symbol, '''
        || p_bucket
        || ''' AS cap_bucket, '
        || TO_CHAR(p_rank)
        || ' AS cap_rank FROM '
        || p_table
        || ' WHERE symbol IS NOT NULL';
    END IF;
  END;
BEGIN
  append_source('NSE_NIFTY50_LARGECAP', 'LARGE', 1);
  append_source('NSE_NIFTY100_LARGECAP', 'LARGE', 1);
  append_source('NIFTY_NEXT50_MIDCAP', 'LARGE', 1);
  append_source('NSE_NIFTY250_MIDCAP', 'MID', 2);
  append_source('NSE_NIFTY150_MIDCAP', 'MID', 2);
  append_source('NSE_NIFTY200_MIDCAP', 'MID', 2);
  append_source('NSE_NIFTY250_SMALLCAP', 'SMALL', 3);
  append_source('NSE_NIFTY500_SMALLCAP', 'SMALL', 3);

  IF NVL(LENGTH(v_union_sql), 0) = 0 THEN
    EXECUTE IMMEDIATE q'[
      CREATE OR REPLACE VIEW VW_SYMBOL_CAP_BUCKET AS
      SELECT
        CAST(NULL AS VARCHAR2(64)) AS symbol,
        CAST(NULL AS VARCHAR2(10)) AS cap_bucket
      FROM dual
      WHERE 1 = 0
    ]';
  ELSE
    EXECUTE IMMEDIATE
      'CREATE OR REPLACE VIEW VW_SYMBOL_CAP_BUCKET AS '
      || 'SELECT symbol, '
      || '       MIN(cap_bucket) KEEP (DENSE_RANK FIRST ORDER BY cap_rank) AS cap_bucket '
      || 'FROM (' || v_union_sql || ') '
      || 'GROUP BY symbol';
  END IF;
END;
/

PROMPT [2/2] Create indexes (if missing) ...
DECLARE
  PROCEDURE create_index_if_missing(p_index_name VARCHAR2, p_sql VARCHAR2) IS
    v_exists NUMBER := 0;
  BEGIN
    SELECT COUNT(*)
      INTO v_exists
      FROM user_indexes
     WHERE index_name = UPPER(p_index_name);

    IF v_exists = 0 THEN
      EXECUTE IMMEDIATE p_sql;
    END IF;
  EXCEPTION
    WHEN OTHERS THEN
      IF SQLCODE NOT IN (-955, -1408) THEN
        RAISE;
      END IF;
  END;

  PROCEDURE create_symbol_index_if_table_exists(p_table_name VARCHAR2, p_index_name VARCHAR2) IS
    v_exists NUMBER := 0;
  BEGIN
    SELECT COUNT(*)
      INTO v_exists
      FROM user_tables
     WHERE table_name = UPPER(p_table_name);

    IF v_exists > 0 THEN
      create_index_if_missing(
        p_index_name,
        'CREATE INDEX ' || p_index_name || ' ON ' || p_table_name || ' (SYMBOL)'
      );
    END IF;
  END;
BEGIN
  create_index_if_missing(
    'IX_MV_SECTOR_UI_SECTOR_SYMBOL',
    'CREATE INDEX IX_MV_SECTOR_UI_SECTOR_SYMBOL ON MV_NSE_SECTOR_UI_SNAPSHOT (SECTOR, SYMBOL)'
  );

  create_index_if_missing(
    'IX_MV_SECTOR_UI_SECTOR_CLOSE',
    'CREATE INDEX IX_MV_SECTOR_UI_SECTOR_CLOSE ON MV_NSE_SECTOR_UI_SNAPSHOT (SECTOR, CLOSE_PRICE)'
  );

  create_index_if_missing(
    'IX_NSE500_RAW_SYM_TRADEDATE',
    'CREATE INDEX IX_NSE500_RAW_SYM_TRADEDATE ON NSE_NIFTY500_DAILY_RAW_DATA_DEV (SYMBOL, TRADING_DATE DESC)'
  );

  create_symbol_index_if_table_exists('NSE_NIFTY50_LARGECAP', 'IX_N50_LCAP_SYMBOL');
  create_symbol_index_if_table_exists('NSE_NIFTY100_LARGECAP', 'IX_N100_LCAP_SYMBOL');
  create_symbol_index_if_table_exists('NIFTY_NEXT50_MIDCAP', 'IX_NEXT50_MCAP_SYMBOL');
  create_symbol_index_if_table_exists('NSE_NIFTY250_MIDCAP', 'IX_N250_MCAP_SYMBOL');
  create_symbol_index_if_table_exists('NSE_NIFTY150_MIDCAP', 'IX_N150_MCAP_SYMBOL');
  create_symbol_index_if_table_exists('NSE_NIFTY200_MIDCAP', 'IX_N200_MCAP_SYMBOL');
  create_symbol_index_if_table_exists('NSE_NIFTY250_SMALLCAP', 'IX_N250_SCAP_SYMBOL');
  create_symbol_index_if_table_exists('NSE_NIFTY500_SMALLCAP', 'IX_N500_SCAP_SYMBOL');
END;
/

PROMPT Sector rotation popup performance objects complete.
