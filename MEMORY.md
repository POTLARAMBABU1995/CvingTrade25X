# Project Memory

Version: v2026-09-17-mcp-secure-multiai
Timestamp: 2026-09-17 20:40:00 IST
Decision: One vendor-neutral read-only MCP core serves local stdio, local Streamable HTTP, and authenticated HTTPS edge/tunnel deployments.
Before Logic: The initial local MCP adapter reused existing price-action services but had only partial remote security/configuration and no scoped OAuth resource-server integration.
After Logic: `backend/mcp_server` keeps the existing tool owners and `/mcp` contract, adds explicit local/tunnel/gateway profiles, SDK-native bearer/OAuth authentication, per-tool read scopes, Host/Origin and resource limits, validators, and client-neutral deployment documentation. Oracle remains private; there is no arbitrary SQL or write tool.
Files Impacted: `backend/mcp_server`, `backend/tests/test_mcp_*`, `scripts/*mcp*`, `.env.example`, `requirements-mcp.txt`, `README.md`, `docs/*MCP*`, and vendor setup docs.
Reason: Allow multiple MCP-compatible AI clients to use one secure adapter without duplicating Flask APIs, exposing Oracle, or forking business logic per vendor.
Boundary: TLS terminates at a trusted tunnel/reverse proxy; OAuth is delegated to an external standards-compliant IdP; live vendor connections require user-owned DNS, tunnel, IdP, and account configuration.
Rollback Notes: Restore edited files from `runtime/backups/2026-09-17_163945_v2026-09-17-mcp-secure-multiai` and `runtime/backups/2026-09-17_171516_v2026-09-17-mcp-runtime-deps`, remove additive MCP docs/scripts/tests, and reinstall the prior `.venv-mcp` if needed.

Version: v1
Timestamp: 2026-06-03 07:33:26 IST
Decision: Flask remains the active backend runtime.
Before Logic: Repository docs contained older FastAPI charting guidance alongside the active Flask application.
After Logic: Current integrated runtime is documented as `backend/app.py` plus Flask blueprints under `backend/routes`; FastAPI migration requires explicit approval.
Files Impacted: `AGENTS.md`, `README.md`, `docs/architecture/enterprise-pattern.md`
Reason: Preserve the working production-grade application shape and avoid accidental greenfield rewrites.
Rollback Notes: Restore the backed-up `AGENTS.md` and `README.md` from `runtime/backups/2026-06-03_073326_v1` or use Git restore.

Version: v65
Timestamp: 2026-06-18 10:10:00 IST
Decision: FYERS batch extraction uses a persisted non-blocking background-job lifecycle.
Before Logic: FYERS start/status used an in-memory thread registry and the browser timeout was temporarily increased to ten minutes; refresh or Flask restart could lose the active-job view.
After Logic: Existing FYERS worker threads remain responsible for extraction, while Oracle `FYERS_EXTRACTION_RUNS` and `FYERS_EXTRACTION_SYMBOL_STATUS` persist job and symbol state. React starts quickly, polls by `job_id`, recovers the latest active job, and supports stop and failed/remaining reruns.
Files Impacted: `backend/services/marketdata_service.py`, `backend/routes/marketdata.py`, `backend/sql/ensure_fyers_automation_job_tracking.sql`, `frontend/src/services/api/fyersApi.ts`, `frontend/src/pages/fyers/FyersAutomationPage.tsx`
Reason: Keep 990-1500+ symbol FYERS extraction independent of browser request lifetime without changing Flask, Oracle system-of-record behavior, or the immutable market-data flow.
Boundary: NSE MCAP, FFMC, and Delivery automation are separate pipelines and must not be combined with FYERS job ownership.
Rollback Notes: Restore backend and frontend files from the v65 backup manifests and remove the additive SQL bundle; destructive Oracle rollback requires DBA approval.

Version: v1
Timestamp: 2026-06-03 07:33:26 IST
Decision: React + TypeScript remains the frontend standard.
Before Logic: React pages already owned active UI routes, with legacy static folders present for compatibility/reference.
After Logic: New UI work must stay in `frontend/src`, use the shared API client, and follow existing component/service patterns.
Files Impacted: `AGENTS.md`, `README.md`, `frontend/src/api/endpoints.ts`
Reason: Prevent new legacy HTML, JS, or CSS feature paths.
Rollback Notes: Remove `frontend/src/api/endpoints.ts` if the forward endpoint standard must be reverted.

Version: v1
Timestamp: 2026-06-03 07:33:26 IST
Decision: Oracle 19c remains the database source of truth.
Before Logic: Oracle utilities and SQL scripts existed, but governance around future DB changes was not centralized.
After Logic: DB changes require forward migration, rollback script, validation script, impact notes, and explicit approval for destructive DDL.
Files Impacted: `database/README.md`, `database/migrations/README.md`, `database/rollback/README.md`, `database/validation/README.md`
Reason: Protect market, auth, strategy, technical, sector, and automation data integrity.
Rollback Notes: Remove the database README guidance files if this governance standard is rolled back.

Version: v1
Timestamp: 2026-06-03 07:33:26 IST
Decision: Existing market-data flow must not be bypassed.
Before Logic: The flow was known operationally and in agent guidance.
After Logic: The immutable flow is documented as FYERS API or NSE files -> `STOCK_EOD_HISTORY` -> auto/manual merge -> `NSE_NIFTY500_DAILY_RAW_DATA_DEV` -> backend APIs -> React UI.
Files Impacted: `AGENTS.md`, `README.md`, `docs/architecture/enterprise-pattern.md`
Reason: Prevent accidental direct browser-to-FYERS or direct FYERS-to-DEV persistence changes.
Rollback Notes: Restore backed-up docs or Git state.

Version: v1
Timestamp: 2026-06-03 07:33:26 IST
Decision: API calls must go through the shared frontend API client.
Before Logic: Services already used `frontend/src/api/client.ts`, but endpoint governance was not documented.
After Logic: New frontend service work must use `frontend/src/api/client.ts` and should use constants from `frontend/src/api/endpoints.ts`.
Files Impacted: `frontend/src/api/endpoints.ts`, `docs/api-catalog.md`, `docs/architecture/enterprise-pattern.md`
Reason: Preserve auth headers, request IDs, timeouts, and diagnostics consistently.
Rollback Notes: Remove endpoint constants only if existing services remain untouched and docs are restored.

Version: v1
Timestamp: 2026-06-03 07:33:26 IST
Decision: Backups must be created before editing existing files.
Before Logic: Local manual backups were ad hoc.
After Logic: `scripts/backup_before_change.py` creates timestamped backups under `runtime/backups` with a manifest and SHA-256 hashes.
Files Impacted: `scripts/backup_before_change.py`, `docs/release/versioning-and-backup-standard.md`, `README.md`
Reason: Make future changes traceable and reversible even before Git operations.
Rollback Notes: Remove the script and restore docs from backup if this standard is reverted.

Version: v45
Timestamp: 2026-06-12 10:55:00 IST
Decision: Independent sector mappings must be split into separate staging tables.
Before Logic: The 3 sectors Restaurants, Hospitality Hotels & Resorts, and Tourism & Travel were lumped into one RESTAURANTS_HOSPITALITY_TRAVEL sector code.
After Logic: Sectors are onboarded individually with independent staging tables (e.g. `NSE_NIFTY_RESTAURANTS_STAGING`) so they properly increment the total sector count on the UI.
Files Impacted: `backend/routes/sector_rotation.py`, `backend/scripts/load_restaurants_hospitality_travel_sector_file.py`, `backend/sql/create_sector_reference_sync_procedures.sql`
Reason: The UI relies on the distinct sector codes returned by `/api/sectors/breadth` to count total sectors. Combining them hides the distinct domains.
Rollback Notes: Run the rollback script and revert changes in git.
