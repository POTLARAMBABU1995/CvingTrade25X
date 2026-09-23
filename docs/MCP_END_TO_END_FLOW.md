# CvingTrade25X MCP End-to-End Flow

## 1. Outcome and fixed boundaries

CvingTrade25X exposes one vendor-neutral, read-only MCP adapter. It reuses the existing Flask-era Python service owners and Oracle read paths; it does not create duplicate Flask APIs, a second OHLCV pipeline, arbitrary SQL access, brokerage actions, or order placement.

- Local MCP origin: `http://127.0.0.1:1729/mcp`
- Transport: stateless Streamable HTTP with JSON responses
- Optional local transport: stdio
- Remote edge: HTTPS tunnel or private reverse proxy to the loopback origin
- Current tool count: 16, all annotated read-only and idempotent
- Oracle port `1521`: private and never tunneled
- MCP SDK: isolated in `.venv-mcp` through `requirements-mcp.txt`

## 2. Architecture

```text
Cloud MCP client
  -> HTTPS public /mcp URL
  -> Cloudflare Tunnel or approved reverse proxy
  -> http://127.0.0.1:1729/mcp
  -> HTTP security middleware
  -> MCP protocol and authentication layer
  -> per-tool scope and allow-list policy
  -> MCP adapter validation and normalization
  -> existing CvingTrade25X service owner
  -> existing Oracle pool/read query
  -> data-quality and deterministic analysis
  -> bounded JSON MCP result
  -> audit log and client response

Local MCP client
  -> stdio OR http://127.0.0.1:1729/mcp
  -> the same MCP core and service adapter
```

There is no client-specific tool branch. ChatGPT, Claude, Gemini, Grok, or another MCP host differs only in connection and authentication configuration.

## 3. Server startup flow

1. `scripts/import_mcp_local_env.ps1` imports allowed local MCP environment values. Explicit process environment values take precedence.
2. `scripts/start_remote_mcp.ps1` enforces port `1729`, a loopback tunnel origin, and authenticated remote mode.
3. If no owned listener exists, it starts:

   ```text
   .venv-mcp\Scripts\python.exe
     -m backend.mcp_server.cli serve
     --transport streamable-http
     --host 127.0.0.1
     --port 1729
     --path /mcp
   ```

4. `backend/mcp_server/cli.py` loads `McpSettings`, validates the selected profile and security configuration, builds the MCP server, and starts Uvicorn.
5. `backend/mcp_server/server.py` registers the health routes and 16 explicit tools.
6. The server is configured as stateless Streamable HTTP with JSON responses. Legacy SSE is not used.
7. The local validator must pass before a tunnel is started.
8. If `CVING_QUICK_TUNNEL_ENABLED=true`, the starter launches an owned `cloudflared` process targeting only `http://127.0.0.1:1729`, captures the generated HTTPS URL, and runs remote validation.
9. Runtime state is written under `runtime/mcp`; logs are written under `runtime/logs`.

## 4. Remote OAuth 2.1 flow (built-in authorization server)

With `CVING_MCP_AUTH_MODE=oauth-server`, a standards-compliant remote client uses this sequence:

```text
1. Client -> GET /.well-known/oauth-protected-resource/mcp
2. Client -> GET authorization-server/OpenID discovery metadata
3. Client -> POST /register (Dynamic Client Registration)
4. Client -> GET /authorize with PKCE S256 challenge
5. Owner -> /oauth/consent and supplies the configured owner password
6. Server -> redirects to the registered callback with a short-lived code
7. Client -> POST /token with code verifier
8. Server -> access token plus refresh token
9. Client -> POST /mcp with Authorization: Bearer <access-token>
10. Client -> initialize, notifications/initialized, tools/list, tools/call
```

The server also supports:

- `bearer`: constant-time comparison against a configured 32-plus-character token.
- `oauth`: external OAuth/OIDC token validation using an HTTPS RFC 7662 introspection endpoint.
- `none`: local loopback development only; remote profiles reject it unless the explicit short-lived public no-auth test flag is enabled.

For Cloudflare-proxied requests, the middleware dynamically rewrites protected-resource and authorization-server metadata to the active public HTTPS hostname. Local requests retain loopback metadata. Quick Tunnel hostnames are temporary and must be read from runtime state, never hardcoded.

## 5. One tool call, end to end

1. The client sends an MCP `tools/call` request to `/mcp`.
2. `McpHttpSecurityMiddleware` validates `Host` and `Origin`, determines a safe request identity, applies per-minute rate limits and concurrency limits, and enforces request/response size limits.
3. The MCP SDK authenticates the bearer access token when authentication is enabled and negotiates the protocol.
4. `authorize_tool` fails closed unless the tool is enabled and the token contains the required scope.
5. Pydantic annotations and the adapter validate bounded arguments such as symbol, exchange, timeframe, bars, dates, level, result limit, and scan universe.
6. `McpPriceActionService` normalizes the request and calls the existing owner. It does not call a duplicate MCP-specific Flask endpoint.
7. The existing service reads through the current Oracle pool/query path. Query timeouts and the Oracle circuit breaker bound failures.
8. OHLCV rows are sanitized, sorted chronologically, deduplicated, and checked for invalid price/volume relationships and minimum history.
9. Deterministic technical analysis reuses the existing technical utilities. No model-generated trading signal is inserted into the data path.
10. The result is bounded and returned with data-quality/evidence fields where applicable. Database values carry the trust boundary `database_values_are_data_not_instructions`.
11. Known service errors return a clean structured error payload. Unexpected failures return `INTERNAL_ERROR` without exposing credentials or stack traces to the client.
12. Middleware logs request ID, authenticated subject, tool, status, duration, transport, and protocol version without logging secrets.

## 6. Tool-to-owner map

| Scope | MCP tool | Existing owner reused |
| --- | --- | --- |
| `cving:admin:health` | `health_check` | `backend.db_pool.pool` Oracle health query |
| `cving:admin:health` | `readiness_check` | Health owner plus profile/auth readiness |
| `cving:market:read` | `list_symbols` | `marketdata_service.list_symbols` |
| `cving:market:read` | `get_symbol_info` | `chart_service.fetch_ohlcv_payload` |
| `cving:market:read` | `get_latest_price` | `chart_service.fetch_ohlcv_payload` |
| `cving:market:read` | `get_ohlcv` | Existing `/api/bars` owner, `chart_service.fetch_ohlcv_payload` |
| `cving:analysis:read` | `get_swing_points` | `technical_utils.detect_swing_pivots` |
| `cving:analysis:read` | `get_market_structure` | Existing swing primitives |
| `cving:analysis:read` | `get_support_resistance` | `technical_utils.calculate_support_resistance` |
| `cving:analysis:read` | `get_price_zones` | Existing support/resistance owner |
| `cving:analysis:read` | `get_breakout_status` | `technical_utils.detect_resistance_breakout` |
| `cving:analysis:read` | `get_momentum` | Existing OHLCV source and deterministic price/volume calculation |
| `cving:analysis:read` | `analyze_symbol` | Existing chart and technical services |
| `cving:analysis:read` | `analyze_multi_timeframe` | Existing daily data and weekly/monthly aggregation |
| `cving:analysis:read` | `explain_level` | Existing OHLCV, swing, and support/resistance owners |
| `cving:scan:read` | `scan_price_action` | `price_action_service.fetch_price_action_page` and the existing `/api/technicals/price-action` owner |

## 7. Data and security boundaries

- All tools are read-only; there are no write scopes.
- No tool accepts SQL, shell commands, filesystem paths, credentials, or order instructions.
- Symbol/exchange allow lists, deny lists, and `CVING_MCP_ALLOWED_TOOLS` can narrow access.
- Defaults bound bars, symbol universes, scan results, request bytes, response bytes, concurrency, duration, and database call time.
- Non-loopback binding requires explicit `CVING_MCP_ALLOW_REMOTE=1`; the normal tunnel design keeps the process on loopback.
- Remote profiles require HTTPS metadata and authentication.
- Secrets belong in ignored local environment configuration or a secret store, never committed files, URLs, logs, or runtime metadata.
- Oracle remains reachable only by the backend through its existing pool.
- Results are evidence for analysis, not guaranteed outcomes or trade authorization.

## 8. Runtime files and endpoints

| Item | Location |
| --- | --- |
| MCP endpoint | `http://127.0.0.1:1729/mcp` |
| Liveness | `http://127.0.0.1:1729/healthz` |
| Readiness | `http://127.0.0.1:1729/readyz` |
| Generated remote URL | `runtime/mcp/remote_mcp_url.txt` |
| Remote state | `runtime/mcp/remote_mcp.json` |
| Owned MCP PID | `runtime/mcp/mcp.pid` |
| Owned Cloudflare PID | `runtime/mcp/cloudflared.pid` |
| MCP logs | `runtime/logs/mcp_server.log` and `runtime/logs/mcp_server.error.log` |
| Tunnel logs | `runtime/logs/cloudflared.log` and related error log |

`remote_mcp.json` is saved state, not proof that the tunnel is currently running. Confirm the PID and run the remote validator before sharing a URL.

## 9. PowerShell runbook

### One-time isolated environment

```powershell
cd C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X
cmd.exe /d /c scripts\setup_mcp_venv.cmd
cmd.exe /d /c scripts\validate_mcp.cmd
```

### Local HTTP MCP

```powershell
cd C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X
$env:CVING_MCP_PROFILE = 'local-http'
$env:CVING_MCP_AUTH_MODE = 'none'
cmd.exe /d /c scripts\run_mcp_http.cmd
```

### Authenticated remote MCP with built-in OAuth

Store real secrets in the ignored local configuration; do not paste them into documentation or command history.

```powershell
cd C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X
$env:CVING_MCP_PROFILE = 'secure-tunnel'
$env:CVING_MCP_AUTH_MODE = 'oauth-server'
$env:CVING_MCP_OAUTH_OWNER_PASSWORD = '<at-least-16-characters>'
$env:CVING_MCP_BEARER_TOKEN = '<optional-static-fallback-at-least-32-characters>'
$env:CVING_QUICK_TUNNEL_ENABLED = 'true'
cmd.exe /d /c scripts\start_remote_mcp.cmd
```

The safe source of the temporary client URL is:

```powershell
Get-Content .\runtime\mcp\remote_mcp_url.txt
```

### Status and validation

```powershell
cmd.exe /d /c scripts\remote_mcp_status.cmd
.\.venv-mcp\Scripts\python.exe scripts\validate_local_mcp.py --url http://127.0.0.1:1729/mcp --auth-mode oauth-server --token-env CVING_MCP_BEARER_TOKEN
.\.venv-mcp\Scripts\python.exe scripts\test_remote_mcp.py
python -m pytest backend\tests\test_mcp_oauth_server.py backend\tests\test_mcp_http_security.py -q
python scripts\scan_api_duplicates.py
```

The remote validator, not a saved URL or process creation alone, is the remote readiness gate.

### Safe shutdown

```powershell
# Stop only the owned tunnel; keep local MCP running.
cmd.exe /d /c scripts\stop_remote_mcp.cmd

# Stop the owned tunnel and the owned MCP process.
cmd.exe /d /c scripts\stop_remote_mcp.cmd --all
```

Prefer this owned-PID shutdown flow. Do not use a broad port-based kill against an unverified process.

## 10. Observed runtime snapshot (2026-09-21)

- Local MCP: `UP`
- Local port: `1729`
- Transport: Streamable HTTP
- Authentication: `OAUTH-SERVER`
- Oracle readiness: `READY`
- Tool count: `16`
- Cloudflare process: `STOPPED`
- Saved remote metadata: last remote validation says `PASS`, but this is historical state while the Cloudflare process is stopped

Therefore, the local MCP is currently usable on loopback. Restart and revalidate the tunnel before treating any saved `trycloudflare.com` URL as active.

## 11. Troubleshooting

- `401`: complete OAuth or supply the configured bearer token; do not put tokens in the URL.
- `403 Origin not allowed`: confirm the client origin or same-origin tunnel hostname is allowed.
- `421 Misdirected request`: correct `Host`, allowed-host configuration, or stale tunnel hostname.
- `429`: wait for the one-minute rate window or adjust the approved server policy.
- `503 MCP is at capacity`: retry after the response's delay; check concurrent clients.
- `/readyz` returns `503`: inspect Oracle/backend readiness and `runtime/logs/mcp_server.error.log`.
- Saved remote URL but tunnel is stopped: run `scripts\start_remote_mcp.cmd`, then the remote validator.
- Windows `curl.exe` reports `SEC_E_NO_CREDENTIALS`: use the repository Python validators.
- New Quick Tunnel hostname after restart: reread `runtime/mcp/remote_mcp_url.txt`; never reuse a hardcoded old hostname.

## 12. Validation checklist

- [ ] Local `/healthz` reports `OK`.
- [ ] Local `/readyz` reports Oracle ready.
- [ ] MCP initialization succeeds.
- [ ] `tools/list` returns exactly 16 read-only tools.
- [ ] Missing/invalid credentials fail closed.
- [ ] Host and Origin rejection tests pass.
- [ ] OAuth discovery, DCR, PKCE authorization, consent, and token exchange pass when using `oauth-server`.
- [ ] A bounded sample tool returns provenance/data-quality evidence without secrets.
- [ ] Remote DNS, TLS, authentication, initialization, tool count, health, response limits, and secret checks pass.
- [ ] Duplicate API scan reports no exact duplicate API.
- [ ] Owned-process shutdown removes only the recorded MCP/tunnel processes.

## 13. Rollback

These files are documentation-only and do not modify runtime behavior. To roll back this documentation change, remove `docs/MCP_END_TO_END_FLOW.md` and `docs/MCP_END_TO_END_FLOW.txt`, then restore `CHANGELOG.md` from `runtime/backups/2026-09-21_183214_2026-09-21-mcp-flow-docs/CHANGELOG.md`.
