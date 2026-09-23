set echo on
set feedback on
set verify off
set define on
set serveroutput on size unlimited

column run_tag new_value run_tag
select to_char(systimestamp, 'YYYYMMDD_HH24MISS') as run_tag from dual;

spool E:\DB_BACKUP_SAFETY\LOGS\move_app_objects_to_new_tablespaces_&&run_tag..log

define backup_confirmed = NO

prompt ============================================================
prompt Guarded move plan for CvingTrade25X application objects
prompt ============================================================
prompt Set: DEFINE backup_confirmed = BACKUP_CONFIRMED
prompt Only run after expdp_used_objects.par, ddl_extract_all_objects.sql, and validation_before_after.sql succeeded.

begin
  if upper('&&backup_confirmed') <> 'BACKUP_CONFIRMED' then
    raise_application_error(-20001, 'Backup gate not satisfied. Set DEFINE backup_confirmed = BACKUP_CONFIRMED before running object moves.');
  end if;
end;
/

prompt ------------------------------------------------------------
prompt Moving non-partitioned application tables to CVING_DATA
prompt ------------------------------------------------------------

declare
  v_sql varchar2(4000);
begin
  for r in (
    select table_name, target_ts
    from (
      select 'NSE_NIFTY500_DAILY_RAW_DATA_DEV' as table_name, 'CVING_DATA' as target_ts from dual union all
      select 'DIM_SYMBOLS', 'CVING_DATA' from dual union all
      select 'NSE_NIFTY50_LARGECAP', 'CVING_DATA' from dual union all
      select 'NSE_NIFTY150_MIDCAP', 'CVING_DATA' from dual union all
      select 'NSE_NIFTY250_SMALLCAP', 'CVING_DATA' from dual union all
      select 'ASURA_BULLISH_TREND_STRATEGY_TESTING', 'CVING_DATA' from dual union all
      select 'ASURA_SCAN_DAILY_FACT', 'CVING_DATA' from dual union all
      select 'GAINERS_TOP25', 'CVING_DATA' from dual union all
      select 'LOOSERS_TOP25', 'CVING_DATA' from dual union all
      select 'VOLUME_MOVERS_TOP25', 'CVING_DATA' from dual union all
      select 'BHRAMHASTRA_BACKTESTING_DATA', 'CVING_DATA' from dual union all
      select 'CVING_STRATEGY_PARAMS', 'CVING_DATA' from dual union all
      select 'CVING_STRATEGY_AGENT_RUNS', 'CVING_DATA' from dual union all
      select 'CVING_STRATEGY_AGENT_BACKTESTS', 'CVING_DATA' from dual union all
      select 'CVING_NSE_MARKET_CAP_HIST', 'CVING_DATA' from dual union all
      select 'CVING_NSE_MCAP_PIPELINE_RUNS', 'CVING_DATA' from dual union all
      select 'CVING_NSE_FFMC_HIST', 'CVING_DATA' from dual union all
      select 'CVING_NSE_FFMC_PIPELINE_RUNS', 'CVING_DATA' from dual union all
      select 'CVING_NSE_DELIVERY_HIST', 'CVING_DATA' from dual union all
      select 'REGISTRATIONS', 'CVING_DATA' from dual union all
      select 'LOGIN_ACTIVITY', 'CVING_DATA' from dual union all
      select 'AUTH_SESSIONS', 'CVING_DATA' from dual union all
      select 'AUTH_QUICK_MPIN', 'CVING_DATA' from dual union all
      select 'PRICE_ACTION_SR_LEVELS_MANUALLY', 'CVING_DATA' from dual
    )
  ) loop
    for t in (
      select partitioned, tablespace_name
      from dba_tables
      where owner = 'SYSTEM'
        and table_name = r.table_name
        and nvl(tablespace_name, '?') <> r.target_ts
    ) loop
      if t.partitioned = 'NO' then
        v_sql := 'alter table SYSTEM.' || r.table_name || ' move tablespace ' || r.target_ts || ' online';
        dbms_output.put_line(v_sql || ';');
        execute immediate v_sql;
      else
        dbms_output.put_line('Skipping partitioned table in non-partitioned section: ' || r.table_name);
      end if;
    end loop;
  end loop;
end;
/

prompt ------------------------------------------------------------
prompt Moving FACT_OHLCV partition defaults and partitions to CVING_DATA
prompt ------------------------------------------------------------

declare
  v_sql varchar2(4000);
begin
  execute immediate 'alter table SYSTEM.FACT_OHLCV modify default attributes tablespace CVING_DATA';
  dbms_output.put_line('alter table SYSTEM.FACT_OHLCV modify default attributes tablespace CVING_DATA;');

  for r in (
    select partition_name
    from dba_tab_partitions p
    where p.table_owner = 'SYSTEM'
      and p.table_name = 'FACT_OHLCV'
      and nvl(p.tablespace_name, '?') <> 'CVING_DATA'
      and not exists (
        select 1
        from dba_tab_subpartitions sp
        where sp.table_owner = p.table_owner
          and sp.table_name = p.table_name
          and sp.partition_name = p.partition_name
      )
    order by p.partition_position
  ) loop
    v_sql := 'alter table SYSTEM.FACT_OHLCV move partition ' || dbms_assert.enquote_name(r.partition_name, false) || ' tablespace CVING_DATA update indexes';
    dbms_output.put_line(v_sql || ';');
    execute immediate v_sql;
  end loop;

  for r in (
    select subpartition_name
    from dba_tab_subpartitions
    where table_owner = 'SYSTEM'
      and table_name = 'FACT_OHLCV'
      and nvl(tablespace_name, '?') <> 'CVING_DATA'
    order by partition_position, subpartition_position
  ) loop
    v_sql := 'alter table SYSTEM.FACT_OHLCV move subpartition ' || dbms_assert.enquote_name(r.subpartition_name, false) || ' tablespace CVING_DATA update indexes';
    dbms_output.put_line(v_sql || ';');
    execute immediate v_sql;
  end loop;
end;
/

prompt ------------------------------------------------------------
prompt Moving application LOB segments to CVING_LOB
prompt ------------------------------------------------------------

declare
  v_sql varchar2(4000);
begin
  for r in (
    select table_name, column_name
    from dba_lobs
    where owner = 'SYSTEM'
      and table_name in (
        'CVING_NSE_DELIVERY_HIST','CVING_NSE_FFMC_HIST','CVING_NSE_FFMC_PIPELINE_RUNS',
        'CVING_NSE_MARKET_CAP_HIST','CVING_NSE_MCAP_PIPELINE_RUNS','CVING_STRATEGY_AGENT_RUNS'
      )
      and nvl(tablespace_name, '?') <> 'CVING_LOB'
    order by table_name, column_name
  ) loop
    v_sql := 'alter table SYSTEM.' || r.table_name || ' move lob (' || r.column_name || ') store as (tablespace CVING_LOB)';
    dbms_output.put_line(v_sql || ';');
    execute immediate v_sql;
  end loop;
end;
/

prompt ------------------------------------------------------------
prompt Materialized view handling
prompt ------------------------------------------------------------
prompt Materialized views are deliberately not auto-moved in this script.
prompt Review DDL backups first, especially for invalid summary-layer materialized views.
prompt If explicit review approves relocation, move or recreate them in CVING_MV using a separate reviewed runbook.

prompt ------------------------------------------------------------
prompt Post-move placement snapshot
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

select table_name, column_name, tablespace_name
from dba_lobs
where owner = 'SYSTEM'
  and table_name in (
    'CVING_NSE_DELIVERY_HIST','CVING_NSE_FFMC_HIST','CVING_NSE_FFMC_PIPELINE_RUNS',
    'CVING_NSE_MARKET_CAP_HIST','CVING_NSE_MCAP_PIPELINE_RUNS','CVING_STRATEGY_AGENT_RUNS'
  )
order by table_name, column_name;

spool off