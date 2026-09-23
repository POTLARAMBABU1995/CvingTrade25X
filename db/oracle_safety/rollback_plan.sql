set echo on
set feedback on
set verify off
set define on
set serveroutput on size unlimited

column run_tag new_value run_tag
select to_char(systimestamp, 'YYYYMMDD_HH24MISS') as run_tag from dual;

spool E:\DB_BACKUP_SAFETY\LOGS\rollback_plan_&&run_tag..log

define rollback_confirmed = NO

prompt ============================================================
prompt Reverse move plan for CvingTrade25X application objects
prompt ============================================================
prompt Set: DEFINE rollback_confirmed = ROLLBACK_APPROVED
prompt Use only after validation proves a rollback is required.

begin
  if upper('&&rollback_confirmed') <> 'ROLLBACK_APPROVED' then
    raise_application_error(-20002, 'Rollback gate not satisfied. Set DEFINE rollback_confirmed = ROLLBACK_APPROVED before running rollback moves.');
  end if;
end;
/

prompt ------------------------------------------------------------
prompt Reversing non-partitioned table moves
prompt ------------------------------------------------------------

declare
  v_sql varchar2(4000);
begin
  for r in (
    select t.table_name, m.original_ts
    from dba_tables t
    join (
      select 'NSE_NIFTY500_DAILY_RAW_DATA_DEV' as table_name, 'SYSTEM' as original_ts from dual union all
      select 'DIM_SYMBOLS', 'SYSTEM' from dual union all
      select 'NSE_NIFTY50_LARGECAP', 'SYSTEM' from dual union all
      select 'NSE_NIFTY150_MIDCAP', 'SYSTEM' from dual union all
      select 'NSE_NIFTY250_SMALLCAP', 'SYSTEM' from dual union all
      select 'ASURA_BULLISH_TREND_STRATEGY_TESTING', 'SYSTEM' from dual union all
      select 'ASURA_SCAN_DAILY_FACT', 'SYSTEM' from dual union all
      select 'GAINERS_TOP25', 'SYSTEM' from dual union all
      select 'LOOSERS_TOP25', 'SYSTEM' from dual union all
      select 'VOLUME_MOVERS_TOP25', 'SYSTEM' from dual union all
      select 'BHRAMHASTRA_BACKTESTING_DATA', 'SYSTEM' from dual union all
      select 'CVING_STRATEGY_PARAMS', 'CVING_APP' from dual union all
      select 'CVING_STRATEGY_AGENT_RUNS', 'CVING_APP' from dual union all
      select 'CVING_STRATEGY_AGENT_BACKTESTS', 'CVING_APP' from dual union all
      select 'CVING_NSE_MARKET_CAP_HIST', 'CVING_APP' from dual union all
      select 'CVING_NSE_MCAP_PIPELINE_RUNS', 'CVING_APP' from dual union all
      select 'CVING_NSE_FFMC_HIST', 'USERS' from dual union all
      select 'CVING_NSE_FFMC_PIPELINE_RUNS', 'USERS' from dual union all
      select 'CVING_NSE_DELIVERY_HIST', 'USERS' from dual union all
      select 'REGISTRATIONS', 'SYSTEM' from dual union all
      select 'LOGIN_ACTIVITY', 'SYSTEM' from dual union all
      select 'AUTH_SESSIONS', 'SYSTEM' from dual union all
      select 'AUTH_QUICK_MPIN', 'SYSTEM' from dual union all
      select 'PRICE_ACTION_SR_LEVELS_MANUALLY', 'CVING_APP' from dual
    ) m
      on m.table_name = t.table_name
    where t.owner = 'SYSTEM'
      and t.partitioned = 'NO'
      and nvl(t.tablespace_name, '?') <> m.original_ts
  ) loop
    v_sql := 'alter table SYSTEM.' || r.table_name || ' move tablespace ' || r.original_ts || ' online';
    dbms_output.put_line(v_sql || ';');
    execute immediate v_sql;
  end loop;
end;
/

prompt ------------------------------------------------------------
prompt Reversing FACT_OHLCV partition and subpartition moves to SYSTEM
prompt ------------------------------------------------------------

declare
  v_sql varchar2(4000);
begin
  execute immediate 'alter table SYSTEM.FACT_OHLCV modify default attributes tablespace SYSTEM';
  dbms_output.put_line('alter table SYSTEM.FACT_OHLCV modify default attributes tablespace SYSTEM;');

  for r in (
    select partition_name
    from dba_tab_partitions p
    where p.table_owner = 'SYSTEM'
      and p.table_name = 'FACT_OHLCV'
      and nvl(p.tablespace_name, '?') <> 'SYSTEM'
      and not exists (
        select 1
        from dba_tab_subpartitions sp
        where sp.table_owner = p.table_owner
          and sp.table_name = p.table_name
          and sp.partition_name = p.partition_name
      )
    order by p.partition_position
  ) loop
    v_sql := 'alter table SYSTEM.FACT_OHLCV move partition ' || dbms_assert.enquote_name(r.partition_name, false) || ' tablespace SYSTEM update indexes';
    dbms_output.put_line(v_sql || ';');
    execute immediate v_sql;
  end loop;

  for r in (
    select subpartition_name
    from dba_tab_subpartitions
    where table_owner = 'SYSTEM'
      and table_name = 'FACT_OHLCV'
      and nvl(tablespace_name, '?') <> 'SYSTEM'
    order by partition_position, subpartition_position
  ) loop
    v_sql := 'alter table SYSTEM.FACT_OHLCV move subpartition ' || dbms_assert.enquote_name(r.subpartition_name, false) || ' tablespace SYSTEM update indexes';
    dbms_output.put_line(v_sql || ';');
    execute immediate v_sql;
  end loop;
end;
/

prompt ------------------------------------------------------------
prompt Reversing LOB placement
prompt ------------------------------------------------------------

declare
  v_sql varchar2(4000);
begin
  for r in (
    select table_name,
           column_name,
           case
             when table_name in ('CVING_NSE_MARKET_CAP_HIST', 'CVING_NSE_MCAP_PIPELINE_RUNS', 'CVING_STRATEGY_AGENT_RUNS') then 'CVING_APP'
             when table_name in ('CVING_NSE_FFMC_HIST', 'CVING_NSE_FFMC_PIPELINE_RUNS') then 'USERS'
             when table_name = 'CVING_NSE_DELIVERY_HIST' then 'SYSTEM'
           end as original_ts
    from dba_lobs
    where owner = 'SYSTEM'
      and table_name in (
        'CVING_NSE_DELIVERY_HIST','CVING_NSE_FFMC_HIST','CVING_NSE_FFMC_PIPELINE_RUNS',
        'CVING_NSE_MARKET_CAP_HIST','CVING_NSE_MCAP_PIPELINE_RUNS','CVING_STRATEGY_AGENT_RUNS'
      )
  ) loop
    if r.original_ts is not null then
      v_sql := 'alter table SYSTEM.' || r.table_name || ' move lob (' || r.column_name || ') store as (tablespace ' || r.original_ts || ')';
      dbms_output.put_line(v_sql || ';');
      execute immediate v_sql;
    end if;
  end loop;
end;
/

prompt ------------------------------------------------------------
prompt Reversing non-partitioned index moves
prompt ------------------------------------------------------------

declare
  v_sql varchar2(4000);
begin
  for r in (
    select i.index_name,
           case
             when i.table_name in ('CVING_STRATEGY_PARAMS','CVING_STRATEGY_AGENT_RUNS','CVING_STRATEGY_AGENT_BACKTESTS','CVING_NSE_MARKET_CAP_HIST','CVING_NSE_MCAP_PIPELINE_RUNS','PRICE_ACTION_SR_LEVELS_MANUALLY') then 'CVING_APP'
             when i.table_name in ('CVING_NSE_FFMC_HIST','CVING_NSE_FFMC_PIPELINE_RUNS','CVING_NSE_DELIVERY_HIST') then 'USERS'
             else 'SYSTEM'
           end as original_ts
    from dba_indexes i
    where i.owner = 'SYSTEM'
      and i.partitioned = 'NO'
      and i.index_type not like 'LOB%'
      and i.table_name in (
        'NSE_NIFTY500_DAILY_RAW_DATA_DEV','DIM_SYMBOLS','NSE_NIFTY50_LARGECAP','NSE_NIFTY150_MIDCAP','NSE_NIFTY250_SMALLCAP',
        'ASURA_BULLISH_TREND_STRATEGY_TESTING','ASURA_SCAN_DAILY_FACT','GAINERS_TOP25','LOOSERS_TOP25','VOLUME_MOVERS_TOP25',
        'BHRAMHASTRA_BACKTESTING_DATA','CVING_STRATEGY_PARAMS','CVING_STRATEGY_AGENT_RUNS','CVING_STRATEGY_AGENT_BACKTESTS',
        'CVING_NSE_MARKET_CAP_HIST','CVING_NSE_MCAP_PIPELINE_RUNS','CVING_NSE_FFMC_HIST','CVING_NSE_FFMC_PIPELINE_RUNS',
        'CVING_NSE_DELIVERY_HIST','REGISTRATIONS','LOGIN_ACTIVITY','AUTH_SESSIONS','AUTH_QUICK_MPIN','PRICE_ACTION_SR_LEVELS_MANUALLY'
      )
      and nvl(i.tablespace_name, '?') <> case
        when i.table_name in ('CVING_STRATEGY_PARAMS','CVING_STRATEGY_AGENT_RUNS','CVING_STRATEGY_AGENT_BACKTESTS','CVING_NSE_MARKET_CAP_HIST','CVING_NSE_MCAP_PIPELINE_RUNS','PRICE_ACTION_SR_LEVELS_MANUALLY') then 'CVING_APP'
        when i.table_name in ('CVING_NSE_FFMC_HIST','CVING_NSE_FFMC_PIPELINE_RUNS','CVING_NSE_DELIVERY_HIST') then 'USERS'
        else 'SYSTEM'
      end
  ) loop
    v_sql := 'alter index SYSTEM.' || r.index_name || ' rebuild tablespace ' || r.original_ts || ' online';
    dbms_output.put_line(v_sql || ';');
    execute immediate v_sql;
  end loop;
end;
/

prompt ------------------------------------------------------------
prompt Reversing FACT_OHLCV index partition moves to SYSTEM
prompt ------------------------------------------------------------

declare
  v_sql varchar2(4000);
begin
  for r in (
    select index_name
    from dba_indexes
    where owner = 'SYSTEM'
      and table_name = 'FACT_OHLCV'
      and partitioned = 'YES'
  ) loop
    v_sql := 'alter index SYSTEM.' || r.index_name || ' modify default attributes tablespace SYSTEM';
    dbms_output.put_line(v_sql || ';');
    execute immediate v_sql;
  end loop;

  for r in (
    select index_name, partition_name
    from dba_ind_partitions
    where index_owner = 'SYSTEM'
      and index_name in (select index_name from dba_indexes where owner = 'SYSTEM' and table_name = 'FACT_OHLCV')
      and nvl(tablespace_name, '?') <> 'SYSTEM'
  ) loop
    v_sql := 'alter index SYSTEM.' || r.index_name || ' rebuild partition ' || dbms_assert.enquote_name(r.partition_name, false) || ' tablespace SYSTEM online';
    dbms_output.put_line(v_sql || ';');
    execute immediate v_sql;
  end loop;

  for r in (
    select index_name, subpartition_name
    from dba_ind_subpartitions
    where index_owner = 'SYSTEM'
      and index_name in (select index_name from dba_indexes where owner = 'SYSTEM' and table_name = 'FACT_OHLCV')
      and nvl(tablespace_name, '?') <> 'SYSTEM'
  ) loop
    v_sql := 'alter index SYSTEM.' || r.index_name || ' rebuild subpartition ' || dbms_assert.enquote_name(r.subpartition_name, false) || ' tablespace SYSTEM online';
    dbms_output.put_line(v_sql || ';');
    execute immediate v_sql;
  end loop;
end;
/

spool off