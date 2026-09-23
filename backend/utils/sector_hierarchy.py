"""Shared sector hierarchy and alias normalization helpers."""

from __future__ import annotations

import re
from typing import Any


def normalize_sector_alias(value: Any) -> str:
    """Return a stable lookup token for sector codes and display names."""
    token = str(value or "").strip().upper()
    token = token.replace("&", " AND ")
    token = re.sub(r"[^A-Z0-9]+", "_", token)
    return re.sub(r"_+", "_", token).strip("_")


def canonical_sector_code(value: Any, aliases: dict[str, str] | None = None) -> str:
    token = normalize_sector_alias(value)
    if not token:
        return ""
    return (aliases or {}).get(token, token)


def hierarchy_fields(row: dict[str, Any]) -> dict[str, Any]:
    """Add backward-compatible hierarchy keys without changing existing keys."""
    code = str(row.get("sectorCode") or row.get("sector_code") or "").strip().upper()
    name = str(row.get("sectorName") or row.get("sector_name") or row.get("sector") or code).strip()
    row.setdefault("sectorCode", code or None)
    row.setdefault("sectorName", name or None)
    row.setdefault("parentSector", row.get("parent_sector"))
    row.setdefault("industry", row.get("industry_name") or row.get("industry"))
    return row
