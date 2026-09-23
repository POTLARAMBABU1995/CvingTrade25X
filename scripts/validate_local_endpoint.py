"""Backward-compatible entry point for validate_local_mcp.py."""

from validate_local_mcp import main


if __name__ == "__main__":
  raise SystemExit(main())
