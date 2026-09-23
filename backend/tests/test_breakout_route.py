from datetime import datetime, timedelta
from pathlib import Path
import sys

from flask import Flask


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import routes.breakout as breakout_route
import services.strong_technicals_service as strong_technicals_service


def _build_client():
    app = Flask(__name__)
    app.register_blueprint(breakout_route.bp)
    return app.test_client()


def _candles(symbol: str, last_close: float):
    start = datetime(2026, 1, 1)
    rows = []
    for index in range(40):
        base = 100.0 + index
        close = last_close if index == 39 else base
        rows.append(
            {
                "date": start + timedelta(days=index),
                "open": close - 1.0,
                "high": close + 1.0,
                "low": close - 2.0,
                "close": close,
                "volume": 100000.0 + index,
            }
        )
    return rows


def test_breakout_route_uses_fast_compute_profile_and_existing_pagination(monkeypatch, tmp_path):
    service = strong_technicals_service
    service._cache.clear()
    monkeypatch.setattr(service, "_SNAPSHOT_DIR", tmp_path)
    monkeypatch.setattr(service, "fetch_latest_trade_date_from_oracle", lambda: None)
    monkeypatch.setattr(service.nse_mcap_svc, "enrich_rows_with_marketcap_index", lambda rows: rows)
    monkeypatch.setattr(service, "get_all_time_high_for_symbols", None)
    monkeypatch.setattr(
        service,
        "_compute_base_rows",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("breakout should not use full strong compute")),
    )
    monkeypatch.setattr(
        service,
        "fetch_recent_ohlc_series_from_oracle",
        lambda trading_days=280: {
            "AAA": _candles("AAA", 150.0),
            "BBB": _candles("BBB", 95.0),
        },
    )

    def fake_breakout(_candles_arg, _resistance, _volume_ratio, _ema_values):
        close = _candles_arg[-1]["close"]
        if close >= 150.0:
            return {"status": "Resistance Breakout", "score": 88.0, "flags": ["Resistance Breakout"]}
        return {"status": "No Breakout", "score": 0.0, "flags": []}

    monkeypatch.setattr(service, "_analyze_breakout", fake_breakout)

    response = _build_client().get(
        "/api/technicals/breakout?page=1&page_size=25&sort_by=breakoutScore&sort_dir=desc&latest_only=true"
    )

    payload = response.get_json()
    cache_key = service._cache_key_for_view("breakout", "daily", True)
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["count"] == 1
    assert payload["total"] == 1
    assert payload["rows"][0]["symbol"] == "AAA"
    assert payload["rows"][0]["breakoutStatus"] == "Resistance Breakout"
    assert payload["rows"][0]["breakoutScore"] == 88.0
    assert payload["summary"]["freshBreakouts"] == 1
    assert payload["meta"]["computeProfile"] == "breakout"
    assert payload["meta"]["sourceWindow"] == "recent_280_trading_days"
    assert "rawLoadDurationMs" in payload["meta"]
    assert Path(service._snapshot_path(cache_key)).exists()
    service._cache.clear()
