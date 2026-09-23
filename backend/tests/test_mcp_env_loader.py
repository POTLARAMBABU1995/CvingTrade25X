from __future__ import annotations

import os

from backend.mcp_server.env_loader import load_local_mcp_env


def test_loads_only_mcp_values_and_preserves_process_environment(tmp_path, monkeypatch):
  env_file = tmp_path / ".env"
  env_file.write_text(
    "CVING_MCP_AUTH_MODE=bearer\n"
    "CVING_MCP_BEARER_TOKEN='file-secret-value'\n"
    "CVING_QUICK_TUNNEL_ENABLED=true\n"
    "ORACLE_PASSWORD=must-not-load\n",
    encoding="utf-8",
  )
  monkeypatch.setenv("CVING_MCP_AUTH_MODE", "oauth")
  monkeypatch.delenv("CVING_MCP_BEARER_TOKEN", raising=False)
  monkeypatch.delenv("CVING_QUICK_TUNNEL_ENABLED", raising=False)
  monkeypatch.delenv("ORACLE_PASSWORD", raising=False)

  loaded = load_local_mcp_env(tmp_path)

  assert os.environ["CVING_MCP_AUTH_MODE"] == "oauth"
  assert os.environ["CVING_MCP_BEARER_TOKEN"] == "file-secret-value"
  assert os.environ["CVING_QUICK_TUNNEL_ENABLED"] == "true"
  assert "ORACLE_PASSWORD" not in os.environ
  assert loaded == ("CVING_MCP_BEARER_TOKEN", "CVING_QUICK_TUNNEL_ENABLED")


def test_missing_env_file_is_a_noop(tmp_path):
  assert load_local_mcp_env(tmp_path) == ()
