from pathlib import Path
import sys
import types

from flask import Flask


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


class FakeCursor:
    def __init__(self):
        self.executed = []
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, binds=None):
        self.executed.append((sql, dict(binds or {})))
        if sql.strip().upper().startswith("DELETE"):
            self.rowcount = 3

    def fetchone(self):
        return [3]


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True


class FakePool:
    def __init__(self):
        self.cursor = FakeCursor()
        self.connection = FakeConnection(self.cursor)

    def acquire(self):
        return self.connection


fake_pool = FakePool()
db_pool_stub = types.ModuleType("db_pool")
db_pool_stub.pool = fake_pool
sys.modules["db_pool"] = db_pool_stub

import routes.corporate_actions as corporate_actions_route


def _client():
    app = Flask(__name__)
    app.register_blueprint(corporate_actions_route.bp)
    return app.test_client()


def test_delete_split_bonus_candidate_symbols_requires_confirmation():
    response = _client().post(
        "/api/corporate-actions/split-bonus-candidates/delete-symbols",
        json={"symbols": ["ABC"]},
    )

    assert response.status_code == 400
    assert response.get_json()["message"] == "Delete confirmation failed"


def test_delete_split_bonus_candidate_symbols_deletes_from_dev_table(monkeypatch):
    pool = FakePool()
    monkeypatch.setattr(corporate_actions_route, "pool", pool)

    response = _client().post(
        "/api/corporate-actions/split-bonus-candidates/delete-symbols",
        json={"confirm_text": "DELETE", "symbols": [" abc ", "ABC", "xyz"]},
    )

    payload = response.get_json()
    delete_sql = [sql for sql, _binds in pool.cursor.executed if sql.strip().upper().startswith("DELETE")][0]
    delete_binds = [binds for sql, binds in pool.cursor.executed if sql.strip().upper().startswith("DELETE")][0]

    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["symbols"] == ["ABC", "XYZ"]
    assert payload["deleted_rows"] == 3
    assert pool.connection.committed is True
    assert "DELETE FROM NSE_NIFTY500_DAILY_RAW_DATA_DEV" in delete_sql
    assert "UPPER(TRIM(SYMBOL)) IN (:sym_0, :sym_1)" in delete_sql
    assert delete_binds == {"sym_0": "ABC", "sym_1": "XYZ"}
