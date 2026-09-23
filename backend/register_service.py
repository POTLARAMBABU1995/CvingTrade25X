import json
import os
import re
import hashlib
import secrets
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional, Tuple

try:  # pragma: no cover
    import oracledb  # type: ignore
except Exception:  # pragma: no cover
    oracledb = None

from werkzeug.security import generate_password_hash, check_password_hash

from db import _acquire_connection, build_dsn

REGISTER_DB_BACKEND = (
    os.getenv('REGISTER_DB_BACKEND')
    or os.getenv('REGISTER_DB_DRIVER')
    or 'oracle'
).strip().lower()
REGISTER_ORACLE_SCHEMA = (os.getenv('REGISTER_ORACLE_SCHEMA') or '').strip()
SESSION_TTL_MINUTES = os.getenv('SESSION_TTL_MINUTES', '1440')
QUICK_MPIN_TTL_HOURS = os.getenv('QUICK_MPIN_TTL_HOURS', '168')
PASSWORD_REAUTH_HOURS = os.getenv('PASSWORD_REAUTH_HOURS', '168')

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
PAN_RE = re.compile(r'^[A-Z]{5}[0-9]{4}[A-Z]$')
AADHAAR_RE = re.compile(r'^\d{4}$')
HEX64_RE = re.compile(r'^[0-9a-fA-F]{64}$')
MOBILE10_RE = re.compile(r'^[6-9]\d{9}$')
CLIENT_ID_RE = re.compile(r'^[A-Z0-9][A-Z0-9_-]{2,49}$')


def _is_oracle_backend() -> bool:
    return REGISTER_DB_BACKEND in ('oracle', 'oracledb')


def _oracle_backend_required_message() -> str:
    return 'Oracle backend required. Set REGISTER_DB_BACKEND=oracle.'


def _session_ttl_minutes() -> int:
    try:
        minutes = int(str(SESSION_TTL_MINUTES).strip())
    except Exception:
        minutes = 30
    return max(15, minutes)


def _quick_mpin_ttl_hours() -> int:
    try:
        hours = int(str(QUICK_MPIN_TTL_HOURS).strip())
    except Exception:
        hours = 168
    return max(1, hours)


def _password_reauth_hours() -> int:
    try:
        hours = int(str(PASSWORD_REAUTH_HOURS).strip())
    except Exception:
        hours = 168
    return max(24, hours)


def _password_reauth_delta() -> timedelta:
    return timedelta(hours=_password_reauth_hours())


def _oracle_schema() -> Optional[str]:
    if not REGISTER_ORACLE_SCHEMA:
        return None
    return REGISTER_ORACLE_SCHEMA.upper()


def _oracle_table_name(base: str) -> str:
    table = base.upper()
    schema = _oracle_schema()
    if schema:
        return f'{schema}.{table}'
    return table


def _require_oracledb() -> None:
    if oracledb is None:
        raise RuntimeError('python-oracledb is not installed. Run: pip install oracledb')


def _get_oracle_connection():
    _require_oracledb()
    return _acquire_connection()


def _isoformat(dt: datetime) -> str:
    # JS Date.parse is more reliable without microseconds.
    dt = dt.replace(microsecond=0)
    return dt.isoformat() + 'Z'


def _now_utc() -> Tuple[datetime, str]:
    dt = datetime.utcnow()
    return dt, _isoformat(dt)


def _normalize_oracle_value(column: str, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, datetime):
        if column == 'dob':
            return value.date().isoformat()
        return _isoformat(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


def _oracle_row_to_dict(cur, row) -> Dict[str, Any]:
    columns = [col[0].lower() for col in (cur.description or []) if col and col[0]]
    out: Dict[str, Any] = {}
    for idx, column in enumerate(columns):
        out[column] = _normalize_oracle_value(column, row[idx])
    return out


def _oracle_table_exists(conn, table_name: str) -> bool:
    name = table_name.upper()
    schema = _oracle_schema()
    with conn.cursor() as cur:
        if schema:
            cur.execute(
                'SELECT COUNT(*) FROM all_tables WHERE owner = :owner AND table_name = :name',
                {'owner': schema, 'name': name}
            )
        else:
            cur.execute(
                'SELECT COUNT(*) FROM user_tables WHERE table_name = :name',
                {'name': name}
            )
        return (cur.fetchone() or [0])[0] > 0


def _oracle_column_exists(conn, table_name: str, column_name: str) -> bool:
    name = table_name.upper()
    column = column_name.upper()
    schema = _oracle_schema()
    with conn.cursor() as cur:
        if schema:
            cur.execute(
                'SELECT COUNT(*) FROM all_tab_columns WHERE owner = :owner AND table_name = :table_name AND column_name = :column_name',
                {'owner': schema, 'table_name': name, 'column_name': column}
            )
        else:
            cur.execute(
                'SELECT COUNT(*) FROM user_tab_columns WHERE table_name = :table_name AND column_name = :column_name',
                {'table_name': name, 'column_name': column}
            )
        return (cur.fetchone() or [0])[0] > 0


def _oracle_index_exists(conn, index_name: str) -> bool:
    name = index_name.upper()
    schema = _oracle_schema()
    with conn.cursor() as cur:
        if schema:
            cur.execute(
                'SELECT COUNT(*) FROM all_indexes WHERE owner = :owner AND index_name = :name',
                {'owner': schema, 'name': name}
            )
        else:
            cur.execute(
                'SELECT COUNT(*) FROM user_indexes WHERE index_name = :name',
                {'name': name}
            )
        return (cur.fetchone() or [0])[0] > 0


def _split_owner_table(qualified_name: str) -> Tuple[Optional[str], str]:
    raw = str(qualified_name or '').strip()
    if '.' in raw:
        owner, table = raw.rsplit('.', 1)
        return owner.strip('"').upper(), table.strip('"').upper()
    return _oracle_schema(), raw.strip('"').upper()


def _primary_key_constraint_names(conn, qualified_table: str) -> set[str]:
    owner, table = _split_owner_table(qualified_table)
    with conn.cursor() as cur:
        if owner:
            cur.execute(
                '''
                SELECT CONSTRAINT_NAME
                  FROM ALL_CONSTRAINTS
                 WHERE OWNER = :owner
                   AND TABLE_NAME = :table_name
                   AND CONSTRAINT_TYPE = 'P'
                ''',
                {'owner': owner, 'table_name': table}
            )
        else:
            cur.execute(
                '''
                SELECT CONSTRAINT_NAME
                  FROM USER_CONSTRAINTS
                 WHERE TABLE_NAME = :table_name
                   AND CONSTRAINT_TYPE = 'P'
                ''',
                {'table_name': table}
            )
        return {str(row[0]).upper() for row in (cur.fetchall() or []) if row and row[0]}


def _is_primary_key_id_violation(conn, qualified_table: str, exc: Exception) -> bool:
    message = str(exc or '')
    if 'ORA-00001' not in message.upper():
        return False
    try:
        pk_names = _primary_key_constraint_names(conn, qualified_table)
    except Exception:
        return False
    upper_message = message.upper()
    return any(name in upper_message for name in pk_names)


def _next_explicit_id(conn, qualified_table: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f'LOCK TABLE {qualified_table} IN EXCLUSIVE MODE')
        cur.execute(f'SELECT NVL(MAX(ID), 0) FROM {qualified_table}')
        row = cur.fetchone()
        return int(row[0] or 0) + 1 if row else 1


def _generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def _session_expiry(now: Optional[datetime] = None) -> datetime:
    now = now or datetime.utcnow()
    return now + timedelta(minutes=_session_ttl_minutes())


def _quick_mpin_expiry(now: Optional[datetime] = None) -> datetime:
    now = now or datetime.utcnow()
    return now + timedelta(hours=_quick_mpin_ttl_hours())


def create_session(registration_id: int,
                   metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not _is_oracle_backend():
        raise RuntimeError(_oracle_backend_required_message())
    meta = metadata or {}
    now = datetime.utcnow()
    expires_at = _session_expiry(now)
    token = _generate_session_token()
    sessions_table = _oracle_table_name('AUTH_SESSIONS')
    session_payload = {
        'registration_id': registration_id,
        'session_token': token,
        'created_at': now,
        'last_seen_at': now,
        'expires_at': expires_at,
        'login_ip': meta.get('source_ip'),
        'user_agent': meta.get('user_agent'),
        'metadata_json': json.dumps(meta, ensure_ascii=False),
    }
    insert_sql = f'''
        INSERT INTO {sessions_table} (
            REGISTRATION_ID, SESSION_TOKEN, CREATED_AT,
            LAST_SEEN_AT, EXPIRES_AT, LOGIN_IP, USER_AGENT, METADATA_JSON
        ) VALUES (
            :registration_id, :session_token, :created_at,
            :last_seen_at, :expires_at, :login_ip, :user_agent, :metadata_json
        )
    '''
    insert_with_id_sql = f'''
        INSERT INTO {sessions_table} (
            ID, REGISTRATION_ID, SESSION_TOKEN, CREATED_AT,
            LAST_SEEN_AT, EXPIRES_AT, LOGIN_IP, USER_AGENT, METADATA_JSON
        ) VALUES (
            :id, :registration_id, :session_token, :created_at,
            :last_seen_at, :expires_at, :login_ip, :user_agent, :metadata_json
        )
    '''
    with _get_oracle_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(insert_sql, session_payload)
        except Exception as exc:
            if not _is_primary_key_id_violation(conn, sessions_table, exc):
                raise
            session_payload = dict(session_payload)
            session_payload['id'] = _next_explicit_id(conn, sessions_table)
            with conn.cursor() as cur:
                cur.execute(insert_with_id_sql, session_payload)
        conn.commit()
    return {
        'token': token,
        'expires_at': _isoformat(expires_at),
        'timeout_minutes': _session_ttl_minutes(),
    }


def validate_session(token: str,
                     metadata: Optional[Dict[str, Any]] = None,
                     refresh: bool = True) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    if not _is_oracle_backend():
        return None
    sessions_table = _oracle_table_name('AUTH_SESSIONS')
    now = datetime.utcnow()
    with _get_oracle_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f'''
                SELECT ID, REGISTRATION_ID, EXPIRES_AT, LOGOUT_AT
                  FROM {sessions_table}
                 WHERE SESSION_TOKEN = :session_token
                ''',
                {'session_token': token}
            )
            row = cur.fetchone()
            if not row:
                return None
            session_id, registration_id, expires_at, logout_at = row
            if logout_at is not None:
                return None
            if expires_at is not None and isinstance(expires_at, datetime):
                if expires_at <= now:
                    return None
            new_expires_at = expires_at
            if refresh:
                new_expires_at = _session_expiry(now)
            cur.execute(
                f'''
                UPDATE {sessions_table}
                   SET LAST_SEEN_AT = :last_seen_at,
                       EXPIRES_AT = :expires_at
                 WHERE ID = :session_id
                ''',
                {
                    'last_seen_at': now,
                    'expires_at': new_expires_at or expires_at,
                    'session_id': session_id,
                }
            )
        conn.commit()
    return {
        'session_id': session_id,
        'registration_id': registration_id,
        'expires_at': _isoformat(new_expires_at or expires_at),
        'timeout_minutes': _session_ttl_minutes(),
    }


def logout_session(token: str) -> bool:
    if not token:
        return False
    if not _is_oracle_backend():
        return False
    sessions_table = _oracle_table_name('AUTH_SESSIONS')
    now = datetime.utcnow()
    with _get_oracle_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f'''
                UPDATE {sessions_table}
                   SET LOGOUT_AT = :logout_at
                 WHERE SESSION_TOKEN = :session_token
                   AND LOGOUT_AT IS NULL
                ''',
                {'logout_at': now, 'session_token': token}
            )
            updated = cur.rowcount or 0
        conn.commit()
    return updated > 0


def init_registration_db(db_path: Optional[str] = None) -> None:
    """Ensure the registrations database and schema exist."""
    if not _is_oracle_backend():
        raise RuntimeError(_oracle_backend_required_message())
    _init_oracle_registration_db()


def _init_oracle_registration_db() -> None:
    _require_oracledb()
    registrations_table = _oracle_table_name('REGISTRATIONS')
    activity_table = _oracle_table_name('LOGIN_ACTIVITY')
    sessions_table = _oracle_table_name('AUTH_SESSIONS')
    quick_mpin_table = _oracle_table_name('AUTH_QUICK_MPIN')
    with _get_oracle_connection() as conn:
        with conn.cursor() as cur:
            if not _oracle_table_exists(conn, 'REGISTRATIONS'):
                cur.execute(
                    f"""
                    CREATE TABLE {registrations_table} (
                        ID NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                        CLIENT_ID VARCHAR2(50) NOT NULL,
                        FULL_NAME VARCHAR2(150) NOT NULL,
                        EMAIL VARCHAR2(150) NOT NULL,
                        MOBILE_E164 VARCHAR2(20) NOT NULL,
                        DOB DATE NOT NULL,
                        GENDER CHAR(1),
                        PAN VARCHAR2(10),
                        AADHAAR_LAST4 VARCHAR2(4),
                        EXP_MONTHS NUMBER(5) DEFAULT 0,
                        PASSWORD_HASH VARCHAR2(512) NOT NULL,
                        PASSWORD_ALGO VARCHAR2(30) NOT NULL,
                        MPIN_HASH VARCHAR2(512),
                        MPIN_ALGO VARCHAR2(30),
                        CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                        UPDATED_AT TIMESTAMP,
                        LAST_PASSWORD_AUTH_AT TIMESTAMP,
                        METADATA_JSON CLOB,
                        CONSTRAINT UQ_REGISTRATIONS_CLIENT UNIQUE (CLIENT_ID),
                        CONSTRAINT UQ_REGISTRATIONS_EMAIL UNIQUE (EMAIL),
                        CONSTRAINT UQ_REGISTRATIONS_MOBILE UNIQUE (MOBILE_E164)
                    )
                    """
                )
            if _oracle_table_exists(conn, 'REGISTRATIONS') and not _oracle_column_exists(conn, 'REGISTRATIONS', 'LAST_PASSWORD_AUTH_AT'):
                cur.execute(
                    f"ALTER TABLE {registrations_table} ADD (LAST_PASSWORD_AUTH_AT TIMESTAMP)"
                )
            if not _oracle_table_exists(conn, 'LOGIN_ACTIVITY'):
                cur.execute(
                    f"""
                    CREATE TABLE {activity_table} (
                        ID NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                        REGISTRATION_ID NUMBER NOT NULL,
                        LOGIN_TIME TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                        LOGIN_IP VARCHAR2(50),
                        LOGIN_DEVICE VARCHAR2(255),
                        LOCATION VARCHAR2(120),
                        METHOD_USED VARCHAR2(30),
                        METADATA_JSON CLOB,
                        CONSTRAINT FK_LOGIN_ACTIVITY_REG
                          FOREIGN KEY (REGISTRATION_ID)
                          REFERENCES {_oracle_table_name('REGISTRATIONS')}(ID)
                    )
                    """
                )
            if not _oracle_table_exists(conn, 'AUTH_SESSIONS'):
                cur.execute(
                    f"""
                    CREATE TABLE {sessions_table} (
                        ID NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                        REGISTRATION_ID NUMBER NOT NULL,
                        SESSION_TOKEN VARCHAR2(128) NOT NULL,
                        CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                        LAST_SEEN_AT TIMESTAMP,
                        EXPIRES_AT TIMESTAMP NOT NULL,
                        LOGOUT_AT TIMESTAMP,
                        LOGIN_IP VARCHAR2(50),
                        USER_AGENT VARCHAR2(255),
                        METADATA_JSON CLOB,
                        CONSTRAINT FK_AUTH_SESSIONS_REG
                          FOREIGN KEY (REGISTRATION_ID)
                          REFERENCES {_oracle_table_name('REGISTRATIONS')}(ID),
                        CONSTRAINT UQ_AUTH_SESSIONS_TOKEN UNIQUE (SESSION_TOKEN)
                    )
                    """
                )
            if not _oracle_table_exists(conn, 'AUTH_QUICK_MPIN'):
                cur.execute(
                    f"""
                    CREATE TABLE {quick_mpin_table} (
                        ID NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                        REGISTRATION_ID NUMBER NOT NULL,
                        TOKEN_HASH VARCHAR2(64) NOT NULL,
                        CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                        EXPIRES_AT TIMESTAMP NOT NULL,
                        LAST_USED_AT TIMESTAMP,
                        REVOKED_AT TIMESTAMP,
                        LOGIN_IP VARCHAR2(50),
                        USER_AGENT VARCHAR2(255),
                        METADATA_JSON CLOB,
                        CONSTRAINT FK_AUTH_QUICK_MPIN_REG
                          FOREIGN KEY (REGISTRATION_ID)
                          REFERENCES {_oracle_table_name('REGISTRATIONS')}(ID),
                        CONSTRAINT UQ_AUTH_QUICK_MPIN_TOKEN UNIQUE (TOKEN_HASH)
                    )
                    """
                )
            if not _oracle_index_exists(conn, 'IDX_LOGIN_ACTIVITY_USER'):
                cur.execute(
                    f"CREATE INDEX IDX_LOGIN_ACTIVITY_USER ON {activity_table} (REGISTRATION_ID)"
                )
            if not _oracle_index_exists(conn, 'IDX_AUTH_SESSIONS_REG'):
                cur.execute(
                    f"CREATE INDEX IDX_AUTH_SESSIONS_REG ON {sessions_table} (REGISTRATION_ID)"
                )
            if not _oracle_index_exists(conn, 'IDX_AUTH_SESSIONS_EXPIRES'):
                cur.execute(
                    f"CREATE INDEX IDX_AUTH_SESSIONS_EXPIRES ON {sessions_table} (EXPIRES_AT)"
                )
            if not _oracle_index_exists(conn, 'IDX_AUTH_QUICK_MPIN_REG'):
                cur.execute(
                    f"CREATE INDEX IDX_AUTH_QUICK_MPIN_REG ON {quick_mpin_table} (REGISTRATION_ID)"
                )
            if not _oracle_index_exists(conn, 'IDX_AUTH_QUICK_MPIN_EXPIRES'):
                cur.execute(
                    f"CREATE INDEX IDX_AUTH_QUICK_MPIN_EXPIRES ON {quick_mpin_table} (EXPIRES_AT)"
                )
        conn.commit()


def _normalize_mobile(value: str) -> Tuple[Optional[str], Optional[str]]:
    if not value:
        return None, None
    digits = re.sub(r'\D', '', value)
    if len(digits) == 12 and digits.startswith('91'):
        digits = digits[2:]
    if len(digits) != 10:
        return None, None
    if not MOBILE10_RE.match(digits):
        return None, None
    return digits, '+91' + digits


def _identifier_matches_user(identifier: str, user: Dict[str, Any]) -> bool:
    if not identifier or not user:
        return False
    value = str(identifier).strip()
    if not value:
        return False
    lower = value.lower()
    upper = value.upper()
    _digits, mobile_e164 = _normalize_mobile(value)
    if user.get('email') and str(user.get('email')).lower() == lower:
        return True
    if user.get('client_id') and str(user.get('client_id')).lower() == lower:
        return True
    if user.get('pan') and str(user.get('pan')).upper() == upper:
        return True
    if mobile_e164 and user.get('mobile_e164') == mobile_e164:
        return True
    return False


def _compute_client_id(mobile_digits: str) -> str:
    mid = mobile_digits[3:7] if len(mobile_digits) >= 7 else mobile_digits.zfill(4)
    return f'CT25X{mid}'


def _normalize_client_id(value: Any) -> Optional[str]:
    text = str(value or '').strip().upper()
    if not text:
        return None
    return text if CLIENT_ID_RE.fullmatch(text) else None


def _is_password_complex(password: str) -> bool:
    if len(password) < 12:
        return False
    checks = [
        re.search(r'[A-Z]', password),
        re.search(r'[a-z]', password),
        re.search(r'[0-9]', password),
        re.search(r'[!@#$%&*]', password),
    ]
    return all(checks)


def _prepare_secret(secret: str) -> Tuple[str, str]:
    if not secret:
        raise ValueError('Secret is required')
    secret = secret.strip()
    if secret.startswith(('pbkdf2:', 'argon2:', 'scrypt:')):
        algo = secret.split(':', 1)[0]
        return secret, algo
    if HEX64_RE.match(secret):
        return secret.lower(), 'sha256'
    return generate_password_hash(secret), 'pbkdf2:sha256'


def register_user(payload: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None,
                  db_path: Optional[str] = None) -> Tuple[Dict[str, Any], int]:
    metadata = metadata or {}
    if not _is_oracle_backend():
        return {'ok': False, 'error': _oracle_backend_required_message()}, 500

    full_name = (payload.get('full_name') or payload.get('fullName') or '').strip()
    if not full_name:
        return {'ok': False, 'error': 'Full name is required.'}, 400
    if len(full_name) > 150:
        return {'ok': False, 'error': 'Full name is too long (max 150 characters).'}, 400

    email = (payload.get('email') or '').strip().lower()
    if not EMAIL_RE.match(email):
        return {'ok': False, 'error': 'Valid email address is required.'}, 400

    mobile_input = payload.get('mobile_e164') or payload.get('mobileNumber') or payload.get('mobile') or ''
    mobile_digits, mobile_e164 = _normalize_mobile(mobile_input)
    if not mobile_digits:
        return {'ok': False, 'error': 'Valid Indian mobile number is required.'}, 400

    dob_str = (payload.get('dob') or payload.get('date_of_birth') or '').strip()
    if not dob_str:
        return {'ok': False, 'error': 'Date of birth is required.'}, 400
    try:
        dob_dt = datetime.strptime(dob_str, '%Y-%m-%d').date()
    except ValueError:
        return {'ok': False, 'error': 'Date of birth must be in YYYY-MM-DD format.'}, 400
    today = datetime.utcnow().date()
    age_years = today.year - dob_dt.year - ((today.month, today.day) < (dob_dt.month, dob_dt.day))
    if age_years < 18:
        return {'ok': False, 'error': 'User must be at least 18 years old.'}, 400

    gender = (payload.get('gender') or '').strip().upper()
    if gender not in ('', 'M', 'F', 'O'):
        return {'ok': False, 'error': 'Gender must be M, F, O, or omitted.'}, 400
    gender_val = gender or None

    pan = (payload.get('pan') or '').strip().upper()
    if pan and not PAN_RE.match(pan):
        return {'ok': False, 'error': 'PAN must match format (5 letters, 4 digits, 1 letter).'}, 400

    aadhaar = (payload.get('aadhaar_last4') or payload.get('aadhaar') or '').strip()
    if aadhaar:
        if not AADHAAR_RE.match(aadhaar):
            return {'ok': False, 'error': 'Aadhaar last 4 must be exactly 4 digits.'}, 400
    else:
        aadhaar = None

    exp_months_raw = payload.get('exp_months') or payload.get('experience_months') or 0
    try:
        exp_months = max(0, int(exp_months_raw))
    except Exception:
        return {'ok': False, 'error': 'Trading experience must be a whole number representing months.'}, 400

    password_input = payload.get('password') or payload.get('password_hash') or payload.get('passwordHash')
    if not password_input:
        return {'ok': False, 'error': 'Password is required.'}, 400
    if not (password_input.startswith(('pbkdf2:', 'argon2:', 'scrypt:')) or HEX64_RE.match(password_input)):
        if not _is_password_complex(password_input):
            return {'ok': False, 'error': 'Password must be at least 12 characters with uppercase, lowercase, number, and special character.'}, 400
    try:
        password_hash, password_algo = _prepare_secret(password_input)
    except Exception as exc:
        return {'ok': False, 'error': f'Unable to process password: {exc}'}, 400

    mpin_input = payload.get('mpin') or payload.get('mpin_hash') or payload.get('mpinHash')
    mpin_hash = None
    mpin_algo = None
    if mpin_input:
        mpin_input = str(mpin_input).strip()
        if not (mpin_input.startswith(('pbkdf2:', 'argon2:', 'scrypt:')) or HEX64_RE.match(mpin_input)):
            if not re.fullmatch(r'\d{6}', mpin_input):
                return {'ok': False, 'error': 'MPIN must be exactly 6 digits.'}, 400
        try:
            mpin_hash, mpin_algo = _prepare_secret(mpin_input)
        except Exception as exc:
            return {'ok': False, 'error': f'Unable to process MPIN: {exc}'}, 400

    client_id_input = (
        payload.get('client_id')
        or payload.get('clientId')
        or payload.get('username')
    )
    client_id = _normalize_client_id(client_id_input) or _compute_client_id(mobile_digits)
    client_id_is_user_supplied = bool(client_id_input)
    if client_id_input and not _normalize_client_id(client_id_input):
        return {'ok': False, 'error': 'Client ID must be 3-50 characters using letters, numbers, underscore, or hyphen.'}, 400
    created_at_dt, created_at = _now_utc()

    meta = {
        'source_ip': metadata.get('source_ip'),
        'user_agent': metadata.get('user_agent'),
        'referrer': metadata.get('referrer'),
    }

    try:
        registrations_table = _oracle_table_name('REGISTRATIONS')
        with _get_oracle_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT ID FROM {registrations_table} WHERE EMAIL = :email",
                    {'email': email}
                )
                if cur.fetchone():
                    return {'ok': False, 'error': 'Email already registered.'}, 409
                cur.execute(
                    f"SELECT ID FROM {registrations_table} WHERE MOBILE_E164 = :mobile_e164",
                    {'mobile_e164': mobile_e164}
                )
                if cur.fetchone():
                    return {'ok': False, 'error': 'Mobile number already registered.'}, 409
                cur.execute(
                    f"SELECT ID FROM {registrations_table} WHERE CLIENT_ID = :client_id",
                    {'client_id': client_id}
                )
                if cur.fetchone():
                    if client_id_is_user_supplied:
                        return {'ok': False, 'error': 'Client ID already registered.'}, 409
                    client_id = f"{client_id}{datetime.utcnow().strftime('%f')[-2:]}"

                user_id_var = cur.var(int)
                cur.execute(
                    f'''
                    INSERT INTO {registrations_table} (
                        CLIENT_ID, FULL_NAME, EMAIL, MOBILE_E164, DOB, GENDER,
                        PAN, AADHAAR_LAST4, EXP_MONTHS,
                        PASSWORD_HASH, PASSWORD_ALGO,
                        MPIN_HASH, MPIN_ALGO,
                        CREATED_AT, METADATA_JSON
                    ) VALUES (
                        :client_id, :full_name, :email, :mobile_e164, :dob, :gender,
                        :pan, :aadhaar_last4, :exp_months,
                        :password_hash, :password_algo,
                        :mpin_hash, :mpin_algo,
                        :created_at, :metadata_json
                    ) RETURNING ID INTO :user_id
                    ''',
                    {
                        'client_id': client_id,
                        'full_name': full_name,
                        'email': email,
                        'mobile_e164': mobile_e164,
                        'dob': dob_dt,
                        'gender': gender_val,
                        'pan': pan or None,
                        'aadhaar_last4': aadhaar,
                        'exp_months': exp_months,
                        'password_hash': password_hash,
                        'password_algo': password_algo,
                        'mpin_hash': mpin_hash,
                        'mpin_algo': mpin_algo,
                        'created_at': created_at_dt,
                        'metadata_json': json.dumps(meta, ensure_ascii=False),
                        'user_id': user_id_var,
                    }
                )
                user_id_val = user_id_var.getvalue()
                if isinstance(user_id_val, list):
                    user_id_val = user_id_val[0]
                user_id = int(user_id_val)
            conn.commit()
    except Exception as exc:
        if 'ORA-00001' in str(exc):
            return {'ok': False, 'error': f'Database constraint error: {exc}'}, 409
        return {'ok': False, 'error': f'Database error: {exc}'}, 500

    return {
        'ok': True,
        'client_id': client_id,
        'user_id': user_id,
        'created_at': created_at
    }, 201


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        if cleaned.endswith('Z'):
            cleaned = cleaned[:-1]
        try:
            return datetime.fromisoformat(cleaned)
        except ValueError:
            return None
    return None


def _password_reauth_required(last_password_auth_at: Any,
                              now: Optional[datetime] = None) -> bool:
    now = now or datetime.utcnow()
    last_dt = _parse_iso_datetime(last_password_auth_at)
    if not last_dt:
        return True
    return last_dt + _password_reauth_delta() <= now


def _password_reauth_due_at(last_password_auth_at: Any,
                            now: Optional[datetime] = None) -> datetime:
    now = now or datetime.utcnow()
    last_dt = _parse_iso_datetime(last_password_auth_at)
    if not last_dt:
        return now
    return last_dt + _password_reauth_delta()


def _auth_policy_payload(last_password_auth_at: Any,
                         now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.utcnow()
    last_dt = _parse_iso_datetime(last_password_auth_at)
    due_at = _password_reauth_due_at(last_dt, now)
    return {
        'password_reauth_hours': _password_reauth_hours(),
        'last_password_auth_at': _isoformat(last_dt) if last_dt else None,
        'password_reauth_due_at': _isoformat(due_at) if due_at else None,
        'password_reauth_required': _password_reauth_required(last_dt, now),
    }


def find_user_by_id(user_id: Any,
                    db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if not user_id:
        return None
    if not _is_oracle_backend():
        return None
    try:
        user_id_val = int(user_id)
    except (TypeError, ValueError):
        return None
    registrations_table = _oracle_table_name('REGISTRATIONS')
    with _get_oracle_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f'SELECT * FROM {registrations_table} WHERE ID = :user_id',
                {'user_id': user_id_val}
            )
            row = cur.fetchone()
            if not row:
                return None
            return _oracle_row_to_dict(cur, row)


def create_quick_mpin_token(registration_id: int,
                            metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not _is_oracle_backend():
        raise RuntimeError(_oracle_backend_required_message())
    meta = metadata or {}
    now = datetime.utcnow()
    expires_at = _quick_mpin_expiry(now)
    token = _generate_session_token()
    token_hash = _sha256_hex(token)
    quick_table = _oracle_table_name('AUTH_QUICK_MPIN')
    quick_payload = {
        'registration_id': registration_id,
        'token_hash': token_hash,
        'created_at': now,
        'expires_at': expires_at,
        'login_ip': meta.get('source_ip'),
        'user_agent': meta.get('user_agent'),
        'metadata_json': json.dumps(meta, ensure_ascii=False),
    }
    insert_sql = f'''
        INSERT INTO {quick_table} (
            REGISTRATION_ID, TOKEN_HASH, CREATED_AT, EXPIRES_AT,
            LAST_USED_AT, REVOKED_AT, LOGIN_IP, USER_AGENT, METADATA_JSON
        ) VALUES (
            :registration_id, :token_hash, :created_at, :expires_at,
            NULL, NULL, :login_ip, :user_agent, :metadata_json
        )
    '''
    insert_with_id_sql = f'''
        INSERT INTO {quick_table} (
            ID, REGISTRATION_ID, TOKEN_HASH, CREATED_AT, EXPIRES_AT,
            LAST_USED_AT, REVOKED_AT, LOGIN_IP, USER_AGENT, METADATA_JSON
        ) VALUES (
            :id, :registration_id, :token_hash, :created_at, :expires_at,
            NULL, NULL, :login_ip, :user_agent, :metadata_json
        )
    '''
    with _get_oracle_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f'''
                UPDATE {quick_table}
                   SET REVOKED_AT = :revoked_at
                 WHERE REGISTRATION_ID = :registration_id
                   AND REVOKED_AT IS NULL
                   AND EXPIRES_AT > :revoked_at
                ''',
                {
                    'revoked_at': now,
                    'registration_id': registration_id,
                }
            )
        try:
            with conn.cursor() as cur:
                cur.execute(insert_sql, quick_payload)
        except Exception as exc:
            if not _is_primary_key_id_violation(conn, quick_table, exc):
                raise
            quick_payload = dict(quick_payload)
            quick_payload['id'] = _next_explicit_id(conn, quick_table)
            with conn.cursor() as cur:
                cur.execute(insert_with_id_sql, quick_payload)
        conn.commit()
    return {
        'token': token,
        'expires_at': _isoformat(expires_at),
    }


def resolve_quick_mpin_token(token: str) -> Optional[Dict[str, Any]]:
    if not token or not _is_oracle_backend():
        return None
    token_hash = _sha256_hex(token.strip())
    quick_table = _oracle_table_name('AUTH_QUICK_MPIN')
    now = datetime.utcnow()
    with _get_oracle_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f'''
                SELECT ID, REGISTRATION_ID, EXPIRES_AT, REVOKED_AT
                  FROM {quick_table}
                 WHERE TOKEN_HASH = :token_hash
                ''',
                {'token_hash': token_hash}
            )
            row = cur.fetchone()
            if not row:
                return None
            token_id, registration_id, expires_at, revoked_at = row
            if revoked_at is not None:
                return None
            if expires_at is not None and isinstance(expires_at, datetime):
                if expires_at <= now:
                    return None
            return {
                'id': token_id,
                'registration_id': registration_id,
                'expires_at': expires_at,
            }


def mark_quick_mpin_used(token_id: Any) -> None:
    if not token_id or not _is_oracle_backend():
        return
    try:
        token_id_val = int(token_id)
    except (TypeError, ValueError):
        return
    quick_table = _oracle_table_name('AUTH_QUICK_MPIN')
    now = datetime.utcnow()
    with _get_oracle_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f'''
                UPDATE {quick_table}
                   SET LAST_USED_AT = :last_used_at
                 WHERE ID = :token_id
                ''',
                {
                    'last_used_at': now,
                    'token_id': token_id_val,
                }
            )
        conn.commit()


def find_user_by_identifier(identifier: str,
                            db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    value = (identifier or '').strip()
    if not value:
        return None
    lower = value.lower()
    upper = value.upper()
    _digits, mobile_e164 = _normalize_mobile(value)
    if not _is_oracle_backend():
        return None
    registrations_table = _oracle_table_name('REGISTRATIONS')
    with _get_oracle_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f'''
                SELECT * FROM {registrations_table}
                WHERE LOWER(EMAIL) = :lower_value
                   OR LOWER(CLIENT_ID) = :lower_value
                   OR UPPER(PAN) = :upper_value
                   OR MOBILE_E164 = :mobile_e164
                ''',
                {
                    'lower_value': lower,
                    'upper_value': upper,
                    'mobile_e164': mobile_e164,
                }
            )
            row = cur.fetchone()
            if not row:
                return None
            return _oracle_row_to_dict(cur, row)


def _verify_secret(secret: str, stored_hash: Optional[str],
                   stored_algo: Optional[str]) -> bool:
    if not secret or not stored_hash:
        return False
    secret = str(secret).strip()
    if not secret:
        return False
    algo = (stored_algo or '').strip().lower()
    if not algo:
        if stored_hash.startswith(('pbkdf2:', 'argon2:', 'scrypt:')):
            algo = stored_hash.split(':', 1)[0]
        elif HEX64_RE.match(stored_hash):
            algo = 'sha256'
    if algo == 'sha256':
        if HEX64_RE.match(secret):
            return secret.lower() == stored_hash.lower()
        return _sha256_hex(secret) == stored_hash.lower()
    if secret.startswith(('pbkdf2:', 'argon2:', 'scrypt:')):
        return secret == stored_hash
    try:
        return check_password_hash(stored_hash, secret)
    except Exception:
        return False


def _normalize_dob(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    value = str(value).strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date().isoformat()
    except ValueError:
        return None


def _normalize_pan(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    value = str(value).strip().upper()
    return value or None


def _normalize_aadhaar_last4(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    digits = re.sub(r'\D', '', str(value))
    if len(digits) < 4:
        return None
    return digits[-4:]


def reset_credentials(payload: Dict[str, Any],
                      metadata: Optional[Dict[str, Any]] = None,
                      db_path: Optional[str] = None) -> Tuple[Dict[str, Any], int]:
    payload = payload or {}
    if not _is_oracle_backend():
        return {'ok': False, 'error': _oracle_backend_required_message()}, 500
    identifier = (
        payload.get('identifier')
        or payload.get('client_id')
        or payload.get('clientId')
        or payload.get('email')
        or payload.get('mobile')
        or payload.get('mobileNumber')
    )
    quick_token = (
        payload.get('quick_token')
        or payload.get('quickToken')
        or payload.get('quick_mpin_token')
        or payload.get('quickMpinToken')
    )
    if not identifier:
        return {'ok': False, 'error': 'Identifier is required.'}, 400

    dob_raw = payload.get('dob') or payload.get('date_of_birth')
    pan_raw = payload.get('pan')
    aadhaar_raw = payload.get('aadhaar_last4') or payload.get('aadhaar')

    dob = _normalize_dob(dob_raw)
    pan = _normalize_pan(pan_raw)
    aadhaar = _normalize_aadhaar_last4(aadhaar_raw)

    if dob_raw and not dob:
        return {'ok': False, 'error': 'Date of birth must be in YYYY-MM-DD format.'}, 400
    if aadhaar_raw and not aadhaar:
        return {'ok': False, 'error': 'Aadhaar last 4 must be exactly 4 digits.'}, 400

    if not any([dob, pan, aadhaar]):
        return {'ok': False, 'error': 'Provide DOB, PAN, or Aadhaar last 4 digits.'}, 400

    user = find_user_by_identifier(identifier, db_path=db_path)
    if not user:
        return {'ok': False, 'error': 'User not found.'}, 404

    matches = []
    if dob:
        matches.append((user.get('dob') or '').strip() == dob)
    if pan:
        matches.append((user.get('pan') or '').strip().upper() == pan)
    if aadhaar:
        matches.append((user.get('aadhaar_last4') or '').strip() == aadhaar)
    if not any(matches):
        return {'ok': False, 'error': 'Invalid verification details.'}, 401

    new_password_input = payload.get('new_password') or payload.get('password')
    new_mpin_input = payload.get('new_mpin') or payload.get('mpin')

    updates: list[Tuple[str, Any]] = []
    updated_items = []

    if new_password_input:
        new_password_input = str(new_password_input).strip()
        if not new_password_input:
            return {'ok': False, 'error': 'Password cannot be empty.'}, 400
        if not (new_password_input.startswith(('pbkdf2:', 'argon2:', 'scrypt:')) or HEX64_RE.match(new_password_input)):
            if not _is_password_complex(new_password_input):
                return {
                    'ok': False,
                    'error': 'Password must be at least 12 characters with uppercase, lowercase, number, and special character.'
                }, 400
        password_hash, password_algo = _prepare_secret(new_password_input)
        updates.append(('password_hash', password_hash))
        updates.append(('password_algo', password_algo))
        updated_items.append('password')

    if new_mpin_input:
        new_mpin_input = str(new_mpin_input).strip()
        if not (new_mpin_input.startswith(('pbkdf2:', 'argon2:', 'scrypt:')) or HEX64_RE.match(new_mpin_input)):
            if not re.fullmatch(r'\d{6}', new_mpin_input):
                return {'ok': False, 'error': 'MPIN must be exactly 6 digits.'}, 400
        mpin_hash, mpin_algo = _prepare_secret(new_mpin_input)
        updates.append(('mpin_hash', mpin_hash))
        updates.append(('mpin_algo', mpin_algo))
        updated_items.append('mpin')

    if not updates:
        return {
            'ok': True,
            'message': 'Password authentication successful. You can set up a new password.',
            'user_id': user.get('id')
        }, 200

    updated_at_dt, updated_at = _now_utc()
    updates.append(('updated_at', updated_at_dt))

    registrations_table = _oracle_table_name('REGISTRATIONS')
    params = {col: val for col, val in updates}
    params['user_id'] = user.get('id')
    set_clause = ', '.join([f"{col.upper()} = :{col}" for col, _ in updates])
    try:
        with _get_oracle_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f'UPDATE {registrations_table} SET {set_clause} WHERE ID = :user_id',
                    params
                )
            conn.commit()
    except Exception as exc:
        return {'ok': False, 'error': f'Database error: {exc}'}, 500

    if len(updated_items) == 2:
        message = 'Password and MPIN updated successfully.'
    elif updated_items == ['mpin']:
        message = 'MPIN updated successfully.'
    else:
        message = 'Password updated successfully.'

    return {'ok': True, 'message': message}, 200


def log_login_activity(user_id: int, method: str,
                       metadata: Optional[Dict[str, Any]] = None,
                       db_path: Optional[str] = None) -> bool:
    meta = metadata or {}
    login_time_dt, login_time = _now_utc()
    if not _is_oracle_backend():
        return False
    activity_table = _oracle_table_name('LOGIN_ACTIVITY')
    try:
        with _get_oracle_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f'''
                    INSERT INTO {activity_table} (
                        REGISTRATION_ID, LOGIN_TIME, LOGIN_IP, LOGIN_DEVICE,
                        LOCATION, METHOD_USED, METADATA_JSON
                    ) VALUES (
                        :registration_id, :login_time, :login_ip, :login_device,
                        :location, :method_used, :metadata_json
                    )
                    ''',
                    {
                        'registration_id': user_id,
                        'login_time': login_time_dt,
                        'login_ip': meta.get('source_ip'),
                        'login_device': meta.get('user_agent'),
                        'location': meta.get('location'),
                        'method_used': method,
                        'metadata_json': json.dumps(meta, ensure_ascii=False),
                    }
                )
            conn.commit()
        return True
    except Exception:
        return False


def authenticate_user(payload: Dict[str, Any],
                      metadata: Optional[Dict[str, Any]] = None,
                      db_path: Optional[str] = None) -> Tuple[Dict[str, Any], int]:
    payload = payload or {}
    if not _is_oracle_backend():
        return {'ok': False, 'error': _oracle_backend_required_message()}, 500
    identifier = (
        payload.get('identifier')
        or payload.get('client_id')
        or payload.get('clientId')
        or payload.get('email')
        or payload.get('mobile')
        or payload.get('mobileNumber')
    )
    quick_token = (
        payload.get('quick_token')
        or payload.get('quickToken')
        or payload.get('quick_mpin_token')
        or payload.get('quickMpinToken')
    )
    password_input = (
        payload.get('password')
        or payload.get('password_hash')
        or payload.get('passwordHash')
    )
    mpin_input = (
        payload.get('mpin')
        or payload.get('mpin_hash')
        or payload.get('mpinHash')
    )

    if not identifier and not quick_token:
        return {'ok': False, 'error': 'Identifier is required.'}, 400
    if not password_input and not mpin_input:
        return {'ok': False, 'error': 'Password or MPIN is required.'}, 400

    now = datetime.utcnow()
    user: Optional[Dict[str, Any]] = None

    if password_input:
        if not identifier:
            return {'ok': False, 'error': 'Identifier is required.'}, 400
        user = find_user_by_identifier(identifier, db_path=db_path)
        if not user:
            return {'ok': False, 'error': 'User not found.'}, 404
        if not _verify_secret(password_input, user.get('password_hash'), user.get('password_algo')):
            return {'ok': False, 'error': 'Invalid credentials.'}, 401
        method = 'Password'
    elif mpin_input:
        token_row = resolve_quick_mpin_token(quick_token) if quick_token else None
        if token_row:
            user = find_user_by_id(token_row.get('registration_id'), db_path=db_path)
            if not user:
                return {'ok': False, 'error': 'User not found.'}, 404
            if identifier and not _identifier_matches_user(identifier, user):
                return {'ok': False, 'error': 'Identifier does not match session.'}, 401
        else:
            if not identifier:
                if quick_token:
                    return {'ok': False, 'error': 'Quick MPIN session expired. Please login with password.'}, 401
                return {'ok': False, 'error': 'Identifier is required.'}, 400
            user = find_user_by_identifier(identifier, db_path=db_path)
            if not user:
                return {'ok': False, 'error': 'User not found.'}, 404
        if not user.get('mpin_hash'):
            return {'ok': False, 'error': 'MPIN not configured.'}, 401
        if not _verify_secret(mpin_input, user.get('mpin_hash'), user.get('mpin_algo')):
            return {'ok': False, 'error': 'Invalid credentials.'}, 401
        if _password_reauth_required(user.get('last_password_auth_at'), now):
            return {'ok': False, 'error': 'Password required (weekly re-auth).'}, 401
        method = 'MPIN'
        if token_row:
            mark_quick_mpin_used(token_row.get('id'))
    else:
        return {'ok': False, 'error': 'Password or MPIN is required.'}, 400

    updated_at_dt, updated_at = _now_utc()
    registrations_table = _oracle_table_name('REGISTRATIONS')
    last_password_auth_at = user.get('last_password_auth_at') if user else None
    updates: list[Tuple[str, Any]] = [('updated_at', updated_at_dt)]
    if method == 'Password':
        updates.append(('last_password_auth_at', updated_at_dt))
        last_password_auth_at = updated_at_dt
    try:
        set_clause = ', '.join([f"{col.upper()} = :{col}" for col, _ in updates])
        params = {col: val for col, val in updates}
        params['user_id'] = user.get('id') if user else None
        with _get_oracle_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f'UPDATE {registrations_table} SET {set_clause} WHERE ID = :user_id',
                    params
                )
            conn.commit()
    except Exception:
        pass

    log_login_activity(user.get('id', 0), method, metadata, db_path=db_path)

    try:
        session_info = create_session(user.get('id', 0), metadata)
    except Exception as exc:
        return {'ok': False, 'error': f'Unable to create session: {exc}'}, 500

    quick_payload: Dict[str, Any] = {}
    if method == 'Password' and user.get('mpin_hash'):
        try:
            quick_info = create_quick_mpin_token(user.get('id', 0), metadata)
            quick_payload = {
                'quick_mpin_token': quick_info.get('token'),
                'quick_mpin_expires_at': quick_info.get('expires_at'),
            }
        except Exception:
            quick_payload = {}

    auth_policy = _auth_policy_payload(last_password_auth_at, now)

    return {
        'ok': True,
        'user': {
            'user_id': user.get('id'),
            'client_id': user.get('client_id'),
            'full_name': user.get('full_name'),
            'email': user.get('email'),
            'mobile_e164': user.get('mobile_e164'),
            'pan': user.get('pan'),
            'mpin_enabled': bool(user.get('mpin_hash')),
            'created_at': user.get('created_at'),
            'updated_at': updated_at
        },
        'session': session_info,
        'session_token': session_info.get('token'),
        'session_expires_at': session_info.get('expires_at'),
        'auth_policy': auth_policy,
        **quick_payload,
    }, 200


def record_login_activity(payload: Dict[str, Any],
                          metadata: Optional[Dict[str, Any]] = None,
                          db_path: Optional[str] = None) -> Tuple[Dict[str, Any], int]:
    payload = payload or {}
    if not _is_oracle_backend():
        return {'ok': False, 'error': _oracle_backend_required_message()}, 500
    user_id = payload.get('user_id') or payload.get('userId') or payload.get('registration_id')
    method = (payload.get('method') or payload.get('method_used') or payload.get('login_method') or '').strip()

    if not user_id:
        return {'ok': False, 'error': 'User id is required.'}, 400
    try:
        user_id_val = int(user_id)
    except (TypeError, ValueError):
        return {'ok': False, 'error': 'User id must be an integer.'}, 400

    if not method:
        method = 'Password'

    ok = log_login_activity(user_id_val, method, metadata, db_path=db_path)
    if not ok:
        return {'ok': False, 'error': 'Unable to record login activity.'}, 500

    return {'ok': True}, 201
