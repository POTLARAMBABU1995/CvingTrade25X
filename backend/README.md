# CvingTrade25X Backend (Flask + Oracle 19c)

This backend serves JSON to the frontend pages via simple HTTP endpoints and reads market data from Oracle 19c using the python-oracledb driver.

- App entry: `backend/app.py`
- Endpoints: `/api/health`, `/api/config`, `/api/trend`, `/api/trend/latestDate`, `/api/trend/ping`, `/api/trend/metrics`, `/api/momentum/macd`, `/api/sr-levels`
- Script: `backend/run.ps1` (creates venv, installs deps, starts app)

## Prerequisites
- Python 3.10+
- Network access from this machine to Oracle 19c
- Oracle DB credentials and connectivity details
- No Oracle Client is required (python-oracledb thin mode)

## Environment Variables
Configure these to point at your Oracle 19c instance. The `run.ps1` sets safe defaults, but you should override them for your environment.

- `ORACLE_USER`: DB username (e.g., `market_user`)
- `ORACLE_PASSWORD`: DB password
- `ORACLE_DSN`: Optional direct DSN override (e.g., `127.0.0.1:1521/cvingpdb.local`). When set, it takes precedence over host/port/SID/service-name variables.
- `ORACLE_HOST`: Host/IP of Oracle (e.g., `localhost` or `10.0.0.42`)
- `ORACLE_PORT`: Listener port (default `1521`)
- `ORACLE_SID`: SID (e.g., `ORCL`) Ã¢â‚¬â€ set this OR `ORACLE_SERVICE_NAME`
- `ORACLE_SERVICE_NAME`: Service name (e.g., `ORCLPDB1`) Ã¢â‚¬â€ alternative to SID
- `ORACLE_SCHEMA` (optional): Owner/schema containing the table (e.g., `MARKET`)
- `ORACLE_TABLE` (optional): Source table name (default `NSE_NIFTY500_DAILY_RAW_DATA_DEV`)
- `TREND_CACHE_TTL` (optional): Cache TTL seconds for trend payload (default `3600`).
- `TREND_LATEST_DATE_CACHE_TTL` (optional): Cache TTL seconds for `/api/trend/latestDate` (default `5`).
- `MOMENTUM_CACHE_TTL` (optional): Cache TTL seconds for MACD payload (default `3600`).
- `SR_CACHE_TTL` (optional): Cache TTL seconds for SR payload (default `600`).
- `SR_TRADING_DAYS_LOOKBACK` (optional): Rolling trading-day window used by `/api/sr-levels` from the latest `LTC_DATE` (default `504`, about 2 trading years).
- `YAMUNA_CSV_OUTPUT_DIR` (optional): CSV export directory for Yamuna ingestion (default `E:\YAMUNA automation`).
- Note: The backend loads full history from the DB, then `/api/sr-levels` evaluates the latest `504` trading-day window by default using the most recent `LTC_DATE`. Cached snapshots and background warmup keep first response under ~5s.

Connection DSN selection:
- If `ORACLE_SID` is set, DSN uses SID.
- Else DSN uses `ORACLE_SERVICE_NAME` (or `orcl` if none provided).

## Expected Table Shape
All endpoints query one table with at least these columns:
- `SYMBOL` (VARCHAR2)
- `TRADING_DATE` (DATE or TIMESTAMP)
- `LTP` (NUMBER) Ã¢â‚¬â€ last traded price used to compute EMAs

Adjust `ORACLE_SCHEMA` and `ORACLE_TABLE` if your table name differs.

## Run Locally (Windows PowerShell)
From the `backend/` directory:

1) Option A Ã¢â‚¬â€ with helper script
- `./run.ps1`
- Override env when needed (example):
  ```powershell
  $env:ORACLE_USER = 'market_user'
  $env:ORACLE_PASSWORD = 'secret'
  $env:ORACLE_HOST = '10.0.0.42'
  $env:ORACLE_SERVICE_NAME = 'ORCLPDB1'
  ./run.ps1
  ```

2) Option B Ã¢â‚¬â€ manual
- `python -m venv .venv; . .\.venv\Scripts\Activate.ps1`
- `pip install --upgrade pip`
- `pip install -r requirements.txt`
- Set env vars as above (PowerShell: `$env:NAME = 'value'`)
- `python app.py`

Server runs on `http://localhost:5055` by default.

- **Windows port exclusions**: Port **5055 is the canonical port for the entire project**. Some OEM images reserve ranges like `5041-5140`, which causes `WinError 10013` when you start Flask. To keep using 5055, release the exclusion (requires elevated prompt):
  - Inspect reservations: `netsh int ipv4 show excludedportrange protocol=tcp`
  - If you see 5055 in a reserved block, temporarily stop the owning service (often Hyper-V/ICS) and run `netsh int ipv4 delete excludedportrange protocol=tcp startport=5041 numberofports=100` (adjust start/length to match your range).
  - Restart the service if needed, then re-run `python app.py` Ã¢â‚¬â€ it should bind 5055.
  - As a fallback you can still override by exporting `PORT`, but remember the frontend and docs assume 5055.

## Verify Health
- Open `http://localhost:5055/api/health` Ã¢â‚¬â€ should show `{ ok:true, db:"up" }` when DB connects.
- Open `http://localhost:5055/api/config` Ã¢â‚¬â€ confirms effective DSN parameters (no secrets).

## Frontend Integration
The Trend Indicators page (`EMA.html`) auto-detects the backend at common ports and will call `/api/trend` to fill four EMA tables. You can also force the API base:

- Add query param: `EMA.html?api=http://localhost:5055`
- Or set once in browser: `localStorage.setItem('API_BASE','http://localhost:5055')`

If the backend is offline, the page falls back to `json/market.json`.

## Troubleshooting
- ORA-12541: TNS:no listener Ã¢â‚¬â€ Check `ORACLE_HOST`/`ORACLE_PORT`, and that the listener is running.
- ORA-12514/12505: service/SID not found Ã¢â‚¬â€ Use the correct `ORACLE_SERVICE_NAME` (e.g., `ORCLPDB1`) or set `ORACLE_SID`.
- Auth failures Ã¢â‚¬â€ Verify `ORACLE_USER`/`ORACLE_PASSWORD` and that the user can `SELECT` from the table.
- Wallet/TCPS Ã¢â‚¬â€ python-oracledb thin supports wallets; not configured here. If you use a wallet, extend `_build_dsn()` and set `oracledb.connect(config_dir=..., wallet_location=..., wallet_password=...)`.
- Cross-origin errors Ã¢â‚¬â€ Frontend is static. This Flask app has CORS enabled for dev via `flask-cors`.

## FYERS Proxy Handling
FYERS helper subprocesses support proxy policy controls so auth/batch calls do not inherit broken global proxy variables (for example `HTTP_PROXY=http://127.0.0.1:9`), which can cause:
- `ProxyError: Unable to connect to proxy`
- `WinError 10061`
- auth-code exchange failures against `api-t1.fyers.in`

Environment variables:
- `FYERS_PROXY_MODE` (default: `direct`)
  - `direct`: remove inherited proxy vars for FYERS subprocesses and set `NO_PROXY`/`no_proxy` to include `localhost,127.0.0.1,::1,api-t1.fyers.in,api.fyers.in`
  - `system`: keep inherited process/system proxy variables unchanged
  - `explicit`: ignore inherited proxy vars and use only `FYERS_*_PROXY` values below
- `FYERS_AUTH_RETRY_COUNT` (default: `2`) retries token-helper auth once when FYERS returns stale/invalid auth-code errors
- `FYERS_HTTP_PROXY` (optional, used in `explicit` mode)
- `FYERS_HTTPS_PROXY` (optional, used in `explicit` mode)
- `FYERS_ALL_PROXY` (optional, used in `explicit` mode)
- `FYERS_NO_PROXY` (optional, used in `explicit` mode)

Restart the Flask backend after changing any `FYERS_PROXY_*` environment variables.

## Registration API (local persistence)
- Endpoint: `POST /api/auth/register` (legacy alias `/auth/register`).
- Storage: Oracle 19c using the same `ORACLE_*` connection settings.
- Optional: `REGISTER_ORACLE_SCHEMA` to target a specific schema (defaults to the connected Oracle user).
- Tables are created automatically with unique constraints on `email`, `mobile_e164`, and `client_id`.
- Schema reference: `backend/sql/create_auth_tables_oracle.sql`.
- Passwords/MPINs accept raw values (hashed with PBKDF2) or pre-hashed `pbkdf2:` / `argon2:` / `scrypt:` / SHA-256 hex strings.
- Restart the Flask app after changing `REGISTER_ORACLE_SCHEMA` or any `ORACLE_*` settings.

## Login API (local persistence)
- Endpoint: `POST /api/auth/login` with `{ identifier, password }` or `{ identifier, mpin }`.
- Successful logins update `updated_at` and append to `login_activity`.
- Login responses include a session token (bearer) and expiry; session TTL defaults to 30 minutes (override with `SESSION_TTL_MINUTES`, minimum 15 minutes).
- Use `GET /api/auth/session` with `Authorization: Bearer <token>` to validate/refresh a session.
- Use `POST /api/auth/logout` with `Authorization: Bearer <token>` to end a session.
- Optional: `POST /api/auth/activity` to record a login event directly.
- Schema reference: `backend/sql/create_auth_tables_oracle.sql`.

## Reset API (local persistence)
- Endpoint: `POST /api/auth/reset` with `{ identifier, dob|pan|aadhaar_last4 }`.
- Provide any one of DOB, PAN, or Aadhaar last 4 digits to validate.
- Include `new_password` and/or `new_mpin` to update credentials after verification.

## Endpoint Summary
- `GET /api/health` Ã¢â‚¬â€ Connectivity check to Oracle.
- `GET /api/config` Ã¢â‚¬â€ Shows non-secret connection settings and table selection.
- All other `/api/*` endpoints require `Authorization: Bearer <session_token>`.
- `GET /api/trend` Ã¢â‚¬â€ Computes EMA groupings from recent prices for all symbols. Optional `?refresh=1` to bypass cache.
- `GET /api/trend/latestDate` - Returns `{ "ltc_date": "YYYY-MM-DD" }` from the trend source with a short-lived cache.
- `GET /api/trend/ping` - Trend API DB heartbeat with measured latency in milliseconds.
- `GET /api/trend/metrics` - Latest-date cache/query counters for SLA monitoring.
- `GET /api/momentum/macd` Ã¢â‚¬â€ MACD momentum stacks with caching.
- `GET /api/sr-levels` Ã¢â‚¬â€ Detailed multi-timeframe support/resistance analysis with tolerance filters.
- `GET /api/price-action-sr-levels-manually` - Returns grouped manual price action SR symbols.
- `POST /api/price-action-sr-levels-manually` - Create, update, or delete a symbol set using `mode`.
- `GET /api/volume` Ã¢â‚¬â€ Volume and OBV indicators.
- `GET /api/atr14` Ã¢â‚¬â€ Average True Range snapshot.
- `GET /api/dashboard/movers` Ã¢â‚¬â€ Top gainers/losers & market breadth for dashboards.
- `GET /api/yamuna/last-ltc-date` - Last inserted LTC_DATE per Yamuna table.
- `POST /api/yamuna/ingest` - Export Yamuna CSV files and MERGE into `GAINERS_TOP25`, `LOOSERS_TOP25`, `VOLUME_MOVERS_TOP25`.
  - Reference DDL script: `db/yamuna_tables.sql` (repo root, idempotent).
- `POST /api/auth/register` Ã¢â‚¬â€ Local registration capture (Oracle-backed).
- `POST /api/auth/login` - Login check against the local registration store.
- `POST /api/auth/activity` - Manual login activity logging.
- `POST /api/auth/reset` - Verify DOB/PAN/Aadhaar and reset password or MPIN.



