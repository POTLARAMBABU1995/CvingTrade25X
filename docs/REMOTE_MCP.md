# Remote MCP Deployment

The public format is `https://mcp.example.com/mcp`. Never publish `http://<public-ip>:1729/mcp` or Oracle port 1521.

## Secure tunnel profile

Set secrets in the process environment or a secret manager, then run:

```powershell
$env:CVING_MCP_PROFILE = 'secure-tunnel'
$env:CVING_MCP_HOST = '127.0.0.1'
$env:CVING_MCP_PUBLIC_BASE_URL = 'https://mcp.example.com/mcp'
$env:CVING_MCP_ALLOWED_HOSTS = 'mcp.example.com,localhost,127.0.0.1'
$env:CVING_MCP_ALLOWED_ORIGINS = 'https://approved-client.example'
$env:CVING_MCP_AUTH_MODE = 'bearer'
$env:CVING_MCP_BEARER_TOKEN = '<32-plus-random-characters>'
scripts\run_secure_profile.cmd
```

The tunnel origin is `http://127.0.0.1:1729`; only the edge is public and HTTPS.

## Reverse proxy requirements

- TLS 1.2+, preferably TLS 1.3, with a trusted certificate.
- Preserve `Host`, `Authorization`, `Origin`, `Accept`, `Content-Type`, `MCP-Protocol-Version`, and `MCP-Session-Id` where applicable.
- Disable proxy buffering for streaming; use a read/idle timeout of at least 300 seconds.
- Limit request bodies to 1 MiB by default.
- Proxy only `/mcp`; keep port 1729 private.
- Set HSTS, `nosniff`, and `no-store` at the edge.

Example Nginx location (adapt and security-review before production):

```nginx
location = /mcp {
  proxy_pass http://127.0.0.1:1729/mcp;
  proxy_http_version 1.1;
  proxy_set_header Host $host;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  proxy_set_header X-Forwarded-Proto https;
  proxy_buffering off;
  proxy_read_timeout 300s;
  client_max_body_size 1m;
}
```

If forwarded addresses are needed for rate limiting, enable proxy trust only for the proxy's exact IP/CIDR. Host validation continues to use the preserved public Host header.

Validate after deployment:

```powershell
scripts\validate_remote_mcp.cmd https://mcp.example.com/mcp
```
