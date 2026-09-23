"""Built-in OAuth 2.1 Authorization Server for standards-compliant MCP client access.

Implements the ``OAuthAuthorizationServerProvider`` protocol from the MCP Python SDK,
providing Authorization Code + PKCE (S256), Dynamic Client Registration (RFC 7591),
token issuance/refresh/revocation, and a minimal owner consent screen.

This is a single-owner personal authorization server suitable for developer MCP
endpoints. Multi-user enterprise deployments should use the external ``oauth``
mode with a proper IdP (Keycloak, Auth0, Entra, etc.).

Secrets are never logged, serialized to metadata, or returned in API responses.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import logging
import secrets
import time
from typing import Any
from urllib.parse import urlencode, urlparse

from mcp.server.auth.provider import (
  AccessToken,
  AuthorizationCode,
  AuthorizationParams,
  AuthorizeError,
  IdentityAssertionParams,
  OAuthAuthorizationServerProvider,
  RefreshToken,
  RegistrationError,
  TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from .config import ALL_SCOPES, McpSettings


_logger = logging.getLogger(__name__)

# Minimum entropy: 160 bits = 20 bytes → 40 hex chars for codes/tokens.
_CODE_BYTES = 20
_TOKEN_BYTES = 32


def _now() -> int:
  return int(time.time())


def _secure_token(n_bytes: int = _TOKEN_BYTES) -> str:
  return secrets.token_urlsafe(n_bytes)


def _pkce_s256_verify(code_verifier: str, code_challenge: str) -> bool:
  """Verify PKCE S256: BASE64URL(SHA256(code_verifier)) == code_challenge."""
  import base64
  digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
  expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
  return hmac.compare_digest(expected, code_challenge)


class CvingOAuthProvider(OAuthAuthorizationServerProvider[
  OAuthClientInformationFull,
  AuthorizationCode,
  AccessToken,
]):
  """In-memory OAuth 2.1 Authorization Server for CvingTrade25X MCP.

  Stores clients, authorization codes, access tokens, and refresh tokens
  in memory. State is lost on process restart — this is standard for
  MCP servers using Dynamic Client Registration.
  """

  def __init__(self, settings: McpSettings) -> None:
    self.settings = settings
    # In-memory stores keyed by ID/token string.
    self._clients: dict[str, OAuthClientInformationFull] = {}
    self._auth_codes: dict[str, AuthorizationCode] = {}
    self._access_tokens: dict[str, AccessToken] = {}
    self._refresh_tokens: dict[str, RefreshToken] = {}
    # Map pending authorization requests to their params.
    self._pending_authorizations: dict[str, _PendingAuth] = {}
    # Track used auth codes to prevent replay.
    self._used_codes: set[str] = set()

  # --- Dynamic Client Registration (RFC 7591) ---

  async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
    return self._clients.get(client_id)

  async def register_client(
    self, client_info: OAuthClientInformationFull,
  ) -> OAuthClientInformationFull:
    # Validate redirect URIs — each must be a valid absolute HTTPS URL
    # (or http://localhost for development clients per OAuth 2.1).
    if not client_info.redirect_uris:
      raise RegistrationError(
        error="invalid_redirect_uri",
        error_description="At least one redirect_uri is required",
      )
    for uri in client_info.redirect_uris:
      parsed = urlparse(str(uri))
      if parsed.scheme == "https":
        continue
      if parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "[::1]"}:
        continue
      # Allow custom URI schemes for native apps (e.g. com.example.app:/callback)
      if ":" in parsed.scheme and not parsed.scheme.startswith("http"):
        continue
      raise RegistrationError(
        error="invalid_redirect_uri",
        error_description=f"redirect_uri must use HTTPS or localhost HTTP: {uri}",
      )

    # Assign client credentials if not already assigned by the DCR handler.
    client_id = client_info.client_id or f"cving-mcp-{secrets.token_urlsafe(16)}"
    client_secret = client_info.client_secret or _secure_token(32)
    registered = OAuthClientInformationFull(
      client_id=client_id,
      client_secret=client_secret,
      client_id_issued_at=client_info.client_id_issued_at or _now(),
      client_secret_expires_at=client_info.client_secret_expires_at or 0,
      redirect_uris=client_info.redirect_uris,
      client_name=client_info.client_name or "MCP Client",
      grant_types=client_info.grant_types or ["authorization_code", "refresh_token"],
      response_types=client_info.response_types or ["code"],
      token_endpoint_auth_method=client_info.token_endpoint_auth_method or "client_secret_post",
      scope=client_info.scope or " ".join(ALL_SCOPES),
    )
    self._clients[client_id] = registered
    _logger.info("mcp.oauth", extra={
      "event": "CLIENT_REGISTERED",
      "client_id": client_id,
      "client_name": registered.client_name,
    })
    return registered

  # --- Authorization Endpoint ---

  async def authorize(
    self,
    client: OAuthClientInformationFull,
    params: AuthorizationParams,
  ) -> str:
    """Store the authorization request and redirect to the consent screen."""
    if not params.code_challenge:
      raise AuthorizeError(
        error="invalid_request",
        error_description="PKCE code_challenge is required (S256)",
      )

    # Validate redirect_uri matches a registered URI.
    redirect_str = str(params.redirect_uri)
    registered_uris = [str(u) for u in (client.redirect_uris or [])]
    if redirect_str not in registered_uris:
      raise AuthorizeError(
        error="invalid_request",
        error_description="redirect_uri does not match any registered URI",
      )

    # Validate requested scopes.
    requested_scopes = params.scopes or list(ALL_SCOPES)
    valid_scopes = [s for s in requested_scopes if s in ALL_SCOPES]
    if not valid_scopes:
      raise AuthorizeError(
        error="invalid_scope",
        error_description=f"No valid scopes requested. Available: {', '.join(ALL_SCOPES)}",
      )

    # Store pending authorization.
    request_id = _secure_token(16)
    self._pending_authorizations[request_id] = _PendingAuth(
      client_id=client.client_id,
      params=params,
      scopes=valid_scopes,
      created_at=_now(),
    )

    # Return URL for the consent page. The SDK will redirect the client here.
    return f"/oauth/consent?request_id={request_id}"

  # --- Authorization Code Management ---

  async def load_authorization_code(
    self,
    client: OAuthClientInformationFull,
    authorization_code: str,
  ) -> AuthorizationCode | None:
    code_obj = self._auth_codes.get(authorization_code)
    if code_obj is None:
      return None
    if code_obj.client_id != client.client_id:
      return None
    if authorization_code in self._used_codes:
      return None
    if code_obj.expires_at < _now():
      self._auth_codes.pop(authorization_code, None)
      return None
    return code_obj

  async def exchange_authorization_code(
    self,
    client: OAuthClientInformationFull,
    authorization_code: AuthorizationCode,
  ) -> OAuthToken:
    code_str = authorization_code.code

    # Mark code as used (single-use enforcement).
    if code_str in self._used_codes:
      raise TokenError(error="invalid_grant", error_description="Authorization code already used")
    self._used_codes.add(code_str)
    self._auth_codes.pop(code_str, None)

    # Issue tokens.
    scopes = authorization_code.scopes or list(ALL_SCOPES)
    resource = str(authorization_code.resource) if authorization_code.resource else self.settings.resource_url
    access_token_str = _secure_token()
    refresh_token_str = _secure_token()
    now = _now()

    access_token = AccessToken(
      token=access_token_str,
      client_id=client.client_id,
      scopes=scopes,
      expires_at=now + self.settings.oauth_access_token_ttl,
      resource=resource,
      subject=authorization_code.subject or "owner",
    )
    refresh_token = RefreshToken(
      token=refresh_token_str,
      client_id=client.client_id,
      scopes=scopes,
      expires_at=now + self.settings.oauth_refresh_token_ttl,
      resource=resource,
      subject=authorization_code.subject or "owner",
    )

    self._access_tokens[access_token_str] = access_token
    self._refresh_tokens[refresh_token_str] = refresh_token

    _logger.info("mcp.oauth", extra={
      "event": "TOKEN_ISSUED",
      "client_id": client.client_id,
      "grant_type": "authorization_code",
      "scopes": scopes,
    })

    return OAuthToken(
      access_token=access_token_str,
      token_type="bearer",
      expires_in=self.settings.oauth_access_token_ttl,
      scope=" ".join(scopes),
      refresh_token=refresh_token_str,
    )

  # --- Token Management ---

  async def load_access_token(self, token: str) -> AccessToken | None:
    # First check static bearer token for dual-auth support.
    if self.settings.bearer_token and len(self.settings.bearer_token) >= 32:
      if hmac.compare_digest(token, self.settings.bearer_token):
        return AccessToken(
          token=token,
          client_id="static-bearer-client",
          scopes=list(ALL_SCOPES),
          resource=self.settings.resource_url,
          subject="static-bearer-client",
        )

    # Then check OAuth-issued tokens.
    access_token = self._access_tokens.get(token)
    if access_token is None:
      return None
    if access_token.expires_at is not None and access_token.expires_at <= _now():
      self._access_tokens.pop(token, None)
      return None
    return access_token

  async def load_refresh_token(
    self,
    client: OAuthClientInformationFull,
    refresh_token: str,
  ) -> RefreshToken | None:
    rt = self._refresh_tokens.get(refresh_token)
    if rt is None:
      return None
    if rt.client_id != client.client_id:
      return None
    if rt.expires_at is not None and rt.expires_at <= _now():
      self._refresh_tokens.pop(refresh_token, None)
      return None
    return rt

  async def exchange_refresh_token(
    self,
    client: OAuthClientInformationFull,
    refresh_token: RefreshToken,
    scopes: list[str],
  ) -> OAuthToken:
    # Rotate tokens.
    self._refresh_tokens.pop(refresh_token.token, None)

    effective_scopes = scopes if scopes else refresh_token.scopes
    effective_scopes = [s for s in effective_scopes if s in ALL_SCOPES and s in refresh_token.scopes]
    if not effective_scopes:
      raise TokenError(error="invalid_scope", error_description="No valid scopes for refresh")

    now = _now()
    new_access_str = _secure_token()
    new_refresh_str = _secure_token()

    new_access = AccessToken(
      token=new_access_str,
      client_id=client.client_id,
      scopes=effective_scopes,
      expires_at=now + self.settings.oauth_access_token_ttl,
      resource=refresh_token.resource or self.settings.resource_url,
      subject=refresh_token.subject,
    )
    new_refresh = RefreshToken(
      token=new_refresh_str,
      client_id=client.client_id,
      scopes=effective_scopes,
      expires_at=now + self.settings.oauth_refresh_token_ttl,
      resource=refresh_token.resource or self.settings.resource_url,
      subject=refresh_token.subject,
    )

    self._access_tokens[new_access_str] = new_access
    self._refresh_tokens[new_refresh_str] = new_refresh

    _logger.info("mcp.oauth", extra={
      "event": "TOKEN_REFRESHED",
      "client_id": client.client_id,
    })

    return OAuthToken(
      access_token=new_access_str,
      token_type="bearer",
      expires_in=self.settings.oauth_access_token_ttl,
      scope=" ".join(effective_scopes),
      refresh_token=new_refresh_str,
    )

  async def revoke_token(
    self,
    token: AccessToken | RefreshToken,
  ) -> None:
    """Revoke an access or refresh token and its counterpart."""
    token_str = token.token
    self._access_tokens.pop(token_str, None)
    self._refresh_tokens.pop(token_str, None)
    # Also revoke sibling tokens for the same client.
    client_id = token.client_id
    for key, at in list(self._access_tokens.items()):
      if at.client_id == client_id:
        self._access_tokens.pop(key, None)
    for key, rt in list(self._refresh_tokens.items()):
      if rt.client_id == client_id:
        self._refresh_tokens.pop(key, None)
    _logger.info("mcp.oauth", extra={
      "event": "TOKEN_REVOKED",
      "client_id": client_id,
    })

  async def exchange_identity_assertion(
    self,
    client: OAuthClientInformationFull,
    params: IdentityAssertionParams,
  ) -> OAuthToken:
    raise TokenError(
      error="unsupported_grant_type",
      error_description="The JWT bearer grant is not supported by this authorization server",
    )

  # --- Consent Flow (Custom Routes) ---

  def consent_handler(self) -> tuple[str, list[str], Any]:
    """Return (path, methods, handler) for the consent endpoint."""
    return "/oauth/consent", ["GET", "POST"], self._handle_consent

  async def _handle_consent(self, request: Request) -> Response:
    """Render consent form (GET) or process consent (POST)."""
    if request.method == "GET":
      return self._render_consent_form(request)
    return await self._process_consent(request)

  def _render_consent_form(self, request: Request) -> Response:
    request_id = request.query_params.get("request_id", "")
    pending = self._pending_authorizations.get(request_id)
    if not pending:
      return HTMLResponse(
        _error_page("Invalid or expired authorization request."),
        status_code=400,
      )
    # Check if pending auth has expired (10 minutes).
    if _now() - pending.created_at > 600:
      self._pending_authorizations.pop(request_id, None)
      return HTMLResponse(
        _error_page("Authorization request has expired. Please try again."),
        status_code=400,
      )
    client = self._clients.get(pending.client_id)
    client_name = html.escape(client.client_name or "Unknown Client") if client else "Unknown Client"
    scopes_display = ", ".join(html.escape(s) for s in pending.scopes)

    return HTMLResponse(_consent_page(
      request_id=html.escape(request_id),
      client_name=client_name,
      scopes=scopes_display,
    ))

  async def _process_consent(self, request: Request) -> Response:
    form = await request.form()
    request_id = str(form.get("request_id", ""))
    password = str(form.get("password", ""))

    pending = self._pending_authorizations.pop(request_id, None)
    if not pending:
      return HTMLResponse(
        _error_page("Invalid or expired authorization request."),
        status_code=400,
      )

    # Verify owner password.
    if not self.settings.oauth_owner_password or not hmac.compare_digest(
      password.encode("utf-8"),
      self.settings.oauth_owner_password.encode("utf-8"),
    ):
      # Re-insert the pending auth so the user can retry.
      self._pending_authorizations[request_id] = pending
      return HTMLResponse(_consent_page(
        request_id=html.escape(request_id),
        client_name=html.escape(
          (self._clients.get(pending.client_id) or OAuthClientInformationFull(
            client_id="", redirect_uris=[],
          )).client_name or "Unknown Client",
        ),
        scopes=", ".join(html.escape(s) for s in pending.scopes),
        error="Invalid password. Please try again.",
      ))

    # Generate authorization code.
    code_str = secrets.token_urlsafe(_CODE_BYTES)
    auth_code = AuthorizationCode(
      code=code_str,
      scopes=pending.scopes,
      expires_at=_now() + self.settings.oauth_code_ttl,
      client_id=pending.client_id,
      code_challenge=pending.params.code_challenge,
      redirect_uri=pending.params.redirect_uri,
      redirect_uri_provided_explicitly=pending.params.redirect_uri_provided_explicitly,
      resource=pending.params.resource,
      subject="owner",
    )
    self._auth_codes[code_str] = auth_code

    # Build redirect URL with code and state.
    redirect_params: dict[str, str] = {"code": code_str}
    if pending.params.state:
      redirect_params["state"] = pending.params.state

    redirect_uri = str(pending.params.redirect_uri)
    separator = "&" if "?" in redirect_uri else "?"
    redirect_url = f"{redirect_uri}{separator}{urlencode(redirect_params)}"

    _logger.info("mcp.oauth", extra={
      "event": "AUTHORIZATION_GRANTED",
      "client_id": pending.client_id,
    })

    return RedirectResponse(url=redirect_url, status_code=302)

  # --- Cleanup ---

  def cleanup_expired(self) -> None:
    """Remove expired tokens, codes, and pending authorizations."""
    now = _now()
    for key, code in list(self._auth_codes.items()):
      if code.expires_at < now:
        self._auth_codes.pop(key, None)
    for key, token in list(self._access_tokens.items()):
      if token.expires_at is not None and token.expires_at <= now:
        self._access_tokens.pop(key, None)
    for key, token in list(self._refresh_tokens.items()):
      if token.expires_at is not None and token.expires_at <= now:
        self._refresh_tokens.pop(key, None)
    for key, pending in list(self._pending_authorizations.items()):
      if now - pending.created_at > 600:
        self._pending_authorizations.pop(key, None)


class _PendingAuth:
  """Temporary state for an in-flight authorization request."""
  __slots__ = ("client_id", "params", "scopes", "created_at")

  def __init__(
    self,
    client_id: str,
    params: AuthorizationParams,
    scopes: list[str],
    created_at: int,
  ) -> None:
    self.client_id = client_id
    self.params = params
    self.scopes = scopes
    self.created_at = created_at


# --- HTML Templates (minimal, no external dependencies) ---

def _consent_page(
  *,
  request_id: str,
  client_name: str,
  scopes: str,
  error: str = "",
) -> str:
  error_html = f'<p style="color:#e53e3e;margin-bottom:16px">{html.escape(error)}</p>' if error else ""
  return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CvingTrade25X MCP – Authorize</title>
<style>
  body{{font-family:system-ui,-apple-system,sans-serif;background:#0f172a;color:#e2e8f0;
    display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0}}
  .card{{background:#1e293b;border-radius:12px;padding:32px;max-width:420px;width:100%;
    box-shadow:0 4px 6px rgba(0,0,0,.3)}}
  h1{{font-size:1.25rem;margin:0 0 8px}}
  .meta{{color:#94a3b8;font-size:.875rem;margin-bottom:20px}}
  label{{display:block;font-size:.875rem;margin-bottom:6px;color:#cbd5e1}}
  input[type=password]{{width:100%;padding:10px 12px;border:1px solid #334155;border-radius:8px;
    background:#0f172a;color:#e2e8f0;font-size:1rem;box-sizing:border-box}}
  input:focus{{outline:none;border-color:#3b82f6}}
  button{{width:100%;padding:10px;border:none;border-radius:8px;background:#3b82f6;color:#fff;
    font-size:1rem;cursor:pointer;margin-top:16px}}
  button:hover{{background:#2563eb}}
  .scopes{{background:#0f172a;border-radius:8px;padding:12px;margin:12px 0;font-size:.85rem;
    color:#94a3b8}}
</style>
</head>
<body>
<div class="card">
  <h1>Authorize MCP Client</h1>
  <p class="meta"><strong>{client_name}</strong> is requesting access to CvingTrade25X MCP.</p>
  <div class="scopes"><strong>Requested scopes:</strong><br>{scopes}</div>
  {error_html}
  <form method="POST" action="/oauth/consent">
    <input type="hidden" name="request_id" value="{request_id}">
    <label for="password">Owner Password</label>
    <input type="password" id="password" name="password" required autocomplete="current-password">
    <button type="submit">Authorize</button>
  </form>
</div>
</body>
</html>"""


def _error_page(message: str) -> str:
  return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CvingTrade25X MCP – Error</title>
<style>
  body{{font-family:system-ui,-apple-system,sans-serif;background:#0f172a;color:#e2e8f0;
    display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0}}
  .card{{background:#1e293b;border-radius:12px;padding:32px;max-width:420px;
    text-align:center;box-shadow:0 4px 6px rgba(0,0,0,.3)}}
  p{{color:#f87171}}
</style>
</head>
<body>
<div class="card">
  <h1>Authorization Error</h1>
  <p>{html.escape(message)}</p>
</div>
</body>
</html>"""
