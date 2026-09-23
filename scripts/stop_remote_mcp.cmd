@echo off
setlocal
if /I "%~1"=="--all" (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_remote_mcp.ps1" -All
) else (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_remote_mcp.ps1"
)
exit /b %errorlevel%
