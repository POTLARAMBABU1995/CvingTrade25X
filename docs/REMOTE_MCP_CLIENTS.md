# Remote MCP Client Compatibility

Use one vendor-neutral endpoint for every compatible client:

```text
https://<public-hostname>/mcp
```

Never configure a cloud client with `localhost`, `127.0.0.1`, Oracle port 1521, or a stdio command. The current server supports Streamable HTTP and bearer authentication; OAuth mode is available when an external OAuth/OIDC provider and introspection endpoint are configured.

Compatibility was checked against official provider documentation on 2026-09-18. Provider availability, account tier, region, and authentication requirements can change.

| AI / client | Direct remote MCP | Authentication | Status / notes |
|---|---:|---|---|
| Gemini Web custom apps | Yes, where the Custom Apps feature is available | OAuth/DCR or client credentials supported by Gemini; verify static bearer behavior in the active account | Enter the public HTTPS `/mcp` URL in Gemini Connected Apps. Current availability is restricted by account, age, region, language, and activity settings. |
| Grok custom connectors | Yes | Provider UI supports required authentication; Grok CLI also documents static bearer headers | Enter the public HTTPS `/mcp` URL. The server must be publicly reachable. |
| Claude Web custom connectors | Yes on supported paid plans | OAuth or authless are documented; use this server's OAuth mode for Claude rather than assuming static bearer support | Add the public URL under Settings > Connectors. Streamable HTTP is supported. |
| Qwen | Requires an MCP-capable Qwen host/client | Qwen Code documents headers and bearer-token environment variables | Qwen Code can use remote Streamable HTTP, but this project does not claim a raw custom-server registration flow in Qwen Web. |
| Kimi | Depends on surface | Kimi Code supports static headers, bearer-token environment variables, and OAuth | Kimi Code accepts remote HTTP MCP URLs. Kimi Web exposes MCP through its plugin system; package/register through that supported flow rather than assuming a raw URL field. |
| GLM / Z.AI | Yes through the Z.AI API MCP-calling feature | Custom headers, including `Authorization`, are supported | Supply `server_url`, `transport_type: streamable-http`, and the bearer header from a secure secret source. |
| DeepSeek | Requires an MCP-capable host/client | Determined by that host/client | No official DeepSeek web custom-MCP registration flow was verified. Use a standards-compliant remote agent/client with a DeepSeek model. |
| Generic MCP client | Yes when Streamable HTTP and the selected auth mode are supported | Bearer now; OAuth with configured provider | Use the single public HTTPS `/mcp` URL and run tool discovery before use. |

Official references:

- [Gemini custom apps](https://support.google.com/gemini/answer/17209137)
- [Gemini API remote MCP](https://ai.google.dev/gemini-api/docs/function-calling)
- [Grok custom MCP connectors](https://docs.x.ai/grok/connectors)
- [Claude remote MCP connectors](https://support.anthropic.com/en/articles/11503834-building-custom-integrations-via-remote-mcp-servers)
- [Qwen Code MCP](https://qwenlm.github.io/qwen-code-docs/en/users/features/mcp/)
- [Kimi Code MCP](https://www.kimi.com/code/docs/en/kimi-code-cli/customization/mcp.html)
- [Kimi plugins](https://www.kimi.com/en/help/plugins-and-skills/overview)
- [Z.AI MCP calling](https://docs.z.ai/guides/capabilities/mcp-call)

Quick Tunnels are for development/testing only. Cloudflare documents no SLA, a 200 in-flight request limit, and no SSE support. This MCP uses Streamable HTTP, but a named tunnel and stable hostname are required for production.
