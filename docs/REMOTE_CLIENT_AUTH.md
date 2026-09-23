# Remote Client Authentication

## Bearer

Set `CVING_MCP_AUTH_MODE=bearer` and provide a cryptographically random token of at least 32 characters through `CVING_MCP_BEARER_TOKEN`. Clients that allow a custom `Authorization: Bearer <token>` header can use this mode. Tokens never belong in URLs, committed files, command output, or `.runtime/` metadata.

## OAuth

Set `CVING_MCP_AUTH_MODE=oauth` and configure the existing external HTTPS introspection settings. The MCP remains a resource server; it does not mint tokens. Client and provider support varies, and an ephemeral Quick Tunnel URL may require OAuth resource/callback configuration to be refreshed.

## Local no-auth

`CVING_MCP_AUTH_MODE=none` is appropriate only on loopback for local development. It remains the local profile default.

## Explicit temporary public no-auth test

Public anonymous mode is disabled by default. A deliberate short test requires both `CVING_MCP_AUTH_MODE=none` and `CVING_MCP_ALLOW_PUBLIC_NOAUTH_TEST=true`. The starter prints a prominent warning, keeps the existing read-only tools and egress/rate/response limits, and never exposes Oracle or arbitrary SQL. Stop the tunnel immediately after testing.

Do not silently fall back to anonymous access when a remote client cannot send bearer headers or complete OAuth. Use a compatible authentication method or do not connect that client.
