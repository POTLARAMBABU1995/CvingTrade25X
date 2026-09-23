from __future__ import annotations

import argparse
import asyncio

from mcp_endpoint_validation import print_report, validate_endpoint


def main() -> int:
  parser = argparse.ArgumentParser(description="Validate a remote HTTPS CvingTrade25X MCP endpoint")
  parser.add_argument("--url", required=True)
  parser.add_argument("--auth-mode", choices=("none", "bearer", "oauth", "oauth-server"), default="bearer")
  parser.add_argument("--token-env", default="CVING_MCP_BEARER_TOKEN")
  parser.add_argument("--test-symbol")
  parser.add_argument("--analyze-symbol", action="store_true")
  args = parser.parse_args()
  code, report = asyncio.run(validate_endpoint(
    url=args.url,
    auth_mode=args.auth_mode,
    token_env=args.token_env,
    symbol=args.test_symbol,
    run_analysis=args.analyze_symbol,
    remote=True,
  ))
  print_report(report)
  return code


if __name__ == "__main__":
  raise SystemExit(main())
