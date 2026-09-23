from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))

from backend.mcp_server.quick_tunnel import QuickTunnelSettings, settings_as_public_dict  # noqa: E402


def main() -> int:
  settings = QuickTunnelSettings.from_env(PROJECT_ROOT)
  print(json.dumps(settings_as_public_dict(settings)))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
