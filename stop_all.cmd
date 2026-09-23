@echo off
setlocal
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0scripts\stop_all.ps1" %*
exit /b %errorlevel%
