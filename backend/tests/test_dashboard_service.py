from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import services.dashboard_service as dashboard_service


def test_resolve_effective_trading_window_skips_partial_latest_date(monkeypatch):
    rows = [
        {'trading_date': datetime(2026, 6, 1), 'row_count': 783},
        {'trading_date': datetime(2026, 6, 2), 'row_count': 783},
        {'trading_date': datetime(2026, 6, 3), 'row_count': 782},
        {'trading_date': datetime(2026, 6, 4), 'row_count': 821},
        {'trading_date': datetime(2026, 6, 5), 'row_count': 334},
    ]
    monkeypatch.setattr(dashboard_service, '_fetch_trading_date_counts', lambda conn, view: rows)

    latest_date, previous_date, count = dashboard_service._resolve_effective_trading_window(object(), 'nse_nifty500_daily_raw_data_dev')

    assert latest_date == datetime(2026, 6, 4)
    assert previous_date == datetime(2026, 6, 3)
    assert count == 821


def test_fetch_top_movers_fast_uses_effective_latest_date(monkeypatch):
    captured = {}

    monkeypatch.setattr(dashboard_service, '_resolve_close_column', lambda conn, view: 'CLOSE_PRICE')
    monkeypatch.setattr(dashboard_service, '_resolve_volume_column', lambda conn, view: 'VOLUME')
    monkeypatch.setattr(
        dashboard_service,
        '_resolve_effective_trading_window',
        lambda conn, view, min_rows=25: (
            datetime(2026, 6, 4),
            datetime(2026, 6, 3),
            821,
        ),
    )

    def fake_execute_query(conn, sql, params=None):
        captured['sql'] = sql
        captured['params'] = params or {}
        return []

    monkeypatch.setattr(dashboard_service, '_execute_query', fake_execute_query)

    result = dashboard_service._fetch_top_movers_fast(object(), 'NSE_NIFTY500_DAILY_RAW_DATA_DEV', limit=5)

    assert result == []
    assert 'WITH current_rows AS (' in captured['sql']
    assert captured['params']['latest_date'] == datetime(2026, 6, 4)
    assert captured['params']['previous_market_date'] == datetime(2026, 6, 3)
    assert captured['params']['limit'] == 5
