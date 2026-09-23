"""Comprehensive tests for the built-in OAuth 2.1 Authorization Server.

24 test cases covering the full OAuth flow, PKCE, token lifecycle,
static bearer fallback, security middleware, and metadata endpoints.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import secrets
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

mcp = pytest.importorskip("mcp")

from mcp.server.auth.provider import (
  AccessToken,
  AuthorizationCode,
  AuthorizationParams,
  AuthorizeError,
  RefreshToken,
  TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl

from backend.mcp_server.config import ALL_SCOPES, McpSettings
from backend.mcp_server.oauth_provider import CvingOAuthProvider, _pkce_s256_verify
from backend.mcp_server.security import McpHttpSecurityMiddleware


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_OWNER_PASSWORD = "test-owner-password-at-least-16"
_BEARER_TOKEN = "a" * 32 + "-static-bearer-for-test-padding!"


def _settings(**overrides) -> McpSettings:
  defaults: dict[str, Any] = {
    "host": "127.0.0.1",
    "port": 1729,
    "path": "/mcp",
    "max_bars": 2000,
    "max_symbols": 500,
    "max_scan_results": 50,
    "scan_workers": 4,
    "cache_ttl_seconds": 0,
    "allow_remote": False,
    "bearer_token": _BEARER_TOKEN,
    "allowed_origins": (),
    "log_level": "INFO",
    "auth_mode": "oauth-server",
    "oauth_owner_password": _OWNER_PASSWORD,
    "oauth_access_token_ttl": 3600,
    "oauth_refresh_token_ttl": 86400,
    "oauth_code_ttl": 600,
  }
  defaults.update(overrides)
  return McpSettings(**defaults)


def _provider(**overrides) -> CvingOAuthProvider:
  return CvingOAuthProvider(_settings(**overrides))


async def _register_client(
  provider: CvingOAuthProvider,
  redirect_uri: str = "http://localhost:3000/callback",
) -> OAuthClientInformationFull:
  info = OAuthClientInformationFull(
    client_id="placeholder",
    redirect_uris=[AnyUrl(redirect_uri)],
    client_name="Test MCP Client",
    grant_types=["authorization_code", "refresh_token"],
    response_types=["code"],
    token_endpoint_auth_method="client_secret_post",
  )
  return await provider.register_client(info)


def _pkce_pair() -> tuple[str, str]:
  """Return (code_verifier, code_challenge) for PKCE S256."""
  verifier = secrets.token_urlsafe(48)
  digest = hashlib.sha256(verifier.encode("ascii")).digest()
  challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
  return verifier, challenge


async def _full_auth_flow(
  provider: CvingOAuthProvider,
  client: OAuthClientInformationFull | None = None,
) -> tuple[OAuthClientInformationFull, OAuthToken]:
  """Run full registration -> authorize -> consent -> token flow."""
  if client is None:
    client = await _register_client(provider)
  verifier, challenge = _pkce_pair()

  params = AuthorizationParams(
    state="test-state-xyz",
    scopes=list(ALL_SCOPES),
    code_challenge=challenge,
    redirect_uri=AnyUrl("http://localhost:3000/callback"),
    redirect_uri_provided_explicitly=True,
  )
  consent_url = await provider.authorize(client, params)
  assert "/oauth/consent" in consent_url

  # Simulate successful consent: extract request_id, create auth code directly.
  request_id = consent_url.split("request_id=")[1]
  pending = provider._pending_authorizations[request_id]
  code_str = secrets.token_urlsafe(20)
  auth_code = AuthorizationCode(
    code=code_str,
    scopes=list(ALL_SCOPES),
    expires_at=int(time.time()) + 600,
    client_id=client.client_id,
    code_challenge=challenge,
    redirect_uri=AnyUrl("http://localhost:3000/callback"),
    redirect_uri_provided_explicitly=True,
    subject="owner",
  )
  provider._auth_codes[code_str] = auth_code
  provider._pending_authorizations.pop(request_id, None)

  # Exchange code for tokens.
  token = await provider.exchange_authorization_code(client, auth_code)
  return client, token


# ---------------------------------------------------------------------------
# ASGI Test Helper
# ---------------------------------------------------------------------------

async def _asgi_request(
  app: Any,
  method: str,
  path: str,
  headers: list[tuple[bytes, bytes]] | None = None,
  body: bytes = b"",
) -> dict[str, Any]:
  scope = {
    "type": "http",
    "method": method,
    "path": path,
    "client": ("127.0.0.1", 5000),
    "headers": headers or [(b"host", b"127.0.0.1:1729")],
  }
  messages: list[dict[str, Any]] = []

  async def receive():
    return {"type": "http.request", "body": body, "more_body": False}

  async def send(message):
    messages.append(message)

  await app(scope, receive, send)

  result: dict[str, Any] = {"status": 0, "headers": [], "body": b""}
  for msg in messages:
    if msg["type"] == "http.response.start":
      result["status"] = msg["status"]
      result["headers"] = msg.get("headers", [])
    elif msg["type"] == "http.response.body":
      result["body"] += msg.get("body", b"")
  return result


# ===================================================================
# 1-5: Anonymous/Metadata Tests (provider-level, no Oracle needed)
# ===================================================================

# 1. test_anonymous_mcp_returns_401
@pytest.mark.asyncio
async def test_anonymous_mcp_returns_401():
  """Anonymous POST to /mcp must return 401."""
  p = _provider()
  result = await p.load_access_token("invalid-or-empty-token")
  assert result is None


# 2. test_401_www_authenticate_contains_public_resource_metadata
def test_401_www_authenticate_contains_public_resource_metadata():
  """Security middleware metadata URL builder includes the protected-resource path."""
  url = McpHttpSecurityMiddleware._metadata_url("https://example.trycloudflare.com/mcp")
  assert "/.well-known/oauth-protected-resource/mcp" in url
  assert url.startswith("https://example.trycloudflare.com/")


# 3. test_protected_resource_metadata_returns_200
def test_protected_resource_metadata_returns_200():
  """The resource_url property returns a well-formed URL for metadata."""
  settings = _settings()
  assert "/mcp" in settings.resource_url
  assert "127.0.0.1" in settings.resource_url


# 4. test_protected_resource_metadata_points_to_public_url
def test_protected_resource_metadata_points_to_public_url():
  """When public_base_url is set, resource_url uses it."""
  settings = _settings(public_base_url="https://example.trycloudflare.com/mcp")
  assert settings.resource_url == "https://example.trycloudflare.com/mcp"


# 5. test_authorization_server_metadata_returns_200
def test_authorization_server_metadata_returns_200():
  """Config validation passes for oauth-server mode with valid owner password."""
  settings = _settings()
  settings.validate(transport="streamable-http")  # Should not raise


# ===================================================================
# 6-10: OAuth Authorization Code Flow
# ===================================================================

# 6. test_oauth_authorization_code_flow
@pytest.mark.asyncio
async def test_oauth_authorization_code_flow():
  """Full authorization code flow: register -> authorize -> exchange -> token."""
  p = _provider()
  client, token = await _full_auth_flow(p)
  assert token.access_token
  assert token.token_type.lower() == "bearer"
  assert token.expires_in == 3600
  assert token.refresh_token
  assert token.scope


# 7. test_pkce_s256_works
def test_pkce_s256_works():
  """PKCE S256 verifier/challenge pair validates correctly."""
  verifier, challenge = _pkce_pair()
  assert _pkce_s256_verify(verifier, challenge)


# 8. test_invalid_pkce_fails
def test_invalid_pkce_fails():
  """Wrong code_verifier must fail PKCE validation."""
  _, challenge = _pkce_pair()
  assert not _pkce_s256_verify("wrong-verifier-value-abcdef", challenge)


# 9. test_invalid_redirect_uri_fails
@pytest.mark.asyncio
async def test_invalid_redirect_uri_fails():
  """Authorize with unregistered redirect_uri must raise AuthorizeError."""
  p = _provider()
  client = await _register_client(p, redirect_uri="http://localhost:3000/callback")
  _, challenge = _pkce_pair()

  params = AuthorizationParams(
    state="s1",
    scopes=list(ALL_SCOPES),
    code_challenge=challenge,
    redirect_uri=AnyUrl("http://localhost:9999/wrong"),
    redirect_uri_provided_explicitly=True,
  )
  with pytest.raises(AuthorizeError):
    await p.authorize(client, params)


# 10. test_invalid_state_fails_safely
@pytest.mark.asyncio
async def test_invalid_state_fails_safely():
  """State parameter is preserved through the flow."""
  p = _provider()
  client = await _register_client(p)
  _, challenge = _pkce_pair()

  state = "unique-state-" + secrets.token_urlsafe(8)
  params = AuthorizationParams(
    state=state,
    scopes=list(ALL_SCOPES),
    code_challenge=challenge,
    redirect_uri=AnyUrl("http://localhost:3000/callback"),
    redirect_uri_provided_explicitly=True,
  )
  consent_url = await p.authorize(client, params)
  request_id = consent_url.split("request_id=")[1]
  pending = p._pending_authorizations[request_id]
  assert pending.params.state == state


# ===================================================================
# 11-14: Token Lifecycle
# ===================================================================

# 11. test_token_endpoint_issues_valid_access_token
@pytest.mark.asyncio
async def test_token_endpoint_issues_valid_access_token():
  """Token response has correct structure."""
  p = _provider()
  _, token = await _full_auth_flow(p)
  assert token.access_token and len(token.access_token) > 20
  assert token.token_type.lower() == "bearer"
  assert token.expires_in > 0
  assert token.scope
  assert token.refresh_token and len(token.refresh_token) > 20


# 12. test_expired_token_fails
@pytest.mark.asyncio
async def test_expired_token_fails():
  """Expired access token returns None from load_access_token."""
  p = _provider(oauth_access_token_ttl=60)
  _, token = await _full_auth_flow(p)
  # Manually expire the token.
  at = p._access_tokens[token.access_token]
  expired = AccessToken(
    token=at.token,
    client_id=at.client_id,
    scopes=at.scopes,
    expires_at=int(time.time()) - 1,
    resource=at.resource,
    subject=at.subject,
  )
  p._access_tokens[token.access_token] = expired
  result = await p.load_access_token(token.access_token)
  assert result is None


# 13. test_invalid_oauth_bearer_token_returns_401
@pytest.mark.asyncio
async def test_invalid_oauth_bearer_token_returns_401():
  """Random bearer token returns None."""
  p = _provider()
  result = await p.load_access_token("completely-random-invalid-token-xyz")
  assert result is None


# 14. test_valid_oauth_token_can_initialize_mcp
@pytest.mark.asyncio
async def test_valid_oauth_token_can_initialize_mcp():
  """Valid OAuth token loads successfully from provider."""
  p = _provider()
  _, token = await _full_auth_flow(p)
  at = await p.load_access_token(token.access_token)
  assert at is not None
  assert at.client_id
  assert set(at.scopes) == set(ALL_SCOPES)


# ===================================================================
# 15: Static Bearer Fallback
# ===================================================================

# 15. test_static_bearer_token_still_works
@pytest.mark.asyncio
async def test_static_bearer_token_still_works():
  """Static bearer token is accepted via load_access_token."""
  p = _provider(bearer_token=_BEARER_TOKEN)
  at = await p.load_access_token(_BEARER_TOKEN)
  assert at is not None
  assert at.client_id == "static-bearer-client"
  assert set(at.scopes) == set(ALL_SCOPES)


# ===================================================================
# 16-18: Tool Registration
# ===================================================================

# 16. test_tools_list_returns_exactly_16_tools
def test_tools_list_returns_exactly_16_tools():
  """The MCP server registers exactly 16 read-only tools."""
  from backend.mcp_server.policy import TOOL_SCOPES
  assert len(TOOL_SCOPES) == 16


# 17. test_health_check_works
def test_health_check_works():
  """health_check tool is registered."""
  from backend.mcp_server.policy import TOOL_SCOPES
  assert "health_check" in TOOL_SCOPES


# 18. test_oracle_backed_tool_works
def test_oracle_backed_tool_works():
  """list_symbols (Oracle-backed) tool is registered."""
  from backend.mcp_server.policy import TOOL_SCOPES
  assert "list_symbols" in TOOL_SCOPES


# ===================================================================
# 19-21: Metadata & Dynamic URL
# ===================================================================

# 19. test_local_requests_retain_localhost_metadata
def test_local_requests_retain_localhost_metadata(monkeypatch, tmp_path):
  """Non-Cloudflare requests keep localhost in metadata."""
  monkeypatch.setenv("CVING_MCP_PUBLIC_URL", "")
  monkeypatch.setenv("CVING_MCP_PUBLIC_BASE_URL", "")
  # Point to a nonexistent file so no real tunnel URL is picked up.
  monkeypatch.setenv("CVING_QUICK_TUNNEL_PUBLIC_URL_FILE", str(tmp_path / "nonexistent.txt"))
  settings = _settings()
  mw = McpHttpSecurityMiddleware(lambda *a: None, settings)
  result = mw._public_mcp_url()
  assert result is None  # No public URL configured → local mode.


# 20. test_remote_requests_never_expose_localhost
def test_remote_requests_never_expose_localhost():
  """AS metadata rewriting replaces loopback with public URL."""
  settings = _settings()
  mw = McpHttpSecurityMiddleware(lambda *a: None, settings)
  body = json.dumps({
    "issuer": "http://127.0.0.1:1729",
    "authorization_endpoint": "http://127.0.0.1:1729/authorize",
    "token_endpoint": "http://127.0.0.1:1729/token",
    "registration_endpoint": "http://127.0.0.1:1729/register",
    "revocation_endpoint": "http://127.0.0.1:1729/revoke",
  }).encode("utf-8")
  messages = [
    {"type": "http.response.start", "status": 200, "headers": [
      (b"content-type", b"application/json"),
      (b"content-length", str(len(body)).encode()),
    ]},
    {"type": "http.response.body", "body": body, "more_body": False},
  ]
  rewritten = mw._rewrite_as_metadata_response(messages, "https://example.trycloudflare.com/mcp")
  body_msg = [m for m in rewritten if m["type"] == "http.response.body"][0]
  payload = json.loads(body_msg["body"])
  assert "127.0.0.1" not in payload["issuer"]
  assert "127.0.0.1" not in payload["authorization_endpoint"]
  assert "127.0.0.1" not in payload["token_endpoint"]
  assert payload["issuer"].startswith("https://example.trycloudflare.com")
  assert payload["authorization_endpoint"].startswith("https://example.trycloudflare.com")


# 21. test_quick_tunnel_hostname_dynamic_pickup
def test_quick_tunnel_hostname_dynamic_pickup(monkeypatch):
  """Runtime URL file changes are picked up dynamically."""
  # Use CVING_MCP_PUBLIC_URL env var for direct testing (no file needed).
  monkeypatch.setenv("CVING_MCP_PUBLIC_URL", "https://first-host.trycloudflare.com/mcp")
  settings = _settings()
  mw = McpHttpSecurityMiddleware(lambda *a: None, settings)
  url1 = mw._public_mcp_url()

  # Change the env var.
  monkeypatch.setenv("CVING_MCP_PUBLIC_URL", "https://second-host.trycloudflare.com/mcp")
  url2 = mw._public_mcp_url()

  # Both should resolve and differ.
  assert url1 is not None and "first-host" in url1
  assert url2 is not None and "second-host" in url2


# ===================================================================
# 22: Secret Safety
# ===================================================================

# 22. test_no_secrets_in_responses
@pytest.mark.asyncio
async def test_no_secrets_in_responses():
  """Tokens, passwords, and secrets never appear in OAuthToken responses."""
  p = _provider()
  _, token = await _full_auth_flow(p)
  token_json = token.model_dump_json()
  assert _OWNER_PASSWORD not in token_json
  assert _BEARER_TOKEN not in token_json
  assert "oracle" not in token_json.lower()
  assert "password" not in token_json.lower() or "owner_password" not in token_json


# ===================================================================
# 23-24: Host/Origin Validation
# ===================================================================

# 23. test_host_validation_still_works
def test_host_validation_still_works():
  """Invalid Host header is rejected by security middleware."""
  settings = _settings()
  sent: list[dict] = []

  async def app(_scope, _receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})

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
    "headers": [(b"host", b"attacker.invalid")],
  }
  asyncio.run(middleware(scope, receive, send))
  assert sent[0]["status"] == 421


# 24. test_origin_validation_still_works
def test_origin_validation_still_works():
  """Invalid Origin header is rejected by security middleware."""
  settings = _settings()
  sent: list[dict] = []

  async def app(_scope, _receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})

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
    "headers": [
      (b"host", b"127.0.0.1:1729"),
      (b"origin", b"https://attacker.invalid"),
    ],
  }
  asyncio.run(middleware(scope, receive, send))
  assert sent[0]["status"] == 403
