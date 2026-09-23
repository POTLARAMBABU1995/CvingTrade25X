@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ===============================================================
REM CvingTrade25X Safe Stop - visible manual logs + file logs
REM ===============================================================
REM Stops only python/pythonw processes that own the CvingTrade25X port.
REM It does NOT kill every Python process on the machine.

for %%I in ("%~dp0.") do set "ROOT=%%~fI"
if not exist "%ROOT%\backend\app.py" set "ROOT=C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X"

if not defined PORT set "PORT=5055"
set "LOG_DIR=%ROOT%\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>nul
set "STOP_LOG=%LOG_DIR%\cvingtrade25x_stop_events.log"

call :log "========== CvingTrade25X safe stop begin =========="
call :log "ROOT=%ROOT%"
call :log "PORT=%PORT%"
call :log "STOP_LOG=%STOP_LOG%"

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& { $ErrorActionPreference = 'Continue'; $port = [int]$env:PORT; $stopLog = $env:STOP_LOG; function Log([string]$m) { $line = '[' + (Get-Date -Format 'dd-MM-yyyy HH:mm:ss.fff') + '] ' + $m; Write-Host $line; Add-Content -LiteralPath $stopLog -Value $line }; Log ('Checking TCP LISTENING process on port ' + $port); $pattern = ':' + $port + '\s+.*LISTENING\s+(\d+)$'; $listenerPids = @(netstat -ano | ForEach-Object { if ($_ -match $pattern) { [int]$Matches[1] } } | Select-Object -Unique); if ($listenerPids.Count -eq 0) { Log ('No listener found on port ' + $port + '. Nothing to stop.'); exit 0 }; $failed = 0; foreach ($listenerPid in $listenerPids) { try { $proc = Get-Process -Id $listenerPid -ErrorAction Stop; Log ('Found listener pid=' + $listenerPid + ' process=' + $proc.ProcessName); if (@('python','pythonw') -contains $proc.ProcessName) { Stop-Process -Id $listenerPid -Force -ErrorAction Stop; Start-Sleep -Milliseconds 500; if (Get-Process -Id $listenerPid -ErrorAction SilentlyContinue) { Log ('ERROR: Process still running after stop attempt. pid=' + $listenerPid); $failed = 1 } else { Log ('Stopped CvingTrade25X Python listener pid=' + $listenerPid + ' on port ' + $port) } } else { Log ('SKIPPED: Non-Python listener process=' + $proc.ProcessName + ' pid=' + $listenerPid + ' on port ' + $port); $failed = 1 } } catch { Log ('ERROR: ' + $_.Exception.Message); $failed = 1 } }; exit $failed }"
set "RC=%ERRORLEVEL%"

if "%RC%"=="0" (
  call :log "CvingTrade25X safe stop finished successfully."
) else (
  call :log "CvingTrade25X safe stop finished with errors. rc=%RC%"
)

echo.
echo Stop log saved at:
echo   %STOP_LOG%
echo.
echo Press any key to close this window.
pause >nul
exit /b %RC%

:log
echo [%DATE% %TIME%] %~1
>> "%STOP_LOG%" echo [%DATE% %TIME%] %~1
exit /b 0
