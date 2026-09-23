from __future__ import annotations

import asyncio
import json

from backend.mcp_server import security as security_module
from backend.mcp_server.config import McpSettings
from backend.mcp_server.security import McpHttpSecurityMiddleware


def _settings(**overrides) -> McpSettings:
  values = {
    "host": "127.0.0.1",
    "port": 1729,
    "path": "/mcp",
    "max_bars": 2000,
    "max_symbols": 500,
    "max_scan_results": 100,
    "scan_workers": 2,
    "cache_ttl_seconds": 0,
    "allow_remote": False,
    "bearer_token": "",
    "allowed_origins": (),
    "log_level": "INFO",
  }
  values.update(overrides)
  return McpSettings(**values)


def _request(settings: McpSettings, headers: list[tuple[bytes, bytes]]) -> tuple[bool, list[dict]]:
  called = False
  messages: list[dict] = []

  async def app(_scope, _receive, _send):
    nonlocal called
    called = True

  async def receive():
    return {"type": "http.request", "body": b"", "more_body": False}

  async def send(message):
    messages.append(message)

  middleware = McpHttpSecurityMiddleware(app, settings)
  scope = {"type": "http", "path": "/mcp", "headers": headers}
  asyncio.run(middleware(scope, receive, send))
  return called, messages


def _response_request(
  settings: McpSettings,
  *,
  path: str,
  headers: list[tuple[bytes, bytes]],
  status: int,
  response_headers: list[tuple[bytes, bytes]],
  body: bytes,
  client: tuple[str, int] = ("127.0.0.1", 5000),
) -> list[dict]:
  messages: list[dict] = []

  async def app(_scope, _receive, send):
    await send({"type": "http.response.start", "status": status, "headers": response_headers})
    await send({"type": "http.response.body", "body": body})

  async def receive():
    return {"type": "http.request", "body": b"", "more_body": False}

  async def send(message):
    messages.append(message)

  middleware = McpHttpSecurityMiddleware(app, settings)
  scope = {
    "type": "http",
    "method": "POST" if path == "/mcp" else "GET",
    "path": path,
    "headers": headers,
    "client": client,
  }
  asyncio.run(middleware(scope, receive, send))
  return messages


def _cloudflare_headers(*extra: tuple[bytes, bytes]) -> list[tuple[bytes, bytes]]:
  return [
    (b"host", b"127.0.0.1:1729"),
    (b"cf-ray", b"test-BOM"),
    (b"cf-connecting-ip", b"203.0.113.10"),
    (b"x-forwarded-proto", b"https"),
    *extra,
  ]


def test_loopback_rejects_untrusted_host_header():
  called, messages = _request(_settings(), [(b"host", b"attacker.example")])

  assert called is False
  assert messages[0]["status"] == 421


def test_remote_host_and_origin_are_fail_closed():
  settings = _settings(
    host="0.0.0.0",
    allow_remote=True,
    allowed_hosts=("mcp.example",),
    allowed_origins=("https://trusted.example",),
  )

  called, messages = _request(
    settings,
    [
      (b"host", b"mcp.example"),
      (b"origin", b"https://attacker.example"),
    ],
  )

  assert called is False
  assert messages[0]["status"] == 403


def test_valid_loopback_request_reaches_mcp_app():
  called, messages = _request(_settings(), [(b"host", b"127.0.0.1:1729")])

  assert called is True
  assert messages == []


def test_local_auth_challenge_keeps_local_metadata(monkeypatch):
  monkeypatch.setenv("CVING_MCP_PUBLIC_URL", "https://public.trycloudflare.com/mcp")
  messages = _response_request(
    _settings(),
    path="/mcp",
    headers=[(b"host", b"127.0.0.1:1729")],
    status=401,
    response_headers=[(
      b"www-authenticate",
      b'Bearer error="invalid_token", resource_metadata="http://127.0.0.1:1729/.well-known/oauth-protected-resource/mcp"',
    )],
    body=b'{"error":"invalid_token"}',
  )

  challenge = dict(messages[0]["headers"])[b"www-authenticate"].decode()
  assert "http://127.0.0.1:1729/.well-known/oauth-protected-resource/mcp" in challenge


def test_cloudflare_auth_challenge_uses_dynamic_public_metadata(monkeypatch):
  monkeypatch.setenv("CVING_MCP_PUBLIC_URL", "https://public.trycloudflare.com/mcp")
  messages = _response_request(
    _settings(),
    path="/mcp",
    headers=_cloudflare_headers(),
    status=401,
    response_headers=[(
      b"www-authenticate",
      b'Bearer error="invalid_token", resource_metadata="http://127.0.0.1:1729/.well-known/oauth-protected-resource/mcp"',
    )],
    body=b'{"error":"invalid_token"}',
  )

  challenge = dict(messages[0]["headers"])[b"www-authenticate"].decode()
  assert 'resource_metadata="https://public.trycloudflare.com/.well-known/oauth-protected-resource/mcp"' in challenge
  assert "127.0.0.1" not in challenge


def test_cloudflare_auth_challenge_reads_windows_bom_runtime_url(monkeypatch, tmp_path):
  monkeypatch.delenv("CVING_MCP_PUBLIC_URL", raising=False)
  monkeypatch.delenv("CVING_MCP_PUBLIC_BASE_URL", raising=False)
  monkeypatch.delenv("CVING_QUICK_TUNNEL_PUBLIC_URL_FILE", raising=False)
  runtime_url = tmp_path / "remote_mcp_url.txt"
  runtime_url.write_bytes(b"\xef\xbb\xbfhttps://bom-test.trycloudflare.com/mcp\r\n")
  monkeypatch.setattr(security_module, "_PROJECT_ROOT", tmp_path)
  monkeypatch.setattr(security_module, "_DEFAULT_PUBLIC_URL_FILE", runtime_url)
  messages = _response_request(
    _settings(),
    path="/mcp",
    headers=_cloudflare_headers(),
    status=401,
    response_headers=[(
      b"www-authenticate",
      b'Bearer error="invalid_token", resource_metadata="http://127.0.0.1:1729/.well-known/oauth-protected-resource/mcp"',
    )],
    body=b'{"error":"invalid_token"}',
  )

  challenge = dict(messages[0]["headers"])[b"www-authenticate"].decode()
  assert 'resource_metadata="https://bom-test.trycloudflare.com/.well-known/oauth-protected-resource/mcp"' in challenge


def test_cloudflare_metadata_document_uses_public_resource_and_no_secret(monkeypatch):
  monkeypatch.setenv("CVING_MCP_PUBLIC_URL", "https://public.trycloudflare.com/mcp")
  secret = "sensitive-bearer-value"
  body = json.dumps({
    "resource": "http://127.0.0.1:1729/mcp",
    "authorization_servers": ["http://127.0.0.1:1729/mcp"],
    "scopes_supported": [],
  }).encode()
  messages = _response_request(
    _settings(),
    path="/.well-known/oauth-protected-resource/mcp",
    headers=_cloudflare_headers((b"authorization", f"Bearer {secret}".encode())),
    status=200,
    response_headers=[(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
    body=body,
  )

  response_body = next(message["body"] for message in messages if message["type"] == "http.response.body")
  payload = json.loads(response_body)
  assert payload["resource"] == "https://public.trycloudflare.com/mcp"
  assert payload["authorization_servers"] == ["https://public.trycloudflare.com/mcp"]
  assert secret.encode() not in response_body


def test_cloudflare_dynamic_host_overrides_stale_runtime_url(monkeypatch, tmp_path):
  monkeypatch.delenv("CVING_MCP_PUBLIC_URL", raising=False)
  monkeypatch.delenv("CVING_MCP_PUBLIC_BASE_URL", raising=False)
  monkeypatch.delenv("CVING_QUICK_TUNNEL_PUBLIC_URL_FILE", raising=False)
  runtime_url = tmp_path / "remote_mcp_url.txt"
  runtime_url.write_text("https://old-stale-tunnel.trycloudflare.com/mcp\n", encoding="utf-8")
  monkeypatch.setattr(security_module, "_PROJECT_ROOT", tmp_path)
  monkeypatch.setattr(security_module, "_DEFAULT_PUBLIC_URL_FILE", runtime_url)

  messages = _response_request(
    _settings(),
    path="/mcp",
    headers=[
      (b"host", b"feb-trading-tools-jackie.trycloudflare.com"),
      (b"cf-ray", b"test-RAY-1"),
      (b"cf-connecting-ip", b"203.0.113.50"),
      (b"x-forwarded-proto", b"https"),
    ],
    status=401,
    response_headers=[(
      b"www-authenticate",
      b'Bearer error="invalid_token", resource_metadata="http://127.0.0.1:1729/.well-known/oauth-protected-resource/mcp"',
    )],
    body=b'{"error":"invalid_token"}',
  )

  challenge = dict(messages[0]["headers"])[b"www-authenticate"].decode()
  assert 'resource_metadata="https://feb-trading-tools-jackie.trycloudflare.com/.well-known/oauth-protected-resource/mcp"' in challenge
  assert "old-stale-tunnel" not in challenge
  assert "127.0.0.1" not in challenge


def test_cloudflare_dynamic_host_works_when_runtime_file_missing(monkeypatch, tmp_path):
  monkeypatch.delenv("CVING_MCP_PUBLIC_URL", raising=False)
  monkeypatch.delenv("CVING_MCP_PUBLIC_BASE_URL", raising=False)
  monkeypatch.delenv("CVING_QUICK_TUNNEL_PUBLIC_URL_FILE", raising=False)
  missing_file = tmp_path / "nonexistent" / "remote_mcp_url.txt"
  monkeypatch.setattr(security_module, "_PROJECT_ROOT", tmp_path)
  monkeypatch.setattr(security_module, "_DEFAULT_PUBLIC_URL_FILE", missing_file)

  messages = _response_request(
    _settings(),
    path="/mcp",
    headers=[
      (b"host", b"feb-trading-tools-jackie.trycloudflare.com"),
      (b"cf-ray", b"test-RAY-2"),
      (b"cf-connecting-ip", b"203.0.113.50"),
      (b"x-forwarded-proto", b"https"),
    ],
    status=401,
    response_headers=[(
      b"www-authenticate",
      b'Bearer error="invalid_token", resource_metadata="http://127.0.0.1:1729/.well-known/oauth-protected-resource/mcp"',
    )],
    body=b'{"error":"invalid_token"}',
  )

  challenge = dict(messages[0]["headers"])[b"www-authenticate"].decode()
  assert 'resource_metadata="https://feb-trading-tools-jackie.trycloudflare.com/.well-known/oauth-protected-resource/mcp"' in challenge


def test_cloudflare_oauth_as_metadata_dynamic_host_rewriting(monkeypatch, tmp_path):
  monkeypatch.delenv("CVING_MCP_PUBLIC_URL", raising=False)
  monkeypatch.delenv("CVING_MCP_PUBLIC_BASE_URL", raising=False)
  runtime_url = tmp_path / "remote_mcp_url.txt"
  runtime_url.write_text("https://old-stale-tunnel.trycloudflare.com/mcp\n", encoding="utf-8")
  monkeypatch.setattr(security_module, "_PROJECT_ROOT", tmp_path)
  monkeypatch.setattr(security_module, "_DEFAULT_PUBLIC_URL_FILE", runtime_url)

  as_metadata = json.dumps({
    "issuer": "http://127.0.0.1:1729",
    "authorization_endpoint": "http://127.0.0.1:1729/authorize",
    "token_endpoint": "http://127.0.0.1:1729/token",
    "registration_endpoint": "http://127.0.0.1:1729/register",
  }).encode()

  messages = _response_request(
    _settings(),
    path="/.well-known/oauth-authorization-server",
    headers=[
      (b"host", b"feb-trading-tools-jackie.trycloudflare.com"),
      (b"cf-ray", b"test-RAY-3"),
      (b"cf-connecting-ip", b"203.0.113.50"),
      (b"x-forwarded-proto", b"https"),
    ],
    status=200,
    response_headers=[(b"content-type", b"application/json"), (b"content-length", str(len(as_metadata)).encode())],
    body=as_metadata,
  )

  body_msg = next(m for m in messages if m["type"] == "http.response.body")
  payload = json.loads(body_msg["body"])
  assert payload["issuer"] == "https://feb-trading-tools-jackie.trycloudflare.com"
  assert payload["authorization_endpoint"] == "https://feb-trading-tools-jackie.trycloudflare.com/authorize"
  assert payload["token_endpoint"] == "https://feb-trading-tools-jackie.trycloudflare.com/token"
  assert payload["registration_endpoint"] == "https://feb-trading-tools-jackie.trycloudflare.com/register"
  assert "127.0.0.1" not in body_msg["body"].decode()

