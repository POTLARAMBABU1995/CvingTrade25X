# Claude and the Temporary Quick Tunnel

Verified against official Anthropic documentation on 2026-09-18.

- Custom remote MCP: supported on Claude and Claude Desktop for Pro, Max, Team, and Enterprise plans.
- Transport: Streamable HTTP is supported. Anthropic also documents SSE, but Cloudflare Quick Tunnels do not support SSE; CvingTrade25X uses the non-SSE JSON response path.
- Authentication: Anthropic documents authless and OAuth remote servers. Static bearer entry is not established in the cited Claude connector documentation.
- Setup: in Settings > Connectors, add the generated `https://<random>.trycloudflare.com/mcp` URL and complete the supported authentication flow.
- Temporary lifecycle: edit or replace the connector URL after the tunnel restarts.

Official details: [Building Custom Connectors via Remote MCP Servers](https://support.anthropic.com/en/articles/11503834-building-custom-integrations-via-remote-mcp-servers).

This repository change was not tested against a live Claude account.
