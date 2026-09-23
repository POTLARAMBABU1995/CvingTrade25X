# Execution Order

## Safe to Run First

1. Run `db/oracle_safety/create_backup_directories.cmd`.
2. Review `db/oracle_safety/page_to_db_object_mapping_report.md`.
3. Review `db/oracle_safety/final_summary.md`.
4. Run `db/oracle_safety/create_oracle_directory_objects.sql`.
5. Run `db/oracle_safety/inventory_report.sql`.
6. Run `db/oracle_safety/app_object_inventory.sql`.
7. Run `db/oracle_safety/tablespace_usage_report.sql`.
8. Run `db/oracle_safety/validation_before_after.sql` and save the pre-move baseline.
9. Run `db/oracle_safety/ddl_extract_all_objects.sql`.
10. Run `expdp` with `db/oracle_safety/expdp_used_objects.par`.
11. Optionally run RMAN with `db/oracle_safety/rman_backup_commands.rman`.

## Review Gate Before Any Storage Change

1. Confirm Data Pump dump files exist under `E:\DB_BACKUP_SAFETY\SQLDEV_EXPORT\DUMP`.
2. Confirm Data Pump log shows success under `E:\DB_BACKUP_SAFETY\SQLDEV_EXPORT\LOG`.
3. Confirm DDL extract files exist under `E:\DB_BACKUP_SAFETY\SQLDEV_EXPORT\DDL`.
4. Confirm pre-move validation row counts are complete.
5. Review the invalid materialized views baseline and accept that they are pre-existing defects, not caused by the backup process.
6. Review the generated move and rollback scripts side by side.

## Only After Backup Validation

1. Run `db/oracle_safety/create_new_tablespaces_on_E_drive.sql`.
2. Re-run `db/oracle_safety/tablespace_usage_report.sql` to confirm new datafiles.
3. Set `backup_confirmed` to `BACKUP_CONFIRMED` inside the SQL*Plus session.
4. Run `db/oracle_safety/move_app_objects_to_new_tablespaces.sql`.
5. Run `db/oracle_safety/rebuild_indexes.sql`.
6. Run `db/oracle_safety/gather_stats.sql`.
7. Run `db/oracle_safety/invalid_objects_recompile.sql`.
8. Run `db/oracle_safety/validation_before_after.sql` again and compare against the baseline.

## Do Not Auto-Execute

- `db/oracle_safety/expdp_full_app_schema.par`
- Any `SCHEMAS=SYSTEM` Data Pump export
- Any drop statement against application objects
- Any manual change to `SYS`, `SYSTEM`, `SYSAUX`, `UNDO`, or `TEMP` internals beyond read-only inspection
- Any broad `ALTER TABLE SYSTEM.FACT_OHLCV MOVE TABLESPACE ...` statement that ignores partitions or subpartitions

## PowerShell Commands

```powershell
Set-Location "C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X\db\oracle_safety"

cmd /c .\create_backup_directories.cmd

sqlplus system/YourPassword@localhost:1521/orcl @create_oracle_directory_objects.sql
sqlplus system/YourPassword@localhost:1521/orcl @inventory_report.sql
sqlplus system/YourPassword@localhost:1521/orcl @app_object_inventory.sql
sqlplus system/YourPassword@localhost:1521/orcl @tablespace_usage_report.sql
sqlplus system/YourPassword@localhost:1521/orcl @validation_before_after.sql
sqlplus system/YourPassword@localhost:1521/orcl @ddl_extract_all_objects.sql

expdp system/YourPassword@localhost:1521/orcl parfile=expdp_used_objects.par

rman target system/YourPassword@localhost:1521/orcl cmdfile=rman_backup_commands.rman log=E:\DB_BACKUP_SAFETY\LOGS\rman_manual_run.log
```

## Data-Only or Metadata-Only Overrides

```powershell
expdp system/YourPassword@localhost:1521/orcl parfile=expdp_used_objects.par CONTENT=METADATA_ONLY
expdp system/YourPassword@localhost:1521/orcl parfile=expdp_used_objects.par CONTENT=DATA_ONLY
```