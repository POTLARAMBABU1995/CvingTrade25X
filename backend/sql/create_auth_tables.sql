-- SQLite schema for CvingTrade25X auth (registration + login activity)

CREATE TABLE IF NOT EXISTS registrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    mobile_e164 TEXT NOT NULL UNIQUE,
    dob TEXT NOT NULL,
    gender TEXT,
    pan TEXT,
    aadhaar_last4 TEXT,
    exp_months INTEGER DEFAULT 0,
    password_hash TEXT NOT NULL,
    password_algo TEXT NOT NULL,
    mpin_hash TEXT,
    mpin_algo TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    metadata_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_registrations_email ON registrations(email);
CREATE INDEX IF NOT EXISTS idx_registrations_mobile ON registrations(mobile_e164);

CREATE TABLE IF NOT EXISTS login_activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    registration_id INTEGER NOT NULL,
    login_time TEXT NOT NULL,
    login_ip TEXT,
    login_device TEXT,
    location TEXT,
    method_used TEXT,
    metadata_json TEXT,
    FOREIGN KEY (registration_id) REFERENCES registrations(id)
);

CREATE INDEX IF NOT EXISTS idx_login_activity_user ON login_activity(registration_id);

CREATE TABLE IF NOT EXISTS auth_quick_mpin (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    registration_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_used_at TEXT,
    revoked_at TEXT,
    login_ip TEXT,
    user_agent TEXT,
    metadata_json TEXT,
    FOREIGN KEY (registration_id) REFERENCES registrations(id)
);

CREATE INDEX IF NOT EXISTS idx_auth_quick_mpin_reg ON auth_quick_mpin(registration_id);
CREATE INDEX IF NOT EXISTS idx_auth_quick_mpin_expires ON auth_quick_mpin(expires_at);
