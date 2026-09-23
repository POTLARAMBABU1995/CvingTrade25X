# MCP Security Architecture

## Trust boundaries

1. Oracle 19c stays on localhost/private networking. Do not publish TCP 1521.
2. The MCP adapter invokes named existing read services only. No tool accepts `sql`, `query`, `command`, `shell`, or `filepath`.
3. The HTTP edge terminates trusted TLS; the origin remains loopback/private HTTP.
4. Database text is returned as bounded data with a trust-boundary marker, never as instructions.

## Authentication and authorization

- `none`: local profiles only.
- `bearer`: constant-time comparison with `CVING_MCP_BEARER_TOKEN`; all four read scopes are granted to that configured service identity.
- `oauth`: external standards-compliant OAuth/OIDC provider. The resource server validates tokens through an HTTPS RFC 7662 introspection endpoint, then enforces expiry, issuer, audience/resource, and scopes.

Tool scopes are default-deny and defined in `backend/mcp_server/policy.py`. There are no write scopes.

## Network and resource controls

- Host and Origin are validated twice: repository middleware and the SDK transport-security layer.
- Forwarded client addresses are read only when `CVING_MCP_TRUST_PROXY=1` and the direct peer belongs to `CVING_MCP_TRUSTED_PROXIES` CIDRs.
- Defaults: 60 requests/minute/identity, 10 concurrent HTTP requests, 1 MiB request/response, 30-second tool timeout, 2,000 bars, 500 scan symbols, 50 results.
- Oracle failures open a bounded circuit breaker; readiness fails closed while Oracle is unavailable.
- Responses add `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`. Configure HSTS at the TLS edge.

## Safe audit fields

Audit records may include request ID, subject, auth mode, tool, status, duration, transport, and protocol version. Authorization headers, tokens, OAuth codes, Oracle credentials, and full OHLCV payloads are never logged.

## Oracle least privilege

Use a dedicated account granted `CREATE SESSION` and `SELECT` only on the exact approved tables/views. Revoke DDL/DML privileges. Runtime code still uses the existing Oracle pool and bind-safe service owners; this enhancement does not change schema or grants.
