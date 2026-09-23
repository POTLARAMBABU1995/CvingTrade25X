# CvingTrade25X MCP Architecture

## Discovered implementation

- SDK: official Python MCP SDK `2.2.0` in isolated `.venv-mcp`.
- Transports: stdio and Streamable HTTP at `/mcp`; legacy SSE is not configured.
- Endpoint: `http://127.0.0.1:1729/mcp` as the private HTTP/tunnel origin.
- Core: `backend/mcp_server/server.py`; transport/profile CLI: `backend/mcp_server/cli.py`.
- Data adapters: existing `chart_service.fetch_ohlcv_payload`, `marketdata_service.list_symbols`, `price_action_service.fetch_price_action_page`, and `technical_utils` functions.
- Oracle: existing application pool and read paths; no MCP SQL/query argument and no MCP write operation.
- Security: SDK protocol negotiation and protected-resource auth, plus repository Host/Origin, rate, concurrency, body/response, timeout, and egress policy.

```text
Local stdio client --------------------+
                                       |
Cloud AI -> HTTPS tunnel -> 127.0.0.1:1729 ---+-> one MCP core -> existing services -> Oracle 19c private
                                       |
Cloud AI -> HTTPS edge/tunnel ----------+
                TLS + auth + policy
```

The core never branches on ChatGPT, Claude, Gemini, Grok, or another client. Client differences end at connection/auth configuration.

## Profiles

| Profile | Transport | Bind | Authentication |
| --- | --- | --- | --- |
| `local-stdio` | stdio | none | process boundary |
| `local-http` | Streamable HTTP | `127.0.0.1:1729` | `none` or optional bearer |
| `secure-tunnel` | Streamable HTTP behind outbound tunnel | loopback | bearer or OAuth |
| `remote-gateway` | Streamable HTTP behind private reverse proxy | private/explicit | bearer or OAuth |

Remote profiles require an HTTPS public base URL and reject `AUTH_MODE=none`. Non-loopback binding additionally requires `CVING_MCP_ALLOW_REMOTE=1`.

## Protocol behavior

The SDK negotiates the current protocol and remains compatible with 2025-era initialization. SDK 2.x supports the 2026-07-28 discovery path and legacy initialization on the same stdio/Streamable HTTP implementation. See the [official SDK protocol guide](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/protocol-versions.md).
