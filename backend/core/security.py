from __future__ import annotations

import re
from typing import Any


SECRET_KEYS = ("password", "token", "secret", "api_key", "apikey", "authorization", "cookie")
TOKEN_RE = re.compile(r"(bearer\s+)[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE)


def mask_secret(value: Any, *, visible: int = 4) -> str:
    text = "" if value is None else str(value)
    if not text:
        return ""
    if len(text) <= visible:
        return "***"
    return f"{text[:visible]}***"


def mask_sensitive_mapping(payload: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in payload.items():
        if any(token in key.lower() for token in SECRET_KEYS):
            safe[key] = mask_secret(value)
        elif isinstance(value, dict):
            safe[key] = mask_sensitive_mapping(value)
        else:
            safe[key] = value
    return safe


def sanitize_log_text(value: Any) -> str:
    text = "" if value is None else str(value)
    return TOKEN_RE.sub(r"\1[REDACTED]", text)
