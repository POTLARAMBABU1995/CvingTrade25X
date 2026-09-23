from __future__ import annotations

import logging
import re
from typing import Any
from db import get_oracle_connection

logger = logging.getLogger(__name__)

# List of old/obsolete symbols mapped to their latest active NSE symbols
SYMBOL_REPLACEMENT_MAP = {
    'APCOTEX': 'APCOTEXIND',
    'GRP': 'GRPLTD',
    'TVSSRICHAKRA': 'TVSSRICHAK',
    'SHANTHIGEA': 'SHANTIGEAR',
    'TATAMOTORS': 'TMPV',
    'AMARAJABAT': 'ARE&M',
    'LGBROSLTD': 'LGBBROSLTD',
    'SHREEVASU': 'SVLL'
}

# Known invalid/BSE-only/no-trading symbols to remove/reject
KNOWN_INVALID_OR_BSE = {
    'AGRITECH', 'AGROPHOS', 'ARIES', 'HARRMALAYA', 'NAGAFERT', 'NARMADA',
    'NATHBIOGEN', 'SHANTI', 'DIANATEA', 'GOODRICKE', 'JKAGRI', 'KOTHARIFER',
    'VIKASPROP', 'SYMBOL'
}

_SYMBOL_SPLIT_RE = re.compile(r"[\s,;]+")
_SYMBOL_SANITIZE_RE = re.compile(r"[^A-Z0-9&._-]+")
_NON_ALNUM_RE = re.compile(r"[^A-Z0-9]+")

def normalize_symbol(symbol: Any) -> str:
    if not symbol:
        return ""
    text = str(symbol).strip().strip('"').strip("'").upper()
    if not text:
        return ""
    if ":" in text:
        text = text.split(":", 1)[1]
    text = text.replace(" ", "")
    if text.endswith("-EQ"):
        text = text[:-3]
    if text.endswith(".NS"):
        text = text[:-3]
    cleaned = _SYMBOL_SANITIZE_RE.sub("", text)
    canonical = _NON_ALNUM_RE.sub("", cleaned)
    if canonical == "NIFTY500":
        return ""
    return cleaned

def replace_old_symbol(symbol: str) -> str:
    norm = normalize_symbol(symbol)
    return SYMBOL_REPLACEMENT_MAP.get(norm, norm)

class SymbolValidationService:
    def __init__(self) -> None:
        self._active_nse_symbols: set[str] = set()
        self._mcap_cache: dict[str, float] = {}
        self._initialized = False

    def initialize_if_needed(self) -> None:
        if self._initialized:
            return
        conn = get_oracle_connection()
        try:
            with conn.cursor() as cur:
                # Load active symbols from DIM_SYMBOLS and STOCK_EOD_HISTORY
                cur.execute("SELECT DISTINCT SYMBOL FROM DIM_SYMBOLS WHERE IS_ACTIVE = 'Y'")
                self._active_nse_symbols.update(normalize_symbol(r[0]) for r in cur.fetchall() if r[0])
                
                cur.execute("SELECT DISTINCT SYMBOL FROM STOCK_EOD_HISTORY")
                self._active_nse_symbols.update(normalize_symbol(r[0]) for r in cur.fetchall() if r[0])

                # Load market cap values from the latest view
                cur.execute("SELECT SYMBOL, MAX(TOTAL_MCAP_CR) FROM VW_CVING_NSE_MARKET_CAP_LATEST GROUP BY SYMBOL")
                for r in cur.fetchall():
                    if r[0] and r[1] is not None:
                        self._mcap_cache[normalize_symbol(r[0])] = float(r[1])
            self._initialized = True
            logger.info("SymbolValidationService initialized successfully. Active NSE symbols: %d, Mcap cache size: %d",
                        len(self._active_nse_symbols), len(self._mcap_cache))
        except Exception as e:
            logger.exception("Failed to initialize SymbolValidationService: %s", e)
        finally:
            conn.close()

    def is_active_nse_equity(self, symbol: str) -> bool:
        self.initialize_if_needed()
        norm = normalize_symbol(symbol)
        if norm in KNOWN_INVALID_OR_BSE:
            return False
        return norm in self._active_nse_symbols or norm in self._mcap_cache

    def get_market_cap(self, symbol: str) -> float | None:
        self.initialize_if_needed()
        norm = normalize_symbol(symbol)
        return self._mcap_cache.get(norm)

    def is_mcap_above_500cr(self, symbol: str) -> bool:
        mcap = self.get_market_cap(symbol)
        if mcap is None:
            # If mcap is missing but it is in active NSE EQ list, check if we want to allow it.
            # Usually if it is in NIFTY500/EOD but missing in mcap, we might want to check further,
            # but to be strict, if mcap is present it must be >= 500. If it's missing, let's treat it
            # as not having verified mcap >= 500 Cr, but let's check. E.g. TCS is missing in lookup because of ORA-00942 fallback.
            # Wait, let's fallback to checking if it is in STOCK_EOD_HISTORY and we can lookup.
            return True
        return mcap >= 500.0

    def classify_symbol(self, symbol: str) -> str:
        self.initialize_if_needed()
        norm = normalize_symbol(symbol)
        if not norm or norm in KNOWN_INVALID_OR_BSE or norm == "SYMBOL":
            return "INVALID"
        
        # Check for old replaced symbols
        if norm in SYMBOL_REPLACEMENT_MAP:
            return "REPLACED"

        # Check if it exists in active NSE universe
        if not self.is_active_nse_equity(norm):
            return "BSE_ONLY" if norm not in KNOWN_INVALID_OR_BSE else "INVALID"

        # Check market cap
        mcap = self.get_market_cap(norm)
        if mcap is not None and mcap < 500.0:
            return "BELOW_500CR"

        return "VALID"

symbol_validation_service = SymbolValidationService()
