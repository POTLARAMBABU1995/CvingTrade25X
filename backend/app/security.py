from fastapi import Header, HTTPException

from .config import get_settings


def verify_api_key(x_api_key: str = Header(None, alias='X-API-Key')) -> None:
    settings = get_settings()
    if not settings.api_key:
        return
    if not x_api_key or x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail='Invalid API key')
