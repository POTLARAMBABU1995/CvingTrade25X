# ChatGPT Setup

ChatGPT cannot connect directly to `http://127.0.0.1:1729/mcp`. Use `https://mcp.example.com/mcp` or OpenAI Secure MCP Tunnel for a private/on-premises server.

1. Start the MCP in `secure-tunnel` or `remote-gateway` profile.
2. Validate the HTTPS endpoint with `scripts\validate_remote_mcp.cmd`.
3. In ChatGPT web, enable Developer Mode if your plan/workspace permits it.
4. Go to Apps/Create, provide the remote MCP endpoint and configured authentication, then select **Scan Tools**.
5. Confirm the same 16 universal read-only tools are discovered; no `search`/`fetch` aliases are required.

OpenAI's current product steps and plan limitations are in [Developer mode and MCP apps](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt). OpenAI states that private/on-premises servers should use Secure MCP Tunnel, but the public page does not publish a stable copy/paste tunnel command; obtain the exact command from the current supported OpenAI UI/documentation rather than inventing one.

For API clients, the OpenAI Responses API supports a remote MCP `server_url` and OAuth authorization token. See the [official OpenAI remote MCP API reference](https://platform.openai.com/docs/api-reference/responses-streaming/response/refusal?lang=python).

No live ChatGPT connection is claimed until a workspace user completes the tunnel/HTTPS and tool-scan steps.
