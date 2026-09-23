# MCP Client Compatibility

Verified from current official documentation on 2026-09-18. “Supported” means the documented client capability, not a live account test against this repository. No vendor account was used for this change.

| Client | Local stdio | Local HTTP | Remote HTTPS | OAuth | Bearer headers | Official documentation | Limitations |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ChatGPT web custom app | No | No | Yes | Product flow supported | Not established for arbitrary static bearer in the cited UI docs | [OpenAI ChatGPT developer mode](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt) | Full MCP: Business/Enterprise/Edu; Pro read/fetch permissions; workspace controls apply |
| OpenAI API remote MCP | No | No | Yes | Caller supplies OAuth access token | Yes through request headers/authorization | [OpenAI remote MCP API fields](https://platform.openai.com/docs/api-reference/realtime-client-events/session?lang=node.js) | Application manages authentication and approvals |
| Claude web/Desktop connector | No | No | Yes, Streamable HTTP | Yes | Static bearer not documented; authless and OAuth documented | [Anthropic custom remote MCP](https://support.anthropic.com/en/articles/11503834-building-custom-integrations-via-remote-mcp-servers) | Pro, Max, Team, Enterprise; OAuth is the documented authenticated path |
| Claude local desktop/code host | Yes | Product dependent | Yes | Product dependent | Product dependent | [Anthropic MCP](https://docs.anthropic.com/en/docs/mcp) | Verify exact Claude client/version |
| Gemini API Interactions | No | No | Yes, Streamable HTTP only | Header/provider dependent | Yes through configured headers | [Gemini remote MCP](https://ai.google.dev/gemini-api/docs/function-calling) | This verifies the API, not the Gemini consumer website |
| Grok custom connector | No | No | Yes, Streamable HTTP | Supported during connector auth | API keys supported where configured | [xAI custom MCP tunneling](https://docs.x.ai/grok/connectors/custom-mcp-tunneling) | Business/Enterprise connector administration; Quick Tunnel URL is temporary |
| Generic MCP SDK 2.x client | Yes | Yes | Yes | Yes | Yes | [MCP Python SDK client transports](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/client/transports.md) | Client must support current Streamable HTTP or stdio |

The repository's automated contract tests use the same in-memory MCP core as both transports. Vendor rows are documentation-verified only; paid account calls are deliberately excluded from normal tests.
