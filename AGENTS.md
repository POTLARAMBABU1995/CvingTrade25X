# Repository Guidelines

## Project Overview
- `CvingTrade25X` is a layered trading, market-data, technical-analysis, strategy, and automation application.
- The active integrated path is React + TypeScript -> shared frontend API client -> Flask blueprints/services -> Oracle 19c, with runtime jobs, caches, locks, snapshots, and batch automation under the existing Python backend.

## Enterprise Governance Standard

### Project Runtime Standard
- Current runtime is Flask plus React plus Oracle 19c.
- Active backend entrypoint is `backend/app.py`; feature APIs are registered as Flask blueprints from `backend/routes`.
- Do not migrate Flask to FastAPI unless the user explicitly approves a runtime migration.
- Do not bypass existing `backend/app.py`, blueprint registration, centralized auth/session handling, or the shared frontend API client.
- Preserve the existing market-data flow: FYERS API or NSE files -> `STOCK_EOD_HISTORY` -> auto/manual merge -> `NSE_NIFTY500_DAILY_RAW_DATA_DEV` -> backend APIs -> React UI.

### Agent Roles
- `Main Engineering Agent`: Owns end-to-end requirement tracing, smallest safe implementation, validation, and rollback notes.
- `Architecture Agent`: Owns architecture consistency, no-duplicate-flow reviews, and durable decisions in `MEMORY.md`.
- `Backend Agent`: Owns Flask routes, request validation, service orchestration, response contracts, and backward-compatible APIs.
- `Frontend Agent`: Owns React + TypeScript pages, shared API services, state handling, Tailwind/shadcn-aligned UI, and frontend tests.
- `Oracle Agent`: Owns Oracle SQL, bind variables, migrations, rollback scripts, validation SQL, and data-flow safety.
- `Security Agent`: Owns secret handling, safe logging, auth boundaries, input validation, dependency checks, SonarQube, and Checkmarx standards.
- `Test Agent`: Owns targeted backend/frontend/contract tests, coverage evidence, and validation reports.
- `Documentation Agent`: Owns `README.md`, `docs/api-catalog.md`, architecture docs, and changelog accuracy.
- `Release Agent`: Owns version entries, backups, release gates, lifecycle controls, and rollback readiness.

### Mandatory Pre-Change Steps
- Inspect existing files before editing.
- Search for existing API endpoints in `backend/routes`.
- Search for existing frontend service methods in `frontend/src/api` and `frontend/src/services`.
- Search for existing backend service methods in `backend/services`.
- Search for existing SQL, repository, or Oracle access logic before adding new DB access.
- Create a local backup of every existing file before editing it with `python scripts\backup_before_change.py ...`.
- Create or update a version entry with timestamp in `CHANGELOG.md`.

### No Duplicate API Rule
- Before adding any endpoint, search `backend/routes`, `backend/services`, `frontend/src/api`, `frontend/src/services`, and `docs/api-catalog.md`.
- Reuse or extend an existing API when it satisfies the requirement.
- Create a new API only when no existing endpoint or backward-compatible extension can satisfy the requirement.
- After any API change, run `python scripts\scan_api_duplicates.py` and update `docs/api-catalog.md`.

### Security Rules
- No hardcoded passwords, tokens, API keys, cookies, Oracle credentials, or session values.
- No direct SQL string concatenation using user input.
- Use bind variables for Oracle SQL.
- Validate every request payload at the route boundary or service boundary.
- Protect authenticated routes through the existing centralized auth/session flow.
- Log request IDs, route, status, duration, and safe context only.
- Never log access tokens, passwords, cookies, raw authorization headers, full session tokens, Aadhaar/PAN values, or DB secrets.

### Testing Rules
- Every backend behavior change requires unit or integration tests where feasible.
- Every frontend service/UI change requires frontend test coverage where feasible.
- Every API change requires API catalog and contract documentation updates.
- Critical changed modules target 99 percent coverage.
- If legacy modules cannot reach 99 percent immediately, document the gap and enforce 99 percent coverage for new and modified critical code.
- Required validation for governance changes: `python scripts\scan_api_duplicates.py` and `python scripts\enterprise_validate.py`.

### Documentation Rules
- After every file change, append or update `CHANGELOG.md`.
- For architecture or process decisions, update `MEMORY.md`.
- For agent/development rules, update `AGENTS.md`.
- For setup, run, validation, release, or rollback changes, update `README.md`.
- For dependency changes, update `requirements.txt` with a version comment.
- No release is complete unless generated reports under `runtime/reports` are reviewed.

## CvingTrade25X Agent Enhancements
- These enhancements extend the existing repository guidance below. For any new or changed UI development, they supersede older legacy HTML/CSS/JavaScript guidance: use the approved React + TypeScript + Tailwind CSS + shadcn/ui stack unless the user explicitly asks for a legacy-file maintenance change.

## Project Memory
- Project: `CvingTrade25X`
- Approved technology stack:
  - Frontend: React + TypeScript only for new UI development; Tailwind CSS for styling; shadcn/ui for shared UI components; reusable components + existing app navigation/layout patterns
  - Backend: Existing Python backend only; preserve the active Flask `backend/app.py` + `backend/routes` + `backend/services` runtime and API contracts
  - Database: Oracle 19c existing schema only; no schema changes without explicit approval
  - Runtime URL: `http://127.0.0.1:5055`
  - API base: `http://127.0.0.1:5055/api`
- Engineering rules:
  - New UI work must be implemented in `frontend/src` with React + TypeScript + Tailwind CSS + shadcn/ui.
  - Do not implement new features using legacy plain HTML, old JavaScript, jQuery, standalone CSS pages, or unrelated UI frameworks.
  - Retired legacy `html/`, root `css/`, and legacy `assets/` UI surfaces are no longer active in the tree; use repository history or `runtime/backups` only as reference.
  - Do not recreate old static UI paths after migration; rebuild recovered behavior in React + TypeScript + Tailwind CSS instead.
  - Preserve existing backend/API/DB contracts unless explicitly approved.
  - Preserve existing business logic and data flow.
  - Prefer small, reviewable, production-grade changes.
  - Reuse existing components, services, toast utilities, table helpers, and styling conventions.
  - Do not add new dependencies without approval.
  - No hardcoded secrets.
  - No destructive DB changes.
  - Use enterprise-grade error handling, validation, logging, and regression-safe implementation.
- Authentication rule:
  - Authentication must be centralized.
  - Once a user is authenticated successfully, all protected pages must use the same global auth session/token.
  - Do not implement page-by-page authentication prompts.
  - Do not duplicate auth checks in every page.
  - Use `AuthProvider`/`AuthContext` + `ProtectedRoute` or the existing central auth mechanism.
  - Auth state must survive route navigation and browser refresh while the session/token is valid.
  - The API client must consistently attach the token/header or include credentials based on the existing auth design.

## Phase 1 Workspace Guardrails
- `/app/phase-1` is an isolated, protected, read-only React workspace owned by `frontend/src/data/phaseOneNav.ts`, `frontend/src/pages/phase-one/PhaseOneWorkspacePage.tsx`, and `frontend/src/services/api/phaseOneApi.ts`; keep it additive and do not replace established detailed workflows.
- Preserve the single non-dropdown `Phase 1` header entry in `frontend/src/components/navigation/CvingLegacyHeader.tsx`; add or change Phase 1 pages by updating nav data, route handling in `frontend/src/App.tsx`, and source request mapping together.
- Phase 1 must compose existing GET services through `legacyApiGet`/`chartApiGet`, reuse centralized auth, normalize symbol input through `normalizeDisplaySymbol`, and tolerate partial-source failures without changing backend/API/Oracle contracts.
- Do not add Phase 1-only backend endpoints, database tables, calculations, market-data writes, or a second login flow unless explicitly approved.
- After Phase 1 workspace changes, run `cd frontend; npm.cmd run test -- tests\phaseOneWorkspace.test.tsx`, `npm.cmd run typecheck`, and `npm.cmd run build`.

## Trade SetUp Watchlist Guardrails
- `/app/tradesetup` is the React Watchlist surface owned by `frontend/src/pages/watchlist/WatchlistPage.tsx`, `frontend/src/services/api/watchlistData.ts`, `frontend/src/App.tsx`, and `frontend/src/components/navigation/CvingLegacyHeader.tsx`; do not create a duplicate `/app/watchlist` route or `/api/watchlist` endpoint.
- Keep the top navigation label as `Watchlist` with the dropdown item `Trade SetUp`, and preserve the symbol-control order covered by tests: Main NSE symbols, `+`, My Watchlist symbols, Setup state, Reset filter.
- Reuse existing data sources through `fetchBars`, `fetchSymbols`, technical APIs, Sector Wise, S&R, Delivery, and `normalizeDisplaySymbol`; exact row matching must continue to accept `symbol`, `stock`, `ticker`, and `code` aliases.
- Saved symbols live in browser storage under `ct_watchlist_strategy_symbols_v1`; the row snapshot `ct_watchlist_strategy_rows_snapshot_v1` should restore only active saved symbols immediately, then refresh the selected saved symbol in the background. Do not fan out all saved symbols on route entry.
- `fetchWatchlistDataRow(..., { returnAfterInitial: true })` should keep first paint inside the existing initial render budget while optional sources hydrate progressively. Treat source failures as per-source status, not as a reason to blank the row when bars/metadata are available.
- Overview tab presentation may hide columns such as FFMC and LTP through the existing tabbed table CSS, but preserve the `WatchlistDataRow` contract unless the user explicitly approves a contract change.
- After Trade SetUp Watchlist changes, run `cd frontend; npm.cmd run test -- tests\watchlistPage.test.tsx tests\watchlistData.test.ts`, then `npm.cmd run typecheck`; add `npm.cmd run build` when route, styling, or production bundle behavior changes.

## FYERS Holdings P&L Guardrails
- The `/app/fyers/holdings` UI is React + TypeScript; do not add legacy HTML, jQuery, or old standalone JavaScript for this module.
- Preserve the Oracle-backed CSV import flow and existing holdings API response keys; add reconciliation/debug fields only as backward-compatible additions.
- Total holding P&L must use quantity, average buy price, and LTP/current price. Today's/day P&L must use quantity, LTP/current price, and previous close.
- Do not mix total P&L with day P&L. If previous close is missing, day P&L should remain neutral rather than using an unrelated fallback.
- Use the safe reconciliation endpoint or service helpers before changing formulas, price-source mapping, or symbol normalization.

## FYERS Automation Polling Guardrails
- In `frontend/src/api/client.ts`, `timeoutMs: null` or `timeoutMs: 0` disables only the synthetic client timeout; caller-provided abort signals must continue to work.
- FYERS automation start/status/stop/resume/rerun operations and failed-symbol list/rerun operations intentionally use no synthetic timeout. Do not restore a generic timeout for these long-running operations without explicit approval.
- Preserve the current bounded timeout budgets for Holdings, NIFTY500 Sync, and failed-symbol deletion unless the exact flow is being changed.
- Transient polling failures must preserve the active job ID, last known job snapshot, cards, logs, telemetry, and Stop action. Clear a stale job only for an explicit `404` with `FYERS_JOB_NOT_FOUND`.

## FYERS Merge and Log Guardrails
- `backend/services/marketdata_service.py` owns FYERS direct-upsert accounting for `STOCK_EOD_HISTORY`; preserve duplicate-safe Oracle `MERGE` behavior and report inserted, updated, and skipped rows from scoped OHLCV evidence.
- Browser-visible FYERS job logs should keep Processing, ETA, and insert/update summaries, but backend diagnostics such as `[FYERS_SYMBOL_RESOLVE]` and `[SINGLE_STOCK_SYNC]` stay in backend logs unless the user explicitly asks to expose them.
- After FYERS merge-count or job-log changes, run focused checks first: `python -m pytest backend\tests\test_marketdata_fyers_proxy.py backend\tests\test_marketdata_fyers_job_progress.py -q` and add `python -m pytest backend\tests\test_marketdata_stock_history_sync.py -q` when `STOCK_EOD_HISTORY` merge behavior is touched.

## NIFTY500 Sync Guardrails
- `/app/fyers/nifty500-sync` owns Existing FYERS CSV load, compare, merge, add, update, and delete through `frontend/src/pages/fyers/Nifty500SyncPage.tsx`, `frontend/src/services/api/fyersApi.ts`, `backend/routes/marketdata.py`, and `backend/services/nifty500_sync_service.py`.
- Preserve the NIFTY500 sync API paths under `/api/marketdata/fyers/nifty500-sync`; keep direct snapshots and `{ data: snapshot }` / `{ payload: snapshot }` / `{ result: snapshot }` envelopes normalized before reading `existing`, `new`, or `summary`.
- CSV mutations must stay behind the locked, normalized, atomic writer in `backend/services/nifty500_sync_service.py`; reject duplicate update targets and keep delete idempotent when a stale UI row is already absent.
- After NIFTY500 Sync changes, run focused checks first: `python -m pytest backend\tests\test_marketdata_nifty500_sync.py -q`, `cd frontend; npm.cmd run test -- tests\nifty500SyncErrorHandling.test.ts`, and `cd frontend; npm.cmd run typecheck`.

## EMA Trend and Export Guardrails
- `/app/technical/ema` uses the existing trend snapshot for table rendering; do not make old snapshots invalid by requiring additive fields such as `allRows`.
- T_D-only download data belongs on the lightweight `GET /api/trend/trading-days` path, independent of normal EMA table snapshots and refresh recomputation.
- EMA T_D TXT/CSV exports must filter only on positive `T_D` below the selected tenure threshold, not on EMA>20 or another visible EMA table condition; no checkbox selection should export no rows.
- Preserve the current export contract unless explicitly changed: TXT is comma-separated symbols only, and CSV is `s.no,symbol,t_d`.
- After EMA trend/export changes, run focused checks first: `python -m pytest backend\tests\test_trend_route_marketcap.py -q`, `cd frontend; npm.cmd run test -- tests\emaDownload.test.ts`, `cd frontend; npm.cmd run typecheck`, and `cd frontend; npm.cmd run build`.

## Background Job Startup Guardrails
- Flask startup owns optional schedulers through `backend/app.py::create_app`; use `enable_background_jobs=False`, `enable_warmup=False`, and explicit scheduler flags in tests or probes that must not start daemon loops.
- `CVING_ENABLE_BACKGROUND_JOBS` gates the broad startup jobs, while `CVING_ENABLE_MANUAL_SR_IMAGE_AUTO_INGEST` can enable only the manual SR image inbox scheduler for `batch/manual_sr_image_queue/01_inbox`.
- `CVING_ENABLE_MARKETDATA_AUTO_MERGE` gates the startup market-data auto-merge job; the Windows launcher defaults it to `1`.
- The Windows launcher `start_flask_cvingtrade25x.bat` defaults background jobs, market-data auto-merge, and manual SR image auto-ingest to `1`, but defaults warmup to `0`; preserve those runtime defaults unless the task is explicitly about startup behavior.
- `CVING_ENABLE_NSE_MARKETDATA_AUTOMATION` controls the long-running NSE market-data scheduler; when unset it follows `CVING_ENABLE_BACKGROUND_JOBS`, so do not silently enable it during local validation.
- For Windows Task Scheduler automation, use the checked-in wrappers instead of ad hoc scheduled commands: `scripts\register_nse_marketdata_automation_task.ps1` -> `scripts\run_nse_marketdata_automation.ps1` for NSE market-data polling, and `scripts\register_manual_sr_image_inbox_task.ps1` -> `scripts\run_manual_sr_image_inbox_automation.ps1` for the 8-hour manual SR image inbox runner.
- After startup or scheduler changes, run focused checks first: `python -m pytest backend\tests\test_app_startup.py backend\tests\test_manual_sr_image_auto_ingest.py backend\tests\test_nse_market_data_scheduler.py -q`.

## Instruction Priority
If instructions conflict, follow this order:
1. Explicit user instruction
2. This `AGENTS.md`
3. Repo-local documentation nearest the code being changed
4. Existing project conventions

## Default Operating Mode
- Work like a senior production engineer on a trading system.
- Preserve correctness, auditability, and existing business behavior unless the task explicitly changes it.
- Keep diffs minimal, safe, and reversible.
- Do not redesign architecture, rename contracts, or add dependencies without a strong reason.
- Read related files first, understand the current flow, then make the narrowest safe change.

## Standard Implementation Workflow
1. Trace the current behavior through the owning UI/page, shared API client, Flask route, backend service, and Oracle or automation layer.
2. Identify and document the root cause before editing.
3. Plan the smallest backward-compatible change and its rollback.
4. Back up existing files, implement only the scoped fix, and avoid unrelated formatting churn.
5. Run targeted checks first, then the broader validation appropriate to the changed layers.
6. Report the root cause, files changed, implementation summary, commands run, validation result, risks, and rollback.

## Required Task Handoff
- Root cause.
- Files changed.
- Implementation summary.
- Commands run.
- Validation result.
- Risks and rollback.

## Assigned Agent Ownership
- `UI/Page Agent`: Owns `frontend/src/pages`, `frontend/src/components`, `frontend/src/hooks`, `frontend/src/services`, `frontend/src/types`, React rendering, Tailwind styling, shadcn/ui composition, responsive behavior, page-level interactions, and visual regressions. Legacy `html/`, `css/`, and `assets/` UI surfaces are maintenance-only unless explicitly requested.
- `Backend/API Agent`: Owns `backend/routes/`, request validation, orchestration, response contracts, and service integration behavior.
- `Oracle/Data Agent`: Owns Oracle queries, DDL/DML scripts, loaders, bulk merge/upsert behavior, indexes, and rollback-aware DB changes.
- `Strategy/Analytics Agent`: Owns screening rules, backtesting, signal generation, ranking, scoring, indicator math, and date/candle alignment.
- `Automation/Observability Agent`: Owns schedulers, background jobs, retries, logging, notifications, cache warmers, and run safety.
- For multi-area changes, keep responsibilities separated and avoid mixing UI, DB, and strategy logic in one layer when the repo already has a better owner.

## Trading and Backtesting Guardrails
- Never introduce lookahead bias or future-data leakage.
- Preserve deterministic entry/exit logic, candle ordering, and timezone/session alignment.
- Do not silently change formulas, thresholds, ranking rules, scoring models, or filters.
- Preserve handling for costs, slippage, fees, and spread if the current flow already models them.
- Do not present hypothetical outputs as guaranteed outcomes.

## Oracle and Data Safety
- Treat Oracle as the likely system of record unless the repo proves otherwise.
- For approved Oracle changes that use the repository-level DB workflow, keep forward, rollback, and validation scripts paired under `database/migrations`, `database/rollback`, and `database/validation`; include purpose, compatibility, data/performance impact, paired script paths, and post-change validation.
- Do not drop, truncate, rename, or broadly reshape schema objects without explicit approval.
- Use parameterized queries or safe binding patterns.
- Be careful with large-table updates, bulk merges, commit behavior, and rollback impact.
- Never hardcode DB credentials or leak them in code, docs, logs, or screenshots.

## Architecture Expectations
- Keep UI concerns in UI files, domain logic in services, and DB access in data-oriented modules.
- Keep handlers/controllers thin and validation at the boundary.
- Keep data contracts explicit and backward compatible where practical.
- Avoid hidden global state, unsafe shortcuts, and speculative refactors during bug fixes.

## Discovery Before Editing
- Inspect repo-defined commands and source-of-truth files first, including `README*`, `package.json`, `requirements*.txt`, `pyproject.toml`, SQL scripts, migration folders, startup scripts, and CI workflows.
- Identify which pages, endpoints, jobs, tables, or reports depend on the behavior before editing.
- Prefer existing project patterns over invented ones.

## Verification Expectations
- For every meaningful change, consider happy path, edge cases, invalid input, failure handling, regression risk, and data integrity risk.
- Be extra careful with strategy rules, Oracle persistence, ingestion jobs, auth, and UI flows tied to DB writes.
- If checks cannot be run, state what was not run, why, and what a human should run next.

## Logging, Auditability, and Performance
- Add useful contextual logs for critical workflows without logging secrets.
- Preserve traceability for data loads, strategy jobs, API failures, and persistence actions.
- Avoid repeated parsing, redundant API calls, N+1 query patterns, and unnecessary large in-memory loads.
- Prefer batching/chunking for heavy Oracle operations and state any scale risk when relevant.

## Human Review Triggers
- Require extra caution or human review for strategy formula changes, position sizing, P&L logic, live execution routing, destructive schema changes, bulk data updates, auth/authorization changes, and customer-visible financial reporting.

## Prohibited Actions
- Do not bypass tests silently.
- Do not fabricate backtest or performance results.
- Do not weaken risk controls, auth, or validation.
- Do not auto-enable live trading behavior.
- Do not replace Oracle-safe flows with unsafe shortcuts.
- Do not make broad refactors during a narrow bug fix without clear need.

## Project Structure & Module Organization
- `frontend/src/`: Source of truth for current UI development using React + TypeScript.
- `frontend/src/pages/`: Route-level React pages.
- `frontend/src/components/`: Reusable React and shadcn/ui-aligned components.
- `frontend/src/hooks/`, `frontend/src/services/`, `frontend/src/types/`, `frontend/src/utils/`: Shared state, API, contract, and utility layers for the React app.
- `frontend/src/styles/` or existing Tailwind entrypoints: Tailwind-first styling. Avoid new standalone CSS unless required by an existing component pattern.
- `backend/`: Existing Python backend. Preserve the current route/service/repository/database organization.
- Retired legacy UI/static surfaces: physical legacy `html/`, root `css/`, and legacy JavaScript/CSS under `assets/` have been removed after React migration. Do not recreate old HTML pages, standalone JavaScript bundles, or legacy CSS paths for new work.
- `tests/` and `frontend/tests/`: Focused backend, frontend, contract, and regression tests where applicable.
- Flask serves the built React SPA from `frontend/dist`, with hashed assets under `/react-assets/`; Vite keeps prior assets during builds via `emptyOutDir: false`. If a React source change is not visible in the Flask-served app, verify the built `frontend/dist/index.html` and served asset before rewriting page logic.

## Build, Test, and Development Commands
- Direct backend foreground server:
  ```powershell
  cd C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X
  python backend\app.py
  ```
  Use the Windows launcher flow when validating hidden startup, locks, logs, stale-listener recovery, or health-check readiness.
- Windows launcher and health verification:
  ```powershell
  cd C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X
  cmd.exe /d /c "call start_flask_cvingtrade25x.bat --hidden"
  Invoke-WebRequest http://127.0.0.1:5055/api/health -UseBasicParsing
  cmd.exe /d /c "call stop_cvingtrade25x.bat"
  ```
  Manual double-click runs reopen in a visible interactive shell; use `--hidden` only for explicit background/startup execution. The launcher health check, not process creation alone, is the readiness gate.
- Frontend dev server:
  ```powershell
  cd C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X\frontend
  npm.cmd run dev
  ```
  Vite defaults to strict port `5174`; use `VITE_DEV_SERVER_PORT` only when intentionally selecting a different strict dev port. `/api` and `/legacy-api` proxy to `VITE_LEGACY_PROXY_TARGET` defaulting to `http://127.0.0.1:5055`, and `/chart-api` proxies to `VITE_CHART_PROXY_TARGET` with the same default.
- Frontend validation:
  ```powershell
  cd C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X\frontend
  npm.cmd run typecheck
  npm.cmd run test
  npm.cmd run build
  ```
  React migration aggregate validation is available as `npm.cmd run validate:migration`, which runs typecheck, build, and tests in the repository-defined order.
- Backend validation:
  ```powershell
  cd C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X
  python -m compileall backend
  python -m pytest backend\tests
  python -m pytest tests\backend\test_start_flask_launcher.py -q
  ```
  `backend\tests` is the main backend suite. The root `tests\backend` folder currently contains focused launcher regression coverage.
- Strategy auth smoke check, when protected strategy route/API auth regressions are suspected:
  ```powershell
  cd C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X
  $env:CVING_SMOKE_IDENTIFIER = '<client-id-or-email-or-mobile>'
  $env:CVING_SMOKE_PASSWORD = '<password>'
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke_strategy_auth.ps1 -BaseUrl http://127.0.0.1:5055
  ```
  Use `CVING_SESSION_TOKEN` instead of credentials when a valid session token is already available. Do not hardcode smoke credentials.
- Non-UI NSE ingestion runner:
  ```powershell
  cd C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X\backend
  python .\run_nse_pipeline.py --dataset all
  python .\run_nse_pipeline.py --dataset market-cap --trade-date YYYY-MM-DD
  python .\run_nse_pipeline.py --dataset ffmc --trade-date YYYY-MM-DD
  python .\run_nse_pipeline.py --dataset delivery --trade-date YYYY-MM-DD
  ```
  Use this runner for the existing NSE Market Cap, FFMC, and Delivery pipelines instead of duplicating those service flows.
- Enterprise/governance validation:
  ```powershell
  cd C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X
  python scripts\scan_api_duplicates.py
  python scripts\enterprise_validate.py
  ```
  `scripts\enterprise_validate.py` wraps the duplicate API scan plus optional backend coverage, Ruff, Bandit, and pip-audit checks when those tools are installed.
- Coverage and security checks for release-sensitive backend changes:
  ```powershell
  cd C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X
  python -m pytest backend\tests --cov=backend --cov-report=term-missing
  ruff check backend scripts
  python -m bandit -q -r backend scripts
  pip-audit
  ```
- Legacy HTML local checks are retired. Use the React build and Flask single-port routes for local UI validation.

## Coding Style & Naming Conventions
- Indentation: 2 spaces; no tabs.
- React/TypeScript: Use functional components, explicit prop/API types, reusable hooks/services, and existing app routing/layout patterns.
- Tailwind CSS: Prefer utility classes and existing design tokens. Keep class composition readable and responsive.
- shadcn/ui: Reuse or extend existing shadcn-style components for controls, dialogs, tables, forms, and common UI primitives where suitable.
- shadcn boundary: Introduce shadcn-style primitives only behind `frontend/src/components/ui/shadcn-wrappers/`; consume them through the existing public UI wrappers where available. Keep complex tables, KPI grids, chart surfaces, and sticky-column layouts custom until parity is proven.
- TypeScript: Keep strict mode enabled, preserve wire DTO field names, and normalize backend data in typed adapters instead of weakening types or spreading `any`.
- API clients: Keep frontend API access in existing service/client layers. Preserve request/response contracts and add backward-compatible fields only.
- Legacy HTML/CSS/JavaScript: retired from the active file tree. If historical behavior must be recovered, use repository history or `runtime/backups`, then re-implement the behavior in React + TypeScript + Tailwind CSS.

### Retired Legacy Static Surfaces
Legacy HTML/CSS/JavaScript files have been removed from the active tree. Keep historical behavior as implementation reference only when recovered from repository history or backups, then rebuild it in React.

## Testing Guidelines
- Frontend automated checks: run `npm.cmd run typecheck`, `npm.cmd run test`, and `npm.cmd run build` from `frontend/` for meaningful React changes.
- React migration/parity checks may use `npm.cmd run validate:migration`, which runs typecheck, build, and tests in the repository-defined order.
- Backend checks: run targeted pytest or `python -m compileall backend` for backend-only changes.
- Manual QA: Validate the affected React route in latest Chrome/Edge/Firefox; inspect both Console and Network for critical errors, unexpected duplicate requests, incorrect endpoint/status behavior, and contract drift.
- Responsiveness: Check the affected React view at ~320px, 768px, 1024px, and 1440px widths.
- Accessibility: Prefer keyboard-only nav; run Lighthouse/DevTools Accessibility checks where UI risk is meaningful.
- Retired legacy static checks: `/html/*`, `/assets/*`, and `/css/*` should return 404. Validate active UI through React routes under `/app/...`.

## Commit & Pull Request Guidelines
- Messages: Imperative and scoped. Examples:
  - `feat(frontend): add holdings reconciliation panel`
  - `fix(frontend): correct strategy toolbar spacing`
  - `fix(backend): preserve symbol update compatibility`
  - `docs: clarify local server instructions`
- PRs: Include a concise description, before/after screenshots for visual changes, steps to validate locally, and any linked issues. Keep PRs focused and small.

## Security & Configuration Tips
- Do not embed secrets or tokens. Prefer local assets over remote CDNs; if using external scripts/styles, include integrity and `crossorigin` attributes.
- Attribute licenses for third-party images/fonts in the relevant docs or frontend source folder if introduced.

## Agent-Specific Instructions
- Keep edits minimal and incremental; preserve existing behavior.
- Do not create new plain HTML pages, standalone JavaScript modules, jQuery flows, or legacy CSS feature paths.
- If a retired legacy behavior is needed, rebuild it in the approved React stack instead of restoring old static files.
- Prefer progressive enhancement in React; add TODOs sparingly and open issues for larger follow-ups.

## Immutable Market Data Flow
This project has a fixed market-data pipeline. Future agents must not change this flow without explicit user approval.

Flow:

```text
React FYERS automation route
  -> Fetch Fyers API data
  -> Insert into STOCK_EOD_HISTORY via existing backend/database flow
  -> Auto Merge or Manual Merge into NSE_NIFTY500_DAILY_RAW_DATA_DEV
  -> React UI pages load UI data from NSE_NIFTY500_DAILY_RAW_DATA_DEV or approved views on top of it
```

Mandatory architecture rules:
- Never bypass `STOCK_EOD_HISTORY`.
- Never insert Fyers API data directly into `NSE_NIFTY500_DAILY_RAW_DATA_DEV` from the FYERS automation UI unless explicitly approved by the user.
- Never make UI pages depend directly on live Fyers API response for persistent technical-analysis data unless explicitly approved.
- New React pages must use existing backend APIs/services backed by `STOCK_EOD_HISTORY`, `NSE_NIFTY500_DAILY_RAW_DATA_DEV`, or approved Oracle views/snapshots. Do not replace this with direct browser-to-Fyers or direct browser-to-Oracle flows.
- Never change merge direction.
- Never rename `STOCK_EOD_HISTORY` or `NSE_NIFTY500_DAILY_RAW_DATA_DEV` without explicit approval.
- Never change this data-flow architecture silently.

Immutable pipeline to preserve:

```text
React FYERS automation route
  -> fetch Fyers API
  -> insert into STOCK_EOD_HISTORY
  -> Auto Merge / Manual Merge
  -> NSE_NIFTY500_DAILY_RAW_DATA_DEV
  -> UI data loads through React pages
```

## Stock History Sync Guardrails
- For `/app/database/stock-history` and stock-history merge/status work, preserve reconciliation on normalized `UPPER(TRIM(SYMBOL)) + TRUNC(TRADING_DATE/TRADE_DATE)` keys across `STOCK_EOD_HISTORY`, `NSE_NIFTY500_DAILY_RAW_DATA_DEV`, and `NSE_NIFTY500_DAILY_RAW_DATA_ORACLE`. Do not validate parity with raw symbol casing, whitespace, or timestamp-bearing dates.
- Keep Oracle `MERGE` updates away from columns used in the `ON` clause, especially `SYMBOL` and trading-date keys.
- Stock-history KPI cards must unwrap nested `data` payloads, honor stock-history-specific stats keys such as `stock_eod_stock_count`, and fall back to Trading Day Coverage rows only when stats are missing or stale.
- After stock-history merge or KPI changes, run targeted checks first: `python -m pytest backend\tests\test_marketdata_stock_history_sync.py -q` for backend merge work, and `cd frontend; npm.cmd run test -- tests\stockHistoryPage.test.ts` plus `npm.cmd run typecheck` for React page work.

## NIFTY500 Historical Symbol Maintenance Guardrails
- For duplicate historical symbol variants in `NSE_NIFTY500_DAILY_RAW_DATA_DEV` and `NSE_NIFTY500_DAILY_RAW_DATA_ORACLE`, use `backend/scripts/consolidate_historical_symbol_variants.py` instead of ad hoc DML. The default run is read-only preview; `--apply` exports affected rows and a manifest under `runtime/backups`.
- Preserve unique history by `SYMBOL + TRUNC(TRADING_DATE)`: delete only overlapping alternate-series rows, rename non-overlap rows to the current canonical symbol, mutate DEV and ORACLE together in one transaction, and rollback from the exported CSVs if needed.

## Symbol Display Normalization Guardrails
- For React display/search/adapters, reuse `frontend/src/utils/symbols.ts::normalizeDisplaySymbol` instead of creating per-page cleanup logic; it strips `NSE:`/`BSE:` prefixes and cash-series suffixes `EQ`, `BE`, `SM`, `ST`, and `BZ` while preserving valid embedded hyphens such as `BAJAJ-AUTO`.
- Do not fix display-only symbol prefix/suffix issues by changing the FYERS -> `STOCK_EOD_HISTORY` -> DEV flow, mutating historical candles, or using ad hoc Oracle DML; preview collision groups first and require an explicit rule before merging or deleting history.

## NSE FFMC/MCAP Quote Session Guardrails
- `backend/services/nse_mcap_service.py` coordinates NSE cookie snapshots and warmup state across concurrent quote clients used by the shared FFMC/MCAP path.
- Preserve the shared lock, in-flight warmup gate, cookie snapshot, and warm-session TTL. Do not revert to independent per-worker warmups, which amplify NSE `401/403` retries.
- Successful quote responses should continue publishing the shared session. A `401/403` should trigger one coordinated forced warmup that waiting workers can reuse.
- After changing this path, run `python -m pytest backend\tests\test_nse_mcap_service.py -q`.

## Sector Onboarding Rules
- **Independent Mappings**: When onboarding multiple sectors that are logically distinct (e.g. "Restaurants", "Hospitality Hotels & Resorts", "Tourism & Travel"), do NOT lump them into a single combined staging table or a single sector code unless explicitly requested. The UI relies on distinct Sector Codes to enumerate the total sector count.
- Each distinct sector must have its own staging table (e.g. `NSE_NIFTY_RESTAURANTS_STAGING`), its own canonical sync registration, its own entry in `NSE_SECTOR_MASTER`, and independent python alias mapping.
- Preserve unique sector selector behavior: backend sector aliases collapse to one canonical UI sector/page. Update `backend/routes/sector_rotation.py` and `frontend/src/data/sectorNav.ts` together when adding aliases or source-pack sectors.
- For source-pack sector expansion, use the existing SQL and loader pattern: create/validate/rollback scripts under `backend/sql/` plus `backend/scripts/load_source_pack_sector_file.py`. Validate with `python -m pytest backend\tests\test_sector_source_pack_expansion_mapping.py backend\tests\test_sector_rotation_route.py -q`, and run focused frontend sector tests when navigation changes.
- Keep `/app/sector/overview` backed by `GET /api/sectors/overview`; do not duplicate overview aggregation in React when backend sector discovery and sector-wise payloads already provide the metrics.

## Sector Overview Guardrails
- `/app/sector/overview` normal reads must stay snapshot-first: `GET /api/sectors/overview` should return the compact persisted overview payload before Oracle latest-date or live table-count lookups, and the frontend normal-read timeout is intentionally 5 seconds.
- After the fast Sector Overview response renders, the React page may check `GET /api/database/sync-status`; trigger the existing `refresh=1` path only when `dev_ltc_date` is newer than the overview payload's `source_dev_ltc_date`, and keep the persisted overview usable if sync-status fails.
- Explicit toolbar Refresh (`GET /api/sectors/overview?refresh=1`) may refresh live sources, but must use metadata-only sector discovery and optional warmed `_sector_wise_trend_cache`; do not force `_load_sector_wise_trend_map()` rebuilds or per-staging-table `COUNT(DISTINCT symbol)` loops in the request path.
- Keep Sector Overview trend cards on the explicit buckets, normalize backend `Sideway` counts to the UI `Sideways` card, and do not reintroduce separate `Insufficient` or `Consolidation` KPI cards unless the API contract is intentionally changed.
- Preserve `ltc_date_scope: LATEST_PER_SYMBOL`, `dd-mm-yyyy` `LTC_DATE`, the one-line `LTC_DATE` KPI value, and the five-card desktop KPI grid unless the request explicitly changes presentation.
- After Sector Overview backend/UI changes, run `python -m pytest backend\tests\test_sector_rotation_route.py -q`; add `cd frontend; npm.cmd run test -- tests\sectorOverviewPage.test.ts`, `npm.cmd run typecheck`, and `npm.cmd run build` when React or CSS changes are touched.

## Sector Symbol Normalization Guardrails
- Sector Overview and Sector Wise Stocks must preserve NSE cash-series awareness for `EQ`, `BE`, `SM`, `ST`, and `BZ`; normalize for lookup while continuing to display one canonical base symbol.
- Do not rewrite historical candles, force a symbol into a different series, or alter the FYERS -> `STOCK_EOD_HISTORY` -> DEV flow to fix a sector display lookup unless explicitly approved.
- For sector-membership-only symbol renames (for example `TTKHEALTH` -> `TTKHLTCARE` in Diversified), update the owning staging table and `NSE_SECTOR_WISE_STOCKS_SNAPSHOT` payload together; do not rewrite market-history rows when canonical history already exists, and clear Sector Rotation caches or restart Flask afterward.
- Sector Overview should honor the existing `LATEST_PER_SYMBOL` behavior: symbols absent on the global maximum DEV date can use their own latest canonical/suffix-aware DEV candle before trend resolution.
- After sector symbol normalization or latest-per-symbol changes, run focused coverage first: `python -m pytest backend\tests\test_sector_rotation_route.py -q` plus frontend sector tests only when navigation or display bindings change.

## Sector Page Workflow Guardrails
- Current React Sector navigation is unversioned: `/app/sector/rotation`, `/app/sector/stockedge-rotation`, `/app/sector/overview`, and `/app/sector/stocks/auto`. Do not reintroduce V-labeled dropdown entries or `/app/sector/rotationv3` / `/app/sector/stocksv3` routes unless explicitly requested.
- `/app/sector/rotation` reads `GET /api/sectors/breadth?version=v3` but preserves the established all-sector breadth table; `/app/sector/stockedge-rotation` is the separate enhanced V3/StockEdge view with All Sectors as default and Best Sectors as a gated filter.
- Backend V1/V2 branches remain backward-compatible. `POST /api/sectors/refresh?version=v3` forces sector reference sync, publishes V3 breadth and stock snapshots, and must preserve prior cache/snapshot state on failure.
- Do not deploy or roll back V3 Oracle objects from `backend/sql/create_sector_rotation_v3_schema.sql`, `backend/sql/validate_sector_rotation_v3_schema.sql`, or `backend/sql/rollback_sector_rotation_v3_schema.sql` without explicit Oracle approval. After an approved schema install, the offline V3 refresh entrypoint is `python backend\scripts\refresh_sector_rotation_v3.py`.
- For V3 route/service/StockEdge changes, run focused coverage first: `python -m pytest backend\tests\test_sector_rotation_v3_service.py backend\tests\test_sector_rotation_v3_repository.py backend\tests\test_sector_rotation_v3_refresh_service.py backend\tests\test_sector_rotation_v3_stock_service.py backend\tests\test_sector_rotation_v3_schema_contract.py backend\tests\test_sector_rotation_v3_backtest.py backend\tests\test_marketdata_sector_rotation_v3_refresh.py backend\tests\test_sector_rotation_route.py -q`, plus `cd frontend; npm.cmd run test -- tests\sectorRotationPage.test.ts tests\sectorWiseStocksPage.test.tsx tests\sectorHeader.test.tsx` and `npm.cmd run typecheck` when frontend routing/navigation changes.
- V3/StockEdge money-flow and rank fields must stay source-backed: preserve source `rankChange5` as the published `rankChange1W`, and keep `volumeRatio20`, `deliveryParticipationScore`, `obvSlopeScore`, `accumulationScore`, `upDownVolumeScore`, and `breadthVolumeScore` wired into the V3 money-flow scorer when source data is present.
- `StrategyToolbar` is the single owner of visible sync/live status and Refresh controls for Sector Overview, Sector Rotation, and Sector Wise Stocks. Do not add duplicate page-header sync badges or Refresh controls outside it.
- Toolbar `Live`/error status reflects page/API reachability; stale database sync or stale snapshot evidence belongs in compact sync badges/messages and payload metadata.
- For Sector Wise Stocks performance work, preserve the existing memory/local snapshot/stale snapshot path before heavier Oracle resolver/query paths when the route supports it. Do not publish partial snapshots, wrong-sector rows, or current-date/current-price rows missing 52-week high/low values.
- If `GET /api/sector/<sector>/stocks/sector-wise?version=v3` returns `V3_SECTOR_NOT_FOUND` or another unavailable V3 stock snapshot for a sector omitted from a partial publication, keep the shared page usable by falling back to its established V1 local snapshot/data path and logging `[SECTOR_WISE_V3_FALLBACK]`.
- V3 stock-strength rows must keep one classifier by exposing V3 `trendState` through the legacy `trend` contract; do not let rendered trend, EMA flags, score, and confidence disagree across separate classifiers.
- Canonical Sector Wise Stocks keeps the single sector selector, search-only row filtering, `STOCK` ascending default sort, `Existing Sector Wise Stocks` tab label, and established visible columns through `TREND`/`SCORE` plus populated legacy analytics. Do not default-filter legacy rows by missing V3 `trendState` or add V3 Stock Strength columns on this page unless explicitly requested.
- Do not show Sector Wise Stocks analytics columns with no populated producer data. Render additive analytics fields only when the backend/adapters provide real values; do not fill blank analytics columns with placeholder formulas.
- Sector Wise Stocks metadata must stay source-backed: `INDEX`/`MCAP`/`MCAP_RANK` enrichment belongs in `backend/services/nse_mcap_service.py` or existing route/service wrappers, and stale per-symbol market-cap fallback should be enabled only where the owning service explicitly requests it.
- Cached or published Sector Wise rows with a current price/date must include real `high52w` and `low52w` values; do not replace missing 52-week data with placeholders or formulas just to populate `52WH`/`52WL` columns.
- Sector Wise Stocks page-level TXT/CSV exports live beside the Sector Hierarchy tab controls and include only blank, `Unknown`, or `Insufficient` Trend rows. TXT is comma-separated symbols; CSV uses the currently displayed Sector Wise columns.
- The consolidated `Download TXT` on `/app/sector/rotation` and `/app/sector/stockedge-rotation` must call the single snapshot-backed `GET /api/sectors/sector-wise-unknown-symbols` endpoint and download `SectorWiseUnknownInsufficient.txt`; do not restore per-sector request fan-out or use Sector Overview as the source.

## Windows Developer Workflow
- Use Windows PowerShell commands by default and prefer `npm.cmd` over `npm` in this workspace.
- Clearly label commands that require Bash, WSL, or an elevated shell.
- Keep command output focused and avoid unrelated formatting or line-ending churn.
