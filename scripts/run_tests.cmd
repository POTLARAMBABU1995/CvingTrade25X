@echo off
setlocal
cd /d "%~dp0.."
if exist ".venv-mcp\Scripts\python.exe" (
  ".venv-mcp\Scripts\python.exe" -m pytest backend\tests\test_mcp_http_security.py backend\tests\test_mcp_auth.py backend\tests\test_mcp_contract.py backend\tests\test_mcp_price_action_service.py -q
) else (
  python -m pytest backend\tests\test_mcp_http_security.py backend\tests\test_mcp_auth.py backend\tests\test_mcp_contract.py backend\tests\test_mcp_price_action_service.py -q
)
exit /b %errorlevel%
