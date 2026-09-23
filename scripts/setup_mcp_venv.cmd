@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv-mcp\Scripts\python.exe" python -m venv --system-site-packages .venv-mcp
if errorlevel 1 exit /b %errorlevel%
call ".venv-mcp\Scripts\activate.bat"
if errorlevel 1 exit /b %errorlevel%
python -m pip install --disable-pip-version-check -r requirements-mcp.txt
if errorlevel 1 exit /b %errorlevel%
python -c "import mcp, oracledb, pandas, dotenv" || (
  echo MCP runtime dependencies are missing from the application Python environment. 1>&2
  exit /b 1
)
endlocal
