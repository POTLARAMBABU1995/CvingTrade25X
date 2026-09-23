from __future__ import annotations

import os
from pathlib import Path


def _iter_env_candidates() -> list[Path]:
    env_file = str(os.getenv("ENV_FILE") or "").strip()
    candidates: list[Path] = []
    if env_file:
        candidates.append(Path(env_file).expanduser())

    module_dir = Path(__file__).resolve().parent
    candidates.append(module_dir / ".env")
    candidates.append(module_dir.parents[1] / ".env")
    return candidates


def load_default_env() -> None:
    seen: set[Path] = set()
    for candidate in _iter_env_candidates():
        try:
            resolved = candidate.resolve()
        except Exception:
            resolved = candidate
        if resolved in seen or not resolved.exists():
            continue
        seen.add(resolved)
        for raw_line in resolved.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key or key in os.environ:
                continue
            os.environ[key] = value.strip().strip("\"").strip("'")

