set echo off
set feedback on
set verify off
set pagesize 200
set linesize 260
set trimspool on
set serveroutput on size unlimited

column run_tag new_value run_tag
select to_char(systimestamp, 'YYYYMMDD_HH24MISS') as run_tag from dual;

spool E:\DB_BACKUP_SAFETY\REPORTS\tablespace_usage_report_&&run_tag..log

prompt ============================================================
prompt CvingTrade25X tablespace and segment usage report
prompt ============================================================

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

prompt ------------------------------------------------------------
prompt Base table tablespace placement
prompt ------------------------------------------------------------

select table_name,
       tablespace_name,
       partitioned,
       num_rows
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
order by tablespace_name, table_name;

prompt ------------------------------------------------------------
prompt Segment footprint by tablespace and segment type
prompt ------------------------------------------------------------

with app_tables as (
  select 'NSE_NIFTY500_DAILY_RAW_DATA_DEV' as table_name from dual union all
  select 'FACT_OHLCV' from dual union all
  select 'DIM_SYMBOLS' from dual union all
  select 'NSE_NIFTY50_LARGECAP' from dual union all
  select 'NSE_NIFTY150_MIDCAP' from dual union all
  select 'NSE_NIFTY250_SMALLCAP' from dual union all
  select 'ASURA_BULLISH_TREND_STRATEGY_TESTING' from dual union all
  select 'ASURA_SCAN_DAILY_FACT' from dual union all
  select 'GAINERS_TOP25' from dual union all
  select 'LOOSERS_TOP25' from dual union all
  select 'VOLUME_MOVERS_TOP25' from dual union all
  select 'BHRAMHASTRA_BACKTESTING_DATA' from dual union all
  select 'CVING_STRATEGY_PARAMS' from dual union all
  select 'CVING_STRATEGY_AGENT_RUNS' from dual union all
  select 'CVING_STRATEGY_AGENT_BACKTESTS' from dual union all
  select 'CVING_NSE_MARKET_CAP_HIST' from dual union all
  select 'CVING_NSE_MCAP_PIPELINE_RUNS' from dual union all
  select 'CVING_NSE_FFMC_HIST' from dual union all
  select 'CVING_NSE_FFMC_PIPELINE_RUNS' from dual union all
  select 'CVING_NSE_DELIVERY_HIST' from dual union all
  select 'REGISTRATIONS' from dual union all
  select 'LOGIN_ACTIVITY' from dual union all
  select 'AUTH_SESSIONS' from dual union all
  select 'AUTH_QUICK_MPIN' from dual union all
  select 'PRICE_ACTION_SR_LEVELS_MANUALLY' from dual
), app_indexes as (
  select index_name
  from dba_indexes
  where owner = 'SYSTEM'
    and table_name in (select table_name from app_tables)
), app_lobs as (
  select segment_name
  from dba_lobs
  where owner = 'SYSTEM'
    and table_name in (select table_name from app_tables)
)
select tablespace_name,
       segment_type,
       round(sum(bytes) / 1024 / 1024, 2) as segment_mb
from dba_segments
where owner = 'SYSTEM'
  and (
    segment_name in (select table_name from app_tables)
    or segment_name in (select index_name from app_indexes)
    or segment_name in (select segment_name from app_lobs)
  )
group by tablespace_name, segment_type
order by tablespace_name, segment_type;

prompt ------------------------------------------------------------
prompt LOB segment placement
prompt ------------------------------------------------------------

select table_name,
       column_name,
       segment_name,
       index_name,
       tablespace_name,
       securefile
from dba_lobs
where owner = 'SYSTEM'
  and table_name in (
    'CVING_NSE_DELIVERY_HIST','CVING_NSE_FFMC_HIST','CVING_NSE_FFMC_PIPELINE_RUNS',
    'CVING_NSE_MARKET_CAP_HIST','CVING_NSE_MCAP_PIPELINE_RUNS','CVING_STRATEGY_AGENT_RUNS'
  )
order by table_name, column_name;

prompt ------------------------------------------------------------
prompt FACT_OHLCV partition placement
prompt ------------------------------------------------------------

select table_name,
       partition_name,
       tablespace_name,
       round(num_rows) as num_rows,
       compression
from dba_tab_partitions
where table_owner = 'SYSTEM'
  and table_name = 'FACT_OHLCV'
order by partition_position;

prompt ------------------------------------------------------------
prompt FACT_OHLCV subpartition placement
prompt ------------------------------------------------------------

select table_name,
       subpartition_name,
       partition_name,
       tablespace_name,
       round(num_rows) as num_rows,
       compression
from dba_tab_subpartitions
where table_owner = 'SYSTEM'
  and table_name = 'FACT_OHLCV'
order by partition_position, subpartition_position;

prompt ------------------------------------------------------------
prompt FACT_OHLCV index and index partition placement
prompt ------------------------------------------------------------

select index_name,
       tablespace_name,
       partitioned,
       status,
       index_type
from dba_indexes
where owner = 'SYSTEM'
  and table_name = 'FACT_OHLCV'
order by index_name;

select index_name,
       partition_name,
       tablespace_name,
       status
from dba_ind_partitions
where index_owner = 'SYSTEM'
  and index_name in (select index_name from dba_indexes where owner = 'SYSTEM' and table_name = 'FACT_OHLCV')
order by index_name, partition_position;

select index_name,
       subpartition_name,
       partition_name,
       tablespace_name,
       status
from dba_ind_subpartitions
where index_owner = 'SYSTEM'
  and index_name in (select index_name from dba_indexes where owner = 'SYSTEM' and table_name = 'FACT_OHLCV')
order by index_name, partition_name, subpartition_name;

spool off