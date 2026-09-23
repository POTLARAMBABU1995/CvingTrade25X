from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from .env_bootstrap import load_default_env  # type: ignore
except Exception:  # pragma: no cover
    from env_bootstrap import load_default_env  # type: ignore

load_default_env()


def _get_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is not None:
        return value.strip()
    return default


@dataclass(slots=True)
class Settings:
    oracle_user: str = _get_env("ORACLE_USER", "CVING_APP")
    oracle_password: str = _get_env("ORACLE_PASSWORD", "")
    oracle_dsn: str = _get_env("ORACLE_DSN", "127.0.0.1:1521/cvingpdb.local")
    oracle_min_pool: int = int(_get_env("ORACLE_MIN_POOL", "2"))
    oracle_max_pool: int = int(_get_env("ORACLE_MAX_POOL", "10"))
    oracle_pool_increment: int = int(_get_env("ORACLE_POOL_INCREMENT", "1"))
    oracle_stmt_cache_size: int = int(_get_env("ORACLE_STMT_CACHE", "40"))
    oracle_arraysize: int = int(_get_env("ORACLE_ARRAYSIZE", "500"))
    redis_url: str | None = _get_env("REDIS_URL")
    cache_ttl_seconds: int = int(_get_env("CACHE_TTL_SECONDS", "30"))
    cache_max_items: int = int(_get_env("CACHE_MAX_ITEMS", "512"))
    default_page_size: int = int(_get_env("SR_DEFAULT_PAGE_SIZE", "25"))
    max_page_size: int = int(_get_env("SR_MAX_PAGE_SIZE", "200"))
    sr_trading_days_lookback: int = int(_get_env("SR_TRADING_DAYS_LOOKBACK", "504"))


settings = Settings()
