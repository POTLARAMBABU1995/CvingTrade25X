@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0quick_tunnel_status.ps1" %*
exit /b %errorlevel%
