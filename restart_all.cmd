@echo off
setlocal
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0scripts\restart_all.ps1" %*
exit /b %errorlevel%
