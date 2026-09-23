# Enterprise Architecture Pattern

## Current Runtime

CvingTrade25X is an existing layered trading and market-data application. The active integrated runtime is:

```text
React + TypeScript UI
  -> frontend/src/api/client.ts
  -> Flask backend/app.py
  -> backend/routes feature blueprints
  -> backend/services business/data services
  -> Oracle 19c
```

Do not migrate the runtime to FastAPI unless explicitly approved. FastAPI charting modules can remain as existing code, but new integrated work must preserve the Flask route/service stack unless the user approves otherwise.

## Preserved Data Flow

```text
FYERS API or NSE files
  -> STOCK_EOD_HISTORY
  -> auto/manual merge
  -> NSE_NIFTY500_DAILY_RAW_DATA_DEV
  -> backend APIs
  -> React UI
```

No UI page should bypass backend APIs. No FYERS persistence flow should bypass `STOCK_EOD_HISTORY`. No Oracle table-flow change is allowed without explicit approval.

## FYERS Automation Job Pattern

```text
React FYERS automation page
  -> quick Flask start endpoint
  -> in-process FYERS background worker
  -> FYERS_EXTRACTION_RUNS / FYERS_EXTRACTION_SYMBOL_STATUS
  -> STOCK_EOD_HISTORY
  -> polled status and symbol outcomes
```

The browser request must not own the extraction lifetime. Start/status/stop/rerun routes remain thin, while `backend/services/marketdata_service.py` owns job orchestration and persistence. Oracle job state is additive and supports page refresh or Flask restart recovery; reruns continue to use existing symbol/trading-date idempotency checks.

NSE MCAP, FFMC, and Delivery automation are independent workflows. Do not merge their workers, endpoints, persistence, or controls with FYERS automation.

## Target Layering Pattern

Route:
- Own HTTP method, path, auth boundary, request parsing, and response shape.
- Keep handlers thin.
- Reuse existing request validators.

Service:
- Own business logic, orchestration, caching, computations, and workflow decisions.
- Keep SQL access delegated where a repository exists.
- Preserve existing response contracts.

Repository:
- Own Oracle SQL, bind variables, connection use, pagination, and persistence.
- New repository modules should inherit or follow `backend/repositories/base_repository.py`.

Schema:
- Own request and response validation when introduced.
- Keep backward-compatible response fields.

Core:
- Own reusable config, logging, response, error, and safe-logging helpers.
- Current helper files under `backend/core` are non-invasive forward standards.

Frontend:
- React pages own rendering and user interaction.
- API access must go through `frontend/src/api/client.ts`.
- Future endpoint constants should live in `frontend/src/api/endpoints.ts`.
- Preserve loading, empty, error, retry, and responsive states.

## No Duplicate API Rule

Before adding an endpoint:

```powershell
rg -n "route\(|@bp\.|@app\." backend\routes backend\app.py
rg -n "/api/" frontend\src\api frontend\src\services
python scripts\scan_api_duplicates.py
```

Then update `docs/api-catalog.md`. Prefer extending an existing endpoint with backward-compatible fields over creating a parallel endpoint.

## Observability Pattern

- Carry `X-Request-ID` from frontend to backend.
- Log route, method, status, duration, and request ID.
- Do not log secrets or raw auth material.
- Runtime status and reports belong under `runtime`.

## Validation Pattern

Required governance validation:

```powershell
python scripts\scan_api_duplicates.py
python scripts\enterprise_validate.py
```

Use targeted backend/frontend tests for code changes and update `CHANGELOG.md` with results.
