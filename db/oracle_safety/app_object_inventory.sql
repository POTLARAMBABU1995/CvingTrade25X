set echo off
set feedback on
set verify off
set pagesize 200
set linesize 260
set trimspool on
set serveroutput on size unlimited

column run_tag new_value run_tag
select to_char(systimestamp, 'YYYYMMDD_HH24MISS') as run_tag from dual;

spool E:\DB_BACKUP_SAFETY\REPORTS\app_object_inventory_&&run_tag..log

prompt ============================================================
prompt CvingTrade25X app object inventory
prompt ============================================================

with app_catalog as (
  select 'USED-LIVE' as object_state, 'TABLE' as object_type, 'SYSTEM' as owner, 'NSE_NIFTY500_DAILY_RAW_DATA_DEV' as object_name from dual union all
  select 'USED-LIVE', 'TABLE', 'SYSTEM', 'FACT_OHLCV' from dual union all
  select 'USED-LIVE', 'TABLE', 'SYSTEM', 'DIM_SYMBOLS' from dual union all
  select 'USED-LIVE', 'TABLE', 'SYSTEM', 'NSE_NIFTY50_LARGECAP' from dual union all
  select 'USED-LIVE', 'TABLE', 'SYSTEM', 'NSE_NIFTY150_MIDCAP' from dual union all
  select 'USED-LIVE', 'TABLE', 'SYSTEM', 'NSE_NIFTY250_SMALLCAP' from dual union all
  select 'USED-LIVE', 'TABLE', 'SYSTEM', 'ASURA_BULLISH_TREND_STRATEGY_TESTING' from dual union all
  select 'USED-LIVE', 'TABLE', 'SYSTEM', 'ASURA_SCAN_DAILY_FACT' from dual union all
  select 'USED-LIVE', 'TABLE', 'SYSTEM', 'GAINERS_TOP25' from dual union all
  select 'USED-LIVE', 'TABLE', 'SYSTEM', 'LOOSERS_TOP25' from dual union all
  select 'USED-LIVE', 'TABLE', 'SYSTEM', 'VOLUME_MOVERS_TOP25' from dual union all
  select 'USED-LIVE', 'TABLE', 'SYSTEM', 'BHRAMHASTRA_BACKTESTING_DATA' from dual union all
  select 'USED-LIVE', 'TABLE', 'SYSTEM', 'CVING_STRATEGY_PARAMS' from dual union all
  select 'USED-LIVE', 'TABLE', 'SYSTEM', 'CVING_STRATEGY_AGENT_RUNS' from dual union all
  select 'USED-LIVE', 'TABLE', 'SYSTEM', 'CVING_STRATEGY_AGENT_BACKTESTS' from dual union all
  select 'USED-LIVE', 'TABLE', 'SYSTEM', 'CVING_NSE_MARKET_CAP_HIST' from dual union all
  select 'USED-LIVE', 'TABLE', 'SYSTEM', 'CVING_NSE_MCAP_PIPELINE_RUNS' from dual union all
  select 'USED-LIVE', 'TABLE', 'SYSTEM', 'CVING_NSE_FFMC_HIST' from dual union all
  select 'USED-LIVE', 'TABLE', 'SYSTEM', 'CVING_NSE_FFMC_PIPELINE_RUNS' from dual union all
  select 'USED-LIVE', 'TABLE', 'SYSTEM', 'CVING_NSE_DELIVERY_HIST' from dual union all
  select 'USED-LIVE', 'TABLE', 'SYSTEM', 'REGISTRATIONS' from dual union all
  select 'USED-LIVE', 'TABLE', 'SYSTEM', 'LOGIN_ACTIVITY' from dual union all
  select 'USED-LIVE', 'TABLE', 'SYSTEM', 'AUTH_SESSIONS' from dual union all
  select 'USED-LIVE', 'TABLE', 'SYSTEM', 'AUTH_QUICK_MPIN' from dual union all
  select 'USED-LIVE', 'TABLE', 'SYSTEM', 'PRICE_ACTION_SR_LEVELS_MANUALLY' from dual union all
  select 'USED-LIVE', 'VIEW', 'SYSTEM', 'V_NSE500_EMA_DAILY' from dual union all
  select 'USED-LIVE', 'VIEW', 'SYSTEM', 'V_NSE_NIFTY50_LARGECAP_OHLCV' from dual union all
  select 'USED-LIVE', 'VIEW', 'SYSTEM', 'V_NSE_NIFTY150_MIDCAP_OHLCV' from dual union all
  select 'USED-LIVE', 'VIEW', 'SYSTEM', 'V_NSE_NIFTY250_SMALLCAP_OHLCV' from dual union all
  select 'USED-LIVE', 'VIEW', 'SYSTEM', 'V_ASURA_SCAN_LATEST' from dual union all
  select 'USED-LIVE', 'VIEW', 'SYSTEM', 'VW_CVING_NSE_MARKET_CAP_LATEST' from dual union all
  select 'USED-LIVE', 'VIEW', 'SYSTEM', 'VW_CVING_NSE_FFMC_LATEST' from dual union all
  select 'USED-LIVE', 'VIEW', 'SYSTEM', 'VW_CVING_NSE_DELIVERY_LATEST' from dual union all
  select 'USED-LIVE', 'SEQUENCE', 'SYSTEM', 'ASURA_BTS_SEQ' from dual union all
  select 'PRESENT-LIVE', 'TABLE', 'SYSTEM', 'ASURA_TRADE_BOOK' from dual union all
  select 'PRESENT-LIVE', 'VIEW', 'SYSTEM', 'VW_SYMBOL_CAP_BUCKET' from dual union all
  select 'PRESENT-LIVE', 'PROCEDURE', 'SYSTEM', 'PR_SYNC_DIM_SYMBOLS_FROM_DEV' from dual union all
  select 'PRESENT-LIVE', 'PROCEDURE', 'SYSTEM', 'PR_MERGE_FACT_OHLCV_FROM_DEV' from dual union all
  select 'PRESENT-LIVE', 'PROCEDURE', 'SYSTEM', 'PR_SYNC_FACT_OHLCV_FROM_DEV' from dual union all
  select 'PRESENT-LIVE', 'PROCEDURE', 'SYSTEM', 'PR_SYNC_DIM_SYMBOLS_CAP_SEG_FROM_INDICES' from dual union all
  select 'PRESENT-LIVE', 'PROCEDURE', 'SYSTEM', 'PR_SYNC_NSE_SYMBOL_SECTOR_MAP_FROM_STAGING' from dual union all
  select 'PRESENT-LIVE', 'PROCEDURE', 'SYSTEM', 'PR_SYNC_SECTOR_REFERENCE_DATA' from dual union all
  select 'PRESENT-LIVE', 'MATERIALIZED VIEW', 'SYSTEM', 'MV_NIFTY50_DAILY_SNAP' from dual union all
  select 'PRESENT-LIVE', 'MATERIALIZED VIEW', 'SYSTEM', 'MV_NIFTY_MIDCAP150_DAILY_SNAP' from dual union all
  select 'PRESENT-LIVE', 'MATERIALIZED VIEW', 'SYSTEM', 'MV_NIFTY_SMALLCAP250_DAILY_SNAP' from dual union all
  select 'PRESENT-LIVE', 'MATERIALIZED VIEW', 'SYSTEM', 'MV_NSE50_DAILY_6M' from dual union all
  select 'PRESENT-LIVE', 'MATERIALIZED VIEW', 'SYSTEM', 'MV_NSE_NIFTY500_EMA_BASE' from dual union all
  select 'PRESENT-LIVE', 'MATERIALIZED VIEW', 'SYSTEM', 'MV_NSE_SECTOR_UI_SNAPSHOT' from dual union all
  select 'CODE-ONLY-STALE', 'TABLE', 'SYSTEM', 'FYERS_HOLDINGS_IMPORTS' from dual union all
  select 'CODE-ONLY-STALE', 'TABLE', 'SYSTEM', 'FYERS_HOLDINGS_CURRENT' from dual union all
  select 'CODE-ONLY-STALE', 'TABLE', 'SYSTEM', 'FYERS_HOLDINGS_AUDIT' from dual union all
  select 'CODE-ONLY-STALE', 'TABLE', 'SYSTEM', 'BHRAMHAPUTRA_SCAN' from dual union all
  select 'CODE-ONLY-STALE', 'TABLE', 'SYSTEM', 'BHRAMHASTRA_BACKTEST' from dual union all
  select 'CODE-ONLY-STALE', 'VIEW', 'SYSTEM', 'V_ASURA_SCAN_WEEKLY_LATEST' from dual union all
  select 'CODE-ONLY-STALE', 'MATERIALIZED VIEW', 'SYSTEM', 'MV_ASURA_SCAN_DAILY' from dual union all
  select 'CODE-ONLY-STALE', 'MATERIALIZED VIEW', 'SYSTEM', 'MV_ASURA_SCAN_WEEKLY' from dual union all
  select 'CODE-ONLY-STALE', 'MATERIALIZED VIEW', 'SYSTEM', 'MV_NSE_SECTOR_BREADTH' from dual
), segment_rollup as (
  select owner, segment_name, round(sum(bytes) / 1024 / 1024, 2) as segment_mb
  from dba_segments
  where owner = 'SYSTEM'
  group by owner, segment_name
)
select c.object_state,
       c.object_type,
       c.owner,
       c.object_name,
       o.status,
       coalesce(t.tablespace_name, i.tablespace_name, l.tablespace_name, m.tablespace_name) as primary_tablespace,
       t.partitioned,
       t.num_rows,
       to_char(t.last_analyzed, 'YYYY-MM-DD HH24:MI:SS') as last_analyzed,
       sr.segment_mb,
       to_char(o.created, 'YYYY-MM-DD HH24:MI:SS') as created,
       to_char(o.last_ddl_time, 'YYYY-MM-DD HH24:MI:SS') as last_ddl_time
from app_catalog c
left join dba_objects o
  on o.owner = c.owner
 and o.object_name = c.object_name
 and o.object_type = c.object_type
left join dba_tables t
  on t.owner = c.owner
 and t.table_name = c.object_name
left join dba_indexes i
  on i.owner = c.owner
 and i.index_name = c.object_name
left join dba_lobs l
  on l.owner = c.owner
 and l.segment_name = c.object_name
left join dba_mviews m
  on m.owner = c.owner
 and m.mview_name = c.object_name
left join segment_rollup sr
  on sr.owner = c.owner
 and sr.segment_name = c.object_name
order by c.object_state, c.object_type, c.object_name;

prompt ------------------------------------------------------------
prompt Dependent indexes for discovered app tables
prompt ------------------------------------------------------------

column index_name format a40
column status format a12
column tablespace_name format a15
select index_name,
       table_name,
       index_type,
       uniqueness,
       status,
       tablespace_name
from dba_indexes
where owner = 'SYSTEM'
  and table_name in (
    'NSE_NIFTY500_DAILY_RAW_DATA_DEV','FACT_OHLCV','DIM_SYMBOLS','NSE_NIFTY50_LARGECAP','NSE_NIFTY150_MIDCAP',
    'NSE_NIFTY250_SMALLCAP','ASURA_BULLISH_TREND_STRATEGY_TESTING','ASURA_SCAN_DAILY_FACT','GAINERS_TOP25',
    'LOOSERS_TOP25','VOLUME_MOVERS_TOP25','BHRAMHASTRA_BACKTESTING_DATA','CVING_STRATEGY_PARAMS',
    'CVING_STRATEGY_AGENT_RUNS','CVING_STRATEGY_AGENT_BACKTESTS','CVING_NSE_MARKET_CAP_HIST','CVING_NSE_MCAP_PIPELINE_RUNS',
    'CVING_NSE_FFMC_HIST','CVING_NSE_FFMC_PIPELINE_RUNS','CVING_NSE_DELIVERY_HIST','REGISTRATIONS','LOGIN_ACTIVITY',
    'AUTH_SESSIONS','AUTH_QUICK_MPIN','PRICE_ACTION_SR_LEVELS_MANUALLY','ASURA_TRADE_BOOK'
  )
order by table_name, index_name;

prompt ------------------------------------------------------------
prompt Constraints for discovered app tables
prompt ------------------------------------------------------------

column constraint_name format a40
column constraint_type format a4
select constraint_name,
       table_name,
       constraint_type,
       status,
       validated,
       deferrable
from dba_constraints
where owner = 'SYSTEM'
  and table_name in (
    'NSE_NIFTY500_DAILY_RAW_DATA_DEV','FACT_OHLCV','DIM_SYMBOLS','NSE_NIFTY50_LARGECAP','NSE_NIFTY150_MIDCAP',
    'NSE_NIFTY250_SMALLCAP','ASURA_BULLISH_TREND_STRATEGY_TESTING','ASURA_SCAN_DAILY_FACT','GAINERS_TOP25',
    'LOOSERS_TOP25','VOLUME_MOVERS_TOP25','BHRAMHASTRA_BACKTESTING_DATA','CVING_STRATEGY_PARAMS',
    'CVING_STRATEGY_AGENT_RUNS','CVING_STRATEGY_AGENT_BACKTESTS','CVING_NSE_MARKET_CAP_HIST','CVING_NSE_MCAP_PIPELINE_RUNS',
    'CVING_NSE_FFMC_HIST','CVING_NSE_FFMC_PIPELINE_RUNS','CVING_NSE_DELIVERY_HIST','REGISTRATIONS','LOGIN_ACTIVITY',
    'AUTH_SESSIONS','AUTH_QUICK_MPIN','PRICE_ACTION_SR_LEVELS_MANUALLY','ASURA_TRADE_BOOK'
  )
order by table_name, constraint_name;

prompt ------------------------------------------------------------
prompt Triggers on discovered app tables
prompt ------------------------------------------------------------

column trigger_name format a40
select trigger_name,
       table_name,
       status,
       triggering_event,
       trigger_type
from dba_triggers
where owner = 'SYSTEM'
  and table_name in (
    'NSE_NIFTY500_DAILY_RAW_DATA_DEV','FACT_OHLCV','DIM_SYMBOLS','NSE_NIFTY50_LARGECAP','NSE_NIFTY150_MIDCAP',
    'NSE_NIFTY250_SMALLCAP','ASURA_BULLISH_TREND_STRATEGY_TESTING','ASURA_SCAN_DAILY_FACT','GAINERS_TOP25',
    'LOOSERS_TOP25','VOLUME_MOVERS_TOP25','BHRAMHASTRA_BACKTESTING_DATA','CVING_STRATEGY_PARAMS',
    'CVING_STRATEGY_AGENT_RUNS','CVING_STRATEGY_AGENT_BACKTESTS','CVING_NSE_MARKET_CAP_HIST','CVING_NSE_MCAP_PIPELINE_RUNS',
    'CVING_NSE_FFMC_HIST','CVING_NSE_FFMC_PIPELINE_RUNS','CVING_NSE_DELIVERY_HIST','REGISTRATIONS','LOGIN_ACTIVITY',
    'AUTH_SESSIONS','AUTH_QUICK_MPIN','PRICE_ACTION_SR_LEVELS_MANUALLY','ASURA_TRADE_BOOK'
  )
order by table_name, trigger_name;

prompt ------------------------------------------------------------
prompt Synonyms touching discovered app objects
prompt ------------------------------------------------------------

select owner, synonym_name, table_owner, table_name, db_link
from dba_synonyms
where table_owner = 'SYSTEM'
  and table_name in (
    'NSE_NIFTY500_DAILY_RAW_DATA_DEV','FACT_OHLCV','DIM_SYMBOLS','NSE_NIFTY50_LARGECAP','NSE_NIFTY150_MIDCAP',
    'NSE_NIFTY250_SMALLCAP','ASURA_BULLISH_TREND_STRATEGY_TESTING','ASURA_SCAN_DAILY_FACT','GAINERS_TOP25',
    'LOOSERS_TOP25','VOLUME_MOVERS_TOP25','BHRAMHASTRA_BACKTESTING_DATA','CVING_STRATEGY_PARAMS',
    'CVING_STRATEGY_AGENT_RUNS','CVING_STRATEGY_AGENT_BACKTESTS','CVING_NSE_MARKET_CAP_HIST','CVING_NSE_MCAP_PIPELINE_RUNS',
    'CVING_NSE_FFMC_HIST','CVING_NSE_FFMC_PIPELINE_RUNS','CVING_NSE_DELIVERY_HIST','REGISTRATIONS','LOGIN_ACTIVITY',
    'AUTH_SESSIONS','AUTH_QUICK_MPIN','PRICE_ACTION_SR_LEVELS_MANUALLY','ASURA_TRADE_BOOK',
    'V_NSE500_EMA_DAILY','V_NSE_NIFTY50_LARGECAP_OHLCV','V_NSE_NIFTY150_MIDCAP_OHLCV','V_NSE_NIFTY250_SMALLCAP_OHLCV',
    'V_ASURA_SCAN_LATEST','VW_CVING_NSE_MARKET_CAP_LATEST','VW_CVING_NSE_FFMC_LATEST','VW_CVING_NSE_DELIVERY_LATEST',
    'MV_NIFTY50_DAILY_SNAP','MV_NIFTY_MIDCAP150_DAILY_SNAP','MV_NIFTY_SMALLCAP250_DAILY_SNAP','MV_NSE50_DAILY_6M',
    'MV_NSE_NIFTY500_EMA_BASE','MV_NSE_SECTOR_UI_SNAPSHOT'
  )
order by owner, synonym_name;

spool off