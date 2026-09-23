PROMPT Creating sector reference sync procedures and alias-safe views.

SET DEFINE OFF;

PROMPT [1/5] Create or replace VW_SYMBOL_CAP_BUCKET ...
DECLARE
  v_union_sql CLOB := '';
  v_exists    NUMBER := 0;

  PROCEDURE append_cap_source(p_table VARCHAR2) IS
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
        || 'SELECT UPPER(TRIM(symbol)) AS symbol, ''LARGE'' AS cap_bucket, 1 AS cap_rank FROM '
        || p_table
        || ' WHERE symbol IS NOT NULL AND NVL(UPPER(TRIM(LARGE_INDEX)), ''N'') = ''Y'' '
        || ' UNION ALL SELECT UPPER(TRIM(symbol)) AS symbol, ''MID'' AS cap_bucket, 2 AS cap_rank FROM '
        || p_table
        || ' WHERE symbol IS NOT NULL AND NVL(UPPER(TRIM(MID_INDEX)), ''N'') = ''Y'' '
        || ' UNION ALL SELECT UPPER(TRIM(symbol)) AS symbol, ''SMALL'' AS cap_bucket, 3 AS cap_rank FROM '
        || p_table
        || ' WHERE symbol IS NOT NULL AND NVL(UPPER(TRIM(SMALL_INDEX)), ''N'') = ''Y'' ';
    END IF;
  END;
BEGIN
  append_cap_source('NSE_NIFTY50_LARGECAP');
  append_cap_source('NSE_NIFTY100_LARGECAP');
  append_cap_source('NSE_NIFTY150_MIDCAP');
  append_cap_source('NSE_NIFTY200_MIDCAP');
  append_cap_source('NSE_NIFTY250_MIDCAP');
  append_cap_source('NSE_NIFTY250_SMALLCAP');
  append_cap_source('NSE_NIFTY500_SMALLCAP');

  IF NVL(LENGTH(v_union_sql), 0) = 0 THEN
    EXECUTE IMMEDIATE q'[
      CREATE OR REPLACE NONEDITIONABLE VIEW VW_SYMBOL_CAP_BUCKET AS
      SELECT
        CAST(NULL AS VARCHAR2(64)) AS symbol,
        CAST(NULL AS VARCHAR2(10)) AS cap_bucket
      FROM dual
      WHERE 1 = 0
    ]';
  ELSE
    EXECUTE IMMEDIATE
      'CREATE OR REPLACE NONEDITIONABLE VIEW VW_SYMBOL_CAP_BUCKET AS '
      || 'WITH cap_union AS (' || v_union_sql || ') '
      || 'SELECT symbol, MIN(cap_bucket) KEEP (DENSE_RANK FIRST ORDER BY cap_rank) AS cap_bucket '
      || 'FROM cap_union GROUP BY symbol';
  END IF;
END;
/

PROMPT [2/5] Create or replace VW_NSE_CANONICAL_SECTOR_STAGE ...
DECLARE
  v_union_sql CLOB := '';
  v_exists    NUMBER := 0;

  PROCEDURE append_stage_source(p_table VARCHAR2, p_sector_code VARCHAR2, p_priority NUMBER) IS
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
        || p_sector_code
        || ''' AS sector_code, '
        || TO_CHAR(p_priority)
        || ' AS sector_priority, '''
        || p_table
        || ''' AS source_table '
        || 'FROM '
        || p_table
        || ' WHERE symbol IS NOT NULL';
    END IF;
  END;
BEGIN
  append_stage_source('NSE_NIFTY_PRIVATE_BANK_STAGING', 'PVT_BANK', 100);
  append_stage_source('NSE_NIFTY_PSU_BANK_STAGING', 'PSU_BANK', 100);
  append_stage_source('NSE_NIFTY_PHARMA_STAGING', 'PHARMA', 100);

  append_stage_source('NSE_NIFTY_MIDSMALL_HEALTHCARE_STAGING', 'MID_HEALTH', 95);
  append_stage_source('NSE_NIFTY_MIDSMALL_FINANCIAL_SERVICES_STAGING', 'MID_FIN', 95);
  append_stage_source('NSE_NIFTY_MIDSMALL_IT_TELECOM_STAGING', 'MID_IT_TEL', 95);

  append_stage_source('NSE_NIFTY_FINANCIAL_SERVICES_25_50_STAGING', 'FIN_25_50', 90);
  append_stage_source('NSE_NIFTY_FINANCIAL_SERVICES_EX_BANK_STAGING', 'FIN_EX_BANK', 85);
  append_stage_source('NSE_NIFTY_OIL_AND_GAS_STAGING', 'OIL_GAS', 85);
  append_stage_source('NSE_NIFTY_OIL_GAS_STAGING', 'OIL_GAS', 85);

  append_stage_source('NSE_NIFTY_ENERGY_STAGING', 'ENERGY', 80);

  append_stage_source('NSE_NIFTY_HEALTHCARE_INDEX_STAGING', 'HEALTH', 75);
  append_stage_source('NSE_NIFTY500_HEALTHCARE_STAGING', 'HEALTH', 75);
  append_stage_source('NSE_NIFTY_HEALTHCARE_STAGING', 'HEALTH', 75);

  append_stage_source('NSE_NIFTY_FINANCIAL_SERVICES_STAGING', 'FIN_SERV', 70);
  append_stage_source('NSE_NIFTY_BANK_STAGING', 'BANK', 65);

  append_stage_source('NSE_NIFTY_AUTO_STAGING', 'AUTO', 60);
  append_stage_source('NSE_NIFTY_CHEMICALS_STAGING', 'CHEM', 60);
  append_stage_source('NSE_NIFTY_CONSUMER_DURABLES_STAGING', 'CONS_DUR', 60);
  append_stage_source('NSE_NIFTY_FMCG_STAGING', 'FMCG', 60);
  append_stage_source('NSE_NIFTY_IT_STAGING', 'IT', 60);
  append_stage_source('NSE_NIFTY_MEDIA_STAGING', 'MEDIA', 60);
  append_stage_source('NSE_NIFTY_METAL_STAGING', 'METAL', 60);
  append_stage_source('NSE_NIFTY_REALTY_STAGING', 'REALTY', 60);
  append_stage_source('NSE_NIFTY_REALITY_STAGING', 'REALTY', 60);

  IF NVL(LENGTH(v_union_sql), 0) = 0 THEN
    EXECUTE IMMEDIATE q'[
      CREATE OR REPLACE NONEDITIONABLE VIEW VW_NSE_CANONICAL_SECTOR_STAGE AS
      SELECT
        CAST(NULL AS VARCHAR2(64)) AS symbol,
        CAST(NULL AS VARCHAR2(32)) AS sector_code,
        CAST(NULL AS NUMBER) AS sector_priority,
        CAST(NULL AS VARCHAR2(128)) AS source_table
      FROM dual
      WHERE 1 = 0
    ]';
  ELSE
    EXECUTE IMMEDIATE
      'CREATE OR REPLACE NONEDITIONABLE VIEW VW_NSE_CANONICAL_SECTOR_STAGE AS '
      || 'WITH stage_union AS (' || v_union_sql || ') '
      || 'SELECT symbol, sector_code, sector_priority, source_table '
      || 'FROM stage_union';
  END IF;
END;
/

PROMPT [3/5] Create or replace PR_SYNC_DIM_SYMBOLS_CAP_SEG_FROM_INDICES ...
CREATE OR REPLACE NONEDITIONABLE PROCEDURE PR_SYNC_DIM_SYMBOLS_CAP_SEG_FROM_INDICES AS
BEGIN
  MERGE INTO DIM_SYMBOLS tgt
  USING VW_SYMBOL_CAP_BUCKET src
    ON (UPPER(TRIM(tgt.SYMBOL)) = src.SYMBOL)
  WHEN MATCHED THEN UPDATE SET
    tgt.MARKET_CAP_SEG = src.CAP_BUCKET,
    tgt.IS_ACTIVE = 'Y',
    tgt.LAST_UPDATED = SYSTIMESTAMP
  WHERE NVL(tgt.MARKET_CAP_SEG, '~') <> NVL(src.CAP_BUCKET, '~')
     OR NVL(tgt.IS_ACTIVE, 'N') <> 'Y';
END;
/

PROMPT [4/5] Create or replace PR_SYNC_NSE_SYMBOL_SECTOR_MAP_FROM_STAGING ...
CREATE OR REPLACE NONEDITIONABLE PROCEDURE PR_SYNC_NSE_SYMBOL_SECTOR_MAP_FROM_STAGING AS
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

PROMPT [5/5] Create or replace PR_SYNC_SECTOR_REFERENCE_DATA ...
CREATE OR REPLACE NONEDITIONABLE PROCEDURE PR_SYNC_SECTOR_REFERENCE_DATA AS
BEGIN
  PR_SYNC_DIM_SYMBOLS_CAP_SEG_FROM_INDICES;
  PR_SYNC_NSE_SYMBOL_SECTOR_MAP_FROM_STAGING;
  COMMIT;
END;
/
