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
  append_cap_source('NIFTY_NEXT50_MIDCAP');
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
  append_stage_source('NSE_NIFTY_AUTO_COMPONENTS_EQUIPMENTS_STAGING', 'AUTO_COMPONENTS_EQUIPMENTS', 60);
  append_stage_source('NSE_NIFTY_AUTO_ANCILLARIES_STAGING', 'AUTO_ANCILLARIES', 60);
  append_stage_source('NSE_NIFTY_CAPITAL_GOODS_STAGING', 'CAPITAL_GOODS', 60);
  append_stage_source('NSE_NIFTY_CHEMICALS_STAGING', 'CHEMICALS', 60);
  append_stage_source('NSE_NIFTY_SPECIALTY_CHEMICALS_STAGING', 'SPECIALTY_CHEMICALS', 60);
  append_stage_source('NSE_NIFTY_PETROCHEMICALS_STAGING', 'PETROCHEMICALS', 60);
  append_stage_source('NSE_NIFTY_PAINTS_STAGING', 'PAINTS', 60);
  append_stage_source('NSE_NIFTY_PLASTIC_PRODUCTS_STAGING', 'PLASTIC_PRODUCTS', 60);
  append_stage_source('NSE_NIFTY_EXPLOSIVES_STAGING', 'EXPLOSIVES', 60);
  append_stage_source('NSE_NIFTY_ABRASIVES_STAGING', 'ABRASIVES', 60);
  append_stage_source('NSE_NIFTY_ELECTRODES_REFRACTORIES_STAGING', 'ELECTRODES_REFRACTORIES', 60);
  append_stage_source('NSE_NIFTY_ALCOHOL_BREWERIES_STAGING', 'ALCOHOL_BREWERIES', 60);
  append_stage_source('NSE_NIFTY_CONSTRUCTION_STAGING', 'CONSTRUCTION', 60);
  append_stage_source('NSE_NIFTY_CONSUMER_DURABLES_STAGING', 'CONS_DUR', 60);
  append_stage_source('NSE_NIFTY_ELECTRONICS_SERVICES_CONSUMER_DURABLES_STAGING', 'ELEC_SERVICES_CONS_DURABLES', 60);
  append_stage_source('NSE_NIFTY_CONSUMER_ELECTRONICS_STAGING', 'CONSUMER_ELECTRONICS', 60);
  append_stage_source('NSE_NIFTY_CONSUMER_SERVICES_STAGING', 'CONSUMER_SERVICES', 60);
  append_stage_source('NSE_NIFTY_FMCG_STAGING', 'FMCG', 60);
  append_stage_source('NSE_NIFTY_HOUSEHOLD_PERSONAL_PRODUCTS_STAGING', 'HOUSEHOLD_PERSONAL_PRODUCTS', 60);
  append_stage_source('NSE_NIFTY_COMMODITIES_TRADING_STAGING', 'COMMODITIES_TRADING', 60);
  append_stage_source('NSE_NIFTY_DEFENCE_AEROSPACE_DEFENSE_STAGING', 'DEFENCE_AEROSPACE_DEFENSE', 60);
  append_stage_source('NSE_NIFTY_DIVERSIFIED_STAGING', 'DIVERSIFIED', 60);
  append_stage_source('NSE_NIFTY_IT_STAGING', 'IT', 60);
  append_stage_source('NSE_NIFTY_IT_ENABLED_SERVICES_STAGING', 'IT_ENABLED_SERVICES', 60);
  append_stage_source('NSE_NIFTY_SOFTWARE_PRODUCTS_SERVICES_STAGING', 'SOFTWARE_PRODUCTS_SERVICES', 60);
  append_stage_source('NSE_NIFTY_MEDIA_STAGING', 'MEDIA', 60);
  append_stage_source('NSE_NIFTY_MEDIA_ENTERTAINMENT_STAGING', 'MEDIA_ENTERTAINMENT', 60);
  append_stage_source('NSE_NIFTY_PRINT_MEDIA_PUBLISHING_STAGING', 'PRINT_MEDIA_PUBLISHING', 60);
  append_stage_source('NSE_NIFTY_METAL_STAGING', 'METAL', 60);
  append_stage_source('NSE_NIFTY_METALS_MINING_STAGING', 'METALS_MINING', 60);
  append_stage_source('NSE_NIFTY_IRON_STEEL_STAGING', 'IRON_STEEL', 60);
  append_stage_source('NSE_NIFTY_MINING_STAGING', 'MINING', 60);
  append_stage_source('NSE_NIFTY_NON_FERROUS_METALS_STAGING', 'NON_FERROUS_METALS', 60);
  append_stage_source('NSE_NIFTY_POWER_STAGING', 'POWER', 60);
  append_stage_source('NSE_NIFTY_SERVICES_STAGING', 'SERVICES', 60);
  append_stage_source('NSE_NIFTY_REALTY_REAL_ESTATE_STAGING', 'REALTY_REAL_ESTATE', 60);
  append_stage_source('NSE_NIFTY_TELECOMMUNICATION_STAGING', 'TELECOM', 60);
  append_stage_source('NSE_NIFTY_UTILITIES_STAGING', 'UTILITIES', 60);
  append_stage_source('NSE_NIFTY_RUBBER_PRODUCTS_TYRES_STAGING', 'RUBBER_PRODUCTS_TYRES', 60);
  append_stage_source('NSE_NIFTY_AVIATION_AIR_TRANSPORT_STAGING', 'AVIATION_AIR_TRANSPORT', 60);
  append_stage_source('NSE_NIFTY_LOGISTICS_SHIPPING_STAGING', 'LOGISTICS_SHIPPING', 60);
  append_stage_source('NSE_NIFTY_PORT_AND_PORT_SERVICES_STAGING', 'PORT_AND_PORT_SERVICES', 60);
  append_stage_source('NSE_NIFTY_ROAD_RAIL_TRANSPORT_STAGING', 'ROAD_RAIL_TRANSPORT', 60);
  append_stage_source('NSE_NIFTY_TRANSPORT_INFRASTRUCTURE_STAGING', 'TRANSPORT_INFRASTRUCTURE', 60);
  append_stage_source('NSE_NIFTY_AGRICULTURE_STAGING', 'AGRICULTURE', 60);
  append_stage_source('NSE_NIFTY_FERTILIZERS_AGROCHEMICALS_STAGING', 'FERTILIZERS_AGROCHEMICALS', 60);
  append_stage_source('NSE_NIFTY_PESTICIDES_AGROCHEMICALS_STAGING', 'PESTICIDES_AGROCHEMICALS', 60);
  append_stage_source('NSE_NIFTY_ASSET_MANAGEMENT_COMPANY_STAGING', 'ASSET_MANAGEMENT_COMPANY', 60);
  append_stage_source('NSE_NIFTY_CEMENT_CEMENT_PRODUCTS_STAGING', 'CEMENT_CEMENT_PRODUCTS', 60);
  append_stage_source('NSE_NIFTY_RETAILING_SPECIALITY_RETAIL_STAGING', 'RETAILING_SPECIALITY_RETAIL', 60);
  append_stage_source('NSE_NIFTY_ECOMMERCE_ERETAI_STAGING', 'ECOMMERCE_ERETAI', 60);
  append_stage_source('NSE_NIFTY_CONSTRUCTION_MATERIALS_STAGING', 'CONSTRUCTION_MATERIALS', 60);
  append_stage_source('NSE_NIFTY_INFRASTRUCTURE_STAGING', 'INFRASTRUCTURE', 60);

  append_stage_source('NSE_NIFTY_ENGINEERING_STAGING', 'ENGINEERING', 60);
  append_stage_source('NSE_NIFTY_ELEC_HEAVY_EQUIP_STAGING', 'ELEC_HEAVY_EQUIPMENT', 60);
  append_stage_source('NSE_NIFTY_INDUSTRIAL_MANUFACTURING_STAGING', 'INDUSTRIAL_MANUFACTURING', 60);
  append_stage_source('NSE_NIFTY_INDUSTRIAL_PRODUCTS_STAGING', 'INDUSTRIAL_PRODUCTS', 60);
  append_stage_source('NSE_NIFTY_INDUSTRIAL_GASES_FUELS_STAGING', 'INDUSTRIAL_GASES_FUELS', 60);
  append_stage_source('NSE_NIFTY_PAPER_PACKAGING_STAGING', 'PAPER_PACKAGING', 60);
  append_stage_source('NSE_NIFTY_WASTE_WATER_MANAGEMENT_STAGING', 'WASTE_WATER_MANAGEMENT', 60);

  append_stage_source('NSE_NIFTY_RETAILING_SPECIALITY_RETAIL_STAGING', 'RETAILING_SPECIALITY_RETAIL', 60);
  append_stage_source('NSE_NIFTY_ECOMMERCE_ERETAI_STAGING', 'ECOMMERCE_ERETAI', 60);
  append_stage_source('NSE_NIFTY_FOOTWEAR_STAGING', 'FOOTWEAR', 60);
  append_stage_source('NSE_NIFTY_GEMS_STAGING', 'GEMS', 60);
  append_stage_source('NSE_NIFTY_JEWELLERY_WATCHES_STAGING', 'JEWELLERY_WATCHES', 60);
  append_stage_source('NSE_NIFTY_LEATHER_LEATHER_PRODUCTS_STAGING', 'LEATHER_LEATHER_PRODUCTS', 60);
  append_stage_source('NSE_NIFTY_TEXTILES_APPARELS_STAGING', 'TEXTILES_APPARELS', 60);
  append_stage_source('NSE_NIFTY_BIOTECHNOLOGY_STAGING', 'BIOTECHNOLOGY', 60);
  append_stage_source('NSE_NIFTY_MEDICAL_EQUIPMENT_SUPPLIES_STAGING', 'MEDICAL_EQUIPMENT_SUPPLIES', 60);
  append_stage_source('NSE_NIFTY_LPG_CNG_PNG_LNG_SUPPLIER_STAGING', 'LPG_CNG_PNG_LNG_SUPPLIER', 60);
  append_stage_source('NSE_NIFTY_LUBRICANTS_STAGING', 'LUBRICANTS', 60);
  append_stage_source('NSE_NIFTY_OIL_EQUIPMENT_SERVICES_STAGING', 'OIL_EQUIPMENT_SERVICES', 60);
  append_stage_source('NSE_NIFTY_PETROLEUM_PRODUCTS_REFINERIES_STAGING', 'PETROLEUM_PRODUCTS_REFINERIES', 60);

  append_stage_source('NSE_NIFTY_RESTAURANTS_STAGING', 'RESTAURANTS', 60);
  append_stage_source('NSE_NIFTY_HOSPITALITY_HOTELS_RESORTS_STAGING', 'HOSPITALITY_HOTELS_RESORTS', 60);
  append_stage_source('NSE_NIFTY_TOURISM_TRAVEL_STAGING', 'TOURISM_TRAVEL', 60);
  append_stage_source('NSE_NIFTY_EDUCATION_E_LEARNING_STAGING', 'EDUCATION_E_LEARNING', 60);

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
