-- CvingTrade25X Sector Rotation V3 - Oracle 19c schema/data validation.
-- Run after create_sector_rotation_v3_schema.sql.
-- This script does not modify application data. EXPLAIN PLAN writes only the
-- conventional optimizer-plan row to PLAN_TABLE.

SET DEFINE OFF;
SET SERVEROUTPUT ON;
SET PAGESIZE 200;
SET LINESIZE 240;
SET LONG 200000;
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK;

PROMPT === Sector Rotation V3 object inventory ===

COLUMN OBJECT_NAME FORMAT A36;
COLUMN OBJECT_TYPE FORMAT A18;
COLUMN STATUS FORMAT A12;

SELECT object_name, object_type, status
FROM user_objects
WHERE object_name IN (
  'NSE_SECTOR_ROT_CONFIG_V3',
  'NSE_SECTOR_ROT_RUN_V3',
  'NSE_SECTOR_ROTATION_SNAP_V3',
  'NSE_SECTOR_ROT_COMP_V3',
  'IX_SEC_ROT_CFG_V3_ACTIVE',
  'IX_SEC_ROT_RUN_V3_PUB',
  'IX_SEC_ROT_SNAP_V3_HIST'
)
ORDER BY object_type, object_name;

PROMPT === V3 constraints ===

COLUMN TABLE_NAME FORMAT A34;
COLUMN CONSTRAINT_NAME FORMAT A30;
COLUMN CONSTRAINT_TYPE FORMAT A4;
COLUMN VALIDATED FORMAT A12;

SELECT table_name, constraint_name, constraint_type, status, validated
FROM user_constraints
WHERE table_name IN (
  'NSE_SECTOR_ROT_CONFIG_V3',
  'NSE_SECTOR_ROT_RUN_V3',
  'NSE_SECTOR_ROTATION_SNAP_V3',
  'NSE_SECTOR_ROT_COMP_V3'
)
ORDER BY table_name, constraint_type, constraint_name;

PROMPT === Seeded V3 configuration ===

COLUMN CONFIG_VERSION FORMAT A24;
COLUMN MODEL_VERSION FORMAT A24;
COLUMN BENCHMARK_CODE FORMAT A14;
COLUMN CONFIG_HASH FORMAT A64;

SELECT
  config_version,
  model_version,
  benchmark_code,
  status,
  effective_from,
  effective_to,
  config_hash
FROM nse_sector_rot_config_v3
ORDER BY effective_from, config_version;

PROMPT === Executable integrity assertions ===

DECLARE
  v_failures PLS_INTEGER := 0;

  PROCEDURE check_expected(
    p_check_name IN VARCHAR2,
    p_sql        IN VARCHAR2,
    p_expected   IN NUMBER
  ) IS
    v_actual NUMBER;
  BEGIN
    EXECUTE IMMEDIATE p_sql INTO v_actual;
    IF v_actual = p_expected THEN
      DBMS_OUTPUT.PUT_LINE('PASS | ' || RPAD(p_check_name, 52) || ' | value=' || v_actual);
    ELSE
      v_failures := v_failures + 1;
      DBMS_OUTPUT.PUT_LINE(
        'FAIL | ' || RPAD(p_check_name, 52)
        || ' | expected=' || p_expected || ', actual=' || v_actual
      );
    END IF;
  END;

  PROCEDURE check_zero(
    p_check_name IN VARCHAR2,
    p_sql        IN VARCHAR2
  ) IS
  BEGIN
    check_expected(p_check_name, p_sql, 0);
  END;
BEGIN
  check_expected(
    'required V3 tables exist',
    q'~SELECT COUNT(*) FROM user_tables WHERE table_name IN (
         'NSE_SECTOR_ROT_CONFIG_V3',
         'NSE_SECTOR_ROT_RUN_V3',
         'NSE_SECTOR_ROTATION_SNAP_V3',
         'NSE_SECTOR_ROT_COMP_V3'
       )~',
    4
  );

  check_expected(
    'required V3 non-PK indexes exist',
    q'~SELECT COUNT(*) FROM user_indexes WHERE index_name IN (
         'IX_SEC_ROT_CFG_V3_ACTIVE',
         'IX_SEC_ROT_RUN_V3_PUB',
         'IX_SEC_ROT_SNAP_V3_HIST'
       )~',
    3
  );

  check_zero(
    'disabled or unvalidated V3 constraints',
    q'~SELECT COUNT(*)
         FROM user_constraints
        WHERE table_name IN (
          'NSE_SECTOR_ROT_CONFIG_V3',
          'NSE_SECTOR_ROT_RUN_V3',
          'NSE_SECTOR_ROTATION_SNAP_V3',
          'NSE_SECTOR_ROT_COMP_V3'
        )
          AND (status <> 'ENABLED' OR validated <> 'VALIDATED')~'
  );

  check_expected(
    'documented default config exists once',
    q'~SELECT COUNT(*)
         FROM nse_sector_rot_config_v3
        WHERE config_version = 'V3_DEFAULT_20260715'
          AND model_version = 'SECTOR_ROTATION_V3'~',
    1
  );

  check_zero(
    'invalid configured factor-weight sums',
    q'~SELECT COUNT(*)
         FROM nse_sector_rot_config_v3
        WHERE ABS(
              momentum_weight + breadth_weight + trend_weight
            + money_flow_weight + risk_weight + data_quality_weight - 1
        ) > 0.000001~'
  );

  check_zero(
    'invalid momentum-horizon weight sums',
    q'~SELECT COUNT(*)
         FROM nse_sector_rot_config_v3
        WHERE ABS(
              horizon_21_weight + horizon_63_weight
            + horizon_126_weight + horizon_252_weight - 1
        ) > 0.000001~'
  );

  check_zero(
    'invalid breadth-blend weight sums',
    q'~SELECT COUNT(*)
         FROM nse_sector_rot_config_v3
        WHERE ABS(
              breadth_equal_weight + breadth_ffmc_weight
            + breadth_mcap_weight - 1
        ) > 0.000001~'
  );

  check_zero(
    'overlapping ACTIVE configs for one model',
    q'~SELECT COUNT(*)
         FROM nse_sector_rot_config_v3 a
         JOIN nse_sector_rot_config_v3 b
           ON b.model_version = a.model_version
          AND b.config_version > a.config_version
          AND b.status = 'ACTIVE'
          AND a.status = 'ACTIVE'
          AND b.effective_from <= NVL(a.effective_to, DATE '9999-12-31')
          AND a.effective_from <= NVL(b.effective_to, DATE '9999-12-31')~'
  );

  check_zero(
    'run metadata disagrees with config',
    q'~SELECT COUNT(*)
         FROM nse_sector_rot_run_v3 r
         JOIN nse_sector_rot_config_v3 c
           ON c.config_version = r.config_version
        WHERE r.model_version <> c.model_version
           OR r.config_hash <> c.config_hash
           OR r.benchmark_code <> c.benchmark_code
           OR r.benchmark_version <> c.benchmark_version
           OR r.universe_version <> c.universe_version~'
  );

  check_zero(
    'published runs without complete snapshot counts',
    q'~SELECT COUNT(*)
         FROM nse_sector_rot_run_v3 r
        WHERE r.status = 'SUCCESS'
          AND r.is_published = 'Y'
          AND r.row_count <> (
            SELECT COUNT(*)
              FROM nse_sector_rotation_snap_v3 s
             WHERE s.run_id = r.run_id
          )~'
  );

  check_zero(
    'snapshot metadata disagrees with owning run',
    q'~SELECT COUNT(*)
         FROM nse_sector_rotation_snap_v3 s
         JOIN nse_sector_rot_run_v3 r
           ON r.run_id = s.run_id
        WHERE s.as_of_date <> r.as_of_date
           OR s.model_version <> r.model_version
           OR s.config_version <> r.config_version
           OR s.benchmark_code <> r.benchmark_code
           OR s.benchmark_version <> r.benchmark_version
           OR s.universe_version <> r.universe_version~'
  );

  check_zero(
    'snapshot scores outside 0-100',
    q'~SELECT COUNT(*)
         FROM nse_sector_rotation_snap_v3
        WHERE (momentum_score IS NOT NULL AND momentum_score NOT BETWEEN 0 AND 100)
           OR (breadth_score IS NOT NULL AND breadth_score NOT BETWEEN 0 AND 100)
           OR (trend_score IS NOT NULL AND trend_score NOT BETWEEN 0 AND 100)
           OR (money_flow_score IS NOT NULL AND money_flow_score NOT BETWEEN 0 AND 100)
           OR (risk_score IS NOT NULL AND risk_score NOT BETWEEN 0 AND 100)
           OR (data_quality_score IS NOT NULL AND data_quality_score NOT BETWEEN 0 AND 100)
           OR (final_rotation_score IS NOT NULL AND final_rotation_score NOT BETWEEN 0 AND 100)~'
  );

  check_zero(
    'valid final scores missing core factors',
    q'~SELECT COUNT(*)
         FROM nse_sector_rotation_snap_v3
        WHERE final_rotation_score IS NOT NULL
          AND (
               momentum_score IS NULL
            OR breadth_score IS NULL
            OR trend_score IS NULL
            OR risk_score IS NULL
          )~'
  );

  check_zero(
    'DATA_WEAK/core-missing state mismatch',
    q'~SELECT COUNT(*)
         FROM nse_sector_rotation_snap_v3
        WHERE (final_rotation_score IS NULL AND rotation_phase <> 'DATA_WEAK')
           OR (final_rotation_score IS NOT NULL AND rotation_phase = 'DATA_WEAK')~'
  );

  check_zero(
    'published snapshots without six factor records',
    q'~SELECT COUNT(*)
         FROM nse_sector_rotation_snap_v3 s
         JOIN nse_sector_rot_run_v3 r
           ON r.run_id = s.run_id
          AND r.status = 'SUCCESS'
          AND r.is_published = 'Y'
        WHERE 6 <> (
          SELECT COUNT(*)
            FROM nse_sector_rot_comp_v3 c
           WHERE c.run_id = s.run_id
             AND c.sector_code = s.sector_code
        )~'
  );

  check_zero(
    'component metadata disagrees with snapshot',
    q'~SELECT COUNT(*)
         FROM nse_sector_rot_comp_v3 c
         JOIN nse_sector_rotation_snap_v3 s
           ON s.run_id = c.run_id
          AND s.sector_code = c.sector_code
        WHERE c.as_of_date <> s.as_of_date
           OR c.model_version <> s.model_version
           OR c.config_version <> s.config_version~'
  );

  check_zero(
    'component scores disagree with snapshot',
    q'~SELECT COUNT(*)
         FROM nse_sector_rot_comp_v3 c
         JOIN nse_sector_rotation_snap_v3 s
           ON s.run_id = c.run_id
          AND s.sector_code = c.sector_code
        WHERE DECODE(
          c.normalized_score,
          CASE c.component_code
            WHEN 'MOMENTUM' THEN s.momentum_score
            WHEN 'BREADTH' THEN s.breadth_score
            WHEN 'TREND' THEN s.trend_score
            WHEN 'MONEY_FLOW' THEN s.money_flow_score
            WHEN 'RISK' THEN s.risk_score
            WHEN 'DATA_QUALITY' THEN s.data_quality_score
          END,
          0,
          1
        ) = 1~'
  );

  check_zero(
    'configured component weights disagree with config',
    q'~SELECT COUNT(*)
         FROM nse_sector_rot_comp_v3 c
         JOIN nse_sector_rot_config_v3 cfg
           ON cfg.config_version = c.config_version
        WHERE ABS(
          c.configured_weight -
          CASE c.component_code
            WHEN 'MOMENTUM' THEN cfg.momentum_weight
            WHEN 'BREADTH' THEN cfg.breadth_weight
            WHEN 'TREND' THEN cfg.trend_weight
            WHEN 'MONEY_FLOW' THEN cfg.money_flow_weight
            WHEN 'RISK' THEN cfg.risk_weight
            WHEN 'DATA_QUALITY' THEN cfg.data_quality_weight
          END
        ) > 0.000001~'
  );

  check_zero(
    'effective weights do not sum to one',
    q'~SELECT COUNT(*)
         FROM nse_sector_rotation_snap_v3 s
         JOIN (
           SELECT run_id, sector_code, SUM(effective_weight) AS effective_weight_sum
           FROM nse_sector_rot_comp_v3
           GROUP BY run_id, sector_code
         ) c
           ON c.run_id = s.run_id
          AND c.sector_code = s.sector_code
        WHERE s.final_rotation_score IS NOT NULL
          AND ABS(c.effective_weight_sum - 1) > 0.000001~'
  );

  check_zero(
    'final score disagrees with weighted components',
    q'~SELECT COUNT(*)
         FROM nse_sector_rotation_snap_v3 s
         JOIN (
           SELECT
             run_id,
             sector_code,
             SUM(NVL(normalized_score, 0) * effective_weight) AS recomputed_score
           FROM nse_sector_rot_comp_v3
           GROUP BY run_id, sector_code
         ) c
           ON c.run_id = s.run_id
          AND c.sector_code = s.sector_code
         JOIN nse_sector_rot_run_v3 r
           ON r.run_id = s.run_id
         JOIN nse_sector_rot_config_v3 cfg
           ON cfg.config_version = r.config_version
        WHERE s.final_rotation_score IS NOT NULL
          AND ABS(
                s.final_rotation_score
                - GREATEST(
                    0,
                    c.recomputed_score
                    - CASE
                        WHEN s.weight_redistribution_applied = 'Y'
                        THEN cfg.missing_money_flow_penalty
                        ELSE 0
                      END
                  )
              ) > 0.001~'
  );

  check_zero(
    'required core component unavailable on scored row',
    q'~SELECT COUNT(*)
         FROM nse_sector_rotation_snap_v3 s
         JOIN nse_sector_rot_comp_v3 c
           ON c.run_id = s.run_id
          AND c.sector_code = s.sector_code
        WHERE s.final_rotation_score IS NOT NULL
          AND c.component_code IN ('MOMENTUM', 'BREADTH', 'TREND', 'RISK', 'DATA_QUALITY')
          AND (c.is_required <> 'Y' OR c.is_available <> 'Y')~'
  );

  check_zero(
    'non-positive current rank',
    q'~SELECT COUNT(*)
         FROM nse_sector_rotation_snap_v3
        WHERE current_rank IS NOT NULL
          AND current_rank <= 0~'
  );

  check_zero(
    'duplicate current ranks within one run',
    q'~SELECT COUNT(*) FROM (
         SELECT run_id, current_rank
         FROM nse_sector_rotation_snap_v3
         WHERE current_rank IS NOT NULL
         GROUP BY run_id, current_rank
         HAVING COUNT(*) > 1
       )~'
  );

  check_zero(
    'rank order disagrees with final score',
    q'~SELECT COUNT(*)
         FROM nse_sector_rotation_snap_v3 stronger
         JOIN nse_sector_rotation_snap_v3 weaker
           ON weaker.run_id = stronger.run_id
          AND weaker.sector_code <> stronger.sector_code
        WHERE stronger.final_rotation_score > weaker.final_rotation_score
          AND stronger.current_rank >= weaker.current_rank~'
  );

  IF v_failures > 0 THEN
    RAISE_APPLICATION_ERROR(
      -20050,
      'Sector Rotation V3 validation failed: ' || v_failures || ' assertion(s).'
    );
  END IF;

  DBMS_OUTPUT.PUT_LINE('PASS | All Sector Rotation V3 integrity assertions succeeded.');
END;
/

PROMPT === Latest published snapshot summary (empty is valid before first run) ===

COLUMN RUN_ID FORMAT A24;
COLUMN IS_PUBLISHED FORMAT A12;

SELECT
  run_id,
  as_of_date,
  model_version,
  status,
  is_published,
  row_count,
  calculation_duration_ms,
  completed_at
FROM (
  SELECT r.*
  FROM nse_sector_rot_run_v3 r
  WHERE r.model_version = 'SECTOR_ROTATION_V3'
    AND r.status = 'SUCCESS'
    AND r.is_published = 'Y'
  ORDER BY r.as_of_date DESC, r.completed_at DESC, r.run_id DESC
)
WHERE ROWNUM = 1;

PROMPT === Optimizer plan for the canonical V3 API snapshot read ===
PROMPT The expected shape is IX_SEC_ROT_RUN_V3_PUB -> PK_SEC_ROT_SNAP_V3 -> small score sort.

EXPLAIN PLAN SET STATEMENT_ID = 'SEC_ROT_V3_API'
FOR
WITH latest_run AS (
  SELECT run_id
  FROM (
    SELECT
      r.run_id,
      ROW_NUMBER() OVER (
        ORDER BY r.as_of_date DESC, r.completed_at DESC, r.run_id DESC
      ) AS rn
    FROM nse_sector_rot_run_v3 r
    WHERE r.model_version = 'SECTOR_ROTATION_V3'
      AND r.is_published = 'Y'
      AND r.status = 'SUCCESS'
  )
  WHERE rn = 1
)
SELECT s.*
FROM latest_run r
JOIN nse_sector_rotation_snap_v3 s
  ON s.run_id = r.run_id
ORDER BY s.final_rotation_score DESC NULLS LAST, s.sector_name, s.sector_code;

SELECT plan_table_output
FROM TABLE(
  DBMS_XPLAN.DISPLAY(
    'PLAN_TABLE',
    'SEC_ROT_V3_API',
    'BASIC +PREDICATE +ALIAS'
  )
);

PROMPT Sector Rotation V3 validation completed successfully.
