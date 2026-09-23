# CvingTrade25X Page and API to Oracle Object Mapping

## Scope

- Runtime confirmed against `SYSTEM@orcl` in `CDB$ROOT`.
- Live application owner discovered so far: `SYSTEM`.
- Export scope approved for execution: object-list export only.
- `ORCLPDB` was observed as mounted only and is not part of the current runtime path.

## Used-Live Mappings

| Page / UI entry | Frontend / API path | Oracle objects | Notes |
| --- | --- | --- | --- |
| `html/Database.html` | `assets/js/database.js` -> `/api/marketdata/*` | `NSE_NIFTY500_DAILY_RAW_DATA_DEV`, `FACT_OHLCV`, `DIM_SYMBOLS`, `NSE_NIFTY50_LARGECAP`, `NSE_NIFTY150_MIDCAP`, `NSE_NIFTY250_SMALLCAP`, `V_NSE500_EMA_DAILY`, `V_NSE_NIFTY50_LARGECAP_OHLCV`, `V_NSE_NIFTY150_MIDCAP_OHLCV`, `V_NSE_NIFTY250_SMALLCAP_OHLCV` | Core market data and derived daily signals |
| `html/dashboard.html` | `assets/js/dashboard.js` -> `/api/dashboard/movers` | `GAINERS_TOP25`, `LOOSERS_TOP25`, `VOLUME_MOVERS_TOP25` | Yamuna mover summary tables |
| `html/EMA.html` | `assets/js/trend.js` -> `/api/trend*` | `NSE_NIFTY500_DAILY_RAW_DATA_DEV`, `V_NSE500_EMA_DAILY` | EMA breakout and trend page |
| `html/RSI50.html` | `assets/js/rsi50.js` -> `/api/rsi50` | `NSE_NIFTY500_DAILY_RAW_DATA_DEV`, `V_NSE500_EMA_DAILY` | RSI over 50 screener |
| `html/VOLUME.html` | `assets/js/volume.js` -> `/api/volume` | `NSE_NIFTY500_DAILY_RAW_DATA_DEV`, `V_NSE500_EMA_DAILY` | Volume expansion page |
| `html/ADX.html` | `assets/js/adx.js` -> `/api/adx` | `NSE_NIFTY500_DAILY_RAW_DATA_DEV`, `V_NSE500_EMA_DAILY` | ADX screener |
| `html/ATR14.html` | `assets/js/atr14.js` -> `/api/atr14` | `NSE_NIFTY500_DAILY_RAW_DATA_DEV`, `V_NSE500_EMA_DAILY` | ATR screener |
| `html/PriceAction.html` | `assets/js/price-action.js` -> `/api/price-action-sr-levels-manually` | `PRICE_ACTION_SR_LEVELS_MANUALLY` | Manual SR storage only |
| `html/Asura.html` | `assets/js/asura.js`, `assets/js/strategy-agent-ui.js` -> `/api/asura*`, `/api/strategy-agent/*` | `ASURA_BULLISH_TREND_STRATEGY_TESTING`, `ASURA_SCAN_DAILY_FACT`, `V_ASURA_SCAN_LATEST`, `ASURA_BTS_SEQ`, `CVING_STRATEGY_PARAMS`, `CVING_STRATEGY_AGENT_RUNS`, `CVING_STRATEGY_AGENT_BACKTESTS` | Asura daily scan plus strategy agent state |
| `html/Strategy.html` | `assets/js/strategy.js`, `assets/js/strategy-agent-ui.js` -> `/api/dashboard/movers`, `/api/strategy-agent/*` | `GAINERS_TOP25`, `LOOSERS_TOP25`, `VOLUME_MOVERS_TOP25`, `CVING_STRATEGY_PARAMS`, `CVING_STRATEGY_AGENT_RUNS`, `CVING_STRATEGY_AGENT_BACKTESTS` | Yamuna mover layouts and strategy agent history |
| `html/Yamuna.html` | `backend/routes/yamuna.py` and shared mover endpoints | `GAINERS_TOP25`, `LOOSERS_TOP25`, `VOLUME_MOVERS_TOP25`, `CVING_STRATEGY_AGENT_RUNS`, `CVING_STRATEGY_AGENT_BACKTESTS`, `CVING_STRATEGY_PARAMS` | Strategy page family uses Yamuna mover data and shared agent persistence |
| `html/Bhramhastra.html` | `assets/js/bhramhastra.js` -> `/api/bhramhastra*` | `BHRAMHASTRA_BACKTESTING_DATA`, `CVING_STRATEGY_AGENT_RUNS`, `CVING_STRATEGY_AGENT_BACKTESTS`, `CVING_STRATEGY_PARAMS` | Backtesting and insert/update workflow |
| `html/Bhramhaputra.html` | `assets/js/bhramhaputra.js` -> `/api/bhramhaputra` | `FACT_OHLCV`, `DIM_SYMBOLS`, `PRICE_ACTION_SR_LEVELS_MANUALLY` | Live DB table `BHRAMHAPUTRA_SCAN` was not confirmed; current page still depends on shared market and SR data |
| `html/SectorRotation.html` | `assets/js/sector-rotation.js` -> `/api/sectors*` | `FACT_OHLCV`, `CVING_NSE_MARKET_CAP_HIST`, `CVING_NSE_FFMC_HIST`, `MV_NSE_SECTOR_UI_SNAPSHOT` | `MV_NSE_SECTOR_BREADTH` is code-referenced but missing live |
| `html/Sector_*.html` detail pages | Shared sector rotation APIs | `FACT_OHLCV`, `CVING_NSE_MARKET_CAP_HIST`, `CVING_NSE_FFMC_HIST`, `MV_NSE_SECTOR_UI_SNAPSHOT` | Sector drill-downs inherit the same backend data path |
| `html/NSE_MARKET_CAP.html` | `assets/js/nse-market-cap.js` -> `/api/marketdata/nse-mcap/*` | `CVING_NSE_MARKET_CAP_HIST`, `CVING_NSE_MCAP_PIPELINE_RUNS`, `VW_CVING_NSE_MARKET_CAP_LATEST` | Shared run table also holds non-market-cap run types |
| `html/NSE_FFMC.html` | `assets/js/nse-ffmc.js` -> `/api/marketdata/nse-ffmc/*` | `CVING_NSE_FFMC_HIST`, `CVING_NSE_FFMC_PIPELINE_RUNS`, `VW_CVING_NSE_FFMC_LATEST` | Dedicated FFMC history and run tracking |
| `html/NSE_Delivery_Data.html` | `assets/js/nse-delivery-data.js` -> `/api/marketdata/nse-delivery/*` | `CVING_NSE_DELIVERY_HIST`, `CVING_NSE_MCAP_PIPELINE_RUNS`, `VW_CVING_NSE_DELIVERY_LATEST` | Delivery run tracking reuses `CVING_NSE_MCAP_PIPELINE_RUNS` with `RUN_TYPE='DELIVERY'` |
| `html/login.html` and `html/register.html` | `assets/js/auth.js`, `assets/js/session.js` -> `/api/auth/*` | `REGISTRATIONS`, `LOGIN_ACTIVITY`, `AUTH_SESSIONS`, `AUTH_QUICK_MPIN` | All auth persistence currently under `SYSTEM` |

## Present in Live DB but Not Yet Proven Page-Used

| Object | Type | Why it is retained in inventory |
| --- | --- | --- |
| `ASURA_TRADE_BOOK` | Table | Live object found in Oracle, but not proven from current page scan |
| `VW_SYMBOL_CAP_BUCKET` | View | Live view used by sync procedures; not directly page-bound |
| `PR_SYNC_DIM_SYMBOLS_FROM_DEV` | Procedure | Live ETL helper for market data consistency |
| `PR_MERGE_FACT_OHLCV_FROM_DEV` | Procedure | Live ETL helper for `FACT_OHLCV` |
| `PR_SYNC_FACT_OHLCV_FROM_DEV` | Procedure | Live ETL helper referenced by sector rotation service |
| `PR_SYNC_DIM_SYMBOLS_CAP_SEG_FROM_INDICES` | Procedure | Live ETL helper |
| `PR_SYNC_NSE_SYMBOL_SECTOR_MAP_FROM_STAGING` | Procedure | Live ETL helper |
| `PR_SYNC_SECTOR_REFERENCE_DATA` | Procedure | Live sector refresh helper |
| `MV_NIFTY50_DAILY_SNAP` | Materialized view | Live but invalid; capture before any remedial work |
| `MV_NIFTY_MIDCAP150_DAILY_SNAP` | Materialized view | Live but invalid; capture before any remedial work |
| `MV_NIFTY_SMALLCAP250_DAILY_SNAP` | Materialized view | Live but invalid; capture before any remedial work |
| `MV_NSE50_DAILY_6M` | Materialized view | Live but invalid; capture before any remedial work |
| `MV_NSE_NIFTY500_EMA_BASE` | Materialized view | Live and valid; base layer for EMA-derived outputs |
| `MV_NSE_SECTOR_UI_SNAPSHOT` | Materialized view | Live but invalid; sector APIs still reference it |

## Code-Defined or Stale References Not Confirmed Live

| Object | State | Notes |
| --- | --- | --- |
| `OHLCV_D`, `OHLCV_W`, `OHLCV_M`, `OHLCV_Y` | Code-only stale | Present in code paths, not confirmed in live Oracle inventory |
| `SYMBOLS`, `INDICATORS_D`, `PIVOTS`, `PATTERNS`, `ZONES` | Code-only stale | Legacy or alternate schema references |
| `FYERS_HOLDINGS_IMPORTS`, `FYERS_HOLDINGS_CURRENT`, `FYERS_HOLDINGS_AUDIT` | Code-defined but not found live | Repo contains DDL and service code; live DB confirmation was negative at the time of scan |
| `BHRAMHAPUTRA_SCAN` | Code-defined but not found live | DDL exists in repo; live DB confirmation pending |
| `BHRAMHASTRA_BACKTEST` | Code-defined but not found live | Separate repo DDL exists; live object not confirmed |
| `MV_ASURA_SCAN_DAILY`, `MV_ASURA_SCAN_WEEKLY` | Code-defined but not found live | Referenced by Asura services, not confirmed live |
| `ASURA_SCAN_WEEKLY_FACT`, `V_ASURA_SCAN_WEEKLY_LATEST` | Code-defined but not found live | Weekly Asura branch not confirmed live |
| `MV_NSE_SECTOR_BREADTH` | Missing live dependency | Sector refresh route attempts to refresh it, but live object lookup returned no rows |

## Highest-Risk Live Tables

| Owner.Object | Tablespace | Approx live row count | Risk |
| --- | --- | --- | --- |
| `SYSTEM.NSE_NIFTY500_DAILY_RAW_DATA_DEV` | `SYSTEM` | `2,326,814` | Large heap table in system tablespace |
| `SYSTEM.FACT_OHLCV` | `SYSTEM` | `2,146,116` | Partitioned and subpartitioned; move must be partition-aware |
| `SYSTEM.CVING_NSE_MARKET_CAP_HIST` | `CVING_APP` | `188,894` | App data already off `SYSTEM`, but not yet under requested E-drive datafile path |
| `SYSTEM.CVING_NSE_FFMC_HIST` | `USERS` | `179,998` | App data in `USERS`, not yet under requested E-drive datafile path |
| `SYSTEM.CVING_NSE_DELIVERY_HIST` | `USERS` | `171,321` | Has LOB storage split across tablespaces |

## Placement Risks Observed

- App owner is `SYSTEM`, not a dedicated application schema.
- Multiple app tables remain in `SYSTEM`.
- Existing non-system app datafiles are on `E:\SOFTWARES\ORADATA\ORCL`, not the requested `E:\DB_BACKUP_SAFETY\ORADATA`.
- `CVING_NSE_DELIVERY_HIST.RESPONSE_PAYLOAD` is stored in `SYSTEM` even though the base table is in `USERS`.
- Invalid materialized views must be backed up before any recreation or move discussion.