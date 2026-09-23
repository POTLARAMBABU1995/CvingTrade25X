@echo off
setlocal
cd /d "%~dp0.."
set "CVING_MCP_PROFILE=local-http"
set "CVING_MCP_HOST=127.0.0.1"
set "CVING_MCP_AUTH_MODE=none"
call scripts\run_mcp_http.cmd
exit /b %errorlevel%
