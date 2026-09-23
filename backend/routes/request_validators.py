from __future__ import annotations

from typing import Any, Iterable


def parse_int(value: Any, default: int, *, min_value: int, max_value: int, field: str) -> int:
    text = str(value or "").strip()
    if not text:
        return default
    try:
        parsed = int(text)
    except Exception:
        raise ValueError(f"Invalid request parameter: {field}")
    if parsed < min_value or parsed > max_value:
        raise ValueError(f"Invalid request parameter: {field}")
    return parsed


def parse_sort_key(value: Any, *, default: str, allowed: Iterable[str], field: str = "sort") -> str:
    token = str(value or "").strip()
    if not token:
        return default
    upper = token.upper()
    allowed_set = {str(item).upper() for item in allowed}
    if upper not in allowed_set:
        raise ValueError(f"Invalid request parameter: {field}")
    return upper


def parse_sort_dir(value: Any, *, default: str = "DESC", field: str = "order") -> str:
    token = str(value or "").strip().upper()
    if not token:
        return default
    if token not in {"ASC", "DESC"}:
        raise ValueError(f"Invalid request parameter: {field}")
    return token

