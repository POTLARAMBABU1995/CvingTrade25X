set echo on
set feedback on
set verify off
set serveroutput on size unlimited

column run_tag new_value run_tag
select to_char(systimestamp, 'YYYYMMDD_HH24MISS') as run_tag from dual;

spool E:\DB_BACKUP_SAFETY\LOGS\create_new_tablespaces_on_E_drive_&&run_tag..log

prompt ============================================================
prompt Creating dedicated CvingTrade25X tablespaces on E drive
prompt ============================================================
prompt Current observed app footprint is roughly 2.9 GB across table, index, and LOB segments.
prompt Initial capacity plan below creates 5.5 GB of dedicated space with autoextend headroom.
prompt Do not run this script until logical backup, DDL backup, and baseline validation are complete.

declare
  v_count number;
begin
  select count(*) into v_count from dba_tablespaces where tablespace_name = 'CVING_DATA';
  if v_count = 0 then
    execute immediate q'[
      create smallfile tablespace CVING_DATA
      datafile 'E:\DB_BACKUP_SAFETY\ORADATA\CVING_DATA01.dbf'
      size 2048M
      autoextend on next 256M maxsize 32767M
      extent management local
      segment space management auto
      logging
    ]';
  else
    dbms_output.put_line('CVING_DATA already exists; no action taken.');
  end if;
end;
/

declare
  v_count number;
begin
  select count(*) into v_count from dba_tablespaces where tablespace_name = 'CVING_INDEX';
  if v_count = 0 then
    execute immediate q'[
      create smallfile tablespace CVING_INDEX
      datafile 'E:\DB_BACKUP_SAFETY\ORADATA\CVING_INDEX01.dbf'
      size 1024M
      autoextend on next 256M maxsize 16384M
      extent management local
      segment space management auto
      logging
    ]';
  else
    dbms_output.put_line('CVING_INDEX already exists; no action taken.');
  end if;
end;
/

declare
  v_count number;
begin
  select count(*) into v_count from dba_tablespaces where tablespace_name = 'CVING_LOB';
  if v_count = 0 then
    execute immediate q'[
      create smallfile tablespace CVING_LOB
      datafile 'E:\DB_BACKUP_SAFETY\ORADATA\CVING_LOB01.dbf'
      size 2048M
      autoextend on next 256M maxsize 32767M
      extent management local
      segment space management auto
      logging
    ]';
  else
    dbms_output.put_line('CVING_LOB already exists; no action taken.');
  end if;
end;
/

declare
  v_count number;
begin
  select count(*) into v_count from dba_tablespaces where tablespace_name = 'CVING_MV';
  if v_count = 0 then
    execute immediate q'[
      create smallfile tablespace CVING_MV
      datafile 'E:\DB_BACKUP_SAFETY\ORADATA\CVING_MV01.dbf'
      size 512M
      autoextend on next 128M maxsize 8192M
      extent management local
      segment space management auto
      logging
    ]';
  else
    dbms_output.put_line('CVING_MV already exists; no action taken.');
  end if;
end;
/

column file_name format a100
select tablespace_name,
       file_name,
       round(bytes / 1024 / 1024, 2) as file_mb,
       autoextensible,
       case when lower(file_name) like 'e:\db_backup_safety\oradata%' then 'ON_TARGET' else 'OFF_TARGET' end as target_path_state
from dba_data_files
where tablespace_name in ('CVING_DATA', 'CVING_INDEX', 'CVING_LOB', 'CVING_MV')
order by tablespace_name, file_name;

spool off