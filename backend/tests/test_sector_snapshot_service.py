from datetime import date
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import services.sector_snapshot_service as snapshot_service


class _FakeCursor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, dict | None]] = []
        self.batches: list[tuple[str, list[dict]]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql: str, binds: dict | None = None) -> None:
        self.executed.append((sql, binds))

    def executemany(self, sql: str, rows: list[dict]) -> None:
        self.batches.append((sql, rows))


class _FakeConnection:
    def __init__(self) -> None:
        self.cursor_instance = _FakeCursor()
        self.committed = False
        self.closed = False
        self.rolled_back = False

    def cursor(self) -> _FakeCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


def test_write_sector_wise_snapshot_accepts_route_stock_aliases_and_batches(monkeypatch):
    connection = _FakeConnection()
    monkeypatch.setattr(snapshot_service, 'get_oracle_connection', lambda: connection)

    snapshot_service.write_sector_wise_snapshot(
        'AUTO',
        date(2026, 7, 13),
        [{
            'stock': 'ashokley',
            'index': 'MID',
            'totalMcap': 93523.51,
            'mcapRank': 124,
            'price': 159.2,
            'ath': 215.42,
            'gapPct': -26.09,
            'high52w': 215.42,
            'low52w': 114.96,
            'ema20Flag': 'Y',
            'ema50Flag': 'N',
            'ema100Flag': 'N',
            'ema200Flag': 'N',
            'trend': 'Downtrend',
            'score': 28,
        }],
    )

    assert connection.committed is True
    assert connection.rolled_back is False
    assert connection.closed is True
    assert len(connection.cursor_instance.batches) == 1
    inserted_rows = connection.cursor_instance.batches[0][1]
    assert inserted_rows == [
        {
            'ltc_date': date(2026, 7, 13),
            'sector': 'AUTO',
            'symbol': 'ASHOKLEY',
            'idx_code': 'MID',
            'mcap': 93523.51,
            'mcap_rank': 124,
            'price': 159.2,
            'ath': 215.42,
            'gap': -26.09,
            'wh52': 215.42,
            'wl52': 114.96,
            'ema20': 'Y',
            'ema50': 'N',
            'ema100': 'N',
            'ema200': 'N',
            'trend': 'Downtrend',
            'score': 28,
            'payload_json': inserted_rows[0]['payload_json'],
        }
    ]
    audit_binds = next(
        binds
        for sql, binds in connection.cursor_instance.executed
        if 'NSE_SECTOR_CACHE_AUDIT_LOG' in sql
    )
    assert audit_binds == {
        'sector': 'AUTO',
        'ltc_date': date(2026, 7, 13),
        'row_count': 1,
    }
