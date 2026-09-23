from __future__ import annotations

import argparse
import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

import anyio

from mcp_endpoint_validation import EXPECTED_TOOLS, print_report, validate_endpoint


def main() -> int:
  parser = argparse.ArgumentParser(
    description="Validate DNS, TLS, authentication, MCP initialization, tools, and health"
  )
  parser.add_argument("--url", required=True, help="Public HTTPS MCP URL ending in /mcp")
  parser.add_argument("--token-env", default="CVING_MCP_BEARER_TOKEN")
  parser.add_argument("--auth-mode", choices=("bearer", "oauth"), default="bearer")
  parser.add_argument("--expected-tool-count", type=int, default=len(EXPECTED_TOOLS))
  parser.add_argument("--test-symbol")
  parser.add_argument(
    "--resolve-ip",
    help="Diagnostic only: preserve URL hostname/SNI but resolve it to this validated IP",
  )
  args = parser.parse_args()

  if args.resolve_ip:
    ipaddress.ip_address(args.resolve_ip)
    endpoint_host = urlparse(args.url).hostname
    if not endpoint_host:
      parser.error("--url must include a hostname")
    original_getaddrinfo = socket.getaddrinfo

    def fixed_getaddrinfo(host: str, *values: object, **options: object):
      return original_getaddrinfo(
        args.resolve_ip if host == endpoint_host else host,
        *values,
        **options,
      )

    async def fixed_loop_getaddrinfo(
      _loop: asyncio.BaseEventLoop,
      host: str,
      *values: object,
      **options: object,
    ):
      return fixed_getaddrinfo(host, *values, **options)

    socket.getaddrinfo = fixed_getaddrinfo
    asyncio.BaseEventLoop.getaddrinfo = fixed_loop_getaddrinfo
    original_connect_tcp = anyio.connect_tcp

    async def fixed_connect_tcp(*values: object, **options: object):
      if options.get("remote_host") == endpoint_host:
        options["remote_host"] = args.resolve_ip
      return await original_connect_tcp(*values, **options)

    anyio.connect_tcp = fixed_connect_tcp

  code, report = asyncio.run(validate_endpoint(
    url=args.url,
    auth_mode=args.auth_mode,
    token_env=args.token_env,
    symbol=args.test_symbol,
    run_analysis=False,
    remote=True,
  ))
  tools_check = report.get("checks", {}).get("tools_list", {})
  actual_count = len(tools_check.get("tools", [])) if isinstance(tools_check, dict) else 0
  report["expected_tool_count"] = args.expected_tool_count
  report["actual_tool_count"] = actual_count
  if args.resolve_ip:
    report["dns_resolution"] = {
      "mode": "diagnostic_override",
      "ip": args.resolve_ip,
      "note": "An explicit diagnostic resolution override was used; normal DNS was bypassed.",
    }
  if actual_count != args.expected_tool_count:
    report["status"] = "FAIL"
    report["tool_count_error"] = (
      f"Expected {args.expected_tool_count} tools but discovered {actual_count}"
    )
    code = 1
  print_report(report)
  return code


if __name__ == "__main__":
  raise SystemExit(main())
