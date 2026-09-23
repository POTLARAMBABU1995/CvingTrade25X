-- Base Oracle query used by /api/sector/<sector>/stocks/sector-wise.
-- Trend is resolved in backend by reusing SR_LEVELS output.
-- GAP and EMA flags are backend-driven.

WITH ranked AS (
    SELECT
        UPPER(TRIM(snap.symbol)) AS symbol,
        snap.ltc_date AS ltc_date,
        snap.close_price AS price,
        snap.ath AS ath,
        snap.high_52w AS high_52w,
        snap.low_52w AS low_52w,
        snap.ema20 AS ema20,
        snap.ema50 AS ema50,
        snap.ema100 AS ema100,
        snap.ema200 AS ema200,
        ROW_NUMBER() OVER (
            PARTITION BY UPPER(TRIM(snap.symbol))
            ORDER BY snap.ltc_date DESC NULLS LAST, snap.close_price DESC NULLS LAST
        ) AS rn
    FROM mv_nse_sector_ui_snapshot snap
    WHERE snap.sector = :sector_code
)
SELECT
    symbol,
    ltc_date,
    price,
    ROUND(((price - ath) / NULLIF(ath, 0)) * 100, 2) AS gap_pct,
    high_52w,
    low_52w,
    ath,
    CASE WHEN price > ema20 THEN 'Y' ELSE 'N' END AS ema20_flag,
    CASE WHEN price > ema50 THEN 'Y' ELSE 'N' END AS ema50_flag,
    CASE WHEN price > ema100 THEN 'Y' ELSE 'N' END AS ema100_flag,
    CASE WHEN price > ema200 THEN 'Y' ELSE 'N' END AS ema200_flag
FROM ranked
WHERE rn = 1;
