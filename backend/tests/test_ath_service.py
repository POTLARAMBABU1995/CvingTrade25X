from __future__ import annotations

from datetime import date
from pathlib import Path
import sys
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import services.ath_service as ath_service


class _FakeCursor:
    def __init__(self, conn: "_FakeConnection") -> None:
        self._conn = conn
        self.description = []
        self._rows = []

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def execute(self, sql: str, binds: dict[str, Any] | None = None) -> None:
        sql_text = str(sql or "")
        self._conn.sqls.append(sql_text)
        self._conn.binds.append(dict(binds or {}))
        upper_sql = sql_text.upper()
        if "ROWNUM = 0" in upper_sql:
            self.description = [
                ("SYMBOL",),
                ("TRADING_DATE",),
                ("HIGH",),
                ("CLOSE_PRICE",),
            ]
            self._rows = []
            return
        if "ROW_NUMBER() OVER" in upper_sql:
            self.description = [
                ("SYMBOL",),
                ("ATH",),
                ("ATH_DATE",),
            ]
            self._rows = list(self._conn.ranked_rows)
            return
        if "GROUP BY" in upper_sql and "MAX(" in upper_sql:
            self.description = [
                ("SYMBOL",),
                ("ATH",),
            ]
            self._rows = list(self._conn.group_rows)
            return
        self.description = []
        self._rows = []

    def fetchall(self):
        return list(self._rows)


class _FakeConnection:
    def __init__(self, *, ranked_rows, group_rows) -> None:
        self.ranked_rows = list(ranked_rows)
        self.group_rows = list(group_rows)
        self.sqls: list[str] = []
        self.binds: list[dict[str, Any]] = []

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self)

    def close(self) -> None:
        return None


def _reset_meta_cache() -> None:
    ath_service._SOURCE_META_CACHE = None  # type: ignore[attr-defined]


def test_ranked_ath_query_uses_high_column(monkeypatch):
    conn = _FakeConnection(
        ranked_rows=[
            ("ABB", 9020.0, date(2024, 7, 5)),
            ("AADHARHFC", 520.5, date(2025, 1, 10)),
        ],
        group_rows=[],
    )
    monkeypatch.setattr(ath_service, "get_oracle_connection", lambda: conn)
    monkeypatch.setattr(ath_service, "_ATH_SOURCE_TABLE", "NSE_NIFTY500_DAILY_RAW_DATA_DEV", raising=False)
    _reset_meta_cache()

    records = ath_service.get_all_time_high_for_symbols(
        ["ABB", "AADHARHFC"],
        include_date=True,
        endpoint="/api/test-ath",
    )

    assert records["ABB"]["ath"] == 9020.0
    assert records["ABB"]["ath_date"] == "2024-07-05"
    assert records["AADHARHFC"]["ath"] == 520.5
    assert any("NSE_NIFTY500_DAILY_RAW_DATA_DEV" in sql.upper() for sql in conn.sqls)
    assert any(
        "ORDER BY T.HIGH DESC, T.TRADING_DATE DESC" in sql.upper()
        for sql in conn.sqls
    )


def test_get_ath_map_for_all_symbols(monkeypatch):
    conn = _FakeConnection(
        ranked_rows=[],
        group_rows=[
            ("ABB", 9020.0),
            ("ACC", 2772.25),
        ],
    )
    monkeypatch.setattr(ath_service, "get_oracle_connection", lambda: conn)
    _reset_meta_cache()

    ath_map = ath_service.get_ath_map(None, endpoint="/api/test-ath-all")

    assert ath_map == {"ABB": 9020.0, "ACC": 2772.25}
    assert any("GROUP BY" in sql.upper() and " IN (" not in sql.upper() for sql in conn.sqls)


def test_get_ath_map_sets_none_for_missing_symbol(monkeypatch):
    conn = _FakeConnection(
        ranked_rows=[],
        group_rows=[
            ("ABB", 9020.0),
        ],
    )
    monkeypatch.setattr(ath_service, "get_oracle_connection", lambda: conn)
    _reset_meta_cache()

    ath_map = ath_service.get_ath_map(["ABB", "MISSING"], endpoint="/api/test-ath-missing")

    assert ath_map["ABB"] == 9020.0
    assert ath_map["MISSING"] is None
