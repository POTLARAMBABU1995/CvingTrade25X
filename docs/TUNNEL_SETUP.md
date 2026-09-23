# Vendor-Neutral Tunnel Setup

Cloudflare Tunnel is the documented vendor-neutral outbound option. The MCP core has no Cloudflare dependency.

## Free temporary Quick Tunnel

Use this only for development/testing. Cloudflare generates a different public hostname on most restarts, provides no SLA, limits Quick Tunnels to 200 concurrent in-flight requests, and does not support SSE. CvingTrade25X uses stateless Streamable HTTP with JSON responses, so required MCP request/response operations do not require SSE; the remote validator must still pass before compatibility is claimed.

1. Install `cloudflared` from the [official Windows downloads](https://developers.cloudflare.com/tunnel/downloads/). Windows installations do not auto-update.
2. Configure bearer authentication (recommended) or OAuth in `.env` and keep MCP bound to `127.0.0.1:1729`.
3. Run `scripts\start_remote_mcp.cmd`. It starts MCP if needed, runs the official `cloudflared tunnel --url http://127.0.0.1:1729` flow with a loopback Host override, captures the actual generated URL, then validates HTTPS/TLS/MCP/auth/tools/health remotely.
4. Inspect with `scripts\remote_mcp_status.cmd`. Stop only the tunnel with `scripts\stop_remote_mcp.cmd`, or stop both owned processes with `scripts\stop_remote_mcp.cmd --all`.

The starter refuses public anonymous mode unless `CVING_MCP_ALLOW_PUBLIC_NOAUTH_TEST=true` is explicitly set. It never tunnels Oracle port 1521 and never writes tokens to `.runtime/`. If `%USERPROFILE%\.cloudflared\config.yml` or `config.yaml` exists, the script warns without modifying it because [Cloudflare documents that Quick Tunnels may not work with that global configuration](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/).

Quick Tunnel status must remain `FAIL` or `NOT TESTED` until the generated HTTPS endpoint passes initialize, protocol negotiation, `tools/list`, `health_check`, authentication, and a bounded market-data tool call. Cloudflare documents the current Quick Tunnel limits in its [official guide](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/).

## Stable named tunnel

1. Install `cloudflared` on Windows and authenticate with `cloudflared tunnel login`.
2. Create a named tunnel and route a stable DNS hostname.
3. Configure ingress to the loopback MCP process:

```yaml
tunnel: <TUNNEL-UUID>
credentials-file: C:\Users\<user>\.cloudflared\<TUNNEL-UUID>.json
ingress:
  - hostname: mcp.example.com
    service: http://127.0.0.1:1729
  - service: http_status:404
```

4. Validate with `cloudflared tunnel ingress validate` and run with `cloudflared tunnel run <name-or-uuid>`.
5. Run `scripts\run_secure_profile.cmd`, then the remote validator.

Cloudflare documents named tunnels, Windows services, and the required catch-all ingress rule in its [official tunnel guide](https://developers.cloudflare.com/tunnel/features/locally-managed-tunnels/create-local-tunnel/). Temporary `trycloudflare.com` URLs are development-only and must not be recorded as production configuration.

Do not place a browser-only access gateway in front of clients that cannot complete that gateway's interaction. MCP bearer/OAuth must remain independently usable.
