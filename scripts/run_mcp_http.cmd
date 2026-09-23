@echo off
setlocal
cd /d "%~dp0.."
if exist ".venv-mcp\Scripts\python.exe" (
  ".venv-mcp\Scripts\python.exe" -m backend.mcp_server.cli serve --transport streamable-http
) else (
  python -m backend.mcp_server.cli serve --transport streamable-http
)
endlocal
