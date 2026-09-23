## 2026-09-22 16:40 IST - MCP managed lifecycle and read-only hardening

- Added Windows lifecycle helpers, logon tasks, bounded watchdog recovery, named Cloudflare service support, diagnostics and one-command wrappers. Existing launchers delegate to the shared implementation.
- Added PID start-time/command ownership checks, netstat fallback, persisted restart history, manual-stop gate and Quick Tunnel lifecycle locking.
- Enforced loopback/authenticated HTTP; added safe health aliases, HTTP deadlines, executing-worker limits, bounded rate identities, strict Origin handling and rotating safe JSON audit logs.
- Added MCP-only Oracle read-only transactions, lexical SQL validation, query/pool limits, optional dedicated credentials, shared legacy pool alias and fail-closed direct-connection fallback. No Oracle DDL/DML executed.
- Added regression coverage, operational docs and a non-executing DBA review template with validation/rollback guidance.
- Validation and deployment limitations: docs/MCP_IMPLEMENTATION_REPORT.md. Elevated deployment and actual named-tunnel configuration remain required.

## 2026-09-21 - MCP End-to-End Flow Documentation

- Added `docs/MCP_END_TO_END_FLOW.md` and the matching plain-text `docs/MCP_END_TO_END_FLOW.txt`.
- Documented the verified local and remote MCP lifecycle, OAuth 2.1/DCR sequence, 16-tool dispatch map, existing-service reuse, Oracle read boundary, security gates, runtime state, validation, troubleshooting, and safe shutdown.
- Recorded the observed runtime distinction between the active local MCP and stopped Cloudflare process so the saved temporary URL is not represented as a currently live permanent endpoint.

## 2026-09-21 - Claude Web OAuth 2.1 DCR & AS Discovery Registration Fix

- Resolved Claude Web custom connector error `"Couldn't register with CVING_MCP's sign-in service"`:
  - Enabled Dynamic Client Registration (`ClientRegistrationOptions(enabled=True, valid_scopes=list(ALL_SCOPES), default_scopes=list(ALL_SCOPES))`) in `backend/mcp_server/server.py` so the MCP SDK mounts `/register` and advertises `registration_endpoint` in RFC 8414 metadata.
  - Fixed client ID preservation in `backend/mcp_server/oauth_provider.py`: previously generated a separate random client ID during `register_client`, causing client ID mismatch on subsequent `/authorize` requests. Now faithfully preserves and stores the client credentials minted during DCR.
  - Added default scope allocation (`ALL_SCOPES`) during registration and scope fallback so clients registering without explicit scopes are granted all MCP read scopes.
  - Added discovery path aliases in `cli.py` and permitted them through `security.py` (`/.well-known/oauth-authorization-server/mcp`, `/.well-known/openid-configuration/mcp`, `/mcp/.well-known/openid-configuration`, `/mcp/register`).
  - Resolved browser `"Origin not allowed"` 403 on `/oauth/consent` POST: implemented `_origin_allowed` in `backend/mcp_server/security.py` to allow same-origin browser form submissions, Cloudflare tunnel domains, and trusted LLM client origins (`claude.ai`, `chatgpt.com`).
  - Added dynamic Cloudflare Host/X-Forwarded-Host detection in `backend/mcp_server/security.py` so metadata URLs always dynamically match the exact active tunnel hostname.
- Verified end-to-end OAuth 2.1 flow via Cloudflare Quick Tunnel (`scripts/test_e2e_oauth.py`):
  1. RFC 7591 Dynamic Client Registration (DCR) -> 201 Created
  2. Authorization Code request with PKCE S256 -> 302 Redirect to Consent page
  3. Owner password consent verification -> 302 Redirect to callback with authorization code
  4. Code exchange for Bearer token -> 200 OK with access token & refresh token
  5. Authenticated MCP `tools/list` call -> 200 OK returning all 16 tools
- 34/34 tests passed in `test_mcp_oauth_server.py` and `test_mcp_http_security.py`.

## 2026-09-21 - Remote MCP Tunnel & Validation Scripts OAuth-Server Mode Support

- Updated `scripts/start_quick_tunnel.ps1`, `scripts/validate_local_mcp.py`, `scripts/validate_remote_mcp.py`, and `scripts/mcp_endpoint_validation.py` to support `oauth-server` authentication mode seamlessly.
- Executed `scripts/start_quick_tunnel.ps1 -Detach`: 100% PASS for HTTPS, TLS 1.3, MCP Initialize, 16 read-only tools, Oracle 19c readiness, response size limits, and secret safety checks.
- Verified active public endpoint at `https://caroline-prediction-anything-thinks.trycloudflare.com/mcp`.

## 2026-09-19 - Historical Data UI Table Rendering, Instant Millisecond Search/Filter/Sort, and Error Recovery

- **UI Table Rendering & Non-disappearing Display ("table is not appearing on ui fix it")**:
  - Initialized `tableName` with `DEFAULT_TABLE` (`'NSE_NIFTY500_DAILY_RAW_DATA_DEV'`) and `tables` with `KNOWN_TABLES` (`['NSE_NIFTY500_DAILY_RAW_DATA_DEV', 'NSE_NIFTY500_DAILY_RAW_DATA_ORACLE']`), eliminating waterfall blocking where table summary waited for asynchronous table-list endpoint before mounting.
  - Implemented 10 shimmering skeleton rows when `status === 'loading' && rows.length === 0` so the table headers, column widths, and structure appear immediately on first paint without blank screens or missing container.
  - Implemented stale-while-revalidate for searches and filters so existing rows stay visible at 75% opacity while background updates execute, preventing any flashing or table disappearance.
  - Added dedicated Retry button to `ErrorAlertCard` and contextual error empty-state message inside `AppDataTable` allowing one-click immediate retry without refreshing the browser.
- **Instant Millisecond Search/Filter/Sort ("data should load on ui in mm ss & filter/sort/search as well")**:
  - Reduced search input debounce to 150ms for snappy real-time responsiveness.
  - Implemented in-memory client query caching (`clientCacheRef`) keyed by table, page, symbol search, and filter parameters; repeated searches and page switches resolve in 0-1ms.
  - Improved date column sorting in `sortValue` with epoch millisecond parsing, supporting both ISO `YYYY-MM-DD` and Indian `DD-MM-YYYY` formats chronologically.
- **Fast Download ("download file should download in mmss only")**:
  - Maintained instant symbol export download trigger with accurate dynamic filename format (`${SYMBOL}_${latest_trade_date}_${HHMMSS}.zip`, e.g. `ITC_18-09-2026_060200.zip`).
  - Added visual progress state on the download button and non-blocking background fetch.
- **Verification**:
  - Vitest component test passed (`frontend/tests/historicalDataPage.test.tsx`).
  - TypeScript typecheck passed with 0 errors (`npm run typecheck`).
  - Frontend production build (`npm run build`) completed with `validate_frontend_bundle.py` passing.
  - Backend pytest passed (`backend/tests/test_historical_data_service.py`).
  - Zero duplicate APIs confirmed (`python scripts/scan_api_duplicates.py`).

### Files Changed

- `frontend/src/pages/ops/HistoricalDataPage.tsx`
- `CHANGELOG.md`

### Rollback

Restore files from `runtime/backups/2026-09-19_075944_v1/`, run `cd frontend && npm run build`.

## 2026-09-19 - Historical Data Performance Optimization & Trade_Date Fix

- **Performance Optimization (>30s to ~1ms)**:
  - Implemented in-memory Master Table Summary caching (`_get_master_table_summary`) in `historical_data_service.py` with extended 1800s (30m) TTL.
  - Sliced and filtered all subsequent symbol searches, record counts, date ranges, and ATH filters in-memory in Python. Search latency dropped from >25-30 seconds to ~1 millisecond (>25,000x speedup).
  - Added 300ms search input debouncing in `HistoricalDataPage.tsx` to eliminate redundant network storms on keystrokes.
  - Implemented one-shot force refresh (`refresh=true`) so clicking the UI Refresh button reloads from Oracle and refreshes the master cache, while subsequent paging and filtering stay cached in-memory.
- **Trade_Date Column Display**:
  - Ensured `trade_date` is populated in all summary rows from `LATEST_TRADING_DATE` and formatted via `formatLegacyDateOnly` into `DD-MM-YYYY`.
  - Restarted stale 5:54 AM Flask process (PID 5708) with the verified launcher; confirmed `/api/health` and verified `Trade_Date` is actively served on port 5055.
- **Verification**:
  - 19 passed in backend pytest (including new tests for in-memory filtering and cache refresh).
  - Vitest component test passed for `HistoricalDataPage`.
  - TypeScript typecheck passed with 0 errors.
  - Frontend production build (`dist/`) generated and passed `validate_bundle.py`.
  - API duplicate scan passed with 0 duplicates.

### Files Changed

- `backend/services/historical_data_service.py`
- `backend/tests/test_historical_data_service.py`
- `frontend/src/pages/ops/HistoricalDataPage.tsx`
- `docs/api-catalog.md`
- `CHANGELOG.md`

### Rollback

Restore files from `runtime/backups/2026-09-19_071747_v1/`, rebuild frontend bundle, and restart Flask server via `start_flask_cvingtrade25x.bat`.

## 2026-09-19 - Historical Data Trade_Date column, auto-width headers/cells, and dynamic export filename

- Added `Trade_Date` column immediately next to the `Price` column on `/app/database/historical-data`.
- Updated backend summary endpoint and SQL queries (`SUMMARY_SELECT_COLUMNS` and `_build_summary_base_sql`) to provide `trade_date` (latest trading date).
- Updated Historical Data table styles to `table-layout: auto` and `white-space: nowrap` with `width: auto` on headers and row data cells, allowing headers and data cells to auto-size to content width with smooth horizontal scrolling.
- Updated export filename format for per-symbol downloads to `SYMBOL_trade_date(latest)_CurrentTimestamp` (e.g. `ITC_18-09-2026_060200.zip` containing `.csv`, `.json`, `.txt`) across backend bundle generation and frontend download trigger.
- Verified backend pytest (18 passed), Vitest component test, TypeScript typecheck, frontend production build, and zero API duplicates.

### Files Changed

- `frontend/src/pages/ops/HistoricalDataPage.tsx`
- `frontend/src/styles.css`
- `frontend/tests/historicalDataPage.test.tsx`
- `backend/services/historical_data_service.py`
- `backend/tests/test_historical_data_service.py`
- `backend/routes/historical_data.py`
- `docs/api-catalog.md`
- `CHANGELOG.md`

### Rollback

Restore files from `runtime/backups/2026-09-19_065621_v1/` and `runtime/backups/2026-09-19_065858_v1/`, rebuild frontend bundle, and restart Flask if needed.

## 2026-09-19 - Historical Data Download header and volume column export

- Updated `/app/database/historical-data` table column header from `CSV / JSON / TXT` to `Download`.
- Updated Historical Data per-symbol export files (CSV, JSON, TXT inside ZIP bundle) to include the `volume` column while keeping all existing columns intact: `s.no, symbol, trade_date, open, high, low, close, volume`.
- Updated backend service `historical_data_service.py` (`CSV_HEADERS` and `_get_symbol_export_rows`) to map and export `volume`.
- Updated backend and frontend test suites covering the new column and header label.
- Rebuilt frontend bundle (`frontend/dist`) and verified bundle integrity and zero API duplicates.

### Files Changed

- `frontend/src/pages/ops/HistoricalDataPage.tsx`
- `frontend/tests/historicalDataPage.test.tsx`
- `backend/services/historical_data_service.py`
- `backend/tests/test_historical_data_service.py`
- `backend/tests/test_historical_data_routes.py`
- `docs/api-catalog.md`
- `CHANGELOG.md`

### Rollback

Restore files from `runtime/backups/2026-09-19_064407_v1/`, rebuild frontend bundle, and restart Flask if needed.

## 2026-09-18 - Built-in OAuth 2.1 Authorization Server for MCP

- Added `oauth-server` auth mode: the MCP server acts as its own OAuth 2.1 Authorization Server, supporting Authorization Code + PKCE (S256), Dynamic Client Registration (RFC 7591), token refresh/revocation, and a minimal owner consent screen.
- New file `backend/mcp_server/oauth_provider.py` implements the MCP SDK's `OAuthAuthorizationServerProvider` protocol with in-memory stores for clients, authorization codes, access tokens, and refresh tokens.
- Modified `backend/mcp_server/config.py`: added `oauth-server` to AUTH_MODES, new settings for `CVING_MCP_OAUTH_OWNER_PASSWORD`, token TTLs, and code TTL; `secure-tunnel` profile auto-defaults to `oauth-server` when owner password is set.
- Modified `backend/mcp_server/server.py`: wire `auth_server_provider` to MCPServer when in `oauth-server` mode. Static bearer fallback handled inside the provider's `load_access_token`.
- Modified `backend/mcp_server/cli.py`: mount `/oauth/consent` route for the consent screen.
- Modified `backend/mcp_server/security.py`: extended path matching for OAuth routes (`/authorize`, `/token`, `/register`, `/revoke`, `/oauth/consent`, `/.well-known/oauth-authorization-server`); added `_rewrite_as_metadata_response` to dynamically rewrite loopback URLs in OAuth AS metadata for Cloudflare requests.
- Preserved existing `bearer` and `oauth` (external introspection) modes unchanged.
- All 16 read-only MCP tools unchanged. No frontend, API, or Oracle changes.

### Files Changed

- `backend/mcp_server/oauth_provider.py` (NEW)
- `backend/mcp_server/config.py`
- `backend/mcp_server/auth.py`
- `backend/mcp_server/server.py`
- `backend/mcp_server/cli.py`
- `backend/mcp_server/security.py`
- `backend/tests/test_mcp_oauth_server.py` (NEW)
- `docs/OAUTH_SETUP.md`

### Rollback

Restore files from `runtime/backups/2026-09-18_210934_v1/`.

## 2026-09-18 - Public OAuth protected-resource metadata for remote MCP

- Kept the MCP listener loopback-only on `127.0.0.1:1729` while making Cloudflare-proxied authentication challenges advertise the current public HTTPS protected-resource metadata URL.
- Resolve the public MCP URL at request time from `CVING_MCP_PUBLIC_URL`, `CVING_MCP_PUBLIC_BASE_URL`, or the ignored runtime file `runtime/mcp/remote_mcp_url.txt`; temporary `trycloudflare.com` hostnames are not hardcoded.
- Rewrite only trusted Cloudflare-proxied MCP challenges and protected-resource metadata responses. Local clients continue to receive localhost metadata, and bearer authentication plus Host/Origin validation remain enforced.
- Added regression coverage for local metadata, remote Cloudflare metadata, missing/valid bearer authentication, public metadata contents, secret safety, and Windows UTF-8 BOM runtime URL files.
- Live verification passed through `https://contents-school-tennis-anthony.trycloudflare.com/mcp`: anonymous access returned 401 with the public metadata URL, authenticated initialize/tool discovery succeeded with all 16 read-only tools, and Oracle 19c readiness remained UP. Oracle port 1521 was not exposed or changed.

### Validation

- Focused authentication/security/tunnel tests: 22 passed.
- Live remote validator: PASS for HTTPS, TLS 1.3, initialize, 16-tool contract, bearer rejection, authenticated tool call, Oracle readiness, response limits, and secret-leak check.
- Ruff over the changed MCP middleware and tests: passed.

### Rollback

Restore `backend/mcp_server/security.py`, `backend/tests/test_mcp_http_security.py`, and `CHANGELOG.md` from `runtime/backups/2026-09-18_191325_v2026-09-18-remote-metadata-url`, then restart the MCP runtime. No Flask API, frontend, Oracle schema/data, trading logic, or tunnel configuration rollback is required.

## 2026-09-18 - Local MCP bearer configuration loading

- Added a stdlib-only MCP `.env` loader that imports only `CVING_MCP_*` and `CVING_QUICK_TUNNEL_*` settings while preserving explicit process-environment precedence.
- Updated the local MCP CLI and Cloudflare Quick Tunnel launcher to use the ignored project `.env`, so bearer authentication works without hardcoding secrets in tracked launchers or command history.
- Added focused tests proving prefix filtering, quote handling, environment precedence, and missing-file behavior. No Flask API, Oracle schema/data, frontend, or trading logic changed.

### Rollback

Restore `.env`, `backend/mcp_server/cli.py`, `scripts/start_quick_tunnel.ps1`, and `CHANGELOG.md` from the pre-change backups; remove `backend/mcp_server/env_loader.py`, `scripts/import_mcp_local_env.ps1`, and `backend/tests/test_mcp_env_loader.py`.

## 2026-09-18 - Optional Cloudflare Quick Tunnel for read-only MCP

- Added Windows start/status/stop wrappers for a free temporary Cloudflare Quick Tunnel over the existing loopback MCP; exact owned PID/path state prevents stopping unrelated `cloudflared` processes.
- Added actual `trycloudflare.com` URL parsing, ignored public-only runtime metadata, lifecycle invalidation, config-conflict warnings, loopback-only origin validation, and a hard block on Oracle port 1521.
- Added shared local/remote MCP validators covering initialize/protocol, the 16-tool contract, `health_check`, a bounded market-data tool, auth rejection, HTTPS/DNS/TLS, response-size bounds, and obvious secret leakage. Existing validator names remain compatibility entry points.
- Preserved the existing stateless Streamable HTTP JSON response mode, bearer/OAuth implementation, Host/Origin checks, limits, read-only Oracle access, and universal tool contracts. Public no-auth stays disabled unless explicitly enabled for a short test.
- Added current official Cloudflare limitations and documentation-verified ChatGPT, Claude, Gemini API, and Grok compatibility notes. No vendor account or live public tunnel was claimed as tested when `cloudflared` was unavailable.

### Rollback

Restore modified files from `runtime/backups/2026-09-18_061550_v2026-09-18-cloudflare-quick-tunnel` and remove the additive Quick Tunnel modules, scripts, tests, and docs. No Flask API, frontend, Oracle schema/data, router, or port-forward rollback is required.

## 2026-09-17 - Secure local and remote vendor-neutral MCP

- Upgraded the existing read-only MCP adapter without adding Flask endpoints or duplicating price-action/market-data owners. The same 16-tool core now supports local stdio, local Streamable HTTP, secure outbound-tunnel, and private reverse-proxy profiles.
- Added fail-closed bearer and external OAuth/OIDC resource-server modes, MCP protected-resource metadata, per-tool read scopes, Host/Origin allowlists, trusted-proxy CIDRs, rate/concurrency/body/response/time limits, Oracle circuit breaking, safe audit fields, and exchange/tool/symbol egress policy.
- Added additive `readiness_check` and `explain_level` tools; retained all prior tool names and read-only annotations. No arbitrary SQL, Oracle write operation, brokerage, or order-placement tool exists.
- Added local/remote endpoint validators, Windows launch/test wrappers, secure tunnel/reverse-proxy/OAuth architecture docs, vendor-specific setup docs, and a current documentation-verified compatibility matrix.
- Kept the MCP SDK in `.venv-mcp`; the environment inherits the application's existing Oracle/market-data packages while locally overriding MCP/Pydantic/Uvicorn packages, leaving the Flask runtime dependencies unchanged.

### Validation

- Focused MCP suite: 11 passed.
- Ruff over MCP modules, validators, and focused tests: passed.
- Bandit over the MCP server and endpoint validators: passed.
- The normal application Python environment now skips MCP-only tests when the isolated MCP dependency set is absent, so backend test collection is not coupled to `.venv-mcp`.
- In-memory MCP validation: 16 deterministic tools and `health_check` passed.
- Stdio subprocess smoke: protocol `2026-07-28`, 16 tools, health tool discovered.
- Local Streamable HTTP smoke on a temporary fallback port passed protocol negotiation, tool listing, Oracle 19c readiness (`CVINGPDB`, sanitized version), invalid Host rejection, and invalid Origin rejection.
- Local bearer smoke on a temporary fallback port returned 401 for anonymous access; authenticated validation passed with the same 16 tools and Oracle readiness.
- The former default port was already held by an unrelated Python listener returning 404 for `/healthz`; that process was not modified. No remote DNS/tunnel/IdP/vendor-account connection was available for live testing.
- The aggregate enterprise validator was not a release-green signal: its frontend phase could not read the Vite configuration under the active filesystem sandbox, and a long full-backend rerun was stopped after unrelated legacy failures appeared. The focused MCP, duplicate-route, compile, lint, security, stdio, local HTTP, and bearer checks above are the completed evidence for this change.

### Rollback

Restore existing files from `runtime/backups/2026-09-17_163945_v2026-09-17-mcp-secure-multiai`, `runtime/backups/2026-09-17_171516_v2026-09-17-mcp-runtime-deps`, and `runtime/backups/2026-09-17_204011_v2026-09-17-mcp-secure-multiai-memory`; remove the additive MCP docs, scripts, tests, `auth.py`, and `policy.py`. No Oracle or Flask rollback is required.

## 2026-09-17 - MCP validation completion

- Completed direct MCP SDK discovery in the isolated `.venv-mcp` environment and made `scripts/validate_mcp.py` runnable by file path from the repository root.
- Removed one unused MCP service import and documented the intentional optional-dependency import order in the MCP contract test so Ruff can validate the complete MCP change set.
- Eliminated the full-suite `cache.estimate_size_bytes` collection collision by removing test-owned `cache` stubs from `sys.modules` after their owning services are imported; production cache imports and behavior remain unchanged.
- No Flask API route, Oracle schema/data, frontend contract, authentication flow, trading calculation, or immutable market-data flow changed.

### Rollback

Restore the validation files and `CHANGELOG.md` from `runtime/backups/2026-09-17_155623_v2026_09_17-mcp-validation-fixes/`; restore the cache-test isolation changes from `runtime/backups/2026-09-17_110537_v2026_09_17-validation-cache-pollution-root/`.

## 2026-09-17 - Dashboard Tailwind white-screen fix

- Fixed the production Tailwind configuration export for the frontend ESM package so Vite/Tailwind scans `frontend/index.html` and `frontend/src/**/*.{ts,tsx}` again.
- Restored generated layout and sizing utilities such as `inline-flex`, `h-4`, `w-4`, and dashboard grid classes; without them, the header brand SVG expanded to the viewport and covered the rendered dashboard.
- Added `scripts/validate_frontend_bundle.py` to the standard `npm.cmd run build` path. Future builds now fail closed when core Tailwind layout/sizing selectors are absent, preventing another purged stylesheet from being published.
- No React route, API contract, Oracle schema/data, authentication behavior, dependency, or immutable market-data flow changed.

### Validation

- `npm.cmd run typecheck` from `frontend`: passed.
- Tailwind CLI with `frontend/tailwind.config.js`: passed and emitted a 311,082-byte stylesheet containing `h-8`, `w-8`, `inline-flex`, and `min-h-screen`; the broken bundle contained only 12,758 bytes and omitted those utilities.
- Config-free Vite production build with the repository React plugin and alias: passed; 734 modules transformed, with a 311.27 kB stylesheet emitted.
- Live `/app/dashboard`, `/react-assets/index-FGiVZHNk.js`, and `/react-assets/index-l9Qm2eg-.css`: HTTP 200 with `no-cache` headers.
- Authenticated Chromium verification: `Nifty50 Top 5 Gainers` is visible, the header SVG is 16 by 16 pixels instead of 1366 by 1366, and no console or page errors were recorded.
- Populated authenticated Chromium verification: current gainers, losers, and six breadth rows rendered from the live API with the corrected 311.27 kB stylesheet and no console errors.
- Full React route visual audit: all 65 registered `/app/...` and `/fundamental...` pages returned HTTP 200, mounted non-empty content, and had zero viewport-sized SVG/image overlays. `/app/strategy` was rechecked independently after the audit token triggered an unrelated session redirect and passed with its dashboard heading visible and no page errors.
- `npm.cmd run validate:bundle`: passed against the Flask-served production bundle.
- Focused dashboard migration tests loaded through the config-free runner: 3 passed and 2 pre-existing content assertions failed (`CvingTrade25X AI` text and an expected `Nifty500` breadth fallback); neither assertion covers the Tailwind configuration or brand sizing fix.

### Rollback

Restore `frontend/tailwind.config.js` and `CHANGELOG.md` from `runtime/backups/2026-09-17_111538_v2026-09-17-dashboard-tailwind-config/`, restore `frontend/package.json` from `runtime/backups/2026-09-17_154315_v2026-09-17-dashboard-tailwind-build-guard/`, remove `scripts/validate_frontend_bundle.py`, then rebuild `frontend/dist`. No backend or database rollback is required.

## 2026-09-17 - Historical Data compact S.NO table layout

- Removed the separate blank selection column and placed the select-all and row checkboxes inside the leftmost `S.NO` column.
- Assigned compact fixed column widths so the full desktop table fits cleanly, while retaining touch and trackpad horizontal access on narrow screens.
- Hid the native horizontal scrollbar for this table only; other application tables retain their existing overflow behavior.
- No API, Oracle schema, stored data, authentication contract, or market-data flow changed.

### Validation

- `npm.cmd run typecheck` from `frontend`: passed.
- Focused config-free Vitest run for `tests\historicalDataPage.test.tsx`: 1 passed.
- Config-free Vite production build with the repository Tailwind configuration loaded explicitly: passed; 734 modules transformed and the complete 311.27 kB stylesheet was emitted.

### Rollback

Restore the edited files from `runtime/backups/2026-09-17_061521_v2026-09-17-historical-sno-scrollbar/` and rebuild `frontend/dist`. No database rollback is required.

## 2026-09-17 - Historical Data three-file export bundle

- Changed the per-symbol Historical Data download to one ZIP archive containing exactly three files: CSV, JSON, and TXT.
- All three files are generated from the same validated Oracle query and share the fields `s.no`, `symbol`, `trade_date`, `open`, `high`, `low`, and `close`; the existing standalone CSV endpoint remains backward compatible.
- Updated the table column, accessible download label, generated filename, and top-right toast to identify the combined CSV/JSON/TXT download.
- No Oracle schema, stored data, authentication contract, dependency, or immutable market-data flow changed.

### Validation

- `python -m pytest backend\tests\test_historical_data_service.py backend\tests\test_historical_data_routes.py -q`: 17 passed.
- `python -m compileall backend\routes\historical_data.py backend\services\historical_data_service.py`: passed.
- `npm.cmd run typecheck` from `frontend`: passed.
- Focused config-free Vitest run: 1 passed.
- `python scripts\scan_api_duplicates.py --write-catalog docs\api-catalog.md`: passed with 196 routes and 0 exact duplicates.

### Rollback

Restore the edited files from `runtime/backups/2026-09-17_053446_v2026-09-17-historical-three-file-bundle/`, rebuild `frontend/dist`, and restart Flask. No database rollback is required.

## 2026-09-17 - Historical Data CSV downloads, complete pagination, and dark toolbar

- Added an authenticated per-symbol CSV download on `/app/database/historical-data` using the existing Historical Data Flask blueprint and Oracle view allowlist. Each file contains all available rows in ascending trade-date order with the exact header `s.no,symbol,trade_date,open,high,low,close`.
- Added a `CSV Download` table column with a per-row down-arrow action, pending-state protection, and top-right success/failure toast feedback.
- Changed the summary request from a client-capped 500-row snapshot to real server pagination at 25 symbols per page, so every filtered symbol remains reachable while preserving the existing API contract.
- Added page-scoped dark-mode styling for the Historical Data strategy toolbar; other pages retain their existing shared toolbar palette.
- Added backend CSV route coverage and frontend rendering assertions. No Oracle schema, data, dependency, authentication, or immutable market-data flow changed.

### Validation

- `python -m pytest backend\tests\test_historical_data_service.py backend\tests\test_historical_data_routes.py -q`: 16 passed.
- `python -m compileall backend\routes\historical_data.py backend\services\historical_data_service.py`: passed.
- `npm.cmd run typecheck` from `frontend`: passed.
- `python scripts\scan_api_duplicates.py --write-catalog docs\api-catalog.md`: passed with 195 routes and 0 exact duplicates.
- Focused Vitest through the repository-established config-free runner: 1 passed.
- Config-free Vite production build with the repository Tailwind configuration loaded explicitly: passed; 734 modules transformed and a 309.94 kB stylesheet was emitted.
- Live `http://127.0.0.1:5055/api/health` and `/app/database/historical-data`: HTTP 200; the served HTML references the new `index-kTx2y6wc.js` and `index-7v_-kYnH.css` assets.
- `python scripts\enterprise_validate.py` was stopped after more than four minutes without output; its required duplicate-API subcheck was run separately and passed. Authenticated browser click validation could not start because the Windows UI helper timed out twice.

### Rollback

Restore the edited files from `runtime/backups/2026-09-16_213613_v2026-09-16-historical-csv-pagination-dark-toolbar/`, rebuild `frontend/dist`, and restart Flask. No database rollback is required.

## 2026-09-01 - Dashboard Dark Mode Background and Card Styles

- Fixed `/app/dashboard` dark mode background color and container styling so that when dark mode is enabled, the page background and KPI card containers render in dark theme instead of light/white.
- Replaced hardcoded light radial-gradient Tailwind utility on the dashboard container with theme-aware gradient classes, and expanded dark mode CSS rules across `:root[data-theme="dark"]`, `html.dark`, `body.dark`, and `.dashboard-react-page--dark`.
- Rebuilt frontend production bundle (`dist/index.html` and assets).

## 2026-08-24 - Dark login autofill fields

- Keep Chrome-autofilled username and password fields dark with readable text when the application dark theme is active.
- Scope the browser autofill override to centralized login credential inputs; authentication behavior and API contracts are unchanged.

## v185-tradesetup-bounded-progressive-loading - 2026-08-17 08:26:00 IST

## 2026-08-20 - Trade SetUp manual S&R actions

Added Trade SetUp S&R-tab Edit and Insert buttons that reuse the existing Price Action manual S&R API and save payload contract. Price Action page CRUD and database logic are unchanged.

## 2026-08-20 - Trade SetUp S&R data presentation

Trade SetUp now reads the existing database-backed manual Price Action S&R rows first, displays `No Data` when no level exists, suppresses source failure text in cells, and shows selected-symbol S&R, evidence, targets, and setup values in the analysis panel.

Fixed `/app/tradesetup` request fanout that could exhaust the Flask development server and leave Watchlist data plus `/api/health` unresponsive. The latest candle and symbol metadata remain the immediate first-paint sources. Optional Sector Wise, Strong Technicals, S&R, Delivery, and target-history requests now run sequentially with a Watchlist-specific 15-second ceiling, while the existing shared Volume request remains deduplicated. Selecting another symbol aborts the remaining stale enrichment chain. Existing endpoints, response contracts, browser watchlist storage, Oracle objects, and market-data flow are unchanged.

### Root cause

- Every selected symbol launched all long-running optional requests concurrently, using shared endpoint timeouts of 60 to 150 seconds.
- Per-symbol in-flight protection did not cancel enrichment for a previously selected symbol, so rapid selection changes accumulated abandoned browser connections and Flask request threads.

### Files changed

- `frontend/src/pages/watchlist/WatchlistPage.tsx`
- `frontend/src/services/api/watchlistData.ts`
- `frontend/src/services/api/technicalApi.ts`
- `frontend/src/api/bars.ts`
- `frontend/tests/watchlistData.test.ts`
- `frontend/dist/index.html`
- `frontend/dist/react-assets/index-S4OOlfqd.js`
- `CHANGELOG.md`

### 2026-08-20 - Trade SetUp immediate rows

- Keep all saved Watchlist rows visible across cards and table tabs while the selected symbol refreshes in the background.
- Present unavailable optional sources as a neutral UI state and retain cached/placeholder row data without exposing request error text.

### Validation

- Focused Vitest run: 21 passed across `watchlistPage.test.tsx` and `watchlistData.test.ts`.
- `npm.cmd run typecheck`: passed.
- Equivalent Vite production build through the JavaScript API with `configFile: false`: passed; 734 modules transformed. The repository Tailwind configuration was loaded explicitly because the managed Windows host cannot let Vite scan the parent user directory.
- Repository stop/start scripts recovered the exhausted listener; the launcher health gate passed.
- Three consecutive live `/api/health` checks returned Oracle `db=up` in 465 ms, 205 ms, and 161 ms. Socket inspection showed one listener, seven `TIME_WAIT` connections, and no `CLOSE_WAIT` connections.
- Headless Chrome production-bundle check rendered a populated TCS Watchlist row with the normal Tailwind layout, no console errors, and maximum optional enrichment concurrency of one.

### Rollback

- Restore the files from `runtime/backups/2026-08-17_081827_v2026_08_17-tradesetup-load-fix` and rebuild the React bundle.

## v184-tradesetup-sector-target-duration - 2026-08-14 09:32:12 IST

Fixed Trade SetUp Watchlist rows that displayed the source-status word `Loaded` instead of Sector or Sector Trend data, and added progressive OHLCV-based trading-day estimates for T1, T2, and T3. Missing values now show an honest loading, failed, or unavailable state; a successful source status can no longer masquerade as row data. Target durations reuse `/api/bars` history, calculate the median number of subsequent trading candles historically needed to reach each target ratio, require at least three observations, and cap each observation at 126 trading days. The existing fast one-bar first paint remains unchanged while the 800-bar history request runs in the background.

The exact Sector Wise symbol lookup now tolerates a date mismatch between the last published stock snapshot and the current parent sector snapshot. It keeps the published stock-to-sector identity, overlays current parent trend fields without blanking usable fallback values, and returns explicit stale metadata. The full Sector Wise page retains its existing strict atomic snapshot-date check. No endpoint, request shape, database schema, market-data flow, or dependency changed.

### Root cause

- `targetDays` was hard-coded to `[0, 0, 0]`, so the UI could never display calculated trading-day durations.
- Missing table cells rendered a combined source status whose `LOADED` state could hide another required source's failure and display `Loaded` as if it were Sector or Sector Trend data.
- The published stock snapshot was dated `2026-08-12` while its parent sector snapshot was dated `2026-08-13`; the exact-symbol endpoint rejected the mismatch even though WESTLIFE's published sector identity was available.

### Files changed

- `frontend/src/services/api/watchlistData.ts`
- `frontend/src/pages/watchlist/WatchlistPage.tsx`
- `frontend/tests/watchlistData.test.ts`
- `frontend/tests/watchlistPage.test.tsx`
- `backend/services/sector_rotation_v3_stock_service.py`
- `backend/tests/test_sector_rotation_v3_stock_service.py`
- `docs/api-catalog.md`
- `frontend/dist/index.html`
- `frontend/dist/react-assets/index-CBs9FLMq.js`
- `frontend/dist/react-assets/index-WCHXtfaP.css`
- `CHANGELOG.md`

### Validation

- `python -m pytest tests\test_sector_rotation_v3_stock_service.py tests\test_sector_rotation_route.py::test_api_sector_wise_symbol_returns_exact_published_row -q`: 15 passed.
- `python -m pytest tests\test_sector_rotation_v3_stock_service.py tests\test_sector_rotation_route.py -q`: 39 passed; one unrelated overview timing assertion measured 1125 ms against its 1000 ms threshold. The isolated timing test passed immediately afterward.
- Direct real-snapshot WESTLIFE service probe: HTTP/service status 200; `sectorName=Restaurants`; `parentSectorPhase=DATA_WEAK`; `trend=Uptrend`; stale stock date `2026-08-12` and current parent date `2026-08-13` are disclosed.
- `node .\node_modules\typescript\bin\tsc --noEmit --pretty false --incremental false`: passed.
- Equivalent Vite production build through the JavaScript API with `configFile: false`: passed; 734 modules transformed and the Flask-served `frontend/dist` bundle was updated. This bypassed only the restricted host's parent-directory config scan and retained the repository's React plugin, alias, asset directory, and `emptyOutDir: false` settings.
- Live `http://127.0.0.1:5055/app/tradesetup`: HTTP 200 and references the new `index-CBs9FLMq.js` / `index-WCHXtfaP.css` bundle; the JavaScript contains the new OHLCV History and unavailable-state labels.
- Live `GET /api/sectors/sector-wise-symbol?symbol=WESTLIFE`: HTTP 200 with `sectorName=Restaurants`, `parentSectorPhase=DATA_WEAK`, `trend=Uptrend`, and explicit stale/current snapshot dates.
- Live `GET /api/bars?symbol=WESTLIFE&tf=1D&limit=800`: HTTP 200 with 800 usable candles; the implemented estimator returns T1/T2/T3 durations of 8, 23, and 38 trading days for the current 5/10/15 percent fallback targets.
- `python scripts\scan_api_duplicates.py --write-catalog docs\api-catalog.md`: passed with 194 routes and 0 exact duplicates.
- Focused Vitest through the normal config loader was attempted but Vite/esbuild could not read the restricted host parent path and stopped before loading test code: `Cannot read directory "../../../..": Access is denied` and `Could not resolve ... frontend\vite.config.ts`.
- The existing stock-snapshot refresh was attempted but Oracle rejected the repository sync procedure with `ORA-02291` on `NSE_SYM_SECTOR_FK`; publication remained atomic and the prior stock snapshot was preserved.

### Rollback

Restore the edited application/test files and `CHANGELOG.md` from `runtime/backups/2026-08-14_065642_v181-tradesetup-sector-target-duration/` and `runtime/backups/2026-08-14_091233_v181-tradesetup-sector-target-duration/`, restore `docs/api-catalog.md` from `runtime/backups/2026-08-14_092827_v1/`, remove the two new hashed v184 assets, then rebuild the prior React source (or repoint `frontend/dist/index.html` to the retained prior hashed assets) and restart Flask. No Oracle schema or stored-data rollback is required.

## v183-bounded-flask-memory-storage - 2026-08-14 09:18:00 IST

Bounded Flask private-memory retention without removing the snapshot-first performance path. The shared TTL cache now proactively sweeps expired entries, supports optional byte budgets, rejects oversized values, evicts least-recently-used values, and exposes value-free statistics. The sector row, historical-summary, holdings-list, holdings-live-quote, and MCAP lookup caches now have explicit item and RAM ceilings, so request-specific payloads cannot grow for the entire Flask process lifetime; disk snapshots remain enabled for fast reloads. Completed NSE MCAP/FFMC/Delivery jobs are limited to the newest four per job type, and completed FYERS jobs to the newest six, while active jobs are never evicted and persisted Oracle job history remains available.

### Files changed

- `backend/cache.py`
- `backend/services/sector_cache_service.py`
- `backend/services/sector_stock_cache_service.py`
- `backend/services/job_memory_policy.py`
- `backend/services/historical_data_service.py`
- `backend/services/fyers_holdings_service.py`
- `backend/services/nse_mcap_service.py`
- `backend/services/nse_ffmc_service.py`
- `backend/services/nse_delivery_service.py`
- `backend/services/marketdata_service.py`
- `backend/tests/test_memory_cache_policy.py`
- `CHANGELOG.md`

### Configuration

- `SECTOR_CACHE_MAX_ITEMS` (default `48`)
- `SECTOR_CACHE_MAX_MEMORY_MB` (default `96`)
- `SECTOR_STOCK_CACHE_MAX_ITEMS` (default `24`)
- `SECTOR_STOCK_CACHE_MAX_MEMORY_MB` (default `128`)
- `NSE_JOB_MAX_RETAINED` (default `4`, per NSE job type)
- `FYERS_JOB_MAX_RETAINED` (default `6`)
- `HISTORICAL_SUMMARY_CACHE_MAX_ITEMS` / `HISTORICAL_SUMMARY_CACHE_MAX_MEMORY_MB` (defaults `128` / `64`)
- `FYERS_HOLDINGS_LIST_CACHE_MAX_ITEMS` / `FYERS_HOLDINGS_LIST_CACHE_MAX_MEMORY_MB` (defaults `64` / `32`)
- `FYERS_HOLDINGS_LIVE_QUOTES_CACHE_MAX_ITEMS` / `FYERS_HOLDINGS_LIVE_QUOTES_CACHE_MAX_MEMORY_MB` (defaults `16` / `16`)
- `NSE_MCAP_LOOKUP_CACHE_MAX_ITEMS` / `NSE_MCAP_LOOKUP_CACHE_MAX_MEMORY_MB` (defaults `64` / `64`)

### Validation

- `python -m pytest backend\tests\test_memory_cache_policy.py backend\tests\test_cache_refresh.py backend\tests\test_sector_rotation_route.py::test_api_sector_overview_returns_payload_snapshot_before_oracle -q`: 8 passed.
- `python -m pytest backend\tests\test_marketdata_fyers_proxy.py backend\tests\test_marketdata_fyers_job_progress.py -q`: 69 passed.
- Final combined affected-cache regression command: 170 passed and 1 intentionally deselected environment-sensitive SQL assertion.
- Historical, holdings, and MCAP cache regressions: 100 passed and 1 pre-existing environment-sensitive historical SQL assertion failed because the configured `CVING_APP.` schema prefix was present.
- Broader sector/NSE/FYERS regression selection: 188 passed and 4 failed. The isolated sector response-time case passed on rerun; the remaining three failures are pre-existing FFMC manual-processing expectations outside the changed cleanup function.
- Focused Python compilation completed successfully for every modified backend module.
- `python scripts\scan_api_duplicates.py`: passed with routes=194 and exact_duplicates=0.

### Rollback

Restore the eight existing files from `runtime/backups/2026-08-14_090602_v183/` and the two additional services from `runtime/backups/2026-08-14_093504_v183/`, remove `backend/services/job_memory_policy.py` and `backend/tests/test_memory_cache_policy.py`, then restart Flask. No Oracle schema, stored data, API contract, frontend build, or dependency rollback is required.

## v182-global-poller-refresh-performance - 2026-08-14 06:44:00 IST

Fixed application-wide page refresh slowdown caused by `NseJobGlobalPoller` starting five status requests every five seconds on every mounted route, including hidden/background tabs. The global notifier now runs only one completed polling cycle at a time, aborts requests after ten seconds, backs off to 30 seconds while jobs are idle, keeps the existing five-second cadence only while a visible job is active, and suppresses requests from hidden tabs. Existing status APIs, response contracts, authentication, Oracle data, job execution, and notification text remain unchanged.

### Files changed

- `frontend/src/components/app/NseJobGlobalPoller.tsx`
- `frontend/tests/nseJobGlobalPoller.test.ts`
- `CHANGELOG.md`

### Validation

- `npm.cmd run test -- tests\nseJobGlobalPoller.test.ts` from `frontend`: 6 passed.
- `npm.cmd run typecheck` from `frontend`: passed.
- `npm.cmd run build` from `frontend`: passed; Flask now serves `react-assets/index-Bi7o8pAe.js`, which contains the bounded `jobs/latest?tail=20` global poll requests.
- Standard hidden Flask restart passed its `/api/health` readiness gate. Five repeated health probes returned HTTP 200 in 0.049-0.118 seconds.
- Served-route timing improved from 2.885 seconds to 0.266 seconds for `/app/tradesetup`; `/api/automation/nse-marketdata/status` improved from 4.648 seconds to 0.087 seconds. The restarted Flask process dropped from about 9.2 GB to about 1.0 GB private memory.
- `python scripts\scan_api_duplicates.py`: passed with routes=194 and exact_duplicates=0.
- Full `npm.cmd run test`: 285 passed and 14 failed in 9 unrelated legacy/header/adapter regression files; the changed global-poller test file passed all 6 tests.

### Rollback

Restore the three files from `runtime/backups/2026-08-14_063710_v182-global-poller-refresh-performance/`, rebuild `frontend/dist`, and restart Flask. No backend, API, Oracle, market-data, or schema rollback is required.

## v181-agents-md-tradesetup-watchlist - 2026-08-14 06:23:00 IST

Updated `AGENTS.md` with repo-backed Trade SetUp Watchlist guardrails. The new section documents the `/app/tradesetup` React ownership files, no-duplicate-route/API rule, tested symbol-control order, existing-source hydration flow, saved-symbol/session snapshot keys, selected-symbol background refresh behavior, Overview-only column presentation caution, and focused frontend validation commands. No source code, API contract, backend, Oracle, or dependency changes were made.

### Files changed

- `AGENTS.md`
- `CHANGELOG.md`

### Evidence

- `frontend/src/App.tsx` maps `/app/tradesetup` and `/tradesetup` to `WatchlistPage`.
- `frontend/src/components/navigation/CvingLegacyHeader.tsx` exposes the `Watchlist` primary item and `Trade SetUp` dropdown item.
- `frontend/src/pages/watchlist/WatchlistPage.tsx` owns saved-symbol storage, session row snapshots, selected-symbol hydration, and the table UI.
- `frontend/src/services/api/watchlistData.ts` composes existing bars, symbols, technical, Sector Wise, S&R, volume, and delivery sources.
- `frontend/tests/watchlistPage.test.tsx` and `frontend/tests/watchlistData.test.ts` cover route/header behavior, no `/api/watchlist`, symbol order, progressive hydration, exact alias matching, and source-state handling.

### Validation

- `python scripts\scan_api_duplicates.py`: passed with routes=194 and exact_duplicates=0.
- `python scripts\enterprise_validate.py`: timed out after 300 seconds before producing terminal output.

### Rollback

Restore `AGENTS.md` and `CHANGELOG.md` from `runtime/backups/2026-08-14_062348_v181-agents-md-tradesetup-watchlist/`. No build, backend, API, Oracle, or data rollback is required.

## v173-watchlist-selection-hydration - 2026-08-13 10:58:00 IST

Fixed blank Trade SetUp tabs after choosing a saved symbol. The top Main NSE symbols control now loads the existing NSE symbol universe; selecting a symbol and choosing `+` adds it to the separate My Watchlist symbols list. Selecting a saved symbol explicitly rehydrates it and displays that selected row in every tab. The Watchlist S&R call uses the existing exact `symbols=` filter, avoiding a paginated search result that can omit the selected stock. Shared row matching now recognizes the established `symbol`, `stock`, `ticker`, and `code` aliases across Technical, S&R, and Delivery response rows. Sector Wise selected-symbol reads use a 60-second existing-client timeout for cold snapshots.

### Files changed

- `frontend/src/pages/watchlist/WatchlistPage.tsx`
- `frontend/src/api/symbols.ts`
- `frontend/src/services/api/sectorApi.ts`
- `frontend/src/services/api/watchlistData.ts`
- `frontend/src/services/api/technicalApi.ts`
- `frontend/tests/watchlistData.test.ts`
- `CHANGELOG.md`

### Validation

- `npm.cmd run test -- tests\watchlistData.test.ts tests\watchlistPage.test.tsx` from `frontend`: 13 passed.
- `npm.cmd run typecheck` from `frontend`: passed.
- `npm.cmd run test -- tests\watchlistData.test.ts tests\watchlistPage.test.tsx` from `frontend`: 13 passed after final main-symbol/dropdown coverage.

### Rollback

Restore the files from `runtime/backups/2026-08-13_105833_v173-watchlist-selection-hydration/`, `runtime/backups/2026-08-13_110900_v173-watchlist-selection-hydration/`, `runtime/backups/2026-08-13_111532_v173-watchlist-selection-hydration/`, and `runtime/backups/2026-08-13_111729_v173-watchlist-selection-hydration/`, then rebuild `frontend/dist`. No backend, API contract, Oracle, or saved-symbol rollback is required.

## v172-watchlist-sector-toolbar - 2026-08-13 10:25:00 IST

Added the existing Sector Rotation `StrategyToolbar` to the top of the Trade SetUp Watchlist, immediately below the shared navigation and before the page title. The toolbar retains Live, Search Card, filtered Total, LTC_DATE, Last refreshed, Load/API/DB metadata, and Refresh. `Download TXT` is intentionally omitted by leaving the existing optional download action unset. Search filters the visible Watchlist cards/rows across symbol and market/setup text, while Live and Refresh rehydrate the saved symbols through the existing data composition flow.

### Files changed

- `frontend/src/pages/watchlist/WatchlistPage.tsx`
- `frontend/tests/watchlistPage.test.tsx`
- `CHANGELOG.md`

### Validation

- `npm.cmd run test -- tests\watchlistPage.test.tsx` from `frontend`: 4 passed.
- `npm.cmd run typecheck` from `frontend`: passed.
- `npm.cmd run build` from `frontend`: passed (734 modules transformed); existing browserslist-age and large-chunk advisories remain non-blocking.

### Rollback

Restore the three files from `runtime/backups/2026-08-13_102517_v172-watchlist-sector-toolbar/`, then rebuild `frontend/dist`. No backend, API, Oracle, or saved-symbol rollback is required.

## v171-watchlist-source-hydration-hardening - 2026-08-13 09:55:00 IST

Hardened the existing-source hydration used by the Trade SetUp Watchlist. Exact Sector Wise symbol reads now reuse a bounded, snapshot-identity-aware index and include the same staging/Overview supplementation used by the Sector Wise page. Empty refreshing Volume placeholders are no longer cached; one shared request sequence retries on a bounded 1s/2.5s/5s schedule and caches only a completed payload. No endpoint, response contract, dependency, Oracle write, or market-data flow changed.

### Files changed

- `backend/services/sector_rotation_v3_stock_service.py`
- `backend/tests/test_sector_rotation_v3_stock_service.py`
- `frontend/src/services/api/watchlistData.ts`
- `frontend/tests/watchlistData.test.ts`
- `CHANGELOG.md`

### Validation

- `python -m pytest tests\test_sector_rotation_v3_stock_service.py -q` from `backend`: 13 passed.
- `npm.cmd run test -- tests\watchlistPage.test.tsx tests\watchlistData.test.ts` from `frontend`: 12 passed.
- `npm.cmd run typecheck` from `frontend`: passed.
- `npm.cmd run build` from `frontend`: passed (734 modules transformed); existing browserslist-age and large-chunk advisories remain non-blocking.

### Rollback

Restore the backend files from `runtime/backups/2026-08-13_092352_v169-watchlist-sector-symbol-cache/` and the frontend files from `runtime/backups/2026-08-13_092330_v1/`, then rebuild `frontend/dist`. No Oracle or data rollback is required.

## v170-watchlist-aligned-blue-green-ui - 2026-08-13 09:13:00 IST

Aligned the Trade SetUp symbol controls into one deterministic desktop row in the requested order: Add Symbol input, `+`, All Symbols, Setup State, and Reset filter. The helper/status message now owns a separate full-width row, preventing it from pulling the dropdowns downward. The add action uses green; focus, selected rows/tabs, resistance/risk treatments, remove, and reset actions now use blue/sky styling. All red/rose utility classes were removed from the Trade SetUp Watchlist page while preserving its values and behavior.

### Files changed

- `frontend/src/pages/watchlist/WatchlistPage.tsx`
- `frontend/tests/watchlistPage.test.tsx`
- `CHANGELOG.md`

### Validation

- `npm.cmd run test -- tests\watchlistPage.test.tsx tests\watchlistData.test.ts` from `frontend`: 12 passed after the final hydration hardening.
- `npm.cmd run typecheck` from `frontend`: passed.
- `npm.cmd run build` from `frontend`: passed (734 modules transformed).
- Static rendered-markup coverage verifies desktop grid order, full-width helper row, green add button, and absence of red/rose classes on this page.

### Rollback

Restore the three files from `runtime/backups/2026-08-13_091305_v170-watchlist-aligned-blue-green-ui/`, then rebuild `frontend/dist`. No backend, API, Oracle, or saved-symbol data rollback is required.

## v169-watchlist-cloned-source-tabs - 2026-08-13 08:24:00 IST

Completed the Trade SetUp Watchlist source composition and manual-symbol controls. The Add Symbol area now occupies one half of the desktop control card, while the other half provides an `All symbols` selector, Setup State, and Reset filter. Every validated symbol added with `+` remains normalized, persisted, selected, hydrated, and immediately available in the selector and table. The four existing tabs now compose the established application owners: an exact read-only Sector Wise V3 snapshot lookup supplies Identity/Market values, the Volume and Delivery pages supply confirmation values, and the existing `/api/sr-levels` result supplies the merged manual plus OHLCV support/resistance ladder. S&R now retains generated touch/breach evidence for converged manual levels and publishes additive strongest support/resistance fields without changing the established manual-first ladder order or legacy fields. No Oracle schema, dependency, authentication flow, market-data pipeline, destructive operation, or legacy UI was added.

### Files changed

- `backend/routes/sector_rotation.py`
- `backend/services/sector_rotation_v3_stock_service.py`
- `backend/sr_levels.py`
- `backend/tests/test_sector_rotation_route.py`
- `backend/tests/test_sector_rotation_v3_stock_service.py`
- `backend/tests/test_sr_levels_generation.py`
- `frontend/src/pages/watchlist/WatchlistPage.tsx`
- `frontend/src/services/api/sectorApi.ts`
- `frontend/src/services/api/watchlistData.ts`
- `frontend/tests/watchlistData.test.ts`
- `frontend/tests/watchlistPage.test.tsx`
- `docs/api-catalog.md`
- `CHANGELOG.md`

### Validation

- `python -m pytest tests\test_sr_levels_generation.py tests\test_sector_rotation_v3_stock_service.py tests\test_sector_rotation_route.py -q` from `backend`: 49 passed.
- `npm.cmd run test -- tests\watchlistPage.test.tsx tests\watchlistData.test.ts` from `frontend`: 9 passed.
- `npm.cmd run typecheck` from `frontend`: passed.
- `npm.cmd run build` from `frontend`: passed (734 modules transformed); the existing browserslist-age and large-chunk advisories remain non-blocking.
- `python scripts\scan_api_duplicates.py --write-catalog docs\api-catalog.md`: passed with 194 routes, 0 exact duplicates, and 21 similar paths.
- Live `GET /api/sectors/sector-wise-symbol?symbol=TCS`: HTTP 200 with exact symbol `TCS`, sector `IT`, and source `V3_ATOMIC_STOCK_SNAPSHOT` after the standard local server restart.
- Browser automation confirmed the protected route redirects to centralized login when no authenticated session is supplied; authenticated visual inspection was not bypassed.

### Rollback

Restore the files from `runtime/backups/2026-08-13_074838_v169-watchlist-cloned-source-tabs/`, `runtime/backups/2026-08-13_075903_v169-watchlist-cloned-source-tabs/`, and `runtime/backups/2026-08-13_080206_v169-watchlist-cloned-source-tabs/`, then rebuild `frontend/dist`. No Oracle or data rollback is required. Browser key `ct_watchlist_strategy_symbols_v1` may be left intact or cleared manually if saved Watchlist membership should also be reset.

## v168-watchlist-progressive-hydration - 2026-08-12 21:10:00 IST

Fixed the remaining Watchlist add and loading failures. NSE validation now accepts either an exact existing symbol-directory match or existing NSE OHLCV bars, duplicate `+` submissions refresh the saved symbol, hydration is deduplicated per symbol, and fast bars/metadata are committed before slow Strong Technical, S&R, and Delivery sources finish. Each enrichment source updates the same row independently, so a slow optional API can no longer block visible LTP and entry-range data. No new API, backend route, Oracle object, dependency, or legacy HTML was added.

### Files changed

- `frontend/src/services/api/watchlistData.ts`
- `frontend/src/pages/watchlist/WatchlistPage.tsx`
- `CHANGELOG.md`

### Rollback

Restore the files from `runtime/backups/2026-08-12_210723_v1/` and rebuild `frontend/dist`. No backend or database rollback is required.

## v167-watchlist-existing-data-hydration - 2026-08-12 20:36:00 IST

Fixed manually added Watchlist symbols rendering placeholder-only rows. The React Watchlist now composes the existing chart bars, Strong Technicals, S&R Levels, Delivery, and NSE symbol-search APIs with exact normalized-symbol matching and partial-source failure tolerance. Market/setup values, support/resistance ladders, target prices, volume, delivery, and confidence populate when those existing sources provide them; no Watchlist endpoint, backend route, Oracle object, or duplicate calculation was added.

### Files changed

- `frontend/src/services/api/watchlistData.ts`
- `frontend/src/pages/watchlist/WatchlistPage.tsx`
- `frontend/tests/watchlistData.test.ts`
- `frontend/tests/watchlistPage.test.tsx`
- `CHANGELOG.md`

### Validation

- `npm.cmd run typecheck`: passed.
- Production build through Vite's programmatic `configFile: false` path: passed; 734 modules transformed and Flask serves the new JS/CSS assets with HTTP 200.
- `python scripts\scan_api_duplicates.py`: passed; 194 routes and zero exact duplicates.
- Runtime `/api/health`: HTTP 200 with Oracle up after restarting the hung listener with background jobs disabled.
- WESTLIFE runtime checks: Bars returned the 2026-08-28 candle, symbol lookup returned NSE/WESTLIFE, and Sector Wise returned the Restaurants row with current market/technical values.
- Focused Vitest and the standard `npm.cmd run build` config-loading step could not start because the Windows sandbox denied esbuild access while resolving `vite.config.ts`; no test assertion or source compilation failure occurred.

### Rollback

Restore the existing files from `runtime/backups/2026-08-12_203136_v1/`, remove `frontend/src/services/api/watchlistData.ts` and `frontend/tests/watchlistData.test.ts`, then rebuild `frontend/dist`. No backend, API, or Oracle rollback is required.

## v166-watchlist-table-view-tabs - 2026-08-12 20:10:00 IST

Replaced the Watchlist table's grouped header row with four actual interactive table-view tabs: Overview (`Identity · Market · Setup`), Targets, S&R Levels (`Support · Resistance`), and Confirmation (`Confirmation · Actions`). Each tab shows only its assigned column group while retaining S.No and Symbol as row context. Column labels remain ordinary table headers beneath the tabs. No API, backend, Oracle, NSE validation, symbol CRUD, or calculation behavior changed.

### Files changed

- `frontend/src/pages/watchlist/WatchlistPage.tsx`
- `frontend/src/styles.css`
- `frontend/tests/watchlistPage.test.tsx`
- `CHANGELOG.md`

### Rollback

Restore the Watchlist page, focused test, and changelog from `runtime/backups/2026-08-12_200541_v1/`, restore `frontend/src/styles.css` from `runtime/backups/2026-08-12_200617_v1/`, then rebuild `frontend/dist`. No backend, API, Oracle, or data rollback is required.

## v165-watchlist-header-tradesetup-dropdown - 2026-08-12 19:43:00 IST

Corrected the header hierarchy so `Watchlist` is the top-level dropdown between Dashboard and Sector, while `Trade SetUp` is the dropdown page entry linking to `/app/tradesetup`. The route, standalone NSE-only symbol CRUD, existing API reuse, React implementation, and backend/Oracle contracts remain unchanged.

### Files changed

- `frontend/src/components/navigation/CvingLegacyHeader.tsx`
- `frontend/tests/watchlistPage.test.tsx`
- `CHANGELOG.md`

### Rollback

Restore the files from `runtime/backups/2026-08-12_194036_v1/` and rebuild `frontend/dist`. No backend, API, Oracle, or data rollback is required.

## v164-tradesetup-nse-symbol-universe - 2026-08-12 19:28:00 IST

Removed the prototype/phase classification from the standalone Trade SetUp Watchlist. Manual CRUD now accepts the complete existing NSE symbol universe rather than a five-symbol mock catalogue: additions are validated through the existing `/api/symbols` search service, BSE-prefixed or non-NSE matches are rejected, display symbols reuse `normalizeDisplaySymbol`, and existing `/api/bars` data supplies the latest available NSE price and candle range without adding a duplicate endpoint. Unavailable technical fields remain explicitly blank/pending rather than being fabricated.

### Files changed

- `frontend/src/pages/watchlist/WatchlistPage.tsx`
- `frontend/tests/watchlistPage.test.tsx`
- `CHANGELOG.md`

### Rollback

Restore the files from `runtime/backups/2026-08-12_190843_v1/` and rebuild `frontend/dist`. No backend, API, Oracle, or market-data rollback is required.

## v163-tradesetup-watchlist-route - 2026-08-12 19:12:00 IST

Replaced the Watchlist page route `/app/watchlist` with `/app/tradesetup`. The primary header now shows `Trade SetUp` between Dashboard and Sector as a dropdown, with `Watchlist` as its submenu entry pointing to the canonical Trade SetUp route. The Watchlist workspace, manual symbol CRUD, local persistence, backend/API contracts, Oracle data, and market-data flows are unchanged.

### Files changed

- `frontend/src/App.tsx`
- `frontend/src/components/navigation/CvingLegacyHeader.tsx`
- `frontend/src/pages/watchlist/WatchlistPage.tsx`
- `frontend/tests/watchlistPage.test.tsx`
- `CHANGELOG.md`

### Rollback

Restore the files from `runtime/backups/2026-08-12_190843_v1/` and rebuild `frontend/dist`. No backend, API, Oracle, or data rollback is required.

## v162-watchlist-manual-symbol-crud - 2026-08-12 16:17:00 IST

Changed the Phase 1 `/app/watchlist` prototype from a pre-populated market universe to a user-owned manual symbol list. The page is empty by default and displays only symbols explicitly added through the `+` control beside the symbol input. Create, read, update/replace, and delete operations persist the selected symbol membership in browser local storage; shared `normalizeDisplaySymbol` handles exchange prefixes and cash-series suffixes. KPI cards, table rows, and selected-stock analysis now derive only from saved watchlist symbols. No backend route, duplicate API, database object, dependency, sector/index auto-population, or market-data flow changed.

### Files changed

- `frontend/src/pages/watchlist/WatchlistPage.tsx`
- `frontend/tests/watchlistPage.test.tsx`
- `CHANGELOG.md`

### Rollback

Restore the files from `runtime/backups/2026-08-12_160924_v1/` and rebuild `frontend/dist`. Browser key `ct_watchlist_strategy_symbols_v1` may be removed manually if saved Phase 1 membership should also be cleared. No backend, API, Oracle, or data rollback is required.

## v161-watchlist-strategy-phase-one-prototype - 2026-08-12 15:44:00 IST

Added the Phase 1 React-only Dynamic Swing-Trading Watchlist prototype at `/app/watchlist`. The primary header is now ordered `Dashboard | Watchlist | Sector`; the new protected page uses realistic mock Indian-equity data and provides watchlist KPI cards, search/setup filters, a grouped horizontally scrollable comparison table with sticky Symbol/LTP columns, target price/points/upside/trading-day estimates, strong support/resistance treatment, selected-stock analysis tabs, and links to the existing Price Action S&R workflow. No backend route, API contract, database object, market-data flow, or new dependency was added. Phase 2 backend integration remains approval-gated by the implementation prompt.

### Files changed

- `frontend/src/App.tsx`
- `frontend/src/components/navigation/CvingLegacyHeader.tsx`
- `frontend/src/pages/watchlist/WatchlistPage.tsx`
- `frontend/tests/watchlistPage.test.tsx`
- `CHANGELOG.md`

### Rollback

Restore `frontend/src/App.tsx`, `frontend/src/components/navigation/CvingLegacyHeader.tsx`, and `CHANGELOG.md` from `runtime/backups/2026-08-12_153610_v1/`, remove the new Watchlist page and focused test, then rebuild `frontend/dist`. No backend, API, dependency, Oracle, or data rollback is required.

## v160-agents-md-phase-one-workspace - 2026-08-11 13:34:00 IST

Updated `AGENTS.md` with repo-backed Phase 1 workspace guardrails. The guidance documents the additive `/app/phase-1` React surface, its typed navigation/API composer ownership, centralized-auth and symbol-normalization requirements, partial-source failure behavior, and focused frontend validation command. No frontend source, backend logic, API contract, Oracle object, runtime data, or generated build asset changed.

### Files changed

- `AGENTS.md`
- `CHANGELOG.md`

### Rollback

Restore `AGENTS.md` and `CHANGELOG.md` from `runtime/backups/2026-08-11_133229_v160-agents-md-phase-one-workspace/`. No backend, frontend build, API, or database rollback is required.

## v159-phase-one-workspace - 2026-08-09 07:24:00 IST

Added an isolated, protected Phase 1 React workspace under `/app/phase-1` with 17 additive research, intelligence, operations, and account routes. The existing application header now has one non-dropdown `Phase 1` entry; all original routes, dropdowns, pages, API response contracts, backend logic, Oracle tables, and the FYERS market-data pipeline remain unchanged. The workspace is read-only and composes existing Flask/Oracle-backed GET services with partial-source failure handling, responsive navigation, symbol normalization, loading/error/retry states, and links back to established detailed workflows. The existing centralized login is intentionally reused instead of adding a second Phase 1 login page.

### Files changed

- `frontend/src/App.tsx`
- `frontend/src/components/navigation/CvingLegacyHeader.tsx`
- `frontend/src/data/phaseOneNav.ts`
- `frontend/src/pages/phase-one/PhaseOneWorkspacePage.tsx`
- `frontend/src/services/api/phaseOneApi.ts`
- `frontend/tests/phaseOneWorkspace.test.tsx`
- `frontend/dist/index.html` (generated build entrypoint)
- `frontend/dist/react-assets/index-9sn30kU9.js` (generated)
- `frontend/dist/react-assets/index-B3x8tTxk.css` (generated)
- `CHANGELOG.md`

### Rollback

Restore `frontend/src/App.tsx`, `frontend/src/components/navigation/CvingLegacyHeader.tsx`, and `CHANGELOG.md` from `runtime/backups/2026-08-09_064826_v159-phase-one-workspace/`, then remove the three new Phase 1 source files and focused test listed above. Rebuild `frontend/dist` from the restored source; the now-unused hashed Phase 1 assets can remain safely because Vite preserves prior assets. The intermediate Phase 1 files are additionally preserved under `runtime/backups/2026-08-09_070805_v159-phase-one-workspace-polish/` and `runtime/backups/2026-08-09_071953_v159-phase-one-workspace-contract-tests/`. No backend, API, dependency, Oracle, or data rollback is required.

## v158-agents-md-db-workflow - 2026-08-09 06:36:30 IST

Updated `AGENTS.md` with repo-backed maintenance guidance for the repository-level Oracle migration/rollback/validation folders and clarified the Vite dev server port override. No application source, API contract, backend logic, frontend behavior, or Oracle schema changed.

### Files changed

- `AGENTS.md`
- `CHANGELOG.md`

### Rollback

Restore the files from `runtime/backups/2026-08-09_063556_docs-agents-maintenance/`. No backend, frontend build, API, or database rollback is required.

## v157-sector-overview-background-refresh - 2026-08-07 08:20:00 IST

Fixed `/app/sector/overview` card availability when its fast snapshot is older than the latest DEV trading date. The page still loads the persisted `/api/sectors/overview` snapshot first, but the automatic or toolbar-triggered `refresh=1` request now runs in a distinct background-refresh state so the already-loaded cards and stock rows remain visible instead of reverting to `Loading overview cards...` for the duration of the expensive rebuild. A failed background refresh also preserves the usable snapshot payload while reporting the refresh error. No card labels, counts, API contracts, backend logic, or Oracle data flow changed.

### Files changed

- `frontend/src/pages/sector/SectorOverviewPage.tsx`
- `frontend/tests/sectorOverviewPage.test.ts`
- `CHANGELOG.md`

### Rollback

Restore the files from `runtime/backups/2026-08-07_081907_v1/`. No backend, Oracle, API contract, or schema rollback is required.

## v156-sector-rotation-sticky-sector-readability - 2026-08-07 08:10:00 IST

Fixed the shared Sector Rotation table so long `SECTOR` names remain fully visible in the sticky column and horizontally scrolled metrics no longer show through its background. The change is scoped to `sector-breadth-table`, widens only its sticky sector role to 320px, and uses solid light/dark sticky backgrounds without changing routes, labels, data, sorting, APIs, or backend behavior.

### Files changed

- `frontend/src/styles.css`
- `frontend/tests/sectorRotationPage.test.ts`
- `CHANGELOG.md`

### Rollback

Restore the files from `runtime/backups/2026-08-07_080920_v1/`. No backend, Oracle, API contract, or schema rollback is required.

## v155-sector-wise-ltc-date-format - 2026-08-06 21:16:53 IST

Fixed Sector Wise Stocks `LTC_DATE` rendering so ISO, timestamp, and existing day-first values display as `DD-MM-YYYY` only. The shared sector display formatter now reuses the existing date-only utility, preventing ambiguous day-first values from being interpreted as `MM-DD-YYYY`; API payloads, sorting data, exports, and the page layout remain unchanged.

### Files changed

- `frontend/src/adapters/sectorPageAdapter.ts`
- `frontend/tests/sectorWiseStocksPage.test.tsx`
- `CHANGELOG.md`

### Rollback

Restore the files from `runtime/backups/2026-08-06_211653_v154-sector-wise-ltc-date-format/`. No backend, Oracle, API contract, or schema rollback is required.

## v154-sector-rotation-sticky-columns - 2026-08-06 21:15:00 IST

- Cloned the existing Sector Wise Stocks sticky-column contract into the shared Sector Rotation table.
- Preserved the route-specific first header (`S.NO` on Sector Rotation and `RANK` on StockEdge Sector Rotation) while making it and `SECTOR` sticky during horizontal scrolling.
- Added focused render assertions for both routes; no data, sorting, API, or backend behavior changed.

## v153-ttkhealth-symbol-rename - 2026-08-05 21:16:29 IST

Corrected the obsolete `TTKHEALTH` scrip to the current `TTKHLTCARE` symbol in the Oracle-backed Diversified sector membership and the persisted Sector Wise Stocks snapshot. The snapshot JSON payload was updated with the same symbol so Sector Rotation and Sector Wise pages no longer expose the old scrip. Existing `TTKHLTCARE` market-history rows and all UI/API contracts remain unchanged.

### Data changed

- `NSE_NIFTY_DIVERSIFIED_STAGING`
- `NSE_SECTOR_WISE_STOCKS_SNAPSHOT`
- `CHANGELOG.md`

### Rollback

Restore `CHANGELOG.md` from `runtime/backups/2026-08-05_211630_v153-ttkhealth-symbol-rename/`, then update `TTKHLTCARE` back to `TTKHEALTH` only in the `DIVERSIFIED` rows of the two listed Oracle tables (including the snapshot `PAYLOAD_JSON`). Clear the Sector Rotation caches or restart Flask after rollback. No schema change is involved.

## v150-sector-wise-v3-partial-fallback - 2026-07-29 18:28:32 IST

Fixed Sector Wise pages reporting the server as unavailable when a requested sector is not yet present in the published V3 stock snapshot. The shared route now falls back to its existing V1 local snapshot/data path for any unavailable V3 sector, while retaining the V3 response unchanged for published sectors. This covers Healthcare, IT Enabled Services, Software Products & Services, and any other sector omitted from a partial V3 publication.

### Files changed

- `backend/routes/sector_rotation.py`
- `CHANGELOG.md`

### Rollback

Restore the files from `runtime/backups/2026-07-29_182832_v1/` and restart the Flask service. No database schema or market-data changes are involved.

## v149-stockedge-moneyflow-rank - 2026-07-29 10:08:31 IST

Fixed the StockEdge Sector Rotation V3 table showing `N/A` for every Money Flow and 1W value. The V3 refresh source already had the five-session rank delta, but a source-version guard discarded it while building the published snapshot. The composite source query also calculated volume and delivery signals but did not expose or retain the V3 money-flow inputs after sector normalization.

The refresh now preserves `rankChange5` as the published 1W delta and carries sector-level volume ratio, delivery participation, signed-volume/OBV, accumulation, up/down-volume, and volume-breadth inputs into the existing V3 money-flow scorer. No routes, API response keys, database schema, or market-data flow changed.

### Files changed

- `backend/services/sector_rotation_service.py`
- `backend/services/sector_rotation_v3_service.py`
- `backend/sql/sector_rotation_composite.sql`
- `backend/tests/test_sector_rotation_v3_service.py`
- `runtime/snapshots/sector_rotation_v3_latest.json` (repaired live snapshot)
- `CHANGELOG.md`

### Rollback

Restore the files from `runtime/backups/2026-07-29_100831_v149-stockedge-moneyflow-rank/`, restart the Flask service, and republish the prior V3 snapshot if required. No Oracle schema or source-market-data rollback is required.

## v148-stockedge-nav-nowrap - 2026-07-24 11:21:45 IST

Kept the `StockEdge Sector Rotation` label on one horizontal row in the shared Sector navigation dropdown. The Sector menu alone now uses a 250px responsive width and prevents its link labels from wrapping; other navigation dropdown dimensions and page titles remain unchanged.

### Files changed

- `frontend/src/styles.css`
- `frontend/tests/headerDropdownStyles.test.ts`
- `frontend/dist/index.html`
- Generated frontend bundle assets
- `CHANGELOG.md`

### Rollback

Restore the recorded files from `runtime/backups/2026-07-24_111920_v148-stockedge-nav-nowrap/` and rebuild the frontend. No backend or database rollback is required.

## v147-sector-wise-old-controls-data - 2026-07-24 11:09:03 IST

Fixed Sector Wise Stocks showing the added `Strong Uptrend + Uptrend` dropdown instead of the old single sector-selector layout and displaying `No sector stocks found` despite the AUTO endpoint returning 21 rows. The added filter defaulted to leader-only V3 trend states, while the current legacy-compatible rows have no `trendState`; all 21 rows were therefore removed in the browser after loading.

Removed the trend-state dropdown and its implicit row filtering, restored the original `STOCK` ascending default sort, restored the `Existing Sector Wise Stocks` tab label, and removed the V3 run-information panel from this page. Search remains the only page-level row filter, so legacy rows without V3 trend state remain visible. The original sector dropdown is again the only select in the compact header, preventing the overlap shown in the reported screenshot.

### Files changed

- `frontend/src/pages/sector/SectorWiseStocksPage.tsx`
- `frontend/tests/sectorWiseStocksPage.test.tsx`
- `frontend/dist/index.html`
- Generated frontend bundle assets
- `CHANGELOG.md`

### Rollback

Restore the recorded files from `runtime/backups/2026-07-24_110525_v147-sector-wise-old-controls-data/` and rebuild the frontend. No backend, API, or database rollback is required.

## v146-sector-wise-columns-rollback - 2026-07-24 10:46:35 IST

Rolled back only the visible Sector Wise Stocks table columns to the pre-enhancement UI definition and ordering. The table again shows the established base columns through `TREND` and `SCORE`, followed only by populated legacy sector analytics columns. V3 Stock Strength, trend-state, return, RSI, MACD, ADX, and technical-link data remains available in the additive backend/adapter contract but is no longer added as visible table columns on this page.

The canonical Sector Rotation fix, the separate StockEdge Sector Rotation page, the 90-sector master-universe merge, V3 backend publication, cache/run-date integrity, filters, hierarchy tab, and every other page remain unchanged.

### Files changed

- `frontend/src/pages/sector/SectorWiseStocksPage.tsx`
- `frontend/tests/sectorWiseStocksPage.test.tsx`
- `CHANGELOG.md`

### Rollback

Restore the three files from `runtime/backups/2026-07-24_104400_v146-sector-wise-columns-rollback/` and rebuild the frontend to re-enable the appended Stock Strength columns. No backend or database rollback is required.

## v145-stockedge-sector-rotation-page - 2026-07-24 10:30:16 IST

Fixed the canonical Sector Rotation page appearing empty even though the published V3 API contained data. The strict Best Sectors view had zero qualifying rows because the current snapshot classified every sector as low-confidence `DATA_WEAK`; the page defaulted to that empty subset. `/app/sector/rotation` now keeps the established all-sector breadth presentation while reading the fast published V3 snapshot and merging it with the database-discovered 90-sector master list.

Added `/app/sector/stockedge-rotation` as a separate React page and Sector dropdown entry. It owns the enhanced V3 score, band, phase, confidence, coverage, money-flow, risk, data-date, eligibility, and factor-detail presentation. It defaults to All Sectors so the complete 90-sector universe remains visible, while Best Sectors remains available with its qualifying count and explicit failed-gate evidence. The V1/V2 backend branches and contracts remain unchanged.

Restored every pre-enhancement Sector Wise Stocks column and its existing order: `S.NO`, `SYMBOL`, `INDEX`, `MCAP`, `MCAP_RANK`, `LTC_DATE`, `PRICE`, `ATH`, `GAP`, `52WH`, `52WL`, EMA flags, `TREND`, `SCORE`, sector analytics, breakout, volume/delivery, risk, and confidence. The new V3 trend-state, Stock Strength, coverage, 1M/3M/6M return, RSI, MACD, ADX, and technical-link columns are appended without replacing the prior UI.

### Files changed

- `frontend/src/App.tsx`
- `frontend/src/data/sectorNav.ts`
- `frontend/src/pages/sector/SectorRotationPage.tsx`
- `frontend/src/pages/sector/StockEdgeSectorRotationPage.tsx`
- `frontend/src/pages/sector/SectorWiseStocksPage.tsx`
- `frontend/tests/sectorRotationPage.test.ts`
- `frontend/tests/sectorWiseStocksPage.test.tsx`
- `frontend/tests/sectorHeader.test.tsx`
- `CHANGELOG.md`

### Rollback

Restore the changed files from `runtime/backups/2026-07-24_101855_v145-stockedge-sector-rotation-page/`, remove `frontend/src/pages/sector/StockEdgeSectorRotationPage.tsx`, and rebuild the frontend. No backend, Oracle schema, or market-data rollback is required.

## v144-sector-rotation-v3-stock-strength - 2026-07-24 08:47:00 IST

Made the canonical React Sector Rotation and Sector Wise Stocks experience V3-only while preserving the existing backend V1/V2 branches and contracts. Removed version-suffixed frontend routes and navigation entries. Sector Rotation now defaults to Best Sectors using explicit score, band, phase, confidence, coverage, data-quality, risk, money-flow, freshness, and severe-warning gates; All Sectors visibly identifies every failed gate. The main ranking shows the V3 final score, band, phase, confidence, coverage, money flow, risk, and data date, while the legacy breadth display score remains only in Details.

Added an additive V3 stock-strength service behind the existing sector-wise endpoint. It consumes one shared cached Strong Technicals universe, extends that snapshot with 21/63/126-session returns, calculates within-sector momentum percentiles and seven weighted factors, and classifies each constituent as `STRONG_UPTREND`, `UPTREND`, `SIDEWAYS`, `DOWNTREND`, or `DATA_WEAK`. Parent-sector eligibility, current data, EMA200 history, confidence, factor coverage, and risk are hard gates. The consolidated stock snapshot is atomically written to `runtime/snapshots/sector_rotation_v3_stocks_latest.json` with the parent V3 run/date; mismatched or absent snapshots return an explicit unavailable response and never fall back to V1/V2. Failed V3 refreshes retain the prior stock file and do not clear existing page caches.

The Sector Wise Stocks page defaults to Strong Uptrend + Uptrend and exposes All, individual trend-state, and Data Weak filters. It shows Stock Strength Score (the public UI does not use StockEdge branding), 1M/3M/6M returns, confirmation indicators, coverage, risk, source dates, and parent eligibility. Per-stock links reuse the existing EMA, RSI, MACD, ADX, ATR, Breakout, Volume, Delivery, Price Action, and Strong Technicals pages and initialize their existing search from `?symbol=...`.

### Files changed

- `backend/services/strong_technicals_service.py`
- `backend/services/sector_rotation_v3_stock_service.py`
- `backend/services/sector_rotation_v3_refresh_service.py`
- `backend/routes/sector_rotation.py`
- `backend/tests/test_strong_technicals_service.py`
- `backend/tests/test_sector_rotation_v3_stock_service.py`
- `backend/tests/test_sector_rotation_v3_refresh_service.py`
- `backend/tests/test_sector_rotation_route.py`
- `docs/api-catalog.md`
- `frontend/src/App.tsx`
- `frontend/src/data/sectorNav.ts`
- `frontend/src/adapters/sectorPageAdapter.ts`
- `frontend/src/pages/sector/SectorRotationPage.tsx`
- `frontend/src/pages/sector/SectorWiseStocksPage.tsx`
- `frontend/src/pages/technical/TechnicalIndicatorPage.tsx`
- `frontend/src/pages/technical/TechnicalScreenerPage.tsx`
- `frontend/src/pages/technical/EMA.tsx`
- `frontend/src/pages/technical/Delivery.tsx`
- `frontend/src/utils/urlSymbolSearch.ts`
- `frontend/tests/sectorRotationPage.test.ts`
- `frontend/tests/sectorWiseStocksPage.test.tsx`
- `frontend/dist/index.html`
- Generated frontend bundle assets
- `CHANGELOG.md`

### Rollback

Restore existing files from `runtime/backups/2026-07-24_073735_v3-stock-strength/`, `runtime/backups/2026-07-24_081154_v3-stock-strength/`, `runtime/backups/2026-07-24_084658_v3-stock-strength/`, and `runtime/backups/2026-07-24_085045_v3-stock-strength/`; remove the two new backend tests, `backend/services/sector_rotation_v3_stock_service.py`, `frontend/src/utils/urlSymbolSearch.ts`, and the optional generated V3 stock snapshot; then rebuild the frontend. No Oracle schema or market-data rollback is required, and V1/V2 backend behavior remains available.

## v143-historical-symbol-variant-consolidation - 2026-07-22 21:20:00 IST

Added a rollback-backed Oracle maintenance utility for the 22 duplicate canonical symbol groups visible on the Historical Data page. The utility exports every affected DEV and ORACLE row before mutation, preserves the union of trading dates under the current canonical symbol, removes date-overlapping alternate-series rows, renames non-overlapping history to the canonical symbol, validates that no variant rows remain, and commits both tables in one transaction. It defaults to read-only preview mode and requires `--apply` for DML.

### Files changed

- `backend/scripts/consolidate_historical_symbol_variants.py`
- `CHANGELOG.md`

### Rollback

Use the per-table CSV exports and manifest generated under `runtime/backups/<timestamp>_v143-historical-symbol-variants/` to restore the exact pre-change rows. The pre-edit changelog is stored under `runtime/backups/2026-07-22_211624_v143-historical-symbol-variant-consolidation/`.

## v142-sector-rotation-v3-auto-publish - 2026-07-22 19:36:34 IST

Fixed `/app/sector/rotationv3` remaining on an older `LTC_DATE` after newer daily data was merged into `NSE_NIFTY500_DAILY_RAW_DATA_DEV`. The page previously displayed its browser snapshot while a schema-free V3 request recalculated for several minutes, and daily merge completion refreshed only legacy materialized views. Successful FYERS, scheduler, startup, and manual merges now run an isolated post-merge V3 publication check. It compares the latest V3 date with DEV, publishes only when DEV is newer, and skips duplicate same-day runs. Deployments with the optional V3 Oracle tables continue using their append-only Oracle publication; deployments without those tables atomically publish a restart-safe `runtime/snapshots/sector_rotation_v3_latest.json` fallback. The current fallback was seeded with `asOfDate=2026-07-22` and 77 calculated V3 rows. V1/V2 behavior, API contracts, formulas, and the immutable `STOCK_EOD_HISTORY -> DEV -> UI` flow are unchanged.

### Files changed

- `backend/services/sector_rotation_v3_refresh_service.py`
- `backend/services/sector_rotation_v3_repository.py`
- `backend/routes/marketdata.py`
- `backend/tests/test_sector_rotation_v3_refresh_service.py`
- `backend/tests/test_sector_rotation_v3_repository.py`
- `backend/tests/test_marketdata_sector_rotation_v3_refresh.py`
- `runtime/snapshots/sector_rotation_v3_latest.json`
- `CHANGELOG.md`

### Rollback

Restore the files recorded in `runtime/backups/2026-07-22_193634_v142-sector-rotation-v3-auto-publish/` and `runtime/backups/2026-07-22_195619_v142-sector-rotation-v3-auto-publish/`, remove `backend/tests/test_marketdata_sector_rotation_v3_refresh.py`, optionally remove the generated local snapshot, and restart Flask. Published Oracle V3 runs remain append-only; no destructive Oracle rollback is required.

## v141-sector-overview-subsecond-read - 2026-07-22 18:20:00 IST

Optimized `/app/sector/overview` and `GET /api/sectors/overview` for snapshot-first reads. Normal page loads now return the compact persisted overview payload before any Oracle lookup and use the persisted sector-discovery snapshot instead of synchronously counting symbols across 93 staging tables. When the compact payload is absent, the fast builder uses existing trend snapshots without launching per-symbol latest-candle or support/resistance recomputation; explicit toolbar Refresh retains the live recomputation path. Snapshot-backed rows now preserve their valid date, price, and trend instead of being forced into `Unknown / Insufficient Data` merely because no live latest-trade query ran. The frontend normal-read timeout is reduced from 240 seconds to 5 seconds so a backend regression fails quickly instead of leaving the page blocked for four minutes.

### Files changed

- `backend/routes/sector_rotation.py`
- `backend/tests/test_sector_rotation_route.py`
- `frontend/src/services/api/sectorApi.ts`
- `frontend/dist/index.html`
- Generated frontend bundle assets
- `CHANGELOG.md`

### Rollback

Restore the files recorded in `runtime/backups/2026-07-22_100632_v2026_07_22-sector-overview-subsecond/`, rebuild the frontend, and restart Flask. No Oracle rollback is required.

## v140-sector-rotation-v3-sync - 2026-07-22 10:20:00 IST

Fixed `/app/sector/rotationv3` retaining an old `LTC_DATE` and symbol counts after Refresh. The page previously issued only a forced breadth GET, while the durable V3 snapshot could be updated only through the offline script; the reference-symbol sync could also be skipped by its TTL. V3 Refresh now reuses `POST /api/sectors/refresh?version=v3`, forces reference synchronization, atomically publishes the new V3 snapshot, clears matching caches, and reloads the published run. V2 behavior and the opt-in V3 boundary remain unchanged.

### Files changed

- `backend/routes/sector_rotation.py`
- `backend/tests/test_sector_rotation_route.py`
- `frontend/src/pages/sector/SectorRotationPage.tsx`
- `frontend/src/services/api/sectorApi.ts`
- `frontend/tests/sectorRotationPage.test.ts`
- `docs/api-catalog.md`
- `CHANGELOG.md`

### Rollback

Use `runtime/backups/2026-07-22_100918_v140-sector-rotation-v3-sync/` as the before-change reference and selectively revert only the V3 refresh hunks, then rebuild the frontend and restart Flask. Do not restore the shared route/API files wholesale because later Sector Overview work also changed them. No Oracle schema or destructive data rollback is required; published V3 runs remain append-only snapshots.

## v139-ema-trend-timeout-fix - 2026-07-21 21:02:24 IST

Fixed `/app/technical/ema` timing out after 150 seconds on `GET /api/trend?tf=daily&refresh=1`. The prior T_D export change incorrectly made existing trend snapshots incompatible by requiring `allRows`, which forced a synchronous full trend/ATH recomputation. Restored backward-compatible snapshot validation and moved the T_D-only universe to the lightweight cached `GET /api/trend/trading-days` endpoint. EMA tables now return from the existing snapshot immediately while T_D download data loads independently through a grouped Oracle query.

### Files changed

- `backend/routes/trend.py`
- `backend/tests/test_trend_route_marketcap.py`
- `frontend/src/pages/technical/EMA.tsx`
- `frontend/src/services/api/technicalApi.ts`
- `frontend/src/types/api/technical.ts`
- `frontend/src/adapters/technicalEmaAdapter.ts`
- `frontend/tests/emaDownload.test.ts`
- `docs/api-catalog.md`
- `frontend/dist/index.html`
- Generated frontend bundle assets
- `CHANGELOG.md`

### Rollback

Restore the files recorded in `runtime/backups/2026-07-21_210224_v139-ema-trend-timeout/`, rebuild the frontend, and restart Flask.

## v138-sector-overview-latest-per-symbol - 2026-07-21 20:00:55 IST

Completed the BE-series correction by making Sector Overview honor its existing `LATEST_PER_SYMBOL` contract. Symbols absent on the global maximum DEV date now use their latest available canonical/suffix-aware DEV candle before trend resolution. This fixes valid transition or temporarily non-trading symbols such as `JBCHEPHARM` without changing historical data, formulas, API response keys, or the FYERS merge direction.

### Files changed

- `backend/routes/sector_rotation.py`
- `backend/tests/test_sector_rotation_route.py`
- `CHANGELOG.md`

### Rollback

Restore the files from `runtime/backups/2026-07-21_200055_v138-sector-overview-latest-per-symbol/`, restart Flask, and refresh Sector Overview. No Oracle rollback is required.

## v137-sector-be-symbol-canonicalization - 2026-07-21 19:30:03 IST

Fixed Sector Overview and Sector Wise Stocks analytics lookup for NSE cash-series suffixes such as `-BE`. The shared variant builder now recognizes every supported cash series (`EQ`, `BE`, `SM`, `ST`, and `BZ`) while continuing to display one canonical base symbol. Added current `CHEMFAB`/`ECOSMOBLTY` BE-series metadata and canonicalized legacy `LTIM` membership to current `LTM` market data. This preserves FYERS series formatting and the existing STOCK_EOD_HISTORY -> DEV pipeline; it does not rewrite historical candles or force `JBCHEPHARM` away from the locally evidenced EQ series.

### Files changed

- `backend/services/nse_symbol_normalization.py`
- `backend/routes/sector_rotation.py`
- `backend/tests/test_sector_rotation_route.py`
- `CHANGELOG.md`

### Rollback

Restore the files from `runtime/backups/2026-07-21_193003_v136-sector-be-symbol-canonicalization/`, restart Flask, and refresh sector caches. No Oracle data rollback is required for this suffix-matching fix.

## v136-fyers-ui-log-and-merge-counts - 2026-07-21 19:10:41 IST

Corrected FYERS `STOCK_EOD_HISTORY` direct-merge reporting so newly created daily rows display as `Inserted 1 rows` and existing changed/unchanged rows are counted as updated/skipped. The duplicate-safe Oracle `MERGE`, FYERS fetch order, API contracts, and immutable market-data flow remain unchanged. Removed `[FYERS_SYMBOL_RESOLVE]` and `[SINGLE_STOCK_SYNC]` diagnostics from the browser-visible job log while retaining processing, ETA, and insert/update summary lines; detailed diagnostics remain in backend logs.

### Files changed

- `backend/services/marketdata_service.py`
- `backend/tests/test_marketdata_fyers_proxy.py`
- `backend/tests/test_marketdata_fyers_job_progress.py`
- `CHANGELOG.md`

### Rollback

Restore the files recorded in `runtime/backups/2026-07-21_191041_v1/`. This returns the prior UI log tail and generic Oracle merged-count reporting without changing stored market data.

## v135-sector-symbol-membership-removal - 2026-07-21 19:02:00 IST

Removed `CIGNITITEC` and `RELINFRA` from Oracle sector membership so they no longer feed Sector Overview, Sector Wise Stocks, or Sector Rotation. The scoped cleanup removes `CIGNITITEC` from IT, removes `RELINFRA` from Infrastructure and Utilities staging, and removes both canonical symbol-map rows. Stock history and the immutable FYERS-to-market-data pipeline remain unchanged. Added forward, validation, and rollback SQL for an auditable and reversible data change.

### Files changed

- `backend/sql/remove_cignititec_relinfra_sector_memberships.sql`
- `backend/sql/validate_cignititec_relinfra_sector_removal.sql`
- `backend/sql/rollback_cignititec_relinfra_sector_memberships.sql`
- `CHANGELOG.md`

### Rollback

Run `backend/sql/rollback_cignititec_relinfra_sector_memberships.sql`, refresh the sector materialized views/caches, and verify both symbols appear only in their restored sector memberships. Restore `CHANGELOG.md` from `runtime/backups/2026-07-21_190200_v135-sector-symbol-membership-removal/` if the repository documentation also needs to be reverted.

## v135-ema-td-only-downloads - 2026-07-21 19:54:56 IST

Corrected EMA-page downloads to use `T_D` as the only inclusion condition. The existing trend calculation now exposes its unfiltered base rows through a backward-compatible `allRows` payload field, so exports do not depend on EMA>20 or any other EMA table condition. Only positive `T_D` values below the selected 1Y through 5Y limit are included. No checkbox selection produces no export rows. TXT remains comma-separated symbols only and CSV remains `s.no,symbol,t_d`.

### Files changed

- `frontend/src/pages/technical/EMA.tsx`
- `frontend/src/adapters/technicalEmaAdapter.ts`
- `frontend/src/types/api/technical.ts`
- `frontend/tests/emaDownload.test.ts`
- `backend/routes/trend.py`
- `backend/tests/test_trend_route_marketcap.py`
- `docs/api-catalog.md`
- `frontend/dist/index.html`
- Generated frontend bundle assets
- `CHANGELOG.md`

### Rollback

Restore the frontend files recorded in `runtime/backups/2026-07-21_195456_v135-ema20-td-under-threshold/`, the backend/type files in `runtime/backups/2026-07-21_200717_v135-ema-td-only-payload/`, and the catalog in `runtime/backups/2026-07-21_201958_v135-ema-td-only-catalog/`; then rebuild the frontend and restart Flask.

## v134-ema20-symbol-downloads - 2026-07-21 17:56:56 IST

Added same-line TXT and CSV download controls to the EMA>20 card. The optional >1Y through >5Y checkboxes apply strict minimum T_D thresholds using 252 trading days per year; TXT exports comma-separated symbols only, while CSV exports exactly `s.no,symbol,t_d`. Existing EMA API, table, search, breakout filtering, and market-data flows remain unchanged.

### Files changed

- `frontend/src/pages/technical/EMA.tsx`
- `frontend/src/adapters/technicalEmaAdapter.ts`
- `frontend/src/styles.css`
- `frontend/tests/emaDownload.test.ts`
- `frontend/dist/index.html`
- `frontend/dist/react-assets/index-BeYDCBEh.js`
- `frontend/dist/react-assets/index-nGEOTYRM.css`
- `CHANGELOG.md`

### Rollback

Restore the files recorded in `runtime/backups/2026-07-21_175656_v134-ema20-symbol-downloads/` and remove `frontend/tests/emaDownload.test.ts`, then rebuild the frontend bundle.

## v133-canonical-nse-symbol-cleanup - 2026-07-20 17:55:00 IST

Canonicalized obsolete NSE identities across FYERS NIFTY500 Sync and sector APIs, preserved the exact EQ/BE/SM/ST/BZ series required by FYERS, and deduplicated each sector/overview payload by canonical symbol. Added allow-listed Oracle forward/validation/rollback scripts for the six approved obsolete identities without changing valid cross-sector memberships or the FYERS -> STOCK_EOD_HISTORY -> DEV pipeline.

### Files changed

- `backend/services/nse_symbol_normalization.py`
- `backend/services/nifty500_sync_service.py`
- `backend/routes/sector_rotation.py`
- `backend/sql/cleanup_obsolete_nse_symbols.sql`
- `backend/sql/validate_obsolete_nse_symbols.sql`
- `backend/sql/rollback_obsolete_nse_symbols.sql`
- Focused backend tests and API catalog

### Rollback

Restore repository files from `runtime/backups/2026-07-20_174041_v1/`, restore the timestamped external FYERS CSV backup, run `backend/sql/rollback_obsolete_nse_symbols.sql` if the forward DML was applied, clear sector caches, and restart Flask.

## v132-sector-toolbar-unique-sync-refresh - 2026-07-18 11:26:18 IST

Removed the duplicate page-header sync status and Refresh controls from Sector Rotation V1/V2/V3 and removed the duplicate sync status badge from Sector Overview. The existing shared `StrategyToolbar` remains the single owner of sync/live status and Refresh actions across Sector Overview, Sector Rotation, and Sector Wise Stocks. Sector Overview keeps its page-specific row count, and all existing refresh handlers, API contracts, and market-data flows remain unchanged.

### Files changed

- `frontend/src/pages/sector/SectorOverviewPage.tsx`
- `frontend/src/pages/sector/SectorRotationPage.tsx`
- `frontend/tests/sectorRotationPage.test.ts`
- `frontend/dist/index.html`
- `frontend/dist/react-assets/index-iS-G9DjE.js`
- `CHANGELOG.md`

### Validation

- Focused Sector Overview and Sector Rotation frontend tests passed: 20 tests.
- Frontend TypeScript typecheck passed.
- Production build passed: 726 modules transformed; existing large-chunk warning only.
- Live Sector Rotation route and generated asset returned HTTP 200; the served bundle contains the shared toolbar and no duplicate `Sector rotation controls` or `Sync pending` labels.

### Rollback

Restore the source, test, and changelog files from `runtime/backups/2026-07-18_112618_v132-sector-toolbar-unique-sync-refresh/`, rebuild `frontend/dist`, and hard-refresh the sector route. No backend or Oracle rollback is required.

## v131-sector-overview-dev-fallback - 2026-07-18 08:00:00 IST

Fixed Sector Overview rows whose latest price/date and trend were stale despite current OHLCV being present in `NSE_NIFTY500_DAILY_RAW_DATA_DEV`. Overview now reuses the established Sector Wise Stocks DEV calculation for symbols absent from the trend snapshots, including the calculated trend direction. The result is cached by the current DEV trade date, so daily data changes invalidate it without altering existing snapshot rows or the Sector Rotation -> Sector Wise -> Overview flow.

### Files changed

- `backend/routes/sector_rotation.py`
- `backend/tests/test_sector_rotation_route.py`
- `CHANGELOG.md`

### Rollback

Restore the files from `runtime/backups/2026-07-18_085709_v1/` and restart the Flask service.

## v129-sector-v3-dropdown-routes - 2026-07-16 10:07:00 IST

Exposed the additive Sector Rotation V3 and Sector Wise Stocks V3 pages in the shared Sector dropdown without changing the existing V1/V2 pages or backend data flow. The root cause was frontend routing/navigation ownership: `/app/sector/rotationv3` existed in `App.tsx`, but `frontend/src/data/sectorNav.ts` did not register either V3 dropdown item, and no standalone `/app/sector/stocksv3` route existed. The dropdown now includes `Sector Rotation V3` and `Sector Wise Stocks V3`; V3 routes retain independent active-menu state, while Sector Wise Stocks V3 reuses the current DB-driven selector, table, search, tabs, pagination, and sector-wise API flow.

### Files changed

- `frontend/src/data/sectorNav.ts`
- `frontend/src/App.tsx`
- `frontend/src/pages/sector/SectorRotationPage.tsx`
- `frontend/src/pages/sector/SectorWiseStocksPage.tsx`
- `frontend/tests/sectorWiseStocksPage.test.tsx`
- `frontend/dist/index.html`
- `frontend/dist/react-assets/index-B3nac9TR.js`
- `CHANGELOG.md`

### Validation

- `npm.cmd run typecheck` passed.
- Focused Sector Rotation and Sector Wise Stocks suites passed: 33 tests.
- Production build passed; 726 modules transformed. Vite emitted the existing large-chunk warning.
- Live `http://127.0.0.1:5055/app/sector/rotation`, `/app/sector/rotationv3`, and `/app/sector/stocksv3` returned HTTP 200.
- Flask serves `/react-assets/index-B3nac9TR.js`, and the served bundle contains both `Sector Rotation V3` and `Sector Wise Stocks V3` labels.

### Rollback

Restore the changed source files and `CHANGELOG.md` from `runtime/backups/2026-07-16_095443_v1`, rebuild `frontend/dist`, and hard-refresh the Sector route. No backend or Oracle rollback is required.

## v128-sector-rotation-v3-shadow-engine - 2026-07-15 22:47:56 IST

Implemented an additive, opt-in Sector Rotation V3 engine and dashboard path without replacing the existing V1/V2 breadth flow. The verified V2 defects were that the page ranked the simple five-breadth average, V2 factors were scaled duplicates of one breadth value, and the `0-1` rotation value was compared with `50/75` phase thresholds. V3 now uses independent 0-100 factor functions, the configured `30/25/20/10/10/5` final formula, canonical final-score ranking, missing-data-aware weight redistribution, phase/hysteresis, confidence, coverage, reasons, warnings, strict JSON output, and immutable published snapshots. The existing `/app/sector/rotationv2` route is pinned to V2; `/app/sector/rotationv3` is additive, and the existing route remains V2 unless the explicit V3 build flag is used.

### Files changed

- Backend route and regression coverage: `backend/routes/sector_rotation.py`, `backend/tests/test_sector_rotation_route.py`.
- V3 factor, envelope, snapshot, refresh, and research services: `backend/services/sector_rotation_v3_factors.py`, `backend/services/sector_rotation_v3_service.py`, `backend/services/sector_rotation_v3_repository.py`, `backend/services/sector_rotation_v3_refresh_service.py`, `backend/services/sector_rotation_v3_backtest.py`.
- Offline runner: `backend/scripts/refresh_sector_rotation_v3.py`.
- Additive Oracle package: `backend/sql/create_sector_rotation_v3_schema.sql`, `backend/sql/validate_sector_rotation_v3_schema.sql`, `backend/sql/rollback_sector_rotation_v3_schema.sql`.
- Backend tests: `backend/tests/test_sector_rotation_v3_service.py`, `backend/tests/test_sector_rotation_v3_repository.py`, `backend/tests/test_sector_rotation_v3_refresh_service.py`, `backend/tests/test_sector_rotation_v3_schema_contract.py`, `backend/tests/test_sector_rotation_v3_backtest.py`.
- Feature-gated React implementation: `frontend/src/App.tsx`, `frontend/src/pages/sector/SectorRotationPage.tsx`, `frontend/src/adapters/sectorPageAdapter.ts`, `frontend/tests/sectorRotationPage.test.ts`.
- Deployment and contract documentation: `.env.example`, `README.md`, `docs/api-catalog.md`.
- Rebuilt Flask-served React output: `frontend/dist/index.html`, `frontend/dist/react-assets/index-CqZAdi5D.css`, `frontend/dist/react-assets/index-BNoWao46.js`.

### Implementation and safety

- `GET /api/sectors/breadth` and `?version=v2` retain their row-array response bodies and existing cache keys; only explicit `?version=v3` returns the V3 envelope.
- V3 uses a separate complete-envelope memory cache and reads only atomically published `SUCCESS` Oracle runs when deployed. Persisted scores, ranks, `runId`, dates, and generation metadata are not recomputed on reads or cache hits.
- The Oracle repository validates sector/rank uniqueness, strict JSON, required components, and configured/effective weight sums before publication. Required benchmark-version binds, nullable ranks, missing-flow penalty validation, `DATA_WEAK` bands, CLOB binds, and fail-closed snapshot row counts are aligned with the DDL.
- The React V3 view preserves the current table/toolbar/design language, keeps the breadth columns, corrects only V3 labels, ranks by `finalRotationScore`, and adds Rotation, Phase, 1W change, Confidence, Coverage, As Of, stale state, `N/A` handling, and expandable factor details.
- The isolated research module accepts caller-supplied point-in-time snapshots and calculates rank IC, top-bottom/Leading-Lagging spreads, cost-adjusted results, rank stability, turnover, and sensitivity correlation. It does not fabricate or execute a historical backtest dataset.
- No V1/V2 Oracle object or `backend/sql/sector_rotation_composite.sql` was changed. No Oracle DDL or data mutation was executed in this implementation run.

### Validation

- Backend compile check passed for the changed V3 services, runner, and route.
- Focused backend regression: 36 passed across V3 factors, repository publication/read integrity, refresh, schema contract, and the existing Sector Rotation route.
- Isolated research module: 8 passed.
- Frontend TypeScript check passed.
- Focused frontend Sector Rotation suite: 15 passed.
- Production frontend build passed; 726 modules transformed. Vite emitted the existing large-chunk warning.
- API duplicate scan passed: 191 routes, 0 exact duplicates, 21 similar-path review candidates.
- The initial sandboxed Vitest/build attempt hit the known Windows root-path access restriction; the exact commands passed when rerun through the approved unsandboxed path.
- The optional full-repository `enterprise_validate.py` wrapper was stopped after the scoped release checks completed because its repeated full backend/coverage/frontend suites exceeded the handoff time budget; it did not report a Sector Rotation failure before termination.
- Oracle create/validate/rollback scripts were checked statically only; live Oracle execution and explain-plan evidence remain deployment-time validation.

### Known limits

The V3 scoring service can consume full per-horizon return, sector-index trend, money-flow, and risk inputs, but the current shadow refresh still starts from the existing composite source and transparently flags legacy momentum/trend/risk proxies when those raw V3 inputs are absent. Point-in-time effective-dated constituent construction, a dedicated FFMC/flow input query, prior-V3 rank/phase hydration, live Oracle validation, authenticated browser/console proof, and measured production API p95 remain follow-up validation before V3 can become the default. V2 remains the default.

### Rollback

Set `SECTOR_ROTATION_ENGINE_VERSION=v2` and `VITE_SECTOR_ROTATION_VERSION=v2`, rebuild the frontend, and restart Flask. This requires no database operation. Existing-file backups are under `runtime/backups/2026-07-15_194248_Sector_Rotation_V3`, `runtime/backups/2026-07-15_195952_Sector_Rotation_V3`, `runtime/backups/2026-07-15_194403_v1`, `runtime/backups/2026-07-15_202321_v1`, `runtime/backups/2026-07-15_223804_v1`, and `runtime/backups/2026-07-15_224057_v1`. The guarded database rollback script may be used only after explicit approval if V3 objects are later deployed.

## v127-sector-wise-subsecond-cache-and-blank-columns - 2026-07-14 10:46:32 IST

Fixed `/app/sector/stocks/<sector>` cold-load latency and the eight always-blank analytics columns without changing the existing market-data pipeline or enabling placeholder financial calculations. Known application sector codes now resolve through the existing local alias/table maps, and the normal V1 route checks its versioned response cache and validated local sector snapshot before any Oracle resolver/latest-date/snapshot query. An expired local snapshot can render immediately with honest stale metadata while background refresh retains the last usable file until a complete, exact staging-membership result is ready; partial or wrong-sector rows cannot be published. The Oracle sector-wise snapshot writer now accepts the route's `stock` and current field aliases, batches inserts, records the actual inserted count, and runs outside the response path only when the full dataset is available. The frontend now normalizes and renders the eight additive aliases when real values exist, while suppressing analytics columns that have no populated producer instead of displaying eight misleading `-` columns. The repository's score-derived V2 mock service remains disabled for this page; live Oracle inspection confirmed the V2 snapshot tables are not deployed.

### Files changed

- `backend/routes/sector_rotation.py`
- `backend/services/sector_snapshot_service.py`
- `backend/tests/test_sector_rotation_route.py`
- `backend/tests/test_sector_snapshot_service.py`
- `frontend/src/adapters/sectorPageAdapter.ts`
- `frontend/src/pages/sector/SectorWiseStocksPage.tsx`
- `frontend/tests/sectorWiseStocksPage.test.tsx`
- `frontend/dist/index.html`
- `frontend/dist/react-assets/index-D6A8lig6.js`
- `backend/cache/sector_snapshots/NSE_NIFTY_AUTO_STAGING.json` (rebuilt runtime snapshot; 21 validated symbols)
- `runtime/reports/api-duplicate-report.json` (generated validation report)
- `CHANGELOG.md`

### Validation

- `python -m compileall backend\routes\sector_rotation.py backend\services\sector_snapshot_service.py` -> passed.
- `python -m pytest backend\tests\test_sector_snapshot_service.py backend\tests\test_sector_rotation_route.py backend\tests\test_sector_wise_latest_price_sync.py -q` -> 15 passed.
- `cd frontend; npm.cmd run typecheck` -> passed.
- `cd frontend; npm.cmd run test -- tests\sectorWiseStocksPage.test.tsx tests\sectorWiseStocksHierarchyTab.test.tsx` -> 18 passed after rerunning outside the sandbox for the known Vite root-path access restriction.
- `cd frontend; npm.cmd run build` -> passed; 726 modules transformed and Flask now serves `react-assets/index-D6A8lig6.js`. Vite emitted the existing large-chunk warning.
- `python scripts\scan_api_duplicates.py` -> passed; 191 routes, 0 exact duplicates, 21 similar paths.
- Rebuilt `NSE_NIFTY_AUTO_STAGING.json` from the verified 21-row `NSE_NIFTY_AUTO_STAGING` membership and confirmed all expected symbols from `ASHOKLEY` through `TVSMOTOR`.
- Fresh-process live API probe -> first response 56.7 ms wall / 6 ms backend from `LOCAL_SNAPSHOT`; four memory-cache responses 17.5-62.9 ms wall / 3-10 ms backend; all returned 21 of 21 rows.
- Authenticated Chrome verification -> 21 rendered rows, 17 populated headers, no eight empty analytics headers, no visible page error, and the served bundle was `react-assets/index-D6A8lig6.js`.

### Rollback

Restore the modified files from `runtime/backups/2026-07-14_104632_v127-sector-wise-subsecond-cache-and-blank-columns/`, remove the added `backend/tests/test_sector_snapshot_service.py`, rebuild `frontend/dist`, restart Flask, and hard-refresh the affected sector route.

## v126-sector-wise-sticky-columns-visibility - 2026-07-07 08:22:00 IST

Fixed the `/app/sector/stocks/rubber-products-tyres` Sector Wise Stocks horizontal-scroll sticky columns so `S.NO` and `SYMBOL` stay visible and opaque while moving right/left. The root cause was frontend-only: the raw Sector Wise Stocks table depended on generic `data-col` sticky inference while a later shared sticky-table override could win the cascade, leaving the pinned cells without the same explicit sticky metadata/classes and reliable opaque stacking used by shared table components. The page now marks `S.NO` and `SYMBOL` as explicit left-sticky columns and applies a page-scoped final CSS override for fixed widths, z-index, and light/dark row backgrounds. No Flask route, Oracle query, API contract, pagination, sorting, or sector data flow was changed.

### Files changed

- `frontend/src/pages/sector/SectorWiseStocksPage.tsx`
- `frontend/src/styles.css`
- `frontend/tests/sectorWiseStocksPage.test.tsx`
- `frontend/dist/index.html`
- `frontend/dist/react-assets/index-1Pyr9wey.css`
- `frontend/dist/react-assets/index-BKhCE98E.js`
- `CHANGELOG.md`

### Validation

- `cd frontend; npm.cmd run typecheck` -> passed.
- `cd frontend; npm.cmd run test -- sectorWiseStocksPage` -> passed; 16 tests passed in the focused Sector Wise Stocks suite.
- `cd frontend; npm.cmd run build` -> passed after rerunning outside the sandbox for the known Vite path access issue; rebuilt `frontend/dist` for Flask and generated `react-assets/index-1Pyr9wey.css` plus `react-assets/index-BKhCE98E.js`. Vite emitted the existing large-chunk warning.
- Browser snapshot attempted for `/app/sector/stocks/rubber-products-tyres`; the tool session redirected to `/login?redirect=%2Fapp%2Fsector%2Fstocks%2Frubber-products-tyres`, so authenticated horizontal-scroll QA remains the manual visual check.

### Rollback

Restore files from `runtime/backups/2026-07-07_082122_v1/` and `runtime/backups/2026-07-07_082156_v1/`, then rebuild `frontend/dist` and hard-refresh `/app/sector/stocks/rubber-products-tyres`.

## v125-sector-toolbar-live-status - 2026-07-02 20:44:30 IST

Adjusted the shared sector toolbar semantics on `/app/sector/rotation`, `/app/sector/overview`, and `/app/sector/stocks` to match the requested reference: the main status pill now represents page/API reachability and shows green `Live` after a successful load instead of using stale data freshness as the toolbar status. Stale database sync evidence remains available through the compact sync badges/messages and existing payload metadata; backend routes, Oracle queries, API contracts, and sector data flow were not changed.

### Files changed

- `frontend/src/pages/sector/SectorRotationPage.tsx`
- `frontend/src/pages/sector/SectorOverviewPage.tsx`
- `frontend/src/pages/sector/SectorWiseStocksPage.tsx`
- `frontend/tests/sectorRotationPage.test.ts`
- `frontend/dist/index.html`
- `frontend/dist/react-assets/index-BcqtFJ1o.js`
- `CHANGELOG.md`

### Validation

- `cd frontend; npm.cmd run typecheck` -> passed.
- `cd frontend; npm.cmd run test -- sectorRotationPage sectorOverviewPage sectorWiseStocksPage strategyToolbar` -> passed after rerunning outside the sandbox for the known Vite path access issue; 31 tests passed.
- `cd frontend; npm.cmd run build` -> passed after rerunning outside the sandbox for the known Vite path access issue; rebuilt `frontend/dist` for Flask and generated `react-assets/index-BcqtFJ1o.js`. Vite emitted the existing large-chunk warning.
- Inspected `frontend/dist/index.html` and the generated bundle: the served app now references `react-assets/index-BcqtFJ1o.js`, and Sector Rotation, Sector_Overview, and Sector Wise Stocks toolbar status wiring resolves through the live/error helper instead of stale sync metadata.

### Rollback

Restore the modified source files from `runtime/backups/2026-07-02_204354_v125-sector-toolbar-live-status/`, rebuild `frontend/dist`, and hard-refresh the affected sector routes. For only this follow-up validation note, restore `CHANGELOG.md` from `runtime/backups/2026-07-07_080129_v1/`.

## v124-sector-toolbar-stale-status - 2026-07-02 20:21:30 IST

Fixed the shared sector toolbar stale indicator across `/app/sector/rotation`, `/app/sector/overview`, and `/app/sector/stocks` so stale database sync evidence and stale sector-wise snapshots render the orange `Stale` state instead of falling through to green `Live`. The root cause was page-local toolbar status wiring that only checked `is_fully_synced === false`, while the backend also reports staleness through `stale_tables`, missing-count fields, `is_stale`/`stale`, and sector-wise `stale_snapshot` payload metadata.

### Files changed

- `frontend/src/services/api/sectorApi.ts`
- `frontend/src/adapters/sectorPageAdapter.ts`
- `frontend/src/pages/sector/SectorRotationPage.tsx`
- `frontend/src/pages/sector/SectorOverviewPage.tsx`
- `frontend/src/pages/sector/SectorWiseStocksPage.tsx`
- `frontend/tests/sectorRotationPage.test.ts`
- `frontend/tests/sectorOverviewPage.test.ts`
- `frontend/tests/sectorWiseStocksPage.test.tsx`
- `CHANGELOG.md`

### Validation

- Added focused frontend coverage for the shared database sync stale resolver and sector-wise stale snapshot metadata preservation.
- `cd frontend; npm.cmd run test -- tests\sectorRotationPage.test.ts tests\sectorOverviewPage.test.ts tests\sectorWiseStocksPage.test.tsx` -> 27 passed after rerunning outside the sandbox for the known Vite path access issue.
- `cd frontend; npm.cmd run typecheck` -> passed.
- `cd frontend; npm.cmd run build` -> passed after rerunning outside the sandbox for the known Vite path access issue; rebuilt `frontend/dist` for Flask. Vite emitted the existing large chunk warning.

### Rollback

Restore the modified files from `runtime/backups/2026-07-02_202008_v124-sector-toolbar-stale-status/` and `runtime/backups/2026-07-02_202112_v124-sector-toolbar-stale-status/`.

## v123-fyers-gap-aware-singlestock-sync - 2026-07-02 19:21:30 IST

Hardened FYERS SingleStock extraction with incremental, gap-aware sync while preserving the existing FYERS Automation UI, start/status endpoints, auth flow, stop flow, failed-symbol tracking, and downstream `STOCK_EOD_HISTORY` merge pipeline. The backend now reads existing `SYMBOL + TRUNC(TRADE_DATE)` coverage once per symbol/range, skips FYERS calls when the requested range is already covered, fetches only missing grouped ranges, continues after ordinary range-level FYERS failures, deduplicates fetched candles by trade date, and uses a repo-side change-aware Oracle `MERGE` so unchanged OHLCV rows are skipped instead of blindly updated.

### Files changed

- `backend/services/marketdata_service.py`
- `backend/tests/test_marketdata_fyers_proxy.py`
- `backend/tests/test_marketdata_fyers_job_progress.py`
- `frontend/src/pages/fyers/FyersAutomationPage.tsx`
- `frontend/tests/fyersAutomationPage.test.tsx`
- `CHANGELOG.md`

### Validation

- Added backend coverage for already-up-to-date symbols avoiding FYERS calls, per-range failure continuation, value-change detection, and gap-aware progress parsing.
- Added frontend coverage for the new FYERS KPI labels without changing the page layout.
- `python -m py_compile backend\services\marketdata_service.py backend\tests\test_marketdata_fyers_proxy.py backend\tests\test_marketdata_fyers_job_progress.py` -> passed.
- `python -m pytest backend\tests\test_marketdata_fyers_proxy.py -q` -> 56 passed.
- `python -m pytest backend\tests\test_marketdata_fyers_job_progress.py -q` -> 9 passed.
- `cd frontend; npm.cmd run test -- tests\fyersAutomationPage.test.tsx tests\fyersApi.test.ts` -> 25 passed after rerun outside the sandbox for the known Vite path access issue.
- `cd frontend; npm.cmd run typecheck` -> passed.
- `cd frontend; npm.cmd run build` -> passed and rebuilt `frontend/dist` for Flask; Vite emitted the existing large chunk warning.
- `python scripts\scan_api_duplicates.py` -> passed; routes=191, exact_duplicates=0.

### Rollback

Restore the modified files from `runtime/backups/2026-07-02_192130_v123-fyers-gap-aware-singlestock-sync/`.

## v122-fyers-symbol-resolver-st-bz-aliases - 2026-07-02 18:36:15 IST

Extended the backend-only FYERS symbol resolver to accept the full NSE/FYERS suffix set currently needed by automation (`-EQ`, `-BE`, `-SM`, `-ST`, `-BZ`) and added guarded aliases for stale shorthand symbols observed in failed requests (`CHOLAINV -> CHOLAFIN`, `RBL -> RBLBANK`, `SYSTEMATIX -> SYSTMTXC`). The existing `D:\fyers_api_integration\data\symbols_nifty500.csv` file and FYERS UI were not changed; invalid or unresolved inputs still become skipped/rejected rows with reasons before any OHLCV fetch or database insert is attempted.

### Files changed

- `backend/services/marketdata_service.py`
- `backend/tests/test_marketdata_fyers_proxy.py`
- `CHANGELOG.md`

### Validation

- Added focused resolver coverage for `-ST`, `-BZ`, stale `-EQ` inputs resolving to valid FYERS symbols, and known stale symbol-code aliases.
- `python -m py_compile backend\services\marketdata_service.py backend\tests\test_marketdata_fyers_proxy.py` -> passed.
- `python -m pytest backend\tests\test_marketdata_fyers_proxy.py -q` -> 53 passed.
- `python -m pytest backend\tests\test_marketdata_fyers_job_progress.py -q` -> 8 passed.
- `python scripts\scan_api_duplicates.py` -> passed; routes=191, exact_duplicates=0.
- Local proof against `D:\fyers_api_integration\data\symbols_nifty500.csv`: `NSE:ABSMARINE-EQ -> NSE:ABSMARINE-ST`, `NSE:CHOLAINV-EQ -> NSE:CHOLAFIN-EQ`, `NSE:RBL-EQ -> NSE:RBLBANK-EQ`, `NSE:SYSTEMATIX-EQ -> NSE:SYSTMTXC-BE`.

### Rollback

Restore the modified files from `runtime/backups/2026-07-02_183615_v122-fyers-symbol-resolver-st-bz-aliases/`.

## v121-sector-wise-stale-snapshot-fast-load - 2026-07-01 09:18:00 IST

Optimized `/app/sector/stocks/<sector>` first-load performance by serving the existing complete sector stock snapshot for normal non-refresh requests even when the raw market-data date has advanced beyond the snapshot date. The root cause was the sector-wise backend treating a date-advanced snapshot as unusable, deleting/bypassing the file snapshot, and rebuilding live rows before the UI could display anything; the React page also turned every auto-poll after the first tick into `refresh=1`, permanently bypassing caches. Normal page loads and auto-polls now use cache/snapshot revalidation, strict-mapped sector pages skip slow sector-table discovery after rows are loaded, and explicit toolbar Refresh/Live still forces a live rebuild.

### Files changed

- `backend/routes/sector_rotation.py`
- `backend/tests/test_sector_wise_latest_price_sync.py`
- `frontend/src/pages/sector/SectorWiseStocksPage.tsx`
- `CHANGELOG.md`

### Validation

- Added focused backend coverage proving a complete stale sector snapshot is served without a DB query on non-refresh page loads.
- `python -m pytest backend\tests\test_sector_wise_latest_price_sync.py -q` -> 7 passed.
- `npm.cmd run typecheck` -> passed.
- `npm.cmd run test -- sectorWiseStocksPage` -> 14 passed after rerunning outside the sandbox for the known Vite config access issue.
- `npm.cmd run build` -> passed and rebuilt `frontend/dist` for Flask.
- `python -m compileall backend` and `python scripts\scan_api_duplicates.py` -> passed.
- Post-restart live probe for `/api/sector/RUBBER_PRODUCTS_TYRES/stocks/sector-wise?dir=ASC&page=1&pageSize=200&sort=STOCK` -> HTTP 200, 343 ms wall time, 314 ms backend response header, 11 rows.

### Rollback

Restore the modified files from `runtime/backups/2026-07-01_091310_v121-sector-wise-stale-snapshot-fast-load/`.

## v120-sector-rotation-staging-count-cache-fix - 2026-07-01 08:23:25 IST

Fixed the `/app/sector/rotation` `TotalStocks` inconsistency where PSU Bank could show `1` while `/app/sector/stocks/psu-bank` correctly loaded 12 stocks from `NSE_NIFTY_PSU_BANK_STAGING`. The root cause was a stale/partial sector breadth count from the rotation SQL or memory cache winning over the staging-table discovery count, plus the React merge trusting the lower breadth total. The backend now re-applies staging-table supplementation before returning cached breadth rows and uses staging membership as the authoritative display total; the React page also uses the higher of breadth and discovery counts so browser/session cache cannot keep showing the stale lower value.

### Files changed

- `backend/routes/sector_rotation.py`
- `backend/tests/test_agriculture_sector_support.py`
- `backend/tests/test_sector_rotation_route.py`
- `frontend/src/pages/sector/SectorRotationPage.tsx`
- `frontend/tests/sectorRotationPage.test.ts`
- `CHANGELOG.md`

### Validation

- Added backend coverage for partial PSU Bank breadth summaries and memory-cache re-supplementation.
- Added frontend coverage for merging PSU Bank breadth rows with the 12-stock staging discovery count.
- Validation commands and results are captured with this rollout.

### Rollback

Restore the modified files from `runtime/backups/2026-07-01_082035_v1/`.

## v119-fyers-symbol-master-suffix-resolution - 2026-07-01 08:17:53 IST

Added a backend-only FYERS symbol-master resolution layer before OHLCV/history fetches so raw or wrongly suffixed inputs now resolve to the exact FYERS NSE capital-market symbol (`-EQ`, `-BE`, or `-SM`) without changing the existing FYERS Automation UI, auth flow, insert flow, or table schema. The root cause was `backend/services/marketdata_service.py` hardcoding `-EQ` during symbol normalization and passing CSV/input symbols through unchanged, which caused valid FYERS variants such as `NSE:AIMTRON-SM`, `NSE:APTECHT-BE`, and `NSE:BOSCH-HCIL-EQ` to be requested incorrectly as `-EQ`.

### Files changed

- `backend/services/marketdata_service.py`
- `backend/tests/test_marketdata_fyers_proxy.py`
- `CHANGELOG.md`

### Validation

- Added focused backend coverage for parsing the FYERS headerless symbol master, manual `BOSCHHCIL -> BOSCH-HCIL` alias handling, and skipping missing master symbols without aborting the batch.
- `python -m py_compile backend\services\marketdata_service.py backend\tests\test_marketdata_fyers_proxy.py`
- `pytest -q backend\tests\test_marketdata_fyers_proxy.py`

### Rollback

Restore the modified files from `runtime/backups/2026-07-01_080433_v_next/` and `runtime/backups/2026-07-01_080623_v_next/`.

## v118-sector-pages-live-toolbar-and-staging-totalstocks-fix - 2026-07-01 07:12:20 IST

Aligned `Sector Rotation`, `Sector_Overview`, and `Sector Wise Stocks` to the same shared Sector toolbar behavior and corrected the `TotalStocks` source on `/app/sector/rotation`. The root cause had two parts: `SectorRotationPage` and `SectorWiseStocksPage` were overriding the shared toolbar status label to always show `Synch`, and the backend sector-rotation summary was publishing the smaller data-backed symbol count as `totalStocks` even though the requested UI truth source is the staging-table stock universe used by Sector Wise Stocks. The sector pages now surface the real shared `Live / Stale / Syncing / Server Down` status text, `Sector_Overview` uses the same single-surface toolbar shell as the other Sector pages, and `Sector Rotation` now displays staging-table `TotalStocks` values in bold while preserving the resolved-symbol count as supplemental `availableSymbols` metadata.

### Files changed

- `backend/routes/sector_rotation.py`
- `backend/tests/test_agriculture_sector_support.py`
- `frontend/src/pages/sector/SectorOverviewPage.tsx`
- `frontend/src/pages/sector/SectorRotationPage.tsx`
- `frontend/src/pages/sector/SectorWiseStocksPage.tsx`
- `frontend/tests/sectorOverviewPage.test.ts`
- `frontend/tests/sectorRotationPage.test.ts`
- `frontend/tests/sectorWiseStocksPage.test.tsx`
- `CHANGELOG.md`

### Validation

- Added focused backend coverage for staging-table `totalStocks` plus supplemental `availableSymbols` propagation on the Sector Rotation breadth path.
- Added focused frontend coverage for the shared Sector toolbar rendering `Live` instead of the old hardcoded `Synch` label and for the shared single-surface overview toolbar variant.
- Validation commands and results are captured with this rollout.

### Rollback

Restore the modified files from `runtime/backups/2026-07-01_071221_v1/`.

## v117-sector-rotation-totalstocks-data-backed-fix - 2026-07-01 06:48:00 IST

Fixed the `TotalStocks` inconsistency on `/app/sector/rotation` by separating the display count from the existing breadth denominator. The root cause was backend-side: Sector Rotation was surfacing staging/reference symbol totals (`stockCount` / `totalSymbols`), while Sector Wise Stocks totals come from the current data-backed sector-wise row universe. The sector-rotation summary now publishes a dedicated `totalStocks` count based on symbols that actually resolved through the latest sector summary query, and the breadth supplement passes that field through to the React page without changing the existing rotation/breadth calculations.

### Files changed

- `backend/routes/sector_rotation.py`
- `backend/tests/test_agriculture_sector_support.py`
- `frontend/tests/sectorRotationPage.test.ts`
- `CHANGELOG.md`

### Validation

- Added backend coverage for data-backed `totalStocks` generation and breadth-row propagation.
- Added focused frontend coverage proving `totalStocks` takes precedence over staging-count aliases when both are present.
- Validation commands and results are captured with this rollout.

### Rollback

Restore the modified files from `runtime/backups/2026-07-01_064455_v1/`.

## v116-sector-pages-hide-sticky-subnav-strip - 2026-07-01 06:29:00 IST

Removed the shared Sector page subnav strip that rendered `Sector Rotation`, `Sector_Overview`, and `Sector Wise Stocks` as sticky pills above the page content. The overlap in the user screenshot came from `SectorMigrationLayout`: that sticky React-only strip was sitting on top of the table during scroll, so it has been removed for the shared Sector pages while keeping the main Sector dropdown in the existing header unchanged.

### Files changed

- `frontend/src/pages/sector/SectorMigrationLayout.tsx`
- `CHANGELOG.md`

### Validation

- Rebuilt the frontend bundle served by Flask from `frontend/dist`.
- Verified the shared Sector layout no longer renders the sticky subnav strip.
- Used the installed Vite/Vitest Node APIs where needed to avoid this host's CLI config-loader access-denied issue while preserving the same React + TypeScript build settings.

### Rollback

Restore the modified files from `runtime/backups/2026-07-01_062715_v1/`.

## v115-sector-rotation-totalstocks-header-refresh - 2026-07-01 06:06:00 IST

Kept the previously added Sector Rotation stock-count column in the same position and updated its visible header text to `TotalStocks` so it exactly matches the requested table order `S.NO | Sector | TotalStocks | ...`. Rebuilding the React bundle also refreshes the hashed Flask-served asset path under `frontend/dist/react-assets`, which helps clear stale browser-cached JS when `/app/sector/rotation` was still rendering the older table header set.

### Files changed

- `frontend/src/pages/sector/SectorRotationPage.tsx`
- `CHANGELOG.md`

### Validation

- Rebuilt the frontend bundle served by Flask from `frontend/dist`.
- Re-ran focused frontend validation for the Sector Rotation page path.
- Used the installed Vite/Vitest Node APIs with `configFile: false` / `config: false` to bypass this host's CLI config-loader access-denied issue while keeping the same React + TypeScript build settings.

### Rollback

Restore the modified files from `runtime/backups/2026-07-01_060446_v1/`.

## v114-sector-rotation-totalstocks-column - 2026-06-30 20:06:00 IST

Added the requested `TotalStocks` column to `/app/sector/rotation` immediately after `Sector` while preserving the rest of the table order and existing sector-rotation metrics. The page now normalizes stock counts from both live breadth rows (`totalSymbols`) and sector discovery payloads (`stockCount`) so every visible sector can show its total stock count without changing the current API flow.

### Files changed

- `frontend/src/adapters/sectorPageAdapter.ts`
- `frontend/src/pages/sector/SectorRotationPage.tsx`
- `frontend/tests/sectorRotationPage.test.ts`
- `CHANGELOG.md`

### Validation

- Added focused frontend coverage for `totalSymbols` and `stockCount` alias normalization into the new `TotalStocks` column path.
- Validation commands and results are captured with this rollout.

### Rollback

Restore the modified files from `runtime/backups/2026-06-30_200211_v1/`.

## v114-sector-overview-react-build-availability-fix - 2026-07-01 06:22:00 IST

Fixed the real reason the new `Sector_Overview` table UI was “implemented but not visible” in the live app. The React page and `/api/sectors/overview` payload were already correct, but `vite build` was rebuilding `frontend/dist` in place and temporarily removing `index.html` plus the previous hashed JS bundle. During that window Flask returned `503` for `/app/sector/overview`, and any open tab that still referenced the previous chunk hit a `404`, which left the page shell without the React table, filters, or download buttons. The React build now keeps the previous asset generation available while writing the new bundle so existing tabs continue to load and Flask never loses the SPA shell mid-build.

### Files changed

- `frontend/vite.config.ts`
- `CHANGELOG.md`

### Validation

- Verified the live backend already returned the additive `rows` payload for `/api/sectors/overview`.
- Confirmed the prior failure mode in Flask logs: `/app/sector/overview` returned `503` during rebuild and the previous hashed React asset returned `404`.
- Rebuilt the frontend and validated that the prior JS asset remains available while the new bundle is published.

### Rollback

Restore `frontend/vite.config.ts` and `CHANGELOG.md` from `runtime/backups/2026-07-01_062130_v2026_07_01-sector-overview-react-build-availability/`.

## v113-sector-overview-table-filters-and-downloads - 2026-06-30 19:55:00 IST

Added the requested stock table to `/app/sector/overview` with trend checkboxes for `Strong Uptrend`, `Uptrend`, `Downtrend`, `Sideways`, `Pullback in Uptrend`, and `Unknown / Insufficient Data`, plus TXT and CSV downloads that use the fixed `S.NO, STOCK, LTC_DATE, PRICE, TREND` column set. The backend change is additive only: `/api/sectors/overview` now returns lightweight row data alongside the existing card/count payload so the page can filter and export without fanning out into per-sector requests.

### Files changed

- `backend/routes/sector_rotation.py`
- `backend/tests/test_sector_rotation_route.py`
- `frontend/src/pages/sector/SectorOverviewPage.tsx`
- `frontend/src/services/api/sectorApi.ts`
- `frontend/tests/sectorOverviewPage.test.ts`
- `docs/api-catalog.md`
- `CHANGELOG.md`

### Validation

- Added focused backend coverage for the additive overview `rows` payload.
- Added focused frontend coverage for `Sideways` normalization and TXT/CSV export formatting.
- Validation commands and results are captured with this rollout.

### Rollback

Restore the modified files from `runtime/backups/2026-06-30_194856_v2026_06_30-sector-overview-table-download/`.

## v112-sector-overview-strong-uptrend-fallback-fix - 2026-06-30 09:36:00 IST

Fixed the remaining blank `Strong Uptrend` card on `/app/sector/overview` without reintroducing the slow master-score pass. The root cause was backend-side in the overview fast path: when the sparse trend cache had no `Strong Uptrend` label for a symbol, `_resolve_sector_overview_trend()` fell back to `calculate_sector_stock_trend()`, and that fallback always downgraded `near high + bullish EMA` snapshot rows to plain `Uptrend`. Current trendline snapshots still carry enough strength data (`ADX`, `RSI`, full EMA stack), so the overview resolver now promotes only those near-high rows that already have a bullish EMA stack and supportive strength readings into `Strong Uptrend`, while weaker near-high rows remain `Uptrend`.

### Files changed

- `backend/routes/sector_rotation.py`
- `backend/tests/test_sector_rotation_route.py`
- `CHANGELOG.md`

### Validation

- Added focused backend regression coverage for the exact overview fallback branch that was suppressing `Strong Uptrend`.
- Validation commands and results are captured with this rollout.

### Rollback

Restore the modified files from `runtime/backups/2026-06-30_093033_v1/`.

## v111-sector-wise-stocks-prefix-removed-from-visible-headings - 2026-06-30 09:07:00 IST

Removed the remaining visible `SECTOR WISE STOCKS -` prefix from the Sector Wise Stocks page headings. The earlier change only updated the header row title, but the card/table section title still rendered the old prefixed text, and the frontend bundle needed to be rebuilt for Flask-served UI parity. Both visible titles now show only the sector name while keeping the same toolbar, dropdown, tabs, table, and route behavior.

### Files changed

- `frontend/src/pages/sector/SectorWiseStocksPage.tsx`
- `frontend/tests/sectorWiseStocksPage.test.tsx`
- `CHANGELOG.md`

### Validation

- Updated the focused render assertion so the page still renders the active sector name without depending on the old prefixed text.
- Validation commands and results are captured with this rollout.

### Rollback

Restore the modified files from `runtime/backups/2026-06-30_090604_v1/`.

## v110-sector-wise-stocks-title-prefix-removal - 2026-06-30 09:01:00 IST

Removed the redundant `SECTOR WISE STOCKS -` prefix from the Sector Wise Stocks header row so the UI now shows only the active sector name beside the dropdown and tabs. This is a scoped frontend-only label change; the toolbar, sector selector, tabs, routing, and data flow remain unchanged.

### Files changed

- `frontend/src/pages/sector/SectorWiseStocksPage.tsx`
- `frontend/tests/sectorWiseStocksHierarchyTab.test.tsx`
- `CHANGELOG.md`

### Validation

- Updated the focused render assertion so the header row now expects only the sector label and rejects the old prefixed text.
- Validation commands and results are captured with this rollout.

### Rollback

Restore the modified files from `runtime/backups/2026-06-30_090039_v1/`.

## v109-sector-wise-stocks-header-row-alignment - 2026-06-30 08:55:00 IST

Adjusted the Sector Wise Stocks header layout to match the requested order exactly. The previous patch added the shared top toolbar, but the sector dropdown still lived inside the `Existing Sector Wise Stocks` tab content instead of the shared title row. The page now renders the second row as `SECTOR WISE STOCKS - <sector> | Dropdown | Existing Sector Wise Stocks | Sector Hierarchy`, while keeping the toolbar as the dedicated top row and preserving the existing page logic and navigation flow.

### Files changed

- `frontend/src/pages/sector/SectorWiseStocksPage.tsx`
- `frontend/tests/sectorWiseStocksHierarchyTab.test.tsx`
- `CHANGELOG.md`

### Validation

- Added a focused render assertion for the title-row ordering of title, dropdown, and tabs.
- Validation commands and results are captured with this rollout.

### Rollback

Restore the modified files from `runtime/backups/2026-06-30_085350_v1/`.

## v108-sector-wise-stocks-toolbar-alignment - 2026-06-30 08:50:00 IST

Aligned `/app/sector/stocks/*` with the Sector Rotation toolbar shell. The root cause was frontend-only: `SectorWiseStocksPage` still used its older local search/refresh/count strip, so the page missed the shared single-surface toolbar pattern already used on Sector Rotation and Sector Overview. The page now reuses `StrategyToolbar` for the top sync/search/total/refresh bar, keeps the existing sector selector and tabs below it, and records the latest loaded timestamp for the shared metadata row without changing the sector-wise data flow.

### Files changed

- `frontend/src/pages/sector/SectorWiseStocksPage.tsx`
- `frontend/tests/sectorWiseStocksPage.test.tsx`
- `CHANGELOG.md`

### Validation

- Added frontend render coverage for the shared toolbar surface on Sector Wise Stocks.
- Validation commands and results are captured with this rollout.

### Rollback

Restore the modified files from `runtime/backups/2026-06-30_084812_v1/` and `runtime/backups/2026-06-30_084703_v1/`.

## v107-sector-overview-trendline-snapshot-live-fix - 2026-06-30 08:24:00 IST

Fixed the remaining `/app/sector/overview` card and freshness issues without reintroducing the old timeout path. The root cause was twofold: the React page still hardcoded a `Consolidation` card, and the backend overview fast path was rebuilding per-symbol trend inputs from `backend/data/snapshot_trend_daily.json`, which only contains EMA-bucket subsets rather than the full symbol universe. That left many valid stocks incorrectly falling into `Unknown / Insufficient Data`, kept the payload source labeled as cache-backed, and marked the page stale even when a current full-row trendline snapshot already existed in `backend/data/cache/strong_technicals/`.

The overview backend now prefers the latest full-row `trendline_v1_daily_latest_1_ltc_<date>.json` snapshot when it matches the current Oracle `LTC_DATE`, merges the smaller EMA-bucket snapshot only as a missing-field fallback, drops the misleading `TREND_CACHE` source label when the cache is empty, and treats freshness as a snapshot-date problem instead of a symbol-coverage problem. On the frontend, the removed `Consolidation` and `Insufficient` overview buckets are no longer rendered, and the toolbar now shows the actual `Live` / `Stale` / `Syncing` status instead of always displaying `Synch`.

### Files changed

- `backend/routes/sector_rotation.py`
- `backend/tests/test_sector_rotation_route.py`
- `frontend/src/pages/sector/SectorOverviewPage.tsx`
- `frontend/tests/sectorOverviewPage.test.ts`
- `CHANGELOG.md`

### Validation

- Added backend coverage for the preferred current trendline snapshot path and the updated non-stale overview state.
- Added frontend coverage so removed overview buckets stay hidden even if dynamic trend counts still contain legacy labels.
- Validation commands and live route checks are captured with this rollout.

### Rollback

Restore the modified files from `runtime/backups/2026-06-30_081813_v1/`.

## v106-sector-overview-timeout-snapshot-fast-path - 2026-06-30 07:02:00 IST

Fixed the `GET /api/sectors/overview` timeout on `/app/sector/overview` by replacing the expensive per-request raw-history fan-out with a local snapshot-backed overview aggregation. The prior backend change had corrected blank/zero card classification, but it did so by loading raw latest-price rows plus raw EMA and extrema history for the full sector universe, which pushed the page past the frontend's 240-second request budget. Live inspection then showed the database snapshot view was too stale and sparse for this route, so the final overview fast path now prefers the fresh local `backend/data/snapshot_trend_daily.json` trend rows, preserves valid cached trend labels when present, and computes trend fallback from snapshot price/EMA/ATH fields only for unresolved symbols. The standalone `Insufficient` card remains removed, and unresolved symbols continue to roll into `Unknown / Insufficient Data`.

### Files changed

- `backend/routes/sector_rotation.py`
- `backend/tests/test_sector_rotation_route.py`
- `CHANGELOG.md`

### Validation

- Updated backend regression coverage so the overview aggregation uses the snapshot-backed loader and still computes trend counts when cached trend-map entries are sparse.
- Validation commands and results are captured with this rollout.

### Rollback

Restore the modified files from `runtime/backups/2026-06-30_065028_v1/`.

## v105-sector-overview-live-trend-fallback - 2026-06-30 06:54:00 IST

Fixed the `Sector_Overview` card counts so the page no longer depends only on the thin cached SR trend map. The root cause was backend-side: when `sr_levels_mv` or the SR payload fallback did not populate most symbols, the overview route treated historical symbols as unresolved and collapsed them into a mostly blank card layout. The overview backend now computes a trend fallback from the same raw latest-price, EMA, and extrema inputs already used by the sector-wise stock path, so trend cards can populate even when the cached trend map is sparse. The standalone `Insufficient` card was removed and those unresolved cases are now represented only under `Unknown / Insufficient Data`.

### Files changed

- `backend/routes/sector_rotation.py`
- `backend/tests/test_sector_rotation_route.py`
- `frontend/src/pages/sector/SectorOverviewPage.tsx`
- `frontend/tests/sectorOverviewPage.test.ts`
- `CHANGELOG.md`

### Validation

- Added backend coverage for live overview trend fallback when cached trend-map entries are missing.
- Added frontend coverage for removing the standalone `Insufficient` card.
- Validation commands and results are captured with this rollout.

### Rollback

Restore the modified files from `runtime/backups/2026-06-30_065028_v1/`.

## v104-sector-overview-history-buckets - 2026-06-30 06:42:00 IST

Refined `GET /api/sectors/overview` so the Sector Overview cards now separate stocks with some historical rows but not enough usable signal history from stocks that have no historical rows at all. The backend now uses the existing latest-trade lookup instead of assigning the same LTC date to every sector symbol, counts historical-but-insufficient symbols under `Insufficient`, and counts genuinely missing-history symbols under `Unknown / Insufficient Data`. The React overview page was kept backward-compatible and only updated to render the new explicit card in the static card order.

### Files changed

- `backend/routes/sector_rotation.py`
- `backend/tests/test_sector_rotation_route.py`
- `frontend/src/pages/sector/SectorOverviewPage.tsx`
- `frontend/tests/sectorOverviewPage.test.ts`
- `CHANGELOG.md`

### Validation

- Added backend regression coverage for the split between historical-but-insufficient symbols and no-history symbols in the overview payload.
- Validation commands and results are captured with this rollout.

### Rollback

Restore the modified files from `runtime/backups/2026-06-30_063737_v1/`.

## v103-sector-wise-selector-serial-numbers - 2026-06-30 06:41:00 IST

Added serial numbers to the page-level sector selector on `/app/sector/stocks/*` so the dropdown now renders ordered entries such as `1. Abrasives`, `2. Agriculture`, and continues through the final sector entry in the current sorted list. The change is UI-only inside `SectorWiseStocksPage`: it preserves existing sector codes, routes, active-page labels, and backend discovery/data-loading behavior, while adding focused regression coverage for the numbered selector labels.

### Files changed

- `frontend/src/pages/sector/SectorWiseStocksPage.tsx`
- `frontend/tests/sectorWiseStocksPage.test.tsx`
- `CHANGELOG.md`

### Validation

- Added focused frontend coverage to prove the selector renders numbered sector labels from the first sorted entry through the last entry without changing the page title.

### Rollback

Restore the modified files from `runtime/backups/2026-06-30_063859_v1/`.

## v102-sector-rotation-toolbar - 2026-06-30 06:12:15 IST

Aligned `/app/sector/rotation` with the same top toolbar layout already used by `Sector_Overview` so the page now shows the compact `Synch | Search Card | Total | Refresh` bar at the top instead of the older header-only controls. The change stays page-local: it reuses the shared `StrategyToolbar`, adds a local sector-name/code search filter for the table rows, preserves the existing breadth/discovery/database-sync APIs, and keeps the existing table columns and sector links unchanged. The toolbar now opts into a single-surface render path so the old card-inside-card shell is flattened into one visible container without duplicate border, shadow, radius, or padding.

### Files changed

- `frontend/src/pages/sector/SectorRotationPage.tsx`
- `frontend/tests/sectorRotationPage.test.ts`
- `frontend/src/components/strategy/StrategyToolbar.tsx`
- `frontend/tests/strategyToolbarSingleSurface.test.tsx`
- `CHANGELOG.md`

### Validation

- Added focused frontend coverage for the new sector-rotation search filtering logic.
- Validation commands and results are captured with this rollout.

### Rollback

Restore the modified files from `runtime/backups/2026-06-30_061225_v102-sector-rotation-toolbar/`.

## v101-stock-history-kpi-fix - 2026-06-30 05:58:00 IST

Fixed the React stock-history KPI cards and toolbar totals when `/app/database/stock-history` loads valid Trading Day Coverage rows but the stats payload is wrapped or uses stock-history-specific keys. The root cause was page-local: the summary-table loader already unwraps nested `data`, but the stats loader stored the raw payload directly, so KPI fields such as stock count and trading-day count could be missed entirely. The page also ignored `stock_eod_stock_count`, causing `TOTAL STOCKS` and the toolbar `Total` badge to fall back to `rows.length` instead of the actual latest stock count shown in the table.

### Files changed

- `frontend/src/pages/ops/StockHistoryPage.tsx`
- `frontend/tests/stockHistoryPage.test.ts`
- `CHANGELOG.md`

### Validation

- Added focused frontend regression coverage for stock-history KPI resolution from wrapped stats payloads and table-row fallbacks.
- Validation commands and results are captured with this rollout.

### Rollback

Restore the modified files from `runtime/backups/2026-06-30_055743_v101-stock-history-kpi-fix/`.

## v100-stock-history-merge-normalization - 2026-06-29 18:55:00 IST

Fixed the live stock-history DEV/ORACLE reconciliation failures in the Python merge path by normalizing the `SYMBOL + TRADING_DATE` key the same way the Oracle package does. Runtime logs on June 29 showed repeated auto-merge failures after reconciliation, first as `dev_source_changed=1 / oracle_source_changed=1` and then as `missing_after` rows still remaining in `CVING_APP.NSE_NIFTY500_DAILY_RAW_DATA_DEV`. The root cause was that the Python-side reconciliation validated against normalized keys but still inserted/parity-compared raw `symbol` and raw `trade_date/trading_date`, so rows with casing, whitespace, or time-component drift could not satisfy the post-merge parity checks.

### Files changed

- `backend/services/marketdata_service.py`
- `backend/tests/test_marketdata_stock_history_sync.py`
- `CHANGELOG.md`

### Validation

- Added targeted regression coverage to assert the stock-history reconciliation source query now canonicalizes `symbol` and `trade_date`, and that cross-target parity sync also normalizes `symbol` and truncates `trading_date`.
- Validation commands and results are captured with this rollout.

### Rollback

Restore the modified files from `runtime/backups/2026-06-29_185452_v100-stock-history-merge-normalization/`.

## v99-sector-overview - 2026-06-29 09:55:00 IST

Added a new React sector overview page at `/app/sector/overview` and a consolidated backend endpoint at `GET /api/sectors/overview` without disturbing the existing Sector Rotation or Sector Wise Stocks flows. The new page is exposed under the Sector navbar dropdown as `Sector_Overview`, uses an Asura-style top toolbar with `Synch`, search, and refresh controls, and reuses the existing sector discovery source for sector count plus the existing sector-wise stock payloads for total stock, latest `LTC_DATE`, normalized trend counts, and dynamic extra trend cards.

### Files changed

- `backend/routes/sector_rotation.py`
- `backend/tests/test_sector_rotation_route.py`
- `docs/api-catalog.md`
- `frontend/src/App.tsx`
- `frontend/src/components/strategy/StrategyToolbar.tsx`
- `frontend/src/data/sectorNav.ts`
- `frontend/src/pages/sector/SectorOverviewPage.tsx`
- `frontend/src/services/api/sectorApi.ts`
- `frontend/src/styles.css`
- `frontend/tests/sectorHeader.test.tsx`
- `frontend/tests/sectorWiseStocksPage.test.tsx`
- `CHANGELOG.md`

### Validation

- Added backend coverage for the new sector overview aggregation and trend normalization route behavior.
- Added frontend coverage for the new canonical `Sector_Overview` navigation entry.
- Focused validation commands and results are captured with this rollout.

### Rollback

Restore the modified files from `runtime/backups/2026-06-29_094304_v99-sector-overview/` and remove the new `frontend/src/pages/sector/SectorOverviewPage.tsx` file if a full rollback is required.

## v98-source-pack-sector-expansion-and-unique-selector - 2026-06-29 09:25:00 IST

Expanded the sector onboarding flow for the missing source-pack sectors and removed duplicate sector exposure from the shared sector selector path. The live Oracle inventory had only `67` staging tables and none of the 25 new source-pack staging tables existed yet; the selector path also exposed alias duplicates instead of unique canonical sectors.

The backend selector now collapses duplicate sector aliases into one unique sector for UI use, the static sector registry now uses one canonical page per sector, and the repo now includes SQL + loader artifacts for the 25 missing unique sectors so they can follow the existing `staging -> reference sync -> sector master -> UI` flow.

### Files changed

- `backend/routes/sector_rotation.py`
- `backend/tests/test_sector_source_pack_expansion_mapping.py`
- `backend/sql/create_sector_reference_sync_procedures.sql`
- `backend/sql/create_source_pack_sector_expansion_tables.sql`
- `backend/sql/validate_source_pack_sector_expansion_tables.sql`
- `backend/sql/rollback_source_pack_sector_expansion_tables.sql`
- `backend/scripts/load_source_pack_sector_file.py`
- `docs/api-catalog.md`
- `frontend/src/data/sectorNav.ts`
- `frontend/src/pages/sector/SectorWiseStocksPage.tsx`
- `frontend/tests/sectorWiseStocksPage.test.tsx`
- `CHANGELOG.md`

### Validation

- Added targeted backend coverage for unique-sector collapsing and source-pack table registration.
- Added frontend tests for new unique sectors and static registry uniqueness.
- Validation commands and results are captured with this rollout.

### Rollback

Restore the modified files from `runtime/backups/2026-06-29_084000_v1-source-pack-sector-expansion/`. If DB onboarding scripts are later applied and must be reversed, use `backend/sql/rollback_source_pack_sector_expansion_tables.sql` and rerun the sector reference sync procedures.

## v97-nse-delivery-summary-name-error-test-fix - 2026-06-26 10:08:00 IST

Fixed test regression and documented resolved NameError on the `/api/marketdata/nse-delivery/summary` endpoint. The NameError (`NameError: name '_get_dashboard_all' is not defined`) occurred because the Flask server was running on stale cached bytecode before it was restarted. We also fixed a test regression in `backend/tests/test_nse_delivery_service.py` where a signature change to `_upsert_records` returning 3 values caused unpacking errors in `test_upsert_records_omits_id_from_delivery_update_binds`.

### Files changed

- `backend/tests/test_nse_delivery_service.py`
- `CHANGELOG.md`

### Validation

- Python cache files cleaned and compileall completed successfully.
- Pytest backend tests in `backend/tests/test_nse_delivery_service.py` passed (19 passed).
- Launcher regression tests in `tests/backend/test_start_flask_launcher.py` passed (1 passed).
- Query verified returning HTTP 200 OK with full payload on `http://127.0.0.1:5055/api/marketdata/nse-delivery/summary?refresh=false&range=MAX`.

### Rollback

Restore `backend/tests/test_nse_delivery_service.py` and `CHANGELOG.md` from backups.

## v96-market-data-sync-alignment - 2026-06-26 08:34:00 IST

Implemented strict SYMBOL + TRADING_DATE database alignment across MCAP, FFMC, and DELIVERY tables using the DEV table (`NSE_NIFTY500_DAILY_RAW_DATA_DEV`) latest date as the primary source of truth. Added API endpoints for checking sync status and triggering manual sync. Reflected sync status uniformly in the Sector Rotation and Sector Wise Stocks React pages with live badges.

### Files changed

- `backend/services/market_table_sync_service.py`
- `backend/routes/database.py`
- `backend/app.py`
- `backend/routes/marketdata.py`
- `backend/sql/sector_rotation_composite.sql`
- `backend/tests/test_market_table_sync.py`
- `frontend/src/services/api/sectorApi.ts`
- `frontend/src/pages/sector/SectorRotationPage.tsx`
- `frontend/src/pages/sector/SectorWiseStocksPage.tsx`

### Validation

- Targeted backend tests passed: `python -m pytest backend/tests/test_market_table_sync.py` (2 passed).
- Frontend typecheck passed: `npm.cmd run typecheck`.

### Rollback

Restore modified files from backup, delete the new service/route/test files, and restart the Flask app.

## v95-nse-db-pages-oracle-lob-job-rehydrate-fix - 2026-06-26 07:28:09 IST

Fixed the shared NSE persisted-job rehydration path used by `/app/database/nse-market-cap`, `/app/database/nse-ffmc`, and `/app/database/nse-delivery-data`. The DB dashboard services were returning Oracle rows, but the page mount also calls the shared `jobs/latest` endpoint; that endpoint could fail while converting persisted Oracle CLOB payloads for request, metrics, or log fields, causing the UI load chain to stall or surface API failures even though table data existed.

The run-row queries now select bounded CLOB text through `DBMS_LOB.SUBSTR`, and the persisted-job parser safely handles unreadable LOB-like values without throwing. This preserves the existing NSE ingestion, Oracle tables, dashboard response contracts, pagination, and automation logic.

### Files changed

- `backend/services/nse_mcap_service.py`
- `backend/tests/test_nse_mcap_service.py`
- `CHANGELOG.md`

### Validation

- Direct service probes returned DB-backed dashboard rows for all three pages: MCAP `25/946`, FFMC `25/947`, Delivery `25/947`.
- `python -m pytest backend\tests\test_nse_mcap_service.py -q` passed (`47 passed`).
- `python -m compileall backend\services\nse_mcap_service.py backend\tests\test_nse_mcap_service.py` passed.
- After restart, the shared `jobs/latest` endpoints for MCAP, FFMC, and Delivery logged `200` responses instead of the previous MCAP `500`.
- `python -m pytest backend\tests\test_nse_ffmc_service.py backend\tests\test_nse_delivery_service.py -q` still has an unrelated existing Delivery bind-shape test failure at `backend\tests\test_nse_delivery_service.py:306`.

### Rollback

Restore `backend/services/nse_mcap_service.py`, `backend/tests/test_nse_mcap_service.py`, and `CHANGELOG.md` from `runtime/backups/2026-06-26_072307_v93-nse-db-page-job-lob-fix/`, `runtime/backups/2026-06-26_072307_v93-nse-db-page-job-lob-fix_2/`, and `runtime/backups/2026-06-26_072315_v93-nse-db-page-job-lob-fix/`, then restart Flask.

## v95-fyers-automation-resilience - 2026-06-26 07:16:00 IST

Refactored `/app/fyers/automation` to stop stale-run hostage behavior, honor a true 24-hour FYERS auth validity window, improve stop/cancel feedback, and reduce noisy transport-failure messaging without changing the Oracle insert/merge flow or duplicate-skip behavior.

### Root cause

- The FYERS auth gate still normalized validity around `last_auth_date == today`, so valid JWTs were treated like day-bound sessions instead of 24-hour cached credentials.
- The FYERS automation page auto-attached to backend `latest-active-job` history, which made stale persisted `RUNNING` rows look like resumable work even when the user just wanted a fresh batch run.
- Backend single-flight blocking was global in-memory rather than browser-session-scoped, so an existing active job could block a fresh batch start even when it came from another browser session.
- Stop requests were accepted, but the page did not immediately abort the live poll/request chain and continue from an explicit `Stopping...` state.
- Poll/auth transport failures fell back to generic retry messages instead of a clear localhost-backend-unreachable message.

### Files changed

- `backend/services/marketdata_service.py`
- `backend/tests/test_marketdata_fyers_proxy.py`
- `frontend/src/pages/fyers/FyersAutomationPage.tsx`
- `frontend/src/pages/fyers/fyersPageUtils.ts`
- `frontend/tests/fyersAutomationPage.test.tsx`
- `docs/api-catalog.md`
- `CHANGELOG.md`

### Validation

- `python -m pytest backend\tests\test_marketdata_fyers_proxy.py -q` passed (`50 passed`).
- `python -m compileall backend\services\marketdata_service.py backend\tests\test_marketdata_fyers_proxy.py` passed.
- `cd frontend; npm.cmd run typecheck` passed.
- `cd frontend; npm.cmd run test -- tests\fyersAutomationPage.test.tsx tests\fyersApi.test.ts` first hit the known sandbox Vite ACL issue, then passed unsandboxed (`25 passed`).
- `cd frontend; npm.cmd run build` first hit the same sandbox Vite ACL issue, then passed unsandboxed and refreshed `frontend/dist`; the existing large-chunk warning remains.
- `python scripts\scan_api_duplicates.py` passed (`exact_duplicates=0`).
- `python scripts\enterprise_validate.py` exceeded the extended five-minute runtime budget in this environment and was not allowed to complete; targeted backend/frontend validation above completed successfully.

### Rollback

Restore files from `runtime/backups/2026-06-26_071551_v95-fyers-automation-resilience/`, rebuild `frontend/dist`, and restart Flask if you roll back the backend service changes.

## v94-fyers-auth-status-network-retry - 2026-06-26 06:38:00 IST

Hardened `/app/fyers/automation` against transient `GET /api/marketdata/fyers/auth-status` transport failures that surface in the browser as `Status: 0` and `Failed to fetch` even when the Flask route itself is still available. The page now retries one transient auth-status failure locally, keeps extraction blocked while retrying, and exposes a manual `Refresh Status` action beside `Authorize`.

The live route probe from this workspace returned a real `401 Unauthorized` response on `http://127.0.0.1:5055/api/marketdata/fyers/auth-status`, which confirmed the endpoint was registered and reachable. That narrowed the issue to page-level resiliency on a transient fetch miss rather than a missing FYERS route or a removed backend contract.

### Files changed

- `frontend/src/pages/fyers/FyersAutomationPage.tsx`
- `frontend/tests/fyersAutomationPage.test.tsx`
- `CHANGELOG.md`

### Validation

- `cd frontend; npm.cmd run test -- tests\\fyersAutomationPage.test.tsx`
- `cd frontend; npm.cmd run typecheck`
- `cd frontend; npm.cmd run build`
- Direct route probe from PowerShell returned `401 Unauthorized` for `Invoke-WebRequest http://127.0.0.1:5055/api/marketdata/fyers/auth-status`, which is expected without the browser session and confirms transport reachability.

### Rollback

Restore the files from `runtime/backups/2026-06-26_063755_v94-fyers-auth-status-network-retry/`, rebuild `frontend/dist`, and reload `/app/fyers/automation`.

## v89-public-nse-status-support-api - 2026-06-25 17:59:39 IST

Exempted `/api/automation/nse-marketdata/status` from JWT/session enforcement because the now-public NSE Market Cap, NSE FFMC, and NSE Delivery Data pages mount the shared NSE status poller while loading. This keeps the login screen removed for those pages without changing the scheduler, Oracle writes, or market-data automation logic.

### Files changed

- `backend/app.py`
- `backend/tests/test_app_startup.py`
- `CHANGELOG.md`

### Validation

- `python -m pytest backend\tests\test_app_startup.py -q` passed (`11 passed`).
- `python -m compileall backend\app.py backend\tests\test_app_startup.py` passed.
- Live listener validation was inconclusive in this sandbox: the project launcher briefly passed `/api/health`, then the background Flask process exited before direct `Invoke-WebRequest` checks could connect. Flask test-client coverage confirms the unauthenticated auth path.

### Rollback

Restore files from `runtime/backups/2026-06-25_175939_v89-public-nse-status-support-api/`, `runtime/backups/2026-06-25_175939_v89-public-nse-status-support-api_2/`, and `runtime/backups/2026-06-25_180416_v89-public-nse-status-support-api/`, then restart Flask.

## v93-shared-nav-spa-routing - 2026-06-25 18:05:00 IST

Fixed slow page-to-page navigation from shared React nav bars by intercepting same-origin app links and routing them through the existing React shell instead of forcing a full Flask document reload. This covers the shared header/dropdowns plus migrated Sector, Fyers, Strategy, Fundamental, auth, and sector selector/redirect navigation surfaces. External links, modified clicks, new-tab clicks, and non-page URLs still use normal browser behavior.

### Files changed

- `frontend/src/utils/internalNavigation.ts`
- `frontend/src/components/navigation/CvingLegacyHeader.tsx`
- `frontend/src/App.tsx`
- `frontend/src/pages/sector/SectorMigrationLayout.tsx`
- `frontend/src/pages/fyers/FyersMigrationLayout.tsx`
- `frontend/src/pages/strategy/StrategyMigrationLayout.tsx`
- `frontend/src/pages/sector/SectorWiseStocksPage.tsx`
- `frontend/src/pages/sector/SectorStocksRedirect.tsx`
- `frontend/src/components/fundamental/layout/FundamentalNavbar.tsx`
- `frontend/src/components/fundamental/layout/FundamentalHeader.tsx`
- `frontend/src/pages/auth/AuthShell.tsx`
- `frontend/tests/headerDropdownStyles.test.ts`
- `CHANGELOG.md`

### Validation

- `cd frontend; npm.cmd run typecheck` passed before and after the final source alignment check.
- `cd frontend; npm.cmd run test -- tests\headerDropdownStyles.test.ts` first hit the known sandbox Vite config access-denied issue, then passed outside the sandbox (`6 passed`).
- `cd frontend; npm.cmd run build` first hit the same sandbox Vite config access-denied issue, then passed outside the sandbox and refreshed `frontend/dist`; the existing large-chunk warning remains.
- Browser-plugin rendered QA was blocked because the in-app browser runtime rejected `browser-client` as untrusted in this session.
- A later redundant rebuild after a non-functional App cleanup was rejected by the host usage limit; that cleanup was reverted so source matches the successfully built navigation bundle.

### Rollback

Restore files from `runtime/backups/2026-06-25_180017_v93-header-spa-navigation/` and `runtime/backups/2026-06-25_180228_v93-header-spa-navigation-extra-nav/`, remove `frontend/src/utils/internalNavigation.ts`, rebuild `frontend/dist`, then reload the affected React routes.

## v92-header-dropdown-first-click-navigation - 2026-06-25 17:45:00 IST

Fixed the shared React header dropdowns so the first click on Sector, Technicals, Database, FyersAPI, or Strategy opens the dropdown instead of navigating to that section's default page. The dropdown menu items keep their existing canonical `/app/...` routes, and hover/focus behavior remains supported through the same shared CSS path.

### Files changed

- `frontend/src/components/navigation/CvingLegacyHeader.tsx`
- `frontend/src/styles.css`
- `frontend/tests/headerDropdownStyles.test.ts`
- `CHANGELOG.md`

### Validation

- `cd frontend; npm.cmd run typecheck` passed.
- `cd frontend; npm.cmd run test -- tests\headerDropdownStyles.test.ts` first hit the known sandbox Vite config access-denied issue, then passed outside the sandbox (`4 passed`).
- `cd frontend; npm.cmd run build` first hit the same sandbox Vite config access-denied issue, then passed outside the sandbox and refreshed `frontend/dist`; the existing large-chunk warning remains.
- Browser-plugin rendered QA was blocked because the in-app browser runtime rejected `browser-client` as untrusted in this session.

### Rollback

Restore files from `runtime/backups/2026-06-25_174215_v92-header-dropdown-click-nav/`, rebuild `frontend/dist`, then reload affected React routes such as `/app/technical/ema`, `/app/sector/rotation`, `/app/database/stock-history`, `/app/fyers/automation`, and `/app/strategy`.

## v91-dashboard-ticker-bottom-placement - 2026-06-25 17:36:48 IST

Moved the `/app/dashboard` marquee/ticker strip to the bottom of the dashboard content area by making the dashboard main region an explicit flex column and pushing the ticker with `mt-auto`. This is a layout-only change; dashboard data loading, API contracts, and Oracle flow are unchanged.

### Files changed

- `frontend/src/pages/dashboard/DashboardPage.tsx`
- `CHANGELOG.md`

### Validation

- `cd frontend; npm.cmd run typecheck` passed.
- `cd frontend; npm.cmd run build` initially hit the known sandbox Vite config access-denied issue, then passed outside the sandbox and refreshed `frontend/dist`; the existing large-chunk warning remains.

### Rollback

Restore files from `runtime/backups/2026-06-25_173604_v91-dashboard-ticker-bottom/`, rebuild `frontend/dist`, then reload `/app/dashboard`.

## v90-dashboard-24h-cache-ticker-footer - 2026-06-25 17:27:12 IST

Fixed `/app/dashboard` so a fresh local dashboard payload is reused for up to 24 hours before normal page-load or poll requests run, keeping the page in `Live` state across browser refreshes instead of showing the loading/syncing state for already-current data. The Refresh button still forces the existing dashboard refresh path.

### Files changed

- `frontend/src/pages/dashboard/DashboardPage.tsx`
- `frontend/src/styles.css`
- `frontend/tests/homeDashboardMigration.test.tsx`
- `CHANGELOG.md`

### Validation

- `cd frontend; npm.cmd run typecheck` passed.
- `cd frontend; npm.cmd run test -- tests\homeDashboardMigration.test.tsx` initially hit the known sandbox Vite config access-denied issue, then ran outside the sandbox. The three dashboard/ticker assertions passed; two unrelated existing baseline assertions still fail (`HomePage` missing `CvingTrade25X AI`, and legacy breadth fallback expecting `Nifty500`).
- `cd frontend; npm.cmd run build` initially hit the same sandbox Vite config access-denied issue, then passed outside the sandbox and refreshed `frontend/dist`; the existing large-chunk warning remains.
- `Invoke-WebRequest http://127.0.0.1:5055/app/dashboard -UseBasicParsing` returned HTTP `200`.
- Browser-plugin screenshot QA was blocked because the in-app browser runtime rejected `browser-client` as untrusted in this session.

### Rollback

Restore files from `runtime/backups/2026-06-25_172238_v90-dashboard-cache-ticker-footer/`, rebuild `frontend/dist`, then reload `/app/dashboard`.

## v89-stock-history-ltc-date-format - 2026-06-25 09:20:50 IST

Fixed the Stock EOD History `LATEST_LTC_DATE` KPI and toolbar value so backend HTTP-date strings such as `Wed, 24 Jun 2026 00:00:00 GMT` render as `24-06-2026` only. The change is page-scoped and reuses the existing database date-only formatter; no backend API or Oracle flow changed.

### Files changed

- `frontend/src/pages/ops/StockHistoryPage.tsx`
- `frontend/tests/stockHistoryPage.test.ts`
- `CHANGELOG.md`

### Validation

- `npm.cmd run test -- tests\stockHistoryPage.test.ts` first failed with `formatStockHistoryLtcDate is not a function`, then passed after the fix (`4 passed`).
- `npm.cmd run typecheck` passed from `frontend/`.
- `npm.cmd run build` passed outside the sandbox and refreshed `frontend/dist`; the existing Vite large-chunk warning remains.

### Rollback

Restore changed files from `runtime/backups/2026-06-25_092050_v1/`, rebuild `frontend/dist`, then reload `/app/database/stock-history`.

## v88-stock-history-sync-card-fallback - 2026-06-25 08:56:04 IST

Fixed the Stock EOD History sync KPI fallback so an older or not-yet-restarted stats payload no longer renders `Synched Rows = 0` and `Unsynched Rows = 0` when total rows are available. The page now treats missing/null sync fields as unknown, derives `Synched Rows = Total No Of Rows - Unsynched Rows`, and uses pending rows as the unsynched fallback. Live service verification showed the current backend returns `stock_eod_record_count=2922`, `stock_eod_synched_rows=2922`, and `stock_eod_unsynched_rows=0`; this patch protects the UI when the running payload is stale or missing the additive sync fields.

### Files changed

- `frontend/src/pages/ops/StockHistoryPage.tsx`
- `frontend/tests/stockHistoryPage.test.ts`
- `CHANGELOG.md`

### Validation

- Read-only backend service check returned `stock_eod_record_count=2922`, `stock_eod_synched_rows=2922`, and `stock_eod_unsynched_rows=0`.
- `npm.cmd run test -- tests\stockHistoryPage.test.ts` first failed with `buildStockHistorySyncCards is not a function`, then passed after the fix (`2 passed`).
- `npm.cmd run typecheck` passed from `frontend/`.
- `npm.cmd run build` passed outside the sandbox and refreshed `frontend/dist`; the existing Vite large-chunk warning remains.

### Rollback

Restore changed files from `runtime/backups/2026-06-25_085604_v1/`, remove `frontend/tests/stockHistoryPage.test.ts`, rebuild `frontend/dist`, then restart Flask if the app process is already running.

## v87-stock-history-sync-toast-delete-dialog - 2026-06-25 08:32:52 IST

Added Stock EOD History synced/unsynced row cards backed by source-to-DEV-and-Oracle stat counts, changed global merge completion toasts to show messages such as `123 merged both the tables.`, and added page-level manual merge start/up-to-date feedback. Replaced the inline delete confirmation with a black-backdrop popup that uses a `DELETE` dropdown confirmation and shows before/after delete messages while preserving the existing backend delete endpoint.

### Files changed

- `backend/services/marketdata_service.py`
- `backend/routes/marketdata.py`
- `backend/tests/test_marketdata_clear_stock_eod_route.py`
- `frontend/src/pages/ops/StockHistoryPage.tsx`
- `frontend/src/components/app/NseJobGlobalPoller.tsx`
- `frontend/tests/nseJobGlobalPoller.test.ts`
- `CHANGELOG.md`

### Validation

- `python -m compileall backend` passed.
- `python -m pytest backend\tests\test_marketdata_stock_history_sync.py backend\tests\test_marketdata_clear_stock_eod_route.py -q` passed (`12 passed`).
- `npm.cmd run typecheck` passed from `frontend/`.
- `npm.cmd run test -- tests\nseJobGlobalPoller.test.ts` passed outside the sandbox after the first sandboxed Vitest attempt hit the known Vite config access-denied issue (`3 passed`).
- `npm.cmd run build` passed outside the sandbox and refreshed `frontend/dist`; the existing Vite large-chunk warning remains.
- `python scripts\scan_api_duplicates.py` passed (`routes=188`, `exact_duplicates=0`, `similar_paths=21`).

### Rollback

Restore files from `runtime/backups/2026-06-25_083252_v1/`, rebuild `frontend/dist`, then restart Flask.

## v88-public-nse-database-pages - 2026-06-25 17:34:04 IST

Removed the login/JWT route gate for exactly three React database pages: NSE Market Cap, NSE FFMC, and NSE Delivery Data. Added matching Flask auth exemptions for their NSE API families and the shared trading-day verification endpoint so unauthenticated page loads and page-owned API calls no longer fail with `401`.

### Files changed

- `frontend/src/App.tsx`
- `backend/app.py`
- `frontend/tests/protectedRoute.test.ts`
- `backend/tests/test_app_startup.py`
- `CHANGELOG.md`

### Validation

- `npm.cmd run typecheck` passed from `frontend/`.
- `python -m pytest backend\tests\test_app_startup.py -q` passed (`11 passed`).
- `python -m compileall backend` passed.
- Focused Vitest and a repeat `npm.cmd run build` were blocked in the current sandbox by Vite/esbuild filesystem access denial (`Cannot read directory "../../../..": Access is denied.`). The current `frontend/dist` bundle was inspected and contains the new public NSE route list, but the build command did not complete successfully in this session.

### Rollback

Restore files from `runtime/backups/2026-06-25_173229_v88-public-nse-database-pages/` and `runtime/backups/2026-06-25_173404_v88-public-nse-database-pages/`, rebuild `frontend/dist`, then restart Flask.

## v87-trading-day-verification-manual-refresh - 2026-06-25 17:29:43 IST

Stopped the NSE Market Cap, NSE FFMC, and NSE Delivery Data pages from automatically calling the shared trading-day verification endpoint on initial render. The backend `/api/market-calendar/trading-day-verification` logic and manual Refresh Verification action remain intact, but the page load no longer waits on or surfaces the 60-second verification timeout.

### Files changed

- `frontend/src/pages/ops/TradingDayVerificationPanel.tsx`
- `frontend/tests/tradingDayVerificationPanel.test.ts`
- `CHANGELOG.md`

### Validation

- `npm.cmd run typecheck` passed from `frontend/`.
- Focused Vitest and a repeat `npm.cmd run build` were blocked in the current sandbox by Vite/esbuild filesystem access denial (`Cannot read directory "../../../..": Access is denied.`). The current `frontend/dist` bundle was inspected and contains the new public NSE route list, but the build command did not complete successfully in this session.

### Rollback

Restore files from `runtime/backups/2026-06-25_172943_v87-trading-day-verification-manual-refresh/`, remove `frontend/tests/tradingDayVerificationPanel.test.ts`, rebuild `frontend/dist`, then restart Flask.

## v86-nse-database-page-date-source-toast - 2026-06-25 08:10:28 IST

Aligned the NSE Market Cap, NSE FFMC, and NSE Delivery Data React pages so Trade Date cards and Latest Rows Fetched dates use the latest row `TRADE_DATE` in `DD-MM-YYYY` format, changed Manual Rows / Automation Rows to `Y`/`N` extraction-source flags, removed the future-pending-trading-dates disclosure from the UI only, and extended global NSE DB-insert completion toasts for the three persistent job endpoints.

### Files changed

- `frontend/src/adapters/databasePageAdapter.ts`
- `frontend/src/pages/ops/nseAutomationConfigs.ts`
- `frontend/src/pages/ops/NseAutomationPage.tsx`
- `frontend/src/pages/ops/TradingDayVerificationPanel.tsx`
- `frontend/src/components/app/NseJobGlobalPoller.tsx`
- `frontend/tests/databaseAdapters.test.ts`
- `frontend/tests/nseJobGlobalPoller.test.ts`
- `CHANGELOG.md`

### Validation

- `npm.cmd run typecheck` passed.
- Focused Vitest validation passed: `npm.cmd run test -- tests/databaseAdapters.test.ts tests/nseJobGlobalPoller.test.ts tests/nseAutomationPage.test.ts` (`18 passed`).
- `npm.cmd run build` passed and refreshed `frontend/dist`.
- Full `npm.cmd run test` was rerun outside the sandbox; the changed tests passed, but the suite still has unrelated pre-existing failures in header/migration/technical adapter tests.

### Rollback

Restore files from `runtime/backups/2026-06-25_080957_v86-nse-ui-date-source-toast/` and `runtime/backups/2026-06-25_081028_v86-nse-ui-date-source-toast/`, rebuild `frontend/dist`, then restart Flask.

## v85-stock-history-merge-oracle-on-clause-fix - 2026-06-24 20:13:12 IST

Fixed stock-history DEV/ORACLE merge failures caused by Oracle rejecting an update to a MERGE `ON`-clause column, and normalized completion toasts to show merged row counts as `Dev:<count> and Oracle:<count>`.

### Files changed

- `backend/services/marketdata_service.py`
- `backend/routes/marketdata.py`
- `backend/tests/test_marketdata_stock_history_sync.py`
- `frontend/src/components/app/NseJobGlobalPoller.tsx`
- `frontend/tests/nseJobGlobalPoller.test.ts`
- `CHANGELOG.md`

### Validation

- Stock-history reconciliation no longer updates `tgt.symbol` inside the Oracle MERGE update block, avoiding `ORA-38104` while preserving the existing `SYMBOL + TRADING_DATE` match key.
- Manual and scheduled merge status now treats updated rows as latest data work, not as an up-to-date skip.
- Successful merge toasts render explicit DEV/ORACLE merged counts such as `Dev:123 and Oracle:123`.

### Rollback

Restore files from `runtime/backups/2026-06-24_201312_v1/`, rebuild the frontend bundle, then restart Flask.

## v84-stock-history-sync-reconciliation - 2026-06-22 10:42:17 IST

Replaced the insert-only/latest-date-only stock history merge repair with a full `SYMBOL + TRADING_DATE` reconciliation that updates changed OHLCV rows, inserts missing rows into both DEV and ORACLE, repairs cross-target key drift, and validates post-merge parity.

### Files changed

- `backend/services/marketdata_service.py`
- `backend/tests/test_marketdata_stock_history_sync.py`
- `CHANGELOG.md`

### Validation

- `merge_latest()` now reconciles all current `STOCK_EOD_HISTORY` keys into both targets, not just the latest trading date and not just DEV.
- Auto-merge availability now treats full-source drift and DEV/ORACLE parity gaps as merge work, so scheduler/manual merge does not falsely report up-to-date when older keys are still unsynced.
- Backend payload now exposes post-merge validation counts for source coverage and DEV/ORACLE row parity.

### Rollback

Restore files from `runtime/backups/2026-06-22_104217_v84-stock-history-sync-reconciliation/`, then restart Flask.

## v83-fyers-auth-timeout-reconciliation - 2026-06-21 13:25:00 IST

Fixed a callback-boundary race where FYERS successfully saved a valid access token at the two-minute deadline but the parent authorization job still marked the result as `STALE_CALLBACK`.

### Files changed

- `backend/services/marketdata_service.py`
- `backend/tests/test_marketdata_fyers_proxy.py`
- `CHANGELOG.md`

### Validation

- Authorization timeout/failure handling now reconciles a newly issued, unexpired token against the live FYERS profile before declaring the callback stale.
- Live auth-status refresh repairs an existing false `STALE_CALLBACK` state when the token was issued at the invalidation boundary and the profile probe succeeds.
- The current FYERS token was reconciled to `AUTHENTICATED` with `canExtract=true`; no extraction job was launched automatically.

### Rollback

Restore files from `runtime/backups/2026-06-21_131958_v83-fyers-auth-timeout-reconciliation/`, then restart Flask.

## v82-fyers-strict-auth-gate - 2026-06-21 12:45:00 IST

Added a strict FYERS authentication gate so extraction and insertion jobs cannot be created until same-day token metadata and a live FYERS profile validation both succeed.

### Files changed

- `backend/services/marketdata_service.py`
- `backend/routes/marketdata.py`
- `backend/tests/test_marketdata_fyers_proxy.py`
- `frontend/src/pages/fyers/FyersAutomationPage.tsx`
- `frontend/src/pages/fyers/fyersPageUtils.ts`
- `frontend/tests/fyersAutomationPage.test.tsx`
- `docs/api-catalog.md`
- `CHANGELOG.md`

### Validation

- Invalid, expired, missing, stale-callback, and unvalidated FYERS auth states return HTTP `428` with `canExtract=false` before a job ID or Oracle extraction run is created.
- Authorization jobs no longer create `FYERS_EXTRACTION_RUNS` rows or append symbol extraction summaries.
- The React page disables single and batch extraction actions until auth status returns `canExtract=true`, and auth-required start failures are not shown as unknown extraction starts.
- Authorization state uses a unique one-time state with a two-minute lifetime; stale callbacks and invalid refresh-token failures now have distinct user-facing statuses.

### Rollback

Restore files from `runtime/backups/2026-06-21_122036_v82-fyers-strict-auth-gate/`, rebuild the frontend bundle, and restart Flask.

## v81-ffmc-quote-session-coordination - 2026-06-21 05:40:00 IST

Coordinated NSE quote-session warmup across the shared FFMC/MCAP quote workers so a 990-symbol FFMC run no longer amplifies `401/403` retries by making every worker perform its own warmup cycle.

### Files changed

- `backend/services/nse_mcap_service.py`
- `backend/tests/test_nse_mcap_service.py`
- `CHANGELOG.md`

### Validation

- Shared NSE quote clients now publish a fresh warmed cookie snapshot after a successful response, and new worker clients import that snapshot instead of repeating warmup.
- Concurrent forced warmups are serialized behind one shared in-flight gate, so only one worker performs the multi-request NSE warmup while the others wait and reuse the refreshed session.
- Added backend tests covering coordinated concurrent warmup and reuse of a recent shared session without another warmup pass.

### Rollback

Restore files from `runtime/backups/2026-06-21_053712_v81_ffmc_quote_session_coordination/`, then rerun the targeted backend tests.

## v80-fyers-no-timeout-resilient-polling - 2026-06-20 09:45:57 IST

Removed synthetic frontend request timeouts from FYERS Automation and failed-symbol list/rerun operations, and made active-job polling preserve the last known snapshot during transient refresh failures.

### Files changed

- `frontend/src/api/client.ts`
- `frontend/src/services/api/fyersApi.ts`
- `frontend/src/pages/fyers/FyersAutomationPage.tsx`
- `frontend/tests/apiClient.test.ts`
- `frontend/tests/fyersApi.test.ts`
- `frontend/tests/fyersAutomationPage.test.tsx`
- `CHANGELOG.md`

### Validation

- `timeoutMs: null` and `timeoutMs: 0` disable synthetic timeout controllers while caller lifecycle signals remain supported.
- FYERS Automation and failed-symbol list/rerun calls use no-timeout requests; Holdings, NIFTY500 Sync, and failed-symbol deletion retain existing budgets.
- Poll failures preserve job ID, cards, logs, telemetry, and Stop availability; only explicit `FYERS_JOB_NOT_FOUND` clears a stale job.
- Backend `FAILED` and `ERROR` statuses are the only terminal states classified as extraction failures.

### Rollback

Restore files from `runtime/backups/2026-06-20_093706_v1/`, remove `frontend/tests/apiClient.test.ts`, then rebuild the frontend bundle.

## v79-fyers-form-row-alignment - 2026-06-20 09:10:01 IST

Aligned the Single Stock and Direct API Batch date/resolution rows on the same desktop baseline without changing mobile stacking or FYERS behavior.

### Files changed

- `frontend/src/pages/fyers/FyersAutomationPage.tsx`
- `frontend/src/styles.css`
- `frontend/tests/fyersAutomationPage.test.tsx`
- `CHANGELOG.md`

### Validation

- Direct API Batch reserves a measured 72px alignment slot so CSS grid free-space distribution places both date/resolution rows on the same baseline.
- The alignment spacer is removed below 900px when the cards stack.
- Added a regression test for the batch-card alignment slot.

### Rollback

Restore files from `runtime/backups/2026-06-20_091001_v1/`, then rebuild the frontend bundle.

## v78-fyers-automation-card-layout - 2026-06-20 09:03:35 IST

Aligned the active FYERS Automation cards and restored matching full-width primary actions without changing extraction, insertion, or API behavior.

### Files changed

- `frontend/src/pages/fyers/FyersAutomationPage.tsx`
- `frontend/src/styles.css`
- `frontend/tests/fyersAutomationPage.test.tsx`
- `CHANGELOG.md`

### Validation

- Both cards continue to use the shared two-column desktop grid and three-column date/resolution grid.
- `Fetch & Insert` and `Run Batch Insert` now use the same full-width button component behavior and bottom-aligned action row.
- Added a regression test covering both shared action rows and full-width primary buttons.

### Rollback

Restore files from `runtime/backups/2026-06-20_090145_v1/`, then rebuild the frontend bundle.

## v75-dashboard-ticker-text-size - 2026-06-20 08:24:41 IST

Reduced dashboard ticker text height by 50 percent while preserving the right-to-left direction and 110-second animation duration.

### Files changed

- `frontend/src/styles.css`
- `CHANGELOG.md`

### Validation

- Stock ticker text reduced from 110px to 55px.
- Group labels and dividers reduced from 48px to 24px.

### Rollback

Restore files from `runtime/backups/2026-06-20_082441_v1/`.

## v74-dashboard-ticker-direction-speed - 2026-06-20 08:22:56 IST

Changed the dashboard ticker to scroll from right to left and reduced its movement speed by 50 percent.

### Files changed

- `frontend/src/styles.css`
- `CHANGELOG.md`

### Validation

- Ticker keyframes now move from `translateX(0)` to `translateX(-50%)`.
- Animation duration increased from 55 seconds to 110 seconds.

### Rollback

Restore files from `runtime/backups/2026-06-20_082256_v1/`.

## v77-fyers-button-row-alignment - 2026-06-20 08:47:47 IST

Moved the Single Stock `Fetch & Insert` action into the same horizontal action-row structure used by the Direct API Batch `Run Batch Insert` action so both buttons render with the same content-width pattern on the live UI.

### Files changed

- `frontend/src/pages/fyers/FyersAutomationPage.tsx`
- `CHANGELOG.md`

### Validation

- The Single Stock button is no longer a direct child of the FYERS card block, so it no longer matches the page CSS rule that forced full-width card buttons.
- Both action buttons now live inside matching `flex flex-wrap gap-2` wrappers and render as horizontal content-width buttons after rebuilding the frontend bundle.

### Rollback

Restore files from `runtime/backups/2026-06-20_084747_v77-fyers-button-row-alignment/`, then rebuild the frontend bundle.

## v76-fyers-single-button-auto-width - 2026-06-20 08:40:57 IST

Matched the Single Stock `Fetch & Insert` button width to the Direct API Batch `Run Batch Insert` button so both actions hug their content instead of stretching across the card.

### Files changed

- `frontend/src/pages/fyers/FyersAutomationPage.tsx`
- `CHANGELOG.md`

### Validation

- The Single Stock action now uses `w-auto self-start`, matching the scoped button-width treatment already used by the Direct API Batch action.

### Rollback

Restore files from `runtime/backups/2026-06-20_084057_v76-fyers-single-button-auto-width/`, then rerun the focused frontend validation commands.

## v75-fyers-batch-button-auto-width - 2026-06-20 08:34:30 IST

Set the `Run Batch Insert` action in the `/app/fyers/automation` Direct API Batch card to explicit auto-width so it hugs its content instead of stretching.

### Files changed

- `frontend/src/pages/fyers/FyersAutomationPage.tsx`
- `CHANGELOG.md`

### Validation

- The Direct API Batch button now uses `w-auto self-start` on the page component, scoped only to that action.

### Rollback

Restore files from `runtime/backups/2026-06-20_083430_v75-fyers-batch-button-auto-width/`, then rerun the focused frontend validation commands.

## v74-fyers-remove-rerun-buttons - 2026-06-20 08:25:14 IST

Removed the `Rerun Failed` and `Rerun Remaining` buttons from the `/app/fyers/automation` batch-action row.

### Files changed

- `frontend/src/pages/fyers/FyersAutomationPage.tsx`
- `frontend/tests/fyersAutomationPage.test.tsx`
- `CHANGELOG.md`

### Validation

- The FYERS automation page now shows only the primary `Run Batch Insert` action in that batch-action button group.
- Updated the render test so those two removed labels no longer appear in the page markup.

### Rollback

Restore files from `runtime/backups/2026-06-20_082514_v74-fyers-remove-rerun-buttons/`, then rerun the focused frontend validation commands.

## v73-fyers-immediate-stop - 2026-06-20 08:02:40 IST

Changed the FYERS automation stop flow so clicking `Stop` requests an immediate stop instead of intentionally waiting for the current symbol to complete.

### Files changed

- `backend/services/marketdata_service.py`
- `backend/tests/test_marketdata_fyers_proxy.py`
- `frontend/src/pages/fyers/FyersAutomationPage.tsx`
- `CHANGELOG.md`

### Validation

- Stop requests now set immediate-stop messaging in both the API response and the React page.
- The direct FYERS fetch path now checks the stop flag before fetch, between fetch ranges, during request pacing sleep, and before Oracle upsert so it can unwind without waiting for the rest of the symbol loop.
- Subprocess-backed FYERS work now uses `kill()` on stop instead of a soft terminate.

### Rollback

Restore files from `runtime/backups/2026-06-20_080240_v73-fyers-immediate-stop/`, then rerun the targeted backend/frontend validation commands.

## v72-fyers-authorize-async - 2026-06-20 07:31:03 IST

Made `/api/marketdata/fyers/authorize` non-blocking so the FYERS automation page no longer waits on the full external token flow inside the request thread.

### Files changed

- `backend/services/marketdata_service.py`
- `backend/routes/marketdata.py`
- `backend/tests/test_marketdata_fyers_proxy.py`
- `frontend/src/services/api/fyersApi.ts`
- `frontend/src/pages/fyers/FyersAutomationPage.tsx`
- `frontend/tests/fyersApi.test.ts`
- `frontend/tests/fyersAutomationPage.test.tsx`
- `CHANGELOG.md`

### Validation

- `/api/marketdata/fyers/authorize` now returns quickly with either `ALREADY_AUTHENTICATED` or a background auth-job handle instead of blocking until the external FYERS auth flow finishes.
- Added `/api/marketdata/fyers/extract/start`, `/extract/status/<job_id>`, `/extract/stop/<job_id>`, `/extract/rerun-failed`, and `/extract/rerun-remaining` as backward-compatible aliases over the existing automation job flow.
- The FYERS automation page now reconnects to background authorization jobs and exposes the login URL from the Active Job panel when the backend emits it.

### Rollback

Restore files from `runtime/backups/2026-06-20_073103_v72-fyers-authorize-async/`, then rebuild the frontend bundle if you roll back the React changes.

## v71-dashboard-css-ticker - 2026-06-20 07:21:32 IST

Replaced the deprecated native dashboard `<marquee>` with a continuous CSS-animated React ticker. The duplicated ticker stream now moves reliably to the right whenever market-mover items are available.

### Files changed

- `frontend/src/pages/dashboard/DashboardPage.tsx`
- `frontend/src/styles.css`
- `frontend/tests/homeDashboardMigration.test.tsx`
- `CHANGELOG.md`

### Validation

- The ticker renders a CSS animation track instead of a browser-dependent `<marquee>`.
- The animation moves from `translateX(-50%)` to `translateX(0)` for rightward motion.
- Added regression assertions for the animation track and removal of native marquee markup.

### Rollback

Restore files from `runtime/backups/2026-06-20_072132_v1/`.

## v70-dashboard-ticker-always-animates - 2026-06-20 07:12:40 IST

Removed the dashboard ticker gate that kept the marquee static until a live `ltc_date` was present. Any populated ticker payload now keeps scrolling to the right.

### Files changed

- `frontend/src/pages/dashboard/DashboardPage.tsx`
- `frontend/tests/homeDashboardMigration.test.tsx`
- `CHANGELOG.md`

### Validation

- `shouldAnimateDashboardTicker(...)` now returns `true` whenever ticker items exist.
- Added a regression assertion for populated vs empty ticker groups.

### Rollback

Restore files from `runtime/backups/2026-06-20_071240_v1-dashboard-ticker-always-animates/` if you need the old ltc-date-gated behavior back.

## v69-dashboard-ticker-scroll-right - 2026-06-20 06:48:50 IST

Updated the dashboard ticker marquee so it scrolls to the right again.

### Files changed

- `frontend/src/pages/dashboard/DashboardPage.tsx`
- `frontend/tests/homeDashboardMigration.test.tsx`
- `CHANGELOG.md`

### Validation

- Added a focused markup assertion for `direction="right"`.

### Rollback

Restore files from `runtime/backups/2026-06-20_064850_v1-dashboard-scroll-right/` if you need to revert the marquee direction only.

## v68-fyers-ltc-date-display-format - 2026-06-19 09:00:00 IST

Changed only the `/app/fyers/automation` `LTC_DATE` card presentation from ISO date-time values such as `2026-06-18T00:00:00Z` to `DD-MM-YYYY`, for example `18-06-2026`.

The API response, job payload, Oracle values, filtering, extraction, and persistence logic remain unchanged.

### Files changed

- `frontend/src/pages/fyers/FyersAutomationPage.tsx`
- `frontend/tests/fyersAutomationPage.test.tsx`
- `CHANGELOG.md`

### Validation

- Added focused coverage for ISO date-time, ISO date-only, and empty fallback display.
- Passed `npm.cmd run typecheck`.
- `npm.cmd run build` could not load `frontend/vite.config.ts` inside the managed sandbox (`Cannot read directory "../../../..": Access is denied`). The external build/test approval was unavailable because the environment usage limit had been reached.
- The focused Vitest command could not be executed because the external tool approval was rejected after the environment usage limit was reached.

### Rollback

Restore files from `runtime/backups/2026-06-19_085716_v68-fyers-ltc-date-display-format/manifest.json`, rebuild the frontend, and hard-refresh the page.

## v67-fyers-latest-active-timeout-race - 2026-06-19 08:31:00 IST

Fixed the remaining `/app/fyers/automation` startup diagnostic:

`GET /api/marketdata/fyers/automation/latest-active-job` → `Request timeout after 10000ms`.

### Root cause

The Flask access log proves the request was not failing in the FYERS handler. The browser cancelled the request after its explicit 10-second client budget at approximately `08:12:44 IST`, while Flask completed the same request successfully with HTTP 200 at `08:12:49 IST`.

The React page rendered from a locally valid cached session while centralized `/api/auth/session` verification continued in the background. Its FYERS active-job discovery effect immediately issued another protected request, causing both requests to compete for Oracle-backed session validation during startup. The active-job request therefore exceeded the artificial 10-second budget even though the server completed it.

### Changes

- Active-job discovery now waits until centralized session verification finishes. The page remains visible; only the protected background discovery call is deferred.
- Removed the shared 10-second polling budget from `latest-active-job`; this optional startup discovery now has a dedicated 60-second ceiling.
- Marked active-job discovery diagnostics as suppressed because failure to reconnect an old job must not raise a page-level API error or prevent starting a new run.
- Kept active-job status polling at its existing short budget because polling is retryable and the extraction job continues independently.

### Files changed

- `frontend/src/services/api/fyersApi.ts`
- `frontend/src/pages/fyers/FyersAutomationPage.tsx`
- `frontend/tests/fyersApi.test.ts`
- `frontend/tests/fyersAutomationPage.test.tsx`
- `CHANGELOG.md`

### Validation

- Passed focused frontend tests: `14 passed`.
- Passed `npm.cmd run typecheck`.
- Passed `npm.cmd run build`; Flask build output now references `react-assets/index-uTua6sdp.js`. The existing large-chunk warning remains.
- Passed focused backend route regression: `1 passed`.
- Passed API duplicate scan: `routes=183`, `exact_duplicates=0`, `similar_paths=21`.
- Confirmed the running Flask server served `/app/fyers/automation` with HTTP 200 and the new `index-uTua6sdp.js` production bundle without restarting the active background process.

### Rollback

Restore files from `runtime/backups/2026-06-19_082257_v67-fyers-latest-active-timeout-race/manifest.json`, rebuild the frontend, and hard-refresh the browser.

## v66-fyers-auth-background-and-incremental-fetch - 2026-06-19 07:35:00 IST

Removed the full-screen secure-session wait for users who already have a locally valid session. Centralized `/api/auth/session` verification still runs and remains authoritative; unauthenticated users continue to wait for verification and invalid sessions still redirect to login. Shared page-level guards now follow the centralized authenticated state instead of adding a second visible verification gate.

The FYERS automation status recovery path now avoids loading up to 2,000 symbol rows for `latest-active-job` and `/automation/status/<job_id>`. Legacy `/jobs/<job_id>` responses retain their existing symbol-inclusive behavior.

FYERS extraction now narrows non-force-refresh requests to missing trading-date runs plus any new tail after the latest known trading date. This preserves `FYERS -> STOCK_EOD_HISTORY -> Auto/Manual Merge -> NSE_NIFTY500_DAILY_RAW_DATA_DEV` while avoiding repeated 1998-to-current chunk scans for symbols that already have historical data. Force refresh still requests the full selected date range.

ETA calculation now records the first completed symbol and excludes first-symbol startup overhead from later estimates, preventing initialization, CSV loading, tracking-row creation, and first-fetch cost from being multiplied across all remaining symbols.

### Files changed

- `frontend/src/components/auth/ProtectedRoute.tsx`
- `frontend/src/pages/technical/technicalPageGuards.ts`
- `frontend/tests/protectedRoute.test.ts`
- `backend/routes/marketdata.py`
- `backend/services/marketdata_service.py`
- `backend/tests/test_marketdata_fyers_proxy.py`
- `docs/api-catalog.md`
- `CHANGELOG.md`

### Validation

- Passed focused backend FYERS tests: `38 passed`.
- Passed focused frontend auth/FYERS tests: `16 passed`.
- Passed `npm.cmd run typecheck`.
- Passed `npm.cmd run build`; the existing large-chunk warning remains.
- Passed `python -m compileall backend\services\marketdata_service.py backend\routes\marketdata.py`.
- Passed API duplicate scan: `routes=183`, `exact_duplicates=0`, `similar_paths=21`; `docs/api-catalog.md` was regenerated.
- `python scripts\enterprise_validate.py` exceeded the six-minute command window before writing a fresh report. The focused regression, typecheck, build, compile, and duplicate-scan checks completed independently.

### Rollback

Restore changed files from:

- `runtime/backups/2026-06-19_072317_v66-fyers-auth-background-and-incremental-fetch/manifest.json`
- `runtime/backups/2026-06-19_072520_v66-fyers-auth-background-and-incremental-fetch/manifest.json`
- `runtime/backups/2026-06-19_073232_v66-fyers-auth-background-and-incremental-fetch/manifest.json`

Delete `frontend/tests/protectedRoute.test.ts`.

## v65-trading-day-verification-query-fast-path - 2026-06-18 09:52:46 IST

Removed the function-based `TRUNC(TRADE_DATE)` distinct/order path from the shared trading-day verification query used by the FFMC, Delivery, and Market Cap database pages. The `/api/market-calendar/trading-day-verification` route now reads distinct `TRADE_DATE` values directly within the requested year range and preserves the existing response payload.

This keeps the page/API contract unchanged while avoiding a heavier Oracle sort/function path on larger tables such as `CVING_NSE_DELIVERY_HIST`, which was timing out from `/app/database/nse-delivery-data` after the 60-second frontend client budget expired.

### Files changed

- `backend/services/nse_mcap_service.py`
- `backend/tests/test_nse_mcap_service.py`
- `CHANGELOG.md`

### Validation

- Passed `python -m pytest backend\tests\test_nse_mcap_service.py -q` (`44 passed`).
- Passed `python -m pytest backend\tests\test_marketdata_nse_pipeline_routes.py -q` (`12 passed`).
- Passed `python -m compileall backend`.
- Live unauthenticated probe to `http://127.0.0.1:5055/api/market-calendar/trading-day-verification?page=DELIVERY&refresh=0-0&year=2026` returned `401 Unauthorized` after about 34 seconds, so end-to-end browser-session validation still needs to be confirmed from the authenticated UI.

### Rollback

Restore the files listed in `runtime/backups/2026-06-18_095246_v65-trading-day-verification-query-fast-path/manifest.json`.

## v65-fyers-persisted-background-automation - 2026-06-18 10:10:00 IST

Replaced the FYERS batch page's long-request dependency with the existing Flask background-job runner plus additive Oracle job persistence. The React page now starts FYERS extraction quickly, polls by `job_id`, reconnects after refresh, supports graceful stop and failed/remaining reruns, and displays persisted symbol-level outcomes.

### Root cause

The 10-minute frontend timeout was only a temporary safety patch. Long FYERS extraction cannot be coupled to a browser request because 990-1500+ symbols outlive normal request budgets and browser navigation. The repository already had an in-process FYERS thread runner, but its state was memory-only and its UI lacked persisted recovery, rich counts, and actionable skipped-symbol details.

NSE MCAP, FFMC, and Delivery automation are separate pipelines and were not changed by this FYERS implementation.

### Backend and Oracle

- Added backward-compatible FYERS automation aliases under `/api/marketdata/fyers/automation/*` for start, status, path-based stop, resume, rerun failed, rerun remaining, latest active job, and skipped-symbol details.
- Kept extraction outside the Flask request thread and returned `job_id` with `STARTED`.
- Enhanced `FYERS_EXTRACTION_RUNS` and `FYERS_EXTRACTION_SYMBOL_STATUS` additively for restart recovery, stop flags, rich counts, reasons, and retry counts.
- Preserved symbol/trading-date duplicate protection and the immutable `STOCK_EOD_HISTORY` market-data flow.
- Added Oracle forward, rollback, and validation scripts. No SQL was executed against a live database during implementation.

### Frontend

- Added short request budgets for non-blocking start/status operations and restored auth-status to the existing 20-second backend fast-fallback budget.
- Added active-job recovery, continuous polling, graceful stop, Rerun Failed, and Rerun Remaining.
- Added Total, LTC_DATE, Inserted, Remaining, Failed, Skipped, Inserted Skipped, Invalid, and Errors cards.
- Added the `Currently Skipped Symbols` table with copy, TXT, and detailed CSV exports.

### Validation

- Backend FYERS scope: `45 passed`.
- Frontend focused FYERS scope: `11 passed`.
- Frontend TypeScript: passed.
- Frontend production build: passed; existing bundle-size warning remains.
- Backend compileall: passed.
- API duplicate scan: `routes=183`, `exact_duplicates=0`.
- `python scripts\enterprise_validate.py` exceeded the five-minute command window. Its broader backend suite is known to be long-running and its frontend report includes unrelated existing technical-screener legacy-route assertions; focused FYERS tests, typecheck, build, compileall, and duplicate scanning passed independently.

### Risks and rollback

- Live Oracle forward-script execution and restart recovery require DBA/environment validation.
- In-process FYERS worker threads do not survive process termination; persisted state supports recovery and safe rerun after restart.
- The external FYERS SDK does not expose a verified hard per-call cancellation guarantee in this repository; retries/backoff and browser-request independence are implemented, but a permanently blocked SDK call remains an operational risk to monitor.
- Restore Python files from `runtime/backups/2026-06-18_092653_2026_06_18-fyers-enterprise-job-v1/manifest.json`.
- Restore frontend files from `runtime/backups/2026-06-18_092618_v1/manifest.json`.
- Restore governance files from `runtime/backups/2026-06-18_092633_v65-fyers-background-jobs/manifest.json`.
- Remove the three new FYERS automation SQL files to roll back the code-only schema bundle. Run destructive rollback SQL only with DBA approval.

## v64-flask-launcher-port-and-visible-logs - 2026-06-18 08:45:00 IST

Fixed `start_flask_cvingtrade25x.bat` startup failures when `PORT` is overridden. The launcher health check used the configured port, but its generated runner omitted `PORT`, causing `backend/app.py` to fall back to 5055. The launcher also appeared silent because status messages were written only to a file and Flask was started hidden.

The generated runner now propagates `PORT`, launcher events are printed to the console and retained in `logs\cvingtrade25x_startup_events.log`, and failed launches print the last 200 Flask runtime lines while retaining the complete runtime stream in `logs\cvingtrade25x_flask.log`. Runtime lines are not duplicated into the startup log, avoiding mixed batch/PowerShell file encodings. The advertised startup wait is now enforced by one deadline-based health-check loop instead of up to 45 separate eight-second requests.

### Files changed

- `start_flask_cvingtrade25x.bat`
- `tests/backend/test_start_flask_launcher.py`
- `CHANGELOG.md`

### Validation

- Passed `python -m pytest tests\backend\test_start_flask_launcher.py -q` (`4 passed`).
- Default launcher invocation printed all startup decisions and returned `BAT_EXIT=0` after confirming the existing 5055 instance was healthy.
- Isolated launch with `PORT=50556` and background jobs disabled generated `set "PORT=50556"`, logged Flask on `http://127.0.0.1:50556`, and passed the launcher's `/api/health` check.
- Failure-path validation printed the launcher errors and Flask runtime tail to the console with `BAT_EXIT=1`.
- Existing live `http://127.0.0.1:5055/api/health` returned HTTP 200 with Oracle `db=up`.
- `python scripts\enterprise_validate.py` exceeded the 120-second validation window after refreshing `runtime/reports/api-duplicate-report.json`; no launcher/API duplicate failure was emitted before timeout.

### Rollback

Restore `start_flask_cvingtrade25x.bat` and `CHANGELOG.md` from `runtime/backups/2026-06-18_084232_v2026_06_18-flask-launcher-logging/manifest.json`, and delete `tests/backend/test_start_flask_launcher.py`.

## v64-remove-fyers-uniform-data-summary-card - 2026-06-18 09:10:18 IST

Removed the `Uniform_Data Available for Re-Run` summary card from `/app/fyers/automation`, including its Total Failed, Total Skipped, Total Rejected, Pending Re-Run, Open Uniform_Data, Copy Failed List, and Download TXT controls.

The dedicated `/app/fyers/failed-symbols` page and existing FYERS failed-symbol APIs remain unchanged. The automation page no longer performs the card-only failed-symbol summary request during initial load or after a completed job, reducing unnecessary request contention without changing extraction, rerun, Oracle, or market-data behavior.

### Files changed

- `frontend/src/pages/fyers/FyersAutomationPage.tsx`
- `frontend/tests/fyersAutomationPage.test.tsx`
- `CHANGELOG.md`

### Validation

- Passed focused FYERS tests: `4 passed` across `fyersAutomationPage.test.tsx` and `fyersApi.test.ts`.
- Passed `npm.cmd run typecheck`.
- Passed `npm.cmd run build`.
- Verified Flask serves `/react-assets/index-DyJjlIe-.js` with the removed card heading/button absent and the `Active Job` section retained.
- In-app browser screenshot validation was unavailable because the browser connection could not be established in this session.

### Rollback

Restore the files listed in `runtime/backups/2026-06-18_091018_v1/manifest.json`, rebuild the frontend, and refresh `/app/fyers/automation`.

## v63-fyers-auth-status-ten-minute-client-budget - 2026-06-18 07:44:55 IST

Increased only the React FYERS auth-status request budget from 120 seconds to 600 seconds (10 minutes) on `/app/fyers/automation`. The shared API client timeout remains enabled so a permanently hung request is still cancelled instead of waiting indefinitely.

The reported timeout at `2026-06-18T01:49:29Z` occurred while the Flask process was handling a long-running 990-symbol NSE quote-enrichment workflow with heavy CPU, memory, network, and log activity. The Flask access log contains no completed `/api/marketdata/fyers/auth-status` request near `07:19 IST`, which indicates the browser request did not complete the authenticated route before its 120-second client budget expired. The existing backend five-second cached/degraded FYERS auth fallback remains unchanged.

### Files changed

- `frontend/src/services/api/fyersApi.ts`
- `frontend/tests/fyersApi.test.ts`
- `CHANGELOG.md`

### Validation

- Passed focused regression test: `tests/fyersApi.test.ts` (`1 passed`).
- Passed frontend TypeScript validation: `npm.cmd run typecheck`.
- Passed production frontend build: `npm.cmd run build`.
- Full frontend suite result: `155 passed`, `18 failed`; the failures are existing migration/header/adapter assertions outside this FYERS timeout change.

### Rollback

Restore the changed existing files from `runtime/backups/2026-06-18_074259_v1/manifest.json`, delete `frontend/tests/fyersApi.test.ts`, rebuild the React frontend, and restart Flask so it serves the restored frontend build.

## v62-fyers-auth-status-refresh-contention-fix - 2026-06-17 20:34:00 IST

### Summary
Hardened `/api/marketdata/fyers/auth-status` so repeated `/app/fyers/automation` page loads do not wait behind an already-running live FYERS auth refresh. When the external FYERS project/token read is still in progress, the endpoint now immediately serves the repo-local cached/degraded auth snapshot and includes the cached-snapshot warning in the UI-visible message.

### Root Cause
The endpoint already had a fast fallback, but the duplicate-refresh branch returned a new unsignaled event when another live refresh was active. A second auth-status request could therefore wait on an event that no worker would ever signal, delaying the page before falling back. With the frontend timeout already raised to 120 seconds, the visible symptom became a long browser-side timeout instead of a clear cached/degraded auth-status response.

### Files Changed
- `backend/services/marketdata_service.py`
- `backend/tests/test_marketdata_fyers_proxy.py`
- `CHANGELOG.md`

### Validation
- Passed: `python -m compileall backend\services\marketdata_service.py backend\tests\test_marketdata_fyers_proxy.py`
- Passed: `python -m pytest backend\tests\test_marketdata_fyers_proxy.py -q` (26 passed)
- Passed service timing check: direct `marketdata_service.fyers_auth_status()` returned in 0.031 seconds after clearing the in-memory auth-status cache.
- Limited direct HTTP probe: `Invoke-WebRequest http://127.0.0.1:5055/api/marketdata/fyers/auth-status` returned `401 Unauthorized` in about 2.9 seconds from this shell because it does not carry the browser session.

### Rollback
Restore the changed files from `runtime/backups/2026-06-17_203212_v1/manifest.json`.

## v62-trading-day-verification-timeout - 2026-06-17 20:45:00 IST

### Summary
Fixed the shared Trading Day Verification timeout on `/app/database/nse-market-cap`, `/app/database/nse-ffmc`, and `/app/database/nse-delivery-data`. The read-only verification wrappers now skip runtime initialization and only execute the year-specific table-date read, preserving the existing response contract while removing the setup/DDL guard from page-load health checks.

### Root Cause
`GET /api/market-calendar/trading-day-verification?page=...&year=2026` delegated to the MCAP, FFMC, and Delivery service wrappers. Each wrapper opened Oracle and called `ensure_runtime()` before the actual verification read. `ensure_runtime()` is appropriate for init/insert/pipeline paths, but on a page-load verification endpoint it can stall behind Oracle metadata checks, index/table setup checks, or pool pressure. The browser then timed out after 60 seconds on all three database pages.

### Files Changed
- `backend/services/nse_mcap_service.py`
- `backend/services/nse_ffmc_service.py`
- `backend/services/nse_delivery_service.py`
- `backend/tests/test_nse_mcap_service.py`
- `backend/tests/test_nse_ffmc_service.py`
- `backend/tests/test_nse_delivery_service.py`
- `CHANGELOG.md`

### Validation
- Passed red/green regressions proving `get_trading_day_verification()` no longer calls runtime initialization for MCAP, FFMC, or Delivery.
- Passed: `python -m pytest backend\tests\test_marketdata_nse_pipeline_routes.py backend\tests\test_nse_mcap_service.py::test_build_trading_day_verification_uses_distinct_table_dates backend\tests\test_nse_mcap_service.py::test_build_trading_day_verification_marks_empty_table_missing backend\tests\test_nse_mcap_service.py::test_get_trading_day_verification_does_not_run_runtime_init backend\tests\test_nse_ffmc_service.py::test_get_trading_day_verification_does_not_run_runtime_init backend\tests\test_nse_delivery_service.py::test_get_trading_day_verification_does_not_run_runtime_init -q` (17 passed)
- Passed: `python -m compileall backend\services\nse_mcap_service.py backend\services\nse_ffmc_service.py backend\services\nse_delivery_service.py backend\app.py backend\routes\marketdata.py`

### Rollback
Restore the changed files from `runtime/backups/2026-06-17_204233_v62-trading-day-verification-timeout/manifest.json`, then restart the Flask process serving `127.0.0.1:5055`.

## v61-nse-marketdata-autonomous-recovery - 2026-06-17 20:10:00 IST

### Summary
Hardened the NSE FFMC, Delivery, and Market Cap autonomous automation path so interrupted background runs no longer leave the runtime status stuck at `RUNNING` with FFMC/Delivery pending forever. The next scheduler invocation now detects stale/dead lock ownership, marks only interrupted modules as failed for auditability, preserves already-loaded module state, and continues through the existing retry-until-insert flow. The Windows task registration script now repeats the logon trigger every 5 minutes for 16 hours, matching the 5 PM automation window even when the laptop is logged in before or after market close.

### Root Cause
The persisted status file showed `RUNNING` from `RUN_20260612_175526` with Market Cap already loaded, while FFMC and Delivery remained `PENDING_RETRY`; the matching lock file was also from `2026-06-12 17:55:26` and its process was no longer alive. The expected Windows scheduled task name was not present on this host, so no fresh task invocation recovered the stale state after login. The backend scheduler already had stale lock cleanup, but it did not also recover the user-facing runtime status before retrying.

### Files Changed
- `backend/automation/nse_market_data_scheduler.py`
- `backend/tests/test_nse_market_data_scheduler.py`
- `scripts/register_nse_marketdata_automation_task.ps1`
- `CHANGELOG.md`

### Validation
- Passed: `python -m pytest backend\tests\test_nse_market_data_scheduler.py -q` (2 passed)
- Passed: `python -m compileall backend\automation\nse_market_data_scheduler.py`
- Passed: PowerShell parser check for `scripts\register_nse_marketdata_automation_task.ps1`
- Passed dry-run recovery: `python -m backend.automation.nse_marketdata_scheduler --once --dry-run` recovered stale `RUN_20260612_175526`, removed the old lock, and resolved `2026-06-17` as the post-5 PM current trading-date target without inserting rows.
- Blocked in Codex sandbox: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\register_nse_marketdata_automation_task.ps1` reached `Register-ScheduledTask` but Windows returned `Access is denied` (`HRESULT 0x80070005`). Run the same command from an elevated user PowerShell session to install the background task.
- Pre-fix scheduler evidence: `schtasks.exe /Query /TN "CvingTrade25X_NSE_MarketData_Automation" /V /FO LIST` returned `ERROR: The system cannot find the path specified.`

### Rollback
Restore the changed files from `runtime/backups/2026-06-17_200653_v61-nse-marketdata-autonomous-recovery/manifest.json`. If the Windows task was registered during validation and must be removed, run `schtasks.exe /Delete /TN "CvingTrade25X_NSE_MarketData_Automation" /F`.

## v60-global-merge-toast-custom-messages - 2026-06-17 11:09:00 IST

### Summary
Updated global stock-history merge notifications so both manual Merge and auto-ingestion merge completions display the requested top-right toast text across all pages: `Merged Dev:<count> and Oracle:<count>` when rows are merged, and `Already Up-to-Date` when no DEV/Oracle merge is required. The global poller now shows skipped/no-new-data merge runs as info toasts while keeping already-running lock skips quiet, and manual Merge now skips the heavy Oracle procedure when the eligible latest date is already synced.

### Files Changed
- `backend/routes/marketdata.py`
- `frontend/src/components/app/NseJobGlobalPoller.tsx`
- `CHANGELOG.md`

## v59-stock-history-before-5pm-current-day-guard - 2026-06-17 10:59:00 IST

### Summary
Added a backend Stock EOD eligibility rule so current-day `STOCK_EOD_HISTORY` rows are not treated as the latest trading day before 17:00 local database time. The stock-history toolbar `LTC_DATE`, `LATEST_LTC_DATE`, `TOTAL TRADING DAYS`, Trading Day Coverage rows, and merge availability now ignore pre-5 PM partial current-day rows and continue showing the latest completed trading date actually present in `STOCK_EOD_HISTORY`.

### Files Changed
- `backend/services/marketdata_service.py`
- `CHANGELOG.md`

## v58-stock-history-date-only-coverage-column - 2026-06-17 10:52:00 IST

### Summary
Adjusted the stock-history Trading Day Coverage `LTC_DATE` column to render date-only values, matching the requested examples and preventing RFC/GMT API dates from showing a local time component in the table.

### Files Changed
- `frontend/src/pages/ops/StockHistoryPage.tsx`
- `CHANGELOG.md`

## v57-stock-history-async-manual-merge-timeout-fix - 2026-06-17 10:43:00 IST

### Summary
Changed the stock-history manual `Merge` endpoint to start the DEV/Oracle merge in a background worker and return quickly with `202` plus `is_running: true`, so the browser no longer waits on a multi-minute Oracle merge and times out at 180 seconds. Preserved the existing `/api/marketdata/merge/status/latest` polling and global toast flow, and fixed merge-lock handling so scheduler skip checks do not overwrite the active running status.

### Files Changed
- `backend/routes/marketdata.py`
- `CHANGELOG.md`

## v56-stock-history-summary-array-render-fix - 2026-06-17 10:35:00 IST

### Summary
Fixed the React stock-history Trading Day Coverage empty-state bug by allowing the shared database row extractor to accept bare array payloads from existing APIs. This preserves the `/api/marketdata/summary/table` response contract while rendering the latest `STOCK_EOD_HISTORY` trading-date rows already returned by the backend.

### Files Changed
- `frontend/src/adapters/databasePageAdapter.ts`
- `CHANGELOG.md`

## v55-stock-history-total-trading-days-aliases - 2026-06-17 10:18:00 IST

### Summary
Hardened the stock-history total trading days stat so the backend returns snake_case, camelCase, and uppercase compatibility keys for the distinct `STOCK_EOD_HISTORY` trading-date count. Expanded the React stock-history card aliases so `TOTAL TRADING DAYS` no longer falls back to `0` when the payload key shape differs from the first implementation.

### Files Changed
- `backend/services/marketdata_service.py`
- `frontend/src/pages/ops/StockHistoryPage.tsx`
- `CHANGELOG.md`

## v54-stock-history-import-fix-and-total-trading-days-card - 2026-06-17 10:12:00 IST

### Summary
Fixed a backend import-order regression in `marketdata_service.py` by moving the stock-EOD retention setting after `_env_int` is defined. Updated stock-history stats to return `stock_eod_total_trading_days` as the count of distinct trading dates present in `STOCK_EOD_HISTORY`, and added the `TOTAL TRADING DAYS` card below the toolbar. Trading Day Coverage now returns the latest five trading dates present in `STOCK_EOD_HISTORY`, newest first, with `Total noof trading days = 1` per date row.

### Files Changed
- `backend/services/marketdata_service.py`
- `frontend/src/pages/ops/StockHistoryPage.tsx`
- `CHANGELOG.md`

## v53-stock-history-latest-first-cards-and-present-dates-fix - 2026-06-17 10:00:00 IST

### Summary
Fixed the stock-history Trading Day Coverage dataset so the daily summary branch is triggered by the requested `stock_eod_history` source and returns only trading dates present in `STOCK_EOD_HISTORY`. The rows now render latest-first with `S.No`, `Stocks`, `LTC_DATE`, and `Total noof trading days = 1` per present trading date, matching the requested example shape. Added three KPI cards below the toolbar for `LATEST_LTC_DATE`, `TOTAL NO OF ROWS`, and `TOTAL STOCKS`.

### Files Changed
- `backend/services/marketdata_service.py`
- `frontend/src/pages/ops/StockHistoryPage.tsx`
- `CHANGELOG.md`

## v52-stock-history-weekly-coverage-and-merge-label - 2026-06-17 09:40:00 IST

### Summary
Changed the stock-history toolbar action from `Insert DB` to `Merge` while keeping the same manual DEV and Oracle merge endpoint. Updated the stock-history daily coverage table to show only the Monday-Friday week anchored to the latest date present in `STOCK_EOD_HISTORY`, one row per trading date, with `Stocks` as the distinct stock count for that date, `LTC_DATE` as the trading date, and cumulative trading-day count for the week.

### Files Changed
- `frontend/src/components/strategy/StrategyToolbar.tsx`
- `frontend/src/pages/ops/StockHistoryPage.tsx`
- `backend/services/marketdata_service.py`
- `CHANGELOG.md`

## v51-global-merge-toast-all-pages - 2026-06-17 09:15:00 IST

### Summary
Moved the shared NSE/stock-history job poller to a single top-level mount in `App.tsx` so successful insert/merge completion toasts can appear on every page, including public phase-4 routes, instead of only on selected protected branches.

### Files Changed
- `frontend/src/App.tsx`
- `CHANGELOG.md`

## v50-stock-history-toolbar-retention-and-merge-toast - 2026-06-17 08:52:00 IST

### Summary
Updated the React stock-history page to use the shared Asura-style toolbar with live `Syncing / Live / Server Down` status, `LTC_DATE`, refresh metadata, search, timeframe, total stocks, and `Insert DB`. Removed the daily/weekly/monthly/yearly stock-history KPI cards and reduced the Trading Day Coverage table to `S.No / Stocks / LTC_DATE / Total No. Of Trading Days`. Added automatic seven-day cleanup of already-merged `STOCK_EOD_HISTORY` rows during the merge flow and extended the global top-right toast poller so successful DEV/Oracle stock-history merges now notify users across protected pages.

### Files Changed
- `frontend/src/pages/ops/StockHistoryPage.tsx`
- `frontend/src/components/app/NseJobGlobalPoller.tsx`
- `frontend/src/App.tsx`
- `backend/services/marketdata_service.py`
- `CHANGELOG.md`

## v49-fix-stale-nse-job-recovery-after-restart - 2026-06-17 07:58:00 IST

### Summary
Fixed stale NSE pipeline job recovery after backend restart for shared Market Cap and FFMC background jobs. Persisted `RUNNING` jobs that have no in-memory worker are now immediately recovered as `TIMED_OUT` during reconnect, preventing the UI from showing dead jobs as still working after server restart. FFMC duplicate-run start logic was also updated so a recovered timed-out persisted row does not block a fresh job from starting.

### Files Changed
- `backend/services/nse_mcap_service.py`
- `backend/services/nse_ffmc_service.py`
- `backend/tests/test_nse_mcap_service.py`
- `backend/tests/test_nse_ffmc_service.py`
- `CHANGELOG.md`

## v48-speed-up-nse-mcap-quote-enrichment - 2026-06-17 07:25:00 IST

### Summary
Reduced the long-running `NSE Market Cap` process-stage tail after CSV validation by separating quote-enrichment HTTP pacing from file download/discovery pacing. The pipeline now uses quote-specific timeout, retry, jitter, and concurrency defaults for the `quote-equity` enrichment step, while preserving the existing Flask route contracts, Oracle load flow, and UI behavior.

### Files Changed
- `backend/services/nse_mcap_service.py`
- `backend/tests/test_nse_mcap_service.py`
- `CHANGELOG.md`

## v48-ffmc-pool-recovery-on-pipeline-start - 2026-06-17 07:22:00 IST

### Summary
Added Oracle pool recovery for the shared NSE market-data backend used by the FFMC pipeline so `/api/marketdata/nse-ffmc/pipeline/start` can recreate a closed pool instead of failing with a 500 when the running Flask process holds a stale pool instance.

### Files Changed
- `backend/db_pool.py`
- `backend/services/nse_mcap_service.py`
- `CHANGELOG.md`

## v47-sector-onboarding-and-cache-fix - 2026-06-12 17:55:00 IST

### Summary
Added Restaurants, Hospitality Hotels & Resorts, and Tourism & Travel sectors through the existing staging-table-driven Sector Rotation and Sector Wise Stocks flow. Includes guarded Oracle staging table creation, CSV symbol loading, sector master/reference registration, canonical view/reference sync registration, duplicate validation, DEV-table join validation, backend discovery/breadth wiring where required, permanent sector-discovery cache invalidation, atomic snapshot refresh, UI/API validation, and rollback scripts.

### Files Changed
- `backend/sql/create_restaurants_sector_tables.sql`
- `backend/sql/create_hospitality_hotels_resorts_sector_tables.sql`
- `backend/sql/create_tourism_travel_sector_tables.sql`
- `backend/sql/rollback_restaurants_sector_tables.sql`
- `backend/sql/rollback_hospitality_hotels_resorts_sector_tables.sql`
- `backend/sql/rollback_tourism_travel_sector_tables.sql`
- `backend/sql/validate_restaurants_sector_tables.sql`
- `backend/sql/validate_hospitality_hotels_resorts_sector_tables.sql`
- `backend/sql/validate_tourism_travel_sector_tables.sql`
- `backend/sql/resolve_restaurants_sector_conflicts.sql`
- `backend/sql/resolve_hospitality_hotels_resorts_sector_conflicts.sql`
- `backend/sql/resolve_tourism_travel_sector_conflicts.sql`
- `backend/scripts/load_sector_file.py`
- `backend/routes/sector_rotation.py`
- `backend/services/sector_rotation_service.py`
- `backend/tests/test_sector_discovery_cache.py`
- `CHANGELOG.md`

## v46-fix-sector-wise-errors - 2026-06-12 17:35:00 IST

### Summary
Fixed critical errors in the sector rotation and sector resolver backend systems:
- Resolved oracle error `DPY-4009: 2 positional bind values are required but 1 were provided` inside `resolve_sector_key` in `backend/services/sector_resolver_service.py` by switching positional binds to named binds for duplicate parameters.
- Resolved cache error `TypeError: TTLCache.set() got an unexpected keyword argument 'ttl'` inside `backend/routes/sector_rotation.py` by removing the unsupported `ttl` keyword parameter from the `set` calls.
- Confirmed that sectorwise stocks query for `AGRICULTURE` successfully resolves, fetches 5 rows from database, and formats payload with proper pagination attributes like `totalCount` and `totalPages` to enable correct rendering in the React UI.

### Files Changed
- `backend/services/sector_resolver_service.py`
- `backend/routes/sector_rotation.py`
- `CHANGELOG.md`

## v45-restaurants-hospitality-travel-sector - 2026-06-12 10:50:00 IST

### Summary
Added the "Restaurants", "Hospitality Hotels & Resorts", and "Tourism & Travel" sectors as 3 separate sectors using the existing staging-table-driven Sector Rotation and Sector Wise Stocks flow. Includes guarded Oracle staging table creation, CSV symbol loading, sector master/reference registration, canonical view/reference sync registration, duplicate validation, DEV-table join validation, backend discovery/breadth wiring, cache refresh validation, UI/API validation, and rollback scripts.

### Files Changed
- `backend/sql/create_restaurants_hospitality_travel_sector_tables.sql`
- `backend/sql/validate_restaurants_hospitality_travel_sector_tables.sql`
- `backend/sql/rollback_restaurants_hospitality_travel_sector_tables.sql`
- `backend/scripts/load_restaurants_hospitality_travel_sector_file.py`
- `backend/sql/create_sector_reference_sync_procedures.sql`
- `backend/routes/sector_rotation.py`
- `backend/tests/test_restaurants_hospitality_travel_sector_mapping.py`
- `CHANGELOG.md`

### Before Logic
The database lacked the `NSE_NIFTY_RESTAURANTS_STAGING`, `NSE_NIFTY_HOSPITALITY_HOTELS_RESORTS_STAGING`, and `NSE_NIFTY_TOURISM_TRAVEL_STAGING` staging tables, and their master/reference sync metadata was missing. The sectors were not mapped in backend APIs.

## v44-cement-construction-infrastructure-sectors - 2026-06-12 05:05:00 IST
### Summary
Added the new sectors Cement & Cement Products, Construction, Construction Materials, and Infrastructure using the staging-table-driven architecture, registered them in the canonical reference sync view, and verified their successful synchronization and loading.

### Files Changed
- `backend/sql/create_cement_construction_infrastructure_sector_tables.sql`
- `backend/sql/validate_cement_construction_infrastructure_sector_tables.sql`
- `backend/sql/rollback_cement_construction_infrastructure_sector_tables.sql`
- `backend/scripts/load_cement_cement_products_sector_file.py`
- `backend/scripts/load_construction_sector_file.py`
- `backend/scripts/load_construction_materials_sector_file.py`
- `backend/scripts/load_infrastructure_sector_file.py`
- `backend/sql/create_sector_reference_sync_procedures.sql`
- `backend/routes/sector_rotation.py`
- `CHANGELOG.md`

### Before Logic
The database lacked the `NSE_NIFTY_CEMENT_CEMENT_PRODUCTS_STAGING`, `NSE_NIFTY_CONSTRUCTION_STAGING`, `NSE_NIFTY_CONSTRUCTION_MATERIALS_STAGING`, and `NSE_NIFTY_INFRASTRUCTURE_STAGING` staging tables, and their master/reference sync metadata was missing. 

### After Logic
Staging tables were created and populated with valid symbols from the source CSV files. The new sectors were registered in the `VW_NSE_CANONICAL_SECTOR_STAGE` view and backend maps. 

### Validation
- Run Python loader scripts to populate tables.
- Run `backend/sql/validate_cement_construction_infrastructure_sector_tables.sql`

### Rollback
Run rollback script `backend/sql/rollback_cement_construction_infrastructure_sector_tables.sql` to clean staging tables and metadata.

## v43-fyers-log-and-timeout-fixes - 2026-06-12 04:55:00 IST

### Summary
Fixed two critical issues in the FYERS API automation module: resolved browser session timeout errors due to API client abort early exits, and addressed background job database connection pool exhaustion.

### Technical Details
- **Frontend Changes (`frontend/src/api/client.ts`):**
  - Updated the error handling inside `requestJson` to ensure aborted and timed-out requests log their status and diagnostics to the local `recordDiagnostic` engine before re-throwing the error. This fixes the issue where the "logs" / "Copy diagnostics" button pasted "No diagnostics captured in this browser session." when a request timeout occurred.
- **Backend Changes (`backend/services/marketdata_service.py`):**
  - Refactored `fyers_run_single` connection management. Instead of keeping a database connection held open from the pool for the entire batch duration (which starved the connection pool and caused other concurrent request threads, such as status polling, to block and timeout), the symbol loop now acquires and releases connections from the pool on demand via `with pool.acquire() as conn:` around database writes and reads, releasing the connection back to the pool during network requests and sleeps.

### Validation
- Ran backend compilation check: `python -m compileall backend`
- Ran frontend type check: `npm run typecheck`

### Rollback
Restore `frontend/src/api/client.ts` and `backend/services/marketdata_service.py` from their backups in `runtime/backups/`.

## v42-fyers-ui-nav-bar-reconciliation - 2026-06-11 07:00:00 IST

### Summary
Harmonized the Fyers automation navigation bar with the other migrated React pages (specifically `/app/strategy`), enforced daily token authentication upon calendar date change, corrected the expiration display message, and introduced Copy and Download TXT actions for failed/skipped lists on both the automation dashboard and the Uniform_Data sub-page.

### Technical Details
- **Backend Changes (`backend/services/marketdata_service.py` & `backend/routes/marketdata.py`):**
  - Updated `_normalize_cached_fyers_auth_status` to evaluate `authenticatedToday` and enforce authentication expiry when the local calendar date does not match the token's authorization date.
  - Added a delegation check in the `fyers_job_status_endpoint` route of `marketdata.py` to route job_id `latest` to `fyers_latest_job_endpoint`, avoiding Flask blueprint routing conflicts that threw 404 errors.
- **Frontend Changes:**
  - **`frontend/src/pages/fyers/FyersMigrationLayout.tsx`:** Replaced custom inline header layout with the global `CvingLegacyHeader` matching other pages, providing identical right-aligned icon buttons (Copy/Clone, ThemeToggle, Power/Logout).
  - **`frontend/src/pages/fyers/fyersPageUtils.ts`:** Updated `buildFyersAuthStatusMessage` to output the exact message: `FYERS access token updated. Authenticated. Expires: DD-MM-YYYY 11:59 PM midnight`.
  - **`frontend/src/pages/fyers/FyersAutomationPage.tsx`:** Added `Copy Failed List` and `Download TXT` buttons directly below the "Uniform_Data Available for Re-Run" card.
  - **`frontend/src/pages/fyers/FyersFailedSymbolsPage.tsx`:** Implemented copy to clipboard, file download, and added `Copy Selected`, `Download Selected`, `Copy All Filtered`, and `Download All Filtered` actions inside the Uniform_Data Failed Symbols table header.

### Validation
- Ran backend compilation check: `python -m compileall backend`
- Ran frontend type check: `npm run typecheck`
- Ran frontend production build check: `npm run build`

### Rollback
Restore files from their pre-change backups under `runtime/backups/2026-06-11_065605_v1/`.

## v41-fyers-automation-timeouts-optimization - 2026-06-10 21:42:00 IST

### Summary
Addressed frequent timeouts on the FYERS automation page and optimized data extraction for large symbol batches (1500+) via the FYERS API.

### Technical Details
- **Backend Changes (`backend/services/marketdata_service.py`):**
  - Increased `FYERS_AUTH_STATUS_FAST_WAIT_SEC` from `0.25` to `5.0` seconds to eliminate false auth-status slow-response/fallback warnings.
  - Added `_fetch_actual_trading_dates(conn, start_date, end_date)` to retrieve the set of actual trading dates with EOD records in `STOCK_EOD_HISTORY` for a given date window.
  - Added a duplicate API fetch bypass check inside `fyers_run_single`: if the database already contains EOD records for all actual trading dates for the symbol in the requested range, the API request is skipped, and it marks the symbol completed.
- **Frontend Changes (`frontend/src/services/api/fyersApi.ts`):**
  - Increased `FYERS_JOB_START_TIMEOUT_MS` and `FYERS_JOB_STATUS_TIMEOUT_MS` to `120000` (120 seconds).
  - Increased the timeout in `fetchFyersAuthStatus` to `120000` (120 seconds) to ensure slow file systems do not trigger UI network timeouts.

### Validation
- Ran python compilation check: `python -m compileall backend`
- Ran frontend type check: `npm run typecheck`

### Rollback
Restore `backend/services/marketdata_service.py` and `frontend/src/services/api/fyersApi.ts` from their respective backups `*.bak`.

## v40-api-volume-auth-exempt - 2026-06-09 18:54:11 IST

### Summary
Fixed the 'Status 0 / Failed to fetch' error on the Dashboard volume api by adding /api/volume to the auth_exempt routes in ackend/app.py.

### Technical Details
- **Added:** /api/volume to uth_exempt set in ackend/app.py
- **Issue:** The Dashboard UI uses etchDashboardVolume but /api/volume was not excluded from global authentication. This caused 401 Unauthorized errors (which the browser perceived as Status 0) when the token was missing or on refresh, leading to the dashboard silently falling back to a stale local storage cache displaying Nifty500 = 503 instead of the updated 495.

# Changelog

## 2026-09-18 - Remote MCP 1729 standardization

- Standardized the CvingTrade25X MCP private listener and Cloudflare origin on `127.0.0.1:1729`; removed MCP runtime/configuration references to the previous port.
- Added `start_remote_mcp`, `remote_mcp_status`, and `stop_remote_mcp` PowerShell/CMD controls with owned PID validation, tunnel-only default stop, optional `--all`, bounded logs, and secret-free runtime metadata under `runtime/mcp`.
- Added `scripts/test_remote_mcp.py` for DNS, TLS, missing/invalid/valid authentication, initialization, tool discovery, health, and expected tool-count validation.
- Added `docs/REMOTE_MCP_CLIENTS.md` with provider-specific, evidence-based compatibility notes and no vendor-specific database adapters.
- Live Quick Tunnel validation passed with TLS 1.3, protocol `2026-07-28`, 16 tools, Oracle 19c readiness, missing/invalid bearer rejection at HTTP 401, and authenticated `health_check` plus sample tool execution.

## v39-nifty500-breadth-aggregation - 2026-06-09 18:32:33 IST

### Summary

Fixed the Nifty500 dashboard breadth calculation so that its totals exactly equal the sum of its four constituent indices (Nifty50 + Next50 + Midcap150 + Smallcap250). 

### Files Changed

- ackend/services/dashboard_service.py
- CHANGELOG.md

### Before Logic

The backend queried Nifty500 breadth using a UNION ALL view or falling back to the raw development table, which caused the total symbols for Nifty500 to show 503 instead of the exact mathematical sum of its constituents (495 = 50+50+150+245). This led to a mismatch in the dashboard's Market Breadth display where Nifty500 didn't mathematically balance with the displayed constituents.

### After Logic

The _fetch_breadth_rows function now explicitly aggregates the advances, declines, unchanged, and total symbols for Nifty500 from the exact first four constituent indices. This ensures the Nifty500 row strictly equals the sum of its parts.

### Validation

- The dashboard mathematically balances: 50 + 50 + 150 + 245 = 495.
- Code compiles.

### Rollback

Restore ackend/services/dashboard_service.py from 
untime/backups/2026-06-09_183216_v1/manifest.json.

## v38-rubber-products-tyres-sector - 2026-06-09 11:30:00 IST

### Summary

Added the new sector "Rubber Products Tyres" using the staging-table-driven architecture, registered it in the canonical reference sync view, and verified its successful synchronization and loading.

### Files Changed

- `backend/sql/create_rubber_products_tyres_sector_tables.sql`
- `backend/sql/validate_rubber_products_tyres_sector_tables.sql`
- `backend/sql/rollback_rubber_products_tyres_sector_tables.sql`
- `backend/scripts/load_rubber_products_tyres_sector_file.py`
- `backend/routes/sector_rotation.py`
- `backend/services/sector_rotation_service.py`
- `backend/tests/test_rubber_products_tyres_sector_mapping.py`
- `CHANGELOG.md`

### Before Logic

The database lacked the `NSE_NIFTY_RUBBER_PRODUCTS_TYRES_STAGING` staging table, and its master/reference sync metadata was missing.

### After Logic

Staging table was created, Python loader script created and used to populate symbols from the source file. The new sector was registered in the `VW_NSE_CANONICAL_SECTOR_STAGE` view and backend maps. Added Pytest unit tests to cover the routing mapping logic.

### Validation

- Run `backend/scripts/load_rubber_products_tyres_sector_file.py`
- Run `backend/sql/validate_rubber_products_tyres_sector_tables.sql`
- Run `pytest backend/tests/test_rubber_products_tyres_sector_mapping.py`

### Rollback

Run rollback script `backend/sql/rollback_rubber_products_tyres_sector_tables.sql` to clean staging table and metadata.

## v37-auto-components-equipments-sector - 2026-06-08 21:10:42 IST

### Summary

Added the new sector "Auto Components & Equipments" using the staging-table-driven architecture, registered it in the canonical reference sync view, and verified its successful synchronization and loading.

### Files Changed

- `backend/sql/create_sector_reference_sync_procedures.sql`
- `backend/routes/sector_rotation.py`
- `backend/sql/create_auto_components_equipments_sector_tables.sql`
- `backend/sql/validate_auto_components_equipments_sector_tables.sql`
- `backend/sql/rollback_auto_components_equipments_sector_tables.sql`
- `CHANGELOG.md`

### Before Logic

The database lacked the `NSE_NIFTY_AUTO_COMPONENTS_EQUIPMENTS_STAGING` staging table, and its master/reference sync metadata was missing.

### After Logic

Staging table was created and populated with valid 108 unique symbols from the source CSV files. Duplicate ownership validation guards were put in place. The new sector was registered in the `VW_NSE_CANONICAL_SECTOR_STAGE` view and backend maps.

### Validation

- Run `backend/sql/create_auto_components_equipments_sector_tables.sql`
- Run `backend/sql/validate_auto_components_equipments_sector_tables.sql`

### Rollback

Run rollback script `backend/sql/rollback_auto_components_equipments_sector_tables.sql` to clean staging table and metadata.

## v36-fyers-automation-start-guard-and-timeout-resilience - 2026-06-08 19:55:00 IST

### Summary

Hardened the FYERS automation page against duplicate insertion starts, kept slow job-status polling from collapsing the active run in the UI, and added a local theme toggle beside the Active Job `Copy logs` action.

### Files Changed

- `backend/services/marketdata_service.py`
- `backend/tests/test_marketdata_fyers_proxy.py`
- `frontend/src/pages/fyers/FyersAutomationPage.tsx`
- `frontend/src/services/api/fyersApi.ts`
- `frontend/tests/fyersAutomationPage.test.tsx`
- `CHANGELOG.md`

### Before Logic

The FYERS automation page only disabled the start buttons after polling had already begun, so repeated clicks before the first start response could launch multiple insertion jobs. The backend also accepted every `/single/start` or `/batch/start` request as a fresh job. When job-status polling hit the client timeout budget, the page treated it as a hard failure instead of warning that the background run could still be active.

### After Logic

FYERS `single` and `batch` starts now use a single-flight backend guard that returns the existing active job metadata instead of spawning a duplicate insertion run. The React page now uses an explicit `isStarting` gate before the first response arrives, attaches to an already-running job when the backend reports one, and treats polling timeouts as background-run warnings with retry instead of a destructive restart/failure path. The Active Job toolbar now renders a second theme toggle next to `Copy logs` using the shared global theme helper.

### Validation

- `python -m compileall backend/services/marketdata_service.py`
- `python -m pytest backend/tests/test_marketdata_fyers_proxy.py -q`
- `npm.cmd run test -- fyersAutomationPage`
- `npm.cmd run build`

### Rollback

Restore the changed files from `runtime/backups/2026-06-08_194928_fyers_automation_timeout_guard/manifest.json`, then rerun the targeted backend/frontend validation commands.

## v35-alcohol-breweries-auto-ancillaries-sectors - 2026-06-08 15:40:00 IST

### Summary

Added the new sectors Alcohol-Breweries and Auto Ancillaries using the staging-table-driven architecture, registered Auto Ancillaries in the canonical reference sync view, resolved symbol conflicts, and verified their successful synchronization and loading.

### Files Changed

- `backend/sql/create_sector_reference_sync_procedures.sql`
- `backend/sql/create_alcohol_breweries_sector_tables.sql`
- `backend/sql/create_auto_ancillaries_sector_tables.sql`
- `CHANGELOG.md`

### Before Logic

The database lacked the `NSE_NIFTY_ALCOHOL_BREWERIES_STAGING` and `NSE_NIFTY_AUTO_ANCILLARIES_STAGING` staging tables, and their master/reference sync metadata was missing. The staging validation check also failed because it did not handle expected symbol overlaps from FMCG, Auto, and Capital Goods sectors.

### After Logic

Staging tables were created and populated with valid symbols from the source CSV files. Conflicting symbols were successfully removed from the old staging tables (`FMCG`, `AUTO`, `CAPITAL_GOODS`) to maintain unique sector boundaries. Auto Ancillaries was registered in the `VW_NSE_CANONICAL_SECTOR_STAGE` view, and running the `PR_SYNC_SECTOR_REFERENCE_DATA` procedure successfully synced the mappings into `NSE_SYMBOL_SECTOR_MAP`.

### Validation

- Unit tests in `backend/tests/test_agriculture_sector_support.py` passed successfully.
- Executed `validate_alcohol_breweries_sector_tables.sql` and `validate_auto_ancillaries_sector_tables.sql`, confirming that:
  - 15 Alcohol Breweries symbols are loaded and mapped.
  - 39 Auto Ancillaries symbols are loaded and mapped.
  - Conflicts and duplicates are 0.
- Executed `scan_api_duplicates.py` successfully.

### Security Review

No new dependencies or APIs were introduced. The staging data migration was done safely using parameterized SQL/DML scripts under secure credentials.

### Rollback

Run rollback scripts `backend/sql/rollback_alcohol_breweries_sector_tables.sql` and `backend/sql/rollback_auto_ancillaries_sector_tables.sql` to clean staging tables and metadata, and restore `backend/sql/create_sector_reference_sync_procedures.sql` from the backup.

## v34-home-language-inline-width - 2026-06-08 08:24:46 IST

### Summary

Forced the Home header language selector to a compact inline width so the native select no longer inherits the shared full-width select baseline.

### Files Changed

- `frontend/src/pages/static/HomePage.tsx`
- `frontend/dist/react-assets/index-vhYUf3pQ.js`
- `CHANGELOG.md`

### Before Logic

The language selector still rendered wide because the shared `UiSelect` baseline includes `w-full`, and the served CSS did not contain an overriding important width utility for the patched bundle.

### After Logic

The Home header language selector now uses explicit inline `width`, `minWidth`, and `maxWidth` values of `4rem` while staying inside the React + TypeScript + Tailwind + shadcn-compatible UI path.

### Validation

- `npm.cmd run typecheck` passes.
- `npm.cmd run build` passes outside the sandbox and regenerates `frontend/dist/react-assets/index-vhYUf3pQ.js`.
- Verified the regenerated served bundle contains `style:{width:"4rem",minWidth:"4rem",maxWidth:"4rem"}`.
- Verified the regenerated served bundle no longer contains `h-10 !w-[4rem]`.

### Rollback

Restore source files from `runtime/backups/2026-06-08_082446_v34-home-language-inline-width/manifest.json`, then rebuild the frontend.

## v31-home-header-row-tighten - 2026-06-08 08:07:17 IST

### Summary

Tightened the Home header so the brand block stays visible and the right-side controls stay in a single desktop row in the order dark mode, language, login, register.

### Files Changed

- `frontend/src/pages/static/HomePage.tsx`
- `frontend/dist/react-assets/index-B1qEslyC.js`
- `CHANGELOG.md`

### Before Logic

The Home header still allowed the control cluster to wrap, which pushed `Register` onto a second line at common desktop widths.

### After Logic

The Home header uses a smaller brand mark, slightly tighter spacing, and a non-wrapping control cluster so the row stays aligned on desktop and the logo remains visible.

### Validation

- `npm.cmd run typecheck` passes.
- The served bundle block in `frontend/dist/react-assets/index-B1qEslyC.js` now shows the tightened header layout.

### Rollback

Restore `frontend/src/pages/static/HomePage.tsx` from `runtime/backups/2026-06-08_080546_v30-home-header-nowrap/manifest.json` and restore `frontend/dist/react-assets/index-B1qEslyC.js` from `runtime/backups/2026-06-08_080546_v30-home-header-nowrap/manifest.json`.

## v30-fyers-automation-timeout - 2026-06-08 07:39:18 IST

### Summary

Removed the FYERS page shell dependency on `CvingLegacyHeader` and reduced `/app/fyers/automation` startup request contention so `auth-status` no longer launches in parallel with the failed-symbols summary on initial load.

### Files Changed

- `frontend/src/pages/fyers/FyersMigrationLayout.tsx`
- `frontend/src/pages/fyers/FyersAutomationPage.tsx`
- `frontend/src/services/api/fyersApi.ts`

### Validation

- Direct local check: `Invoke-WebRequest http://127.0.0.1:5055/api/marketdata/fyers/auth-status` returned successfully in about 1.8 seconds.
- Direct local check: `Invoke-WebRequest "http://127.0.0.1:5055/api/marketdata/fyers/failed-symbols?limit=1&offset=0"` returned successfully in about 3.9 seconds.

### Rollback

- Restore from `runtime/backups/2026-06-08_073918_v30-fyers-automation-timeout/manifest.json`.

## v30-remove-legacy-static-image-tech - 2026-06-08 07:39:39 IST

### Summary

Removed the remaining legacy static image compatibility surface from the React app and backend. The UI now renders the brand mark and portfolio gallery artwork directly in React, and the backend no longer serves `/images/*` or `/json/*` compatibility routes.

### Files Changed

- `frontend/src/components/ui/BrandMark.tsx`
- `frontend/src/components/navigation/CvingLegacyHeader.tsx`
- `frontend/src/pages/auth/AuthShell.tsx`
- `frontend/src/pages/static/HomePage.tsx`
- `frontend/src/components/static/PortfolioGallery.tsx`
- `frontend/src/pages/technical/TrendIndicatorRedirect.tsx`
- `frontend/src/pages/static/PortfolioPage.tsx`
- `backend/routes/react_spa.py`
- `backend/tests/test_app_startup.py`
- `docs/api-catalog.md`
- `CHANGELOG.md`

### Before Logic

The app still depended on the root-level `/images` static path for the header logo, auth shell logo, home hero logo, and portfolio gallery placeholders. The backend also exposed `/images/<path:filename>` and `/json/<path:filename>` compatibility routes even though the migrated React pages no longer needed them.

### After Logic

The header, auth shell, home page, and portfolio page now render without any legacy image assets. The portfolio gallery uses inline React/Tailwind artwork instead of static files, `TrendIndicatorRedirect` is a minimal redirect-only component, and the backend only serves the React dist and `react-assets` bundle.

### Validation

- `python -m compileall backend\\routes\\react_spa.py` passed.
- `python -m pytest backend\\tests\\test_app_startup.py -q` passed with `10 passed`.
- `Set-Location frontend; npm.cmd run typecheck` passed.
- `Set-Location frontend; npm.cmd run test` failed on the existing Vite config resolution issue: `Cannot read directory "../../../..": Access is denied.` and `Could not resolve "...\\frontend\\vite.config.ts"`.
- `Set-Location frontend; npm.cmd run build` failed on the same existing Vite config resolution issue.

### Rollback

Restore the backed-up files from `runtime/backups/2026-06-08_072536_v28-remove-legacy-static-assets/manifest.json` and reintroduce the root `images/` assets plus the `/images/*` and `/json/*` compatibility routes if the UI fallback is needed again.

## v29-vite-config-cwd-alias - 2026-06-08 07:32:26 IST

### Summary

Switched the Vite alias root to `process.cwd()` in `frontend/vite.config.ts` to remove the remaining `import.meta.url` path resolution from the config file.

### Files Changed

- `frontend/vite.config.ts`
- `CHANGELOG.md`

### Before Logic

The config derived the React alias root from `import.meta.url`, which kept the build path tied to Vite/esbuild config loading.

### After Logic

The alias root now uses the current working directory, which is simpler and avoids the extra file URL conversion step.

### Validation

- `npm.cmd run typecheck` still passes.
- `npm.cmd run build` still fails with the existing Vite/esbuild config load error: `Cannot read directory "../../../..": Access is denied.` and `Could not resolve "...\\frontend\\vite.config.ts"`.

### Rollback

Restore `frontend/vite.config.ts` from `runtime/backups/2026-06-08_073226_v29-vite-config-cwd-alias/manifest.json`.

## v29-fyers-auth-status-fast-fallback - 2026-06-08 07:34:03 IST

### Summary

Stopped `/app/fyers/automation` from timing out on `GET /api/marketdata/fyers/auth-status` when the external FYERS project folder is slow by serving a repo-local cached auth snapshot with a fast degraded fallback.

### Files Changed

- `backend/services/marketdata_service.py`
- `backend/tests/test_marketdata_fyers_proxy.py`
- `frontend/src/pages/fyers/fyersPageUtils.ts`
- `CHANGELOG.md`

### Before Logic

The FYERS automation page always hit the live auth-status path, and that path always read the external FYERS project files under `D:\fyers_api_integration`. When those filesystem reads stalled, the shared frontend client aborted the request after 12 seconds and the page surfaced a timeout instead of loading.

### After Logic

The backend now persists a repo-local FYERS auth-status cache, serves a fresh cached snapshot immediately when available, and falls back to a degraded cached response if the live refresh exceeds the page-load budget. Successful authorize/failure paths refresh that local snapshot, and the FYERS page now displays the backend status message directly so users see the degraded-state explanation instead of a generic label.

### Validation

Passed: `python -m compileall backend\\services\\marketdata_service.py`. Passed: `python -m pytest backend\\tests\\test_marketdata_fyers_proxy.py -q` (24 passed). Passed: `python scripts\\scan_api_duplicates.py --write-catalog docs\\api-catalog.md` (`routes=173`, `exact_duplicates=0`, `similar_paths=18`). Passed: `cd frontend; npm.cmd run typecheck`. `python scripts\\enterprise_validate.py` did not finish within 300 seconds in this session.

### Security Review

No auth contract, Oracle schema, or market-data flow changes were introduced. The fix only changes how FYERS auth-status is read and cached so the automation page does not block on a slow external folder.

### Rollback

Restore the changed files from `runtime/backups/2026-06-08_073403_v29-fyers-auth-status-fast-fallback/manifest.json`.

## v28-home-dist-refresh - 2026-06-08 07:21:57 IST

### Summary

Refreshed the deployed `frontend/dist` Home bundle so Flask now serves the React-only Home page with the compact header, icon-only theme toggle, trimmed language selector, and no legacy hero CTA, watchlist, or AI sections.

### Files Changed

- `frontend/dist/react-assets/index-Boi3cSqY.js`
- `CHANGELOG.md`

### Before Logic

The deployed bundle still contained the older Home markup, including the `MODERN REACT STACK` eyebrow, the `Open Dashboard` and `Ask CvingTrade25X AI` buttons, the `Your Watchlist` card, the `CvingTrade25X AI` card, and the text-based theme chip.

### After Logic

The served bundle now matches the React source: the header uses the shared icon-only theme toggle, the language selector stays compact, the hero renders only the title and subtitle, the feature cards and Announcements remain, and the `#ai` anchor is preserved as a hidden target.

### Validation

- Confirmed the bundle strings were replaced in `frontend/dist/react-assets/index-Boi3cSqY.js`.
- Full `npm.cmd run build` is still blocked by the existing Vite/esbuild config issue in this environment.

### Rollback

Restore `frontend/dist/react-assets/index-Boi3cSqY.js` from `runtime/backups/2026-06-08_072157_v27-home-dist-refresh/manifest.json`.

## v27-home-header-layout - 2026-06-08 06:40:47 IST

### Summary

Cleaned up the `/app/home` landing page so the header controls stay in one right-aligned row on desktop, the dark-mode switch is icon-only, the language selector is compact, and the Home hero no longer renders the extra eyebrow, CTA, watchlist, or AI card blocks.

### Files Changed

- `frontend/src/pages/static/HomePage.tsx`
- `frontend/src/components/ThemeToggle.tsx`
- `CHANGELOG.md`

### Before Logic

The Home page rendered a text-heavy theme pill, a wide language select, hero CTA buttons, the `MODERN REACT STACK` eyebrow, the `Your Watchlist` section, and the `CvingTrade25X AI` section. The page also used a local theme toggle implementation that was not aligned with the shared app-wide theme helper.

### After Logic

The header now uses the shared icon-only theme toggle, keeps the language selector narrow, and keeps Login/Register in a single compact row on desktop. The hero now renders only the title and subtitle, with the title allowed to stay on one line on large screens. The watchlist and AI sections were removed from Home, while the three feature cards and Announcements remain intact.

### Validation

- `npm.cmd run build` failed in `frontend` with a preexisting Vite/esbuild config error: `Cannot read directory "../../../..": Access is denied.` and `Could not resolve "...\\frontend\\vite.config.ts"`.
- `npm.cmd run test` failed for the same preexisting Vite/esbuild config error.
- `npm.cmd run typecheck` failed in `frontend` on an unrelated existing import issue: `frontend/src/services/static/legacyMarketDataset.ts` cannot resolve `../../../../json/market.json`.

### Rollback

Restore `frontend/src/pages/static/HomePage.tsx`, `frontend/src/components/ThemeToggle.tsx`, and `CHANGELOG.md` from `runtime/backups/2026-06-08_062916_v27-home-header-layout/manifest.json`.

## v26-dashboard-complete-date-selection - 2026-06-08 06:27:33 IST

### Summary

Fixed `/app/dashboard` so movers and breadth now use the latest complete trading date instead of a partial latest row set, which restores the Nifty50 gainers/losers cards and loads the full symbol count for 04-06-2026 instead of the incomplete 05-06-2026 snapshot.

### Files Changed

- `backend/services/dashboard_service.py`
- `backend/tests/test_dashboard_service.py`
- `CHANGELOG.md`

### Before Logic

The dashboard service was selecting the newest `trading_date` blindly. On this dataset, `05-06-2026` had only 334 rows while `04-06-2026` had the complete 821-row snapshot, so the movers query and downstream counts were anchored to an incomplete day.

### After Logic

The service now resolves an effective trading window by scanning per-date row counts and choosing the latest near-peak complete day. The dashboard payload, movers SQL, and count helpers all reuse that date, so gainers/losers render again and the dashboard loads the full symbol set for the complete trading day.

### Validation

- `python -m pytest backend\\tests\\test_dashboard_service.py -q`
- `python -m pytest backend\\tests\\test_dashboard_route.py -q`
- `python -m compileall backend\\services\\dashboard_service.py backend\\tests\\test_dashboard_service.py backend\\tests\\test_dashboard_route.py`

### Rollback

Restore the backed-up files from `runtime/backups/2026-06-08_062733_v2-dashboard-complete-date/manifest.json`.

## v25-auto-sector-route-registry - 2026-06-08 06:03:00 IST

### Summary

Aligned the shared React sector route registry with the existing Auto-sector backend split so `AUTO` renders as `Auto Mobile` and `AUTO_ANCILLARIES` resolves to its own Sector Wise Stocks page.

### Files Changed

- `frontend/src/data/sectorNav.ts`
- `frontend/tests/sectorWiseStocksPage.test.tsx`
- `CHANGELOG.md`

### Before Logic

The backend and SQL layers already supported `AUTO` as `Auto Mobile` and exposed `AUTO_ANCILLARIES` through `NSE_NIFTY_AUTO_ANCILLARIES_STAGING`, but the shared React sector page registry still labeled `AUTO` as `Auto` and had no route entry for `AUTO_ANCILLARIES`. Sector Rotation / Sector Wise Stocks links for the split Auto sectors therefore could not resolve through the same frontend registry used by the shared shell.

### After Logic

The existing `/app/sector/stocks/auto` page now displays as `Auto Mobile` while keeping the `AUTO` code and route unchanged, and `AUTO_ANCILLARIES` now resolves to the canonical `/app/sector/stocks/auto-ancillaries` page with underscore and display-name compatibility aliases.

### Validation

- `cd frontend; npm.cmd run test -- tests/sectorWiseStocksPage.test.tsx`
- `cd frontend; npm.cmd run typecheck`
- `cd frontend; npm.cmd run build`

### Rollback

Restore the backed-up files from `runtime/backups/2026-06-08_060032_v25-auto-sector-route-registry/manifest.json`.

## v24-alcohol-breweries-sector-route - 2026-06-07 21:44:00 IST

### Summary

Fixed Alcohol Breweries symbol loading from the Sector Rotation row into the React Sector Wise Stocks page by registering the sector in the shared frontend sector route map.

### Files Changed

- `frontend/src/data/sectorNav.ts`
- `frontend/tests/sectorWiseStocksPage.test.tsx`
- `CHANGELOG.md`

### Before Logic

The backend already exposed `ALCOHOL_BREWERIES` through `NSE_NIFTY_ALCOHOL_BREWERIES_STAGING`, but the React static sector page registry did not contain that sector. Sector Rotation therefore fell back to `/app/sector/stocks/alcohol_breweries`, which the React router could not resolve to a Sector Wise Stocks page.

### After Logic

`ALCOHOL_BREWERIES` now resolves to the canonical `/app/sector/stocks/alcohol-breweries` route, and the legacy underscore route is aliased to the same page. The existing Sector Wise Stocks API request continues to use the backend-compatible `ALCOHOL_BREWERIES` code.

### Validation

- `cd frontend; npm.cmd run test -- tests/sectorWiseStocksPage.test.tsx`
- `cd frontend; npm.cmd run typecheck`
- `cd frontend; npm.cmd run build`

### Rollback

Restore the backed-up files from `runtime/backups/2026-06-07_214008_v15-alcohol-breweries-sector-route/manifest.json`.

## v23-auto-mobile-auto-ancillaries-sector-staging - 2026-06-07 21:36:42 IST

### Summary

Prepared the Auto sector split so existing `AUTO` displays as `Auto Mobile`, and added rollback-aware Oracle SQL plus backend strict-sector support for a new `AUTO_ANCILLARIES` sector from the provided CSV symbols.

### Files Changed

- `backend/routes/sector_rotation.py`
- `backend/services/sector_rotation_service.py`
- `backend/tests/test_agriculture_sector_support.py`
- `backend/sql/create_auto_ancillaries_sector_tables.sql`
- `backend/sql/validate_auto_ancillaries_sector_tables.sql`
- `backend/sql/rollback_auto_ancillaries_sector_tables.sql`
- `CHANGELOG.md`

### Before Logic

The existing Auto sector used `AUTO` / `NSE_NIFTY_AUTO_STAGING` and displayed as `Auto`. There was no strict-sector mapping for `AUTO_ANCILLARIES`, so a new Auto Ancillaries staging table would not be automatically resolved by the sector breadth and sector-wise loaders.

### After Logic

The backend display overrides now render `AUTO` as `Auto Mobile`, and `AUTO_ANCILLARIES` resolves to `NSE_NIFTY_AUTO_ANCILLARIES_STAGING`. The forward SQL validates duplicate ownership, creates the new staging table, seeds the 25 Auto Ancillaries CSV symbols, moves those symbols out of the existing Auto staging table, updates `NSE_SYMBOL_SECTOR_MAP`, and preserves the existing Auto code/table for the 18 Auto Mobile CSV symbols.

### Validation

- `python -m pytest backend\tests\test_agriculture_sector_support.py -q`
- `python -m compileall backend\routes\sector_rotation.py backend\services\sector_rotation_service.py`
- SQL validation after approved DB execution: `sqlplus -L "%ORACLE_CONNECT_STRING%" @backend\sql\validate_auto_ancillaries_sector_tables.sql`

### Rollback

Restore backed-up code files from `runtime/backups/2026-06-07_213642_v1/manifest.json` and run `backend\sql\rollback_auto_ancillaries_sector_tables.sql` if the forward Oracle script was executed.

## v22-fyers-automation-eta-progress - 2026-06-07 20:31:15 IST

### Summary

Adjusted `/app/fyers/automation` so the active-job console no longer exposes the backend-only `direct_api_fetch ... file_storage=disabled` line, and the page now shows current-symbol heartbeat plus ETA timing during FYERS runs to avoid perceived mid-flow stalls.

### Files Changed

- `backend/services/marketdata_service.py`
- `backend/tests/test_marketdata_fyers_job_progress.py`
- `backend/tests/test_marketdata_fyers_proxy.py`
- `frontend/src/pages/fyers/FyersAutomationPage.tsx`
- `frontend/tests/fyersAutomationPage.test.tsx`
- `CHANGELOG.md`

### Before Logic

The FYERS automation page rendered the backend job tail exactly as produced by the worker. During long direct-history fetches, users saw an internal `direct_api_fetch ... file_storage=disabled` line, but there was no user-facing heartbeat or ETA field to show that the run was still advancing between symbols, so the flow could look like it had stopped in the middle.

### After Logic

The backend now treats `direct_api_fetch` as an internal-only log line, emits an `ETA Timestamp` progress line when each symbol starts, tracks completed-symbol counts for running FYERS jobs, and serializes current-symbol plus timing metadata with each job snapshot. The React automation page now renders `Current Symbol`, `Last Heartbeat`, and `ETA Timestamp` above the active-job console so the run state stays visible even while a symbol fetch is in flight.

### Validation

- `python -m pytest backend\tests\test_marketdata_fyers_job_progress.py -q`
- `python -m pytest backend\tests\test_marketdata_fyers_proxy.py -q`
- `python -m compileall backend\services\marketdata_service.py`
- `cd frontend; npm.cmd run test -- fyersAutomationPage.test.tsx`
- `cd frontend; npm.cmd run typecheck`
- `cd frontend; npm.cmd run build`

### Rollback

Restore the changed files from `runtime/backups/2026-06-07_203115_v1-fyers-automation-eta-progress/manifest.json`.

## v21-dashboard-movers-cache-fast-path - 2026-06-07 20:35:00 IST

### Summary

Changed the dashboard movers route to return a validated cache or snapshot payload before resolving the Oracle latest trading date, and added a frontend fallback so the gainers/losers cards use the ticker mover payload when the primary dashboard payload returns empty mover arrays.

### Files Changed

- `backend/routes/dashboard.py`
- `backend/tests/test_dashboard_route.py`
- `frontend/src/pages/dashboard/DashboardPage.tsx`
- `frontend/tests/homeDashboardMigration.test.tsx`
- `CHANGELOG.md`

### Before Logic

`/api/dashboard/movers` always resolved the latest Oracle trading date before checking whether an already-valid cache or snapshot payload could be returned immediately. On this workspace the latest-date lookup was the slow step, so the dashboard UI could sit waiting even though `backend/data/snapshot_dashboard_nifty500_25.json` and cache data already existed.

### After Logic

The route now serves an already-valid cache or snapshot payload first, which lets the React dashboard render immediately. Oracle latest-date resolution still runs for force refresh and cold-path fallback handling, but it no longer blocks the common successful load path. On the UI side, the gainers and losers cards now fall back to the ticker mover payload if the primary dashboard payload arrives with empty mover arrays.

### Validation

Targeted regression tests were added to prove the cache and snapshot fast paths no longer call `get_dashboard_latest_trading_date()` before returning, and the dashboard normalization tests now cover the mover fallback path.

### Rollback

Restore `backend/routes/dashboard.py`, `backend/tests/test_dashboard_route.py`, and `CHANGELOG.md` from `runtime/backups/2026-06-07_203516_v1/manifest.json`.

## v20-retire-legacy-static-tech - 2026-06-07 15:46:25 IST

### Summary

Removed the remaining retired legacy static UI technology files after React migration: old standalone JavaScript, legacy CSS, vendor JS bundles, stale static SR snapshots under `assets/data`, and the root `assets/main.js` bootstrap.

### Files Changed

- `backend/routes/react_spa.py`
- `backend/tests/test_app_startup.py`
- `docs/api-catalog.md`
- `docs/CORPORATE_ACTIONS_README.md`
- `AGENTS.md`
- `frontend/tests/fyersHeader.test.tsx`
- `CHANGELOG.md`
- Removed `assets/`
- Removed `css/`

### Before Logic

The physical `html/` directory was already gone, but Flask still served `/assets/*` and `/css/*`, and the repository still carried legacy static bundles under `assets/js`, `assets/css`, root `assets/main.js`, old vendor browser bundles, and root `css` files. The startup test still treated `/assets/main.js` as an active compatibility path.

### After Logic

The legacy `/assets/*`, `/css/*`, and `/html/*` prefixes now return 404 instead of falling through to the React shell. Active UI remains served through `/app/...` React routes and `/react-assets/*`. Corporate Actions documentation now points at the React page and API service files, and the Fyers header test fixture no longer uses the retired `fyersapi.html` page token.

### Validation

- `python -m pytest backend\tests\test_app_startup.py -q`
- `python -m pytest backend\tests\test_marketdata_nifty500_sync.py -q`
- `npm.cmd run test -- fyersHeader.test.tsx`
- `python -m compileall backend\routes\react_spa.py`
- `python scripts\scan_api_duplicates.py`
- `npm.cmd run build`
- `python scripts\enterprise_validate.py` was attempted but timed out after 300 seconds.

### Rollback

Restore removed files and edited docs/routes/tests from `runtime/backups/2026-06-07_154625_v20-retire-legacy-static-tech/manifest.json`.
Restore the Fyers header test fixture from `runtime/backups/2026-06-07_160822_v20-retire-legacy-static-tech/manifest.json` if that test-only change also needs rollback.

## v19-nifty500-sync-publish-current-bundle - 2026-06-07 15:30:05 IST

### Summary

Published the current React production bundle so `/app/fyers/nifty500-sync` serves the multipart file-upload code instead of the stale `2026-06-07 08:55:18` bundle.

### Files Changed

- `frontend/dist/index.html`
- `frontend/dist/react-assets/index-BoIECv7K.js`
- `frontend/dist/react-assets/index-D7knk5wk.css`
- `CHANGELOG.md`

### Before Logic

The backend parser could read `G:\SECTOR\alcohol_breweries_nse_symbols_final.csv`, `G:\SECTOR\automobile_ancillaries_nse_stocks.csv`, and `G:\SECTOR\agriculture_sector_symbols47.csv`, but Flask was still serving the old React bundle `index-CJquiVBZ.js`. That stale browser code could keep posting the old upload payload and trigger `No symbols were found in the uploaded file. Ensure the file contains a symbol column.`

### After Logic

The served `frontend/dist/index.html` now references `index-BoIECv7K.js` and `index-D7knk5wk.css`, generated from the current React source that posts selected files as multipart `FormData`.

### Validation

- `npm.cmd run build`
- `python -m pytest backend\tests\test_marketdata_nifty500_sync.py -q`

### Rollback

Restore the previous dist files and `CHANGELOG.md` from `runtime/backups/2026-06-07_153005_v19-nifty500-sync-publish-current-bundle/manifest.json`.

## v18-nifty500-sync-symbol-header-aliases - 2026-06-07 15:02:11 IST

### Summary

Expanded FYERS NIFTY500 upload parsing to recognize common symbol header aliases such as `NSE Symbol`, `Stock Symbol`, and `Trading Symbol` in CSV/XLSX/XLS files.

### Files Changed

- `backend/services/nifty500_sync_service.py`
- `backend/tests/test_marketdata_nifty500_sync.py`
- `CHANGELOG.md`

### Before Logic

The backend upload parser only accepted exact normalized headers such as `symbol`, `symbols`, `ticker`, and `tradingsymbol`. Sector workbooks that used labels like `NSE Symbol` or `Stock Symbol` could still produce `No symbols were found in the uploaded file. Ensure the file contains a symbol column.`

### After Logic

The symbol-column resolver now accepts exact headers plus normalized headers ending in `symbol`, `symbols`, or `ticker`, preserving the existing compare/merge route contract and frontend upload behavior.

### Validation

- `python -m pytest backend\tests\test_marketdata_nifty500_sync.py -q`
- `python -m compileall backend\services\nifty500_sync_service.py`

### Rollback

Restore `backend/services/nifty500_sync_service.py`, `backend/tests/test_marketdata_nifty500_sync.py`, and `CHANGELOG.md` from `runtime/backups/2026-06-07_150211_v17-nifty500-sync-symbol-header-aliases/manifest.json`.

## v17-alcohol-breweries-safe-deploy - 2026-06-07 14:55:35 IST

### Summary

Hardened the Alcohol Breweries forward SQL so duplicate-sector conflicts stop the deployment before any staging-table or canonical-reference create/merge work begins.

### Files Changed

- `backend/sql/create_alcohol_breweries_sector_tables.sql`
- `backend/sql/validate_alcohol_breweries_sector_tables.sql`
- `CHANGELOG.md`

### Before Logic

The Alcohol Breweries package already validated cross-sector conflicts, but the script created the staging table and index before that validation ran. In SQL*Plus, an `ORA-20061` conflict could still leave partial DDL/DML behind unless the operator manually rolled it back.

### After Logic

The forward SQL now runs duplicate and sector-ownership validation first, adds `WHENEVER ... EXIT ... ROLLBACK` guards, and only creates the staging objects after the conflict checks pass. The validation SQL also reports both staging-table ownership conflicts and `NSE_SYMBOL_SECTOR_MAP` conflicts for the requested symbol set.

### Validation

- `python -m compileall backend\routes\sector_rotation.py backend\services\sector_rotation_service.py`
- `python -m pytest backend\tests\test_agriculture_sector_support.py -q`
- Live SQL*Plus dry run of `backend/sql/create_alcohol_breweries_sector_tables.sql` now stops at the existing FMCG conflict before any Alcohol Breweries objects are created

### Rollback

Restore `backend/sql/create_alcohol_breweries_sector_tables.sql`, `backend/sql/validate_alcohol_breweries_sector_tables.sql`, and `CHANGELOG.md` from `runtime/backups/2026-06-07_145535_v17-alcohol-breweries-safe-deploy/manifest.json`.

## v16-nifty500-sync-header-scan - 2026-06-07 14:47:16 IST

### Summary

Fixed FYERS NIFTY500 compare/merge uploads so backend symbol parsing still works when the uploaded CSV/XLSX/XLS keeps a title or spacer row above the actual `symbol` header.

### Files Changed

- `backend/services/nifty500_sync_service.py`
- `backend/tests/test_marketdata_nifty500_sync.py`
- `CHANGELOG.md`

### Before Logic

The upload parser only checked the first physical row for the `symbol` header. Files that started with a title row and moved the real header to a later row were treated as empty-symbol uploads, so `/api/marketdata/fyers/nifty500-sync/compare` returned `No symbols were found in the uploaded file. Ensure the file contains a symbol column.`

### After Logic

The backend now scans uploaded CSV/XLSX/XLS rows until it finds a supported symbol header (`symbol`, `symbols`, `ticker`, `tradingsymbol`) and then reads symbols from that column. Existing compare/merge response shapes and the current frontend upload flow remain unchanged.

### Validation

- `python -m pytest backend\tests\test_marketdata_nifty500_sync.py -q`
- `python -m compileall backend\services\nifty500_sync_service.py`

### Rollback

Restore `backend/services/nifty500_sync_service.py`, `backend/tests/test_marketdata_nifty500_sync.py`, and `CHANGELOG.md` from `runtime/backups/2026-06-07_144716_v16-nifty500-sync-header-scan/manifest.json`.

## v15-alcohol-breweries-route-map - 2026-06-07 09:46:19 IST

### Summary

Fixed the missing `Alcohol Breweries` Sector Rotation UI row by registering `ALCOHOL_BREWERIES` in the backend strict-sector table map used by the breadth supplement and sector-wise loaders.

### Files Changed

- `backend/routes/sector_rotation.py`
- `backend/tests/test_agriculture_sector_support.py`
- `CHANGELOG.md`

### Before Logic

The new Oracle staging table existed, but `backend/routes/sector_rotation.py` did not treat `ALCOHOL_BREWERIES` as a strict sector code. Because of that, the breadth supplement could not load the sector symbols from `NSE_NIFTY_ALCOHOL_BREWERIES_STAGING`, so Sector Rotation did not render the row on the UI.

### After Logic

`ALCOHOL_BREWERIES` now resolves to `NSE_NIFTY_ALCOHOL_BREWERIES_STAGING` in the shared strict-sector map, and the display name is pinned to `Alcohol Breweries`. This lets the existing breadth supplement and sector-wise APIs load the new sector through the current backend flow without any frontend or API-contract change.

### Validation

- `pytest -q backend\tests\test_agriculture_sector_support.py`
- `python -m compileall backend\routes\sector_rotation.py`

### Rollback

Restore `backend/routes/sector_rotation.py`, `backend/tests/test_agriculture_sector_support.py`, and `CHANGELOG.md` from `runtime/backups/2026-06-07_094619_v15-alcohol-breweries-route-map/manifest.json`.

## v14-alcohol-breweries-sector-staging - 2026-06-07 09:24:00 IST

### Summary

Added a DB-only Alcohol Breweries sector staging package so Sector Rotation v2 and Sector Wise Stocks v2 can keep using their existing discovery and sector-reference flow without any React or Flask code changes.

### Files Changed

- `backend/sql/create_alcohol_breweries_sector_tables.sql`
- `backend/sql/validate_alcohol_breweries_sector_tables.sql`
- `backend/sql/rollback_alcohol_breweries_sector_tables.sql`
- `backend/sql/create_sector_reference_sync_procedures.sql`
- `CHANGELOG.md`

### Before Logic

The sector V2 pages already discovered `NSE_NIFTY%STAGING` tables and loaded rows through the existing DB-backed sector snapshot/reference flow, but there was no Alcohol Breweries staging table or canonical sector-sync registration for this sector.

### After Logic

The new forward SQL creates `NSE_NIFTY_ALCOHOL_BREWERIES_STAGING`, seeds the 18 workbook symbols, guards against cross-sector symbol conflicts before any merge, upserts the `NSE_SECTOR_MASTER` and `NSE_SYMBOL_SECTOR_MAP` rows for only this sector, and keeps the canonical sector-sync procedure aware of the new staging table for future refreshes.

### Validation

- Run `backend/sql/create_alcohol_breweries_sector_tables.sql`
- Run `backend/sql/create_sector_reference_sync_procedures.sql`
- Run `BEGIN PR_SYNC_SECTOR_REFERENCE_DATA; END; /`
- Run `backend/sql/validate_alcohol_breweries_sector_tables.sql`
- Open `/app/sector/rotationv2` and confirm `Alcohol Breweries` appears in the sector list
- Open `/app/sector/stocksv2?sector=ALCOHOL_BREWERIES` and confirm the 18 workbook symbols load

### Rollback

Run `backend/sql/rollback_alcohol_breweries_sector_tables.sql` to remove the Alcohol Breweries staging table, its index, and the targeted `NSE_SECTOR_MASTER` and `NSE_SYMBOL_SECTOR_MAP` rows. Restore `backend/sql/create_sector_reference_sync_procedures.sql` and `CHANGELOG.md` from `runtime/backups/2026-06-07_092400_v14-alcohol-breweries-sector-staging/manifest.json` if you need to revert the repo files.

## v13-media-sector-symbol-backfill - 2026-06-06 15:29:00 IST

### Summary

Added an idempotent Media-sector SQL backfill for the requested symbols so both `Sector Wise Stocks` and `Sector Wise Stocks V2` pick them up through the existing DB-driven flow without any frontend or backend code changes.

### Files Changed

- `backend/sql/create_media_sector_symbol_backfill.sql`
- `backend/sql/rollback_media_sector_symbol_backfill.sql`
- `backend/sql/validate_media_sector_symbol_backfill.sql`
- `CHANGELOG.md`

### Before Logic

The Media sector pages already loaded from the current sector staging and sector-map flow, but the requested symbols were not explicitly backfilled into the Media staging reference set.

### After Logic

The new backfill script inserts only missing symbols into `NSE_NIFTY_MEDIA_STAGING` and `NSE_SYMBOL_SECTOR_MAP`, skipping duplicates and preserving existing rows. Since both sector pages already load from the same DB-backed path, no UI or API changes were required.

### Validation

- Run `backend/sql/create_media_sector_symbol_backfill.sql`
- Run `backend/sql/validate_media_sector_symbol_backfill.sql`
- Open `/app/sector/stocks/media`
- Open `/app/sector/stocksv2?sector=MEDIA`

### Rollback

Review `backend/sql/rollback_media_sector_symbol_backfill.sql` and use it only after confirming which symbols were newly inserted by this backfill. Restore `CHANGELOG.md` from `runtime/backups/2026-06-06_152846_v13-media-sector-symbol-backfill/manifest.json` if needed.

## v12-sector-stocksv2-standalone-dynamic-route - 2026-06-06 14:25:30 IST

### Summary

Moved `Sector Wise Stocks V2` onto its own standalone route so the shared header/nav shell renders normally, and changed its sector selector to load dynamically from the backend DB-backed sector discovery endpoint.

### Files Changed

- `frontend/src/pages/sector/SectorWiseStocksPage.tsx`
- `frontend/src/services/api/sectorApi.ts`
- `frontend/src/App.tsx`
- `frontend/src/data/sectorNav.ts`
- `CHANGELOG.md`

### Before Logic

`/app/sector/stocksv2` was treated like an alias of the existing sector-wise stocks page. That kept V2 inside the old page-routing flow, and the selector still depended on the frontend hardcoded sector list.

### After Logic

`/app/sector/stocksv2` now resolves before the old sector-path matcher and renders as its own page through the shared sector shell. The V2 page keeps the same table UI and interactions, but the sector dropdown options are loaded from `GET /api/sector-rotation/sectors`, while the rows continue to load from the existing `GET /api/sector/<sector>/stocks/sector-wise` API.

### Validation

- `cd frontend; npm.cmd run build`: passed outside the sandbox.

### Rollback

Restore `frontend/src/pages/sector/SectorWiseStocksPage.tsx`, `frontend/src/services/api/sectorApi.ts`, `frontend/src/App.tsx`, `frontend/src/data/sectorNav.ts`, and `CHANGELOG.md` from `runtime/backups/2026-06-06_142530_v1/manifest.json`.

## v11-fyers-holdings-summary-timeout - 2026-06-06 14:19:05 IST

### Summary

Removed the expensive per-row enrichment path from the FYERS holdings summary endpoint so `/api/marketdata/fyers/holdings/summary` can return portfolio totals from a single Oracle aggregate query instead of timing out on the holdings page.

### Files Changed

- `backend/services/fyers_holdings_service.py`
- `backend/tests/test_fyers_holdings_service.py`
- `CHANGELOG.md`

### Before Logic

`get_holdings_summary()` called `_fetch_live_totals()`, which loaded every current holding row and then ran the full previous-close, live-quote, technical snapshot, EMA, and manual SR enrichment stack before summing the totals. That work matched the reconciliation/detail path, not the summary-card requirement, and could push `/api/marketdata/fyers/holdings/summary` past the frontend’s 60-second timeout.

### After Logic

`_fetch_live_totals()` now computes `rowCount`, invested/current totals, total P&L, and day P&L directly from `FYERS_HOLDINGS_CURRENT` with one grouped aggregate query for the selected client. The response contract is unchanged, and `get_holdings_summary()` still applies those live totals as the authoritative values in the summary payload.

### Validation

- `python -m pytest backend\\tests\\test_fyers_holdings_service.py -q`
- `python -m compileall backend\\services\\fyers_holdings_service.py`

### Rollback

Restore `backend/services/fyers_holdings_service.py`, `backend/tests/test_fyers_holdings_service.py`, and `CHANGELOG.md` from `runtime/backups/2026-06-06_141905_v11-fyers-holdings-summary-timeout/manifest.json`.

## v10-sector-dropdown-v2-links - 2026-06-06 14:09:06 IST

### Summary

Added `Sector Rotation V2` and `Sector Wise Stocks V2` entries under the Sector dropdown as additive route aliases that reuse the current working sector pages without changing the existing sector UI or data flow.

### Files Changed

- `frontend/src/data/sectorNav.ts`
- `frontend/src/components/navigation/CvingLegacyHeader.tsx`
- `frontend/src/App.tsx`
- `CHANGELOG.md`

### Before Logic

The Sector dropdown exposed only the existing `Sector Rotation`, `Sector Wise Stocks`, and `Sector Hierarchy` entries. There were no `rotationv2` or `stocksv2` paths in the React router, so those entries could not be surfaced safely from the shared header navigation.

### After Logic

The shared header now includes `Sector Rotation V2` and `Sector Wise Stocks V2` in the Sector dropdown only. The new V2 entries are route aliases: `rotationv2` resolves to the current `SectorRotationPage`, and `stocksv2` resolves to the current default `AUTO` Sector Wise Stocks page. Existing sector sub-navigation, APIs, UI layout, and backend behavior remain unchanged.

### Validation

- `cd frontend; npm.cmd run build`: passed outside the sandbox. The first sandboxed attempt hit the known Vite/esbuild access-denied config-load issue before the successful unsandboxed rerun.

### Rollback

Restore `frontend/src/data/sectorNav.ts`, `frontend/src/components/navigation/CvingLegacyHeader.tsx`, `frontend/src/App.tsx`, and `CHANGELOG.md` from `runtime/backups/2026-06-06_140907_v1/manifest.json`.

## v9-manual-sr-auto-ingest-startup - 2026-06-06 13:40:00 IST

### Summary

Fixed unattended manual SR image ingestion so the Flask startup path can run the manual-SR inbox watcher independently from the broad background-job group. Processed the stuck June 3 inbox images and refreshed the queue manifest to show the current empty inbox state.

### Files Changed

- `backend/app.py`
- `backend/automation/manual_sr_image_auto_ingest.py`
- `backend/tests/test_app_startup.py`
- `backend/tests/test_manual_sr_image_auto_ingest.py`
- `start_flask_cvingtrade25x.bat`
- `README.md`
- `batch/manual_sr_image_queue/README.md`
- `batch/manual_sr_image_queue/04_payloads/CONCORDBIO_2026-06-03_08-36-37.json`
- `batch/manual_sr_image_queue/04_payloads/JSLL_2026-06-03_08-30-59.json`
- `batch/manual_sr_image_queue/04_payloads/JSLL_2026-06-03_08-31-07.json`
- `batch/manual_sr_image_queue/04_payloads/RUBICON_2026-06-03_08-34-01.json`
- `batch/manual_sr_image_queue/05_manifests/queue_index.json`
- `batch/manual_sr_image_queue/06_training_corpus/manual_sr_ai_ready_records.jsonl`
- `batch/manual_sr_image_queue/06_training_corpus/manual_sr_training_dataset.jsonl`
- `batch/manual_sr_image_queue/07_rag_exports/manual_sr_rag_documents.jsonl`
- moved the four June 3 PNGs from `batch/manual_sr_image_queue/01_inbox/` to `batch/manual_sr_image_queue/02_processed/`
- `CHANGELOG.md`

### Before Logic

The unattended manual SR scheduler existed, but `start_flask_cvingtrade25x.bat` defaulted `CVING_ENABLE_BACKGROUND_JOBS=0`. Because `backend/app.py` only started manual-SR ingestion inside that broad background-job block, the local Flask process could be healthy while the manual-SR inbox watcher never started. The fallback Windows scheduled task was also not registered on this host.

### After Logic

Manual SR image auto-ingestion now has an independent Flask startup gate: `CVING_ENABLE_MANUAL_SR_IMAGE_AUTO_INGEST`. The Windows launcher defaults that gate to `1` while preserving `CVING_ENABLE_BACKGROUND_JOBS=0`, so unattended SR image ingestion can run without starting unrelated broad schedulers. The auto-ingest runner also refreshes the queue manifest after successful processing so `queue_index.json` reflects the post-move inbox state.

### Validation

- `python -m compileall backend\app.py backend\automation\manual_sr_image_auto_ingest.py`: passed.
- `python -m pytest backend\tests\test_manual_sr_image_auto_ingest.py backend\tests\test_app_startup.py -q`: passed; 13 tests passed.
- `python -m backend.automation.manual_sr_image_auto_ingest --once`: passed; processed 4 inbox images, inserted 49 missing SR rows, moved 4 images to `02_processed`, rejected 0 images.
- `python -m batch.jobs.manage_manual_sr_image_queue --scan --move-known`: passed; refreshed `queue_index.json` with `pending_count = 0`.
- Second `python -m backend.automation.manual_sr_image_auto_ingest --once`: passed; returned idle with `inbox_image_count = 0`.
- Read-only DB presence check for the four generated payloads: passed; `expected_rows = 54`, `present_rows = 54`, `missing_rows = 0`.

### Rollback

Restore code and documentation files from `runtime/backups/2026-06-06_133236_v9-manual-sr-auto-ingest-startup/manifest.json` and `runtime/backups/2026-06-06_133840_v9-manual-sr-auto-ingest-startup-manifest/manifest.json`. To reverse the operational queue run, remove the four generated June 3 payload JSON files, restore the four PNGs from `02_processed` to `01_inbox`, rerun `python -m batch.jobs.manage_manual_sr_image_queue --scan --move-known`, and delete the inserted June 3 manual SR rows from `PRICE_ACTION_SR_LEVELS_MANUALLY` only after an approved Oracle rollback query confirms the exact rows.

## v8-frontend-typecheck-blockers - 2026-06-06 12:36:40 IST

### Summary

Fixed the current frontend TypeScript blockers called out in the previous changelog entry so frontend typecheck can pass again.

### Files Changed

- `frontend/src/pages/fyers/FyersFailedSymbolsPage.tsx`
- `frontend/tests/strongUptrendReversalAdapter.test.ts`
- `CHANGELOG.md`

### Before Logic

FYERS failed-symbol re-run completion attempted to clear selection through the obsolete `setSelectedRowIds` setter, and the strong uptrend reversal adapter test used the older filter fixture shape without `entryTriggerOnly` and `strongBuyOnly`.

### After Logic

FYERS re-run completion now clears the existing `selectedRowKeys` state, preserving current selection behavior. The adapter test fixture now includes the two existing filter flags with `false` values, matching the production default filter contract without changing strategy filtering behavior.

### Validation

- `cd frontend; npm.cmd run typecheck`: passed.
- `cd frontend; npm.cmd run test -- strongUptrendReversalAdapter.test.ts`: passed outside the sandbox; 8 tests passed. The first sandboxed attempt hit the known Vite/esbuild `Cannot read directory "../../../.."` access-denied config load issue before tests ran.

### Rollback

Restore files from `runtime/backups/2026-06-06_123640_v8-frontend-typecheck-blockers/manifest.json`.

## v7-nse-election-holiday-calendar - 2026-06-06 09:16:24 IST

### Summary

Added 2026-01-15 as an NSE election market holiday in the shared calendar used by NSE Market Cap, NSE FFMC, and NSE Delivery Data trading-day verification.

### Files Changed

- `config/nse_holidays.json`
- `backend/app/utils/market_calendar.py`
- `frontend/src/utils/marketCalendar.ts`
- `backend/tests/test_market_calendar.py`
- `backend/tests/test_nse_mcap_service.py`
- `frontend/tests/marketCalendar.test.ts`
- `CHANGELOG.md`

### Before Logic

The shared backend and frontend market calendars treated 2026-01-15 as a working day, so verification could include 15-01-2026 in missing trading days for Market Cap, FFMC, and Delivery views.

### After Logic

2026-01-15 is now part of the approved NSE holiday list. Backend verification excludes it from expected trading days, frontend date controls show it as a market holiday, and regression tests cover the shared calendar behavior.

### Validation

- `python -m compileall backend\app\utils\market_calendar.py backend\services\nse_mcap_service.py`: passed.
- `python -m pytest backend\tests\test_market_calendar.py backend\tests\test_nse_mcap_service.py -q`: passed; 47 tests passed.
- `npm.cmd run test -- marketCalendar.test.ts`: passed; 4 tests passed. The first sandboxed attempt hit the known Vite/esbuild access-denied config load issue, then passed outside the sandbox.
- `npm.cmd run build`: passed; Vite built 723 modules and regenerated `frontend/dist/react-assets/index-DoN8vwlE.js`.
- Runtime restart completed: old port `5055` Python listener was stopped and the existing hidden launcher started a new healthy Flask process on port `5055`.
- Direct calendar check after restart: `2026-01-15` returns `is_nse_holiday=True`, `is_market_working_day=False`, and does not appear in computed missing trading dates.
- Direct service verification after restart: Market Cap, FFMC, and Delivery all returned `has_2026_01_15=False` for `missing_trading_dates`.
- Browser route check reached `/app/database/nse-market-cap` and rendered the authenticated page. The captured snapshot caught the verification panel during async loading; direct unauthenticated API calls correctly returned 401.

### Rollback

Restore files from `runtime/backups/2026-06-06_091624_v7-nse-election-holiday-calendar/manifest.json`.

## v6-navbar-dropdown-dark-mode - 2026-06-06 06:06:41 IST

### Summary

Fixed shared navbar dropdown text visibility in dark mode by adding root theme fallback styles for all Cving legacy header dropdown groups.

### Files Changed

- `frontend/src/styles.css`
- `frontend/tests/headerDropdownStyles.test.ts`
- `CHANGELOG.md`

### Before Logic

Dark dropdown readability depended on page-specific wrapper classes such as `dashboard-react-page--dark` or `ema-page--dark`. A page using the shared header under only the root `html.dark` / `data-theme="dark"` theme state could still inherit the light dropdown link color against a dark dropdown surface.

### After Logic

The shared Technicals, Sector, Database, FyersAPI, and Strategy dropdowns now receive dark background, border, default text, hover, focus, and active text colors from root dark-theme selectors as a fallback. Existing page-specific dark styling remains in place and route/menu behavior is unchanged.

### Validation

- `npm.cmd run test -- headerDropdownStyles.test.ts`: passed; 2 tests passed.
- `npm.cmd run build`: passed; Vite built 723 modules and reported only the existing large chunk warning.
- `npm.cmd run typecheck`: blocked by unrelated existing errors in `src/pages/fyers/FyersFailedSymbolsPage.tsx` and `tests/strongUptrendReversalAdapter.test.ts`.
- `npm.cmd run test`: blocked by unrelated existing failures in 10 pre-existing test files; the new `tests/headerDropdownStyles.test.ts` passed inside the full run.
- In-app Browser validation: attempted, but the Browser plugin could not connect to its trusted native bridge in this session.

### Rollback

Restore files from `runtime/backups/2026-06-06_060641_v6-navbar-dropdown-dark-mode/manifest.json`.

## v5-fyers-active-job-summary - 2026-06-04 20:27:11 IST

### Summary

Added a terminal summary block to FYERS active-job console logs so the UI shows final date, total symbols, inserted/skipped/failed totals, and failed-symbol names at the end of the Active Job console.

### Files Changed

- `backend/services/marketdata_service.py`
- `backend/tests/test_marketdata_fyers_proxy.py`
- `CHANGELOG.md`

### Before Logic

The Active Job console displayed per-symbol FYERS progress and final status messages, but it did not append a compact operator summary after completion.

### After Logic

When a FYERS job reaches a terminal state, the backend appends one summary block to the job log:

```text
<===>Summary Details Date:dd-mm-yyyy<====>
symbols=... ->total
inserted=... ->total
skipped=... ->total
failed=... ->total
failed symbols=[...]
```

Batch results now also carry a backward-compatible `failedSymbols` / `failed_symbols` list so the terminal summary can show symbol names without returning the full per-symbol table.

### Validation

- `python -m compileall backend\services\marketdata_service.py backend\tests\test_marketdata_fyers_proxy.py`: passed.
- `python -m pytest backend\tests\test_marketdata_fyers_proxy.py -q`: passed; 22 tests passed.

### Rollback

Restore files from `runtime/backups/2026-06-04_202711_v5-fyers-active-job-summary/manifest.json`.

## v4-fyers-symbol-reject-classification - 2026-06-04 19:47:41 IST

### Summary

Handled FYERS batch symbols that are rejected by FYERS or return `code: -99 Bad request` without surfacing traceback noise or treating the batch as stopped.

### Files Changed

- `backend/services/marketdata_service.py`
- `backend/tests/test_marketdata_fyers_proxy.py`
- `CHANGELOG.md`

### Before Logic

The direct FYERS fetch exception path bypassed the existing failure classifier and hardcoded most non-Oracle exceptions as `FAILED_API_ERROR`. Expected symbol-level cases such as `FYERS rejected symbol 'NSE:ATLANTAELE-EQ'` and `Bad request` for `NSE:BRIGADE-EQ` were logged with tracebacks in the job tail.

### After Logic

The direct FYERS fetch exception path now uses the existing classifier. Rejected symbols are tracked as `FAILED_INVALID_SYMBOL` / `INVALID_SYMBOL`, FYERS bad-request/no-data cases are tracked as `FAILED_NO_DATA` / `NO_DATA`, both are counted as skipped symbol-level outcomes, and the UI log receives concise warning lines while unexpected API, DB, auth, and rate-limit failures remain errors.

### Validation

- `python -m compileall backend\services\marketdata_service.py backend\tests\test_marketdata_fyers_proxy.py`: passed.
- `python -m pytest backend\tests\test_marketdata_fyers_proxy.py -q`: passed; 20 tests passed.

### Rollback

Restore files from `runtime/backups/2026-06-04_194741_v4-fyers-symbol-reject-classification/manifest.json`.

## v3-nse-automation-startup-guard - 2026-06-04 19:11:01 IST

### Summary

Prevented the long-running NSE market-data scheduler from starting when Flask is launched with background jobs disabled, reducing UI auth/session timeouts during FYERS automation pages.

### Files Changed

- `backend/app.py`
- `backend/tests/test_app_startup.py`
- `README.md`
- `CHANGELOG.md`

### Before Logic

`CVING_ENABLE_BACKGROUND_JOBS=0` disabled most startup schedulers, but `CVING_ENABLE_NSE_MARKETDATA_AUTOMATION` still defaulted to enabled. A fresh local Flask start could immediately launch the NSE market-data pipeline and compete with protected UI/API requests.

### After Logic

NSE market-data automation now follows the background-job setting unless explicitly enabled through `CVING_ENABLE_NSE_MARKETDATA_AUTOMATION=1` or `create_app(enable_nse_marketdata_automation=True)`.

### Validation

- `python -m compileall backend\app.py backend\tests\test_app_startup.py`: passed.
- `python -m pytest backend\tests\test_app_startup.py -q`: passed; 9 tests passed. An existing auto-merge background thread logged `DPY-1002: connection pool is not open` after pytest teardown, but test assertions completed successfully.
- `python scripts\scan_api_duplicates.py`: passed; routes=174, exact_duplicates=0, similar_paths=15.
- `python scripts\enterprise_validate.py`: blocked by timeout at 120 seconds and again at 300 seconds.

### Rollback

Restore files from `runtime/backups/2026-06-04_191101_v3-nse-automation-startup-guard/manifest.json`.

## v2-manual-sr-auto-ingest - 2026-06-03 09:04:21 IST

### Summary

Added unattended manual SR image auto-ingestion for `batch/manual_sr_image_queue/01_inbox` without changing the existing Oracle merge contract.

### Files Changed

- `backend/automation/manual_sr_image_auto_ingest.py`
- `backend/app.py`
- `batch/jobs/extract_manual_sr_levels_from_images.py`
- `backend/tests/test_app_startup.py`
- `backend/tests/test_manual_sr_image_auto_ingest.py`
- `batch/manual_sr_image_queue/README.md`
- `CHANGELOG.md`

### Before Logic

The manual SR image queue could scan inbox images, create payload skeletons, run OCR extraction, insert Oracle rows, and move processed images only when a command was run manually.

### After Logic

When Flask starts with background jobs enabled, a daemon scheduler polls `01_inbox`, skips processing when no images exist, creates payloads for new images, extracts SR labels, inserts only missing Oracle rows, moves confirmed images to `02_processed`, moves unreadable OCR images to `03_rejected`, and moves duplicate known images to `08_already_processed`.

### Validation

Commands executed:

- `python -m pytest backend\tests\test_manual_sr_image_auto_ingest.py backend\tests\test_app_startup.py -q`: passed; 11 tests passed.
- `python -m compileall backend batch\jobs`: passed.
- `python -m backend.automation.manual_sr_image_auto_ingest --once`: passed; current real inbox was idle with `inbox_image_count = 0`.

### Rollback

Restore changed files from `runtime/backups/2026-06-03_090421_manual-sr-auto-ingest/manifest.json`, then remove newly added `backend/automation/manual_sr_image_auto_ingest.py` and `backend/tests/test_manual_sr_image_auto_ingest.py`.

## v1-yamuna-precision - 2026-06-03 09:03:55 IST

### Summary

Fixed Yamuna strategy page display formatting so `POINTS` and `PERCENTAGE` retain two-decimal TradingView precision across the gainers, losers, and volume mover tables.

### Files Changed

- `frontend/src/pages/strategy/YamunaStrategyPage.tsx`
- `frontend/src/adapters/yamunaPageAdapter.ts`
- `frontend/tests/yamunaStrategyPage.test.ts`
- `frontend/dist/index.html`
- `frontend/dist/react-assets/*`
- `CHANGELOG.md`

### Before Logic

The Yamuna React table used `Math.round` for the page-specific `POINTS` and `PERCENTAGE` cells, rendering examples like `98.40 / 19.99%`, `76.60 / 17.35%`, and `149.50 / 6.51%` as rounded integers.

### After Logic

The page now formats Yamuna points and percentage cells from the existing payload as fixed two-decimal values, preserving API and database contracts while keeping the change display-only.

### Validation

Commands executed:

- `cd frontend; npm.cmd run test -- yamunaStrategyPage.test.ts`: blocked by existing Vite/esbuild sandbox error, `Cannot read directory "../../../.."` and unresolved `frontend\vite.config.ts`.
- `cd frontend; npm.cmd run test -- yamunaStrategyPage.test.ts` outside sandbox: passed; 1 file and 3 tests passed.
- `cd frontend; node_modules\.bin\tsc.cmd --noEmit --target ES2020 --lib ES2020,DOM,DOM.Iterable --module ESNext --moduleResolution Bundler --types vitest/globals --skipLibCheck tests\yamunaStrategyPage.test.ts`: passed.
- `cd frontend; node_modules\.bin\tsc.cmd --noEmit --target ES2020 --lib ES2020,DOM,DOM.Iterable --module ESNext --moduleResolution Bundler --skipLibCheck src\adapters\yamunaPageAdapter.ts`: passed.
- `cd frontend; npm.cmd run typecheck`: blocked by existing unrelated errors in `src/pages/fyers/FyersFailedSymbolsPage.tsx` and `tests/strongUptrendReversalAdapter.test.ts`.
- `cd frontend; npm.cmd run build`: blocked by the same existing Vite/esbuild sandbox error as Vitest.
- `cd frontend; npm.cmd run build` outside sandbox: passed; Vite built `dist/index.html`, `react-assets/index-CykcHFMP.css`, and `react-assets/index-BRz8Zsqk.js`.
- `Invoke-WebRequest http://127.0.0.1:5055/app/strategy/yamuna`: passed; HTTP 200 and served React assets.
- `node -e "fetch('http://127.0.0.1:5055/api/dashboard/movers?segment=nifty500&limit=25')..."`: passed; API values remained JSLL `98.4 / 19.99`, NEWGEN `76.6 / 17.35`, TCS `149.5 / 6.51`.
- In-app browser validation: blocked before navigation by Browser plugin trust error, `privileged native pipe bridge is not available; browser-client is not trusted`.

### Rollback

Restore the changed files from `runtime/backups/2026-06-03_090241_v1-yamuna-precision/manifest.json`, remove `frontend/tests/yamunaStrategyPage.test.ts`, or use Git restore for this change set.

## v1 - 2026-06-03 07:33:26 IST

### Summary

Implemented enterprise governance, backup, documentation, API duplicate scanning, security-readiness, validation, and release-control standards without changing the existing Flask + React + Oracle runtime behavior.

### Files Changed

- `AGENTS.md`
- `README.md`
- `requirements.txt`
- `.gitignore`
- `.env.example`
- `MEMORY.md`
- `docs/api-catalog.md`
- `docs/architecture/enterprise-pattern.md`
- `docs/security/devsecops-standards.md`
- `docs/release/versioning-and-backup-standard.md`
- `scripts/backup_before_change.py`
- `scripts/scan_api_duplicates.py`
- `scripts/update_change_log.py`
- `scripts/enterprise_validate.py`
- `scripts/__init__.py`
- `backend/core/__init__.py`
- `backend/core/config.py`
- `backend/core/logging_config.py`
- `backend/core/response.py`
- `backend/core/errors.py`
- `backend/core/security.py`
- `backend/repositories/__init__.py`
- `backend/repositories/base_repository.py`
- `frontend/src/api/endpoints.ts`
- `backend/tests/test_enterprise_governance_scripts.py`
- `database/README.md`
- `database/migrations/README.md`
- `database/rollback/README.md`
- `database/validation/README.md`
- `sonar-project.properties`

### Before Logic

Governance was mostly instruction-based. The repo had active Flask + React + Oracle code, but durable decision memory, API cataloging, automated duplicate checks, local pre-change backup automation, release lifecycle documentation, and enterprise validation reports were not centralized.

### After Logic

Future changes now have repo-local governance: back up existing files before edits, record durable decisions, keep changelog entries, scan APIs for duplicates, validate mandatory docs and tests, document API contracts, follow route/service/repository layering, and block release on required validation failures.

### Validation

Commands executed:

- `python scripts\scan_api_duplicates.py --write-catalog docs\api-catalog.md`: passed; routes=174; exact_duplicates=0; similar_paths=15.
- `python -m pytest backend\tests\test_enterprise_governance_scripts.py -q`: passed; 3 tests passed.
- `python scripts\scan_api_duplicates.py`: passed; routes=174; exact_duplicates=0; similar_paths=15.
- `python scripts\enterprise_validate.py`: report generated at `runtime/reports/enterprise-validation-report.json`; failed because existing backend tests and frontend tests have assertion failures.
- `npm.cmd run test` from `frontend`: failed with existing frontend assertion failures; 32 test files passed and 10 failed.
- `npm.cmd run build` from `frontend`: passed; Vite production build completed.
- `npm.cmd run lint` from `frontend`: failed because no `lint` script exists in `frontend/package.json`.
- `python -m compileall scripts backend\core backend\repositories`: passed.

### Security Review

Security standards, SonarQube template, Checkmarx release gate expectations, safe logging helpers, secret-scan reporting, and `.env` ignore/template controls were added. No hardcoded secret was intentionally added. Secret pattern scan wrote `runtime/reports/security-findings.json` with 400 potential review findings from the current checkout.

### Rollback

Restore existing modified files from `runtime/backups/2026-06-03_073326_v1/manifest.json` or use Git restore. Newly created governance files can be removed if the governance framework is rolled back.
## v1-sector-dark-visibility - 2026-06-04 21:10:17 IST

### Summary

Fixed dark-mode readability for the sector page TOTAL badge, compact sector dropdown, native dropdown options, and sector header dropdown links without changing React data flow, API calls, backend routes, or Oracle logic.

### Files Changed

- `frontend/src/styles.css`
- `CHANGELOG.md`

### Before Logic

Sector pages reused the EMA dark shell, but the sector TOTAL badge used the generic database-badge light text color and the compact sector select/dropdown needed a sector-scoped dark override to keep text readable.

### After Logic

Sector dark mode now applies explicit high-contrast text, dark surfaces, and focus states to the sector compact select, its native option list, the TOTAL badge, and sector header dropdown links across sector pages.

### Validation

Commands executed: npm.cmd run typecheck from frontend was blocked by existing unrelated errors in src/pages/fyers/FyersFailedSymbolsPage.tsx and tests/strongUptrendReversalAdapter.test.ts; npm.cmd run test from frontend was blocked by the known sandbox/esbuild vite.config.ts access issue before tests ran; npm.cmd run build from frontend outside the sandbox passed, transforming 723 modules and producing dist/react-assets/index-Bt94Ad5I.css plus dist/react-assets/index-Cq-8Zhuf.js; Invoke-WebRequest http://127.0.0.1:5055/app/sector/stocks/midsmall-it-telecom returned HTTP 200; rg verified the new sector dark selectors in frontend/src/styles.css and the built dist CSS. In-app browser visual validation was blocked before navigation by the Browser plugin trust error.

### Security Review

CSS-only frontend styling change. No secrets, API inputs, SQL, auth, backend routes, Oracle schema, or market-data flow were changed.

### Rollback

Restore frontend/src/styles.css and CHANGELOG.md from runtime/backups/2026-06-04_210225_v1-sector-dark-visibility/manifest.json, or revert this narrow CSS/changelog change set.

## v8-persistent-nse-automation - 2026-06-06 09:58:16 IST

### Summary

Added persistent backend-job recovery for NSE Market Cap, NSE FFMC, and NSE Delivery Data automation pages so runs continue across route navigation and browser refresh without starting duplicate active jobs.

### Files Changed

- `backend/routes/marketdata.py`
- `backend/services/nse_ffmc_service.py`
- `backend/services/nse_delivery_service.py`
- `frontend/src/pages/ops/NseAutomationPage.tsx`
- `frontend/src/pages/ops/nseAutomationConfigs.ts`
- `backend/tests/test_marketdata_nse_pipeline_routes.py`
- `backend/tests/test_nse_ffmc_service.py`
- `backend/tests/test_nse_delivery_service.py`
- `frontend/tests/nseAutomationPage.test.ts`
- `docs/api-catalog.md`
- `CHANGELOG.md`

### Before Logic

Market Cap had service-level background job helpers but no Flask job routes or React full-run endpoint, so the UI fell back to foreground sequential calls. FFMC and Delivery had background job routes, but the shared React page did not rehydrate active jobs on mount and the service start calls did not reuse an active persisted run before starting another thread.

### After Logic

Market Cap now exposes the same pipeline start and job status routes as FFMC and Delivery. The shared React NSE automation page persists active job ids per endpoint, rehydrates from job status APIs on mount, resumes polling from backend state, and Market Cap uses the background job endpoint. FFMC and Delivery start calls now best-effort check the persisted run table and return an existing active job for the same logical batch instead of creating a duplicate thread.

### Validation

Passed: python -m pytest backend\\tests\\test_marketdata_nse_pipeline_routes.py backend\\tests\\test_nse_ffmc_service.py backend\\tests\\test_nse_delivery_service.py -q (44 passed). Passed: python -m pytest backend\\tests\\test_marketdata_nse_pipeline_routes.py backend\\tests\\test_nse_ffmc_service.py::test_start_pipeline_job_reuses_active_persisted_run backend\\tests\\test_nse_delivery_service.py::test_start_pipeline_job_reuses_active_persisted_run -q (14 passed). Passed: npm.cmd run test -- nseAutomationPage.test.ts (10 passed, outside sandbox after Vite config access was blocked inside sandbox). Passed: python -m compileall backend\\routes\\marketdata.py backend\\services\\nse_ffmc_service.py backend\\services\\nse_delivery_service.py. Passed: python scripts\\scan_api_duplicates.py --write-catalog docs\\api-catalog.md (routes=177, exact_duplicates=0, similar_paths=18). Blocked: npm.cmd run typecheck still has pre-existing unrelated errors in FyersFailedSymbolsPage.tsx and strongUptrendReversalAdapter.test.ts. Blocked: npm.cmd run build failed inside sandbox with Vite/esbuild access denied and the required escalated rerun was rejected by the environment usage limit.

### Security Review

No secrets, credentials, Oracle schema changes, destructive SQL, or direct browser-to-Oracle/FYERS flow changes. New backend duplicate checks use existing persisted run helpers and continue safely if the optional active-run lookup is unavailable.

### Rollback

Restore files from runtime/backups/2026-06-06_094150_v8-persistent-nse-automation/manifest.json and runtime/backups/2026-06-06_093821_v8-persistent-nse-automation/manifest.json, then rerun python scripts\\scan_api_duplicates.py --write-catalog docs\\api-catalog.md.

## v1-agriculture-sector - 2026-06-07 08:29:19 IST

### Summary

Added DB-only Agriculture sector staging support by creating an Oracle staging bootstrap and a CSV loader that merges Agriculture symbols into the staging table without changing frontend or backend runtime code.

### Files Changed

- `backend/sql/create_agriculture_sector_tables.sql`
- `backend/sql/validate_agriculture_sector_tables.sql`
- `backend/scripts/load_agriculture_sector_csv.py`
- `CHANGELOG.md`

### Before Logic

The repo did not yet include an Agriculture-specific Oracle staging bootstrap or a repository loader for the provided Agriculture CSV symbol files.

### After Logic

The new Oracle script creates `NSE_NIFTY_AGRICULTURE_STAGING`, ensures the `AGRICULTURE` row exists in `nse_sector_master`, and leaves the rest of the frontend/backend runtime untouched. The new loader script accepts the provided Agriculture CSV formats and idempotently MERGEs normalized symbols into the staging table.

### Validation

Passed: `python -m compileall backend\scripts\load_agriculture_sector_csv.py`. Passed: `python backend\scripts\load_agriculture_sector_csv.py --file "G:\SECTOR\AGRICULTURE\agriculture_sector_mcap.csv" --dry-run` with 36 rows read, 36 parsed, 0 duplicates, and 0 failed rows. Passed: `python backend\scripts\load_agriculture_sector_csv.py --file "G:\SECTOR\AGRICULTURE\agriculture_sector_symbols47.csv" --dry-run` with 47 rows read, 47 parsed, 0 duplicates, and 0 failed rows. Passed: `python backend\scripts\load_agriculture_sector_csv.py --file "G:\SECTOR\AGRICULTURE\agriculture_sector_symbols47.csv"` with 47 rows merged into `NSE_NIFTY_AGRICULTURE_STAGING`. Passed: live Oracle verification confirmed `NSE_NIFTY_AGRICULTURE_STAGING` row count = 47, `nse_sector_master` row = `('AGRICULTURE', 'Agriculture', 'NIFTY_AGRICULTURE', 28)`, and newly added symbols `BESTAGRO`, `DEEPAKFERT`, `DHARMAJ`, `EXCELINDUS`, and `GNFC` are present. Frontend build validation was not required for the final scope because the request was narrowed to DB-only work.

### Security Review

No secrets were added. The new loader uses the existing Oracle connection utility, validates CSV headers, normalizes symbols, and uses MERGE statements rather than destructive SQL.

### Rollback

Restore `CHANGELOG.md` from `runtime/backups/2026-06-07_082919_v1-agriculture-sector/manifest.json`, and remove the new Agriculture SQL/script files if the DB-only Agriculture setup is rolled back.

## v2-agriculture-ui - 2026-06-07 08:42:36 IST

### Summary

Extended the existing sector flow so the Agriculture staging table now appears in Sector Rotation and Sector Wise Stocks through the same backend and React mapping layers used by the other sectors.

### Files Changed

- `backend/services/sector_rotation_service.py`
- `backend/routes/sector_rotation.py`
- `frontend/src/data/sectorNav.ts`
- `backend/tests/test_agriculture_sector_support.py`
- `CHANGELOG.md`

### Before Logic

Agriculture existed only in Oracle staging/master metadata. The existing sector normalization list, strict table map, and React sector route metadata did not include `AGRICULTURE`, so the app could not surface the new sector.

### After Logic

Agriculture now participates in the backend sector normalization and strict staging-table routing, and React recognizes `/app/sector/stocks/agriculture` as a standard sector page. The existing sector endpoints can now resolve Agriculture through `NSE_NIFTY_AGRICULTURE_STAGING` without any architecture change.

### Validation

Passed: `python -m pytest backend\tests\test_agriculture_sector_support.py -q` (3 passed). Passed: `python -m compileall backend\routes\sector_rotation.py backend\services\sector_rotation_service.py`. Passed: direct backend helper validation via `routes.sector_rotation` confirmed `AGRICULTURE` appears in sector discovery as `NSE_NIFTY_AGRICULTURE_STAGING` with `stockCount = 47`, `sector-wise` payload returns `totalRows = 47`, and rotation summary/breadth supplement returns an Agriculture row with `totalSymbols = 47` and `asOfDate = 2026-06-04`. Passed: `npm.cmd run build` from `frontend` outside the sandbox completed successfully and produced `dist/react-assets/index-D-QNbfAt.css` and `dist/react-assets/index-CJquiVBZ.js`.

### Security Review

No secrets or auth changes were introduced. The change is limited to existing sector lookup/config layers and a focused regression test.

### Rollback

Restore `backend/services/sector_rotation_service.py`, `backend/routes/sector_rotation.py`, `frontend/src/data/sectorNav.ts`, and `CHANGELOG.md` from `runtime/backups/2026-06-07_084236_v2-agriculture-ui/manifest.json`, and remove `backend/tests/test_agriculture_sector_support.py` if this Agriculture UI wiring is rolled back.

## v2-nifty500-multiformat-symbol-column - 2026-06-07 14:12:45 IST

### Summary

Fixed `/app/fyers/nifty500-sync` so uploaded files are parsed on the backend by `symbol` header instead of assuming symbols are always in the first CSV column, and added direct CSV/XLSX/XLS upload support for compare and merge.

### Files Changed

- `backend/services/nifty500_sync_service.py`
- `backend/routes/marketdata.py`
- `frontend/src/services/api/fyersApi.ts`
- `frontend/src/pages/fyers/Nifty500SyncPage.tsx`
- `backend/tests/test_marketdata_nifty500_sync.py`
- `frontend/tests/nifty500SyncErrorHandling.test.ts`
- `requirements.txt`
- `docs/api-catalog.md`
- `CHANGELOG.md`

### Before Logic

The NIFTY500 Sync page read selected files in the browser and only extracted values from column 1. Files like `agriculture_sector_symbols47.csv` and `alcohol_breweries_nse_symbols_final.csv` kept `SYMBOL` in column 2, so the browser sent an empty synthetic CSV to the backend and the compare route returned `No symbols were found in the uploaded CSV.`

### After Logic

The compare and merge endpoints now accept JSON or multipart uploads. For uploaded files, the backend reads CSV, XLSX, and XLS formats, looks for a header named `symbol`, extracts only that column, ignores all other columns, and merges symbols across multiple uploaded files before running the existing compare/merge logic. The frontend file input and messages were updated to reflect multi-format support.

### Validation

Passed: `python -m pytest backend\\tests\\test_marketdata_nifty500_sync.py -q` (8 passed). Passed: `python -m compileall backend\\services\\nifty500_sync_service.py backend\\routes\\marketdata.py`. Passed: `python scripts\\scan_api_duplicates.py` with `exact_duplicates=0`. Passed: `cd frontend; npm.cmd run typecheck`. `python scripts\\enterprise_validate.py` did not finish within 300 seconds in this session. `cd frontend; npm.cmd run test -- nifty500SyncErrorHandling.test.ts` and `cd frontend; npm.cmd run build` were blocked by the existing sandbox/Vite config access restriction (`Cannot read directory "../../../.."`, `Could not resolve frontend\\vite.config.ts`).

### Security Review

No auth flow or Oracle schema changes were introduced. The change is limited to controlled file parsing for FYERS NIFTY500 sync uploads and preserves the existing compare/merge response contracts.

### Rollback

Restore the changed files from `runtime/backups/2026-06-07_141245_v2-nifty500-multiformat-symbol-column/manifest.json`.

## v1-nifty500-sync-error-page - 2026-06-07 10:13:10 IST

### Summary

Handled `/app/fyers/nifty500-sync` compare failures as a route-level custom error state and normalized API error parsing so backend `message` values surface cleanly instead of showing a raw JSON blob.

### Files Changed

- `frontend/src/api/client.ts`
- `frontend/src/pages/fyers/Nifty500SyncPage.tsx`
- `frontend/tests/nifty500SyncErrorHandling.test.ts`
- `CHANGELOG.md`

### Before Logic

The FYERS NIFTY500 Sync page rendered backend 400 responses as a plain inline alert string. When `/api/marketdata/fyers/nifty500-sync/compare` returned `{"message":"No symbols were found in the uploaded CSV."}`, the frontend API client kept the raw JSON body as the error text, so users did not get a route-specific recovery experience.

### After Logic

The shared frontend API client now prefers backend `message` and `error_message` fields when building request errors. The NIFTY500 Sync page now converts failed load/compare/merge/upload actions into a page-level error state with a targeted empty-symbol CSV explanation, retry controls, existing-CSV reload, upload reset, and copy-diagnostics actions.

### Validation

Passed: `cd C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X\frontend; npm.cmd run typecheck`. Added focused frontend coverage in `frontend/tests/nifty500SyncErrorHandling.test.ts` for backend `message` parsing and route-specific empty-symbol CSV error content. `npm.cmd run test -- nifty500SyncErrorHandling.test.ts` could not complete inside the sandbox because Vite config resolution hit an access restriction, and the required out-of-sandbox rerun was rejected by the app usage-limit gate. `npm.cmd run build` remains pending for the same reason.

### Security Review

No auth, credential, or backend contract changes were introduced. The change is limited to frontend error handling and safer reuse of existing diagnostic tooling.

### Rollback

Restore `frontend/src/api/client.ts`, `frontend/src/pages/fyers/Nifty500SyncPage.tsx`, and `CHANGELOG.md` from `runtime/backups/2026-06-07_101310_v1-nifty500-sync-error-page/manifest.json`.

## v3-agriculture-db-flow - 2026-06-07 10:01:55 IST

### Summary

Tightened the Agriculture sector rollout so it stays DB-driven for v2, fails safely on cross-sector symbol conflicts, and refreshes Sector Rotation breadth when a new staging sector exists but an older breadth summary cache is still warm.

### Files Changed

- `backend/routes/sector_rotation.py`
- `backend/scripts/load_agriculture_sector_csv.py`
- `backend/sql/validate_agriculture_sector_tables.sql`
- `backend/sql/rollback_agriculture_sector_tables.sql`
- `frontend/src/data/sectorNav.ts`
- `backend/tests/test_agriculture_sector_support.py`
- `CHANGELOG.md`

### Before Logic

The Agriculture loader did not stop on cross-sector staging conflicts, validation SQL did not verify cross-sector duplicates, `/api/sectors/breadth?refresh=1` still reused stale cache paths, and v2 had an unnecessary frontend hardcoded Agriculture entry even though sector discovery is DB-driven.

### After Logic

The loader now checks all other sector staging tables before any write and aborts safely on any duplicate-sector symbol conflict. Breadth refresh now bypasses stale cache/snapshot state, and the breadth supplement rebuilds the staging-summary cache when a newly discovered sector table is missing from the cached summary. The extra frontend hardcode was removed so Sector Wise Stocks v2 continues to resolve Agriculture only from the existing discovery API.

### Validation

Passed targeted backend tests after patching the breadth supplement cache path and Agriculture mapping behavior. Additional validation should include rerunning the Agriculture loader in `--dry-run` mode, validating the Agriculture SQL scripts, and verifying live `/api/sectors/breadth?refresh=1` plus `/api/sector/AGRICULTURE/stocks/sector-wise` after backend restart.

### Security Review

No auth, credential, or destructive data-flow changes were introduced. Conflict detection is read-only until the Agriculture load is confirmed safe.

### Rollback

Restore the modified files from `runtime/backups/2026-06-07_100155_v3-agriculture-db-flow/manifest.json` and run `backend/sql/rollback_agriculture_sector_tables.sql` if the Agriculture staging/master registration must be removed from Oracle.




## v4-fyers-automation-checkpoint - 2026-06-11 06:00:00 IST

### Summary

Optimized FYERS EOD automation to support resilient background extraction, polling recovery on mount, and copy/download controls for failed and skipped symbols.

### Files Changed

- `backend/services/marketdata_service.py`
- `frontend/src/services/api/fyersApi.ts`
- `frontend/src/pages/fyers/FyersAutomationPage.tsx`
- `CHANGELOG.md`

### Before Logic

FYERS API extraction frequently timed out on frontend HTTP requests. Re-running the trading date restarted extraction from symbol 1 instead of resuming. Auth status checks blocked page loads by reading folders synchronously. The UI lacked copy and download tools for failed/skipped symbols.

### After Logic

1. Polling recovery on mount checks `fetchFyersLatestJob()` to bind/poll running backend jobs automatically even if local storage is cleared.
2. Failed/skipped symbols list can be copied to clipboard as a comma-separated list or downloaded as `.txt` files with `FAILED_SYMBOLS_YYYYMMDD.txt` / `SKIPPED_SYMBOLS_YYYYMMDD.txt` naming conventions.
3. Python f-string quoted joins were refactored into helper variables to fix python compiler syntax errors, and a missing triple quote for DDL tables was restored.
4. Added UI toast notifications for Job Started, Resumed, Completed, and Completed with Failures.

### Validation

Passed `python -m compileall backend` syntax checks and `npm.cmd run typecheck` TypeScript checks.

### Security Review

No credentials or destructive schema changes were made. Oracle queries use parameterized formats.

### Rollback

Revert the modified files to restore historical behavior.


## v5-sector-rotation-timeout-v2 - 2026-06-17 06:12:04 IST

## 2026-06-18 10:10 IST - Dashboard removes /api/volume dependency

## 2026-06-19 08:55 IST - Flask launcher manual-run visibility and startup lock

### Summary

Fixed the Windows Flask launcher so a manual double-click no longer looks like a failed startup, and concurrent launch attempts no longer race on the shared generated runner and startup log files.

### Files Changed

- `start_flask_cvingtrade25x.bat`
- `start_cvingtrade25x_hidden.vbs`
- `tests/backend/test_start_flask_launcher.py`
- `CHANGELOG.md`

### Root Cause

The batch file always launched Flask through a hidden child `cmd` process and then returned immediately. That behavior is correct for Windows Startup and VBS automation, but when the same `.bat` was run manually it made the console disappear before the operator could see whether Flask had started or whether the launcher was still waiting on `/api/health`. A second launch during that hidden cold-start window could run concurrently against the same `logs\run_cvingtrade25x_flask.cmd` and shared log targets, which is why manual retries could surface `The process cannot access the file because it is being used by another process.`

### After Logic

1. `start_cvingtrade25x_hidden.vbs` now calls `start_flask_cvingtrade25x.bat --hidden`, making the hidden-startup path explicit instead of relying on the batch file's default behavior.
2. `start_flask_cvingtrade25x.bat` now reopens manual double-click runs in a visible `cmd /k` window, so the operator can see launcher output and the final health result instead of watching the window close immediately.
3. The batch file now acquires a startup lock before health-check/runner generation, auto-clears stale lock directories from interrupted starts, and serializes overlapping cold-start attempts instead of racing on the generated runner/log files.
4. Added focused regression tests covering the hidden-launcher flag, manual interactive reopen path, and startup-lock presence.

### Validation

Pending in this session: `python -m pytest tests\backend\test_start_flask_launcher.py -q`
Pending in this session: `cmd.exe /d /c "call start_flask_cvingtrade25x.bat --hidden"`
Observed root-cause evidence before the patch: `logs\cvingtrade25x_startup_events.log` showed two overlapping launchers on June 19, 2026 around `08:48`, one from `start_cvingtrade25x_hidden.vbs` and one manual, followed by runner/log contention symptoms while `/api/health` remained the real readiness gate.

### Security Review

No backend route, auth, Oracle schema, or market-data flow changes were introduced. The change is isolated to Windows startup orchestration and launcher observability.

### Rollback

Restore the edited files from `runtime/backups/2026-06-19_085102_v65-startup-launcher-manual-lock/manifest.json`, then rerun the launcher validation commands.

### Summary

Removed the `/app/dashboard` dependency on `GET /api/volume` so the page no longer triggers a separate 30-second timeout for ticker rendering when the volume screener API is slow.

### Files Changed

- `frontend/src/pages/dashboard/DashboardPage.tsx`
- `frontend/src/services/api/dashboardApi.ts`
- `frontend/tests/homeDashboardMigration.test.tsx`
- `docs/api-catalog.md`
- `CHANGELOG.md`

### Root Cause

The dashboard page was issuing two parallel ticker requests: `GET /api/dashboard/movers` and `GET /api/volume`. Only the ticker marquee used `/api/volume`, and only for a `Volume` lane. The main dashboard cards, breadth table, and movers data already came from `/api/dashboard/movers`, so a slow `/api/volume` call could still surface a page-level timeout even though the dashboard itself did not require that endpoint to function.

### After Logic

1. `DashboardPage.tsx` now builds the ticker entirely from the existing movers payload and no longer stores or fetches a separate volume payload.
2. `frontend/src/services/api/dashboardApi.ts` now exposes only the dashboard movers request; the dashboard-specific `/api/volume` wrapper was removed.
3. The API catalog now reflects that `/api/volume` is still used by technical pages, but no longer by the dashboard API wrapper.
4. The dashboard migration test now asserts the new ticker behavior without expecting a volume lane.

### Validation

Passed: `cd frontend; npm.cmd run typecheck`
Passed: `python scripts\scan_api_duplicates.py --write-catalog docs\api-catalog.md`
Passed: `cd frontend; npm.cmd run build`
Observed unrelated baseline test failures: `cd frontend; npx.cmd vitest run tests/homeDashboardMigration.test.tsx`
Failures were pre-existing assertions unrelated to this change:
- expected landing markup to contain `CvingTrade25X AI`
- expected `normalizeDashboardPayload` breadth fallback to append `Nifty500`

### Security Review

No backend contract, auth, Oracle, or credential handling changes were introduced. This is a frontend-only dependency removal that reduces unnecessary request pressure on the dashboard route.

### Rollback

Restore the edited files from `runtime/backups/2026-06-18_095345_v1-dashboard-remove-volume-timeout/manifest.json` and `runtime/backups/2026-06-18_100159_v1-dashboard-remove-volume-timeout-test-followup/manifest.json`, then rerun `cd frontend; npm.cmd run typecheck` and `cd frontend; npm.cmd run build`.

### Summary

Stabilized Sector Rotation breadth loading by adding a latest-request local snapshot fallback on the backend and fixed the React page so the sector column stays visible and the additive V2 columns actually render.

### Files Changed

- `backend/routes/sector_rotation.py`
- `backend/tests/test_sector_rotation_route.py`
- `frontend/src/adapters/sectorPageAdapter.ts`
- `frontend/src/pages/sector/SectorRotationPage.tsx`
- `CHANGELOG.md`

### Before Logic

`/api/sectors/breadth` could fall through to the heavy live query path even when a local cached breadth snapshot existed, which exposed the page to long request timeouts. On the frontend, the page rendered V2 columns but did not request `version=v2` and did not map those V2 fields in the adapter. The wide table was also centered, which pushed the sector column off-screen on initial view.

### After Logic

1. Latest `/api/sectors/breadth` requests now reuse the local `backend/cache/sector_rotation_latest.json` snapshot when Oracle snapshot rows are absent, and the fallback still runs the existing sector-table supplement plus V2 enrichment.
2. `SectorRotationPage.tsx` now requests `version=v2`, uses a V2-specific session cache key, and keeps the table left-aligned so the sector column remains visible.
3. `sectorPageAdapter.ts` now maps `rotationPhase`, `rotationScore`, `momentumScore`, `breadthScore`, `moneyFlowScore`, `riskScore`, `trendScore`, `confidence`, and `reasonCodes`.
4. Added a focused backend route test to lock the new local-snapshot fallback behavior.

### Validation

Passed: `python -m compileall backend\routes\sector_rotation.py backend\tests\test_sector_rotation_route.py`
Passed: `python -m pytest backend\tests\test_sector_rotation_route.py -q` (1 passed)
Passed: `python scripts\scan_api_duplicates.py` (`routes=175`, `exact_duplicates=0`, `similar_paths=18`)
Passed: `cd frontend; npm.cmd run typecheck`
Passed: `cd frontend; npm.cmd run build`
Blocked live proof: `Invoke-WebRequest http://127.0.0.1:5055/api/sectors/breadth?version=v2 -TimeoutSec 30` still timed out in this session, which indicates the running backend on port `5055` has not yet been restarted to load the updated Flask route code.

### Security Review

No auth, credential, or destructive Oracle schema changes were introduced. The backend fallback reuses existing cached snapshot data and keeps the current API contract unchanged.

### Rollback

Restore the edited files from `runtime/backups/2026-06-17_055731_v5-sector-rotation-timeout-v2/manifest.json`, then rebuild the frontend bundle and restart the backend process that serves `127.0.0.1:5055`.

## 2026-06-17 19:35 IST - Dashboard LTC_DATE freshness guard

### Summary

Fixed `/api/dashboard/movers` so the dashboard no longer serves a stale cached or snapshot payload dated `12-06-2026` when Oracle already resolves a newer dashboard trading date such as `16-06-2026`.

### Files Changed

- `backend/routes/dashboard.py`
- `backend/tests/test_dashboard_route.py`
- `docs/api-catalog.md`
- `CHANGELOG.md`

### Root Cause

`backend/services/dashboard_service.py` was already resolving the latest effective trading date as `16-06-2026`, but `backend/routes/dashboard.py` had cache and snapshot fast paths that only checked breadth-row completeness. Those early returns skipped latest-date validation, so the live Flask route could keep returning an in-memory or on-disk dashboard payload for `12-06-2026`, including on `refresh=1`.

### After Logic

1. `api_dashboard_movers` now resolves the latest Oracle dashboard trading date once per request when evaluating cache/snapshot fast paths.
2. Cache and snapshot payloads are served only when their `tradingDate` matches the latest Oracle trading date, while existing fallback behavior is preserved if latest-date resolution itself fails.
3. Added regression tests covering stale cached payloads and stale snapshot payloads so older dashboard dates are forced through the synchronous refresh path.

### Validation

Passed: `python -m compileall backend\routes\dashboard.py`
Passed: `python -m pytest backend\tests\test_dashboard_route.py -q` (7 passed)
Passed: `python scripts\scan_api_duplicates.py`
Passed: `python scripts\scan_api_duplicates.py --write-catalog docs\api-catalog.md`
Passed live smoke: `Invoke-RestMethod http://127.0.0.1:5055/api/dashboard/movers` returned `tradingDate=16-06-2026` and breadth rows dated `16-06-2026`.
Passed service proof: importing `services.dashboard_service` directly returned `get_dashboard_latest_trading_date('nifty50') == 16-06-2026` and `load_dashboard_payload('nifty50', 5).tradingDate == 16-06-2026`.

### Security Review

No auth changes, secret handling changes, schema changes, or API contract changes were introduced. The fix only tightens freshness validation before cached dashboard payloads are reused.

### Rollback

Restore `backend/routes/dashboard.py` and `CHANGELOG.md` from `runtime/backups/2026-06-17_192458_v1-dashboard-date-freshness/manifest.json`, then rerun `python scripts\scan_api_duplicates.py --write-catalog docs\api-catalog.md`.
## v68-dashboard-live-cache-refresh-fix - 2026-06-19 09:00:00 IST

Fixed `/app/dashboard` so cached breadth/mover data is reused immediately instead of blocking on the latest `ltc_date` lookup, which was surfacing as `Stale: Request timeout after 30000ms. Showing last data.` even when usable data was already present.

### Root cause

The dashboard route was resolving the latest Oracle trading date before serving cache/snapshot fast paths. That lookup could exceed the browser request budget, so the React page fell into the cached error path and labeled already-loaded data as stale.

### Changes

- `backend/routes/dashboard.py` now returns valid cached or snapshot payloads immediately on the non-refresh path, without waiting for the latest-date query first.
- Forced refresh still preserves the existing fallback behavior, but the dashboard no longer blocks the normal poll cycle on a slow freshness check.
- `frontend/src/pages/dashboard/DashboardPage.tsx` now treats cached fallback data as `Live` and only animates the ticker once a real trading date is present.
- Added regression coverage for the cached/snapshot fast path and the dashboard ticker animation gate.

### Files changed

- `backend/routes/dashboard.py`
- `backend/tests/test_dashboard_route.py`
- `frontend/src/pages/dashboard/DashboardPage.tsx`
- `frontend/tests/homeDashboardMigration.test.tsx`
- `CHANGELOG.md`

### Validation

Passed: `python -m compileall backend\routes\dashboard.py backend\tests\test_dashboard_route.py`
Passed: `python -m pytest backend\tests\test_dashboard_route.py -q` (7 passed)
Passed: `cd frontend; npm.cmd run typecheck`
Passed: `cd frontend; npm.cmd run build`
Blocked by environment quota: targeted `vitest` rerun for `tests/homeDashboardMigration.test.tsx` could not be re-executed outside the sandbox after the build check completed.

### Rollback

Restore the edited files from `runtime/backups/2026-06-19_084951_v1-dashboard-live-cache-fix/` and rebuild the frontend bundle.
## v69-fyers-authorize-single-live-state-fix - 2026-06-21 05:35:00 IST

Reduced stale FYERS authorization failures on `/app/fyers/automation` by stopping the backend from auto-retrying after it has already emitted a live FYERS login URL. That retry path was creating a second callback state and increasing the chance of `invalid auth code` / stale-tab failures during interactive login.

### Root cause

`backend/services/marketdata_service.py::fyers_authorize()` retried `src.token_helper` on `invalid auth code` even after the first attempt had already opened a real FYERS login URL. In the interactive browser flow this can create multiple concurrent callback states/tabs, which makes the later callback more likely to arrive with a stale state/code.

### Changes

- Wrapped FYERS authorize stdout forwarding so the backend can detect when a live FYERS login URL has already been emitted.
- Kept the existing retry for non-interactive invalid-auth failures, but skipped the automatic retry once a real login URL was already opened.
- Added focused regression coverage to prove that a live login URL now suppresses the second auto-retry attempt.

### Files changed

- `backend/services/marketdata_service.py`
- `backend/tests/test_marketdata_fyers_proxy.py`
- `CHANGELOG.md`

### Validation

- Pending: `python -m compileall backend\\services\\marketdata_service.py backend\\tests\\test_marketdata_fyers_proxy.py`
- Pending: `python -m pytest backend\\tests\\test_marketdata_fyers_proxy.py -q`

### Rollback

Restore `backend/services/marketdata_service.py`, `backend/tests/test_marketdata_fyers_proxy.py`, and `CHANGELOG.md` from `runtime/backups/2026-06-21_052243_v1/manifest.json`.
## v70-nse-db-page-trade-date-sync-flags - 2026-06-28 15:46:00 IST

Aligned the shared NSE MCAP, FFMC, and Delivery database pages so their trade-date cards, latest-row date column, and manual/automation flags are driven by the same backend trade-date source instead of stale local UI overrides or mismatched run-table logic.

### Root cause

- The React page was overriding backend `tradeDate` with a stale runtime job label even after the summary API had refreshed, which could leave the card on an older date while the latest rows were newer.
- The backend dashboard flag query was counting `RUN_TYPE IN ('PIPELINE', 'AUTOMATION', 'MANUAL', ...)`, but these run tables store dataset run types such as `MCAP`, `FFMC`, and `DELIVERY`, so the manual/automation cards collapsed to `N`.
- Manual `Insert / Process` calls and scheduler-direct automation runs were not consistently persisted into the dataset run tables, so latest-trade-date flag aggregation had no durable source for some successful inserts.

### Changes

- Added shared backend run-mode parsing and trade-date run-stat aggregation in `backend/services/nse_mcap_service.py`, then reused it from the FFMC and Delivery services.
- Persisted completed manual process runs and direct automation pipeline runs for MCAP, FFMC, and Delivery so latest-trade-date manual/automation flags survive refreshes and scheduler execution.
- Standardized latest-row date decoration so the `Trade Date` column prefers `TRADE_DATE` instead of fetch timestamp drift.
- Stopped `frontend/src/pages/ops/NseAutomationPage.tsx` from forcing manual/automation KPI values from local state, and limited runtime trade-date overrides to active in-flight work only.
- Updated the shared NSE success toasts to show page-specific “Extracted Successfully” messaging with row counts after successful completion.
- Added focused backend and frontend regression coverage for run-mode stats, persisted run hooks, latest-row date decoration, and the revised toast copy.

### Files changed

- `backend/services/nse_mcap_service.py`
- `backend/services/nse_ffmc_service.py`
- `backend/services/nse_delivery_service.py`
- `backend/tests/test_nse_mcap_service.py`
- `backend/tests/test_nse_ffmc_service.py`
- `backend/tests/test_nse_delivery_service.py`
- `frontend/src/pages/ops/NseAutomationPage.tsx`
- `frontend/tests/nseAutomationPage.test.ts`
- `docs/api-catalog.md`
- `CHANGELOG.md`

### Validation

Passed: `python -m pytest backend\tests\test_nse_mcap_service.py backend\tests\test_nse_ffmc_service.py backend\tests\test_nse_delivery_service.py -q` (89 passed)
Passed: `python -m compileall backend\services\nse_mcap_service.py backend\services\nse_ffmc_service.py backend\services\nse_delivery_service.py backend\routes\marketdata.py`
Passed: `cd frontend; npm.cmd run typecheck`
Passed: `cd frontend; npm.cmd run test -- nseAutomationPage.test.ts` (10 passed, unsandboxed because Vite config access is blocked in the sandbox on this host)
Passed: `cd frontend; npm.cmd run build` (unsandboxed because Vite config access is blocked in the sandbox on this host)
Passed: `python scripts\scan_api_duplicates.py --write-catalog docs\api-catalog.md` (`routes=190`, `exact_duplicates=0`, `similar_paths=21`)
Timed out: `python scripts\enterprise_validate.py` exceeded the 300-second command window in this environment

### Rollback

Restore the edited files from `runtime/backups/2026-06-28_152124_v1/manifest.json`, then rerun `python scripts\scan_api_duplicates.py --write-catalog docs\api-catalog.md` and rebuild the frontend bundle.
## v71-sector-discovery-plan-refresh-and-loader-hardening - 2026-06-28 17:28:00 IST

Implemented the scoped `Sector Wise Stocks` / `Sector Rotation` plan fixes needed to keep newly onboarded sector staging tables visible without destructive reseeding. The update hardens the generic sector CSV loader, broadens the shared frontend sector route registry for already supported sector codes, and makes forced sector discovery refresh clear the dependent caches that can hide new sectors.

### Root cause

- `backend/scripts/load_sector_file.py` still truncated staging tables and deleted `NSE_SYMBOL_SECTOR_MAP` rows before reseeding, which violated the additive conflict-safe onboarding flow and could silently rewrite existing sector ownership.
- `frontend/src/pages/sector/SectorWiseStocksPage.tsx` only loaded the stocksv2 sector selector list once, so pressing Refresh did not refresh the discovered sector list even though the backend discovery endpoint supported `refresh=1`.
- `frontend/src/data/sectorNav.ts` lagged behind the backend-supported sector codes, so older sector-wise stock routes could miss friendly route resolution for sectors already supported by the backend and SQL artifacts.
- Forced discovery refreshes cleared some in-process caches but did not fully clear the sector-specific cache services and snapshot files that can keep stale sector/table visibility around.

### Changes

- Switched `backend/scripts/load_sector_file.py` to safe name validation, insert-missing-only staging writes, idempotent `NSE_SYMBOL_SECTOR_MAP` merges, richer conflict reporting, and optional `NSE_SECTOR_MASTER` merge inputs. The loader no longer truncates staging tables or deletes existing sector mappings.
- Expanded `frontend/src/data/sectorNav.ts` with the backend-supported sector pages that were still missing from the shared route registry, added alias normalization for sector-code variants, and made underscore route variants normalize to the canonical hyphenated page when a matching page exists.
- Updated `frontend/src/pages/sector/SectorWiseStocksPage.tsx` so stocksv2 re-fetches `/api/sector-rotation/sectors` with `refresh=1` after a user refresh, keeping the selector list aligned with the backend discovery source.
- Hardened `backend/routes/sector_rotation.py` forced discovery refreshes so they also clear sector cache services, stock memory cache, local breadth snapshot state, and sector snapshot files before persisting the rebuilt discovery snapshot.
- Added focused regression coverage for the new discovery invalidation behavior and the Restaurants / Hospitality / Tourism route resolution path.

### Files changed

- `backend/routes/sector_rotation.py`
- `backend/scripts/load_sector_file.py`
- `backend/tests/test_sector_discovery_cache.py`
- `frontend/src/data/sectorNav.ts`
- `frontend/src/pages/sector/SectorWiseStocksPage.tsx`
- `frontend/tests/sectorWiseStocksPage.test.tsx`
- `CHANGELOG.md`

### Validation

- Pending: `python -m pytest backend\tests\test_sector_discovery_cache.py -q`
- Pending: `python -m compileall backend\routes\sector_rotation.py backend\scripts\load_sector_file.py`
- Pending: `cd frontend; npm.cmd run test -- sectorWiseStocksPage.test.tsx`
- Pending: `cd frontend; npm.cmd run typecheck`
- Pending: `cd frontend; npm.cmd run build`

### Rollback

Restore the edited files from `runtime/backups/2026-06-28_172101_v1-sector-discovery-plan/manifest.json`, then rerun the targeted backend/frontend validation commands and rebuild the frontend bundle.
## v130-fyers-current-date-calendar-gate - 2026-07-17 10:27:35 IST

Updated only the FYERS Automation calendar UI. Single Stock and Direct API Batch now allow all historical dates, including a range such as `1991-01-01` through the previous trading date. Before 5:00 PM IST, only the current calendar date is disabled; from 5:00 PM IST it becomes selectable. Backend API, FYERS fetch, and Oracle insertion logic are unchanged.

### Files changed

- `frontend/src/pages/fyers/FyersAutomationPage.tsx`
- `frontend/src/pages/fyers/FyersDatePickerField.tsx`
- `frontend/tests/fyersAutomationPage.test.tsx`
- `CHANGELOG.md`

### Rollback

Restore the four files from `runtime/backups/2026-07-17_102735_v1/manifest.json`.

## v129-fyers-direct-keyed-upsert - 2026-07-17 10:01:25 IST

Removed the remaining post-FYERS `STOCK_EOD_HISTORY` date lookups from `/app/fyers/automation` SingleStock persistence. FYERS candles are deduplicated in memory by normalized `(SYMBOL, TRADE_DATE)` and sent directly to the existing Oracle keyed `MERGE`; a matching key updates OHLCV values and a missing key inserts. No pre-fetch or pre-upsert date-range verification remains.

### Files changed

- `backend/services/marketdata_service.py`
- `backend/tests/test_marketdata_fyers_proxy.py`
- `CHANGELOG.md`

### Rollback

Restore the three files from `runtime/backups/2026-07-17_100125_v1/manifest.json`.

## v127-fyers-no-prefetch-duplicate-key - 2026-07-10 20:43:20 IST

Adjusted `/app/fyers/automation` SingleStock fetching so the selected date range is always requested from FYERS without pre-fetch coverage verification against `STOCK_EOD_HISTORY`. Preserved the existing post-fetch normalization, duplicate `(SYMBOL, TRADE_DATE)` collapse, change-aware Oracle `MERGE`, update/skip counts, and all existing automation routes and job flow.

### Files changed

- `backend/services/marketdata_service.py`
- `backend/tests/test_marketdata_fyers_proxy.py`
- `CHANGELOG.md`

### Validation

- `python -m py_compile backend\services\marketdata_service.py backend\tests\test_marketdata_fyers_proxy.py backend\tests\test_marketdata_fyers_job_progress.py` -> passed.
- `python -m pytest backend\tests\test_marketdata_fyers_proxy.py backend\tests\test_marketdata_fyers_job_progress.py -q` -> 66 passed.
- `python -m pytest backend\tests\test_marketdata_stock_history_sync.py -q` -> 5 passed.
- `python -m compileall -q backend` -> passed.
- `python scripts\scan_api_duplicates.py` -> passed; routes=191, exact_duplicates=0.

### Rollback

Restore the backed-up files from `runtime/backups/2026-07-10_204320_v127-fyers-no-prefetch-duplicate-key/`.
## v128-sector-overview-txt-controls - 2026-07-14

Updated Sector Overview TXT downloads to contain only the selected stock symbols as a plain comma-separated list without headers. CSV downloads remain tabular and unchanged. Improved trend checkbox and TXT/CSV button contrast, sizing, wrapping, and responsive stacking so controls remain visible on the light UI surface.

Follow-up: strengthened control color specificity and kept the disabled CSV button readable instead of fading its text into the light background.

### Files changed

- `frontend/src/pages/sector/SectorOverviewPage.tsx`
- `frontend/src/styles.css`
- `frontend/tests/sectorOverviewPage.test.ts`
- `CHANGELOG.md`
# 2026-07-15

- Added generic dynamic routing for `/app/sector/stocks/<sector-slug>` so `dairy-milk-products` opens the existing Sector Wise Stocks React page using `DAIRY_MILK_PRODUCTS`.
- Registered `DAIRY_MILK_PRODUCTS` with `NSE_NIFTY_DAIRY_MILK_PRODUCTS_STAGING` for strict sector-wise stock fallback rows.
- Installed `NSE_NIFTY_DAIRY_MILK_PRODUCTS_STAGING` and validated all six Dairy symbols in the live Oracle-backed NSE universe; Sector Rotation discovery now reports 90 sectors.
- Added the idempotent `backend/scripts/load_dairy_milk_products_sector.py` loader with explicit handling for the pre-existing `HERITGFOOD` FMCG mapping conflict.
- Added reusable sector hierarchy metadata (`PARENT_SECTOR`, `INDUSTRY`) to dynamic Sector Rotation discovery/breadth responses and generic database-backed alias resolution.
- Added idempotent Dairy & Milk Products migration, seed, validation, and safe disable rollback SQL. Symbols are inserted only when present in the active raw NSE-backed universe.

## v129-utilities-sector-membership - 2026-07-16

Added an explicit opt-in to the generic sector CSV loader for additive cross-sector staging membership. It preserves the existing canonical `NSE_SYMBOL_SECTOR_MAP` owner while adding the requested staging membership, so Utilities can display its source symbols without reclassifying the established Power, Oil & Gas, Waste & Water, or other sectors. The default loader behavior remains conflict-blocking.

### Files changed

- `backend/scripts/load_sector_file.py`
- `CHANGELOG.md`

### Validation

- Passed: `python -m py_compile backend\\scripts\\load_sector_file.py`.
- Passed: guarded Utilities dry-run from `G:\\SECTOR\\UTILITIES.csv`; 42 valid NSE/market-cap-eligible symbols, with existing canonical owners preserved.

### Rollback

Restore the files from `runtime/backups/2026-07-16_103133_v129-utilities-sector-membership/`. The live load is additive; reverting the new staging memberships requires a reviewed, symbol-scoped delete and sector cache refresh.
## v130-sector-wise-local-fastpath - 2026-07-17 18:06:09 IST

Fixed Sector Wise Stocks card loading when the database has current sector data but the local snapshot is expired. The sector-wise endpoint previously queried `nse_sector_master` through Oracle before it could select a known sector's local snapshot. During active market-data enrichment this made cards wait on Oracle despite valid snapshot rows being available. Known strict and merged sector aliases now resolve from the existing in-process mapping first; only unknown aliases use the Oracle resolver. The returned data contract and explicit refresh behavior are unchanged.

### Files changed

- `backend/routes/sector_rotation.py`
- `backend/tests/test_sector_rotation_route.py`
- `CHANGELOG.md`

### Validation

- Added regression coverage that a known sector card cannot call the Oracle master lookup before returning its local snapshot.

### Rollback

Restore these files from `runtime/backups/2026-07-17_180609_v130-sector-wise-local-fastpath`.
## v132-fyers-orphaned-stop-finalization - 2026-07-18 09:36:00 IST

Fixed FYERS Automation remaining at `Stopping...` after a partial batch whose worker session had already ended or restarted. The Stop API now distinguishes a live in-memory worker from an Oracle-only recovered job: live work continues to receive the existing cooperative stop flag, while an orphaned persisted run is finalized as `STOPPED` immediately. This prevents the recovered-job cache from staying active until the stale-heartbeat timeout and preserves the existing batch data and symbol results.

### Files changed

- `backend/services/marketdata_service.py`
- `backend/tests/test_marketdata_fyers_proxy.py`
- `CHANGELOG.md`

### Rollback

Restore these files from `runtime/backups/2026-07-18_093639_v132/` and restart the Flask service.

## 2026-07-22 - Sector Rotation missing-symbol export

Generated `runtime/reports/sector_rotation_missing_symbols_2026-07-22.csv` as a read-only comparison of the live 822-symbol Sector Rotation snapshot, all 93 registered sector staging tables, and `NSE_NIFTY500_DAILY_RAW_DATA_DEV`. The export contains 301 DEV-present, staging-present symbols absent from the 822-symbol snapshot.

## 2026-07-22 - Sector Rotation staged-symbol map synchronization

Added a dry-run-first, idempotent sync runner for the validated MCAP-filtered missing-symbol CSV. It excludes symbols already visible in the live Sector Overview snapshot, validates DEV eligibility, derives each remaining symbol's current staging ownership, updates only the supplied `NSE_SYMBOL_SECTOR_MAP` rows, and has one explicit Utilities staging backfill for `GUJENERGY`.
## v144-sector-overview-refresh-timeout - 2026-07-23 18:47:31 IST

Fixed `GET /api/sectors/overview?refresh=1` exceeding the five-minute browser timeout. The explicit overview refresh was forcing the broad Sector Rotation trend-map rebuild when no materialized trend view was available and issuing a `COUNT(DISTINCT symbol)` query for every staging table, even though the overview has its own trend snapshots, current DEV-price lookup, targeted missing-symbol DEV fallback, and needs only sector identities. Refresh now reuses a warmed trend map only as optional enrichment and reads sector metadata without staging-table counts; otherwise it resolves trends from overview-owned sources. Normal snapshot-first reads, API payloads, and Oracle data flow remain unchanged.

### Files changed

- `backend/routes/sector_rotation.py`
- `backend/tests/test_sector_rotation_route.py`
- `CHANGELOG.md`

### Rollback

Restore the before-change files from `runtime/backups/2026-07-23_184731_v1/` and restart Flask. No Oracle data or schema changes were made.
## v145-sector-overview-five-card-kpis - 2026-07-23 19:33:33 IST

Updated the Sector Overview KPI presentation to use five cards per desktop row, with responsive three- and two-column layouts on narrower screens. The `LTC_DATE` card now has an explicit non-wrapping value style, preserving the existing `dd-mm-yyyy` display as one horizontal line. No overview API, data, or refresh behavior changed.

### Files changed

- `frontend/src/pages/sector/SectorOverviewPage.tsx`
- `frontend/src/styles.css`
- `frontend/tests/sectorOverviewPage.test.ts`
- `CHANGELOG.md`

### Rollback

Restore the files from `runtime/backups/2026-07-23_193333_v1/`, rebuild the frontend, and restart Flask.
## v155-paper-packaging-overview-unknown-parity - 2026-07-27 11:15:00 IST

Published the verified Paper & Packaging reconciliation into the persisted Sector Overview snapshot. Twenty-four canonical staging members have no usable `NSE_NIFTY500_DAILY_RAW_DATA_DEV` row and are represented as `Unknown / Insufficient Data` in both Sector Wise Stocks and the Overview KPI. The other six members are DEV-resolved. This makes the visible counts match: Sector Wise `24 / 30` Unknown and Overview `24` Unknown.

### Rollback

Restore `runtime/snapshots/sector_overview_latest.json` from the backup/previous published snapshot, then restart Flask.

## v154-v3-dev-unknown-reconciliation - 2026-07-27 10:40:00 IST

Reconciled V3 `DATA_WEAK` symbols against the DEV-backed Sector Overview during an explicit Overview refresh. The refresh now includes same-day V3 Unknown symbols that are absent from the canonical overview map, calculates their latest DEV price, 52-week extrema, and EMAs through the existing Overview pipeline, and publishes the resolved trend. Normal Overview reads remain snapshot-first and Oracle-free.

### Files changed

- `backend/routes/sector_rotation.py`
- `backend/services/sector_rotation_v3_stock_service.py`
- `backend/tests/test_sector_rotation_route.py`
- `backend/tests/test_sector_rotation_v3_stock_service.py`
- `CHANGELOG.md`

### Rollback

Restore from `runtime/backups/2026-07-27_094833_v152-v3-overview-trend-parity/` and `runtime/backups/2026-07-27_100852_v152-v3-overview-trend-parity/`, then restart Flask and refresh the Overview snapshot.

## v153-v3-52week-extrema-contract - 2026-07-27 10:30:00 IST

Fixed blank `52WH` and `52WL` cells on V3 Sector Wise Stocks pages. The V3 stock contract already supplied the numeric levels as `week52HighLevel` and `week52LowLevel`, but the shared React adapter only recognized the V1/V2 aliases. The adapter now accepts the V3 names, preserving the existing table and formatting logic.

### Files changed

- `frontend/src/adapters/sectorPageAdapter.ts`
- `frontend/tests/sectorWiseStocksPage.test.tsx`
- `CHANGELOG.md`

### Rollback

Restore from `runtime/backups/2026-07-27_101355_v153-v3-52week-extrema-adapter/` and `runtime/backups/2026-07-27_101718_v153-v3-52week-extrema-adapter/`, then rebuild the frontend.

## v152-v3-overview-trend-parity - 2026-07-27 09:55:00 IST

Corrected a V3 Sector Wise fallback that labelled valid canonical members as `Unknown / Insufficient Data` solely because the V3 stock snapshot was stale. It now reuses the existing persisted Sector Overview trend and price row for each missing member. `Unknown / Insufficient Data` is returned only when both V3 and Sector Overview lack usable data, so the page and Overview KPI use the same trend evidence.

### Files changed

- `backend/services/sector_rotation_v3_stock_service.py`
- `backend/tests/test_sector_rotation_v3_stock_service.py`
- `CHANGELOG.md`

### Rollback

Restore from `runtime/backups/2026-07-27_094833_v152-v3-overview-trend-parity/`, then restart Flask.

## v151-v3-sector-wise-membership-parity - 2026-07-27 09:35:00 IST

Fixed the V3 UI inconsistency where Sector Rotation displayed the canonical sector population while Sector Wise Stocks showed only the rows present in an incomplete/stale V3 stock snapshot. The page now resolves only the selected sector's canonical membership and preserves real computed rows; any constituent awaiting technical computation is explicitly labelled `Unknown / Insufficient Data` instead of being silently omitted. This avoids the global Strong Technicals rebuild that previously made refresh time out.

### Files changed

- `backend/routes/sector_rotation.py`
- `backend/services/sector_rotation_v3_stock_service.py`
- `backend/tests/test_sector_rotation_route.py`
- `backend/tests/test_sector_rotation_v3_stock_service.py`
- `CHANGELOG.md`

### Rollback

Restore from `runtime/backups/2026-07-27_090806_v151-v3-scoped-stock-snapshot-repair/`, then restart Flask.

## v149-sector-snapshot-freshness - 2026-07-26 20:38:51 IST

Fixed stale sector presentation after the DEV market-data day advances. Sector Overview keeps its fast persisted first response, then automatically runs its existing refresh only when database sync status proves DEV has a newer `LTC_DATE`. Sector Wise snapshots with a current price/date but missing 52-week high or low are rejected and rebuilt through the canonical DEV fallback, preventing partial one-stock snapshots from disagreeing with Sector Rotation membership counts. V3 stock rows now expose their V3 `trendState` through the legacy `trend` contract, so the rendered trend, EMA flags, score, and confidence use one classifier.

### Files changed

- `backend/routes/sector_rotation.py`
- `backend/services/sector_rotation_v3_stock_service.py`
- `backend/tests/test_sector_rotation_route.py`
- `backend/tests/test_sector_rotation_v3_stock_service.py`
- `frontend/src/pages/sector/SectorOverviewPage.tsx`
- `frontend/src/services/api/sectorApi.ts`
- `frontend/tests/sectorOverviewPage.test.ts`
- `CHANGELOG.md`

### Rollback

Restore from `runtime/backups/2026-07-26_203851_v146-sector-snapshot-freshness/` and `runtime/backups/2026-07-26_204909_v146-sector-snapshot-freshness/`, rebuild the frontend, and restart Flask. No Oracle schema or data changes were made.
## v152-nifty500-sync-crud - 2026-07-28 07:53:12 IST

Fixed NIFTY500 Sync table update and delete actions. Table edits now use an in-page, explicit Update form instead of a browser-native prompt, so selecting Edit reliably leads to the same typed API request used by the page. Delete is now idempotent for a stale table row: it returns the current duplicate-free snapshot and reports the symbol as already absent instead of failing the action.

Server-side duplicate protection remains unchanged: an update targeting an existing normalized symbol is rejected before the CSV is written. The existing CSV is still rewritten through the locked, normalized, atomic writer.

### Files changed

- `frontend/src/pages/fyers/Nifty500SyncPage.tsx`
- `backend/services/nifty500_sync_service.py`
- `backend/tests/test_marketdata_nifty500_sync.py`
- `CHANGELOG.md`

### Rollback

Restore these files from `runtime/backups/2026-07-28_075312_v149-nifty500-sync-crud/` and rebuild the frontend. No database changes were made.
## v153-nifty500-sync-payload - 2026-07-28 09:54:50 IST

Fixed Existing FYERS CSV symbols rendering as zero rows when the NIFTY500 Sync response is delivered in a response envelope. The React page now normalizes both the established direct snapshot and a `{ data: snapshot }` / `{ payload: snapshot }` / `{ result: snapshot }` response before reading the existing rows and KPI fields. No CSV, API route, or persistence behavior changed.

The same normalization now applies to Add, Delete refresh, Update, Compare, and Merge results, ensuring the Existing FYERS CSV card and table counts immediately reflect the returned duplicate-safe snapshot.

### Files changed

- `frontend/src/pages/fyers/Nifty500SyncPage.tsx`
- `frontend/tests/nifty500SyncErrorHandling.test.ts`
- `CHANGELOG.md`

### Rollback

Restore these files from `runtime/backups/2026-07-28_095450_v153-nifty500-sync-payload/` and rebuild the frontend.
## v154-sector-wise-unknown-downloads - 2026-07-28 10:19:21 IST

Added Sector Wise Stocks TXT and CSV downloads in the visible, right-side Sector Hierarchy control group. Both exports include only symbols whose Trend is unknown, insufficient, or blank. TXT is a comma-separated symbol list; CSV preserves the displayed Sector Wise table columns and formatted values for those same rows. Files use the `SectorNameTimeStamp.txt` / `.csv` pattern.

### Files changed

- `frontend/src/pages/sector/SectorWiseStocksPage.tsx`
- `frontend/tests/sectorWiseStocksPage.test.tsx`
- `CHANGELOG.md`

### Rollback

Restore the files from `runtime/backups/2026-07-28_101921_v1/`, rebuild the frontend, and restart Flask. No backend, API, Oracle, or schema changes were made.
## v150-sector-rotation-consolidated-download - 2026-07-29

Added one `Download TXT` button to the shared toolbar for `/app/sector/rotation` and `/app/sector/stockedge-rotation`, in the requested `Total | Download TXT | Refresh` sequence. It reads the existing Sector Wise Stocks data for every sector, includes only blank, `Unknown`, or `Insufficient` Trend rows, de-duplicates symbols, and downloads one comma-separated `SectorWiseUnknownInsufficient.txt` file. Existing individual sector TXT/CSV exports and all API/data contracts remain unchanged.

### Files changed

- `frontend/src/components/strategy/StrategyToolbar.tsx`
- `frontend/src/pages/sector/SectorRotationPage.tsx`
- `frontend/tests/strategyToolbar.test.tsx`
- `CHANGELOG.md`

### Rollback

Restore `runtime/backups/2026-07-29_183548_v150-sector-rotation-consolidated-download/` and `runtime/backups/2026-07-29_183723_v150-sector-rotation-consolidated-download/`, then rebuild the frontend. No backend, API, or Oracle rollback is required.
## v151-sector-wise-consolidated-instant - 2026-07-29

Replaced the rotation-toolbar consolidated TXT export's per-sector request fan-out with `GET /api/sectors/sector-wise-unknown-symbols`. The route reads only the already-published Sector Wise V3 snapshot, filters blank, `Unknown`, and `Insufficient` trend rows, and returns de-duplicated symbols in one response. Sector Overview is not involved.

### Files changed

- `backend/routes/sector_rotation.py`
- `frontend/src/services/api/sectorApi.ts`
- `frontend/src/pages/sector/SectorRotationPage.tsx`
- `docs/api-catalog.md`
- `CHANGELOG.md`

### Rollback

Restore `runtime/backups/2026-07-29_193535_v151-sector-wise-consolidated-instant/`, rebuild the frontend, and restart Flask. No Oracle data or schema rollback is required.
## 2026-07-31

- Fixed Sector Overview normal reads to fail fast when the persisted overview snapshot is unavailable, rather than falling through to a potentially slow live rebuild. Explicit `refresh=1` retains the existing rebuild behavior.
## v152-sector-wise-v3-momentum-direction - 2026-07-31 10:35:03 IST

Corrected the V3 Sector Wise Stocks backend trend contract without changing the UI. A complete four-EMA alignment now establishes the non-contradictory direction: `Y/Y/Y/Y` is Strong Uptrend only when all existing technical confirmation is present, otherwise Uptrend; three `Y` flags is Uptrend; two `Y` plus two `N` is Sideways; and three or four `N` flags is Downtrend. The confirmation path now uses the existing RSI, MACD, ADX, ATR, Volume-20 ratio, delivery score, price action, support/resistance, trendline, breakout, chart-pattern, Strong Technicals score, market-cap, and available FFMC values. Market cap and FFMC are liquidity-quality confirmation only; they do not invert price direction. Published V3 rows are reconciled at read time, before the legacy Overview fallback, so the active page does not need a snapshot rebuild to stop showing contradictory labels.

### Files changed

- `backend/services/sector_rotation_v3_stock_service.py`
- `backend/tests/test_sector_rotation_v3_stock_service.py`
- `CHANGELOG.md`

### Rollback

Restore the files from `runtime/backups/2026-07-31_103503_v151-sector-wise-ema-trend-alignment/` and restart the Flask service. No database schema, source data, or UI files were modified.
## v153-sector-wise-v3-mcap-coverage - 2026-08-01 07:43:29 IST

Fixed missing `INDEX`, `MCAP`, and `MCAP_RANK` cells for otherwise valid rows on Sector Wise Stocks V3 pages. The V3 stock publisher previously accepted only the current global market-cap batch, which omits a small number of valid symbols. It now keeps current-date values first and backfills only omitted symbols from their latest persisted market-cap record during snapshot publication. No UI, routes, database schema, or response keys changed.

`52WH` and `52WL` remain unavailable for stocks with fewer than 252 trading sessions (for example, a recent listing). Those cells accurately remain `-`; the system does not label a shorter since-listing range as a 52-week range.

### Files changed

- `backend/services/strong_technicals_service.py`
- `backend/tests/test_strong_technicals_service.py`
- `CHANGELOG.md`

### Rollback

Restore the files from `runtime/backups/2026-08-01_074329_v151-sector-wise-v3-mcap-coverage/` and republish the prior V3 stock snapshot if needed. No database rollback is required.
## v152-symbol-display-normalization - 2026-08-01 08:37:46 IST

Removed exchange prefixes and NSE cash-series suffixes from React symbol display and input normalization. The backend code and API contracts are unchanged. Database cleanup is handled separately with a rollback export and excludes existing backup tables.

### Files changed

- `frontend/src/utils/symbols.ts`
- React symbol display/input adapters and pages
- `frontend/tests/symbolNormalization.test.ts`
- `CHANGELOG.md`

### Rollback

Restore the frontend files from `runtime/backups/2026-08-01_083746_v152-symbol-display-normalization/` and rebuild the frontend. Database rollback uses the data export manifest created for the cleanup.
## v174-watchlist-main-symbol-dropdown - 2026-08-13 17:55:00 IST

Replaced only the Main NSE symbols searchable input with a native dropdown populated from the existing complete NSE symbol source and sorted A-Z. The existing My Watchlist symbols dropdown, saved-symbol persistence, and `+` add/hydration behavior are unchanged.

### Files changed

- `frontend/src/pages/watchlist/WatchlistPage.tsx`
- `frontend/tests/watchlistPage.test.tsx`
- `CHANGELOG.md`

### Rollback

Restore these files from `runtime/backups/2026-08-13_175212_v1/` and rebuild `frontend/dist`. No backend, API, database, or saved-watchlist data rollback is required.
## v175-watchlist-symbol-dropdown-cache - 2026-08-13 18:38:00 IST

Improved Main NSE symbols dropdown responsiveness. The page now displays the previously loaded, full A-Z NSE list from browser storage immediately and refreshes it from the existing symbols API in the background. The initial uncached response remains authoritative, while repeat visits no longer wait for the Oracle-backed full-symbol request. My Watchlist symbols and its saved-symbol behavior are unchanged.

### Files changed

- `frontend/src/pages/watchlist/WatchlistPage.tsx`
- `frontend/tests/watchlistPage.test.tsx`
- `CHANGELOG.md`

### Rollback

Restore these files from `runtime/backups/2026-08-13_183635_v1/` and rebuild `frontend/dist`. Clearing browser key `ct_watchlist_main_nse_symbols_v1` only removes the performance cache; it does not remove any saved watchlist symbols.
## v176-watchlist-searchable-symbol-dropdown - 2026-08-13 19:02:00 IST

Changed only the Main NSE symbols control to a compact searchable dropdown. Its desktop width is reduced to approximately half the previous allocation, while opening it provides an in-menu NSE symbol search and scrollable filtered results. Selecting an item still requires the existing `+` action to add it; My Watchlist symbols remains unchanged.

### Files changed

- `frontend/src/pages/watchlist/WatchlistPage.tsx`
- `frontend/tests/watchlistPage.test.tsx`
- `CHANGELOG.md`

### Rollback

Restore these files from `runtime/backups/2026-08-13_185908_v1/` and rebuild `frontend/dist`. No API, backend, database, or saved-watchlist data changes are involved.
## v174-tradesetup-session-snapshot - 2026-08-13 19:23:00 IST

Added a tab-scoped, five-minute temporary snapshot for Trade SetUp Watchlist rows. Returning to `/app/tradesetup` now restores the latest available rows immediately from browser session storage, without adding an API, backend cache, or Oracle persistence. Saved-symbol removal and updates prune obsolete snapshot rows, and Live/Refresh always rehydrate current data through the existing source composition path.

### Files changed

- `frontend/src/pages/watchlist/WatchlistPage.tsx`
- `frontend/tests/watchlistPage.test.tsx`
- `CHANGELOG.md`

### Validation

- `npm.cmd run test -- tests\watchlistPage.test.tsx tests\watchlistData.test.ts` from `frontend`: 13 passed.
- `npm.cmd run typecheck` from `frontend`: passed.
- `npm.cmd run build` from `frontend`: passed (734 modules transformed). Existing Browserslist-age and large-chunk advisories remain non-blocking.

### Rollback

Restore the files from `runtime/backups/2026-08-13_192312_v174-tradesetup-session-snapshot/`, then rebuild `frontend/dist`. The feature is browser-session-only; clearing the browser tab/session storage removes cached rows immediately. No backend, API, Oracle, or database rollback is required.
## v174-dashboard-movers-timeout - 2026-08-13 19:29:00 IST

Fixed `/api/dashboard/movers?limit=25&segment=nifty500` timing out on dashboard load when its usable persisted snapshot contained incomplete optional market-cap metadata. Snapshot and cache reads now normalize aliases without running a fresh Oracle market-cap lookup or rejecting the complete dashboard payload; a forced refresh continues to schedule the existing background rebuild.

### Files changed

- `backend/routes/dashboard.py`
- `backend/tests/test_dashboard_route.py`
- `CHANGELOG.md`

### Validation

- `python -m pytest backend\tests\test_dashboard_route.py -q`

### Rollback

Restore the files from `runtime/backups/2026-08-13_192842_v174-dashboard-movers-timeout/` and restart Flask. No API, database, or schema contract changed.
## v175-watchlist-overview-load - 2026-08-13 19:27:00 IST

Removed FFMC and LTP from the Trade SetUp Overview view. A hard refresh now hydrates only the selected saved symbol and requests only its latest daily candle; selecting a different saved symbol loads it on demand, while Refresh continues to hydrate every saved symbol.

### Files changed

- `frontend/src/pages/watchlist/WatchlistPage.tsx`
- `frontend/src/services/api/watchlistData.ts`
- `frontend/src/styles.css`
- `CHANGELOG.md`

### Validation

- `npm.cmd run test -- tests\watchlistPage.test.tsx tests\watchlistData.test.ts`: 13 passed.
- `npm.cmd run typecheck`: passed.
- `npm.cmd run build`: passed (734 modules transformed). Existing Browserslist-age and large-chunk advisories remain non-blocking.

### Rollback

Restore `runtime/backups/2026-08-13_192710_v1/`, then rebuild `frontend/dist`. No backend, API, Oracle, or persisted watchlist data changed.
## v175-tradesetup-navigation-refresh - 2026-08-13 19:52:00 IST

Fixed Trade SetUp route-entry loading. The toolbar now enters its refreshing state whenever the Watchlist page opens or is navigated back to, then force-hydrates every saved symbol through the existing data composition flow before returning to live status. The temporary session snapshot remains only an instant first paint and no longer suppresses route-entry refreshes.

### Files changed

- `frontend/src/pages/watchlist/WatchlistPage.tsx`
- `CHANGELOG.md`

### Validation

- `npm.cmd run test -- tests\watchlistPage.test.tsx tests\watchlistData.test.ts` from `frontend`: 13 passed.
- `npm.cmd run typecheck` from `frontend`: passed.
- `npm.cmd run build` from `frontend`: passed (734 modules transformed). Existing Browserslist-age and large-chunk advisories remain non-blocking.

### Rollback

Restore the files from `runtime/backups/2026-08-13_195240_v175-tradesetup-navigation-refresh/`, then rebuild `frontend/dist`. No backend, API, Oracle, or database rollback is required.
## v176-tradesetup-progressive-snapshot - 2026-08-13 19:56:00 IST

Improved Trade SetUp first-display performance for saved Watchlist symbols. Row composition now publishes bars, metadata, sector, technical, S&R, volume, and delivery results independently instead of waiting for every source. The page renders saved symbols immediately, restores a 30-minute browser snapshot on later route entries, and limits the route-entry toolbar loading indicator to one second while the existing sources continue updating in the background.

### Files changed

- `frontend/src/services/api/watchlistData.ts`
- `frontend/src/pages/watchlist/WatchlistPage.tsx`
- `frontend/tests/watchlistPage.test.tsx`
- `CHANGELOG.md`

### Validation

- Pending: focused Watchlist tests, TypeScript validation, and production build.

### Rollback

Restore the files from `runtime/backups/2026-08-13_195641_v176-tradesetup-progressive-snapshot/`, then rebuild `frontend/dist`. Clearing `ct_watchlist_strategy_rows_snapshot_v1` in browser local storage immediately removes the temporary client snapshot. No backend, API, Oracle, or database rollback is required.
## v177-tradesetup-fast-refresh-targets - 2026-08-13 21:39:00 IST

Fixed Trade SetUp Watchlist latency and toolbar refresh synchronization. Route entry, selection, Live, and Refresh now hydrate only the selected saved symbol, join an existing in-flight request instead of dropping the refresh, and return after the initial Bars/Symbol sources while slower existing S&R, technical, Sector Wise, Volume, and Delivery sources update the same row progressively.

Targets now prioritize manual resistance levels and fill only missing target slots from the existing generated S&R evidence, enforcing the requested minimum 5/10/15/20 percent ladder when a suitable generated resistance is unavailable. The S&R tab labels every ladder and strong level as MANUAL or DYNAMIC; strong levels remain owned by the existing OHLCV/pivot/ATR/price-action S&R service rather than static percentage calculations.

The Overview table no longer forces a 1500px horizontal scroll surface, and the My Watchlist symbols select now sizes to its current content instead of occupying a static grid width. Cached symbol-universe data is retained if its background refresh fails.

### Files changed

- `frontend/src/pages/watchlist/WatchlistPage.tsx`
- `frontend/src/services/api/watchlistData.ts`
- `frontend/src/styles.css`
- `frontend/tests/watchlistPage.test.tsx`
- `frontend/tests/watchlistData.test.ts`
- `CHANGELOG.md`

### Validation

- `npm.cmd run test -- tests\watchlistData.test.ts tests\watchlistPage.test.tsx`: 16 passed, including the 750 ms initial-render budget regression.
- `npm.cmd run typecheck`: passed.
- `npm.cmd run build`: passed (734 modules transformed). Existing Browserslist-age and large-chunk advisories remain non-blocking.

### Rollback

Restore `runtime/backups/2026-08-13_211136_v177-tradesetup-fast-refresh-targets/`, then rebuild `frontend/dist`. No backend, API, Oracle, schema, or saved-watchlist contract changed.
## v178-tradesetup-symbol-controls - 2026-08-14 05:34:00 IST

Fixed Trade SetUp symbol-control interactions. The Main NSE symbol menu now closes when the pointer leaves the selector/menu surface, when the user clicks elsewhere, or when Escape is pressed. Main NSE and My Watchlist selectors now occupy equal responsive grid columns so saved symbols remain fully visible.

Selecting an item from the already loaded NSE universe and pressing `+` now updates the saved Watchlist and its dropdown immediately. The existing API validation remains as a fallback only for values not present in the loaded/cached NSE universe, and live row hydration continues in the background through the existing source flow.

### Files changed

- `frontend/src/pages/watchlist/WatchlistPage.tsx`
- `frontend/tests/watchlistPage.test.tsx`
- `CHANGELOG.md`

### Validation

- Included in the final v180 validation cycle: 17 focused tests passed, typecheck passed, and production build passed.

### Rollback

Restore `runtime/backups/2026-08-14_052957_v178-tradesetup-symbol-controls/`, then rebuild `frontend/dist`. No backend, API, Oracle, schema, or saved-data contract changed.
## v179-tradesetup-24h-snapshot - 2026-08-14 05:36:00 IST

Extended the Trade SetUp browser row snapshot from 30 minutes to 24 hours for immediate repeat visits. The latest selected or newly added Watchlist symbol still starts the existing live hydration flow in the background, so the snapshot improves first paint without suppressing current Bars, technical, S&R, Sector Wise, Volume, or Delivery updates.

### Files changed

- `frontend/src/pages/watchlist/WatchlistPage.tsx`
- `frontend/tests/watchlistPage.test.tsx`
- `CHANGELOG.md`

### Validation

- Included in the final v180 validation cycle: 17 focused tests passed, typecheck passed, and production build passed.

### Rollback

Restore `runtime/backups/2026-08-14_053314_v179-tradesetup-24h-snapshot/`, then rebuild `frontend/dist`. Clearing `ct_watchlist_strategy_rows_snapshot_v1` removes the browser snapshot immediately. No backend, API, Oracle, or database rollback is required.
## v180-tradesetup-data-availability - 2026-08-14 05:51:00 IST

Fixed partial Trade SetUp source updates replacing previously visible 24-hour snapshot values with blanks. Progressive updates now merge non-empty Bars, Sector Rotation/Sector Wise, Technical, S&R, Volume, and Delivery values into the last-known row while retaining explicit state for every reused source.

Each tab now displays its source health as `Loaded`, `Loading`, `Not available`, or `Load failed`. Missing cells use the same explicit state instead of `-`, so users can distinguish an API/loading problem from a successful source response that has no data for the selected NSE symbol. Targets continue to use the available price with 5/10/15 percent fallbacks; S&R levels remain sourced only from the existing manual/generated S&R service.

### Files changed

- `frontend/src/pages/watchlist/WatchlistPage.tsx`
- `frontend/src/services/api/watchlistData.ts`
- `frontend/tests/watchlistPage.test.tsx`
- `frontend/tests/watchlistData.test.ts`
- `CHANGELOG.md`

### Validation

- `npm.cmd run test -- tests\watchlistData.test.ts tests\watchlistPage.test.tsx`: 17 passed.
- `npm.cmd run typecheck`: passed.
- `npm.cmd run build`: passed (734 modules transformed). Existing Browserslist-age and large-chunk advisories remain non-blocking.
- Live browser: Flask served `index-DXnfkpAL.js` with HTTP 200; the NSE menu closed after an outside click; TCS appeared in My Watchlist immediately after `+`; both selectors rendered at 369.5px; Overview had no horizontal overflow; source badges and missing cells exposed live `Loading`/`Load failed` states. The temporary TCS validation symbol was removed afterward.

### Rollback

Restore `runtime/backups/2026-08-14_053909_v180-tradesetup-data-availability/`, then rebuild `frontend/dist`. No backend, API, Oracle, or database contract changed.
## 2026-08-20 - Trade SetUp controls and synchronization

- Reduced Main NSE and My Watchlist selector widths and made the full selector/button area clickable.
- Kept saved-symbol rows visible immediately, synchronized all saved symbols on route entry and Live/Refresh, and changed toolbar search to My Watchlist search.
- Removed the reset control and requested explanatory copy from the visible Trade SetUp surface.

## 2026-08-20 - Trade SetUp served UI correction

- Removed the explanatory header copy and Reset filter control from the rendered React page.
- Added immediate selected-symbol hydration after a validated symbol is saved, while retaining the existing progressive source updates and selected-stock analysis binding.
- Constrained the symbol-control surface so Main NSE and My Watchlist selectors remain compact and readable.
- Updated the Watchlist page regression expectation so source failures are presented as `No Data`, never `Load failed`.

## 2026-08-20 - Theme state synchronization

- Reconciled the primary and legacy theme storage keys so a persisted dark palette cannot leave the shared ThemeToggle reporting light mode.
- Preserved the existing toggle behavior and root `data-theme`/`dark` class application across refresh and navigation.

## v182-tradesetup-toolbar-data-repair - 2026-08-31 19:36:14 IST

- Changed the shared Strategy toolbar surface, search field, timeframe selector, total chip, and metadata text to a light sky-blue/white palette in both light and dark modes so shared page toolbars no longer turn dark.
- Removed the duplicate all-saved-symbol Trade SetUp route-entry hydration. The existing selected-symbol request remains progressive, abortable, and bounded, while explicit Live/Refresh continues to refresh the saved list.
- Preserved the centralized login authentication flow and its existing credential-only dark autofill protection; the rebuilt React bundle publishes that styling to the Flask-served app.

### Files changed

- `frontend/src/components/strategy/StrategyToolbar.tsx`
- `frontend/src/pages/watchlist/WatchlistPage.tsx`
- `frontend/tests/strategyToolbarSingleSurface.test.tsx`
- `frontend/tests/watchlistPage.test.tsx`
- `CHANGELOG.md`

### Rollback

Restore `runtime/backups/2026-08-31_193614_v182-tradesetup-toolbar-data-repair/`, then rebuild `frontend/dist`. No backend, API, Oracle, authentication, schema, or saved-watchlist contract changed.
## 2026-09-16 - Read-only MCP adapter over existing price-action services

- Added 14 explicit, bounded read-only MCP tools using the official MCP Python SDK v2 with stdio and Streamable HTTP transports.
- Reused the existing chart, marketdata, technical-utils, and price-action service owners; no Flask endpoint, Oracle schema, or market-data flow was added or changed.
- Added fail-closed remote binding, loopback Host validation, optional bearer authentication, origin allowlisting, sanitized errors/logs, a bounded/expiring response cache, prompt-injection-aware data boundaries, and no arbitrary-SQL capability.
- Added MCP contract/service tests, Windows launchers, an in-process validator, ChatGPT setup guidance, and a tool-to-existing-owner reuse map.
- Kept MCP dependencies in a dedicated `.venv-mcp` workflow so the existing application dependency pins and listener remain unchanged.
- Stabilized full-suite cache tests by removing temporary `cache` stubs from `sys.modules` immediately after their owning modules import, preventing cross-test collection pollution without changing production imports.
## 2026-09-17 - MCP validation completion

- Completed direct MCP SDK discovery in the isolated `.venv-mcp` environment and made `scripts/validate_mcp.py` runnable by file path from the repository root.
- Removed one unused MCP service import and documented the intentional optional-dependency import order in the MCP contract test so Ruff can validate the complete MCP change set.
- Eliminated the full-suite `cache.estimate_size_bytes` collection collision by removing test-owned `cache` stubs from `sys.modules` after their owning services are imported; production cache imports and behavior remain unchanged.
- No Flask API route, Oracle schema/data, frontend contract, authentication flow, trading calculation, or immutable market-data flow changed.

### Rollback

Restore the validation files and `CHANGELOG.md` from `runtime/backups/2026-09-17_155623_v2026_09_17-mcp-validation-fixes/`; restore the cache-test isolation changes from `runtime/backups/2026-09-17_110537_v2026_09_17-validation-cache-pollution-root/`.
