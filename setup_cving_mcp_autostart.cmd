@echo off
setlocal
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0scripts\setup_cving_mcp_autostart.ps1" %*
exit /b %errorlevel%
