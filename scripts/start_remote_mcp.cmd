@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_remote_mcp.ps1" %*
exit /b %errorlevel%
