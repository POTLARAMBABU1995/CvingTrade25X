from __future__ import annotations

from typing import Any, Dict

from services.strong_technicals_service import fetch_strong_technicals_page


def fetch_price_action_page(**params: Any) -> Dict[str, Any]:
  return fetch_strong_technicals_page(view='price_action', **params)
