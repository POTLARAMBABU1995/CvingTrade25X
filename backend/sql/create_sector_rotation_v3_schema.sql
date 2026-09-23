-- CvingTrade25X Sector Rotation V3 - additive Oracle 19c persistence.
--
-- Scope:
--   * Creates V3-only configuration, run-audit, snapshot and component tables.
--   * Seeds one immutable default configuration when it is absent.
--   * Creates only the indexes required by configuration resolution, atomic
--     last-successful-run lookup and historical rank lookup.
--
-- Safety:
--   * Does not alter, delete, rename or replace any V1/V2 object.
--   * Every CREATE is dictionary-guarded, so an exact re-run is a no-op.
--   * This script intentionally creates tables rather than materialized views;
--     the refresh service can build a complete run and expose it atomically by
--     changing NSE_SECTOR_ROT_RUN_V3.IS_PUBLISHED to Y only after validation.
--   * Review and execute with the existing application Oracle owner. Codex does
--     not execute this DDL automatically.

SET DEFINE OFF;
SET SERVEROUTPUT ON;
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK;

DECLARE
  PROCEDURE create_table_if_missing(
    p_table_name IN VARCHAR2,
    p_ddl        IN VARCHAR2
  ) IS
    v_count PLS_INTEGER;
  BEGIN
    SELECT COUNT(*)
      INTO v_count
      FROM user_tables
     WHERE table_name = UPPER(p_table_name);

    IF v_count = 0 THEN
      EXECUTE IMMEDIATE p_ddl;
      DBMS_OUTPUT.PUT_LINE('Created table ' || UPPER(p_table_name));
    ELSE
      DBMS_OUTPUT.PUT_LINE('Kept existing table ' || UPPER(p_table_name));
    END IF;
  END;
BEGIN
  create_table_if_missing(
    'NSE_SECTOR_ROT_CONFIG_V3',
    q'~
      CREATE TABLE NSE_SECTOR_ROT_CONFIG_V3 (
        CONFIG_VERSION                 VARCHAR2(64)  NOT NULL,
        MODEL_NAME                     VARCHAR2(100) DEFAULT 'Sector Rotation' NOT NULL,
        MODEL_VERSION                  VARCHAR2(64)  NOT NULL,
        BENCHMARK_CODE                 VARCHAR2(50)  NOT NULL,
        BENCHMARK_VERSION              VARCHAR2(64)  NOT NULL,
        UNIVERSE_VERSION               VARCHAR2(64)  NOT NULL,
        EFFECTIVE_FROM                 DATE          NOT NULL,
        EFFECTIVE_TO                   DATE,
        STATUS                         VARCHAR2(16)  DEFAULT 'DRAFT' NOT NULL,
        MOMENTUM_WEIGHT                NUMBER(9,8)   NOT NULL,
        BREADTH_WEIGHT                 NUMBER(9,8)   NOT NULL,
        TREND_WEIGHT                   NUMBER(9,8)   NOT NULL,
        MONEY_FLOW_WEIGHT              NUMBER(9,8)   NOT NULL,
        RISK_WEIGHT                    NUMBER(9,8)   NOT NULL,
        DATA_QUALITY_WEIGHT            NUMBER(9,8)   NOT NULL,
        HORIZON_21_WEIGHT              NUMBER(9,8)   NOT NULL,
        HORIZON_63_WEIGHT              NUMBER(9,8)   NOT NULL,
        HORIZON_126_WEIGHT             NUMBER(9,8)   NOT NULL,
        HORIZON_252_WEIGHT             NUMBER(9,8)   NOT NULL,
        BREADTH_EQUAL_WEIGHT           NUMBER(9,8)   NOT NULL,
        BREADTH_FFMC_WEIGHT            NUMBER(9,8)   NOT NULL,
        BREADTH_MCAP_WEIGHT            NUMBER(9,8)   NOT NULL,
        MIN_UNIVERSE_COVERAGE_PCT      NUMBER(5,2)   NOT NULL,
        MIN_MONEY_FLOW_COVERAGE_PCT    NUMBER(5,2)   NOT NULL,
        MIN_HISTORY_DAYS               NUMBER(5)     NOT NULL,
        WINSOR_LOWER_PCT               NUMBER(5,2)   NOT NULL,
        WINSOR_UPPER_PCT               NUMBER(5,2)   NOT NULL,
        PHASE_POSITIVE_THRESHOLD       NUMBER(12,6)  NOT NULL,
        PHASE_NEGATIVE_THRESHOLD       NUMBER(12,6)  NOT NULL,
        PHASE_CONFIRM_COUNT            NUMBER(2)     NOT NULL,
        PHASE_CONFIRM_WINDOW           NUMBER(2)     NOT NULL,
        STALE_TOLERANCE_TRADING_DAYS   NUMBER(3)     NOT NULL,
        MISSING_MONEY_FLOW_PENALTY     NUMBER(7,4)   NOT NULL,
        CONFIG_JSON                    CLOB          NOT NULL,
        CONFIG_HASH                    VARCHAR2(128) NOT NULL,
        SOURCE_CODE_COMMIT             VARCHAR2(128),
        CREATED_BY                     VARCHAR2(128) DEFAULT USER NOT NULL,
        CREATED_AT                     TIMESTAMP(6) WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
        UPDATED_AT                     TIMESTAMP(6) WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
        CONSTRAINT PK_SEC_ROT_CFG_V3 PRIMARY KEY (CONFIG_VERSION),
        CONSTRAINT UQ_SEC_ROT_CFG_V3_HASH UNIQUE (MODEL_VERSION, CONFIG_HASH),
        CONSTRAINT CK_SEC_ROT_CFG_V3_DATES CHECK (
          EFFECTIVE_TO IS NULL OR EFFECTIVE_TO >= EFFECTIVE_FROM
        ),
        CONSTRAINT CK_SEC_ROT_CFG_V3_STATUS CHECK (
          STATUS IN ('DRAFT', 'ACTIVE', 'RETIRED')
        ),
        CONSTRAINT CK_SEC_ROT_CFG_V3_WT_SUM CHECK (
          ABS(
              MOMENTUM_WEIGHT + BREADTH_WEIGHT + TREND_WEIGHT
            + MONEY_FLOW_WEIGHT + RISK_WEIGHT + DATA_QUALITY_WEIGHT - 1
          ) <= 0.000001
        ),
        CONSTRAINT CK_SEC_ROT_CFG_V3_HOR_SUM CHECK (
          ABS(
              HORIZON_21_WEIGHT + HORIZON_63_WEIGHT
            + HORIZON_126_WEIGHT + HORIZON_252_WEIGHT - 1
          ) <= 0.000001
        ),
        CONSTRAINT CK_SEC_ROT_CFG_V3_BLEND CHECK (
          ABS(
              BREADTH_EQUAL_WEIGHT + BREADTH_FFMC_WEIGHT
            + BREADTH_MCAP_WEIGHT - 1
          ) <= 0.000001
        ),
        CONSTRAINT CK_SEC_ROT_CFG_V3_RANGE CHECK (
              MOMENTUM_WEIGHT BETWEEN 0 AND 1
          AND BREADTH_WEIGHT BETWEEN 0 AND 1
          AND TREND_WEIGHT BETWEEN 0 AND 1
          AND MONEY_FLOW_WEIGHT BETWEEN 0 AND 1
          AND RISK_WEIGHT BETWEEN 0 AND 1
          AND DATA_QUALITY_WEIGHT BETWEEN 0 AND 1
          AND HORIZON_21_WEIGHT BETWEEN 0 AND 1
          AND HORIZON_63_WEIGHT BETWEEN 0 AND 1
          AND HORIZON_126_WEIGHT BETWEEN 0 AND 1
          AND HORIZON_252_WEIGHT BETWEEN 0 AND 1
          AND BREADTH_EQUAL_WEIGHT BETWEEN 0 AND 1
          AND BREADTH_FFMC_WEIGHT BETWEEN 0 AND 1
          AND BREADTH_MCAP_WEIGHT BETWEEN 0 AND 1
          AND MIN_UNIVERSE_COVERAGE_PCT BETWEEN 0 AND 100
          AND MIN_MONEY_FLOW_COVERAGE_PCT BETWEEN 0 AND 100
          AND MIN_HISTORY_DAYS > 0
          AND WINSOR_LOWER_PCT BETWEEN 0 AND 100
          AND WINSOR_UPPER_PCT BETWEEN 0 AND 100
          AND WINSOR_LOWER_PCT < WINSOR_UPPER_PCT
          AND PHASE_NEGATIVE_THRESHOLD <= PHASE_POSITIVE_THRESHOLD
          AND PHASE_CONFIRM_COUNT BETWEEN 1 AND PHASE_CONFIRM_WINDOW
          AND STALE_TOLERANCE_TRADING_DAYS >= 0
          AND MISSING_MONEY_FLOW_PENALTY BETWEEN 0 AND 100
        ),
        CONSTRAINT CK_SEC_ROT_CFG_V3_JSON CHECK (CONFIG_JSON IS JSON)
      )
    ~'
  );

  create_table_if_missing(
    'NSE_SECTOR_ROT_RUN_V3',
    q'~
      CREATE TABLE NSE_SECTOR_ROT_RUN_V3 (
        RUN_ID                    VARCHAR2(64)  NOT NULL,
        AS_OF_DATE                DATE          NOT NULL,
        MODEL_VERSION             VARCHAR2(64)  NOT NULL,
        CONFIG_VERSION            VARCHAR2(64)  NOT NULL,
        CONFIG_HASH               VARCHAR2(128) NOT NULL,
        BENCHMARK_CODE            VARCHAR2(50)  NOT NULL,
        BENCHMARK_VERSION         VARCHAR2(64)  NOT NULL,
        UNIVERSE_VERSION          VARCHAR2(64)  NOT NULL,
        SOURCE_MAX_TRADING_DATE   DATE,
        STARTED_AT                TIMESTAMP(6) WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
        COMPLETED_AT              TIMESTAMP(6) WITH TIME ZONE,
        STATUS                    VARCHAR2(20)  DEFAULT 'STARTED' NOT NULL,
        IS_PUBLISHED              CHAR(1)       DEFAULT 'N' NOT NULL,
        PUBLISHED_AT              TIMESTAMP(6) WITH TIME ZONE,
        ROW_COUNT                 NUMBER(6)     DEFAULT 0 NOT NULL,
        INPUT_SYMBOL_COUNT        NUMBER(8)     DEFAULT 0 NOT NULL,
        ELIGIBLE_SYMBOL_COUNT     NUMBER(8)     DEFAULT 0 NOT NULL,
        EXCLUDED_SYMBOL_COUNT     NUMBER(8)     DEFAULT 0 NOT NULL,
        CALCULATION_DURATION_MS   NUMBER(12),
        ERROR_CODE                VARCHAR2(100),
        ERROR_MESSAGE             VARCHAR2(2000),
        RUN_METADATA_JSON         CLOB,
        CREATED_AT                TIMESTAMP(6) WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
        UPDATED_AT                TIMESTAMP(6) WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
        CONSTRAINT PK_SEC_ROT_RUN_V3 PRIMARY KEY (RUN_ID),
        CONSTRAINT FK_SEC_ROT_RUN_V3_CFG FOREIGN KEY (CONFIG_VERSION)
          REFERENCES NSE_SECTOR_ROT_CONFIG_V3 (CONFIG_VERSION),
        CONSTRAINT CK_SEC_ROT_RUN_V3_DATE CHECK (AS_OF_DATE = TRUNC(AS_OF_DATE)),
        CONSTRAINT CK_SEC_ROT_RUN_V3_STATUS CHECK (
          STATUS IN (
            'STARTED', 'VALIDATING', 'CALCULATING', 'PERSISTED',
            'SUCCESS', 'FAILED', 'CANCELLED'
          )
        ),
        CONSTRAINT CK_SEC_ROT_RUN_V3_PUB CHECK (
              (IS_PUBLISHED = 'N' AND PUBLISHED_AT IS NULL)
           OR (IS_PUBLISHED = 'Y' AND STATUS = 'SUCCESS' AND PUBLISHED_AT IS NOT NULL)
        ),
        CONSTRAINT CK_SEC_ROT_RUN_V3_COUNTS CHECK (
              ROW_COUNT >= 0
          AND INPUT_SYMBOL_COUNT >= 0
          AND ELIGIBLE_SYMBOL_COUNT >= 0
          AND EXCLUDED_SYMBOL_COUNT >= 0
          AND (CALCULATION_DURATION_MS IS NULL OR CALCULATION_DURATION_MS >= 0)
        ),
        CONSTRAINT CK_SEC_ROT_RUN_V3_TIME CHECK (
          COMPLETED_AT IS NULL OR COMPLETED_AT >= STARTED_AT
        ),
        CONSTRAINT CK_SEC_ROT_RUN_V3_JSON CHECK (
          RUN_METADATA_JSON IS NULL OR RUN_METADATA_JSON IS JSON
        )
      )
    ~'
  );

  create_table_if_missing(
    'NSE_SECTOR_ROTATION_SNAP_V3',
    q'~
      CREATE TABLE NSE_SECTOR_ROTATION_SNAP_V3 (
        RUN_ID                         VARCHAR2(64)  NOT NULL,
        SECTOR_CODE                    VARCHAR2(100) NOT NULL,
        SECTOR_NAME                    VARCHAR2(255) NOT NULL,
        AS_OF_DATE                     DATE          NOT NULL,
        MODEL_VERSION                  VARCHAR2(64)  NOT NULL,
        CONFIG_VERSION                 VARCHAR2(64)  NOT NULL,
        BENCHMARK_CODE                 VARCHAR2(50)  NOT NULL,
        BENCHMARK_VERSION              VARCHAR2(64)  NOT NULL,
        UNIVERSE_VERSION               VARCHAR2(64)  NOT NULL,
        LATEST_DATA_DATE               DATE,
        GENERATED_AT                   TIMESTAMP(6) WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,

        TOTAL_STOCKS                   NUMBER(6),
        ELIGIBLE_STOCK_COUNT           NUMBER(6),
        VALID_PRICE_COUNT              NUMBER(6),
        VALID_INDICATOR_COUNT          NUMBER(6),
        STALE_STOCK_COUNT              NUMBER(6),
        EXCLUDED_STOCK_COUNT           NUMBER(6),
        OUTLIER_COUNT                  NUMBER(6),
        MISSING_CRITICAL_FIELD_COUNT   NUMBER(6),
        COVERAGE_PERCENT               NUMBER(7,4),
        HISTORY_COVERAGE_PERCENT       NUMBER(7,4),
        MONEY_FLOW_COVERAGE_PERCENT    NUMBER(7,4),

        RSI55_PERCENT                  NUMBER(7,4),
        RSI50_PERCENT                  NUMBER(7,4),
        SMA20_PERCENT                  NUMBER(7,4),
        SMA50_PERCENT                  NUMBER(7,4),
        SMA100_PERCENT                 NUMBER(7,4),
        SMA200_PERCENT                 NUMBER(7,4),
        BULLISH_STACK_PERCENT          NUMBER(7,4),
        LEGACY_DISPLAY_SCORE           NUMBER(7,4),

        RELATIVE_RETURN_21             NUMBER(22,10),
        RELATIVE_RETURN_63             NUMBER(22,10),
        RELATIVE_RETURN_126            NUMBER(22,10),
        RELATIVE_RETURN_252            NUMBER(22,10),
        RELATIVE_STRENGTH_LEVEL        NUMBER(12,6),
        MOMENTUM_SCORE                 NUMBER(9,6),
        MOMENTUM_ACCELERATION_RAW      NUMBER(22,10),
        MOMENTUM_ACCELERATION_SCORE    NUMBER(9,6),
        MOMENTUM_DIRECTION             VARCHAR2(20),

        BREADTH_SCORE                  NUMBER(9,6),
        BREADTH_DELTA_1D               NUMBER(12,6),
        BREADTH_DELTA_5D               NUMBER(12,6),
        BREADTH_DELTA_21D              NUMBER(12,6),
        BREADTH_DIRECTION              VARCHAR2(20),

        TREND_SCORE                    NUMBER(9,6),
        TREND_STATE                    VARCHAR2(24),
        MONEY_FLOW_SCORE               NUMBER(9,6),
        MONEY_FLOW_DIRECTION           VARCHAR2(20),

        RISK_SCORE                     NUMBER(9,6),
        VOLATILITY_63                  NUMBER(22,10),
        DOWNSIDE_VOLATILITY_126        NUMBER(22,10),
        MAX_DRAWDOWN_126               NUMBER(22,10),
        MAX_DRAWDOWN_252               NUMBER(22,10),
        BETA_252                       NUMBER(22,10),
        BETA_INSTABILITY               NUMBER(22,10),
        CONCENTRATION_HHI              NUMBER(18,12),
        TOP1_WEIGHT                    NUMBER(12,10),
        TOP3_WEIGHT                    NUMBER(12,10),
        TOP5_WEIGHT                    NUMBER(12,10),
        LIQUIDITY_RISK                 NUMBER(9,6),
        RISK_REGIME                    VARCHAR2(16),

        DATA_QUALITY_SCORE             NUMBER(9,6),
        DATA_QUALITY_STATUS            VARCHAR2(24),
        FINAL_ROTATION_SCORE           NUMBER(9,6),
        ROTATION_BAND                  VARCHAR2(16),
        ROTATION_PHASE                 VARCHAR2(16)  NOT NULL,
        PREVIOUS_PHASE                 VARCHAR2(16),
        PHASE_CHANGED_AT               DATE,
        PHASE_DURATION_DAYS            NUMBER(6),
        PHASE_CONFIDENCE               NUMBER(9,6),

        CURRENT_RANK                   NUMBER(6),
        RANK_CHANGE_1D                 NUMBER(6),
        RANK_CHANGE_1W                 NUMBER(6),
        RANK_CHANGE_1M                 NUMBER(6),
        SCORE_CHANGE_1D                NUMBER(12,6),
        SCORE_CHANGE_1W                NUMBER(12,6),
        CONFIDENCE                     VARCHAR2(12)  NOT NULL,
        CONFIDENCE_SCORE               NUMBER(9,6),
        WEIGHT_REDISTRIBUTION_APPLIED  CHAR(1)       DEFAULT 'N' NOT NULL,

        CONFIGURED_WEIGHTS_JSON        CLOB          NOT NULL,
        EFFECTIVE_WEIGHTS_JSON         CLOB          NOT NULL,
        REASON_CODES_JSON              CLOB,
        POSITIVE_REASONS_JSON          CLOB,
        RISK_WARNINGS_JSON             CLOB,
        DIVERGENCE_CODES_JSON          CLOB,
        SUMMARY_EXPLANATION            VARCHAR2(2000),
        PAYLOAD_JSON                   CLOB,
        CREATED_AT                     TIMESTAMP(6) WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
        UPDATED_AT                     TIMESTAMP(6) WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,

        CONSTRAINT PK_SEC_ROT_SNAP_V3 PRIMARY KEY (RUN_ID, SECTOR_CODE),
        CONSTRAINT FK_SEC_ROT_SNAP_V3_RUN FOREIGN KEY (RUN_ID)
          REFERENCES NSE_SECTOR_ROT_RUN_V3 (RUN_ID),
        CONSTRAINT FK_SEC_ROT_SNAP_V3_CFG FOREIGN KEY (CONFIG_VERSION)
          REFERENCES NSE_SECTOR_ROT_CONFIG_V3 (CONFIG_VERSION),
        CONSTRAINT CK_SEC_ROT_SNAP_V3_DATE CHECK (
              AS_OF_DATE = TRUNC(AS_OF_DATE)
          AND (LATEST_DATA_DATE IS NULL OR LATEST_DATA_DATE <= AS_OF_DATE)
        ),
        CONSTRAINT CK_SEC_ROT_SNAP_V3_COUNT CHECK (
              (TOTAL_STOCKS IS NULL OR TOTAL_STOCKS >= 0)
          AND (ELIGIBLE_STOCK_COUNT IS NULL OR ELIGIBLE_STOCK_COUNT >= 0)
          AND (VALID_PRICE_COUNT IS NULL OR VALID_PRICE_COUNT >= 0)
          AND (VALID_INDICATOR_COUNT IS NULL OR VALID_INDICATOR_COUNT >= 0)
          AND (STALE_STOCK_COUNT IS NULL OR STALE_STOCK_COUNT >= 0)
          AND (EXCLUDED_STOCK_COUNT IS NULL OR EXCLUDED_STOCK_COUNT >= 0)
          AND (OUTLIER_COUNT IS NULL OR OUTLIER_COUNT >= 0)
          AND (MISSING_CRITICAL_FIELD_COUNT IS NULL OR MISSING_CRITICAL_FIELD_COUNT >= 0)
        ),
        CONSTRAINT CK_SEC_ROT_SNAP_V3_PCT CHECK (
              (COVERAGE_PERCENT IS NULL OR COVERAGE_PERCENT BETWEEN 0 AND 100)
          AND (HISTORY_COVERAGE_PERCENT IS NULL OR HISTORY_COVERAGE_PERCENT BETWEEN 0 AND 100)
          AND (MONEY_FLOW_COVERAGE_PERCENT IS NULL OR MONEY_FLOW_COVERAGE_PERCENT BETWEEN 0 AND 100)
          AND (RSI55_PERCENT IS NULL OR RSI55_PERCENT BETWEEN 0 AND 100)
          AND (RSI50_PERCENT IS NULL OR RSI50_PERCENT BETWEEN 0 AND 100)
          AND (SMA20_PERCENT IS NULL OR SMA20_PERCENT BETWEEN 0 AND 100)
          AND (SMA50_PERCENT IS NULL OR SMA50_PERCENT BETWEEN 0 AND 100)
          AND (SMA100_PERCENT IS NULL OR SMA100_PERCENT BETWEEN 0 AND 100)
          AND (SMA200_PERCENT IS NULL OR SMA200_PERCENT BETWEEN 0 AND 100)
          AND (BULLISH_STACK_PERCENT IS NULL OR BULLISH_STACK_PERCENT BETWEEN 0 AND 100)
          AND (LEGACY_DISPLAY_SCORE IS NULL OR LEGACY_DISPLAY_SCORE BETWEEN 0 AND 100)
        ),
        CONSTRAINT CK_SEC_ROT_SNAP_V3_SCORE CHECK (
              (MOMENTUM_SCORE IS NULL OR MOMENTUM_SCORE BETWEEN 0 AND 100)
          AND (MOMENTUM_ACCELERATION_SCORE IS NULL OR MOMENTUM_ACCELERATION_SCORE BETWEEN 0 AND 100)
          AND (BREADTH_SCORE IS NULL OR BREADTH_SCORE BETWEEN 0 AND 100)
          AND (TREND_SCORE IS NULL OR TREND_SCORE BETWEEN 0 AND 100)
          AND (MONEY_FLOW_SCORE IS NULL OR MONEY_FLOW_SCORE BETWEEN 0 AND 100)
          AND (RISK_SCORE IS NULL OR RISK_SCORE BETWEEN 0 AND 100)
          AND (LIQUIDITY_RISK IS NULL OR LIQUIDITY_RISK BETWEEN 0 AND 100)
          AND (DATA_QUALITY_SCORE IS NULL OR DATA_QUALITY_SCORE BETWEEN 0 AND 100)
          AND (FINAL_ROTATION_SCORE IS NULL OR FINAL_ROTATION_SCORE BETWEEN 0 AND 100)
          AND (PHASE_CONFIDENCE IS NULL OR PHASE_CONFIDENCE BETWEEN 0 AND 100)
          AND (CONFIDENCE_SCORE IS NULL OR CONFIDENCE_SCORE BETWEEN 0 AND 100)
          AND (CURRENT_RANK IS NULL OR CURRENT_RANK > 0)
        ),
        CONSTRAINT CK_SEC_ROT_SNAP_V3_CORE CHECK (
          FINAL_ROTATION_SCORE IS NULL OR (
            MOMENTUM_SCORE IS NOT NULL
            AND BREADTH_SCORE IS NOT NULL
            AND TREND_SCORE IS NOT NULL
            AND RISK_SCORE IS NOT NULL
            AND DATA_QUALITY_SCORE IS NOT NULL
          )
        ),
        CONSTRAINT CK_SEC_ROT_SNAP_V3_PHASE CHECK (
              ROTATION_PHASE IN ('LEADING', 'IMPROVING', 'WEAKENING', 'LAGGING', 'DATA_WEAK')
          AND (PREVIOUS_PHASE IS NULL OR PREVIOUS_PHASE IN ('LEADING', 'IMPROVING', 'WEAKENING', 'LAGGING', 'DATA_WEAK'))
        ),
        CONSTRAINT CK_SEC_ROT_SNAP_V3_BAND CHECK (
          ROTATION_BAND IS NULL OR ROTATION_BAND IN (
            'VERY_STRONG', 'STRONG', 'POSITIVE', 'NEUTRAL', 'WEAK', 'VERY_WEAK', 'DATA_WEAK'
          )
        ),
        CONSTRAINT CK_SEC_ROT_SNAP_V3_DQ CHECK (
          DATA_QUALITY_STATUS IS NULL OR DATA_QUALITY_STATUS IN (
            'EXCELLENT', 'GOOD', 'ACCEPTABLE', 'WEAK', 'DATA_INSUFFICIENT'
          )
        ),
        CONSTRAINT CK_SEC_ROT_SNAP_V3_CONF CHECK (
              CONFIDENCE IN ('HIGH', 'MEDIUM', 'LOW')
          AND WEIGHT_REDISTRIBUTION_APPLIED IN ('Y', 'N')
        ),
        CONSTRAINT CK_SEC_ROT_SNAP_V3_RISK CHECK (
          RISK_REGIME IS NULL OR RISK_REGIME IN ('LOW', 'NORMAL', 'ELEVATED', 'HIGH', 'EXTREME')
        ),
        CONSTRAINT CK_SEC_ROT_SNAP_V3_JSON CHECK (
              CONFIGURED_WEIGHTS_JSON IS JSON
          AND EFFECTIVE_WEIGHTS_JSON IS JSON
          AND (REASON_CODES_JSON IS NULL OR REASON_CODES_JSON IS JSON)
          AND (POSITIVE_REASONS_JSON IS NULL OR POSITIVE_REASONS_JSON IS JSON)
          AND (RISK_WARNINGS_JSON IS NULL OR RISK_WARNINGS_JSON IS JSON)
          AND (DIVERGENCE_CODES_JSON IS NULL OR DIVERGENCE_CODES_JSON IS JSON)
          AND (PAYLOAD_JSON IS NULL OR PAYLOAD_JSON IS JSON)
        )
      )
    ~'
  );

  create_table_if_missing(
    'NSE_SECTOR_ROT_COMP_V3',
    q'~
      CREATE TABLE NSE_SECTOR_ROT_COMP_V3 (
        RUN_ID                    VARCHAR2(64)  NOT NULL,
        SECTOR_CODE               VARCHAR2(100) NOT NULL,
        AS_OF_DATE                DATE          NOT NULL,
        MODEL_VERSION             VARCHAR2(64)  NOT NULL,
        CONFIG_VERSION            VARCHAR2(64)  NOT NULL,
        COMPONENT_CODE            VARCHAR2(24)  NOT NULL,
        RAW_VALUE                 NUMBER(28,12),
        NORMALIZED_SCORE          NUMBER(9,6),
        CONFIGURED_WEIGHT         NUMBER(9,8)   NOT NULL,
        EFFECTIVE_WEIGHT          NUMBER(9,8)   NOT NULL,
        COVERAGE_PERCENT          NUMBER(7,4),
        COMPONENT_DIRECTION       VARCHAR2(24),
        COMPONENT_STATUS          VARCHAR2(24),
        IS_REQUIRED               CHAR(1)       DEFAULT 'N' NOT NULL,
        IS_AVAILABLE              CHAR(1)       DEFAULT 'Y' NOT NULL,
        REDISTRIBUTION_APPLIED    CHAR(1)       DEFAULT 'N' NOT NULL,
        INPUT_COUNT               NUMBER(8),
        VALID_COUNT               NUMBER(8),
        MISSING_COUNT             NUMBER(8),
        METRICS_JSON              CLOB          NOT NULL,
        REASON_CODES_JSON         CLOB,
        WARNINGS_JSON             CLOB,
        CREATED_AT                TIMESTAMP(6) WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
        CONSTRAINT PK_SEC_ROT_COMP_V3 PRIMARY KEY (RUN_ID, SECTOR_CODE, COMPONENT_CODE),
        CONSTRAINT FK_SEC_ROT_COMP_V3_SNAP FOREIGN KEY (RUN_ID, SECTOR_CODE)
          REFERENCES NSE_SECTOR_ROTATION_SNAP_V3 (RUN_ID, SECTOR_CODE),
        CONSTRAINT FK_SEC_ROT_COMP_V3_CFG FOREIGN KEY (CONFIG_VERSION)
          REFERENCES NSE_SECTOR_ROT_CONFIG_V3 (CONFIG_VERSION),
        CONSTRAINT CK_SEC_ROT_COMP_V3_CODE CHECK (
          COMPONENT_CODE IN ('MOMENTUM', 'BREADTH', 'TREND', 'MONEY_FLOW', 'RISK', 'DATA_QUALITY')
        ),
        CONSTRAINT CK_SEC_ROT_COMP_V3_RANGE CHECK (
              (NORMALIZED_SCORE IS NULL OR NORMALIZED_SCORE BETWEEN 0 AND 100)
          AND CONFIGURED_WEIGHT BETWEEN 0 AND 1
          AND EFFECTIVE_WEIGHT BETWEEN 0 AND 1
          AND (COVERAGE_PERCENT IS NULL OR COVERAGE_PERCENT BETWEEN 0 AND 100)
          AND (INPUT_COUNT IS NULL OR INPUT_COUNT >= 0)
          AND (VALID_COUNT IS NULL OR VALID_COUNT >= 0)
          AND (MISSING_COUNT IS NULL OR MISSING_COUNT >= 0)
        ),
        CONSTRAINT CK_SEC_ROT_COMP_V3_FLAG CHECK (
              IS_REQUIRED IN ('Y', 'N')
          AND IS_AVAILABLE IN ('Y', 'N')
          AND REDISTRIBUTION_APPLIED IN ('Y', 'N')
        ),
        CONSTRAINT CK_SEC_ROT_COMP_V3_NULL CHECK (
          IS_AVAILABLE = 'Y' OR NORMALIZED_SCORE IS NULL
        ),
        CONSTRAINT CK_SEC_ROT_COMP_V3_JSON CHECK (
              METRICS_JSON IS JSON
          AND (REASON_CODES_JSON IS NULL OR REASON_CODES_JSON IS JSON)
          AND (WARNINGS_JSON IS NULL OR WARNINGS_JSON IS JSON)
        )
      )
    ~'
  );
END;
/

COMMENT ON TABLE NSE_SECTOR_ROT_CONFIG_V3 IS
  'Immutable versioned configuration for the independent Sector Rotation V3 factors.';
COMMENT ON TABLE NSE_SECTOR_ROT_RUN_V3 IS
  'V3 refresh audit and publication gate; only SUCCESS rows with IS_PUBLISHED=Y are API-visible.';
COMMENT ON TABLE NSE_SECTOR_ROTATION_SNAP_V3 IS
  'Reproducible per-run, per-sector V3 snapshot. Historical reruns are retained by RUN_ID.';
COMMENT ON TABLE NSE_SECTOR_ROT_COMP_V3 IS
  'Independent raw/normalized factor evidence and effective weights for each V3 sector snapshot.';
COMMENT ON COLUMN NSE_SECTOR_ROTATION_SNAP_V3.LEGACY_DISPLAY_SCORE IS
  'Backward-compatible average of the five legacy breadth percentages; never the V3 ranking key.';
COMMENT ON COLUMN NSE_SECTOR_ROTATION_SNAP_V3.FINAL_ROTATION_SCORE IS
  'Canonical 0-100 V3 ranking score; NULL when a required core component is unavailable.';
COMMENT ON COLUMN NSE_SECTOR_ROT_RUN_V3.IS_PUBLISHED IS
  'Atomic API exposure gate. Set to Y only after the run snapshot and components pass validation.';

DECLARE
  PROCEDURE create_index_if_missing(
    p_index_name IN VARCHAR2,
    p_ddl        IN VARCHAR2
  ) IS
    v_count PLS_INTEGER;
  BEGIN
    SELECT COUNT(*)
      INTO v_count
      FROM user_indexes
     WHERE index_name = UPPER(p_index_name);

    IF v_count = 0 THEN
      EXECUTE IMMEDIATE p_ddl;
      DBMS_OUTPUT.PUT_LINE('Created index ' || UPPER(p_index_name));
    ELSE
      DBMS_OUTPUT.PUT_LINE('Kept existing index ' || UPPER(p_index_name));
    END IF;
  END;
BEGIN
  -- Resolves the effective configuration without scanning historical configs.
  create_index_if_missing(
    'IX_SEC_ROT_CFG_V3_ACTIVE',
    'CREATE INDEX IX_SEC_ROT_CFG_V3_ACTIVE ON NSE_SECTOR_ROT_CONFIG_V3 '
      || '(MODEL_VERSION, STATUS, EFFECTIVE_FROM DESC, EFFECTIVE_TO)'
  );

  -- First lookup performed by the snapshot repository. Equality columns lead;
  -- newest date/completion are descending for last-known-good retrieval.
  create_index_if_missing(
    'IX_SEC_ROT_RUN_V3_PUB',
    'CREATE INDEX IX_SEC_ROT_RUN_V3_PUB ON NSE_SECTOR_ROT_RUN_V3 '
      || '(MODEL_VERSION, IS_PUBLISHED, STATUS, AS_OF_DATE DESC, COMPLETED_AT DESC)'
  );

  -- Supports point-in-time rank history. The main API fetch is already covered
  -- by the snapshot primary key prefix (RUN_ID, SECTOR_CODE); sorting roughly
  -- one row per sector does not justify a redundant FINAL_ROTATION_SCORE index.
  create_index_if_missing(
    'IX_SEC_ROT_SNAP_V3_HIST',
    'CREATE INDEX IX_SEC_ROT_SNAP_V3_HIST ON NSE_SECTOR_ROTATION_SNAP_V3 '
      || '(MODEL_VERSION, SECTOR_CODE, AS_OF_DATE DESC, RUN_ID)'
  );
END;
/

-- Seed the documented default configuration once. A re-run never updates an
-- existing configuration; governance changes require a new CONFIG_VERSION.
MERGE INTO NSE_SECTOR_ROT_CONFIG_V3 target
USING (
  SELECT
    'V3_DEFAULT_20260715' AS CONFIG_VERSION,
    'Sector Rotation' AS MODEL_NAME,
    'SECTOR_ROTATION_V3' AS MODEL_VERSION,
    'NIFTY500' AS BENCHMARK_CODE,
    'NIFTY500_SOURCE_CURRENT' AS BENCHMARK_VERSION,
    'NSE_SECTOR_MASTER_PIT_V1' AS UNIVERSE_VERSION,
    DATE '2026-07-15' AS EFFECTIVE_FROM,
    q'~{
      "modelVersion":"SECTOR_ROTATION_V3",
      "factorWeights":{"momentum":0.30,"breadth":0.25,"trend":0.20,"moneyFlow":0.10,"risk":0.10,"dataQuality":0.05},
      "momentumHorizonWeights":{"d21":0.15,"d63":0.30,"d126":0.30,"d252":0.25},
      "breadthBlendWeights":{"equal":0.60,"ffmc":0.25,"marketCap":0.15},
      "minimumUniverseCoveragePercent":85,
      "minimumMoneyFlowCoveragePercent":60,
      "minimumHistoryDays":252,
      "winsorization":{"lowerPercentile":1,"upperPercentile":99},
      "phase":{"positiveAccelerationThreshold":5,"negativeAccelerationThreshold":-5,"confirmCount":2,"confirmWindow":3},
      "staleToleranceTradingDays":1,
      "missingMoneyFlowPenalty":3,
      "scoreBands":{"veryStrong":85,"strong":70,"positive":55,"neutral":45,"weak":30},
      "benchmark":"NIFTY500",
      "benchmarkVersion":"NIFTY500_SOURCE_CURRENT",
      "universeVersion":"NSE_SECTOR_MASTER_PIT_V1"
    }~' AS CONFIG_JSON
  FROM dual
) source
ON (target.CONFIG_VERSION = source.CONFIG_VERSION)
WHEN NOT MATCHED THEN
  INSERT (
    CONFIG_VERSION,
    MODEL_NAME,
    MODEL_VERSION,
    BENCHMARK_CODE,
    BENCHMARK_VERSION,
    UNIVERSE_VERSION,
    EFFECTIVE_FROM,
    STATUS,
    MOMENTUM_WEIGHT,
    BREADTH_WEIGHT,
    TREND_WEIGHT,
    MONEY_FLOW_WEIGHT,
    RISK_WEIGHT,
    DATA_QUALITY_WEIGHT,
    HORIZON_21_WEIGHT,
    HORIZON_63_WEIGHT,
    HORIZON_126_WEIGHT,
    HORIZON_252_WEIGHT,
    BREADTH_EQUAL_WEIGHT,
    BREADTH_FFMC_WEIGHT,
    BREADTH_MCAP_WEIGHT,
    MIN_UNIVERSE_COVERAGE_PCT,
    MIN_MONEY_FLOW_COVERAGE_PCT,
    MIN_HISTORY_DAYS,
    WINSOR_LOWER_PCT,
    WINSOR_UPPER_PCT,
    PHASE_POSITIVE_THRESHOLD,
    PHASE_NEGATIVE_THRESHOLD,
    PHASE_CONFIRM_COUNT,
    PHASE_CONFIRM_WINDOW,
    STALE_TOLERANCE_TRADING_DAYS,
    MISSING_MONEY_FLOW_PENALTY,
    CONFIG_JSON,
    CONFIG_HASH,
    SOURCE_CODE_COMMIT
  ) VALUES (
    source.CONFIG_VERSION,
    source.MODEL_NAME,
    source.MODEL_VERSION,
    source.BENCHMARK_CODE,
    source.BENCHMARK_VERSION,
    source.UNIVERSE_VERSION,
    source.EFFECTIVE_FROM,
    'ACTIVE',
    0.30,
    0.25,
    0.20,
    0.10,
    0.10,
    0.05,
    0.15,
    0.30,
    0.30,
    0.25,
    0.60,
    0.25,
    0.15,
    85,
    60,
    252,
    1,
    99,
    5,
    -5,
    2,
    3,
    1,
    3,
    TO_CLOB(source.CONFIG_JSON),
    RAWTOHEX(STANDARD_HASH(source.CONFIG_JSON, 'SHA256')),
    'UNSPECIFIED'
  );

COMMIT;

PROMPT Sector Rotation V3 additive schema is ready.
PROMPT API publication contract: join snapshots to a SUCCESS run where IS_PUBLISHED = Y.
PROMPT No V1 or V2 object was modified.
