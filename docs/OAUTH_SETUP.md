# MCP OAuth Authentication Setup

CvingTrade25X MCP supports three authentication modes for remote access:

## 1. Built-in OAuth 2.1 Authorization Server (`oauth-server`) — Recommended

The MCP server acts as its own OAuth 2.1 Authorization Server, implementing:
- Authorization Code flow with PKCE (S256 only)
- Dynamic Client Registration (RFC 7591)
- Protected Resource Metadata (RFC 9728)
- Authorization Server Metadata (RFC 8414)
- Token Refresh and Revocation (RFC 7009)

This is the recommended mode for maximum compatibility with standards-compliant MCP clients.

### Configuration

```powershell
$env:CVING_MCP_AUTH_MODE = 'oauth-server'
$env:CVING_MCP_OAUTH_OWNER_PASSWORD = '<at-least-16-character-password>'  # Owner consent password
$env:CVING_MCP_BEARER_TOKEN = '<at-least-32-character-token>'             # Optional static bearer fallback
$env:CVING_MCP_OAUTH_ACCESS_TOKEN_TTL_SECONDS = '3600'                    # Optional, default: 1 hour
$env:CVING_MCP_OAUTH_REFRESH_TOKEN_TTL_SECONDS = '86400'                  # Optional, default: 24 hours
```

### How it Works

1. Client discovers the authorization server via `/.well-known/oauth-protected-resource/mcp`
2. Client dynamically registers via `/register` (RFC 7591)
3. Client initiates Authorization Code + PKCE flow via `/authorize`
4. Owner approves access on the consent page at `/oauth/consent`
5. Client exchanges authorization code for tokens at `/token`
6. Client uses Bearer token for MCP requests to `/mcp`

### Static Bearer Token Fallback

When `CVING_MCP_BEARER_TOKEN` is also configured, clients that don't support OAuth
can use `Authorization: Bearer <token>` directly. Both authentication methods work
simultaneously on the same `/mcp` endpoint.

### Client Compatibility

| Client | OAuth 2.1 | Static Bearer | Streamable HTTP |
|--------|-----------|--------------|-----------------|
| Claude | ✅ OAuth + DCR | ✅ | ✅ |
| Gemini | ✅ where supported | ✅ | ✅ |
| ChatGPT | ✅ where supported | ✅ | ✅ |
| Grok | ✅ where supported | ✅ | ✅ |
| Qwen | ✅ where supported | ✅ | ✅ |
| Kimi | ✅ where supported | ✅ | ✅ |
| GLM/Z.AI | ✅ where supported | ✅ | ✅ |
| DeepSeek | ✅ via MCP host | ✅ via MCP host | ✅ |
| Cursor/VS Code | ✅ | ✅ | ✅ |
| Generic MCP Host | ✅ | ✅ | ✅ |

> **Note**: "Server compatible" means the server exposes all required standards-compliant
> endpoints. Whether a specific client currently has a custom MCP UI is a client-side limitation.

### Cloudflare Quick Tunnel

All OAuth metadata endpoints dynamically resolve the public HTTPS URL from the
Cloudflare Quick Tunnel. When the tunnel restarts with a new hostname, all OAuth
discovery responses automatically use the new URL. Never hardcode `*.trycloudflare.com`.

---

## 2. Static Bearer Token (`bearer`)

Simple authentication using a pre-shared token.

```powershell
$env:CVING_MCP_AUTH_MODE = 'bearer'
$env:CVING_MCP_BEARER_TOKEN = '<at-least-32-character-token>'
```

Clients pass `Authorization: Bearer <token>` on every request. No OAuth flow needed.

---

## 3. External OAuth/OIDC Provider (`oauth`)

Use an external OAuth 2.1/OIDC provider (Keycloak, Auth0, Entra, etc.) for
enterprise deployments. The MCP server validates tokens via RFC 7662 introspection.

```powershell
$env:CVING_MCP_AUTH_MODE = 'oauth'
$env:CVING_MCP_OAUTH_ISSUER_URL = 'https://id.example.com'
$env:CVING_MCP_OAUTH_INTROSPECTION_URL = 'https://id.example.com/oauth2/introspect'
$env:CVING_MCP_OAUTH_CLIENT_ID = '<resource-server-client-id>'
$env:CVING_MCP_OAUTH_CLIENT_SECRET = '<secret-from-secret-store>'
$env:CVING_MCP_OAUTH_RESOURCE_URL = 'https://mcp.example.com/mcp'
$env:CVING_MCP_OAUTH_EXPECTED_AUDIENCE = 'https://mcp.example.com/mcp'
```

The external issuer must publish discovery metadata, PKCE support, and these scopes:
- `cving:market:read`
- `cving:analysis:read`
- `cving:scan:read`
- `cving:admin:health`

---

## Security Notes

- No secrets are ever logged, returned in responses, or included in metadata.
- MCP binds only to `127.0.0.1:1729` — never directly exposed to the internet.
- Oracle port 1521 is never tunneled.
- All 16 MCP tools are read-only.
- PKCE S256 is mandatory for all authorization code grants.
- Dynamic client registrations are stored in-memory (lost on restart).
