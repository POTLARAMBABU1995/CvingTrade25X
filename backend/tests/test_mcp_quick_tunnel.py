from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from backend.mcp_server.config import McpSettings
from backend.mcp_server.quick_tunnel import (
  QuickTunnelSettings,
  build_mcp_url,
  mark_inactive,
  parse_trycloudflare_url,
  public_metadata,
  write_public_metadata,
)
from backend.mcp_server.security import McpHttpSecurityMiddleware


def _mcp_settings(**overrides) -> McpSettings:
  values = {
    "host": "127.0.0.1",
    "port": 1729,
    "path": "/mcp",
    "max_bars": 2000,
    "max_symbols": 500,
    "max_scan_results": 50,
    "scan_workers": 4,
    "cache_ttl_seconds": 0,
    "allow_remote": False,
    "bearer_token": "",
    "allowed_origins": (),
    "log_level": "INFO",
  }
  values.update(overrides)
  return McpSettings(**values)


def test_parses_actual_quick_tunnel_url_and_builds_mcp_endpoint():
  base = parse_trycloudflare_url("INF Your quick Tunnel has been created! Visit https://Blue-River.trycloudflare.com now")

  assert base == "https://blue-river.trycloudflare.com"
  assert build_mcp_url(base) == "https://blue-river.trycloudflare.com/mcp"


@pytest.mark.parametrize("value", [
  "https://trycloudflare.com",
  "http://unsafe.trycloudflare.com",
  "https://unsafe.trycloudflare.com.evil.example",
  "https://user:pass@unsafe.trycloudflare.com",
])
def test_rejects_malformed_quick_tunnel_urls(value: str):
  with pytest.raises(ValueError):
    if "trycloudflare.com.evil" in value or value.startswith("http") and "user:pass" not in value:
      parse_trycloudflare_url(value)
    else:
      build_mcp_url(value)


def test_quick_tunnel_origin_is_loopback_and_never_oracle(monkeypatch, tmp_path: Path):
  monkeypatch.setenv("CVING_QUICK_TUNNEL_ORIGIN", "http://127.0.0.1:1521")

  with pytest.raises(ValueError, match="1521"):
    QuickTunnelSettings.from_env(tmp_path)


def test_public_noauth_is_disabled_by_default(monkeypatch):
  monkeypatch.delenv("CVING_MCP_ALLOW_PUBLIC_NOAUTH_TEST", raising=False)
  settings = _mcp_settings(
    profile="secure-tunnel",
    auth_mode="none",
    public_base_url="https://safe.trycloudflare.com/mcp",
  )

  with pytest.raises(ValueError, match="reject"):
    settings.validate_http_security()


def test_legacy_public_noauth_override_is_rejected():
  settings = _mcp_settings(
    profile="secure-tunnel",
    auth_mode="none",
    public_base_url="https://safe.trycloudflare.com/mcp",
    allow_public_noauth_test=True,
  )

  with pytest.raises(ValueError, match="reject"):
    settings.validate_http_security()


def test_public_noauth_override_does_not_apply_to_remote_gateway():
  settings = _mcp_settings(
    profile="remote-gateway",
    auth_mode="none",
    public_base_url="https://mcp.example/mcp",
    allow_public_noauth_test=True,
  )

  with pytest.raises(ValueError, match="reject"):
    settings.validate_http_security()


def test_runtime_metadata_contains_public_state_only(monkeypatch, tmp_path: Path):
  monkeypatch.setenv("CVING_QUICK_TUNNEL_PUBLIC_URL_FILE", ".runtime/url.txt")
  monkeypatch.setenv("CVING_QUICK_TUNNEL_METADATA_FILE", ".runtime/endpoint.json")
  monkeypatch.setenv("CVING_QUICK_TUNNEL_PID_FILE", ".runtime/cloudflared.pid")
  monkeypatch.setenv("CVING_QUICK_TUNNEL_LOG_FILE", ".runtime/cloudflared.log")
  settings = QuickTunnelSettings.from_env(tmp_path)
  metadata = public_metadata(
    base_url="https://safe.trycloudflare.com",
    mcp_url="https://safe.trycloudflare.com/mcp",
    local_origin="http://127.0.0.1:1729",
    pid=123,
    cloudflared_path=str(tmp_path / "cloudflared.exe"),
    cloudflared_version="cloudflared test",
    authentication="bearer",
  )

  write_public_metadata(settings, metadata)
  serialized = settings.metadata_file.read_text(encoding="utf-8")
  pid_state = json.loads(settings.pid_file.read_text(encoding="utf-8"))

  assert "token" not in serialized.lower()
  assert "password" not in serialized.lower()
  assert pid_state["pid"] == 123
  assert settings.public_url_file.read_text(encoding="utf-8").strip().endswith("/mcp")

  mark_inactive(settings, reason="test")
  stopped = json.loads(settings.metadata_file.read_text(encoding="utf-8"))
  assert stopped["active"] is False
  assert not settings.pid_file.exists()
  assert not settings.public_url_file.exists()


def test_http_response_limit_fails_closed():
  settings = _mcp_settings(max_response_bytes=32)
  sent: list[dict] = []

  async def app(_scope, _receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"x" * 64})

  async def receive():
    return {"type": "http.request", "body": b"", "more_body": False}

  async def send(message):
    sent.append(message)

  middleware = McpHttpSecurityMiddleware(app, settings)
  scope = {
    "type": "http",
    "method": "POST",
    "path": "/mcp",
    "client": ("127.0.0.1", 5000),
    "headers": [(b"host", b"127.0.0.1:1729")],
  }
  asyncio.run(middleware(scope, receive, send))

  assert sent[0]["status"] == 507
