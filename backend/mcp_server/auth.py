from __future__ import annotations

import asyncio
import base64
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from mcp.server.auth.provider import AccessToken, TokenVerifier

from .config import ALL_SCOPES, McpSettings


class StaticBearerVerifier(TokenVerifier):
  def __init__(self, settings: McpSettings):
    self.settings = settings

  async def verify_token(self, token: str) -> AccessToken | None:
    if not hmac.compare_digest(token, self.settings.bearer_token):
      return None
    return AccessToken(
      token=token,
      client_id="static-bearer-client",
      subject="static-bearer-client",
      scopes=list(ALL_SCOPES),
      resource=self.settings.resource_url,
    )


class OAuthIntrospectionVerifier(TokenVerifier):
  """Validate opaque or JWT access tokens through an external RFC 7662 endpoint."""

  def __init__(self, settings: McpSettings):
    self.settings = settings

  async def verify_token(self, token: str) -> AccessToken | None:
    try:
      payload = await asyncio.to_thread(self._introspect, token)
    except (OSError, ValueError, json.JSONDecodeError):
      return None
    if not payload.get("active"):
      return None
    now = int(time.time())
    try:
      expires_at = int(payload["exp"]) if payload.get("exp") is not None else None
    except (TypeError, ValueError):
      return None
    if expires_at is not None and expires_at <= now:
      return None
    issuer = str(payload.get("iss") or "").rstrip("/")
    if issuer != self.settings.oauth_issuer_url:
      return None
    audience = payload.get("aud") or payload.get("resource")
    audiences = {str(value) for value in audience} if isinstance(audience, list) else {str(audience or "")}
    expected_audience = self.settings.oauth_expected_audience or self.settings.resource_url
    if expected_audience and expected_audience not in audiences:
      return None
    raw_scopes = payload.get("scope") or payload.get("scp") or []
    scopes = raw_scopes.split() if isinstance(raw_scopes, str) else [str(value) for value in raw_scopes]
    scopes = [scope for scope in scopes if scope in ALL_SCOPES]
    if not scopes:
      return None
    subject = str(payload.get("sub") or payload.get("client_id") or "oauth-client")
    client_id = str(payload.get("client_id") or subject)
    return AccessToken(
      token=token,
      client_id=client_id,
      subject=subject,
      scopes=scopes,
      expires_at=expires_at,
      resource=expected_audience,
      claims={"iss": issuer, "aud": sorted(audiences)},
    )

  def _introspect(self, token: str) -> dict[str, Any]:
    body = urllib.parse.urlencode({"token": token, "token_type_hint": "access_token"}).encode("utf-8")
    credentials = f"{self.settings.oauth_client_id}:{self.settings.oauth_client_secret}".encode("utf-8")
    request = urllib.request.Request(
      self.settings.oauth_introspection_url,
      data=body,
      method="POST",
      headers={
        "Authorization": f"Basic {base64.b64encode(credentials).decode('ascii')}",
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "CvingTrade25X-MCP/2",
      },
    )
    try:
      # Config validation requires an explicit HTTPS introspection URL.
      with urllib.request.urlopen(  # nosec B310
        request,
        timeout=self.settings.tool_timeout_seconds,
      ) as response:
        if response.status != 200:
          return {}
        return json.loads(response.read(self.settings.max_response_bytes).decode("utf-8"))
    except urllib.error.HTTPError:
      return {}


def build_token_verifier(settings: McpSettings) -> TokenVerifier | None:
  if settings.auth_mode == "bearer":
    return StaticBearerVerifier(settings)
  if settings.auth_mode == "oauth":
    return OAuthIntrospectionVerifier(settings)
  return None
