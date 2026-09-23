# CvingTrade25X MCP Setup

> This compatibility page is retained for existing links. The current split documentation is `CHATGPT_SETUP.md`, `MCP_ARCHITECTURE.md`, `REMOTE_MCP.md`, `TUNNEL_SETUP.md`, and `OAUTH_SETUP.md`.

## Local development

Create the dedicated MCP virtual environment, then validate the registered tool contracts. The isolated environment prevents the current MCP SDK's Uvicorn requirement from changing the existing application runtime pin.
The venv uses the already configured application Python packages for Oracle/market-data imports and keeps MCP/Pydantic/Uvicorn overrides local to `.venv-mcp`.

```powershell
cd C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X
scripts\setup_mcp_venv.cmd
.venv-mcp\Scripts\python.exe scripts\validate_mcp.py
```

Run over stdio for a local MCP host or Inspector:

```powershell
scripts\run_mcp_stdio.cmd
```

Run local Streamable HTTP:

```powershell
scripts\run_mcp_http.cmd
```

The private tunnel origin is `http://127.0.0.1:1729/mcp`. The Flask application remains on its existing port and is not replaced by the MCP process. Remote clients must use the public HTTPS endpoint produced by `scripts\start_remote_mcp.cmd`.

MCP Inspector:

```powershell
.venv-mcp\Scripts\mcp.exe dev backend\mcp_server\server.py
```

Verify `tools/list`, call `health_check`, then call `get_latest_price` and `analyze_symbol` for a known symbol.

## ChatGPT and remote clients

ChatGPT remote MCP connections cannot directly reach a localhost endpoint. Keep Oracle and port 1521 private. Use the currently supported OpenAI private-network/tunnel mechanism or deploy the MCP behind authenticated HTTPS. Re-check current OpenAI documentation before deployment because product availability and setup UI can change.

The OpenAI API supports MCP tools as remote integrations: <https://developers.openai.com/api/reference/cli/resources/responses/methods/create>. The official MCP Python SDK supports stdio and Streamable HTTP: <https://github.com/modelcontextprotocol/python-sdk>.

## Security controls

- HTTP binds to `127.0.0.1` by default.
- A non-loopback bind fails closed unless `CVING_MCP_ALLOW_REMOTE=1`, a bearer token of at least 32 characters, and an explicit origin allowlist are configured.
- Set `CVING_MCP_BEARER_TOKEN` to require authentication even on localhost.
- Never publish Oracle port 1521 or copy credentials into a client configuration.
- All tool arguments are typed and bounded; symbols/timeframes are allowlisted.
- The service has no arbitrary-SQL or write tool.
- Errors are sanitized on the MCP wire; detailed exceptions stay in local logs.
- Database outputs are bounded, carry provenance/trust-boundary metadata, and are treated as untrusted data rather than instructions.
- Run behind TLS and a supported identity-aware tunnel for any remote deployment.

Example tunnel settings (use a secret store, not a checked-in file; keep the MCP origin loopback-bound):

```powershell
$env:CVING_MCP_PROFILE = 'secure-tunnel'
$env:CVING_MCP_PUBLIC_BASE_URL = 'https://mcp.example.com/mcp'
$env:CVING_MCP_ALLOWED_HOSTS = 'mcp.example.com,localhost,127.0.0.1'
$env:CVING_MCP_AUTH_MODE = 'bearer'
$env:CVING_MCP_BEARER_TOKEN = '<at-least-32-random-characters>'
$env:CVING_MCP_ALLOWED_ORIGINS = 'https://your-approved-client.example'
scripts\run_secure_profile.cmd
```

## Troubleshooting

- `health_check` may return `DEGRADED` while the MCP process itself remains alive if Oracle is unavailable.
- `TIMEFRAME_NOT_AVAILABLE` for 1H/4H is expected until an existing reliable intraday source is added to the application.
- `DATA_QUALITY_ERROR` means the MCP refused to produce a misleading verdict.
- Never weaken bounds or expose a generic SQL tool to work around missing data.
