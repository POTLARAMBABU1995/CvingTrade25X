"""Backward-compatible entry point for validate_remote_mcp.py."""

from validate_remote_mcp import main


if __name__ == "__main__":
  raise SystemExit(main())
