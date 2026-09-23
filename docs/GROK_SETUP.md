# Grok Setup

Grok custom connectors require an MCP URL reachable from xAI's cloud. Localhost is not reachable.

1. Start the secure MCP profile and stable HTTPS tunnel/gateway.
2. Validate `https://mcp.example.com/mcp`.
3. In `grok.com/connectors`, choose **New Connector** then **Custom**.
4. Enter the HTTPS MCP URL and complete bearer/OAuth authentication.
5. Verify the universal tool list and call `health_check`.

xAI's [custom MCP connector documentation](https://docs.x.ai/grok/connectors) requires a public endpoint, and its [tunneling guide](https://docs.x.ai/grok/connectors/custom-mcp-tunneling) confirms that Streamable HTTP works through Cloudflare Tunnel while authentication remains independently required.

No live Grok connection is claimed until the connector is created in the user's xAI account.
