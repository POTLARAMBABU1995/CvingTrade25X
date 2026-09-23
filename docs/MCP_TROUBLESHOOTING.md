# MCP troubleshooting

| Observation | Action |
| --- | --- |
| Local 401, /health 404 | Older MCP process is still running. Stop through its verified owner and launch the new code. |
| Local 401, readiness 503 | Oracle dependency unavailable. Inspect safe event types and Oracle status; do not restart Oracle automatically. |
| Local healthy, public unavailable | Check DNS, tunnel config/service and networking. Keep MCP running. |
| Tunnel running, origin unreachable | Check owned MCP startup/configuration and watchdog restart budget. |
| Port occupied by unknown PID | Do not kill it. Verify owner and stop through that application's launcher. |
| 429 | Token or aggregate peer request budget reached. Back off; do not rotate invalid tokens. |
| 503 capacity | Wait for executing workers to finish. |
| 504 | HTTP deadline expired; synchronous work may finish under the Oracle timeout. |
| RESOURCE_LIMIT on scan | Existing application price-action snapshot is unavailable; cold full-universe reads exceed the MCP query budget. |
| CRITICAL watchdog | Five attempts within ten minutes. Fix the cause before explicit start clears manual-stop marker. |
| Service/task access denied | Use an elevated PowerShell session for install/uninstall; do not bypass ownership checks. |
| Legacy PID lacks start_ticks | Old ownership state is insufficient to kill a process safely. Verify and stop through its original owner. |

Run scripts/diagnose_mcp.ps1. It saves safe status, DNS, firewall state and the
allowlisted lifecycle log under runtime/diagnostics. It does not dump environment
variables, arbitrary logs, process command lines or credentials.

Regression commands:
```powershell
.\.venv-mcp\Scripts\python.exe -m pytest backend\tests\test_mcp_hardening.py backend\tests\test_mcp_contract.py backend\tests\test_mcp_auth.py backend\tests\test_mcp_http_security.py backend\tests\test_mcp_env_loader.py backend\tests\test_mcp_price_action_service.py backend\tests\test_mcp_oauth_server.py backend\tests\test_mcp_quick_tunnel.py -q
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\test_mcp_lifecycle.ps1
.\.venv-mcp\Scripts\python.exe scripts\scan_api_duplicates.py
```
The lifecycle harness uses isolated mocked process/network operations. It does
not prove Task Scheduler installation, Service Control Manager recovery or reboot.
