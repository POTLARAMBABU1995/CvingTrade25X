@echo off
setlocal
cd /d "%~dp0.."
if "%~1"=="" (
  echo Usage: scripts\validate_remote_mcp.cmd https://mcp.example.com/mcp 1>&2
  exit /b 2
)
if exist ".venv-mcp\Scripts\python.exe" (
  ".venv-mcp\Scripts\python.exe" scripts\validate_remote_endpoint.py --url "%~1"
) else (
  python scripts\validate_remote_endpoint.py --url "%~1"
)
exit /b %errorlevel%
