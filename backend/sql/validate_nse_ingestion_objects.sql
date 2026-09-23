PROMPT Validate NSE ingestion objects.

SELECT table_name
FROM user_tables
WHERE table_name IN (
  'CVING_NSE_MARKET_CAP_HIST',
  'CVING_NSE_MCAP_PIPELINE_RUNS',
  'CVING_NSE_FFMC_HIST',
  'CVING_NSE_FFMC_PIPELINE_RUNS',
  'CVING_NSE_DELIVERY_HIST'
)
ORDER BY table_name;

SELECT view_name
FROM user_views
WHERE view_name IN (
  'VW_CVING_NSE_MARKET_CAP_LATEST',
  'VW_CVING_NSE_FFMC_LATEST',
  'VW_CVING_NSE_DELIVERY_LATEST'
)
ORDER BY view_name;

SELECT index_name, table_name
FROM user_indexes
WHERE table_name IN ('CVING_NSE_MARKET_CAP_HIST', 'CVING_NSE_MCAP_PIPELINE_RUNS', 'CVING_NSE_FFMC_HIST', 'CVING_NSE_FFMC_PIPELINE_RUNS', 'CVING_NSE_DELIVERY_HIST')
ORDER BY table_name, index_name;

SELECT trade_date, source_name, COUNT(*) row_count
FROM CVING_NSE_MARKET_CAP_HIST
GROUP BY trade_date, source_name
ORDER BY trade_date DESC, source_name;

SELECT trade_date, source_name, COUNT(*) row_count
FROM CVING_NSE_FFMC_HIST
GROUP BY trade_date, source_name
ORDER BY trade_date DESC, source_name;

SELECT trade_date, source_name, COUNT(*) row_count
FROM CVING_NSE_DELIVERY_HIST
GROUP BY trade_date, source_name
ORDER BY trade_date DESC, source_name;

SELECT run_type, status, COUNT(*) run_count
FROM CVING_NSE_MCAP_PIPELINE_RUNS
GROUP BY run_type, status
ORDER BY run_type, status;

SELECT run_type, status, COUNT(*) run_count
FROM CVING_NSE_FFMC_PIPELINE_RUNS
GROUP BY run_type, status
ORDER BY run_type, status;
