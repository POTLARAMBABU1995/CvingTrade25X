@echo off
setlocal
cd /d "%~dp0.."
set "CVING_MCP_PROFILE=secure-tunnel"
set "CVING_MCP_HOST=127.0.0.1"
if not defined CVING_MCP_PUBLIC_BASE_URL (
  echo CVING_MCP_PUBLIC_BASE_URL must be set to the public HTTPS MCP base URL. 1>&2
  exit /b 2
)
if not defined CVING_MCP_BEARER_TOKEN if /i not "%CVING_MCP_AUTH_MODE%"=="oauth" (
  echo Set CVING_MCP_BEARER_TOKEN or configure CVING_MCP_AUTH_MODE=oauth. 1>&2
  exit /b 2
)
call scripts\run_mcp_http.cmd
exit /b %errorlevel%
