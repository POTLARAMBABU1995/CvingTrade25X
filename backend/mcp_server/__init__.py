"""Read-only MCP adapter for the existing CvingTrade25X services."""

from typing import Any

__all__ = ["build_server"]


def build_server(*args: Any, **kwargs: Any) -> Any:
  """Load the optional MCP SDK only when the MCP server is requested."""
  from .server import build_server as _build_server

  return _build_server(*args, **kwargs)
