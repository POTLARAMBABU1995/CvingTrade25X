set echo off
set feedback off
set verify off
set pagesize 0
set linesize 32767
set long 2000000
set longchunksize 2000000
set trimspool on
set serveroutput on size unlimited

column run_tag new_value run_tag
select to_char(systimestamp, 'YYYYMMDD_HH24MISS') as run_tag from dual;

spool E:\DB_BACKUP_SAFETY\LOGS\ddl_extract_all_objects_&&run_tag..log

begin
  dbms_metadata.set_transform_param(dbms_metadata.session_transform, 'PRETTY', true);
  dbms_metadata.set_transform_param(dbms_metadata.session_transform, 'SQLTERMINATOR', true);
  dbms_metadata.set_transform_param(dbms_metadata.session_transform, 'SEGMENT_ATTRIBUTES', true);
  dbms_metadata.set_transform_param(dbms_metadata.session_transform, 'STORAGE', true);
  dbms_metadata.set_transform_param(dbms_metadata.session_transform, 'TABLESPACE', true);
end;
/

spool E:\DB_BACKUP_SAFETY\SQLDEV_EXPORT\DDL\cvingtrade25x_all_objects_&&run_tag..sql

prompt -- =========================================================
prompt -- TABLE DDL
prompt -- =========================================================
select dbms_metadata.get_ddl('TABLE', table_name, owner)
from dba_tables
where owner = 'SYSTEM'
  and table_name in (
    'NSE_NIFTY500_DAILY_RAW_DATA_DEV','FACT_OHLCV','DIM_SYMBOLS','NSE_NIFTY50_LARGECAP','NSE_NIFTY150_MIDCAP',
    'NSE_NIFTY250_SMALLCAP','ASURA_BULLISH_TREND_STRATEGY_TESTING','ASURA_SCAN_DAILY_FACT','GAINERS_TOP25',
    'LOOSERS_TOP25','VOLUME_MOVERS_TOP25','BHRAMHASTRA_BACKTESTING_DATA','CVING_STRATEGY_PARAMS',
    'CVING_STRATEGY_AGENT_RUNS','CVING_STRATEGY_AGENT_BACKTESTS','CVING_NSE_MARKET_CAP_HIST','CVING_NSE_MCAP_PIPELINE_RUNS',
    'CVING_NSE_FFMC_HIST','CVING_NSE_FFMC_PIPELINE_RUNS','CVING_NSE_DELIVERY_HIST','REGISTRATIONS','LOGIN_ACTIVITY',
    'AUTH_SESSIONS','AUTH_QUICK_MPIN','PRICE_ACTION_SR_LEVELS_MANUALLY','ASURA_TRADE_BOOK'
  )
order by table_name;

prompt -- =========================================================
prompt -- INDEX DDL
prompt -- =========================================================
select dbms_metadata.get_ddl('INDEX', index_name, owner)
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
  and index_type not like 'LOB%'
order by table_name, index_name;

prompt -- =========================================================
prompt -- CONSTRAINT DDL
prompt -- =========================================================
select dbms_metadata.get_ddl('CONSTRAINT', constraint_name, owner)
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
  and constraint_type in ('P', 'U', 'C')
order by table_name, constraint_name;

prompt -- =========================================================
prompt -- REF CONSTRAINT DDL
prompt -- =========================================================
select dbms_metadata.get_ddl('REF_CONSTRAINT', constraint_name, owner)
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
  and constraint_type = 'R'
order by table_name, constraint_name;

prompt -- =========================================================
prompt -- VIEW DDL
prompt -- =========================================================
select dbms_metadata.get_ddl('VIEW', view_name, owner)
from dba_views
where owner = 'SYSTEM'
  and view_name in (
    'V_NSE500_EMA_DAILY','V_NSE_NIFTY50_LARGECAP_OHLCV','V_NSE_NIFTY150_MIDCAP_OHLCV',
    'V_NSE_NIFTY250_SMALLCAP_OHLCV','V_ASURA_SCAN_LATEST','VW_CVING_NSE_MARKET_CAP_LATEST',
    'VW_CVING_NSE_FFMC_LATEST','VW_CVING_NSE_DELIVERY_LATEST','VW_SYMBOL_CAP_BUCKET'
  )
order by view_name;

prompt -- =========================================================
prompt -- MATERIALIZED VIEW DDL
prompt -- =========================================================
select dbms_metadata.get_ddl('MATERIALIZED_VIEW', mview_name, owner)
from dba_mviews
where owner = 'SYSTEM'
  and mview_name in (
    'MV_NIFTY50_DAILY_SNAP','MV_NIFTY_MIDCAP150_DAILY_SNAP','MV_NIFTY_SMALLCAP250_DAILY_SNAP',
    'MV_NSE50_DAILY_6M','MV_NSE_NIFTY500_EMA_BASE','MV_NSE_SECTOR_UI_SNAPSHOT'
  )
order by mview_name;

prompt -- =========================================================
prompt -- SEQUENCE DDL
prompt -- =========================================================
select dbms_metadata.get_ddl('SEQUENCE', sequence_name, sequence_owner)
from dba_sequences
where sequence_owner = 'SYSTEM'
  and sequence_name in ('ASURA_BTS_SEQ')
order by sequence_name;

prompt -- =========================================================
prompt -- PROCEDURE DDL
prompt -- =========================================================
select dbms_metadata.get_ddl('PROCEDURE', object_name, owner)
from dba_objects
where owner = 'SYSTEM'
  and object_type = 'PROCEDURE'
  and object_name in (
    'PR_SYNC_DIM_SYMBOLS_FROM_DEV','PR_MERGE_FACT_OHLCV_FROM_DEV','PR_SYNC_FACT_OHLCV_FROM_DEV',
    'PR_SYNC_DIM_SYMBOLS_CAP_SEG_FROM_INDICES','PR_SYNC_NSE_SYMBOL_SECTOR_MAP_FROM_STAGING','PR_SYNC_SECTOR_REFERENCE_DATA'
  )
order by object_name;

prompt -- =========================================================
prompt -- TRIGGER DDL
prompt -- =========================================================
select dbms_metadata.get_ddl('TRIGGER', trigger_name, owner)
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
order by trigger_name;

prompt -- =========================================================
prompt -- SYNONYM DDL
prompt -- =========================================================
select dbms_metadata.get_ddl('SYNONYM', synonym_name, owner)
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
    'VW_SYMBOL_CAP_BUCKET','MV_NIFTY50_DAILY_SNAP','MV_NIFTY_MIDCAP150_DAILY_SNAP','MV_NIFTY_SMALLCAP250_DAILY_SNAP',
    'MV_NSE50_DAILY_6M','MV_NSE_NIFTY500_EMA_BASE','MV_NSE_SECTOR_UI_SNAPSHOT'
  )
order by owner, synonym_name;

prompt -- =========================================================
prompt -- OBJECT GRANTS
prompt -- =========================================================
select 'grant ' || privilege || ' on ' || owner || '.' || table_name || ' to ' || grantee ||
       case when grantable = 'YES' then ' with grant option;' else ';' end
from dba_tab_privs
where owner = 'SYSTEM'
  and table_name in (
    'NSE_NIFTY500_DAILY_RAW_DATA_DEV','FACT_OHLCV','DIM_SYMBOLS','NSE_NIFTY50_LARGECAP','NSE_NIFTY150_MIDCAP',
    'NSE_NIFTY250_SMALLCAP','ASURA_BULLISH_TREND_STRATEGY_TESTING','ASURA_SCAN_DAILY_FACT','GAINERS_TOP25',
    'LOOSERS_TOP25','VOLUME_MOVERS_TOP25','BHRAMHASTRA_BACKTESTING_DATA','CVING_STRATEGY_PARAMS',
    'CVING_STRATEGY_AGENT_RUNS','CVING_STRATEGY_AGENT_BACKTESTS','CVING_NSE_MARKET_CAP_HIST','CVING_NSE_MCAP_PIPELINE_RUNS',
    'CVING_NSE_FFMC_HIST','CVING_NSE_FFMC_PIPELINE_RUNS','CVING_NSE_DELIVERY_HIST','REGISTRATIONS','LOGIN_ACTIVITY',
    'AUTH_SESSIONS','AUTH_QUICK_MPIN','PRICE_ACTION_SR_LEVELS_MANUALLY','ASURA_TRADE_BOOK'
  )
order by owner, table_name, grantee, privilege;

spool off
spool off