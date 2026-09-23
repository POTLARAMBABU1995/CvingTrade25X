WITH
__PRICE_SOURCE_CTE__,
anchor_date AS (
    SELECT MAX(p.trading_date) AS trade_date
    FROM price_source p
    WHERE :requested_trade_date IS NULL
       OR p.trading_date <= :requested_trade_date
),
sector_master AS (
    SELECT sector_code, sector_name, index_code, display_order
    FROM (
        SELECT
            t.sector_code,
            t.sector_name,
            t.index_code,
            NVL(t.display_order, 9999) AS display_order,
            ROW_NUMBER() OVER (
                PARTITION BY t.sector_code
                ORDER BY NVL(t.display_order, 9999), t.sector_name
            ) AS rn
        FROM nse_sector_master t
    )
    WHERE rn = 1
),
symbol_universe AS (
    SELECT DISTINCT
        sm.sector_code,
        m.sector_name,
        m.index_code,
        m.display_order,
        UPPER(TRIM(sm.symbol)) AS symbol
    FROM nse_symbol_sector_map sm
    JOIN sector_master m
      ON m.sector_code = sm.sector_code
),
mcap_ranked AS (
    SELECT
        u.symbol,
        t.trade_date,
        t.total_mcap_cr,
        ROW_NUMBER() OVER (
            PARTITION BY u.symbol
            ORDER BY t.trade_date DESC, t.fetch_ts DESC NULLS LAST, t.id DESC
        ) AS rn
    FROM symbol_universe u
    LEFT JOIN cving_nse_market_cap_hist t
      ON UPPER(TRIM(t.symbol)) = u.symbol
     AND t.trade_date = (SELECT trade_date FROM anchor_date)
     AND NVL(UPPER(t.fetch_status), 'SUCCESS') = 'SUCCESS'
),
mcap_latest AS (
    SELECT symbol, total_mcap_cr
    FROM mcap_ranked
    WHERE rn = 1
),
ffmc_ranked AS (
    SELECT
        u.symbol,
        t.trade_date,
        t.ffmc_cr,
        t.total_mcap_cr,
        ROW_NUMBER() OVER (
            PARTITION BY u.symbol
            ORDER BY t.trade_date DESC, t.fetch_ts DESC NULLS LAST, t.id DESC
        ) AS rn
    FROM symbol_universe u
    LEFT JOIN cving_nse_ffmc_hist t
      ON UPPER(TRIM(t.symbol)) = u.symbol
     AND t.trade_date = (SELECT trade_date FROM anchor_date)
     AND NVL(UPPER(t.fetch_status), 'SUCCESS') = 'SUCCESS'
),
ffmc_latest AS (
    SELECT symbol, ffmc_cr, total_mcap_cr
    FROM ffmc_ranked
    WHERE rn = 1
),
anchor_weights AS (
    SELECT
        u.sector_code,
        u.sector_name,
        u.index_code,
        u.display_order,
        u.symbol,
        NVL(m.total_mcap_cr, 0) AS total_mcap_cr,
        NVL(f.ffmc_cr, m.total_mcap_cr) AS ffmc_cr,
        CASE
            WHEN NVL(m.total_mcap_cr, 0) > 0 THEN m.total_mcap_cr
            WHEN NVL(f.ffmc_cr, 0) > 0 THEN f.ffmc_cr
            ELSE 1
        END AS return_weight
    FROM symbol_universe u
    LEFT JOIN mcap_latest m
      ON m.symbol = u.symbol
    LEFT JOIN ffmc_latest f
      ON f.symbol = u.symbol
),
price_ranked AS (
    SELECT
        aw.sector_code,
        aw.sector_name,
        aw.index_code,
        aw.display_order,
        aw.symbol,
        p.trading_date,
        p.close_price,
        p.high_price,
        p.low_price,
        p.volume,
        ROW_NUMBER() OVER (
            PARTITION BY aw.symbol
            ORDER BY p.trading_date DESC
        ) AS rn_desc
    FROM anchor_weights aw
    JOIN price_source p
      ON p.symbol = aw.symbol
    WHERE p.trading_date <= (SELECT trade_date FROM anchor_date)
),
price_history AS (
    SELECT *
    FROM price_ranked
    WHERE rn_desc <= 320
),
price_calc1 AS (
    SELECT
        p.*,
        LAG(close_price) OVER (PARTITION BY symbol ORDER BY trading_date) AS prev_close_price,
        LAG(high_price) OVER (PARTITION BY symbol ORDER BY trading_date) AS prev_high_price,
        LAG(low_price) OVER (PARTITION BY symbol ORDER BY trading_date) AS prev_low_price,
        LAG(close_price, 21) OVER (PARTITION BY symbol ORDER BY trading_date) AS close_lag21,
        LAG(close_price, 55) OVER (PARTITION BY symbol ORDER BY trading_date) AS close_lag55,
        LAG(close_price, 63) OVER (PARTITION BY symbol ORDER BY trading_date) AS close_lag63,
        LAG(close_price, 126) OVER (PARTITION BY symbol ORDER BY trading_date) AS close_lag126,
        LAG(close_price, 252) OVER (PARTITION BY symbol ORDER BY trading_date) AS close_lag252,
        AVG(close_price) OVER (PARTITION BY symbol ORDER BY trading_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS sma20,
        AVG(close_price) OVER (PARTITION BY symbol ORDER BY trading_date ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) AS sma50,
        AVG(close_price) OVER (PARTITION BY symbol ORDER BY trading_date ROWS BETWEEN 99 PRECEDING AND CURRENT ROW) AS sma100,
        AVG(close_price) OVER (PARTITION BY symbol ORDER BY trading_date ROWS BETWEEN 199 PRECEDING AND CURRENT ROW) AS sma200,
        AVG(volume) OVER (PARTITION BY symbol ORDER BY trading_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS volume_ma20
    FROM price_history p
),
price_calc2 AS (
    SELECT
        c1.*,
        CASE WHEN prev_close_price > 0 THEN (close_price / prev_close_price) - 1 END AS daily_ret,
        close_price - prev_close_price AS delta_close,
        GREATEST(close_price - prev_close_price, 0) AS gain,
        GREATEST(prev_close_price - close_price, 0) AS loss,
        GREATEST(
            high_price - low_price,
            GREATEST(ABS(high_price - prev_close_price), ABS(low_price - prev_close_price))
        ) AS true_range,
        CASE
            WHEN prev_high_price IS NOT NULL
             AND prev_low_price IS NOT NULL
             AND (high_price - prev_high_price) > (prev_low_price - low_price)
             AND (high_price - prev_high_price) > 0
            THEN (high_price - prev_high_price)
            ELSE 0
        END AS plus_dm,
        CASE
            WHEN prev_high_price IS NOT NULL
             AND prev_low_price IS NOT NULL
             AND (prev_low_price - low_price) > (high_price - prev_high_price)
             AND (prev_low_price - low_price) > 0
            THEN (prev_low_price - low_price)
            ELSE 0
        END AS minus_dm,
        CASE WHEN close_lag21 > 0 THEN (close_price / close_lag21) - 1 END AS ret21,
        CASE WHEN close_lag55 > 0 THEN (close_price / close_lag55) - 1 END AS ret55,
        CASE WHEN close_lag63 > 0 THEN (close_price / close_lag63) - 1 END AS ret63,
        CASE WHEN close_lag126 > 0 THEN (close_price / close_lag126) - 1 END AS ret126,
        CASE WHEN close_lag252 > 0 THEN (close_price / close_lag252) - 1 END AS ret252
    FROM price_calc1 c1
),
price_calc3 AS (
    SELECT
        c2.*,
        AVG(gain) OVER (PARTITION BY symbol ORDER BY trading_date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS avg_gain14,
        AVG(loss) OVER (PARTITION BY symbol ORDER BY trading_date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS avg_loss14,
        SUM(true_range) OVER (PARTITION BY symbol ORDER BY trading_date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS sum_tr14,
        SUM(plus_dm) OVER (PARTITION BY symbol ORDER BY trading_date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS sum_plus_dm14,
        SUM(minus_dm) OVER (PARTITION BY symbol ORDER BY trading_date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS sum_minus_dm14,
        STDDEV_SAMP(daily_ret) OVER (PARTITION BY symbol ORDER BY trading_date ROWS BETWEEN 62 PRECEDING AND CURRENT ROW) AS sigma63_stock,
        MAX(close_price) OVER (PARTITION BY symbol ORDER BY trading_date ROWS BETWEEN 125 PRECEDING AND CURRENT ROW) AS peak126
    FROM price_calc2 c2
),
price_calc4 AS (
    SELECT
        c3.*,
        CASE WHEN sum_tr14 > 0 THEN 100 * sum_plus_dm14 / sum_tr14 END AS plus_di14,
        CASE WHEN sum_tr14 > 0 THEN 100 * sum_minus_dm14 / sum_tr14 END AS minus_di14,
        CASE WHEN peak126 > 0 THEN (close_price / peak126) - 1 END AS drawdown126
    FROM price_calc3 c3
),
price_calc5 AS (
    SELECT
        c4.*,
        CASE
            WHEN avg_loss14 IS NULL THEN NULL
            WHEN avg_loss14 = 0 AND avg_gain14 = 0 THEN 50
            WHEN avg_loss14 = 0 THEN 100
            ELSE 100 - (100 / (1 + (avg_gain14 / NULLIF(avg_loss14, 0))))
        END AS rsi14,
        CASE
            WHEN plus_di14 IS NOT NULL
             AND minus_di14 IS NOT NULL
             AND (plus_di14 + minus_di14) > 0
            THEN 100 * ABS(plus_di14 - minus_di14) / NULLIF(plus_di14 + minus_di14, 0)
        END AS dx,
        MIN(drawdown126) OVER (PARTITION BY symbol ORDER BY trading_date ROWS BETWEEN 125 PRECEDING AND CURRENT ROW) AS max_drawdown126
    FROM price_calc4 c4
),
price_calc6 AS (
    SELECT
        c5.*,
        AVG(dx) OVER (PARTITION BY symbol ORDER BY trading_date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS adx14
    FROM price_calc5 c5
),
benchmark_daily_returns AS (
    SELECT
        p.trading_date,
        SUM(p.daily_ret * aw.return_weight) / NULLIF(SUM(aw.return_weight), 0) AS benchmark_daily_ret
    FROM price_calc6 p
    JOIN anchor_weights aw
      ON aw.symbol = p.symbol
    WHERE p.daily_ret IS NOT NULL
    GROUP BY p.trading_date
),
sector_daily_returns AS (
    SELECT
        p.trading_date,
        p.sector_code,
        p.sector_name,
        p.index_code,
        p.display_order,
        SUM(p.daily_ret * aw.return_weight) / NULLIF(SUM(aw.return_weight), 0) AS sector_daily_ret
    FROM price_calc6 p
    JOIN anchor_weights aw
      ON aw.symbol = p.symbol
    WHERE p.daily_ret IS NOT NULL
    GROUP BY p.trading_date, p.sector_code, p.sector_name, p.index_code, p.display_order
),
benchmark_series AS (
    SELECT
        b.*,
        EXP(
            SUM(CASE WHEN 1 + benchmark_daily_ret > 0 THEN LN(1 + benchmark_daily_ret) END)
            OVER (ORDER BY trading_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        ) AS benchmark_index
    FROM benchmark_daily_returns b
),
benchmark_feat AS (
    SELECT
        b.*,
        LAG(benchmark_index, 21) OVER (ORDER BY trading_date) AS benchmark_index_lag21,
        LAG(benchmark_index, 55) OVER (ORDER BY trading_date) AS benchmark_index_lag55,
        LAG(benchmark_index, 63) OVER (ORDER BY trading_date) AS benchmark_index_lag63,
        LAG(benchmark_index, 126) OVER (ORDER BY trading_date) AS benchmark_index_lag126,
        LAG(benchmark_index, 252) OVER (ORDER BY trading_date) AS benchmark_index_lag252
    FROM benchmark_series b
),
benchmark_anchor AS (
    SELECT
        trading_date,
        CASE WHEN benchmark_index_lag21 > 0 THEN (benchmark_index / benchmark_index_lag21) - 1 END AS benchmark_return21,
        CASE WHEN benchmark_index_lag55 > 0 THEN (benchmark_index / benchmark_index_lag55) - 1 END AS benchmark_return55,
        CASE WHEN benchmark_index_lag63 > 0 THEN (benchmark_index / benchmark_index_lag63) - 1 END AS benchmark_return63,
        CASE WHEN benchmark_index_lag126 > 0 THEN (benchmark_index / benchmark_index_lag126) - 1 END AS benchmark_return126,
        CASE WHEN benchmark_index_lag252 > 0 THEN (benchmark_index / benchmark_index_lag252) - 1 END AS benchmark_return252
    FROM benchmark_feat
    WHERE trading_date = (SELECT trade_date FROM anchor_date)
),
stock_anchor_metrics AS (
    SELECT
        p.symbol,
        p.sector_code,
        p.sector_name,
        p.index_code,
        p.display_order,
        p.trading_date,
        p.close_price,
        p.prev_close_price,
        p.high_price,
        p.low_price,
        p.ret21,
        p.ret55,
        p.ret63,
        p.ret126,
        p.ret252,
        p.rsi14,
        p.sma20,
        p.sma50,
        p.sma100,
        p.sma200,
        p.adx14,
        p.volume,
        p.volume_ma20,
        aw.total_mcap_cr,
        aw.ffmc_cr,
        CASE WHEN p.ret55 IS NOT NULL AND ba.benchmark_return55 IS NOT NULL AND (p.ret55 - ba.benchmark_return55) > 0 THEN 1 ELSE 0 END AS rs55_gt0_flag,
        CASE WHEN p.rsi14 > 50 THEN 1 ELSE 0 END AS rsi14_gt50_flag,
        CASE WHEN p.close_price > p.sma20 THEN 1 ELSE 0 END AS above_sma20_flag,
        CASE WHEN p.close_price > p.sma50 THEN 1 ELSE 0 END AS above_sma50_flag,
        CASE WHEN p.close_price > p.sma100 THEN 1 ELSE 0 END AS above_sma100_flag,
        CASE WHEN p.close_price > p.sma200 THEN 1 ELSE 0 END AS above_sma200_flag,
        CASE WHEN p.adx14 > 20 THEN 1 ELSE 0 END AS adx14_gt20_flag,
        CASE WHEN p.volume_ma20 IS NOT NULL AND p.volume > p.volume_ma20 THEN 1 ELSE 0 END AS volume_gt_ma20_flag
    FROM price_calc6 p
    JOIN anchor_weights aw
      ON aw.symbol = p.symbol
    CROSS JOIN benchmark_anchor ba
    WHERE p.rn_desc = 1
),
breadth_by_sector AS (
    SELECT
        sector_code,
        sector_name,
        index_code,
        display_order,
        COUNT(*) AS total_symbols,
        ROUND(100 * AVG(rs55_gt0_flag), 2) AS rsi55_pct,
        ROUND(100 * AVG(rsi14_gt50_flag), 2) AS rsi50_pct,
        ROUND(100 * AVG(above_sma20_flag), 2) AS sma20_pct,
        ROUND(100 * AVG(above_sma50_flag), 2) AS sma50_pct,
        ROUND(100 * AVG(above_sma100_flag), 2) AS sma100_pct,
        (
            0.20 * AVG(rs55_gt0_flag) +
            0.10 * AVG(rsi14_gt50_flag) +
            0.15 * AVG(above_sma20_flag) +
            0.15 * AVG(above_sma50_flag) +
            0.10 * AVG(above_sma100_flag) +
            0.10 * AVG(above_sma200_flag) +
            0.10 * AVG(adx14_gt20_flag) +
            0.10 * AVG(volume_gt_ma20_flag)
        ) AS count_breadth,
        (
            0.20 * (SUM(NVL(total_mcap_cr, 0) * rs55_gt0_flag) / NULLIF(SUM(NVL(total_mcap_cr, 0)), 0)) +
            0.10 * (SUM(NVL(total_mcap_cr, 0) * rsi14_gt50_flag) / NULLIF(SUM(NVL(total_mcap_cr, 0)), 0)) +
            0.15 * (SUM(NVL(total_mcap_cr, 0) * above_sma20_flag) / NULLIF(SUM(NVL(total_mcap_cr, 0)), 0)) +
            0.15 * (SUM(NVL(total_mcap_cr, 0) * above_sma50_flag) / NULLIF(SUM(NVL(total_mcap_cr, 0)), 0)) +
            0.10 * (SUM(NVL(total_mcap_cr, 0) * above_sma100_flag) / NULLIF(SUM(NVL(total_mcap_cr, 0)), 0)) +
            0.10 * (SUM(NVL(total_mcap_cr, 0) * above_sma200_flag) / NULLIF(SUM(NVL(total_mcap_cr, 0)), 0)) +
            0.10 * (SUM(NVL(total_mcap_cr, 0) * adx14_gt20_flag) / NULLIF(SUM(NVL(total_mcap_cr, 0)), 0)) +
            0.10 * (SUM(NVL(total_mcap_cr, 0) * volume_gt_ma20_flag) / NULLIF(SUM(NVL(total_mcap_cr, 0)), 0))
        ) AS mcap_breadth,
        (
            0.20 * (SUM(NVL(COALESCE(ffmc_cr, total_mcap_cr), 0) * rs55_gt0_flag) / NULLIF(SUM(NVL(COALESCE(ffmc_cr, total_mcap_cr), 0)), 0)) +
            0.10 * (SUM(NVL(COALESCE(ffmc_cr, total_mcap_cr), 0) * rsi14_gt50_flag) / NULLIF(SUM(NVL(COALESCE(ffmc_cr, total_mcap_cr), 0)), 0)) +
            0.15 * (SUM(NVL(COALESCE(ffmc_cr, total_mcap_cr), 0) * above_sma20_flag) / NULLIF(SUM(NVL(COALESCE(ffmc_cr, total_mcap_cr), 0)), 0)) +
            0.15 * (SUM(NVL(COALESCE(ffmc_cr, total_mcap_cr), 0) * above_sma50_flag) / NULLIF(SUM(NVL(COALESCE(ffmc_cr, total_mcap_cr), 0)), 0)) +
            0.10 * (SUM(NVL(COALESCE(ffmc_cr, total_mcap_cr), 0) * above_sma100_flag) / NULLIF(SUM(NVL(COALESCE(ffmc_cr, total_mcap_cr), 0)), 0)) +
            0.10 * (SUM(NVL(COALESCE(ffmc_cr, total_mcap_cr), 0) * above_sma200_flag) / NULLIF(SUM(NVL(COALESCE(ffmc_cr, total_mcap_cr), 0)), 0)) +
            0.10 * (SUM(NVL(COALESCE(ffmc_cr, total_mcap_cr), 0) * adx14_gt20_flag) / NULLIF(SUM(NVL(COALESCE(ffmc_cr, total_mcap_cr), 0)), 0)) +
            0.10 * (SUM(NVL(COALESCE(ffmc_cr, total_mcap_cr), 0) * volume_gt_ma20_flag) / NULLIF(SUM(NVL(COALESCE(ffmc_cr, total_mcap_cr), 0)), 0))
        ) AS ffmc_breadth
    FROM stock_anchor_metrics
    GROUP BY sector_code, sector_name, index_code, display_order
),
breadth_scored AS (
    SELECT
        b.*,
        (0.50 * NVL(mcap_breadth, 0)) +
        (0.20 * NVL(ffmc_breadth, NVL(mcap_breadth, 0))) +
        (0.30 * NVL(count_breadth, 0)) AS breadth_composite
    FROM breadth_by_sector b
),
delivery_recent AS (
    SELECT
        sam.sector_code,
        sam.symbol,
        d.trade_date,
        d.delivery_qty,
        d.delivery_pct,
        d.total_traded_qty,
        d.no_of_trades,
        d.turnover_lacs,
        ROW_NUMBER() OVER (
            PARTITION BY sam.symbol
            ORDER BY d.trade_date DESC, d.fetch_ts DESC NULLS LAST, d.id DESC
        ) AS rn_desc
    FROM stock_anchor_metrics sam
    LEFT JOIN cving_nse_delivery_hist d
      ON UPPER(TRIM(d.symbol)) = sam.symbol
     AND d.trade_date <= (SELECT trade_date FROM anchor_date)
     AND NVL(UPPER(d.fetch_status), 'SUCCESS') = 'SUCCESS'
),
delivery_stats AS (
    SELECT
        sector_code,
        symbol,
        MAX(CASE WHEN rn_desc = 1 AND trade_date = (SELECT trade_date FROM anchor_date) THEN trade_date END) AS latest_delivery_date,
        MAX(CASE WHEN rn_desc = 1 AND trade_date = (SELECT trade_date FROM anchor_date) THEN delivery_qty END) AS latest_delivery_qty,
        MAX(CASE WHEN rn_desc = 1 AND trade_date = (SELECT trade_date FROM anchor_date) THEN delivery_pct END) AS latest_delivery_pct,
        MAX(CASE WHEN rn_desc = 1 AND trade_date = (SELECT trade_date FROM anchor_date) THEN total_traded_qty END) AS latest_traded_qty,
        MAX(CASE WHEN rn_desc = 1 AND trade_date = (SELECT trade_date FROM anchor_date) THEN no_of_trades END) AS latest_trade_count,
        MAX(CASE WHEN rn_desc = 1 AND trade_date = (SELECT trade_date FROM anchor_date) THEN turnover_lacs END) AS latest_turnover_lacs,
        AVG(CASE WHEN rn_desc <= 20 THEN delivery_qty END) AS avg_delivery_qty_20,
        AVG(CASE WHEN rn_desc <= 20 THEN total_traded_qty END) AS avg_traded_qty_20,
        AVG(CASE WHEN rn_desc <= 20 THEN no_of_trades END) AS avg_trade_count_20,
        AVG(CASE WHEN rn_desc <= 20 THEN delivery_pct END) AS avg_delivery_pct_20
    FROM delivery_recent
    GROUP BY sector_code, symbol
),
delivery_scored AS (
    SELECT
        d.*,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latest_delivery_pct)
            OVER (PARTITION BY sector_code) AS sector_median_delivery_pct,
        CASE
            WHEN latest_delivery_pct IS NOT NULL
             AND latest_delivery_pct >= GREATEST(NVL(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latest_delivery_pct)
                OVER (PARTITION BY sector_code), 0), :delivery_pct_floor)
            THEN 1 ELSE 0
        END AS delivery_pct_pass,
        CASE
            WHEN latest_delivery_qty IS NOT NULL
             AND avg_delivery_qty_20 IS NOT NULL
             AND avg_delivery_qty_20 > 0
             AND latest_delivery_qty >= (avg_delivery_qty_20 * :delivery_qty_multiplier)
            THEN 1 ELSE 0
        END AS delivery_qty_pass,
        CASE
            WHEN latest_traded_qty IS NOT NULL
             AND avg_traded_qty_20 IS NOT NULL
             AND avg_traded_qty_20 > 0
             AND latest_traded_qty >= (avg_traded_qty_20 * :trade_qty_multiplier)
            THEN 1 ELSE 0
        END AS trade_qty_pass,
        CASE
            WHEN latest_trade_count IS NOT NULL
             AND avg_trade_count_20 IS NOT NULL
             AND avg_trade_count_20 > 0
             AND latest_trade_count >= (avg_trade_count_20 * :trade_count_multiplier)
            THEN 1 ELSE 0
        END AS trade_count_pass
    FROM delivery_stats d
),
delivery_sector AS (
    SELECT
        sector_code,
        COUNT(CASE WHEN latest_delivery_date IS NOT NULL THEN 1 END) AS screened_stocks,
        AVG(CASE WHEN latest_delivery_date IS NOT NULL THEN latest_delivery_pct END) AS delivery_participation_score,
        COUNT(
            CASE
                WHEN latest_delivery_date IS NOT NULL
                 AND (
                    (0.40 * delivery_pct_pass) +
                    (0.30 * delivery_qty_pass) +
                    (0.20 * trade_qty_pass) +
                    (0.10 * trade_count_pass)
                 ) >= :stock_confirmation_min_score
                THEN 1
            END
        ) AS confirmed_stocks,
        AVG(
            CASE
                WHEN latest_delivery_date IS NOT NULL THEN
                    (0.40 * delivery_pct_pass) +
                    (0.30 * delivery_qty_pass) +
                    (0.20 * trade_qty_pass) +
                    (0.10 * trade_count_pass)
            END
        ) AS avg_stock_confirmation_score
    FROM delivery_scored
    GROUP BY sector_code
),
money_flow_by_sector AS (
    SELECT
        sector_code,
        ROUND(AVG(CASE WHEN volume_ma20 > 0 THEN volume / volume_ma20 END), 6) AS volume_ratio20,
        ROUND(50 + 50 * (SUM(CASE WHEN close_price > prev_close_price THEN volume WHEN close_price < prev_close_price THEN -volume ELSE 0 END) / NULLIF(SUM(volume), 0)), 6) AS obv_slope_score,
        ROUND(AVG(CASE WHEN high_price > low_price THEN 100 * (close_price - low_price) / (high_price - low_price) END), 6) AS accumulation_score,
        ROUND(100 * SUM(CASE WHEN close_price >= prev_close_price THEN volume ELSE 0 END) / NULLIF(SUM(volume), 0), 6) AS up_down_volume_score,
        ROUND(100 * AVG(volume_gt_ma20_flag), 6) AS breadth_volume_score
    FROM stock_anchor_metrics
    GROUP BY sector_code
),
sector_series AS (
    SELECT
        s.*,
        EXP(
            SUM(CASE WHEN 1 + sector_daily_ret > 0 THEN LN(1 + sector_daily_ret) END)
            OVER (PARTITION BY sector_code ORDER BY trading_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        ) AS sector_index
    FROM sector_daily_returns s
),
sector_series_feat AS (
    SELECT
        s.*,
        LAG(sector_index, 21) OVER (PARTITION BY sector_code ORDER BY trading_date) AS sector_index_lag21,
        LAG(sector_index, 63) OVER (PARTITION BY sector_code ORDER BY trading_date) AS sector_index_lag63,
        LAG(sector_index, 126) OVER (PARTITION BY sector_code ORDER BY trading_date) AS sector_index_lag126,
        LAG(sector_index, 252) OVER (PARTITION BY sector_code ORDER BY trading_date) AS sector_index_lag252,
        AVG(sector_index) OVER (PARTITION BY sector_code ORDER BY trading_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS sector_sma20,
        AVG(sector_index) OVER (PARTITION BY sector_code ORDER BY trading_date ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) AS sector_sma50,
        AVG(sector_index) OVER (PARTITION BY sector_code ORDER BY trading_date ROWS BETWEEN 99 PRECEDING AND CURRENT ROW) AS sector_sma100,
        AVG(sector_index) OVER (PARTITION BY sector_code ORDER BY trading_date ROWS BETWEEN 199 PRECEDING AND CURRENT ROW) AS sector_sma200,
        STDDEV_SAMP(sector_daily_ret) OVER (PARTITION BY sector_code ORDER BY trading_date ROWS BETWEEN 62 PRECEDING AND CURRENT ROW) AS sigma63,
        MAX(sector_index) OVER (PARTITION BY sector_code ORDER BY trading_date ROWS BETWEEN 125 PRECEDING AND CURRENT ROW) AS sector_peak126
    FROM sector_series s
),
sector_series_feat2 AS (
    SELECT
        sf.*,
        MIN(CASE WHEN sector_peak126 > 0 THEN (sector_index / sector_peak126) - 1 END)
            OVER (PARTITION BY sector_code ORDER BY trading_date ROWS BETWEEN 125 PRECEDING AND CURRENT ROW) AS max_drawdown126
    FROM sector_series_feat sf
),
sector_anchor AS (
    SELECT
        sf.sector_code,
        sf.sector_name,
        sf.index_code,
        sf.display_order,
        sf.trading_date,
        CASE WHEN sf.sector_index_lag21 > 0 THEN (sf.sector_index / sf.sector_index_lag21) - 1 END AS sector_return21,
        CASE WHEN sf.sector_index_lag63 > 0 THEN (sf.sector_index / sf.sector_index_lag63) - 1 END AS sector_return63,
        CASE WHEN sf.sector_index_lag126 > 0 THEN (sf.sector_index / sf.sector_index_lag126) - 1 END AS sector_return126,
        CASE WHEN sf.sector_index_lag252 > 0 THEN (sf.sector_index / sf.sector_index_lag252) - 1 END AS sector_return252,
        CASE WHEN bf.benchmark_return21 IS NOT NULL THEN bf.benchmark_return21 END AS benchmark_return21,
        CASE WHEN bf.benchmark_return63 IS NOT NULL THEN bf.benchmark_return63 END AS benchmark_return63,
        CASE WHEN bf.benchmark_return126 IS NOT NULL THEN bf.benchmark_return126 END AS benchmark_return126,
        CASE WHEN bf.benchmark_return252 IS NOT NULL THEN bf.benchmark_return252 END AS benchmark_return252,
        CASE WHEN sf.sector_sma20  > 0 AND sf.sector_index > sf.sector_sma20  THEN 1 ELSE 0 END AS sector_above_sma20,
        CASE WHEN sf.sector_sma50  > 0 AND sf.sector_index > sf.sector_sma50  THEN 1 ELSE 0 END AS sector_above_sma50,
        CASE WHEN sf.sector_sma100 > 0 AND sf.sector_index > sf.sector_sma100 THEN 1 ELSE 0 END AS sector_above_sma100,
        CASE WHEN sf.sector_sma200 > 0 AND sf.sector_index > sf.sector_sma200 THEN 1 ELSE 0 END AS sector_above_sma200,
        CASE WHEN sf.sector_index_lag252 > 0 AND ((sf.sector_index / sf.sector_index_lag252) - 1) > 0 THEN 1 ELSE 0 END AS sector_ret252_positive,
        sf.sigma63,
        sf.max_drawdown126
    FROM sector_series_feat2 sf
    JOIN benchmark_anchor bf
      ON bf.trading_date = sf.trading_date
    WHERE sf.trading_date = (SELECT trade_date FROM anchor_date)
),
sector_factors AS (
    SELECT
        sa.sector_code,
        sa.sector_name,
        sa.index_code,
        sa.display_order,
        br.total_symbols,
        br.rsi55_pct,
        br.rsi50_pct,
        br.sma20_pct,
        br.sma50_pct,
        br.sma100_pct,
        br.count_breadth,
        br.mcap_breadth,
        br.ffmc_breadth,
        br.breadth_composite,
        (sa.sector_return21  - sa.benchmark_return21)  AS rel_ret21,
        (sa.sector_return63  - sa.benchmark_return63)  AS rel_ret63,
        (sa.sector_return126 - sa.benchmark_return126) AS rel_ret126,
        (sa.sector_return252 - sa.benchmark_return252) AS rel_ret252,
        (
            (0.20 * sa.sector_above_sma20) +
            (0.20 * sa.sector_above_sma50) +
            (0.20 * sa.sector_above_sma100) +
            (0.20 * sa.sector_above_sma200) +
            (0.20 * sa.sector_ret252_positive)
        ) AS absolute_trend,
        sa.sigma63,
        sa.max_drawdown126,
        mf.volume_ratio20,
        ds.delivery_participation_score,
        mf.obv_slope_score,
        mf.accumulation_score,
        mf.up_down_volume_score,
        mf.breadth_volume_score,
        NVL(ds.confirmed_stocks, 0) AS confirmed_stocks,
        NVL(ds.screened_stocks, 0) AS screened_stocks,
        NVL(ds.avg_stock_confirmation_score, 0) AS avg_stock_confirmation_score
    FROM sector_anchor sa
    JOIN breadth_scored br
      ON br.sector_code = sa.sector_code
    LEFT JOIN money_flow_by_sector mf
      ON mf.sector_code = sa.sector_code
    LEFT JOIN delivery_sector ds
      ON ds.sector_code = sa.sector_code
),
cross_stats AS (
    SELECT
        AVG(rel_ret21) AS avg_rel_ret21,
        STDDEV_SAMP(rel_ret21) AS std_rel_ret21,
        AVG(rel_ret63) AS avg_rel_ret63,
        STDDEV_SAMP(rel_ret63) AS std_rel_ret63,
        AVG(rel_ret126) AS avg_rel_ret126,
        STDDEV_SAMP(rel_ret126) AS std_rel_ret126,
        AVG(rel_ret252) AS avg_rel_ret252,
        STDDEV_SAMP(rel_ret252) AS std_rel_ret252,
        AVG(breadth_composite) AS avg_breadth,
        STDDEV_SAMP(breadth_composite) AS std_breadth,
        AVG(sigma63) AS avg_sigma63,
        STDDEV_SAMP(sigma63) AS std_sigma63,
        AVG(max_drawdown126) AS avg_max_drawdown126,
        STDDEV_SAMP(max_drawdown126) AS std_max_drawdown126
    FROM sector_factors
),
scored AS (
    SELECT
        sf.*,
        CASE WHEN cs.std_rel_ret21 > 0 THEN (sf.rel_ret21 - cs.avg_rel_ret21) / cs.std_rel_ret21 ELSE 0 END AS z_rel_ret21,
        CASE WHEN cs.std_rel_ret63 > 0 THEN (sf.rel_ret63 - cs.avg_rel_ret63) / cs.std_rel_ret63 ELSE 0 END AS z_rel_ret63,
        CASE WHEN cs.std_rel_ret126 > 0 THEN (sf.rel_ret126 - cs.avg_rel_ret126) / cs.std_rel_ret126 ELSE 0 END AS z_rel_ret126,
        CASE WHEN cs.std_rel_ret252 > 0 THEN (sf.rel_ret252 - cs.avg_rel_ret252) / cs.std_rel_ret252 ELSE 0 END AS z_rel_ret252,
        CASE WHEN cs.std_breadth > 0 THEN (sf.breadth_composite - cs.avg_breadth) / cs.std_breadth ELSE 0 END AS z_breadth,
        CASE WHEN cs.std_sigma63 > 0 THEN (sf.sigma63 - cs.avg_sigma63) / cs.std_sigma63 ELSE 0 END AS z_sigma63,
        CASE WHEN cs.std_max_drawdown126 > 0 THEN (sf.max_drawdown126 - cs.avg_max_drawdown126) / cs.std_max_drawdown126 ELSE 0 END AS z_max_drawdown126
    FROM sector_factors sf
    CROSS JOIN cross_stats cs
),
rotations AS (
    SELECT
        s.*,
        (
            (0.30 * z_rel_ret21) +
            (0.25 * z_rel_ret63) +
            (0.15 * z_rel_ret126) +
            (0.10 * z_rel_ret252) +
            (0.20 * z_breadth)
        ) AS relative_momentum,
        (0 - z_sigma63) AS risk_adjustment_min,
        ((-0.60 * z_sigma63) + (-0.40 * z_max_drawdown126)) AS risk_adjustment
    FROM scored s
),
final_rows AS (
    SELECT
        r.*,
        (
            (0.45 * relative_momentum) +
            (0.20 * absolute_trend) +
            (0.25 * breadth_composite) +
            (0.10 * risk_adjustment)
        ) AS rotation_score,
        (
            (
                (0.45 * relative_momentum) +
                (0.20 * absolute_trend) +
                (0.25 * breadth_composite) +
                (0.10 * risk_adjustment)
            ) * (0.5 + (0.5 * absolute_trend)) * (1 / (1 + GREATEST(NVL(sigma63, 0), 0)))
        ) AS final_rotation,
        CASE
            WHEN NVL(screened_stocks, 0) = 0 THEN 'Neutral / NA'
            WHEN (confirmed_stocks / NULLIF(screened_stocks, 0)) >= :stock_confirmation_strong_ratio
                THEN 'Strong (' || confirmed_stocks || '/' || screened_stocks || ')'
            WHEN (confirmed_stocks / NULLIF(screened_stocks, 0)) >= :stock_confirmation_moderate_ratio
                THEN 'Moderate (' || confirmed_stocks || '/' || screened_stocks || ')'
            ELSE 'Weak (' || confirmed_stocks || '/' || screened_stocks || ')'
        END AS stock_confirmation_screening,
        CASE
            WHEN NVL(screened_stocks, 0) = 0 THEN 'Neutral'
            WHEN (confirmed_stocks / NULLIF(screened_stocks, 0)) >= :stock_confirmation_strong_ratio THEN 'Strong'
            WHEN (confirmed_stocks / NULLIF(screened_stocks, 0)) >= :stock_confirmation_moderate_ratio THEN 'Moderate'
            ELSE 'Weak'
        END AS stock_confirmation_label
    FROM rotations r
)
SELECT
    sector_code AS "sectorCode",
    sector_name AS "sectorName",
    index_code AS "indexCode",
    total_symbols AS "totalSymbols",
    rsi55_pct AS "rsi55Pct",
    rsi50_pct AS "rsi50Pct",
    sma20_pct AS "sma20Pct",
    sma50_pct AS "sma50Pct",
    sma100_pct AS "sma100Pct",
    (SELECT trade_date FROM anchor_date) AS "asOfDate",
    ROUND(relative_momentum, 6) AS "relativeMomentum",
    ROUND(absolute_trend, 6) AS "absoluteTrend",
    ROUND(breadth_composite, 6) AS "breadthComposite",
    ROUND(mcap_breadth, 6) AS "mcapBreadth",
    ROUND(ffmc_breadth, 6) AS "ffmcBreadth",
    ROUND(count_breadth, 6) AS "countBreadth",
    ROUND(risk_adjustment, 6) AS "riskAdjustment",
    ROUND(rotation_score, 6) AS "rotationScore",
    ROUND(final_rotation, 6) AS "finalRotation",
    volume_ratio20 AS "volumeRatio20",
    ROUND(delivery_participation_score, 6) AS "deliveryParticipationScore",
    obv_slope_score AS "obvSlopeScore",
    accumulation_score AS "accumulationScore",
    up_down_volume_score AS "upDownVolumeScore",
    breadth_volume_score AS "breadthVolumeScore",
    ROUND(CASE WHEN COUNT(*) OVER () = 1 THEN 100 ELSE 100 * PERCENT_RANK() OVER (ORDER BY final_rotation) END, 2) AS "rankScore",
    stock_confirmation_screening AS "stockConfirmationScreening",
    stock_confirmation_label AS "stockConfirmationLabel",
    confirmed_stocks AS "confirmedStocks",
    screened_stocks AS "screenedStocks",
    ROUND(avg_stock_confirmation_score, 6) AS "stockConfirmationScoreAvg"
FROM final_rows
ORDER BY final_rotation DESC NULLS LAST, sector_name, sector_code
