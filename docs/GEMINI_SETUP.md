# Gemini Setup

Gemini CLI supports local stdio and Streamable HTTP. Current official syntax:

```powershell
gemini mcp add --transport http cvingtrade25x http://127.0.0.1:1729/mcp
gemini mcp list
```

With local bearer authentication:

```powershell
gemini mcp add --transport http --header "Authorization: Bearer <token>" cvingtrade25x http://127.0.0.1:1729/mcp
```

For stdio:

```powershell
gemini mcp add cvingtrade25x C:\Users\admin\Documents\CvingTrade25X\CvingTrade25X\.venv-mcp\Scripts\python.exe -- -m backend.mcp_server.cli serve --transport stdio
```

For a remote client, replace localhost with `https://mcp.example.com/mcp` and configure the relevant auth header/OAuth flow. Confirm the project folder is trusted before diagnosing a local stdio server as disconnected.

Syntax and transport behavior were verified on 2026-09-17 against the [official Gemini CLI MCP server guide](https://geminicli.com/docs/tools/mcp-server/).
