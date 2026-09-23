from __future__ import annotations

from typing import Any, Callable, Dict

try:
    from .asura_trade_service import sync_asura_bullish_strategy
except ImportError:  # pragma: no cover
    from services.asura_trade_service import sync_asura_bullish_strategy  # type: ignore


StrategyHandler = Callable[..., Dict[str, Any]]

_STRATEGY_HANDLERS: Dict[str, StrategyHandler] = {
    "asura": sync_asura_bullish_strategy,
    "asura_bullish": sync_asura_bullish_strategy,
    "asura_bullish_trend": sync_asura_bullish_strategy,
}


def run_strategy_sync(strategy: str, **kwargs: Any) -> Dict[str, Any]:
    key = (strategy or "").strip().lower()
    handler = _STRATEGY_HANDLERS.get(key)
    if not handler:
        raise ValueError(f"Unknown strategy '{strategy}'")
    return handler(**kwargs)
