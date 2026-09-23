from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from mcp import Client


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))

from backend.mcp_server.server import build_server  # noqa: E402


EXPECTED_TOOLS = {
  "health_check",
  "readiness_check",
  "list_symbols",
  "get_symbol_info",
  "get_latest_price",
  "get_ohlcv",
  "get_swing_points",
  "get_market_structure",
  "get_support_resistance",
  "get_price_zones",
  "get_breakout_status",
  "get_momentum",
  "analyze_symbol",
  "analyze_multi_timeframe",
  "explain_level",
  "scan_price_action",
}


async def validate() -> int:
  async with Client(build_server()) as client:
    listed = await client.list_tools()
    names = {tool.name for tool in listed.tools}
    missing = sorted(EXPECTED_TOOLS - names)
    if missing:
      print(json.dumps({"status": "FAIL", "missing_tools": missing}, indent=2))
      return 1
    result = await client.call_tool("health_check", {})
    print(json.dumps({
      "status": "PASS" if not result.is_error else "FAIL",
      "tools": sorted(names),
      "health": result.structured_content,
    }, indent=2, default=str))
    return 0 if not result.is_error else 1


if __name__ == "__main__":
  raise SystemExit(asyncio.run(validate()))
