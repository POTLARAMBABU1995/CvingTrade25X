# ChatGPT and the Temporary Quick Tunnel

Verified against official OpenAI documentation on 2026-09-18.

- Custom remote MCP: supported in ChatGPT developer mode. Full MCP is documented for Business and Enterprise/Edu; Pro is limited to read/fetch permissions.
- Endpoint: use the generated `https://<random>.trycloudflare.com/mcp`, never localhost.
- Authentication: use the authentication flow supported by the configured ChatGPT app. The current product documentation does not establish arbitrary static bearer-header entry in the ChatGPT UI, so do not make that claim. Use OAuth when required.
- Transport: this server exposes stateless Streamable HTTP JSON request/response behavior. The Quick Tunnel must pass `scripts\validate_remote_mcp.py` before use.
- Temporary lifecycle: replace the app URL after every tunnel restart.

Current product setup and plan controls: [Developer mode and MCP apps in ChatGPT](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt).

This repository change was not tested against a live ChatGPT workspace/account.
