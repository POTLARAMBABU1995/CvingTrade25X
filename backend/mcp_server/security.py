from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import logging
import os
import re
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .config import McpSettings


_logger = logging.getLogger(__name__)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PUBLIC_URL_FILE = _PROJECT_ROOT / "runtime" / "mcp" / "remote_mcp_url.txt"
_RESOURCE_METADATA_PATTERN = re.compile(r'resource_metadata="[^"]*"', re.IGNORECASE)


class McpHttpSecurityMiddleware:
  """Fail-closed HTTP limits around the SDK's MCP/auth middleware."""

  def __init__(self, app: Callable[..., Awaitable[Any]], settings: McpSettings):
    self.app = app
    self.settings = settings
    self._active = 0
    self._active_lock = asyncio.Lock()
    self._request_times: dict[str, deque[float]] = defaultdict(deque)

  async def __call__(self, scope: dict[str, Any], receive: Callable[..., Any], send: Callable[..., Any]) -> None:
    request_path = str(scope.get("path") or "")
    metadata_path = f"/.well-known/oauth-protected-resource{self.settings.path}"
    as_metadata_paths = (
      "/.well-known/oauth-authorization-server",
      "/.well-known/oauth-authorization-server/mcp",
      "/.well-known/openid-configuration",
      "/.well-known/openid-configuration/mcp",
      "/mcp/.well-known/openid-configuration",
    )
    oauth_paths = (
      metadata_path,
      *as_metadata_paths,
      "/authorize",
      "/token",
      "/register",
      "/revoke",
      "/mcp/authorize",
      "/mcp/token",
      "/mcp/register",
      "/mcp/revoke",
      "/oauth/consent",
    )
    if scope.get("type") != "http":
      await self.app(scope, receive, send)
      return
    if request_path in {"/docs", "/redoc", "/openapi.json", "/admin", "/debug"}:
      await self._reject(send, 404, b"Not found")
      return
    if not (
      request_path in {"/health", "/live", "/ready", "/healthz", "/readyz"}
      or
      request_path.startswith(self.settings.path)
      or request_path in oauth_paths
      or any(request_path.startswith(p) for p in oauth_paths if p != metadata_path)
    ):
      await self.app(scope, receive, send)
      return

    headers = self._headers(scope)
    if not self._host_allowed(headers.get("host", "")):
      await self._reject(send, 421, b"Misdirected request")
      return
    origin = headers.get("origin", "")
    if origin and not self._origin_allowed(origin, headers):
      await self._reject(send, 403, b"Origin not allowed")
      return

    public_mcp_url = self._public_mcp_url(headers) if self._is_cloudflare_request(scope, headers) else None

    request_id = uuid.uuid4().hex
    identity = self._identity(scope, headers)
    peer = "peer:" + str((scope.get("client") or ("unknown",))[0])
    if not self._within_rate_limit(peer) or not self._within_rate_limit(identity):
      _logger.warning("mcp.audit", extra={"event": "RATE_LIMITED", "identity": identity})
      await self._reject(send, 429, b"Rate limit exceeded", extra_headers=[(b"retry-after", b"60")])
      return
    async with self._active_lock:
      if self._active >= self.settings.max_concurrent_requests:
        await self._reject(send, 503, b"MCP is at capacity", extra_headers=[(b"retry-after", b"1")])
        return
      self._active += 1

    response_bytes = 0
    response_started = False
    request_bytes = 0
    buffered_messages: list[dict[str, Any]] = []
    buffer_response = (
      str(scope.get("method") or "").upper() == "POST"
      or bool(public_mcp_url and (request_path == metadata_path or request_path in as_metadata_paths))
    )

    async def guarded_receive() -> dict[str, Any]:
      nonlocal request_bytes
      message = await receive()
      request_bytes += len(message.get("body", b""))
      if request_bytes > self.settings.max_request_body_size:
        raise _BodyTooLarge
      return message

    async def guarded_send(message: dict[str, Any]) -> None:
      nonlocal response_bytes, response_started
      if message.get("type") == "http.response.start":
        response_started = True
        existing = list(message.get("headers", []))
        if public_mcp_url:
          existing = self._rewrite_authenticate_headers(existing, public_mcp_url)
        existing.append((b"x-request-id", request_id.encode("ascii")))
        existing.extend([(b"cache-control", b"no-store"), (b"x-content-type-options", b"nosniff")])
        message = {**message, "headers": existing}
      elif message.get("type") == "http.response.body":
        response_bytes += len(message.get("body", b""))
        if response_bytes > self.settings.max_response_bytes:
          raise _ResponseTooLarge
      if buffer_response:
        buffered_messages.append(message)
      else:
        await send(message)

    started = time.perf_counter()
    try:
      await asyncio.wait_for(self.app(scope, guarded_receive, guarded_send),
                             timeout=self.settings.request_timeout_seconds)
      if public_mcp_url and request_path == metadata_path:
        buffered_messages = self._rewrite_metadata_response(buffered_messages, public_mcp_url)
      elif public_mcp_url and request_path in as_metadata_paths:
        buffered_messages = self._rewrite_as_metadata_response(buffered_messages, public_mcp_url)
      for message in buffered_messages:
        await send(message)
    except asyncio.TimeoutError:
      if not response_started or buffer_response:
        await self._reject(send, 504, b"MCP request timed out")
    except _BodyTooLarge:
      if not response_started or buffer_response:
        await self._reject(send, 413, b"Request body too large")
    except _ResponseTooLarge:
      _logger.warning("mcp.response_limit", extra={"identity": identity})
      if not response_started or buffer_response:
        await self._reject(send, 507, b"Response exceeds configured limit")
    except Exception:
      _logger.error("mcp.request_failed", extra={"request_id": request_id})
      if not response_started or buffer_response:
        await self._reject(send, 500, b"MCP request failed")
    finally:
      async with self._active_lock:
        self._active -= 1
      _logger.info("mcp.audit", extra={
        "event": "MCP_CONNECTION",
        "request_id": request_id,
        "identity": identity,
        "transport": "streamable-http",
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
      })

  @staticmethod
  def _headers(scope: dict[str, Any]) -> dict[str, str]:
    return {key.decode("latin-1").lower(): value.decode("latin-1") for key, value in scope.get("headers", [])}

  def _host_allowed(self, host_header: str) -> bool:
    host = host_header.strip().lower()
    if not host:
      return False
    hostname = host
    if host.startswith("[") and "]" in host:
      hostname = host[: host.find("]") + 1]
    elif host.count(":") == 1:
      hostname = host.rsplit(":", 1)[0]
    allowed = {item.lower() for item in self.settings.allowed_hosts}
    if host in allowed or hostname in allowed:
      return True
    if hostname.endswith(".trycloudflare.com"):
      return True
    if self._is_allowed_public_domain(hostname):
      return True
    return False

  def _origin_allowed(self, origin_header: str, headers: dict[str, str]) -> bool:
    origin = origin_header.strip().lower()
    if not origin:
      return True
    allowed = {item.lower() for item in self.settings.allowed_origins}
    if origin in allowed:
      return True

    parsed_origin = urlparse(origin)
    origin_host = (parsed_origin.hostname or "").lower()
    if not origin_host:
      return False

    # Only the validated Host may establish same-origin; forwarded headers are
    # client-controlled and must never grant an Origin permission.
    req_host = headers.get("host", "").strip().lower()
    if parsed_origin.scheme == "https" and parsed_origin.netloc == req_host and self._host_allowed(req_host):
      return True
    return False

  def _is_allowed_public_domain(self, hostname: str) -> bool:
    clean = hostname.strip().lower()
    if not clean or clean in {"localhost", "127.0.0.1", "::1", "[::1]"}:
      return False
    for allowed in self.settings.allowed_hosts:
      allowed_clean = allowed.lower().split(":")[0]
      if allowed_clean not in {"localhost", "127.0.0.1", "::1", "[::1]"} and clean == allowed_clean:
        return True
    if clean == str(os.getenv("CVING_MCP_PUBLIC_HOST", "")).strip().lower():
      return True
    for candidate_url in (
      self.settings.public_base_url,
      self.settings.oauth_resource_url,
      str(os.getenv("CVING_MCP_PUBLIC_URL", "")).strip(),
      str(os.getenv("CVING_MCP_PUBLIC_BASE_URL", "")).strip(),
    ):
      if candidate_url:
        cand_host = (urlparse(candidate_url).hostname or "").lower()
        if cand_host and clean == cand_host:
          return True
    return False

  def _public_mcp_url(self, headers: dict[str, str] | None = None) -> str | None:
    dynamic_host: str | None = None
    if headers:
      raw_host = (headers.get("host") or headers.get("x-forwarded-host") or "").strip().lower()
      if raw_host:
        h = raw_host
        if h.startswith("[") and "]" in h:
          cand_h = h[: h.find("]") + 1]
        elif ":" in h:
          cand_h = h.split(":", 1)[0]
        else:
          cand_h = h
        if cand_h.endswith(".trycloudflare.com") or self._is_allowed_public_domain(cand_h):
          dynamic_host = cand_h

    configured = str(os.getenv("CVING_MCP_PUBLIC_URL", "")).strip()
    if not configured:
      configured = str(os.getenv("CVING_MCP_PUBLIC_BASE_URL", "")).strip()
    if not configured:
      raw_path = str(os.getenv("CVING_QUICK_TUNNEL_PUBLIC_URL_FILE", "")).strip()
      candidate = Path(raw_path) if raw_path else _DEFAULT_PUBLIC_URL_FILE
      if not candidate.is_absolute():
        candidate = _PROJECT_ROOT / candidate
      try:
        candidate = candidate.resolve(strict=False)
        candidate.relative_to(_PROJECT_ROOT.resolve(strict=False))
        configured = candidate.read_text(encoding="utf-8").lstrip("\ufeff").strip()
      except (OSError, ValueError):
        configured = ""

    file_mcp_url: str | None = None
    if configured:
      parsed = urlparse(configured)
      if (
        parsed.scheme == "https"
        and parsed.hostname
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
      ):
        path = parsed.path.rstrip("/")
        if not path or path == self.settings.path:
          file_mcp_url = f"https://{parsed.netloc}{self.settings.path}"

    if dynamic_host:
      dynamic_url = f"https://{dynamic_host}{self.settings.path}"
      if not file_mcp_url:
        return dynamic_url
      file_host = (urlparse(file_mcp_url).hostname or "").lower()
      if file_host != dynamic_host:
        return dynamic_url
      return file_mcp_url

    return file_mcp_url

  @staticmethod
  def _is_cloudflare_request(scope: dict[str, Any], headers: dict[str, str]) -> bool:
    del scope
    return bool(headers.get("cf-ray") and headers.get("cf-connecting-ip"))

  def _rewrite_authenticate_headers(
    self,
    headers: list[tuple[bytes, bytes]],
    public_mcp_url: str,
  ) -> list[tuple[bytes, bytes]]:
    metadata_url = self._metadata_url(public_mcp_url)
    rewritten: list[tuple[bytes, bytes]] = []
    for key, value in headers:
      if key.lower() != b"www-authenticate":
        rewritten.append((key, value))
        continue
      decoded = value.decode("latin-1")
      if _RESOURCE_METADATA_PATTERN.search(decoded):
        decoded = _RESOURCE_METADATA_PATTERN.sub(f'resource_metadata="{metadata_url}"', decoded)
      rewritten.append((key, decoded.encode("latin-1")))
    return rewritten

  def _rewrite_metadata_response(
    self,
    messages: list[dict[str, Any]],
    public_mcp_url: str,
  ) -> list[dict[str, Any]]:
    body_messages = [message for message in messages if message.get("type") == "http.response.body"]
    if not body_messages:
      return messages
    raw_body = b"".join(message.get("body", b"") for message in body_messages)
    try:
      payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
      return messages
    if not isinstance(payload, dict):
      return messages
    payload["resource"] = public_mcp_url
    parsed_pub = urlparse(public_mcp_url)
    public_base = f"{parsed_pub.scheme}://{parsed_pub.netloc}"
    authorization_servers = payload.get("authorization_servers")
    if isinstance(authorization_servers, list):
      rewritten_as: list[str] = []
      for value in authorization_servers:
        if self._is_loopback_url(str(value)):
          old_path = urlparse(str(value)).path.rstrip("/")
          rewritten_as.append(f"{public_base}{old_path}" if old_path else public_base)
        else:
          rewritten_as.append(value)
      payload["authorization_servers"] = rewritten_as
    rewritten_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    rewritten: list[dict[str, Any]] = []
    body_written = False
    for message in messages:
      if message.get("type") == "http.response.start":
        headers = [
          (key, str(len(rewritten_body)).encode("ascii")) if key.lower() == b"content-length" else (key, value)
          for key, value in message.get("headers", [])
        ]
        rewritten.append({**message, "headers": headers})
      elif message.get("type") == "http.response.body":
        if not body_written:
          rewritten.append({**message, "body": rewritten_body, "more_body": False})
          body_written = True
      else:
        rewritten.append(message)
    return rewritten

  @staticmethod
  def _metadata_url(public_mcp_url: str) -> str:
    parsed = urlparse(public_mcp_url)
    return f"{parsed.scheme}://{parsed.netloc}/.well-known/oauth-protected-resource{parsed.path}"

  @staticmethod
  def _is_loopback_url(value: str) -> bool:
    try:
      return (urlparse(value).hostname or "").lower() in {"127.0.0.1", "localhost", "::1"}
    except ValueError:
      return False

  def _rewrite_as_metadata_response(
    self,
    messages: list[dict[str, Any]],
    public_mcp_url: str,
  ) -> list[dict[str, Any]]:
    """Rewrite OAuth Authorization Server metadata for Cloudflare/remote requests."""
    body_messages = [m for m in messages if m.get("type") == "http.response.body"]
    if not body_messages:
      return messages
    raw_body = b"".join(m.get("body", b"") for m in body_messages)
    try:
      payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
      return messages
    if not isinstance(payload, dict):
      return messages
    parsed = urlparse(public_mcp_url)
    public_base = f"{parsed.scheme}://{parsed.netloc}"
    # Rewrite all URL fields that point to loopback.
    url_fields = (
      "issuer", "authorization_endpoint", "token_endpoint",
      "registration_endpoint", "revocation_endpoint", "jwks_uri",
      "resource_server_url",
    )
    for field in url_fields:
      if field in payload and isinstance(payload[field], str) and self._is_loopback_url(payload[field]):
        old_parsed = urlparse(payload[field])
        payload[field] = f"{public_base}{old_parsed.path}"
    rewritten_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    rewritten: list[dict[str, Any]] = []
    body_written = False
    for message in messages:
      if message.get("type") == "http.response.start":
        headers = [
          (key, str(len(rewritten_body)).encode("ascii")) if key.lower() == b"content-length" else (key, value)
          for key, value in message.get("headers", [])
        ]
        rewritten.append({**message, "headers": headers})
      elif message.get("type") == "http.response.body":
        if not body_written:
          rewritten.append({**message, "body": rewritten_body, "more_body": False})
          body_written = True
      else:
        rewritten.append(message)
    return rewritten

  def _identity(self, scope: dict[str, Any], headers: dict[str, str]) -> str:
    client_host = str((scope.get("client") or ("unknown",))[0])
    if self.settings.trust_proxy and self._trusted_proxy(client_host):
      forwarded = headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
      if forwarded:
        client_host = forwarded
    authorization = headers.get("authorization", "")
    if authorization:
      digest = hashlib.sha256(authorization.encode("utf-8")).hexdigest()[:16]
      return f"token:{digest}"
    return f"ip:{client_host}"

  def _trusted_proxy(self, host: str) -> bool:
    try:
      address = ipaddress.ip_address(host)
      return any(address in ipaddress.ip_network(network, strict=False) for network in self.settings.trusted_proxies)
    except ValueError:
      return False

  def _within_rate_limit(self, identity: str) -> bool:
    now = time.monotonic()
    # Bound identities even when attackers rotate invalid authorization headers.
    if len(self._request_times) >= 2048:
      stale = [key for key, values in self._request_times.items() if not values or now - values[-1] >= 60]
      for key in stale:
        del self._request_times[key]
      if identity not in self._request_times and len(self._request_times) >= 2048:
        return False
    queue = self._request_times[identity]
    while queue and now - queue[0] >= 60:
      queue.popleft()
    if len(queue) >= self.settings.rate_limit_per_minute:
      return False
    queue.append(now)
    return True

  @staticmethod
  async def _reject(
    send: Callable[..., Any],
    status: int,
    body: bytes,
    *,
    extra_headers: list[tuple[bytes, bytes]] | None = None,
  ) -> None:
    headers = [
      (b"content-type", b"text/plain; charset=utf-8"),
      (b"cache-control", b"no-store"),
      (b"x-content-type-options", b"nosniff"),
    ]
    headers.extend(extra_headers or [])
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class _BodyTooLarge(Exception):
  pass


class _ResponseTooLarge(Exception):
  pass
