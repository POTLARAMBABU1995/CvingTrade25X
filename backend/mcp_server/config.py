from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from urllib.parse import urlparse


PROFILES = {"local-stdio", "local-http", "secure-tunnel", "remote-gateway"}
AUTH_MODES = {"none", "bearer", "oauth", "oauth-server"}
ALL_SCOPES = (
  "cving:market:read",
  "cving:analysis:read",
  "cving:scan:read",
  "cving:admin:health",
)


def _env_bool(name: str, default: bool = False) -> bool:
  value = str(os.getenv(name, "1" if default else "0")).strip().lower()
  return value in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
  try:
    value = int(str(os.getenv(name, default)).strip())
  except (TypeError, ValueError):
    value = default
  return max(minimum, min(maximum, value))


def _env_csv(name: str, default: str = "") -> tuple[str, ...]:
  return tuple(item.strip() for item in str(os.getenv(name, default)).split(",") if item.strip())


@dataclass(frozen=True, slots=True)
class McpSettings:
  host: str
  port: int
  path: str
  max_bars: int
  max_symbols: int
  max_scan_results: int
  scan_workers: int
  cache_ttl_seconds: int
  allow_remote: bool
  bearer_token: str
  allowed_origins: tuple[str, ...]
  log_level: str
  profile: str = "local-http"
  auth_mode: str = "none"
  allowed_hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "[::1]")
  public_base_url: str = ""
  trust_proxy: bool = False
  trusted_proxies: tuple[str, ...] = ()
  rate_limit_per_minute: int = 60
  max_concurrent_requests: int = 10
  max_request_body_size: int = 1_048_576
  max_response_bytes: int = 1_048_576
  request_timeout_seconds: int = 45
  tool_timeout_seconds: int = 30
  db_query_timeout_ms: int = 15_000
  oracle_circuit_failures: int = 3
  oracle_circuit_reset_seconds: int = 30
  allowed_exchanges: tuple[str, ...] = ("NSE",)
  allowed_tools: tuple[str, ...] = ()
  symbol_allowlist: tuple[str, ...] = ()
  symbol_denylist: tuple[str, ...] = ()
  oauth_issuer_url: str = ""
  oauth_resource_url: str = ""
  oauth_introspection_url: str = ""
  oauth_client_id: str = ""
  oauth_client_secret: str = ""
  oauth_expected_audience: str = ""
  oauth_owner_password: str = ""
  oauth_access_token_ttl: int = 3600
  oauth_refresh_token_ttl: int = 86400
  oauth_code_ttl: int = 600
  allow_public_noauth_test: bool = False

  @classmethod
  def from_env(cls) -> "McpSettings":
    profile = str(os.getenv("CVING_MCP_PROFILE", "local-http")).strip().lower() or "local-http"
    owner_password = str(os.getenv("CVING_MCP_OAUTH_OWNER_PASSWORD", "")).strip()
    default_auth = "bearer" if profile in {"secure-tunnel", "remote-gateway"} else "none"
    if profile in {"secure-tunnel", "remote-gateway"} and owner_password and len(owner_password) >= 16:
      default_auth = "oauth-server"
    path = str(os.getenv("CVING_MCP_PATH", "/mcp")).strip() or "/mcp"
    if not path.startswith("/"):
      path = f"/{path}"
    old_max_symbols = _env_int("CVING_MCP_MAX_SYMBOLS", 500, minimum=1, maximum=5000)
    old_max_results = _env_int("CVING_MCP_MAX_SCAN_RESULTS", 50, minimum=1, maximum=500)
    old_workers = _env_int("CVING_MCP_SCAN_WORKERS", 4, minimum=1, maximum=16)
    return cls(
      host=str(os.getenv("CVING_MCP_HOST", "127.0.0.1")).strip() or "127.0.0.1",
      port=_env_int("CVING_MCP_PORT", 1729, minimum=1, maximum=65535),
      path=path,
      max_bars=_env_int("CVING_MCP_MAX_BARS", 2000, minimum=35, maximum=5000),
      max_symbols=_env_int("CVING_SCAN_MAX_UNIVERSE", old_max_symbols, minimum=1, maximum=5000),
      max_scan_results=_env_int("CVING_SCAN_MAX_RESULTS", old_max_results, minimum=1, maximum=500),
      scan_workers=_env_int("CVING_SCAN_WORKERS", old_workers, minimum=1, maximum=16),
      cache_ttl_seconds=_env_int("CVING_MCP_CACHE_TTL_SECONDS", 30, minimum=0, maximum=3600),
      allow_remote=_env_bool("CVING_MCP_ALLOW_REMOTE", False),
      bearer_token=str(os.getenv("CVING_MCP_BEARER_TOKEN", "")).strip(),
      allowed_origins=_env_csv("CVING_MCP_ALLOWED_ORIGINS"),
      log_level=str(os.getenv("CVING_MCP_LOG_LEVEL", "INFO")).strip().upper() or "INFO",
      profile=profile,
      auth_mode=str(os.getenv("CVING_MCP_AUTH_MODE", default_auth)).strip().lower() or default_auth,
      allowed_hosts=_env_csv("CVING_MCP_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]"),
      public_base_url=str(os.getenv("CVING_MCP_PUBLIC_URL") or os.getenv("CVING_MCP_PUBLIC_BASE_URL") or ("https://" + os.environ["CVING_MCP_PUBLIC_HOST"] + path if os.getenv("CVING_MCP_PUBLIC_HOST") else "")).strip().rstrip("/"),
      trust_proxy=_env_bool("CVING_MCP_TRUST_PROXY", False),
      trusted_proxies=_env_csv("CVING_MCP_TRUSTED_PROXIES"),
      rate_limit_per_minute=_env_int("CVING_MCP_RATE_LIMIT_PER_MINUTE", 60, minimum=1, maximum=10_000),
      max_concurrent_requests=_env_int("CVING_MCP_MAX_CONCURRENT_REQUESTS", 10, minimum=1, maximum=500),
      max_request_body_size=_env_int("CVING_MCP_MAX_REQUEST_BODY_BYTES", 1_048_576, minimum=1024, maximum=16_777_216),
      max_response_bytes=_env_int("CVING_MCP_MAX_RESPONSE_BYTES", 1_048_576, minimum=4096, maximum=16_777_216),
      request_timeout_seconds=_env_int("CVING_MCP_REQUEST_TIMEOUT_SECONDS", 45, minimum=1, maximum=600),
      tool_timeout_seconds=_env_int("CVING_MCP_TOOL_TIMEOUT_SECONDS", 30, minimum=1, maximum=600),
      db_query_timeout_ms=_env_int("CVING_MCP_DB_QUERY_TIMEOUT_MS", 15_000, minimum=1000, maximum=300_000),
      oracle_circuit_failures=_env_int("CVING_MCP_ORACLE_CIRCUIT_FAILURES", 3, minimum=1, maximum=20),
      oracle_circuit_reset_seconds=_env_int("CVING_MCP_ORACLE_CIRCUIT_RESET_SECONDS", 30, minimum=1, maximum=600),
      allowed_exchanges=tuple(item.upper() for item in _env_csv("CVING_MCP_ALLOWED_EXCHANGES", "NSE")),
      allowed_tools=_env_csv("CVING_MCP_ALLOWED_TOOLS"),
      symbol_allowlist=tuple(item.upper() for item in _env_csv("CVING_MCP_SYMBOL_ALLOWLIST")),
      symbol_denylist=tuple(item.upper() for item in _env_csv("CVING_MCP_SYMBOL_DENYLIST")),
      oauth_issuer_url=str(os.getenv("CVING_MCP_OAUTH_ISSUER_URL", "")).strip().rstrip("/"),
      oauth_resource_url=str(os.getenv("CVING_MCP_OAUTH_RESOURCE_URL", "")).strip().rstrip("/"),
      oauth_introspection_url=str(os.getenv("CVING_MCP_OAUTH_INTROSPECTION_URL", "")).strip(),
      oauth_client_id=str(os.getenv("CVING_MCP_OAUTH_CLIENT_ID", "")).strip(),
      oauth_client_secret=str(os.getenv("CVING_MCP_OAUTH_CLIENT_SECRET", "")).strip(),
      oauth_expected_audience=str(os.getenv("CVING_MCP_OAUTH_EXPECTED_AUDIENCE", "")).strip(),
      oauth_owner_password=owner_password,
      oauth_access_token_ttl=_env_int("CVING_MCP_OAUTH_ACCESS_TOKEN_TTL_SECONDS", 3600, minimum=60, maximum=86400),
      oauth_refresh_token_ttl=_env_int("CVING_MCP_OAUTH_REFRESH_TOKEN_TTL_SECONDS", 86400, minimum=300, maximum=604800),
      oauth_code_ttl=_env_int("CVING_MCP_OAUTH_CODE_TTL_SECONDS", 600, minimum=30, maximum=3600),
      allow_public_noauth_test=_env_bool("CVING_MCP_ALLOW_PUBLIC_NOAUTH_TEST", False),
    )

  @property
  def is_loopback(self) -> bool:
    return self.host.lower() in {"127.0.0.1", "localhost", "::1", "[::1]"}

  @property
  def resource_url(self) -> str:
    configured = str(os.getenv("CVING_MCP_PUBLIC_URL", "")).strip()
    public_host = str(os.getenv("CVING_MCP_PUBLIC_HOST", "")).strip()
    return self.oauth_resource_url or configured or (f"https://{public_host}{self.path}" if public_host else "") or self.public_base_url or f"http://{self.host}:{self.port}{self.path}"

  def validate(self, *, transport: str) -> None:
    if self.profile not in PROFILES:
      raise ValueError(f"CVING_MCP_PROFILE must be one of: {', '.join(sorted(PROFILES))}")
    if self.auth_mode not in AUTH_MODES:
      raise ValueError(f"CVING_MCP_AUTH_MODE must be one of: {', '.join(sorted(AUTH_MODES))}")
    if transport == "stdio":
      if self.profile not in {"local-stdio", "local-http"}:
        raise ValueError("stdio is available only in local-stdio or local-http profiles")
      return
    if self.auth_mode == "none":
      raise ValueError("HTTP profiles reject anonymous authentication")
    if not self.allowed_hosts:
      raise ValueError("CVING_MCP_ALLOWED_HOSTS must not be empty")
    if self.host != "127.0.0.1" or self.port != 1729 or self.path != "/mcp":
      raise ValueError("MCP HTTP must bind only to 127.0.0.1:1729/mcp")
    if self.profile in {"secure-tunnel", "remote-gateway"}:
      if self.auth_mode == "none" and (
        self.profile != "secure-tunnel" or not self.allow_public_noauth_test
      ):
        raise ValueError("Remote profiles reject CVING_MCP_AUTH_MODE=none")
      parsed = urlparse(self.public_base_url)
      if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Remote profiles require an HTTPS CVING_MCP_PUBLIC_BASE_URL")
    for public_url in (self.public_base_url, self.oauth_resource_url):
      if public_url:
        public = urlparse(public_url)
        if public.scheme != "https" or not public.hostname or public.username or public.password or public.query or public.fragment:
          raise ValueError("Public MCP URLs require HTTPS without credentials, query or fragment")
    if self.auth_mode == "bearer" and len(self.bearer_token) < 32:
      raise ValueError("Bearer mode requires CVING_MCP_BEARER_TOKEN with at least 32 characters")
    if self.auth_mode == "oauth":
      required = {
        "CVING_MCP_OAUTH_ISSUER_URL": self.oauth_issuer_url,
        "CVING_MCP_OAUTH_INTROSPECTION_URL": self.oauth_introspection_url,
        "CVING_MCP_OAUTH_CLIENT_ID": self.oauth_client_id,
        "CVING_MCP_OAUTH_CLIENT_SECRET": self.oauth_client_secret,
      }
      missing = [name for name, value in required.items() if not value]
      if missing:
        raise ValueError(f"OAuth mode is missing: {', '.join(missing)}")
      for name, value in (("issuer", self.oauth_issuer_url), ("introspection", self.oauth_introspection_url)):
        if urlparse(value).scheme != "https":
          raise ValueError(f"OAuth {name} URL must use HTTPS")
    if self.auth_mode == "oauth-server":
      if len(self.oauth_owner_password) < 16:
        raise ValueError("oauth-server mode requires CVING_MCP_OAUTH_OWNER_PASSWORD with at least 16 characters")
    if self.trust_proxy:
      if not self.trusted_proxies:
        raise ValueError("CVING_MCP_TRUST_PROXY=1 requires CVING_MCP_TRUSTED_PROXIES")
      for network in self.trusted_proxies:
        ipaddress.ip_network(network, strict=False)

  def validate_http_security(self) -> None:
    self.validate(transport="streamable-http")
