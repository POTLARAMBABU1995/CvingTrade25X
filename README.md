# CvingTrade25X

CvingTrade25X is an existing layered trading and market-data application. The current integrated runtime is Flask + React + TypeScript + Oracle 19c. FastAPI charting modules exist in the repository, but the active single-port application flow is served through `backend/app.py`; do not migrate or rewrite this runtime without explicit approval.

## Architecture Overview

```text
React + TypeScript UI
  frontend/src
    -> shared API client
       frontend/src/api/client.ts
    -> Flask app
       backend/app.py
    -> feature blueprints
       backend/routes
    -> business/data services
       backend/services
    -> Oracle 19c
       market, auth, strategy, technical, sector, automation tables
    -> runtime state
       runtime, logs, backend/cache, status, locks, snapshots
    -> automation and batch jobs
       batch and backend/automation
```

The immutable market-data flow is:

```text
FYERS API or NSE files
  -> STOCK_EOD_HISTORY
  -> auto/manual merge
  -> NSE_NIFTY500_DAILY_RAW_DATA_DEV
  -> backend APIs
  -> React UI
```

Do not bypass `STOCK_EOD_HISTORY`, write directly from FYERS into `NSE_NIFTY500_DAILY_RAW_DATA_DEV`, or make React pages depend on live FYERS responses for persistent technical-analysis data unless explicitly approved.

## Runtime

### Read-only MCP adapter

`backend/mcp_server` exposes the existing Oracle-backed chart, marketdata, and price-action services as 16 explicit read-only MCP tools. It does not add duplicate Flask APIs, an arbitrary-SQL tool, or a second OHLCV pipeline. One MCP core serves local stdio, local Streamable HTTP, secure outbound tunnels, and private reverse-proxy gateways.

```powershell
cd C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X
scripts\setup_mcp_venv.cmd
scripts\validate_mcp.cmd
scripts\run_stdio.cmd
scripts\run_local_http.cmd
```

Use `http://127.0.0.1:1729/mcp` only as the private tunnel origin. Cloud clients must use the generated or configured HTTPS `/mcp` endpoint; Oracle port 1521 remains private. Remote profiles reject anonymous access unless the explicit short-lived public test flag is enabled, and support a constant-time static bearer or an external OAuth/OIDC provider through RFC 7662 introspection and MCP protected-resource metadata.

Start a tunnel-backed profile only after setting its HTTPS URL, allowed host/origin, and auth secret/provider variables:

```powershell
$env:CVING_MCP_PUBLIC_BASE_URL = 'https://mcp.example.com/mcp'
$env:CVING_MCP_ALLOWED_HOSTS = 'mcp.example.com,localhost,127.0.0.1'
$env:CVING_MCP_AUTH_MODE = 'bearer'
$env:CVING_MCP_BEARER_TOKEN = '<at-least-32-random-characters>'
scripts\run_secure_profile.cmd
```

See `docs/MCP_ARCHITECTURE.md`, `docs/REMOTE_MCP.md`, `docs/SECURITY_ARCHITECTURE.md`, and `docs/CLIENT_COMPATIBILITY.md`. Client-specific setup is in `docs/CHATGPT_SETUP.md`, `docs/CLAUDE_SETUP.md`, `docs/GEMINI_SETUP.md`, and `docs/GROK_SETUP.md`.

### CvingTrade25X Remote MCP — Free Temporary Cloudflare Tunnel

This optional development/test path exposes only the existing loopback MCP. It does not expose Oracle, open router ports, add a second MCP, or add vendor-specific tools.

```powershell
cd C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X
$env:CVING_MCP_PROFILE = 'local-http'
$env:CVING_MCP_AUTH_MODE = 'bearer'
$env:CVING_MCP_BEARER_TOKEN = '<at-least-32-random-characters>'
scripts\run_mcp_http.cmd
```

In a second PowerShell window, validate and start the tunnel:

```powershell
cd C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X
$env:CVING_MCP_AUTH_MODE = 'bearer'
$env:CVING_MCP_BEARER_TOKEN = '<same-token>'
scripts\start_quick_tunnel.cmd
```

Run `scripts\start_remote_mcp.cmd`. It validates or starts MCP on `http://127.0.0.1:1729`, checks `cloudflared`, creates an owned Quick Tunnel, captures the random HTTPS URL under `runtime\mcp`, and validates the remote MCP. Use `scripts\remote_mcp_status.cmd` for status and `scripts\stop_remote_mcp.cmd` (tunnel only) or `scripts\stop_remote_mcp.cmd --all` (owned tunnel and owned MCP) to stop it.

```powershell
scripts\quick_tunnel_status.cmd
scripts\stop_quick_tunnel.cmd
```

The URL is temporary and normally changes after `cloudflared` restarts. Quick Tunnels are development-only, have no SLA, allow at most 200 in-flight requests, and do not support SSE. CvingTrade25X uses stateless Streamable HTTP JSON responses, but each generated endpoint is still tested rather than assumed compatible. See `docs/TUNNEL_SETUP.md`, `docs/REMOTE_CLIENT_AUTH.md`, and the `*_QUICK_TUNNEL.md` client notes.

- Backend entrypoint: `backend/app.py`
- Backend routes: `backend/routes`
- Backend services: `backend/services`
- Oracle utilities: `backend/db.py`, `backend/db_pool.py`, `backend/oracle_pool.py`
- Frontend entrypoint: `frontend/src/main.tsx`
- Frontend app routing: `frontend/src/App.tsx`
- Shared frontend API client: `frontend/src/api/client.ts`
- Frontend service wrappers: `frontend/src/services`
- Runtime URL: `http://127.0.0.1:5055`
- API base: `http://127.0.0.1:5055/api`

## FYERS Background Automation

`/app/fyers/automation` uses a non-blocking job lifecycle. Batch start returns a `job_id` immediately, extraction continues in the existing FYERS background worker, and the React page polls status through the shared API client.

Oracle job state is stored in `FYERS_EXTRACTION_RUNS` and `FYERS_EXTRACTION_SYMBOL_STATUS`. This supports refresh recovery, latest-active lookup, graceful stop, and safe reruns of failed or remaining symbols while preserving the existing `STOCK_EOD_HISTORY` insertion flow and symbol/trading-date duplicate protection.

Forward, rollback, and validation SQL are:

- `backend/sql/ensure_fyers_automation_job_tracking.sql`
- `backend/sql/rollback_fyers_automation_job_tracking.sql`
- `backend/sql/validate_fyers_automation_job_tracking.sql`

NSE MCAP, FFMC, and Delivery automation remain separate from FYERS API automation.

## Sector Rotation V3 (Opt-In Shadow Mode)

Sector Rotation V3 is an additive analytics path on the existing route:

```text
GET /api/sectors/breadth?version=v3
```

V1/V2 remain the default rollback surfaces. `/app/sector/rotationv2` is explicitly pinned to V2, while the additive `/app/sector/rotationv3` route is explicitly pinned to V3 for internal comparison. The existing `/app/sector/rotation` page enables V3 only when the frontend is built with `VITE_SECTOR_ROTATION_VERSION=v3`; the backend environment selector is `SECTOR_ROTATION_ENGINE_VERSION=v3`. Leaving either flag unset preserves the existing V2 page behavior.

The V3 response ranks by canonical `finalRotationScore` and returns independent 0-100 factor scores, phase, confidence, coverage, rank movement, reasons, warnings, effective weights, and backward-compatible aliases. Published snapshots are read as immutable envelopes from additive V3 objects; if those objects are not deployed, an explicit V3 request can use the isolated shadow calculation without writing into V1/V2 snapshots.

Additive Oracle deployment, validation, and guarded rollback scripts are:

- `backend/sql/create_sector_rotation_v3_schema.sql`
- `backend/sql/validate_sector_rotation_v3_schema.sql`
- `backend/sql/rollback_sector_rotation_v3_schema.sql`

Run the DDL only through an approved Oracle 19c connection and only after review. The rollback script is intentionally blocked unless its explicit destructive confirmation token is changed. Normal application rollback requires no database operation.

Offline snapshot refresh after the V3 schema is approved and installed:

```powershell
cd C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X
$env:SECTOR_ROTATION_ENGINE_VERSION = "v3"
python backend\scripts\refresh_sector_rotation_v3.py
```

Application rollback:

```powershell
$env:SECTOR_ROTATION_ENGINE_VERSION = "v2"
$env:VITE_SECTOR_ROTATION_VERSION = "v2"
```

## Environment Standard

Use environment variables or local `.env` files for credentials and machine-specific settings. Do not commit secrets.

- `.env`: local only, ignored by Git.
- `.env.example`: safe placeholder template.
- `ORACLE_USER`, `ORACLE_PASSWORD`, `ORACLE_DSN`, `ORACLE_HOST`, `ORACLE_PORT`, `ORACLE_SERVICE_NAME`, `ORACLE_SID`: Oracle connectivity.
- `PORT`: Flask runtime port, default `5055`.
- `VITE_API_BASE_URL`: optional frontend API base override.
- `VITE_SECTOR_ROTATION_VERSION`: build-time Sector Rotation selector; only exact `v3` enables the V3 table, otherwise V2 remains active.
- `SECTOR_ROTATION_ENGINE_VERSION`: backend default breadth engine; use `v3` only for controlled V3 validation and return to `v2` for application rollback.
- `CORS_ALLOW_ORIGINS`: local allowlist for development origins.
- `CVING_ENABLE_BACKGROUND_JOBS`: enables optional startup schedulers and cache warmers when set to `1`.
- `CVING_ENABLE_MANUAL_SR_IMAGE_AUTO_INGEST`: controls the manual SR image inbox auto-ingest scheduler. The Windows startup launcher defaults this to `1` so `batch/manual_sr_image_queue/01_inbox` is processed even when broad background jobs stay disabled.
- `CVING_ENABLE_NSE_MARKETDATA_AUTOMATION`: controls the NSE market-data scheduler. When unset, it follows `CVING_ENABLE_BACKGROUND_JOBS`; set it to `1` only when the long-running NSE automation should start with Flask.

## Local Run Commands

From Windows PowerShell:

```powershell
cd C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X
python backend\app.py
```

Frontend dev server:

```powershell
cd C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X\frontend
npm.cmd run dev
```

Frontend production build:

```powershell
cd C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X\frontend
npm.cmd run typecheck
npm.cmd run test
npm.cmd run build
```

Backend validation:

```powershell
cd C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X
python -m compileall backend
python -m pytest backend\tests
```

Enterprise validation:

```powershell
cd C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X
python scripts\scan_api_duplicates.py
python scripts\enterprise_validate.py
```

Coverage, when `pytest-cov` is installed:

```powershell
cd C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X
python -m pytest backend\tests --cov=backend --cov-report=term-missing
```

Security checks, when tools are installed:

```powershell
cd C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X
python -m bandit -r backend scripts
pip-audit
ruff check backend scripts
```

## Backup Before Change Standard

Before modifying any existing file, create a local backup:

```powershell
cd C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X
python scripts\backup_before_change.py AGENTS.md README.md --version v2 --reason "short reason"
```

Backups are written under `runtime/backups/<timestamp>_<version>/` with `manifest.json`, source path, backup path, and SHA-256 hash.

## API Catalog Standard

The source of truth for endpoint governance is `docs/api-catalog.md`.

Before adding or changing an API:

```powershell
cd C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X
rg -n "route\\(|@bp\\.|@app\\." backend\routes backend\app.py
rg -n "/api/" frontend\src\api frontend\src\services
python scripts\scan_api_duplicates.py --write-catalog docs\api-catalog.md
```

No new endpoint may be merged unless `docs/api-catalog.md` is updated and `runtime/reports/api-duplicate-report.json` has no exact duplicate route.

## Release Process

1. Create a feature branch.
2. Inspect existing route, service, UI, DB, and automation ownership.
3. Back up existing files before edits.
4. Make minimal, reversible changes.
5. Update `CHANGELOG.md`, `MEMORY.md`, docs, and API catalog as applicable.
6. Run backend, frontend, duplicate API, and enterprise validation.
7. Review `runtime/reports/enterprise-validation-report.json` and `runtime/reports/security-findings.json`.
8. Prepare release notes and rollback notes.
9. Tag release only after QA/UAT/Pre-Prod gates pass.

## Rollback Process

Preferred rollback is Git:

```powershell
git status
git diff
git restore <file>
```

If Git rollback is not appropriate, restore from the backup manifest:

```powershell
cd C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X
Copy-Item runtime\backups\<folder>\<file> <file> -Force
Get-Content runtime\backups\<folder>\manifest.json
```

For DB changes, use the paired rollback script under `database/rollback` and validate with the paired script under `database/validation`. Destructive Oracle changes require explicit approval.

## Environment Lifecycle

Dev:
- Local development.
- Debug allowed.
- Local backup mandatory.
- Unit tests, lint/typecheck, and local validation required before handoff.

QA:
- Functional testing.
- No production secrets.
- Integration tests, API duplicate scan, and Oracle validation scripts required.

UAT:
- Business validation.
- Production-like masked data only.
- Release notes and user-facing workflow validation required.

Pre-Prod:
- Deployment rehearsal.
- Production-like config.
- Rollback validation and performance sanity testing required.

Prod:
- Tagged release only.
- Approved deployment only.
- No manual file or DB changes.
- Post-deployment validation, monitoring, and rollback plan required.

## Governance Files

- `AGENTS.md`: agentic development rules and guardrails.
- `MEMORY.md`: durable project decisions with versioned entries.
- `CHANGELOG.md`: versioned technical changelog.
- `docs/api-catalog.md`: endpoint catalog and duplicate-risk review.
- `docs/architecture/enterprise-pattern.md`: route/service/repository/UI pattern.
- `docs/security/devsecops-standards.md`: SonarQube, Checkmarx, dependency, and secret standards.
- `docs/release/versioning-and-backup-standard.md`: release, backup, rollback, and lifecycle policy.
- `sonar-project.properties`: local SonarQube configuration template.

## Managed MCP operations (2026-09-22)

See [MCP operations](docs/MCP_OPERATIONS.md), [autostart](docs/MCP_AUTOSTART.md),
[security](docs/MCP_SECURITY.md), [Cloudflare setup](docs/CLOUDFLARE_TUNNEL.md),
and [troubleshooting](docs/MCP_TROUBLESHOOTING.md).
Run `setup_cving_mcp_autostart.cmd` from an elevated Windows PowerShell after
configuring your actual named tunnel. Use `start_all.cmd`, `stop_all.cmd`,
`restart_all.cmd` and `cving_mcp_status.cmd` for the managed stack.
