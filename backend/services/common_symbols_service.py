"""Read-only symbol universe shared by FYERS and NSE ingestion pages."""
from __future__ import annotations

import logging
import time

try:
    from ..db import _acquire_connection
except ImportError:
    from db import _acquire_connection

from .nse_symbol_normalization import canonical_nse_symbol, format_fyers_nse_symbol

SOURCE_TABLE = "NSE_SYMBOLS_COMMON_DATA"
logger = logging.getLogger(__name__)


def load_common_symbols(*, fyers: bool = False) -> list[str]:
    """Read fresh membership; never fall back to files or historical prices."""
    started = time.monotonic()
    try:
        with _acquire_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT DISTINCT UPPER(TRIM(SYMBOL)) FROM NSE_SYMBOLS_COMMON_DATA WHERE TRIM(SYMBOL) IS NOT NULL ORDER BY 1")
                values = [row[0] for row in cur.fetchall()]
    except Exception as exc:
        logger.exception("Common symbol universe read failed source=%s", SOURCE_TABLE)
        raise RuntimeError("Symbol source is unavailable. Check Oracle connectivity and NSE_SYMBOLS_COMMON_DATA access, then retry.") from exc
    symbols: dict[str, str] = {}
    for value in values:
        symbol = canonical_nse_symbol(value)
        if symbol:
            symbols.setdefault(symbol, format_fyers_nse_symbol(value) if fyers else symbol)
    if not symbols:
        raise ValueError("NSE_SYMBOLS_COMMON_DATA contains no valid symbols. Populate the table and retry.")
    logger.info("Common symbol universe loaded source=%s count=%d duration_ms=%d", SOURCE_TABLE, len(symbols), (time.monotonic() - started) * 1000)
    return [symbols[key] for key in sorted(symbols)]
