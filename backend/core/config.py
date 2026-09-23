from __future__ import annotations

import os
from dataclasses import dataclass


def get_env(name: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.getenv(name)
    if value is None or value == "":
        if required:
            raise RuntimeError(f"Missing required environment variable: {name}")
        return "" if default is None else default
    return value.strip()


def get_env_int(name: str, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    raw = get_env(name, str(default))
    try:
        value = int(raw)
    except Exception:
        value = int(default)
    if minimum is not None:
        value = max(value, minimum)
    if maximum is not None:
        value = min(value, maximum)
    return value


def get_env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class RuntimeSettings:
    environment: str = get_env("APP_ENV", "dev")
    service_name: str = get_env("APP_NAME", "cvingtrade25x")
    request_id_header: str = get_env("REQUEST_ID_HEADER", "X-Request-ID")


runtime_settings = RuntimeSettings()
