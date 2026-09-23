@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_quick_tunnel.ps1" %*
exit /b %errorlevel%
