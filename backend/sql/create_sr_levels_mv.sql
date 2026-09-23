-- Materialized view to precompute support & resistance summaries.
-- Run as a privileged user and adjust tablespace/index options for your environment.

CREATE MATERIALIZED VIEW sr_levels_mv
NOLOGGING
PARALLEL
BUILD IMMEDIATE
REFRESH FAST ON DEMAND
ENABLE QUERY REWRITE
AS
SELECT
    s.symbol,
    s.timeframe,
    s.tolerance,
    s.price,
    s.trading_date,
    s.ltc_date,
    s.trading_days,
    s.support_display,
    s.resistance_display,
    s.score,
    s.trend_direction
FROM sr_levels_agg s;

CREATE INDEX ix_sr_levels_mv_tf_tol_sym
    ON sr_levels_mv (timeframe, tolerance, symbol)
    COMPRESS 2;

GRANT SELECT ON sr_levels_mv TO cving_app;
