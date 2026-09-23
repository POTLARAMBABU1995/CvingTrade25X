@echo off
setlocal enabledelayedexpansion

for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "RUN_TAG=%%I"

set "BASE_DIR=%~dp0"
set "SQLPLUS_CONNECT=%ORACLE_CONNECT_STRING%"

if "%ORACLE_CONNECT_STRING%"=="" (
  echo [ERROR] Set ORACLE_CONNECT_STRING. Example: system/YourPassword@localhost:1521/orcl
  exit /b 1
)

echo [INFO] Run tag: %RUN_TAG%
echo [INFO] Using workspace bundle: %BASE_DIR%

call "%BASE_DIR%create_backup_directories.cmd" || exit /b 1

echo [INFO] Creating Oracle DIRECTORY objects...
sqlplus -L "%SQLPLUS_CONNECT%" @"%BASE_DIR%create_oracle_directory_objects.sql"
if errorlevel 1 exit /b 1

echo [INFO] Generating discovery reports before export...
sqlplus -L "%SQLPLUS_CONNECT%" @"%BASE_DIR%inventory_report.sql"
if errorlevel 1 exit /b 1
sqlplus -L "%SQLPLUS_CONNECT%" @"%BASE_DIR%app_object_inventory.sql"
if errorlevel 1 exit /b 1
sqlplus -L "%SQLPLUS_CONNECT%" @"%BASE_DIR%tablespace_usage_report.sql"
if errorlevel 1 exit /b 1
sqlplus -L "%SQLPLUS_CONNECT%" @"%BASE_DIR%validation_before_after.sql"
if errorlevel 1 exit /b 1

echo [INFO] Extracting DDL backup...
sqlplus -L "%SQLPLUS_CONNECT%" @"%BASE_DIR%ddl_extract_all_objects.sql"
if errorlevel 1 exit /b 1

echo [INFO] Starting approved object-list Data Pump export...
expdp "%SQLPLUS_CONNECT%" parfile="%BASE_DIR%expdp_used_objects.par"
if errorlevel 1 exit /b 1

echo [INFO] Export workflow completed. Review logs under E:\DB_BACKUP_SAFETY\SQLDEV_EXPORT\LOG and E:\DB_BACKUP_SAFETY\LOGS.
echo [INFO] Do not run create_new_tablespaces_on_E_drive.sql or move_app_objects_to_new_tablespaces.sql until the export and validation outputs are reviewed.
endlocal