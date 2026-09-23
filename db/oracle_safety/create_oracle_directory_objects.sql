set echo on
set feedback on
set serveroutput on size unlimited
set verify off
set define on

column run_tag new_value run_tag
select to_char(systimestamp, 'YYYYMMDD_HH24MISS') as run_tag from dual;

spool E:\DB_BACKUP_SAFETY\LOGS\create_oracle_directory_objects_&&run_tag..log

prompt Creating or replacing Oracle DIRECTORY objects for CvingTrade25X safety exports.
prompt Run this as SYSTEM or another account with CREATE ANY DIRECTORY privilege.

create or replace directory CVING_DPUMP_DUMP_DIR as 'E:\DB_BACKUP_SAFETY\SQLDEV_EXPORT\DUMP';
create or replace directory CVING_DPUMP_LOG_DIR as 'E:\DB_BACKUP_SAFETY\SQLDEV_EXPORT\LOG';
create or replace directory CVING_DDL_DIR as 'E:\DB_BACKUP_SAFETY\SQLDEV_EXPORT\DDL';
create or replace directory CVING_REPORT_DIR as 'E:\DB_BACKUP_SAFETY\REPORTS';

declare
  v_session_user varchar2(128);
begin
  v_session_user := upper(sys_context('USERENV', 'SESSION_USER'));
  if v_session_user <> 'SYSTEM' then
    execute immediate 'grant read, write on directory CVING_DPUMP_DUMP_DIR to SYSTEM';
    execute immediate 'grant read, write on directory CVING_DPUMP_LOG_DIR to SYSTEM';
    execute immediate 'grant read, write on directory CVING_DDL_DIR to SYSTEM';
    execute immediate 'grant read, write on directory CVING_REPORT_DIR to SYSTEM';
  else
    dbms_output.put_line('Running as SYSTEM; explicit self-grants skipped.');
  end if;
end;
/

prompt Directory objects after create/replace:
column directory_name format a30
column directory_path format a100
select directory_name, directory_path
from dba_directories
where directory_name in (
  'CVING_DPUMP_DUMP_DIR',
  'CVING_DPUMP_LOG_DIR',
  'CVING_DDL_DIR',
  'CVING_REPORT_DIR'
)
order by directory_name;

spool off