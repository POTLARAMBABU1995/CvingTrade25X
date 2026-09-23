@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0remote_mcp_status.ps1" %*
exit /b %errorlevel%
