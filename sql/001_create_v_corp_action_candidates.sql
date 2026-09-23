-- Corporate Actions Split / Bonus Detector (read-only view)
-- Creates:
--   V_CORP_ACTION_CANDIDATES
-- Source table (read-only):
--   NSE_NIFTY500_DAILY_RAW_DATA_DEV
--
-- Notes:
-- - No table DDL/DML is executed.
-- - Close-price column is auto-detected by priority:
--   PREVIOUS_CLOSE, CLOSE_PRICE, CLOSE, LTP, PRICE, LAST_PRICE, ADJ_CLOSE, CLOSING_PRICE

DECLARE
  v_close_col VARCHAR2(128);
  v_sql CLOB;
BEGIN
  BEGIN
    SELECT column_name
      INTO v_close_col
      FROM (
        SELECT
          c.column_name,
          CASE c.column_name
            WHEN 'PREVIOUS_CLOSE' THEN 1
            WHEN 'CLOSE_PRICE' THEN 2
            WHEN 'CLOSE' THEN 3
            WHEN 'LTP' THEN 4
            WHEN 'PRICE' THEN 5
            WHEN 'LAST_PRICE' THEN 6
            WHEN 'ADJ_CLOSE' THEN 7
            WHEN 'CLOSING_PRICE' THEN 8
            ELSE 999
          END AS ord
        FROM user_tab_columns c
        WHERE c.table_name = 'NSE_NIFTY500_DAILY_RAW_DATA_DEV'
          AND c.column_name IN (
            'PREVIOUS_CLOSE',
            'CLOSE_PRICE',
            'CLOSE',
            'LTP',
            'PRICE',
            'LAST_PRICE',
            'ADJ_CLOSE',
            'CLOSING_PRICE'
          )
        ORDER BY ord
      )
    WHERE ROWNUM = 1;
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      raise_application_error(
        -20001,
        'No supported close column found in NSE_NIFTY500_DAILY_RAW_DATA_DEV. Expected one of PREVIOUS_CLOSE/CLOSE_PRICE/CLOSE/LTP/PRICE/LAST_PRICE/ADJ_CLOSE/CLOSING_PRICE.'
      );
  END;

  v_sql := q'[
CREATE OR REPLACE VIEW V_CORP_ACTION_CANDIDATES AS
WITH base_data AS (
    SELECT
      SYMBOL,
      TRADING_DATE,
      ]' || v_close_col || q'[ AS PRICE,
      LAG(]' || v_close_col || q'[) OVER (
        PARTITION BY SYMBOL
        ORDER BY TRADING_DATE
      ) AS PREV_PRICE,
      LAG(TRADING_DATE) OVER (
        PARTITION BY SYMBOL
        ORDER BY TRADING_DATE
      ) AS PREV_TRADING_DATE
    FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV
    WHERE SYMBOL IS NOT NULL
      AND TRADING_DATE IS NOT NULL
      AND ]' || v_close_col || q'[ IS NOT NULL
      AND ]' || v_close_col || q'[ > 0
),
price_moves AS (
    SELECT
      SYMBOL,
      PREV_TRADING_DATE,
      TRADING_DATE,
      ROUND(PREV_PRICE, 4) AS PREV_PRICE,
      ROUND(PRICE, 4) AS PRICE,
      ROUND(((PREV_PRICE - PRICE) / PREV_PRICE) * 100, 4) AS DROP_PCT,
      ROUND(PRICE / PREV_PRICE, 6) AS ACTUAL_FACTOR
    FROM base_data
    WHERE PREV_PRICE IS NOT NULL
      AND PREV_PRICE > 0
      AND PRICE > 0
      AND PRICE < PREV_PRICE
),
factor_map AS (
    SELECT
      pm.*,
      ABS(pm.ACTUAL_FACTOR - 0.500000) AS D_SPLIT_12,
      ABS(pm.ACTUAL_FACTOR - 0.333333) AS D_SPLIT_13,
      ABS(pm.ACTUAL_FACTOR - 0.250000) AS D_SPLIT_14,
      ABS(pm.ACTUAL_FACTOR - 0.200000) AS D_SPLIT_15,
      ABS(pm.ACTUAL_FACTOR - 0.666667) AS D_BONUS_12,
      ABS(pm.ACTUAL_FACTOR - 0.750000) AS D_BONUS_13,
      ABS(pm.ACTUAL_FACTOR - 0.800000) AS D_BONUS_14,
      ABS(pm.ACTUAL_FACTOR - 0.833333) AS D_BONUS_15
    FROM price_moves pm
    WHERE pm.DROP_PCT >= 15
),
scored AS (
    SELECT
      fm.*,
      LEAST(
        fm.D_SPLIT_12,
        fm.D_SPLIT_13,
        fm.D_SPLIT_14,
        fm.D_SPLIT_15,
        fm.D_BONUS_12,
        fm.D_BONUS_13,
        fm.D_BONUS_14,
        fm.D_BONUS_15
      ) AS MIN_FACTOR_DIFF
    FROM factor_map fm
)
SELECT
  SYMBOL,
  PREV_TRADING_DATE,
  TRADING_DATE,
  PREV_PRICE,
  PRICE,
  DROP_PCT,
  ACTUAL_FACTOR,
  RTRIM(
    CASE WHEN D_SPLIT_12 <= 0.05 THEN 'SPLIT 1:2 / BONUS 1:1 / ' END ||
    CASE WHEN D_SPLIT_13 <= 0.05 THEN 'SPLIT 1:3 / ' END ||
    CASE WHEN D_SPLIT_14 <= 0.05 THEN 'SPLIT 1:4 / ' END ||
    CASE WHEN D_SPLIT_15 <= 0.05 THEN 'SPLIT 1:5 / ' END ||
    CASE WHEN D_BONUS_12 <= 0.05 THEN 'BONUS 1:2 / ' END ||
    CASE WHEN D_BONUS_13 <= 0.05 THEN 'BONUS 1:3 / ' END ||
    CASE WHEN D_BONUS_14 <= 0.05 THEN 'BONUS 1:4 / ' END ||
    CASE WHEN D_BONUS_15 <= 0.05 THEN 'BONUS 1:5 / ' END,
    ' /'
  ) AS POSSIBLE_ACTIONS,
  CASE
    WHEN D_SPLIT_12 = MIN_FACTOR_DIFF THEN 50.00
    WHEN D_SPLIT_13 = MIN_FACTOR_DIFF THEN 66.67
    WHEN D_SPLIT_14 = MIN_FACTOR_DIFF THEN 75.00
    WHEN D_SPLIT_15 = MIN_FACTOR_DIFF THEN 80.00
    WHEN D_BONUS_12 = MIN_FACTOR_DIFF THEN 33.33
    WHEN D_BONUS_13 = MIN_FACTOR_DIFF THEN 25.00
    WHEN D_BONUS_14 = MIN_FACTOR_DIFF THEN 20.00
    WHEN D_BONUS_15 = MIN_FACTOR_DIFF THEN 16.67
    ELSE NULL
  END AS EXPECTED_DROP_PCT,
  ROUND(
    GREATEST(0, 100 - (MIN_FACTOR_DIFF / 0.05) * 100),
    4
  ) AS CONFIDENCE_SCORE,
  CASE
    WHEN DROP_PCT >= 50 THEN 'HIGH_DROP'
    ELSE 'LOW_DROP'
  END AS DETECTION_BUCKET
FROM scored
WHERE MIN_FACTOR_DIFF <= 0.05
]';

  EXECUTE IMMEDIATE v_sql;
END;
/
