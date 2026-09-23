from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.mcp_server.config import McpSettings
from backend.mcp_server.errors import McpServiceError
from backend.mcp_server.service import McpPriceActionService


def _settings() -> McpSettings:
  return McpSettings(
    host="127.0.0.1",
    port=1729,
    path="/mcp",
    max_bars=2000,
    max_symbols=500,
    max_scan_results=100,
    scan_workers=2,
    cache_ttl_seconds=0,
    allow_remote=False,
    bearer_token="",
    allowed_origins=(),
    log_level="INFO",
  )


def _payload(count: int = 160) -> dict:
  start = date(2026, 1, 1)
  candles = []
  volume = []
  base = 100.0
  for index in range(count):
    wave = (index % 10) - 5
    close = base + (index * 0.18) + (wave * 0.55)
    open_value = close - (0.7 if index % 2 == 0 else -0.35)
    high = max(open_value, close) + 1.2
    low = min(open_value, close) - 1.1
    stamp = (start + timedelta(days=index)).isoformat()
    candles.append({"time": stamp, "open": open_value, "high": high, "low": low, "close": close})
    volume.append({"time": stamp, "value": 100000 + (index * 1000)})
  return {"symbol": "ABC", "timeframe": "daily", "candles": candles, "volume": volume}


def test_analyze_symbol_reuses_one_ohlcv_fetch(monkeypatch):
  service = McpPriceActionService(_settings())
  calls = []

  def fake_fetch(symbol, timeframe):
    calls.append((symbol, timeframe))
    return _payload()

  monkeypatch.setattr(service, "_fetch_raw_payload", fake_fetch)

  result = service.analyze_symbol("NSE:ABC-EQ", "1D", 120)

  assert calls == [("ABC", "1D")]
  assert result["meta"]["symbol"] == "ABC"
  assert result["meta"]["bars_analyzed"] == 120
  assert result["meta"]["reuse_contract"] == [
    "backend.services.chart_service.fetch_ohlcv_payload",
    "backend.services.technical_utils",
  ]
  assert result["data_quality"]["status"] == "PASS"
  assert 0 <= result["score"]["overall"] <= 100


def test_invalid_symbol_is_rejected_without_querying(monkeypatch):
  service = McpPriceActionService(_settings())
  monkeypatch.setattr(
    service,
    "_fetch_raw_payload",
    lambda *_args: (_ for _ in ()).throw(AssertionError("database must not be queried")),
  )

  with pytest.raises(McpServiceError) as exc_info:
    service.get_ohlcv("ABC'; DELETE FROM X --", "1D", 100)

  assert exc_info.value.code == "INVALID_ARGUMENT"


def test_scan_uses_existing_price_action_service_rows(monkeypatch):
  service = McpPriceActionService(_settings())
  monkeypatch.setattr(
    service,
    "_existing_price_action_rows",
    lambda _timeframe, _limit: [
      {
        "symbol": "ABC",
        "price": 100,
        "priceActionScore": 82,
        "techStatus": "Strong",
        "trendStructure": "Strong Uptrend",
        "nearestSupport": 98,
        "nearestResistance": 112,
        "ltcDate": "2026-09-16",
      },
      {"symbol": "LOW", "price": 50, "priceActionScore": 45},
    ],
  )

  payload = service.scan_price_action(min_score=75, near_support_pct=3, min_resistance_distance_pct=8)

  assert payload["count"] == 1
  assert payload["results"][0]["symbol"] == "ABC"
  assert payload["source"] == "existing /api/technicals/price-action service"
