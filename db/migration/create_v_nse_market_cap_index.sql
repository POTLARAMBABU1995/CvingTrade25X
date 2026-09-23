-- Latest-date market-cap index classification view for NSE MarketCap Index page
CREATE OR REPLACE VIEW V_NSE_MARKET_CAP_INDEX AS
WITH latest_data AS (
  SELECT
    h.trade_date,
    h.symbol,
    h.symbol AS script,
    h.series AS mcap_series,
    h.security_name,
    h.total_mcap_cr AS market_cap_crores
  FROM CVING_NSE_MARKET_CAP_HIST h
  WHERE h.trade_date = (
    SELECT MAX(trade_date)
    FROM CVING_NSE_MARKET_CAP_HIST
    WHERE total_mcap_cr IS NOT NULL
  )
    AND h.total_mcap_cr IS NOT NULL
),
dedup_data AS (
  SELECT
    ld.trade_date,
    ld.script,
    ld.symbol,
    ld.mcap_series,
    ld.security_name,
    ld.market_cap_crores,
    ROW_NUMBER() OVER (
      PARTITION BY ld.symbol
      ORDER BY ld.market_cap_crores DESC NULLS LAST, ld.symbol ASC
    ) AS symbol_rn
  FROM latest_data ld
),
ranked_data AS (
  SELECT
    d.script,
    d.symbol,
    d.mcap_series,
    d.security_name,
    d.market_cap_crores,
    ROW_NUMBER() OVER (
      ORDER BY d.market_cap_crores DESC NULLS LAST, d.symbol ASC
    ) AS mcap_rank
  FROM dedup_data d
  WHERE d.symbol_rn = 1
)
SELECT
  r.script,
  r.symbol,
  CASE
    WHEN r.mcap_rank BETWEEN 1 AND 100 THEN 'LARGE'
    WHEN r.mcap_rank BETWEEN 101 AND 250 THEN 'MID'
    ELSE 'SMALL'
  END AS index_category,
  r.mcap_rank,
  r.market_cap_crores,
  r.mcap_series,
  r.security_name
FROM ranked_data r;

-- Recommended indexes on base table:
-- CREATE INDEX IDX_MCAP_HIST_TRADE_DATE ON CVING_NSE_MARKET_CAP_HIST (TRADE_DATE);
-- CREATE INDEX IDX_MCAP_HIST_SYMBOL_DATE ON CVING_NSE_MARKET_CAP_HIST (SYMBOL, TRADE_DATE);
-- CREATE INDEX IDX_MCAP_HIST_DATE_MCAP ON CVING_NSE_MARKET_CAP_HIST (TRADE_DATE, TOTAL_MCAP_CR);
