# CVING_MCP operations

## Architecture
Remote MCP client -> HTTPS Cloudflare named tunnel -> cloudflared Windows service
-> 127.0.0.1:1729/mcp -> existing 16-tool service adapter -> existing Oracle pool.
The MCP process applies read-only SQL and transaction guards. Flask keeps its
existing database behavior. No database migration is executed by setup.

## Commands (Windows PowerShell, project root)
```powershell
.\start_all.cmd
.\cving_mcp_status.cmd
.\restart_all.cmd
.\stop_all.cmd
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\diagnose_mcp.ps1
```
Start checks environment/imports, serializes lifecycle actions, checks listener
ownership, and accepts a healthy existing 401 endpoint without adopting its PID.
Stop/restart only terminate processes with matching executable, start time,
recorded project and MCP command line. An untracked listener remains untouched.
Old startmcp/stopmcp and remote launchers delegate to the shared implementation.

Manual stop sets runtime/mcp/operator_stopped. The watchdog respects that marker.
Explicit start clears it. A restart-budget exhaustion also sets the marker;
inspect the cause before an explicit restart. Stop before changing tunnel mode.

## Health
- /live and /healthz: cheap liveness, no Oracle request.
- /health, /ready, /readyz: redacted readiness; 200 reachable, 503 unavailable.
- /mcp without bearer token: expected 401; 401 alone is not Oracle readiness.
- Protected health_check/readiness_check tools retain their existing contracts.
Readiness uses an asynchronous worker and a 15-second cache. HTTP health routes
share Host, Origin, rate, concurrency and timeout controls.

## Logs
runtime/logs/mcp.log contains JSON events, request IDs, tool names, outcomes and
durations, rotating at CVING_MCP_LOG_MAX_BYTES (10 MiB) with 5 backups by default.
Raw service message arguments and exceptions are not serialized. Access logging
is disabled to avoid OAuth secrets in URLs. watchdog.log records safe lifecycle
events and rotates at 10 MiB with 5 backups. Quick Tunnel uses its existing logs.
Cloudflare service diagnostics also use the Windows event log. No token is
passed in service command-line arguments.

## Rollback
Stop the owned stack and uninstall owned scheduled tasks/service using the
scripts in MCP_AUTOSTART.md. Restore only the changed existing files from the
SHA-256 manifests under runtime/backups/2026-09-22_*mcp*. Leave newly added files
unused if rollback is needed; do not delete unrelated files or change Oracle.
The existing .env is unchanged. Restore prior launchers only after disabling the
new task to avoid competing startup mechanisms.
