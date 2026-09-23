# Cloudflare tunnel configuration

Current installation used Quick Tunnel. It has no stable hostname configured.
No domain, tunnel UUID or account credentials are invented by setup.

Configure ignored .env:
```dotenv
CVING_CLOUDFLARE_MODE=named
CVING_MCP_PUBLIC_HOST=mcp.your-owned-domain.example
CVING_MCP_PUBLIC_URL=https://mcp.your-owned-domain.example/mcp
CVING_CLOUDFLARE_TUNNEL_ID=<existing-tunnel-uuid>
CVING_CLOUDFLARE_CONFIG=<absolute-path-to-reviewed-config.yml>
```
The domain above is an example only. Create a locally managed named tunnel and
DNS route in your Cloudflare account. Its config should contain exactly this
route and deny catch-all (replace all placeholders):
```yaml
tunnel: <existing-tunnel-uuid>
credentials-file: 'C:\protected\<existing-tunnel-uuid>.json'
ingress:
  - hostname: mcp.your-owned-domain.example
    service: http://127.0.0.1:1729
  - service: http_status:404
```
Protect credentials/config with ACLs and allow SYSTEM to read them. The installer
uses the existing cloudflared executable and its ingress validator, refuses an
unowned existing service, installs Automatic startup and recovery, then confirms
Running and public 401. It never logs or passes a tunnel token on the command line.
This managed installer supports **locally managed named tunnels**. Existing
remotely managed/token services are detected but deliberately not adopted or
replaced; migrate them separately through Cloudflare administration if desired.

Official setup references:
- https://developers.cloudflare.com/tunnel/features/locally-managed-tunnels/create-local-tunnel/
- https://developers.cloudflare.com/tunnel/features/locally-managed-tunnels/as-a-service/windows/

quick mode is development/testing only. Its temporary URL can change on restart.
disabled mode starts local MCP only. Without CVING_CLOUDFLARE_MODE, the legacy
CVING_QUICK_TUNNEL_ENABLED switch is honored, avoiding a silent mode migration.
Stop the stack before switching mode. Changing hostname requires matching DNS,
ingress, PUBLIC_HOST/PUBLIC_URL and any explicit OAuth issuer/resource overrides,
then restart and validate discovery and authenticated MCP calls.

Remote clients use the HTTPS /mcp URL with the existing Bearer or OAuth flow.
Client MCP support differs; compatibility with every named AI vendor is not
asserted merely because the endpoint uses the standard transport.
