set echo on
set feedback on
set verify off
set serveroutput on size unlimited

column run_tag new_value run_tag
select to_char(systimestamp, 'YYYYMMDD_HH24MISS') as run_tag from dual;

spool E:\DB_BACKUP_SAFETY\LOGS\rebuild_indexes_&&run_tag..log

prompt ============================================================
prompt Rebuilding discovered application indexes into CVING_INDEX
prompt ============================================================

declare
  v_sql varchar2(4000);
begin
  for r in (
    select index_name
    from dba_indexes
    where owner = 'SYSTEM'
      and table_name in (
        'NSE_NIFTY500_DAILY_RAW_DATA_DEV','DIM_SYMBOLS','NSE_NIFTY50_LARGECAP','NSE_NIFTY150_MIDCAP','NSE_NIFTY250_SMALLCAP',
        'ASURA_BULLISH_TREND_STRATEGY_TESTING','ASURA_SCAN_DAILY_FACT','GAINERS_TOP25','LOOSERS_TOP25','VOLUME_MOVERS_TOP25',
        'BHRAMHASTRA_BACKTESTING_DATA','CVING_STRATEGY_PARAMS','CVING_STRATEGY_AGENT_RUNS','CVING_STRATEGY_AGENT_BACKTESTS',
        'CVING_NSE_MARKET_CAP_HIST','CVING_NSE_MCAP_PIPELINE_RUNS','CVING_NSE_FFMC_HIST','CVING_NSE_FFMC_PIPELINE_RUNS',
        'CVING_NSE_DELIVERY_HIST','REGISTRATIONS','LOGIN_ACTIVITY','AUTH_SESSIONS','AUTH_QUICK_MPIN','PRICE_ACTION_SR_LEVELS_MANUALLY'
      )
      and partitioned = 'NO'
      and index_type not like 'LOB%'
      and nvl(tablespace_name, '?') <> 'CVING_INDEX'
    order by index_name
  ) loop
    v_sql := 'alter index SYSTEM.' || r.index_name || ' rebuild tablespace CVING_INDEX online';
    dbms_output.put_line(v_sql || ';');
    execute immediate v_sql;
  end loop;
end;
/

declare
  v_sql varchar2(4000);
begin
  for r in (
    select index_name
    from dba_indexes
    where owner = 'SYSTEM'
      and table_name = 'FACT_OHLCV'
      and partitioned = 'YES'
    order by index_name
  ) loop
    v_sql := 'alter index SYSTEM.' || r.index_name || ' modify default attributes tablespace CVING_INDEX';
    dbms_output.put_line(v_sql || ';');
    execute immediate v_sql;
  end loop;

  for r in (
    select index_name, partition_name
    from dba_ind_partitions
    where index_owner = 'SYSTEM'
      and index_name in (select index_name from dba_indexes where owner = 'SYSTEM' and table_name = 'FACT_OHLCV')
      and nvl(tablespace_name, '?') <> 'CVING_INDEX'
    order by index_name, partition_position
  ) loop
    v_sql := 'alter index SYSTEM.' || r.index_name || ' rebuild partition ' || dbms_assert.enquote_name(r.partition_name, false) || ' tablespace CVING_INDEX online';
    dbms_output.put_line(v_sql || ';');
    execute immediate v_sql;
  end loop;

  for r in (
    select index_name, subpartition_name
    from dba_ind_subpartitions
    where index_owner = 'SYSTEM'
      and index_name in (select index_name from dba_indexes where owner = 'SYSTEM' and table_name = 'FACT_OHLCV')
      and nvl(tablespace_name, '?') <> 'CVING_INDEX'
    order by index_name, partition_name, subpartition_name
  ) loop
    v_sql := 'alter index SYSTEM.' || r.index_name || ' rebuild subpartition ' || dbms_assert.enquote_name(r.subpartition_name, false) || ' tablespace CVING_INDEX online';
    dbms_output.put_line(v_sql || ';');
    execute immediate v_sql;
  end loop;
end;
/

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

spool off