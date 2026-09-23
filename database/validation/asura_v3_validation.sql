-- Asura V3 validation queries (read-only)
-- Run against Oracle after deploying /api/strategy/asura-v3 endpoints.

-- 1) Dashboard summary count
SELECT COUNT(1) AS dashboard_summary_count
FROM VW_ASURA_V3_3_DASHBOARD_SUMMARY;

-- 2) Latest signals count
SELECT COUNT(1) AS latest_signals_count
FROM VW_ASURA_V3_3_LATEST_SIGNALS;

-- 3) Yearly summary count
SELECT COUNT(1) AS yearly_summary_count
FROM VW_ASURA_V3_3_YEARLY_SUMMARY;

-- 4) Risk summary count
SELECT COUNT(1) AS risk_summary_count
FROM VW_ASURA_V3_3_RISK_SUMMARY;

-- 5) Cost summary count
SELECT COUNT(1) AS cost_summary_count
FROM VW_ASURA_V3_3_COST_SUMMARY;

-- 6) Symbol rating distribution
SELECT UPPER(NVL(SYMBOL_RATING, 'UNKNOWN')) AS symbol_rating,
       COUNT(1) AS total_symbols
FROM VW_ASURA_V3_2_SYMBOL_RATING
GROUP BY UPPER(NVL(SYMBOL_RATING, 'UNKNOWN'))
ORDER BY symbol_rating;

-- 7) Latest signal sample
SELECT *
FROM VW_ASURA_V3_3_LATEST_SIGNALS
ORDER BY SIGNAL_DATE DESC NULLS LAST, SYMBOL ASC
FETCH FIRST 10 ROWS ONLY;

-- 8) RRR validation (expect ratio near 1 where risk is non-zero)
SELECT SYMBOL,
       SIGNAL_DATE,
       ENTRY_PRICE,
       STOP_LOSS,
       TARGET_1R,
       ROUND((TARGET_1R - ENTRY_PRICE) / NULLIF((ENTRY_PRICE - STOP_LOSS), 0), 2) AS computed_rrr
FROM VW_ASURA_V3_3_LATEST_SIGNALS
WHERE ENTRY_PRICE IS NOT NULL
  AND STOP_LOSS IS NOT NULL
  AND TARGET_1R IS NOT NULL
  AND NULLIF((ENTRY_PRICE - STOP_LOSS), 0) IS NOT NULL
FETCH FIRST 100 ROWS ONLY;
