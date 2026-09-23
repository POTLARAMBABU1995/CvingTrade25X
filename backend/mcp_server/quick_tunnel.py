from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


_QUICK_TUNNEL_URL = re.compile(
  r"https://[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.trycloudflare\.com(?=[\s/'\"\\]|$)",
  re.IGNORECASE,
)
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _env_bool(name: str, default: bool = False) -> bool:
  value = str(os.getenv(name, "1" if default else "0")).strip().lower()
  return value in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
  try:
    value = int(str(os.getenv(name, default)).strip())
  except (TypeError, ValueError):
    value = default
  return max(minimum, min(maximum, value))


def _runtime_path(project_root: Path, name: str, default: str) -> Path:
  raw = str(os.getenv(name, default)).strip() or default
  candidate = Path(raw)
  resolved = (candidate if candidate.is_absolute() else project_root / candidate).resolve(strict=False)
  root = project_root.resolve(strict=False)
  try:
    resolved.relative_to(root)
  except ValueError as exc:
    raise ValueError(f"{name} must remain inside the project root") from exc
  return resolved


@dataclass(frozen=True, slots=True)
class QuickTunnelSettings:
  enabled: bool
  provider: str
  origin: str
  mcp_path: str
  base_url_file: Path
  public_url_file: Path
  started_at_file: Path
  metadata_file: Path
  log_file: Path
  pid_file: Path
  startup_timeout_seconds: int
  allow_public_noauth_test: bool

  @classmethod
  def from_env(cls, project_root: Path) -> "QuickTunnelSettings":
    path = str(os.getenv("CVING_MCP_PATH", "/mcp")).strip() or "/mcp"
    if not path.startswith("/"):
      path = f"/{path}"
    settings = cls(
      enabled=_env_bool("CVING_QUICK_TUNNEL_ENABLED", False),
      provider=str(os.getenv("CVING_QUICK_TUNNEL_PROVIDER", "cloudflare")).strip().lower(),
      origin=str(os.getenv("CVING_QUICK_TUNNEL_ORIGIN", "http://127.0.0.1:1729")).strip().rstrip("/"),
      mcp_path=path,
      base_url_file=_runtime_path(
        project_root, "CVING_QUICK_TUNNEL_BASE_URL_FILE", "runtime/mcp/public_url.txt"
      ),
      public_url_file=_runtime_path(
        project_root, "CVING_QUICK_TUNNEL_PUBLIC_URL_FILE", "runtime/mcp/remote_mcp_url.txt"
      ),
      started_at_file=_runtime_path(
        project_root, "CVING_QUICK_TUNNEL_STARTED_AT_FILE", "runtime/mcp/tunnel_started_at.txt"
      ),
      metadata_file=_runtime_path(
        project_root, "CVING_QUICK_TUNNEL_METADATA_FILE", "runtime/mcp/remote_mcp.json"
      ),
      log_file=_runtime_path(project_root, "CVING_QUICK_TUNNEL_LOG_FILE", "runtime/logs/cloudflare_mcp.log"),
      pid_file=_runtime_path(project_root, "CVING_QUICK_TUNNEL_PID_FILE", "runtime/mcp/cloudflared.pid"),
      startup_timeout_seconds=_env_int(
        "CVING_QUICK_TUNNEL_STARTUP_TIMEOUT_SECONDS", 30, minimum=5, maximum=300
      ),
      allow_public_noauth_test=_env_bool("CVING_MCP_ALLOW_PUBLIC_NOAUTH_TEST", False),
    )
    settings.validate()
    return settings

  def validate(self) -> None:
    if self.provider != "cloudflare":
      raise ValueError("CVING_QUICK_TUNNEL_PROVIDER must be cloudflare")
    parsed = urlparse(self.origin)
    if parsed.scheme != "http" or parsed.hostname not in _LOOPBACK_HOSTS:
      raise ValueError("CVING_QUICK_TUNNEL_ORIGIN must be a loopback HTTP URL")
    if parsed.port == 1521:
      raise ValueError("Oracle port 1521 must never be tunneled")
    if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
      raise ValueError("CVING_QUICK_TUNNEL_ORIGIN must not include a path, query, or fragment")

  @property
  def local_mcp_url(self) -> str:
    return f"{self.origin}{self.mcp_path}"


def parse_trycloudflare_url(output: str) -> str:
  match = _QUICK_TUNNEL_URL.search(output or "")
  if not match:
    raise ValueError("TUNNEL_URL_NOT_FOUND")
  return match.group(0).lower().rstrip("/")


def build_mcp_url(base_url: str, mcp_path: str = "/mcp") -> str:
  parsed = urlparse(base_url)
  if parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(".trycloudflare.com"):
    raise ValueError("Quick Tunnel base URL must be HTTPS on trycloudflare.com")
  if parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.username or parsed.password:
    raise ValueError("Quick Tunnel base URL must not contain credentials, a path, query, or fragment")
  path = mcp_path if mcp_path.startswith("/") else f"/{mcp_path}"
  return f"https://{parsed.hostname}{path}"


def public_metadata(
  *,
  base_url: str,
  mcp_url: str,
  local_origin: str,
  pid: int,
  cloudflared_path: str,
  cloudflared_version: str,
  authentication: str,
  remote_validation: str = "NOT TESTED",
) -> dict[str, object]:
  return {
    "provider": "cloudflare",
    "type": "quick",
    "base_url": base_url,
    "mcp_url": mcp_url,
    "created_at": datetime.now(timezone.utc).isoformat(),
    "local_origin": local_origin,
    "temporary": True,
    "active": True,
    "pid": int(pid),
    "cloudflared_path": str(Path(cloudflared_path).resolve(strict=False)),
    "cloudflared_version": cloudflared_version,
    "authentication": authentication,
    "remote_validation": remote_validation,
  }


def write_public_metadata(settings: QuickTunnelSettings, metadata: dict[str, object]) -> None:
  for path in (
    settings.base_url_file,
    settings.public_url_file,
    settings.started_at_file,
    settings.metadata_file,
    settings.pid_file,
    settings.log_file,
  ):
    path.parent.mkdir(parents=True, exist_ok=True)
  settings.base_url_file.write_text(f"{metadata['base_url']}\n", encoding="utf-8")
  settings.public_url_file.write_text(f"{metadata['mcp_url']}\n", encoding="utf-8")
  settings.started_at_file.write_text(f"{metadata['created_at']}\n", encoding="utf-8")
  settings.metadata_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
  pid_payload = {
    key: metadata[key]
    for key in ("pid", "cloudflared_path", "created_at", "local_origin")
  }
  settings.pid_file.write_text(json.dumps(pid_payload, indent=2), encoding="utf-8")


def mark_inactive(settings: QuickTunnelSettings, *, reason: str) -> None:
  metadata: dict[str, object] = {}
  if settings.metadata_file.is_file():
    try:
      metadata = json.loads(settings.metadata_file.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
      metadata = {}
  metadata.update({
    "active": False,
    "stopped_at": datetime.now(timezone.utc).isoformat(),
    "inactive_reason": reason,
  })
  settings.metadata_file.parent.mkdir(parents=True, exist_ok=True)
  settings.metadata_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
  settings.public_url_file.unlink(missing_ok=True)
  settings.base_url_file.unlink(missing_ok=True)
  settings.started_at_file.unlink(missing_ok=True)
  settings.pid_file.unlink(missing_ok=True)


def settings_as_public_dict(settings: QuickTunnelSettings) -> dict[str, object]:
  payload = asdict(settings)
  for key in (
    "base_url_file",
    "public_url_file",
    "started_at_file",
    "metadata_file",
    "log_file",
    "pid_file",
  ):
    payload[key] = str(payload[key])
  return payload
