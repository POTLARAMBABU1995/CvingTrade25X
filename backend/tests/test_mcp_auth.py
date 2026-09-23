# ruff: noqa: E402 -- optional MCP dependency gate must run before MCP imports.
from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("mcp")

from mcp.server.auth.middleware.auth_context import AuthenticatedUser, auth_context_var
from mcp.server.auth.provider import AccessToken

from backend.mcp_server.auth import OAuthIntrospectionVerifier, StaticBearerVerifier
from backend.mcp_server.config import McpSettings
from backend.mcp_server.policy import authorize_tool


def _settings(**overrides) -> McpSettings:
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
    "bearer_token": "a" * 32,
    "allowed_origins": (),
    "log_level": "INFO",
    "auth_mode": "bearer",
  }
  values.update(overrides)
  return McpSettings(**values)


def test_remote_profile_rejects_anonymous_http():
  settings = _settings(
    profile="secure-tunnel",
    auth_mode="none",
    public_base_url="https://mcp.example/mcp",
  )

  try:
    settings.validate_http_security()
  except ValueError as exc:
    assert "reject" in str(exc).lower()
  else:
    raise AssertionError("anonymous remote profile must fail closed")


def test_static_bearer_uses_exact_token_and_read_scopes():
  verifier = StaticBearerVerifier(_settings())

  assert asyncio.run(verifier.verify_token("wrong")) is None
  access = asyncio.run(verifier.verify_token("a" * 32))

  assert access is not None
  assert "cving:market:read" in access.scopes
  assert all(":read" in scope or scope.endswith(":health") for scope in access.scopes)


def test_tool_scope_is_default_deny():
  settings = _settings()
  token = AccessToken(token="opaque", client_id="test", scopes=["cving:market:read"])
  context_token = auth_context_var.set(AuthenticatedUser(token))
  try:
    assert authorize_tool(settings, "get_ohlcv") is None
    denied = authorize_tool(settings, "analyze_symbol")
    assert denied and denied["error"]["code"] == "TOOL_DENIED"
    unknown = authorize_tool(settings, "execute_sql")
    assert unknown and unknown["error"]["code"] == "TOOL_DENIED"
  finally:
    auth_context_var.reset(context_token)


def test_oauth_introspection_rejects_wrong_audience(monkeypatch):
  settings = _settings(
    auth_mode="oauth",
    bearer_token="",
    oauth_issuer_url="https://id.example",
    oauth_resource_url="https://mcp.example/mcp",
    oauth_introspection_url="https://id.example/introspect",
    oauth_client_id="client",
    oauth_client_secret="secret",
  )
  verifier = OAuthIntrospectionVerifier(settings)
  monkeypatch.setattr(verifier, "_introspect", lambda _token: {
    "active": True,
    "client_id": "client",
    "scope": "cving:market:read",
    "iss": "https://id.example",
    "aud": "https://different.example/mcp",
  })

  assert asyncio.run(verifier.verify_token("opaque")) is None
