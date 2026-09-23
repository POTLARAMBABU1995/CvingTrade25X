--------------------------------------------------------
--  Backup generated - 2026-03-29 15:01:25
--------------------------------------------------------
--  Source owner: SYSTEM
--  Source container: CDB$ROOT
--  Source object type: PROCEDURE
--  Source object name: PR_MERGE_FACT_OHLCV_FROM_DEV

CREATE OR REPLACE NONEDITIONABLE PROCEDURE "PR_MERGE_FACT_OHLCV_FROM_DEV" (
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
