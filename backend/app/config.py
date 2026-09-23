import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional


def _load_env_file(path: str) -> None:
    if not path or not os.path.exists(path):
        return
    with open(path, 'r', encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            if key and key not in os.environ:
                os.environ[key] = value.strip().strip('\"')


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value and value.isdigit() else default


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {'1', 'true', 'yes', 'on'}


@dataclass(frozen=True)
class Settings:
    app_name: str
    environment: str
    db_user: str
    db_password: str
    db_dsn: str
    db_pool_min: int
    db_pool_max: int
    db_pool_increment: int
    db_pool_timeout: int
    api_key: str
    default_limit: int
    max_limit: int
    cache_ttl_seconds: int
    cache_max_items: int
    enable_gzip: bool
    gzip_min_size: int

    @classmethod
    def from_env(cls) -> 'Settings':
        env_file = os.getenv('ENV_FILE', '.env')
        _load_env_file(env_file)
        return cls(
            app_name=os.getenv('APP_NAME', 'CvingTrade25X Charting API'),
            environment=os.getenv('APP_ENV', 'dev'),
            db_user=os.getenv('DB_USER', ''),
            db_password=os.getenv('DB_PASSWORD', ''),
            db_dsn=os.getenv('DB_DSN', ''),
            db_pool_min=_get_int('DB_POOL_MIN', 2),
            db_pool_max=_get_int('DB_POOL_MAX', 10),
            db_pool_increment=_get_int('DB_POOL_INCREMENT', 1),
            db_pool_timeout=_get_int('DB_POOL_TIMEOUT', 60),
            api_key=os.getenv('API_KEY', ''),
            default_limit=_get_int('DEFAULT_LIMIT', 800),
            max_limit=_get_int('MAX_LIMIT', 2000),
            cache_ttl_seconds=_get_int('CACHE_TTL_SECONDS', 30),
            cache_max_items=_get_int('CACHE_MAX_ITEMS', 256),
            enable_gzip=_get_bool('ENABLE_GZIP', True),
            gzip_min_size=_get_int('GZIP_MIN_SIZE', 1024),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
