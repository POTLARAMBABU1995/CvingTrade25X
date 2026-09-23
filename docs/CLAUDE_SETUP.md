# Claude Setup

## Remote connector

Use the reachable HTTPS URL `https://mcp.example.com/mcp`; a Claude cloud connector cannot use localhost or local stdio. Configure OAuth/bearer authorization according to the selected Claude product, then verify tool discovery and call `health_check`.

## Local clients

For a Claude-compatible local desktop/CLI host that supports stdio, launch:

```powershell
C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X\.venv-mcp\Scripts\python.exe -m backend.mcp_server.cli serve --transport stdio
```

Do not place Oracle credentials in the client configuration. The local subprocess inherits its server-side environment from the host process.

Current Anthropic entry points and product distinctions are linked from [Anthropic MCP documentation](https://docs.anthropic.com/en/docs/mcp). The Messages API connector requires a public HTTPS server and accepts an OAuth bearer access token; the caller manages token acquisition/refresh. Product support can differ between Claude.ai, Claude Desktop, Claude Code, and the API, so validate the exact target product before rollout.
