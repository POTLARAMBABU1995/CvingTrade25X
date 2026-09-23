from __future__ import annotations

import argparse
import asyncio

from mcp_endpoint_validation import print_report, validate_endpoint


def main() -> int:
  parser = argparse.ArgumentParser(description="Validate the local CvingTrade25X Streamable HTTP MCP endpoint")
  parser.add_argument("--url", default="http://127.0.0.1:1729/mcp")
  parser.add_argument("--auth-mode", choices=("none", "bearer", "oauth", "oauth-server"), default="none")
  parser.add_argument("--token-env", default="CVING_MCP_BEARER_TOKEN")
  parser.add_argument("--test-symbol")
  args = parser.parse_args()
  code, report = asyncio.run(validate_endpoint(
    url=args.url,
    auth_mode=args.auth_mode,
    token_env=args.token_env,
    symbol=args.test_symbol,
    run_analysis=False,
    remote=False,
    check_local_security=True,
  ))
  print_report(report)
  return code


if __name__ == "__main__":
  raise SystemExit(main())
