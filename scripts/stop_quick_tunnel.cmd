@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_quick_tunnel.ps1" %*
exit /b %errorlevel%
