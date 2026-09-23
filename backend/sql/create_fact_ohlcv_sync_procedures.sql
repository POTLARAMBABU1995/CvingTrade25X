PROMPT Creating FACT_OHLCV sync procedures.

CREATE OR REPLACE NONEDITIONABLE PROCEDURE PR_SYNC_DIM_SYMBOLS_FROM_DEV (
  p_default_sector         IN VARCHAR2 DEFAULT 'UNASSIGNED',
  p_default_market_cap_seg IN VARCHAR2 DEFAULT NULL
) AS
BEGIN
  LOCK TABLE DIM_SYMBOLS IN SHARE ROW EXCLUSIVE MODE;

  UPDATE DIM_SYMBOLS s
     SET s.IS_ACTIVE = 'Y',
         s.LAST_UPDATED = SYSTIMESTAMP
   WHERE NVL(s.IS_ACTIVE, 'N') <> 'Y'
     AND EXISTS (
       SELECT 1
       FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV d
       WHERE UPPER(TRIM(d.SYMBOL)) = UPPER(TRIM(s.SYMBOL))
     );

  INSERT INTO DIM_SYMBOLS (
    SYMBOL_ID,
    SYMBOL,
    SECTOR,
    MARKET_CAP_SEG,
    IS_ACTIVE,
    COMPANY_NAME,
    LAST_UPDATED
  )
  WITH new_symbols AS (
    SELECT DISTINCT UPPER(TRIM(d.SYMBOL)) AS symbol
    FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV d
    LEFT JOIN DIM_SYMBOLS s
      ON UPPER(TRIM(s.SYMBOL)) = UPPER(TRIM(d.SYMBOL))
    WHERE d.SYMBOL IS NOT NULL
      AND s.SYMBOL_ID IS NULL
  ),
  base_id AS (
    SELECT NVL(MAX(SYMBOL_ID), 0) AS max_symbol_id
    FROM DIM_SYMBOLS
  )
  SELECT
    base_id.max_symbol_id + ROW_NUMBER() OVER (ORDER BY ns.symbol) AS symbol_id,
    ns.symbol,
    p_default_sector,
    p_default_market_cap_seg,
    'Y',
    ns.symbol,
    SYSTIMESTAMP
  FROM new_symbols ns
  CROSS JOIN base_id;
END;
/

CREATE OR REPLACE NONEDITIONABLE PROCEDURE PR_MERGE_FACT_OHLCV_FROM_DEV (
  p_from_date IN DATE DEFAULT NULL,
  p_to_date   IN DATE DEFAULT NULL
) AS
BEGIN
  MERGE INTO FACT_OHLCV tgt
  USING (
    SELECT
      s.SYMBOL_ID,
      d.TRADING_DATE,
      CAST(d.OPEN AS NUMBER(18, 6)) AS open_val,
      CAST(d.HIGH AS NUMBER(18, 6)) AS high_val,
      CAST(d.LOW AS NUMBER(18, 6)) AS low_val,
      CAST(d.PREVIOUS_CLOSE AS NUMBER(18, 6)) AS previous_close_val,
      CAST(d.VOLUME AS NUMBER(18, 6)) AS volume_val
    FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV d
    JOIN DIM_SYMBOLS s
      ON UPPER(TRIM(s.SYMBOL)) = UPPER(TRIM(d.SYMBOL))
    WHERE d.TRADING_DATE IS NOT NULL
      AND (p_from_date IS NULL OR d.TRADING_DATE >= p_from_date)
      AND (p_to_date IS NULL OR d.TRADING_DATE <= p_to_date)
  ) src
    ON (tgt.SYMBOL_ID = src.SYMBOL_ID AND tgt.TRADING_DATE = src.TRADING_DATE)
  WHEN MATCHED THEN UPDATE SET
    tgt.OPEN = src.open_val,
    tgt.HIGH = src.high_val,
    tgt.LOW = src.low_val,
    tgt.PREVIOUS_CLOSE = src.previous_close_val,
    tgt.VOLUME = src.volume_val
  WHERE NVL(tgt.OPEN, -999999999999999) <> NVL(src.open_val, -999999999999999)
     OR NVL(tgt.HIGH, -999999999999999) <> NVL(src.high_val, -999999999999999)
     OR NVL(tgt.LOW, -999999999999999) <> NVL(src.low_val, -999999999999999)
     OR NVL(tgt.PREVIOUS_CLOSE, -999999999999999) <> NVL(src.previous_close_val, -999999999999999)
     OR NVL(tgt.VOLUME, -999999999999999) <> NVL(src.volume_val, -999999999999999)
  WHEN NOT MATCHED THEN INSERT (
    SYMBOL_ID,
    TRADING_DATE,
    OPEN,
    HIGH,
    LOW,
    PREVIOUS_CLOSE,
    VOLUME
  ) VALUES (
    src.SYMBOL_ID,
    src.TRADING_DATE,
    src.open_val,
    src.high_val,
    src.low_val,
    src.previous_close_val,
    src.volume_val
  );
END;
/

CREATE OR REPLACE NONEDITIONABLE PROCEDURE PR_SYNC_FACT_OHLCV_FROM_DEV (
  p_from_date IN DATE DEFAULT NULL,
  p_to_date   IN DATE DEFAULT NULL
) AS
BEGIN
  PR_SYNC_DIM_SYMBOLS_FROM_DEV;
  PR_MERGE_FACT_OHLCV_FROM_DEV(p_from_date => p_from_date, p_to_date => p_to_date);
  COMMIT;
END;
/
