from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.context import CallNext, HandlerResult, ServerRequestContext

from .config import McpSettings
from .errors import McpServiceError


_logger = logging.getLogger(__name__)

TOOL_SCOPES = {
  "health_check": "cving:admin:health",
  "readiness_check": "cving:admin:health",
  "list_symbols": "cving:market:read",
  "get_symbol_info": "cving:market:read",
  "get_latest_price": "cving:market:read",
  "get_ohlcv": "cving:market:read",
  "get_swing_points": "cving:analysis:read",
  "get_market_structure": "cving:analysis:read",
  "get_support_resistance": "cving:analysis:read",
  "get_price_zones": "cving:analysis:read",
  "get_breakout_status": "cving:analysis:read",
  "get_momentum": "cving:analysis:read",
  "analyze_symbol": "cving:analysis:read",
  "analyze_multi_timeframe": "cving:analysis:read",
  "explain_level": "cving:analysis:read",
  "scan_price_action": "cving:scan:read",
}


def authorize_tool(settings: McpSettings, tool_name: str) -> dict[str, Any] | None:
  if settings.allowed_tools and tool_name not in settings.allowed_tools:
    return McpServiceError("TOOL_DENIED", "This tool is disabled by server policy.").to_payload()
  if settings.auth_mode == "none":
    return None
  access_token = get_access_token()
  required = TOOL_SCOPES.get(tool_name)
  if access_token is None or required is None or required not in access_token.scopes:
    return McpServiceError("TOOL_DENIED", f"Required scope: {required or 'unknown'}").to_payload()
  return None


class McpAuditTimeoutMiddleware:
  def __init__(self, settings: McpSettings):
    self.settings = settings

  async def __call__(self, ctx: ServerRequestContext[Any, Any], call_next: CallNext) -> HandlerResult:
    started = time.perf_counter()
    params = dict(ctx.params or {})
    tool_name = str(params.get("name") or "") if ctx.method == "tools/call" else ""
    token = get_access_token()
    subject = token.subject if token else "local-anonymous"
    status = "OK"
    try:
      return await asyncio.wait_for(call_next(ctx), timeout=self.settings.tool_timeout_seconds)
    except TimeoutError:
      status = "TIMEOUT"
      raise
    except Exception:
      status = "ERROR"
      raise
    finally:
      _logger.info("mcp.audit", extra={
        "event": "TOOL_CALL" if tool_name else "MCP_CONNECTION",
        "request_id": str(ctx.request_id or ""),
        "authenticated_subject": subject,
        "auth_mode": self.settings.auth_mode,
        "tool_name": tool_name,
        "status": status,
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        "transport": "mcp",
        "mcp_protocol_version": ctx.protocol_version,
      })
