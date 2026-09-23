set echo off
set feedback on
set verify off
set pagesize 200
set linesize 260
set trimspool on
set serveroutput on size unlimited

column run_tag new_value run_tag
select to_char(systimestamp, 'YYYYMMDD_HH24MISS') as run_tag from dual;

spool E:\DB_BACKUP_SAFETY\REPORTS\validation_before_after_&&run_tag..log

prompt ============================================================
prompt CvingTrade25X validation before and after export or move
prompt ============================================================

prompt ------------------------------------------------------------
prompt Instance and container confirmation
prompt ------------------------------------------------------------

select name, db_unique_name, open_mode, cdb from v$database;
select instance_name, host_name, version from v$instance;
select sys_context('USERENV', 'CON_NAME') as con_name from dual;

prompt ------------------------------------------------------------
prompt Exact row counts for used-live tables
prompt ------------------------------------------------------------

declare
  v_count number;
begin
  dbms_output.put_line('TABLE_NAME|ROW_COUNT');
  for r in (
    select 'SYSTEM' as owner_name, 'NSE_NIFTY500_DAILY_RAW_DATA_DEV' as table_name from dual union all
    select 'SYSTEM', 'FACT_OHLCV' from dual union all
    select 'SYSTEM', 'DIM_SYMBOLS' from dual union all
    select 'SYSTEM', 'NSE_NIFTY50_LARGECAP' from dual union all
    select 'SYSTEM', 'NSE_NIFTY150_MIDCAP' from dual union all
    select 'SYSTEM', 'NSE_NIFTY250_SMALLCAP' from dual union all
    select 'SYSTEM', 'ASURA_BULLISH_TREND_STRATEGY_TESTING' from dual union all
    select 'SYSTEM', 'ASURA_SCAN_DAILY_FACT' from dual union all
    select 'SYSTEM', 'GAINERS_TOP25' from dual union all
    select 'SYSTEM', 'LOOSERS_TOP25' from dual union all
    select 'SYSTEM', 'VOLUME_MOVERS_TOP25' from dual union all
    select 'SYSTEM', 'BHRAMHASTRA_BACKTESTING_DATA' from dual union all
    select 'SYSTEM', 'CVING_STRATEGY_PARAMS' from dual union all
    select 'SYSTEM', 'CVING_STRATEGY_AGENT_RUNS' from dual union all
    select 'SYSTEM', 'CVING_STRATEGY_AGENT_BACKTESTS' from dual union all
    select 'SYSTEM', 'CVING_NSE_MARKET_CAP_HIST' from dual union all
    select 'SYSTEM', 'CVING_NSE_MCAP_PIPELINE_RUNS' from dual union all
    select 'SYSTEM', 'CVING_NSE_FFMC_HIST' from dual union all
    select 'SYSTEM', 'CVING_NSE_FFMC_PIPELINE_RUNS' from dual union all
    select 'SYSTEM', 'CVING_NSE_DELIVERY_HIST' from dual union all
    select 'SYSTEM', 'REGISTRATIONS' from dual union all
    select 'SYSTEM', 'LOGIN_ACTIVITY' from dual union all
    select 'SYSTEM', 'AUTH_SESSIONS' from dual union all
    select 'SYSTEM', 'AUTH_QUICK_MPIN' from dual union all
    select 'SYSTEM', 'PRICE_ACTION_SR_LEVELS_MANUALLY' from dual
  ) loop
    execute immediate 'select count(*) from ' || r.owner_name || '.' || r.table_name into v_count;
    dbms_output.put_line(r.owner_name || '.' || r.table_name || '|' || v_count);
  end loop;
end;
/

prompt ------------------------------------------------------------
prompt Object counts by type for discovered live objects
prompt ------------------------------------------------------------

with app_catalog as (
  select 'TABLE' as object_type, 'SYSTEM' as owner, 'NSE_NIFTY500_DAILY_RAW_DATA_DEV' as object_name from dual union all
  select 'TABLE', 'SYSTEM', 'FACT_OHLCV' from dual union all
  select 'TABLE', 'SYSTEM', 'DIM_SYMBOLS' from dual union all
  select 'TABLE', 'SYSTEM', 'NSE_NIFTY50_LARGECAP' from dual union all
  select 'TABLE', 'SYSTEM', 'NSE_NIFTY150_MIDCAP' from dual union all
  select 'TABLE', 'SYSTEM', 'NSE_NIFTY250_SMALLCAP' from dual union all
  select 'TABLE', 'SYSTEM', 'ASURA_BULLISH_TREND_STRATEGY_TESTING' from dual union all
  select 'TABLE', 'SYSTEM', 'ASURA_SCAN_DAILY_FACT' from dual union all
  select 'TABLE', 'SYSTEM', 'GAINERS_TOP25' from dual union all
  select 'TABLE', 'SYSTEM', 'LOOSERS_TOP25' from dual union all
  select 'TABLE', 'SYSTEM', 'VOLUME_MOVERS_TOP25' from dual union all
  select 'TABLE', 'SYSTEM', 'BHRAMHASTRA_BACKTESTING_DATA' from dual union all
  select 'TABLE', 'SYSTEM', 'CVING_STRATEGY_PARAMS' from dual union all
  select 'TABLE', 'SYSTEM', 'CVING_STRATEGY_AGENT_RUNS' from dual union all
  select 'TABLE', 'SYSTEM', 'CVING_STRATEGY_AGENT_BACKTESTS' from dual union all
  select 'TABLE', 'SYSTEM', 'CVING_NSE_MARKET_CAP_HIST' from dual union all
  select 'TABLE', 'SYSTEM', 'CVING_NSE_MCAP_PIPELINE_RUNS' from dual union all
  select 'TABLE', 'SYSTEM', 'CVING_NSE_FFMC_HIST' from dual union all
  select 'TABLE', 'SYSTEM', 'CVING_NSE_FFMC_PIPELINE_RUNS' from dual union all
  select 'TABLE', 'SYSTEM', 'CVING_NSE_DELIVERY_HIST' from dual union all
  select 'TABLE', 'SYSTEM', 'REGISTRATIONS' from dual union all
  select 'TABLE', 'SYSTEM', 'LOGIN_ACTIVITY' from dual union all
  select 'TABLE', 'SYSTEM', 'AUTH_SESSIONS' from dual union all
  select 'TABLE', 'SYSTEM', 'AUTH_QUICK_MPIN' from dual union all
  select 'TABLE', 'SYSTEM', 'PRICE_ACTION_SR_LEVELS_MANUALLY' from dual union all
  select 'VIEW', 'SYSTEM', 'V_NSE500_EMA_DAILY' from dual union all
  select 'VIEW', 'SYSTEM', 'V_NSE_NIFTY50_LARGECAP_OHLCV' from dual union all
  select 'VIEW', 'SYSTEM', 'V_NSE_NIFTY150_MIDCAP_OHLCV' from dual union all
  select 'VIEW', 'SYSTEM', 'V_NSE_NIFTY250_SMALLCAP_OHLCV' from dual union all
  select 'VIEW', 'SYSTEM', 'V_ASURA_SCAN_LATEST' from dual union all
  select 'VIEW', 'SYSTEM', 'VW_CVING_NSE_MARKET_CAP_LATEST' from dual union all
  select 'VIEW', 'SYSTEM', 'VW_CVING_NSE_FFMC_LATEST' from dual union all
  select 'VIEW', 'SYSTEM', 'VW_CVING_NSE_DELIVERY_LATEST' from dual union all
  select 'SEQUENCE', 'SYSTEM', 'ASURA_BTS_SEQ' from dual union all
  select 'PROCEDURE', 'SYSTEM', 'PR_SYNC_DIM_SYMBOLS_FROM_DEV' from dual union all
  select 'PROCEDURE', 'SYSTEM', 'PR_MERGE_FACT_OHLCV_FROM_DEV' from dual union all
  select 'PROCEDURE', 'SYSTEM', 'PR_SYNC_FACT_OHLCV_FROM_DEV' from dual union all
  select 'PROCEDURE', 'SYSTEM', 'PR_SYNC_DIM_SYMBOLS_CAP_SEG_FROM_INDICES' from dual union all
  select 'PROCEDURE', 'SYSTEM', 'PR_SYNC_NSE_SYMBOL_SECTOR_MAP_FROM_STAGING' from dual union all
  select 'PROCEDURE', 'SYSTEM', 'PR_SYNC_SECTOR_REFERENCE_DATA' from dual union all
  select 'MATERIALIZED VIEW', 'SYSTEM', 'MV_NIFTY50_DAILY_SNAP' from dual union all
  select 'MATERIALIZED VIEW', 'SYSTEM', 'MV_NIFTY_MIDCAP150_DAILY_SNAP' from dual union all
  select 'MATERIALIZED VIEW', 'SYSTEM', 'MV_NIFTY_SMALLCAP250_DAILY_SNAP' from dual union all
  select 'MATERIALIZED VIEW', 'SYSTEM', 'MV_NSE50_DAILY_6M' from dual union all
  select 'MATERIALIZED VIEW', 'SYSTEM', 'MV_NSE_NIFTY500_EMA_BASE' from dual union all
  select 'MATERIALIZED VIEW', 'SYSTEM', 'MV_NSE_SECTOR_UI_SNAPSHOT' from dual
)
select object_type, count(*) as configured_count,
       sum(case when o.object_name is not null then 1 else 0 end) as live_count,
       sum(case when o.status = 'INVALID' then 1 else 0 end) as invalid_count
from app_catalog c
left join dba_objects o
  on o.owner = c.owner
 and o.object_name = c.object_name
 and o.object_type = c.object_type
group by object_type
order by object_type;

prompt ------------------------------------------------------------
prompt Invalid object check
prompt ------------------------------------------------------------

select owner, object_type, object_name, status
from dba_objects
where owner = 'SYSTEM'
  and object_name in (
    'MV_NIFTY50_DAILY_SNAP','MV_NIFTY_MIDCAP150_DAILY_SNAP','MV_NIFTY_SMALLCAP250_DAILY_SNAP',
    'MV_NSE50_DAILY_6M','MV_NSE_NIFTY500_EMA_BASE','MV_NSE_SECTOR_UI_SNAPSHOT'
  )
order by object_type, object_name;

prompt ------------------------------------------------------------
prompt Table, index, and LOB tablespace placement
prompt ------------------------------------------------------------

select table_name, tablespace_name, partitioned
from dba_tables
where owner = 'SYSTEM'
  and table_name in (
    'NSE_NIFTY500_DAILY_RAW_DATA_DEV','FACT_OHLCV','DIM_SYMBOLS','NSE_NIFTY50_LARGECAP','NSE_NIFTY150_MIDCAP',
    'NSE_NIFTY250_SMALLCAP','ASURA_BULLISH_TREND_STRATEGY_TESTING','ASURA_SCAN_DAILY_FACT','GAINERS_TOP25',
    'LOOSERS_TOP25','VOLUME_MOVERS_TOP25','BHRAMHASTRA_BACKTESTING_DATA','CVING_STRATEGY_PARAMS',
    'CVING_STRATEGY_AGENT_RUNS','CVING_STRATEGY_AGENT_BACKTESTS','CVING_NSE_MARKET_CAP_HIST','CVING_NSE_MCAP_PIPELINE_RUNS',
    'CVING_NSE_FFMC_HIST','CVING_NSE_FFMC_PIPELINE_RUNS','CVING_NSE_DELIVERY_HIST','REGISTRATIONS','LOGIN_ACTIVITY',
    'AUTH_SESSIONS','AUTH_QUICK_MPIN','PRICE_ACTION_SR_LEVELS_MANUALLY'
  )
order by table_name;

select index_name, table_name, tablespace_name, status, partitioned
from dba_indexes
where owner = 'SYSTEM'
  and table_name in (
    'NSE_NIFTY500_DAILY_RAW_DATA_DEV','FACT_OHLCV','DIM_SYMBOLS','NSE_NIFTY50_LARGECAP','NSE_NIFTY150_MIDCAP',
    'NSE_NIFTY250_SMALLCAP','ASURA_BULLISH_TREND_STRATEGY_TESTING','ASURA_SCAN_DAILY_FACT','GAINERS_TOP25',
    'LOOSERS_TOP25','VOLUME_MOVERS_TOP25','BHRAMHASTRA_BACKTESTING_DATA','CVING_STRATEGY_PARAMS',
    'CVING_STRATEGY_AGENT_RUNS','CVING_STRATEGY_AGENT_BACKTESTS','CVING_NSE_MARKET_CAP_HIST','CVING_NSE_MCAP_PIPELINE_RUNS',
    'CVING_NSE_FFMC_HIST','CVING_NSE_FFMC_PIPELINE_RUNS','CVING_NSE_DELIVERY_HIST','REGISTRATIONS','LOGIN_ACTIVITY',
    'AUTH_SESSIONS','AUTH_QUICK_MPIN','PRICE_ACTION_SR_LEVELS_MANUALLY'
  )
order by table_name, index_name;

select table_name, column_name, tablespace_name, segment_name, index_name
from dba_lobs
where owner = 'SYSTEM'
  and table_name in (
    'CVING_NSE_DELIVERY_HIST','CVING_NSE_FFMC_HIST','CVING_NSE_FFMC_PIPELINE_RUNS',
    'CVING_NSE_MARKET_CAP_HIST','CVING_NSE_MCAP_PIPELINE_RUNS','CVING_STRATEGY_AGENT_RUNS'
  )
order by table_name, column_name;

prompt ------------------------------------------------------------
prompt FACT_OHLCV partition and index partition validation
prompt ------------------------------------------------------------

select partition_name, tablespace_name, compression
from dba_tab_partitions
where table_owner = 'SYSTEM'
  and table_name = 'FACT_OHLCV'
order by partition_position;

select subpartition_name, partition_name, tablespace_name, compression
from dba_tab_subpartitions
where table_owner = 'SYSTEM'
  and table_name = 'FACT_OHLCV'
order by partition_position, subpartition_position;

select index_name, partition_name, tablespace_name, status
from dba_ind_partitions
where index_owner = 'SYSTEM'
  and index_name in (select index_name from dba_indexes where owner = 'SYSTEM' and table_name = 'FACT_OHLCV')
order by index_name, partition_position;

select index_name, subpartition_name, partition_name, tablespace_name, status
from dba_ind_subpartitions
where index_owner = 'SYSTEM'
  and index_name in (select index_name from dba_indexes where owner = 'SYSTEM' and table_name = 'FACT_OHLCV')
order by index_name, partition_name, subpartition_name;

prompt ------------------------------------------------------------
prompt Sample health checks
prompt ------------------------------------------------------------

select max(trading_date) as raw_max_trading_date from system.nse_nifty500_daily_raw_data_dev;
select max(trading_date) as fact_max_trading_date from system.fact_ohlcv;
select count(*) as market_cap_latest_rows from system.vw_cving_nse_market_cap_latest;
select count(*) as ffmc_latest_rows from system.vw_cving_nse_ffmc_latest;
select count(*) as delivery_latest_rows from system.vw_cving_nse_delivery_latest;
select count(*) as asura_latest_rows from system.v_asura_scan_latest;
select nvl(run_type, '(NULL)') as run_type, count(*) as run_count
from system.cving_nse_mcap_pipeline_runs
group by run_type
order by run_type;

prompt ------------------------------------------------------------
prompt Export-vs-discovery comparison for code-defined missing objects
prompt ------------------------------------------------------------

with code_defined as (
  select 'TABLE' as object_type, 'FYERS_HOLDINGS_IMPORTS' as object_name from dual union all
  select 'TABLE', 'FYERS_HOLDINGS_CURRENT' from dual union all
  select 'TABLE', 'FYERS_HOLDINGS_AUDIT' from dual union all
  select 'TABLE', 'BHRAMHAPUTRA_SCAN' from dual union all
  select 'TABLE', 'BHRAMHASTRA_BACKTEST' from dual union all
  select 'VIEW', 'V_ASURA_SCAN_WEEKLY_LATEST' from dual union all
  select 'MATERIALIZED VIEW', 'MV_ASURA_SCAN_DAILY' from dual union all
  select 'MATERIALIZED VIEW', 'MV_ASURA_SCAN_WEEKLY' from dual union all
  select 'MATERIALIZED VIEW', 'MV_NSE_SECTOR_BREADTH' from dual
)
select c.object_type,
       c.object_name,
       case when o.object_name is null then 'MISSING_LIVE' else 'PRESENT_LIVE' end as live_state,
       o.status
from code_defined c
left join dba_objects o
  on o.owner = 'SYSTEM'
 and o.object_name = c.object_name
 and o.object_type = c.object_type
order by c.object_type, c.object_name;

spool off