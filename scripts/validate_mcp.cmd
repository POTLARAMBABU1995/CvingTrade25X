@echo off
setlocal
cd /d "%~dp0.."
if exist ".venv-mcp\Scripts\python.exe" (
  ".venv-mcp\Scripts\python.exe" scripts\validate_mcp.py
) else (
  python scripts\validate_mcp.py
)
exit /b %errorlevel%
