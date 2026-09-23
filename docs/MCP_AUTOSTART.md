# Windows MCP autostart

Run from the project root in an elevated Windows PowerShell window:
```powershell
.\setup_cving_mcp_autostart.cmd
```
The dedicated .venv-mcp must already exist. No dependencies are installed and no
Oracle objects/data are modified by this command. Environment values are loaded
from ignored .env without overriding explicit process values.

CVING_MCP_AutoStart and CVING_MCP_Watchdog run at this user's logon with highest
privileges, correct working directory, hidden windows, IgnoreNew concurrency,
and bounded Task Scheduler restart attempts. This is **logon startup**, not a
password-storing unattended pre-logon task. cloudflared's named service is
Automatic and may connect before logon; the origin becomes available at logon.

The watchdog retries unreachable MCP three times, restarts only an owned MCP,
and allows five restart attempts in a rolling ten-minute window. Its history is
persisted across runs. HTTP errors other than connection failure are reported
without restart. A tunnel failure never restarts Oracle or MCP. Cloudflare public
checks use capped 5, 10, 20, 40, 60 second backoff. Named service recovery is also
configured in Service Control Manager.

Install/uninstall components separately:
```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\install_mcp_autostart.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\install_cloudflared_service.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\uninstall_mcp_autostart.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\uninstall_cloudflared_service.ps1
```
Existing task/service names with another owner are rejected. Stop/uninstall does
not target arbitrary Python or cloudflared processes. An old Startup-folder VBS
may still run; its repository launcher now delegates to the same lifecycle lock.
Review that shortcut before retiring the old deployment. An existing process
without the new ownership state must be stopped through its original owner.

Verification after installation: sign out/in, inspect task LastTaskResult, run
cving_mcp_status.cmd, then validate authenticated tools/list and Oracle readiness.
A reboot/logon test has not been performed by this code change.
