from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import services.trend_service as trend_service


def _series(points: int):
    start = datetime(1998, 1, 1)
    return [(start + timedelta(days=index), float(100 + index)) for index in range(points)]


def test_build_rows_extends_year_returns_from_available_history(monkeypatch):
    monkeypatch.setattr(trend_service, "get_all_time_high_for_symbols", lambda *args, **kwargs: {})
    monkeypatch.setattr(trend_service, "warn_if_ath_below_current", lambda *args, **kwargs: None)

    series_by_symbol = {
        "ABB": _series(7060),
        "SHORT": _series(200),
    }

    rows = trend_service.build_rows(series_by_symbol)
    abb = next(row for row in rows if row["symbol"] == "ABB")
    short = next(row for row in rows if row["symbol"] == "SHORT")
    closes = [value for _dt, value in series_by_symbol["ABB"]]
    expected_y25 = ((closes[-1] - closes[-(25 * trend_service.TRADING_DAYS_PER_YEAR + 1)]) / closes[-(25 * trend_service.TRADING_DAYS_PER_YEAR + 1)]) * 100.0

    assert abb["y25"] == f"{expected_y25:.2f}%"
    assert abb["y26"] != "-"
    assert abb["y27"] != "-"
    assert abb["y28"] != "-"
    assert "y28Sort" in abb
    assert "y29" not in abb
    assert short["y28"] == "-"


def test_return_column_metadata_includes_dynamic_max_year():
    metadata = trend_service.return_column_metadata_for_series({"ABB": _series(7060)})
    year_keys = [column["key"] for column in metadata if column.get("kind") == "year"]

    assert "y25" in year_keys
    assert "y26" in year_keys
    assert "y27" in year_keys
    assert "y28" in year_keys
    assert "y29" not in year_keys
