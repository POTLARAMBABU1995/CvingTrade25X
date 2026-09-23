# Gemini and the Temporary Quick Tunnel

Verified against official Google AI documentation on 2026-09-18.

- Gemini API Interactions supports remote MCP servers over Streamable HTTP only; SSE servers are not supported.
- The API accepts a full remote MCP URL and optional headers, including authentication headers.
- Use `https://<random>.trycloudflare.com/mcp` after it passes the repository remote validator.
- This establishes Gemini API support, not availability in the Gemini consumer website. Consumer-product custom MCP support is marked UNKNOWN until official documentation establishes it.
- Replace the URL after every Quick Tunnel restart.

Official details: [Gemini API function calling and Remote MCP](https://ai.google.dev/gemini-api/docs/function-calling).

This repository change was not tested with a live Gemini API project or consumer account.
