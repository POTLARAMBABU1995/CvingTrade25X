# ruff: noqa: E402 -- optional MCP dependency gate must run before MCP imports.
from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("mcp")

from mcp import Client

from backend.mcp_server.config import McpSettings
from backend.mcp_server.server import build_server
from backend.mcp_server.service import McpPriceActionService


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


def test_mcp_lists_only_explicit_read_only_tools(monkeypatch):
  settings = McpSettings(
    host="127.0.0.1",
    port=1729,
    path="/mcp",
    max_bars=2000,
    max_symbols=500,
    max_scan_results=100,
    scan_workers=2,
    cache_ttl_seconds=0,
    allow_remote=False,
    bearer_token="",
    allowed_origins=(),
    log_level="INFO",
  )
  service = McpPriceActionService(settings)
  monkeypatch.setattr(service, "health_check", lambda: {"status": "OK", "read_only": True})

  async def run_contract():
    async with Client(build_server(service)) as client:
      listed = await client.list_tools()
      tools = {tool.name: tool for tool in listed.tools}
      result = await client.call_tool("health_check", {})
      return tools, result

  tools, result = asyncio.run(run_contract())

  assert set(tools) == EXPECTED_TOOLS
  assert "execute_sql" not in tools
  assert all(tool.annotations and tool.annotations.read_only_hint for tool in tools.values())
  assert result.is_error is False
  assert result.structured_content == {"status": "OK", "read_only": True}
