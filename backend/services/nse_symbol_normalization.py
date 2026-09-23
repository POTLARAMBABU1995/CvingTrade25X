from __future__ import annotations

import re
from typing import Any


NSE_CASH_SERIES = ("EQ", "BE", "SM", "ST", "BZ")
_SERIES_RE = re.compile(r"-(EQ|BE|SM|ST|BZ)$", re.IGNORECASE)
_KEY_RE = re.compile(r"[^A-Z0-9]+")

# Approved current NSE identities. Old values are accepted only as input aliases;
# API output and persisted symbol lists always use the replacement.
NSE_SYMBOL_REPLACEMENTS: dict[str, str] = {
    "BOSCHHCIL": "BOSCH-HCIL",
    "MIRCELECTR": "ONIDA",
    "RESTAURANT": "RBA",
    "SCHLOSS": "THELEELA",
    "SHOPPERS": "SHOPERSTOP",
    "VISHALMEGA": "VMM",
    "LTIM": "LTM",
}

# Exact series verified against the active FYERS/NSE cash universe and current
# DEV rows. Symbols not listed here remain EQ by default.
NSE_SYMBOL_SERIES: dict[str, str] = {
    "AIMTRON": "SM",
    "APTECHT": "BE",
    "BSHSL": "BE",
    "CELLECOR": "ST",
    "CHEMCON": "BE",
    "CHEMFAB": "BE",
    "DANISH": "SM",
    "DPSCLTD": "BE",
    "EFFWA": "ST",
    "ECOSMOBLTY": "BE",
    "FLYSBS": "SM",
    "KHAICHEM": "BE",
    "MONOLITH": "SM",
    "NAMOEWASTE": "ST",
    "OBSCP": "SM",
    "RELINFRA": "BE",
    "SACHEEROME": "SM",
    "SSEGL": "SM",
    "TEJASCARGO": "SM",
    "VALIANTORG": "BE",
    "VHLTD": "BE",
    "VINSYS": "ST",
    "ZTECH": "SM",
}


def _clean_symbol(value: Any) -> tuple[str, str | None]:
    text = "".join(str(value or "").strip().upper().split())
    if not text:
        return "", None
    if ":" in text:
        text = text.split(":", 1)[1]
    if text.endswith(".NS"):
        text = text[:-3]
    match = _SERIES_RE.search(text)
    series = match.group(1).upper() if match else None
    if match:
        text = text[: match.start()]
    return text.strip("-"), series


def canonical_nse_symbol(value: Any) -> str:
    symbol, _series = _clean_symbol(value)
    if not symbol:
        return ""
    lookup_key = _KEY_RE.sub("", symbol)
    return NSE_SYMBOL_REPLACEMENTS.get(lookup_key, symbol)


def canonical_nse_symbol_key(value: Any) -> str:
    return _KEY_RE.sub("", canonical_nse_symbol(value))


def format_fyers_nse_symbol(value: Any, *, default_series: str = "EQ") -> str:
    symbol, explicit_series = _clean_symbol(value)
    canonical = canonical_nse_symbol(symbol)
    if not canonical:
        raise ValueError("Symbol is required.")
    series = explicit_series or NSE_SYMBOL_SERIES.get(canonical) or default_series.upper()
    if series not in NSE_CASH_SERIES:
        series = "EQ"
    return f"NSE:{canonical}-{series}"
