# Grok and the Temporary Quick Tunnel

Verified against official xAI documentation on 2026-09-18.

- Grok custom connectors accept a publicly reachable custom MCP URL; localhost/private addresses are rejected.
- xAI explicitly documents Cloudflare Quick Tunnel for Streamable HTTP MCP servers and notes that SSE must use another tunnel.
- Business/Enterprise team administration is required for the documented connector-management flow.
- Add `https://<random>.trycloudflare.com/mcp`, then complete the authentication supported by the connector. Replace the connector URL after every tunnel restart.

Official details: [xAI Custom MCP Server Tunneling](https://docs.x.ai/grok/connectors/custom-mcp-tunneling) and [Connector Management](https://docs.x.ai/grok/connector-management).

This repository change was not tested against a live Grok account.
