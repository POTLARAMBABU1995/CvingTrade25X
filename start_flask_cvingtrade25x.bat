@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ===============================================================
REM Launcher mode rules
REM   - Manual double-click/default  : visible CMD + logs + pause
REM   - Windows Startup through VBS  : pass --hidden, no CMD window
REM IMPORTANT: Do not place this BAT directly in the Startup folder.
REM            Place start_cvingtrade25x_hidden.vbs in Startup instead.
REM ===============================================================
set "LAUNCHER_MODE=interactive"
if /I "%~1"=="--hidden" set "LAUNCHER_MODE=hidden"
if /I "%~1"=="--startup" set "LAUNCHER_MODE=hidden"
if /I "%~1"=="--interactive" set "LAUNCHER_MODE=interactive"

set "STARTUP_LOCK_HELD=0"

REM ===============================================================
REM CvingTrade25X Flask Auto Start - Windows Startup Safe Launcher
REM ===============================================================
REM Fixes:
REM 1) Uses project root based on this BAT location, with fallback path.
REM 2) Enables autonomous background jobs by default.
REM 3) Avoids duplicate Flask process on port 5055.
REM 4) Starts Flask hidden and verifies /api/health before success.
REM 5) Prints startup decisions to the console and writes them to logs.

for %%I in ("%~dp0.") do set "ROOT=%%~fI"
if not exist "%ROOT%\backend\app.py" set "ROOT=C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X"

set "APP_DIR=%ROOT%\backend"
set "LOG_DIR=%ROOT%\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>nul

if not defined PORT set "PORT=5055"
if not defined HEALTH_PATH set "HEALTH_PATH=/api/health"
if not defined STARTUP_LOG set "STARTUP_LOG=%LOG_DIR%\cvingtrade25x_startup_events.log"
if not defined FLASK_LOG set "FLASK_LOG=%LOG_DIR%\cvingtrade25x_flask.log"
if not defined RUNNER_CMD set "RUNNER_CMD=%LOG_DIR%\run_cvingtrade25x_flask.cmd"
if not defined STARTUP_WAIT_SECONDS set "STARTUP_WAIT_SECONDS=45"
if not defined HEALTH_REQUEST_TIMEOUT_SECONDS set "HEALTH_REQUEST_TIMEOUT_SECONDS=3"
if not defined FLASK_LOG_TAIL_LINES set "FLASK_LOG_TAIL_LINES=200"
if not defined STARTUP_LOCK_DIR set "STARTUP_LOCK_DIR=%LOG_DIR%\cvingtrade25x_startup.lock"
if not defined STARTUP_LOCK_WAIT_SECONDS set "STARTUP_LOCK_WAIT_SECONDS=60"
if not defined STARTUP_LOCK_STALE_SECONDS set "STARTUP_LOCK_STALE_SECONDS=120"

call :acquire_startup_lock "%STARTUP_LOCK_WAIT_SECONDS%"
set "LOCK_RC=%ERRORLEVEL%"
if "%LOCK_RC%"=="2" (
  set "FINAL_RC=0"
  goto :finish
)
if not "%LOCK_RC%"=="0" (
  set "FINAL_RC=1"
  goto :finish
)

call :log "========== CvingTrade25X startup launcher begin =========="
call :log "LAUNCHER_MODE=%LAUNCHER_MODE%"
call :log "ROOT=%ROOT%"
call :log "APP_DIR=%APP_DIR%"
call :log "PORT=%PORT%"
call :log "HEALTH_PATH=%HEALTH_PATH%"
call :log "STARTUP_LOG=%STARTUP_LOG%"
call :log "FLASK_LOG=%FLASK_LOG%"
call :log "Acquired startup lock: %STARTUP_LOCK_DIR%"

if not exist "%APP_DIR%\app.py" (
  call :log "ERROR: app.py not found at %APP_DIR%\app.py"
  set "FINAL_RC=1"
  goto :finish
)

cd /d "%APP_DIR%" || (
  call :log "ERROR: Failed to change directory to %APP_DIR%"
  set "FINAL_RC=1"
  goto :finish
)

REM Runtime defaults. Existing machine/user environment variables can override these.
if not defined FLASK_DEBUG set "FLASK_DEBUG=0"
if not defined FLASK_ENV set "FLASK_ENV=production"

REM IMPORTANT: keep autonomous jobs ON by default for Windows startup.
REM Your backend holiday/weekend/after-5PM logic remains inside the app; this only allows the scheduler to run.
if not defined CVING_ENABLE_BACKGROUND_JOBS set "CVING_ENABLE_BACKGROUND_JOBS=1"
if not defined CVING_ENABLE_MANUAL_SR_IMAGE_AUTO_INGEST set "CVING_ENABLE_MANUAL_SR_IMAGE_AUTO_INGEST=1"
if not defined CVING_ENABLE_MARKETDATA_AUTO_MERGE set "CVING_ENABLE_MARKETDATA_AUTO_MERGE=1"
if not defined CVING_ENABLE_WARMUP set "CVING_ENABLE_WARMUP=0"

call :log "FLASK_DEBUG=%FLASK_DEBUG%"
call :log "FLASK_ENV=%FLASK_ENV%"
call :log "CVING_ENABLE_BACKGROUND_JOBS=%CVING_ENABLE_BACKGROUND_JOBS%"
call :log "CVING_ENABLE_MANUAL_SR_IMAGE_AUTO_INGEST=%CVING_ENABLE_MANUAL_SR_IMAGE_AUTO_INGEST%"
call :log "CVING_ENABLE_MARKETDATA_AUTO_MERGE=%CVING_ENABLE_MARKETDATA_AUTO_MERGE%"
call :log "CVING_ENABLE_WARMUP=%CVING_ENABLE_WARMUP%"

REM 1) Already healthy: do nothing.
call :is_http_healthy "%PORT%"
if not errorlevel 1 (
  call :log "OK: Existing Flask instance is healthy at http://127.0.0.1:%PORT%%HEALTH_PATH%. Startup skipped."
  set "FINAL_RC=0"
  goto :finish
)

REM 2) Port occupied but unhealthy: recover only stale python/pythonw listeners.
call :is_port_listening "%PORT%"
if not errorlevel 1 (
  call :log "WARN: Port %PORT% is listening but health check failed. Attempting stale Python listener recovery."
  call :stop_stale_python_listener "%PORT%"
  if errorlevel 1 (
    call :log "ERROR: Port %PORT% recovery failed. Non-Python process may be using the port or Stop-Process failed."
    set "FINAL_RC=1"
    goto :finish
  )
  timeout /t 2 /nobreak >nul 2>nul

  call :is_port_listening "%PORT%"
  if not errorlevel 1 (
    call :log "ERROR: Port %PORT% is still occupied after stale listener recovery."
    set "FINAL_RC=1"
    goto :finish
  )
)

REM 3) Choose Python interpreter. Project venv is preferred over global Python.
set "PYTHON_EXE="
call :try_python "%APP_DIR%\.venv\Scripts\python.exe"
call :try_python "%ROOT%\.venv\Scripts\python.exe"
call :try_python "%ROOT%\venv\Scripts\python.exe"
call :try_python "C:\Users\admin\AppData\Local\Programs\Python\Python310\python.exe"
call :try_python "python"

if not defined PYTHON_EXE (
  call :log "ERROR: No Python interpreter found with required modules: flask, flask_cors, oracledb, pandas."
  set "FINAL_RC=1"
  goto :finish
)

call :log "Selected Python: %PYTHON_EXE%"

REM 4) Create isolated runner so nested quoting from Windows Startup/VBS is stable.
(
  echo @echo off
  echo setlocal EnableExtensions
  echo cd /d "%APP_DIR%"
  echo set "PORT=%PORT%"
  echo set "FLASK_DEBUG=%FLASK_DEBUG%"
  echo set "FLASK_ENV=%FLASK_ENV%"
  echo set "CVING_ENABLE_BACKGROUND_JOBS=%CVING_ENABLE_BACKGROUND_JOBS%"
  echo set "CVING_ENABLE_MANUAL_SR_IMAGE_AUTO_INGEST=%CVING_ENABLE_MANUAL_SR_IMAGE_AUTO_INGEST%"
  echo set "CVING_ENABLE_MARKETDATA_AUTO_MERGE=%CVING_ENABLE_MARKETDATA_AUTO_MERGE%"
  echo set "CVING_ENABLE_WARMUP=%CVING_ENABLE_WARMUP%"
  echo "%PYTHON_EXE%" -u app.py ^>^> "%FLASK_LOG%" 2^>^&1
  echo exit /b %%ERRORLEVEL%%
) > "%RUNNER_CMD%"

if errorlevel 1 (
  call :log "ERROR: Failed to create runner command: %RUNNER_CMD%"
  set "FINAL_RC=1"
  goto :finish
)

call :log "Starting Flask hidden via runner: %RUNNER_CMD%"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath $env:ComSpec -ArgumentList '/d','/c','call ""%RUNNER_CMD%""' -WorkingDirectory '%APP_DIR%' -WindowStyle Hidden; exit 0" >> "%STARTUP_LOG%" 2>>&1

if errorlevel 1 (
  call :log "ERROR: Start-Process failed."
  set "FINAL_RC=1"
  goto :finish
)

REM 5) Do not trust process launch only. Verify HTTP health after launch.
call :log "Waiting up to %STARTUP_WAIT_SECONDS% seconds for http://127.0.0.1:%PORT%%HEALTH_PATH%."
call :wait_http_healthy "%PORT%" "%STARTUP_WAIT_SECONDS%"
if not errorlevel 1 (
  call :log "OK: Flask startup verified healthy at http://127.0.0.1:%PORT%%HEALTH_PATH%."
  call :log "Flask runtime output is being appended to %FLASK_LOG%"
  set "FINAL_RC=0"
  goto :finish
)

call :log "ERROR: Flask process was launched but health check did not become ready within %STARTUP_WAIT_SECONDS% seconds."
call :log "ERROR: Review runtime log: %FLASK_LOG%"
call :append_flask_tail
set "FINAL_RC=1"
goto :finish


:finish
set "RC=%FINAL_RC%"
call :release_startup_lock >nul 2>nul
if /I "%LAUNCHER_MODE%"=="interactive" (
  echo.
  if "%RC%"=="0" (
    echo Launcher finished successfully. Flask is running in the background.
    echo Health URL: http://127.0.0.1:%PORT%%HEALTH_PATH%
    echo Startup log: %STARTUP_LOG%
    echo Flask log: %FLASK_LOG%
  ) else (
    echo Launcher failed. Review:
    echo   %STARTUP_LOG%
    echo   %FLASK_LOG%
  )
  echo.
  echo Last startup log lines:
  powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "if (Test-Path -LiteralPath '%STARTUP_LOG%') { Get-Content -LiteralPath '%STARTUP_LOG%' -Tail 25 }" 2>nul
  echo.
  echo Manual run complete. Press any key to close this window.
  pause >nul
)
exit /b %RC%


:log
echo [%DATE% %TIME%] %~1
>> "%STARTUP_LOG%" echo [%DATE% %TIME%] %~1
exit /b 0


:acquire_startup_lock
set "LOCK_WAIT=%~1"
if not defined LOCK_WAIT set "LOCK_WAIT=60"
set /a LOCK_ELAPSED=0
:acquire_startup_lock_retry
mkdir "%STARTUP_LOCK_DIR%" >nul 2>nul && (
  > "%STARTUP_LOCK_DIR%\owner.txt" echo launcher_mode=%LAUNCHER_MODE% started=%DATE% %TIME%
  set "STARTUP_LOCK_HELD=1"
  exit /b 0
)
set /a LOCK_ELAPSED+=1
call :is_http_healthy "%PORT%"
if not errorlevel 1 exit /b 2
call :clear_stale_startup_lock "%STARTUP_LOCK_STALE_SECONDS%"
if not errorlevel 1 goto :acquire_startup_lock_retry
if !LOCK_ELAPSED! GEQ %LOCK_WAIT% exit /b 1
timeout /t 1 /nobreak >nul 2>nul
goto :acquire_startup_lock_retry


:clear_stale_startup_lock
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$lockPath = '%STARTUP_LOCK_DIR%'; $staleSeconds = [int]%~1; if (-not (Test-Path -LiteralPath $lockPath)) { exit 1 }; $ownerPath = Join-Path $lockPath 'owner.txt'; $stampPath = if (Test-Path -LiteralPath $ownerPath) { $ownerPath } else { $lockPath }; $age = [DateTime]::UtcNow - (Get-Item -LiteralPath $stampPath).LastWriteTimeUtc; if ($age.TotalSeconds -lt $staleSeconds) { exit 1 }; Remove-Item -LiteralPath $lockPath -Recurse -Force -ErrorAction Stop; exit 0" >nul 2>nul
exit /b %ERRORLEVEL%


:release_startup_lock
if "%STARTUP_LOCK_HELD%"=="1" (
  if exist "%STARTUP_LOCK_DIR%\owner.txt" del /f /q "%STARTUP_LOCK_DIR%\owner.txt" >nul 2>nul
  rmdir "%STARTUP_LOCK_DIR%" >nul 2>nul
  set "STARTUP_LOCK_HELD=0"
)
exit /b 0


:is_port_listening
netstat -ano -p tcp | findstr /R /C:":%~1 .*LISTENING" >nul 2>nul
exit /b %ERRORLEVEL%


:is_http_healthy
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:%~1%HEALTH_PATH%' -UseBasicParsing -TimeoutSec %HEALTH_REQUEST_TIMEOUT_SECONDS%; if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 400) { exit 0 } exit 1 } catch { exit 1 }" >nul 2>nul
exit /b %ERRORLEVEL%


:wait_http_healthy
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$port = [int]%~1; $waitSeconds = [int]%~2; $requestTimeout = [int]%HEALTH_REQUEST_TIMEOUT_SECONDS%; $uri = 'http://127.0.0.1:' + $port + '%HEALTH_PATH%'; $deadline = [DateTime]::UtcNow.AddSeconds($waitSeconds); do { try { $r = Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec $requestTimeout; if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 400) { exit 0 } } catch { }; if ([DateTime]::UtcNow -lt $deadline) { Start-Sleep -Seconds 1 } } while ([DateTime]::UtcNow -lt $deadline); exit 1"
exit /b %ERRORLEVEL%


:stop_stale_python_listener
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$port = [int]%~1; $pattern = ':' + $port + '\s+.*\s+LISTENING\s+(\d+)$'; $listeners = @(netstat -ano | ForEach-Object { if ($_ -match $pattern) { [int]$Matches[1] } } | Select-Object -Unique); if ($listeners.Count -eq 0) { exit 0 }; foreach ($listenerPid in $listeners) { $proc = Get-Process -Id $listenerPid -ErrorAction Stop; if (@('python','pythonw') -notcontains $proc.ProcessName) { Write-Error ('Port ' + $port + ' is owned by non-Python process ' + $proc.ProcessName + ' pid=' + $listenerPid); exit 2 }; Stop-Process -Id $listenerPid -Force -ErrorAction Stop; Write-Output ('Stopped stale Python listener pid=' + $listenerPid + ' on port ' + $port) }; exit 0" >> "%STARTUP_LOG%" 2>>&1
exit /b %ERRORLEVEL%


:try_python
if defined PYTHON_EXE exit /b 0
set "CANDIDATE=%~1"

if /I "%CANDIDATE%"=="python" (
  where python >nul 2>nul || exit /b 0
  python -c "import flask, flask_cors, oracledb, pandas" >nul 2>nul && set "PYTHON_EXE=python"
  exit /b 0
)


if exist "%CANDIDATE%" (
  "%CANDIDATE%" -c "import flask, flask_cors, oracledb, pandas" >nul 2>nul && set "PYTHON_EXE=%CANDIDATE%"
)
exit /b 0


:append_flask_tail
if not exist "%FLASK_LOG%" (
  call :log "Runtime Flask log does not exist yet."
  exit /b 0
)
>> "%STARTUP_LOG%" echo ---- Last %FLASK_LOG_TAIL_LINES% Flask runtime log lines ----
echo ---- Last %FLASK_LOG_TAIL_LINES% Flask runtime log lines ----
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Get-Content -LiteralPath '%FLASK_LOG%' -Tail %FLASK_LOG_TAIL_LINES%" 2^>^&1
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Get-Content -LiteralPath '%FLASK_LOG%' -Tail %FLASK_LOG_TAIL_LINES%" >> "%STARTUP_LOG%" 2>>&1
echo ---- End Flask runtime log lines ----
>> "%STARTUP_LOG%" echo ---- End Flask runtime log lines ----
exit /b 0
