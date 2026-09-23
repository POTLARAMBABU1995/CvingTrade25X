from __future__ import annotations

import os
from pathlib import Path


_ALLOWED_PREFIXES = ("CVING_MCP_", "CVING_QUICK_TUNNEL_", "CVING_CLOUDFLARE_")


def load_local_mcp_env(project_root: Path | None = None) -> tuple[str, ...]:
  """Load MCP-only values from the ignored project .env without overriding the shell."""
  root = project_root or Path(__file__).resolve().parents[2]
  env_file = root / ".env"
  if not env_file.is_file():
    return ()

  loaded: list[str] = []
  for raw_line in env_file.read_text(encoding="utf-8-sig").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
      continue
    name, value = line.split("=", 1)
    name = name.strip()
    if not name.startswith(_ALLOWED_PREFIXES) or name in os.environ:
      continue
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
      value = value[1:-1]
    os.environ[name] = value
    loaded.append(name)
  return tuple(loaded)
