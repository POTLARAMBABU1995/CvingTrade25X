set echo on
set feedback on
set verify off
set serveroutput on size unlimited

column run_tag new_value run_tag
select to_char(systimestamp, 'YYYYMMDD_HH24MISS') as run_tag from dual;

spool E:\DB_BACKUP_SAFETY\LOGS\gather_stats_&&run_tag..log

prompt ============================================================
prompt Gathering optimizer statistics for discovered application tables
prompt ============================================================

declare
begin
  for r in (
    select table_name
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
    order by table_name
  ) loop
    dbms_output.put_line('Gathering stats for SYSTEM.' || r.table_name);
    dbms_stats.gather_table_stats(
      ownname          => 'SYSTEM',
      tabname          => r.table_name,
      estimate_percent => dbms_stats.auto_sample_size,
      method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
      degree           => dbms_stats.auto_degree,
      cascade          => true,
      granularity      => 'AUTO',
      no_invalidate    => false
    );
  end loop;
end;
/

select table_name, num_rows, to_char(last_analyzed, 'YYYY-MM-DD HH24:MI:SS') as last_analyzed
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

spool off