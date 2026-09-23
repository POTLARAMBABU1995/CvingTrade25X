from __future__ import annotations

import argparse
import os
import sys
from dataclasses import replace

import uvicorn
from mcp.server.transport_security import TransportSecuritySettings

from .config import McpSettings
from .env_loader import load_local_mcp_env
from .security import McpHttpSecurityMiddleware
from .server import build_server
from .service import McpPriceActionService


def _parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(description="CvingTrade25X read-only MCP server")
  subparsers = parser.add_subparsers(dest="command", required=True)

  serve = subparsers.add_parser("serve", help="Serve the MCP over stdio or Streamable HTTP")
  serve.add_argument("--transport", choices=("stdio", "streamable-http"), default="stdio")
  serve.add_argument("--host", default=None)
  serve.add_argument("--port", type=int, default=None)
  serve.add_argument("--path", default=None)
  return parser


def main(argv: list[str] | None = None) -> int:
  args = _parser().parse_args(argv)
  load_local_mcp_env()
  settings = McpSettings.from_env()
  from .observability import configure_logging
  configure_logging(settings.log_level)
  os.environ["CVING_MCP_PROCESS_READONLY"] = "1"
  # Legacy services import db_pool by both names; keep one bounded pool.
  from backend import db_pool
  sys.modules.setdefault("db_pool", db_pool)

  if args.transport == "stdio":
    settings.validate(transport="stdio")
    server = build_server()
    server.run(transport="stdio")
    return 0

  host = str(args.host or settings.host).strip()
  port = int(args.port or settings.port)
  path = str(args.path or settings.path).strip()
  effective = replace(settings, host=host, port=port, path=path if path.startswith("/") else f"/{path}")
  effective.validate_http_security()
  server = build_server(McpPriceActionService(effective))
  allowed_hosts = sorted({
    value
    for host_value in effective.allowed_hosts
    for value in (host_value, host_value if ":" in host_value else f"{host_value}:*")
  })
  app = server.streamable_http_app(
    streamable_http_path=effective.path,
    stateless_http=True,
    json_response=True,
    max_request_body_size=effective.max_request_body_size,
    transport_security=TransportSecuritySettings(
      enable_dns_rebinding_protection=False,
      allowed_hosts=allowed_hosts,
      allowed_origins=list(effective.allowed_origins),
    ),
    host=effective.host,
  )
  # Mount the consent page and route aliases when using built-in OAuth server.
  if effective.auth_mode == "oauth-server":
    from starlette.routing import Route
    from .oauth_provider import CvingOAuthProvider
    # The provider is already created inside build_server; retrieve it.
    provider = getattr(server, "_auth_server_provider", None)
    if isinstance(provider, CvingOAuthProvider):
      path, methods, handler = provider.consent_handler()
      app.routes.insert(0, Route(path, handler, methods=methods))

    # Add aliases for AS discovery and OAuth endpoints
    routes_by_path = {r.path: r for r in app.routes if hasattr(r, "path")}
    as_route = routes_by_path.get("/.well-known/oauth-authorization-server")
    if as_route:
      for alias_path in (
        "/.well-known/oauth-authorization-server/mcp",
        "/.well-known/openid-configuration",
        "/.well-known/openid-configuration/mcp",
        "/mcp/.well-known/openid-configuration",
      ):
        if alias_path not in routes_by_path:
          app.routes.append(Route(alias_path, as_route.endpoint, methods=list(as_route.methods or ["GET", "OPTIONS"])))

    for endpoint_name in ("/register", "/authorize", "/token", "/revoke"):
      route_obj = routes_by_path.get(endpoint_name)
      if route_obj:
        mcp_alias = f"/mcp{endpoint_name}"
        if mcp_alias not in routes_by_path:
          app.routes.append(Route(mcp_alias, route_obj.endpoint, methods=list(route_obj.methods or ["GET", "POST", "OPTIONS"])))
  secured_app = McpHttpSecurityMiddleware(app, effective)
  uvicorn.run(
    secured_app,
    host=effective.host,
    port=effective.port,
    log_level=effective.log_level.lower(),
    use_colors=False,
    access_log=False,
    proxy_headers=False,
    server_header=False,
  )
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
