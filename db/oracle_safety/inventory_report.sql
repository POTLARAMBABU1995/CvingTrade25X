set echo off
set feedback on
set verify off
set pagesize 200
set linesize 240
set trimspool on
set serveroutput on size unlimited

column run_tag new_value run_tag
select to_char(systimestamp, 'YYYYMMDD_HH24MISS') as run_tag from dual;

spool E:\DB_BACKUP_SAFETY\REPORTS\inventory_report_&&run_tag..log

prompt ============================================================
prompt CvingTrade25X inventory report
prompt ============================================================

column name format a20
column open_mode format a20
column db_unique_name format a20
select name, db_unique_name, open_mode, cdb from v$database;

column host_name format a40
column instance_name format a20
select instance_name, host_name, version, startup_time from v$instance;

column con_name format a20
select sys_context('USERENV', 'CON_NAME') as con_name from dual;

prompt ------------------------------------------------------------
prompt PDB status
prompt ------------------------------------------------------------

column name format a30
column restricted format a12
select con_id, name, open_mode, restricted
from v$pdbs
order by con_id;

prompt ------------------------------------------------------------
prompt Live app object counts by discovery state and object type
prompt ------------------------------------------------------------

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
  select 'PRESENT-LIVE', 'MATERIALIZED VIEW', 'SYSTEM', 'MV_NSE_SECTOR_UI_SNAPSHOT' from dual
)
select object_state, object_type, count(*) as configured_count,
       sum(case when o.object_name is not null then 1 else 0 end) as live_count,
       sum(case when o.status = 'INVALID' then 1 else 0 end) as invalid_count
from app_catalog c
left join dba_objects o
  on o.owner = c.owner
 and o.object_name = c.object_name
 and o.object_type = c.object_type
group by object_state, object_type
order by object_state, object_type;

prompt ------------------------------------------------------------
prompt Used-live tables with row counts and tablespaces
prompt ------------------------------------------------------------

column table_name format a35
column tablespace_name format a15
column partitioned format a12
column num_rows format 9999999990
column last_analyzed format a20
select t.table_name,
       t.tablespace_name,
       t.partitioned,
       t.num_rows,
       to_char(t.last_analyzed, 'YYYY-MM-DD HH24:MI:SS') as last_analyzed
from dba_tables t
where t.owner = 'SYSTEM'
  and t.table_name in (
    'NSE_NIFTY500_DAILY_RAW_DATA_DEV','FACT_OHLCV','DIM_SYMBOLS','NSE_NIFTY50_LARGECAP',
    'NSE_NIFTY150_MIDCAP','NSE_NIFTY250_SMALLCAP','ASURA_BULLISH_TREND_STRATEGY_TESTING',
    'ASURA_SCAN_DAILY_FACT','GAINERS_TOP25','LOOSERS_TOP25','VOLUME_MOVERS_TOP25',
    'BHRAMHASTRA_BACKTESTING_DATA','CVING_STRATEGY_PARAMS','CVING_STRATEGY_AGENT_RUNS',
    'CVING_STRATEGY_AGENT_BACKTESTS','CVING_NSE_MARKET_CAP_HIST','CVING_NSE_MCAP_PIPELINE_RUNS',
    'CVING_NSE_FFMC_HIST','CVING_NSE_FFMC_PIPELINE_RUNS','CVING_NSE_DELIVERY_HIST',
    'REGISTRATIONS','LOGIN_ACTIVITY','AUTH_SESSIONS','AUTH_QUICK_MPIN','PRICE_ACTION_SR_LEVELS_MANUALLY'
  )
order by t.num_rows desc nulls last, t.table_name;

prompt ------------------------------------------------------------
prompt Invalid app objects
prompt ------------------------------------------------------------

column object_name format a40
column status format a10
column last_ddl_time format a20
select owner, object_type, object_name, status,
       to_char(last_ddl_time, 'YYYY-MM-DD HH24:MI:SS') as last_ddl_time
from dba_objects
where owner = 'SYSTEM'
  and object_name in (
    'MV_NIFTY50_DAILY_SNAP','MV_NIFTY_MIDCAP150_DAILY_SNAP','MV_NIFTY_SMALLCAP250_DAILY_SNAP',
    'MV_NSE50_DAILY_6M','MV_NSE_NIFTY500_EMA_BASE','MV_NSE_SECTOR_UI_SNAPSHOT'
  )
order by object_type, object_name;

prompt ------------------------------------------------------------
prompt Duplicate-volume candidates across used-live tables
prompt ------------------------------------------------------------

with used_tables as (
  select table_name, num_rows
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
)
select a.table_name as table_a,
       b.table_name as table_b,
       a.num_rows as rows_a,
       b.num_rows as rows_b,
       abs(nvl(a.num_rows, 0) - nvl(b.num_rows, 0)) as row_delta
from used_tables a
join used_tables b
  on a.table_name < b.table_name
where a.num_rows is not null
  and b.num_rows is not null
  and abs(a.num_rows - b.num_rows) <= greatest(10, round(greatest(a.num_rows, b.num_rows) * 0.01))
order by row_delta, table_a, table_b;

prompt ------------------------------------------------------------
prompt Tablespace datafile placement for relevant tablespaces
prompt ------------------------------------------------------------

column file_name format a100
select tablespace_name,
       file_name,
       round(bytes / 1024 / 1024, 2) as file_mb,
       autoextensible,
       case
         when lower(file_name) like 'e:\db_backup_safety\oradata%' then 'ON_TARGET'
         else 'OFF_TARGET'
       end as target_path_state
from dba_data_files
where tablespace_name in ('SYSTEM', 'USERS', 'CVING_APP', 'CVING_DATA', 'CVING_INDEX', 'CVING_LOB', 'CVING_MV')
order by tablespace_name, file_name;

spool off