@echo off
setlocal
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0scripts\cving_mcp_status.ps1" %*
exit /b %errorlevel%
