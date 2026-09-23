set echo on
set feedback on
set verify off
set serveroutput on size unlimited

column run_tag new_value run_tag
select to_char(systimestamp, 'YYYYMMDD_HH24MISS') as run_tag from dual;

spool E:\DB_BACKUP_SAFETY\LOGS\invalid_objects_recompile_&&run_tag..log

prompt ============================================================
prompt Recompile eligible invalid application objects
prompt ============================================================
prompt Materialized views are reported but intentionally skipped for auto-recompile in this script.

prompt ------------------------------------------------------------
prompt Invalid objects before compile attempt
prompt ------------------------------------------------------------

select owner, object_type, object_name, status
from dba_objects
where owner = 'SYSTEM'
  and object_name in (
    'V_NSE500_EMA_DAILY','V_NSE_NIFTY50_LARGECAP_OHLCV','V_NSE_NIFTY150_MIDCAP_OHLCV','V_NSE_NIFTY250_SMALLCAP_OHLCV',
    'V_ASURA_SCAN_LATEST','VW_CVING_NSE_MARKET_CAP_LATEST','VW_CVING_NSE_FFMC_LATEST','VW_CVING_NSE_DELIVERY_LATEST',
    'PR_SYNC_DIM_SYMBOLS_FROM_DEV','PR_MERGE_FACT_OHLCV_FROM_DEV','PR_SYNC_FACT_OHLCV_FROM_DEV',
    'PR_SYNC_DIM_SYMBOLS_CAP_SEG_FROM_INDICES','PR_SYNC_NSE_SYMBOL_SECTOR_MAP_FROM_STAGING','PR_SYNC_SECTOR_REFERENCE_DATA',
    'MV_NIFTY50_DAILY_SNAP','MV_NIFTY_MIDCAP150_DAILY_SNAP','MV_NIFTY_SMALLCAP250_DAILY_SNAP',
    'MV_NSE50_DAILY_6M','MV_NSE_NIFTY500_EMA_BASE','MV_NSE_SECTOR_UI_SNAPSHOT'
  )
order by object_type, object_name;

begin
  for r in (
    select object_type, object_name
    from dba_objects
    where owner = 'SYSTEM'
      and status = 'INVALID'
      and object_name in (
        'V_NSE500_EMA_DAILY','V_NSE_NIFTY50_LARGECAP_OHLCV','V_NSE_NIFTY150_MIDCAP_OHLCV','V_NSE_NIFTY250_SMALLCAP_OHLCV',
        'V_ASURA_SCAN_LATEST','VW_CVING_NSE_MARKET_CAP_LATEST','VW_CVING_NSE_FFMC_LATEST','VW_CVING_NSE_DELIVERY_LATEST',
        'PR_SYNC_DIM_SYMBOLS_FROM_DEV','PR_MERGE_FACT_OHLCV_FROM_DEV','PR_SYNC_FACT_OHLCV_FROM_DEV',
        'PR_SYNC_DIM_SYMBOLS_CAP_SEG_FROM_INDICES','PR_SYNC_NSE_SYMBOL_SECTOR_MAP_FROM_STAGING','PR_SYNC_SECTOR_REFERENCE_DATA'
      )
  ) loop
    if r.object_type = 'VIEW' then
      execute immediate 'alter view SYSTEM.' || r.object_name || ' compile';
      dbms_output.put_line('alter view SYSTEM.' || r.object_name || ' compile;');
    elsif r.object_type = 'PROCEDURE' then
      execute immediate 'alter procedure SYSTEM.' || r.object_name || ' compile';
      dbms_output.put_line('alter procedure SYSTEM.' || r.object_name || ' compile;');
    elsif r.object_type = 'FUNCTION' then
      execute immediate 'alter function SYSTEM.' || r.object_name || ' compile';
      dbms_output.put_line('alter function SYSTEM.' || r.object_name || ' compile;');
    elsif r.object_type = 'PACKAGE' then
      execute immediate 'alter package SYSTEM.' || r.object_name || ' compile';
      dbms_output.put_line('alter package SYSTEM.' || r.object_name || ' compile;');
    elsif r.object_type = 'PACKAGE BODY' then
      execute immediate 'alter package SYSTEM.' || r.object_name || ' compile body';
      dbms_output.put_line('alter package SYSTEM.' || r.object_name || ' compile body;');
    elsif r.object_type = 'TRIGGER' then
      execute immediate 'alter trigger SYSTEM.' || r.object_name || ' compile';
      dbms_output.put_line('alter trigger SYSTEM.' || r.object_name || ' compile;');
    end if;
  end loop;
end;
/

prompt ------------------------------------------------------------
prompt Materialized views intentionally skipped for manual review
prompt ------------------------------------------------------------

select owner, object_name, status
from dba_objects
where owner = 'SYSTEM'
  and object_type = 'MATERIALIZED VIEW'
  and object_name in (
    'MV_NIFTY50_DAILY_SNAP','MV_NIFTY_MIDCAP150_DAILY_SNAP','MV_NIFTY_SMALLCAP250_DAILY_SNAP',
    'MV_NSE50_DAILY_6M','MV_NSE_NIFTY500_EMA_BASE','MV_NSE_SECTOR_UI_SNAPSHOT'
  )
order by object_name;

prompt ------------------------------------------------------------
prompt Invalid objects after compile attempt
prompt ------------------------------------------------------------

select owner, object_type, object_name, status
from dba_objects
where owner = 'SYSTEM'
  and status = 'INVALID'
  and object_name in (
    'V_NSE500_EMA_DAILY','V_NSE_NIFTY50_LARGECAP_OHLCV','V_NSE_NIFTY150_MIDCAP_OHLCV','V_NSE_NIFTY250_SMALLCAP_OHLCV',
    'V_ASURA_SCAN_LATEST','VW_CVING_NSE_MARKET_CAP_LATEST','VW_CVING_NSE_FFMC_LATEST','VW_CVING_NSE_DELIVERY_LATEST',
    'PR_SYNC_DIM_SYMBOLS_FROM_DEV','PR_MERGE_FACT_OHLCV_FROM_DEV','PR_SYNC_FACT_OHLCV_FROM_DEV',
    'PR_SYNC_DIM_SYMBOLS_CAP_SEG_FROM_INDICES','PR_SYNC_NSE_SYMBOL_SECTOR_MAP_FROM_STAGING','PR_SYNC_SECTOR_REFERENCE_DATA',
    'MV_NIFTY50_DAILY_SNAP','MV_NIFTY_MIDCAP150_DAILY_SNAP','MV_NIFTY_SMALLCAP250_DAILY_SNAP',
    'MV_NSE50_DAILY_6M','MV_NSE_NIFTY500_EMA_BASE','MV_NSE_SECTOR_UI_SNAPSHOT'
  )
order by object_type, object_name;

spool off