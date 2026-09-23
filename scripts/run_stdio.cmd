@echo off
setlocal
cd /d "%~dp0.."
set "CVING_MCP_PROFILE=local-stdio"
call scripts\run_mcp_stdio.cmd
exit /b %errorlevel%
