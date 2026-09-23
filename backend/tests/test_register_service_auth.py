from datetime import datetime, timedelta
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import register_service as svc


def test_authenticate_user_allows_direct_mpin_with_recent_password_auth(monkeypatch):
    now = datetime.utcnow()
    user = {
        'id': 7,
        'client_id': 'CT25X7000',
        'full_name': 'Trader One',
        'email': 'trader@example.com',
        'mobile_e164': '+919876543210',
        'pan': 'ABCDE1234F',
        'mpin_hash': 'hash',
        'mpin_algo': 'sha256',
        'created_at': '2026-04-02T12:00:00Z',
        'last_password_auth_at': now - timedelta(hours=1),
    }

    monkeypatch.setattr(svc, '_is_oracle_backend', lambda: True)
    monkeypatch.setattr(svc, 'find_user_by_identifier', lambda identifier, db_path=None: user)
    monkeypatch.setattr(svc, '_verify_secret', lambda secret, stored_hash, stored_algo: secret == '123456')
    monkeypatch.setattr(svc, 'log_login_activity', lambda user_id, method, metadata, db_path=None: True)
    monkeypatch.setattr(svc, 'create_session', lambda registration_id, metadata=None: {
        'token': 'session-token',
        'expires_at': '2026-04-03T12:00:00Z',
        'timeout_minutes': 1440,
    })

    class _Cursor:
        def execute(self, *_args, **_kwargs):
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Conn:
        def cursor(self):
            return _Cursor()

        def commit(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(svc, '_get_oracle_connection', lambda: _Conn())

    payload, status = svc.authenticate_user({'identifier': 'trader@example.com', 'mpin': '123456'})

    assert status == 200
    assert payload['ok'] is True
    assert payload['user']['user_id'] == 7
    assert payload['session_token'] == 'session-token'


def test_authenticate_user_rejects_direct_mpin_when_password_reauth_due(monkeypatch):
    user = {
        'id': 9,
        'client_id': 'CT25X9000',
        'email': 'reauth@example.com',
        'mobile_e164': '+919999999999',
        'mpin_hash': 'hash',
        'mpin_algo': 'sha256',
        'last_password_auth_at': None,
    }

    monkeypatch.setattr(svc, '_is_oracle_backend', lambda: True)
    monkeypatch.setattr(svc, 'find_user_by_identifier', lambda identifier, db_path=None: user)
    monkeypatch.setattr(svc, '_verify_secret', lambda secret, stored_hash, stored_algo: True)

    payload, status = svc.authenticate_user({'identifier': 'reauth@example.com', 'mpin': '123456'})

    assert status == 401
    assert payload['ok'] is False
    assert payload['error'] == 'Password required (weekly re-auth).'


def test_create_session_falls_back_to_explicit_id_on_pk_collision(monkeypatch):
    executed = []

    class _Cursor:
        def execute(self, sql, params=None):
            statement = ' '.join(str(sql).split())
            executed.append((statement, dict(params or {})))
            if 'INSERT INTO AUTH_SESSIONS (' in statement and ':id' not in statement:
                raise Exception('ORA-00001: unique constraint (CVING_APP.SYS_C007451) violated')
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Conn:
        def __init__(self):
            self.committed = False

        def cursor(self):
            return _Cursor()

        def commit(self):
            self.committed = True

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    conn = _Conn()
    monkeypatch.setattr(svc, '_is_oracle_backend', lambda: True)
    monkeypatch.setattr(svc, '_get_oracle_connection', lambda: conn)
    monkeypatch.setattr(svc, '_generate_session_token', lambda: 'session-token')
    monkeypatch.setattr(svc, '_is_primary_key_id_violation', lambda conn_obj, table, exc: True)
    monkeypatch.setattr(svc, '_next_explicit_id', lambda conn_obj, table: 362)

    payload = svc.create_session(2, {'source_ip': '127.0.0.1'})

    assert payload['token'] == 'session-token'
    assert conn.committed is True
    insert_statements = [entry for entry in executed if entry[0].startswith('INSERT INTO AUTH_SESSIONS')]
    assert len(insert_statements) == 2
    assert 'id' not in insert_statements[0][1]
    assert insert_statements[1][1]['id'] == 362
