-- ATH validation queries for CvingTrade25X
-- Source table fixed for ATH: NSE_NIFTY500_DAILY_RAW_DATA_DEV
-- Rule: ATH = highest historical HIGH per SYMBOL

-- 1) Production ATH query for all symbols (ATH + ATH_DATE)
SELECT
    SYMBOL,
    HIGH AS ATH,
    TRADING_DATE AS ATH_DATE
FROM (
    SELECT
        SYMBOL,
        HIGH,
        TRADING_DATE,
        ROW_NUMBER() OVER (
            PARTITION BY SYMBOL
            ORDER BY HIGH DESC, TRADING_DATE DESC
        ) AS RN
    FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV
)
WHERE RN = 1
ORDER BY SYMBOL;


-- 2) Sample-symbol ATH validation query
SELECT
    SYMBOL,
    HIGH AS ATH,
    TRADING_DATE AS ATH_DATE
FROM (
    SELECT
        SYMBOL,
        HIGH,
        TRADING_DATE,
        ROW_NUMBER() OVER (
            PARTITION BY SYMBOL
            ORDER BY HIGH DESC, TRADING_DATE DESC
        ) AS RN
    FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV
    WHERE SYMBOL IN (
        '360ONE',
        'AADHARHFC',
        'AARTIIND',
        'AAVAS',
        'ABB',
        'ABCAPITAL',
        'ABDL',
        'ABFRL',
        'ABREL',
        'ABSLAMC',
        'ACC'
    )
)
WHERE RN = 1
ORDER BY SYMBOL;


-- 3) Compare ATH with latest current price proxy (latest PREVIOUS_CLOSE in raw table)
WITH ath_source AS (
    SELECT
        SYMBOL,
        HIGH AS ATH,
        TRADING_DATE AS ATH_DATE
    FROM (
        SELECT
            SYMBOL,
            HIGH,
            TRADING_DATE,
            ROW_NUMBER() OVER (
                PARTITION BY SYMBOL
                ORDER BY HIGH DESC, TRADING_DATE DESC
            ) AS RN
        FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV
    )
    WHERE RN = 1
),
current_price_source AS (
    SELECT
        SYMBOL,
        PREVIOUS_CLOSE AS CURRENT_PRICE
    FROM (
        SELECT
            SYMBOL,
            PREVIOUS_CLOSE,
            TRADING_DATE,
            ROW_NUMBER() OVER (
                PARTITION BY SYMBOL
                ORDER BY TRADING_DATE DESC
            ) AS RN
        FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV
    )
    WHERE RN = 1
)
SELECT
    x.SYMBOL,
    x.ATH,
    x.ATH_DATE,
    y.CURRENT_PRICE,
    ROUND(((x.ATH - y.CURRENT_PRICE) / x.ATH) * 100, 2) AS DISTANCE_FROM_ATH_PERCENT
FROM ath_source x
JOIN current_price_source y
  ON x.SYMBOL = y.SYMBOL
ORDER BY x.SYMBOL;


-- 4) Optional index checks before any index creation
SELECT INDEX_NAME, TABLE_NAME, STATUS
FROM USER_INDEXES
WHERE TABLE_NAME = 'NSE_NIFTY500_DAILY_RAW_DATA_DEV'
ORDER BY INDEX_NAME;

SELECT INDEX_NAME, COLUMN_NAME, COLUMN_POSITION
FROM USER_IND_COLUMNS
WHERE TABLE_NAME = 'NSE_NIFTY500_DAILY_RAW_DATA_DEV'
ORDER BY INDEX_NAME, COLUMN_POSITION;
