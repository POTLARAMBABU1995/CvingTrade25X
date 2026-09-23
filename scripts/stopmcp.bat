@echo off
setlocal
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0stop_mcp.ps1" %*
exit /b %errorlevel%
