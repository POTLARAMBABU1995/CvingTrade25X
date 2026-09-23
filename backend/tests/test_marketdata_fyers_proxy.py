import base64
import datetime as dt
import json
import os
from pathlib import Path
import sys
import time
import pytest

from flask import Flask


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import services.marketdata_service as service
import routes.marketdata as marketdata_route


def _build_test_jwt(payload: dict[str, object]) -> str:
    header = {"alg": "HS256", "typ": "JWT"}

    def _encode(value: dict[str, object]) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

    return f"{_encode(header)}.{_encode(payload)}.signature"


def test_apply_fyers_proxy_policy_direct_strips_inherited_and_sets_no_proxy(monkeypatch):
    monkeypatch.setattr(service, "FYERS_PROXY_MODE", "direct")
    monkeypatch.setattr(service, "FYERS_HTTP_PROXY", "")
    monkeypatch.setattr(service, "FYERS_HTTPS_PROXY", "")
    monkeypatch.setattr(service, "FYERS_ALL_PROXY", "")
    monkeypatch.setattr(service, "FYERS_NO_PROXY", "")

    env = {
        "HTTP_PROXY": "http://127.0.0.1:9",
        "HTTPS_PROXY": "http://127.0.0.1:9",
        "ALL_PROXY": "http://127.0.0.1:9",
        "GIT_HTTP_PROXY": "http://127.0.0.1:9",
        "GIT_HTTPS_PROXY": "http://127.0.0.1:9",
        "NO_PROXY": "example.com",
    }
    resolved, diagnostics = service._apply_fyers_proxy_policy(env)

    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "GIT_HTTP_PROXY", "GIT_HTTPS_PROXY"):
        assert key not in resolved
        assert key.lower() not in resolved

    no_proxy = resolved.get("NO_PROXY", "")
    assert no_proxy
    tokens = [item.strip().lower() for item in no_proxy.split(",") if item.strip()]
    assert "example.com" in tokens
    for required in service._FYERS_DIRECT_NO_PROXY_REQUIRED:
        assert required.lower() in tokens
    assert resolved["no_proxy"] == resolved["NO_PROXY"]
    assert diagnostics["mode"] == "direct"


def test_apply_fyers_proxy_policy_system_keeps_inherited(monkeypatch):
    monkeypatch.setattr(service, "FYERS_PROXY_MODE", "system")
    monkeypatch.setattr(service, "FYERS_HTTP_PROXY", "")
    monkeypatch.setattr(service, "FYERS_HTTPS_PROXY", "")
    monkeypatch.setattr(service, "FYERS_ALL_PROXY", "")
    monkeypatch.setattr(service, "FYERS_NO_PROXY", "")

    env = {
        "HTTP_PROXY": "http://proxy.local:8080",
        "HTTPS_PROXY": "http://proxy.local:8443",
        "NO_PROXY": "localhost",
    }
    resolved, diagnostics = service._apply_fyers_proxy_policy(env)

    assert resolved["HTTP_PROXY"] == "http://proxy.local:8080"
    assert resolved["HTTPS_PROXY"] == "http://proxy.local:8443"
    assert resolved["NO_PROXY"] == "localhost"
    assert diagnostics["mode"] == "system"
    assert diagnostics["proxy"]["HTTP_PROXY"] == "http://proxy.local:8080"


def test_apply_fyers_proxy_policy_explicit_overrides_inherited(monkeypatch):
    monkeypatch.setattr(service, "FYERS_PROXY_MODE", "explicit")
    monkeypatch.setattr(service, "FYERS_HTTP_PROXY", "http://explicit-proxy:8080")
    monkeypatch.setattr(service, "FYERS_HTTPS_PROXY", "http://explicit-proxy:8443")
    monkeypatch.setattr(service, "FYERS_ALL_PROXY", "http://explicit-proxy:9000")
    monkeypatch.setattr(service, "FYERS_NO_PROXY", "localhost,127.0.0.1")

    env = {
        "HTTP_PROXY": "http://dead-proxy:9",
        "HTTPS_PROXY": "http://dead-proxy:9",
        "ALL_PROXY": "http://dead-proxy:9",
        "GIT_HTTP_PROXY": "http://dead-proxy:9",
        "NO_PROXY": "example.com",
    }
    resolved, diagnostics = service._apply_fyers_proxy_policy(env)

    assert resolved["HTTP_PROXY"] == "http://explicit-proxy:8080"
    assert resolved["HTTPS_PROXY"] == "http://explicit-proxy:8443"
    assert resolved["ALL_PROXY"] == "http://explicit-proxy:9000"
    assert resolved["NO_PROXY"] == "localhost,127.0.0.1"
    assert resolved["no_proxy"] == "localhost,127.0.0.1"
    assert "GIT_HTTP_PROXY" not in resolved
    assert diagnostics["mode"] == "explicit"
    assert diagnostics["proxy"]["HTTP_PROXY"] == "http://explicit-proxy:8080"


def test_sanitize_proxy_value_redacts_credentials():
    sanitized = service._sanitize_proxy_value("http://myuser:mypass@proxy.example.com:8080")
    assert sanitized == "http://***:***@proxy.example.com:8080"
    assert "myuser" not in sanitized
    assert "mypass" not in sanitized


def test_fyers_authorize_rewrites_proxy_failure_message(monkeypatch):
    monkeypatch.setattr(service, "_resolve_fyers_project_dir", lambda: Path("D:/fyers_api_integration"))
    monkeypatch.setattr(service, "_mark_fyers_auth_pending", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(service, "_mark_fyers_auth_failure", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(service, "_run_fyers_module", lambda *args, **kwargs: {
        "ok": False,
        "returncode": 1,
        "timed_out": False,
        "duration_seconds": 1.0,
        "stdout": "",
        "stderr": (
            "Auth code exchange request failed: "
            "ProxyError('Unable to connect to proxy', "
            "NewConnectionError('[WinError 10061]'))"
        ),
        "stdout_tail": [],
        "stderr_tail": ["ProxyError: Unable to connect to proxy"],
        "command": ["python", "-m", "src.token_helper"],
        "cwd": "D:/fyers_api_integration",
        "proxy_policy": "direct",
        "proxy_env": {"NO_PROXY": "localhost,127.0.0.1"},
    })

    payload = service.fyers_authorize(force=True)

    assert payload["ok"] is False
    assert "proxy connectivity" in payload["message"].lower()
    assert payload["logs"]["stderrTail"] == ["ProxyError: Unable to connect to proxy"]
    assert payload["logs"]["proxyMode"] == "direct"
    assert payload["logs"]["proxy"] == {"NO_PROXY": "localhost,127.0.0.1"}


def test_fyers_start_authorize_job_returns_fast_authenticated_payload(monkeypatch):
    monkeypatch.setattr(service, "_resolve_fyers_project_dir", lambda: Path("D:/fyers_api_integration"))
    monkeypatch.setattr(service, "_today_local_iso", lambda: "2026-06-20")
    monkeypatch.setattr(service, "_is_fyers_authenticated_today", lambda _project_dir: (True, {"last_auth_date": "2026-06-20"}))
    monkeypatch.setattr(service, "_read_fyers_token_metadata", lambda _project_dir: {
        "authenticated": True,
        "expiresAt": "2026-06-20T23:59:59+05:30",
        "expiresAtUtc": "2026-06-20T18:29:59Z",
    })
    cached_payloads: list[dict[str, object]] = []
    monkeypatch.setattr(service, "_write_cached_fyers_auth_status", lambda payload: cached_payloads.append(payload))

    payload = service.fyers_start_authorize_job({"force": False})

    assert payload["ok"] is True
    assert payload["status"] == "ALREADY_AUTHENTICATED"
    assert payload["requiresAuthorization"] is False
    assert payload["expires_at"] == "2026-06-20T23:59:59+05:30"
    assert cached_payloads


def test_fyers_start_authorize_job_starts_background_job(monkeypatch):
    monkeypatch.setattr(service, "_resolve_fyers_project_dir", lambda: Path("D:/fyers_api_integration"))
    monkeypatch.setattr(service, "_today_local_iso", lambda: "2026-06-20")
    monkeypatch.setattr(service, "_is_fyers_authenticated_today", lambda _project_dir: (False, {}))
    monkeypatch.setattr(service, "_read_fyers_token_metadata", lambda _project_dir: {"authenticated": False})
    monkeypatch.setattr(service, "_cleanup_fyers_jobs_locked", lambda _now_ts: None)
    started_calls: list[tuple[str, dict[str, object], object]] = []
    monkeypatch.setattr(
        service,
        "_run_fyers_job_async",
        lambda stage, payload, runner: started_calls.append((stage, payload, runner)) or {
            "ok": True,
            "jobId": "auth-job-1",
            "job_id": "auth-job-1",
            "runId": "auth-job-1",
            "run_id": "auth-job-1",
            "stage": stage,
            "status": "STARTED",
            "message": "started",
        },
    )

    payload = service.fyers_start_authorize_job({"force": True})

    assert payload["ok"] is True
    assert payload["status"] == "AUTH_URL_CREATED"
    assert payload["jobId"] == "auth-job-1"
    assert payload["requiresAuthorization"] is True
    assert started_calls == [("authorize", {"force": True}, service.fyers_run_authorize_job)]


def test_invalid_auth_code_failure_pattern():
    assert service._is_invalid_auth_code_failure("Token exchange failed: {'message': 'invalid auth code'}")
    assert service._is_invalid_auth_code_failure("RuntimeError: State mismatch")
    assert not service._is_invalid_auth_code_failure("network timeout reached")


def test_fyers_history_auth_failure_pattern():
    assert service._is_fyers_auth_failure(
        "FYERS history error: {'code': -16, 'message': 'Could not authenticate the user', 's': 'error'}"
    )
    assert service._is_fyers_auth_failure("RuntimeError: invalid access token")
    assert not service._is_fyers_auth_failure("FYERS request limit exceeded")


def test_classify_fyers_rejected_symbol_as_invalid_symbol():
    status, error_code, message = service._classify_symbol_failure(
        "ValueError: FYERS rejected symbol 'NSE:ATLANTAELE-EQ'. Use a valid FYERS symbol code.",
        stage="fetch",
    )

    assert status == "FAILED_INVALID_SYMBOL"
    assert error_code == "INVALID_SYMBOL"
    assert message == "FYERS rejected symbol"


def test_classify_fyers_bad_request_as_no_data():
    status, error_code, message = service._classify_symbol_failure(
        "RuntimeError: FYERS history error for NSE:BRIGADE-EQ 2026-06-03..2026-06-03: "
        "{'s': 'error', 'code': -99, 'message': 'Bad request'}",
        stage="fetch",
    )

    assert status == "FAILED_NO_DATA"
    assert error_code == "NO_DATA"
    assert message == "No candle data returned by FYERS"


def test_fyers_run_single_tracks_expected_symbol_rejections_without_tracebacks(monkeypatch):
    class FakeAcquire:
        def __enter__(self):
            return object()

        def __exit__(self, *_args):
            return False

    class FakePool:
        def acquire(self):
            return FakeAcquire()

    merged_failures = []
    skipped_rows = []
    log_lines = []

    monkeypatch.setattr(service, "pool", FakePool())
    monkeypatch.setattr(service, "ensure_valid_fyers_auth", lambda **_kwargs: {
        "ok": True,
        "status": "AUTHENTICATED",
        "authenticated": True,
        "canExtract": True,
        "expiresAt": "2026-06-03T23:59:59+05:30",
    })
    monkeypatch.setattr(service, "_resolve_fyers_project_dir", lambda: Path("D:/fyers_api_integration"))
    monkeypatch.setattr(service, "_ensure_fyers_tracking_tables", lambda _conn: None)
    monkeypatch.setattr(service, "_fetch_existing_symbol_dates_by_range", lambda *_args, **_kwargs: set())
    monkeypatch.setattr(service, "_fetch_actual_trading_dates", lambda *_args, **_kwargs: {dt.date(2026, 6, 3)})
    monkeypatch.setattr(service, "_db_init_extraction_run", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "_db_init_extraction_symbols", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "_db_update_extraction_symbol", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "_db_update_extraction_run_counts", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "_fetch_previously_failed_permanent_symbols", lambda *_args, **_kwargs: set())
    monkeypatch.setattr(service, "FYERS_REQUEST_SLEEP_SECONDS", 0)
    monkeypatch.setattr(
        service,
        "_merge_failed_symbol",
        lambda _conn, **kwargs: merged_failures.append(kwargs),
    )
    monkeypatch.setattr(
        service,
        "_insert_skipped_rejected_symbol",
        lambda _conn, **kwargs: skipped_rows.append(kwargs),
    )

    def fake_direct_fetch(*, symbol, **_kwargs):
        if symbol == "NSE:ATLANTAELE-EQ":
            raise ValueError(
                "FYERS rejected symbol 'NSE:ATLANTAELE-EQ'. Use a valid FYERS symbol code (e.g., NSE:RELIANCE-EQ)."
            )
        if symbol == "NSE:BRIGADE-EQ":
            raise RuntimeError(
                "FYERS history error for NSE:BRIGADE-EQ 2026-06-03..2026-06-03: "
                "{'s': 'error', 'code': -99, 'message': 'Bad request'}"
            )
        raise AssertionError(f"unexpected symbol: {symbol}")

    monkeypatch.setattr(service, "_direct_fetch_fyers_rows", fake_direct_fetch)

    payload = service.fyers_run_single(
        {
            "symbol": "NSE:ATLANTAELE-EQ,NSE:BRIGADE-EQ",
            "startDate": "2026-06-03",
            "endDate": "2026-06-03",
            "authorize": False,
        },
        line_logger=log_lines.append,
    )

    assert payload["stats"]["processed"] == 2
    assert payload["stats"]["skipped"] == 2
    assert payload["stats"]["failed"] == 0
    assert [row["status"] for row in merged_failures] == ["FAILED_INVALID_SYMBOL", "FAILED_NO_DATA"]
    assert [row["error_code"] for row in skipped_rows] == ["INVALID_SYMBOL", "NO_DATA"]
    assert any("NSE:ATLANTAELE-EQ skipped" in line for line in log_lines)
    assert any("NSE:BRIGADE-EQ skipped" in line for line in log_lines)
    assert not any("Traceback" in line for line in log_lines)


def test_fyers_run_single_stops_auth_expiry_without_failed_symbol_tracking(monkeypatch):
    class FakeAcquire:
        def __enter__(self):
            return object()

        def __exit__(self, *_args):
            return False

    class FakePool:
        def acquire(self):
            return FakeAcquire()

    monkeypatch.setattr(service, "pool", FakePool())
    monkeypatch.setattr(service, "ensure_valid_fyers_auth", lambda **_kwargs: {
        "ok": True,
        "status": "AUTHENTICATED",
        "authenticated": True,
        "canExtract": True,
        "expiresAt": "2026-06-03T23:59:59+05:30",
    })
    monkeypatch.setattr(service, "_resolve_fyers_project_dir", lambda: Path("D:/fyers_api_integration"))
    monkeypatch.setattr(service, "_ensure_fyers_tracking_tables", lambda _conn: None)
    monkeypatch.setattr(service, "_fetch_existing_symbol_dates_by_range", lambda *_args, **_kwargs: set())
    monkeypatch.setattr(service, "_fetch_actual_trading_dates", lambda *_args, **_kwargs: {dt.date(2026, 6, 3)})
    monkeypatch.setattr(service, "_db_init_extraction_run", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "_db_init_extraction_symbols", lambda *_args, **_kwargs: None)
    updated_symbols = []
    monkeypatch.setattr(
        service,
        "_db_update_extraction_symbol",
        lambda _conn, *_args: updated_symbols.append(_args),
    )
    monkeypatch.setattr(service, "_db_update_extraction_run_counts", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "_fetch_previously_failed_permanent_symbols", lambda *_args, **_kwargs: set())
    monkeypatch.setattr(service, "FYERS_REQUEST_SLEEP_SECONDS", 0)
    monkeypatch.setattr(
        service,
        "_direct_fetch_fyers_rows",
        lambda **_kwargs: (_ for _ in ()).throw(
            RuntimeError("FYERS history error: {'code': -16, 'message': 'Could not authenticate the user'}")
        ),
    )
    monkeypatch.setattr(
        service,
        "_merge_failed_symbol",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("auth expiry must not create failed-symbol rows")
        ),
    )
    monkeypatch.setattr(
        service,
        "_insert_skipped_rejected_symbol",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("auth expiry must not create skipped/rejected rows")
        ),
    )

    payload = service.fyers_run_single({
        "symbol": "NSE:RELIANCE-EQ",
        "startDate": "2026-06-03",
        "endDate": "2026-06-03",
        "authorize": False,
    })

    assert payload["ok"] is False
    assert payload["status"] == "AUTH_EXPIRED"
    assert payload["canExtract"] is False
    assert payload["requiresAuthorization"] is True
    assert payload["stats"]["failed"] == 0
    assert payload["results"] == []
    assert any(args[-2:] == ("AUTH_EXPIRED", service.FYERS_AUTH_REQUIRED_MESSAGE) for args in updated_symbols)


def test_build_fyers_fetch_ranges_only_requests_missing_trading_runs_and_new_tail():
    start_date = dt.date(2026, 6, 1)
    end_date = dt.date(2026, 6, 6)
    actual_dates = {
        dt.date(2026, 6, 1),
        dt.date(2026, 6, 2),
        dt.date(2026, 6, 3),
        dt.date(2026, 6, 4),
        dt.date(2026, 6, 5),
    }
    existing_dates = {
        dt.date(2026, 6, 1),
        dt.date(2026, 6, 2),
        dt.date(2026, 6, 4),
    }

    ranges = service._build_fyers_fetch_ranges(
        start_date=start_date,
        end_date=end_date,
        actual_trading_dates=actual_dates,
        existing_dates=existing_dates,
        force_refresh=False,
    )

    assert ranges == [
        (dt.date(2026, 6, 3), dt.date(2026, 6, 3)),
        (dt.date(2026, 6, 5), dt.date(2026, 6, 6)),
    ]


def test_build_fyers_fetch_ranges_preserves_full_range_for_force_refresh():
    ranges = service._build_fyers_fetch_ranges(
        start_date=dt.date(1998, 1, 1),
        end_date=dt.date(2026, 6, 19),
        actual_trading_dates={dt.date(2026, 6, 18)},
        existing_dates={dt.date(2026, 6, 18)},
        force_refresh=True,
    )

    assert ranges == [(dt.date(1998, 1, 1), dt.date(2026, 6, 19))]


def test_fyers_authorize_retries_invalid_auth_code_then_succeeds(monkeypatch):
    monkeypatch.setattr(service, "FYERS_AUTH_RETRY_COUNT", 2)
    monkeypatch.setattr(service, "_resolve_fyers_project_dir", lambda: Path("D:/fyers_api_integration"))
    monkeypatch.setattr(service, "_mark_fyers_auth_pending", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(service, "_mark_fyers_auth_success", lambda _dir: {"last_auth_date": "2026-02-27"})

    calls = []

    def fake_run(*_args, **kwargs):
        calls.append(kwargs.get("env_overrides") or {})
        if len(calls) == 1:
            return {
                "ok": False,
                "returncode": 1,
                "timed_out": False,
                "duration_seconds": 0.2,
                "stdout": "",
                "stderr": "RuntimeError: Token exchange failed: {'code': -1, 'message': 'invalid auth code', 's': 'error'}",
                "stdout_tail": [],
                "stderr_tail": ["invalid auth code"],
                "command": ["python", "-m", "src.token_helper"],
                "cwd": "D:/fyers_api_integration",
                "proxy_policy": "direct",
                "proxy_env": {"NO_PROXY": "localhost,127.0.0.1"},
            }
        return {
            "ok": True,
            "returncode": 0,
            "timed_out": False,
            "duration_seconds": 0.4,
            "stdout": "Access token saved to token.json",
            "stderr": "",
            "stdout_tail": ["Access token saved to token.json"],
            "stderr_tail": [],
            "command": ["python", "-m", "src.token_helper"],
            "cwd": "D:/fyers_api_integration",
            "proxy_policy": "direct",
            "proxy_env": {"NO_PROXY": "localhost,127.0.0.1"},
        }

    monkeypatch.setattr(service, "_run_fyers_module", fake_run)

    payload = service.fyers_authorize(force=True)

    assert payload["ok"] is True
    assert len(calls) == 2
    assert "FYERS_STATE" in calls[0]
    assert "FYERS_STATE" in calls[1]
    assert calls[0]["FYERS_STATE"] != calls[1]["FYERS_STATE"]


def test_fyers_authorize_skips_auto_retry_after_login_url_emitted(monkeypatch):
    monkeypatch.setattr(service, "FYERS_AUTH_RETRY_COUNT", 2)
    monkeypatch.setattr(service, "_resolve_fyers_project_dir", lambda: Path("D:/fyers_api_integration"))
    monkeypatch.setattr(service, "_mark_fyers_auth_pending", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(service, "_mark_fyers_auth_failure", lambda *_args, **_kwargs: {})

    calls = []
    log_lines = []

    def fake_run(*_args, **kwargs):
        calls.append(kwargs.get("env_overrides") or {})
        on_stdout_line = kwargs.get("on_stdout_line")
        if on_stdout_line:
            on_stdout_line("Login URL: https://api-t1.fyers.in/api/v3/generate-authcode?state=swingtrade-login-test")
        return {
            "ok": False,
            "returncode": 1,
            "timed_out": False,
            "duration_seconds": 0.2,
            "stdout": "Login URL: https://api-t1.fyers.in/api/v3/generate-authcode?state=swingtrade-login-test",
            "stderr": "RuntimeError: Token exchange failed: {'code': -1, 'message': 'invalid auth code', 's': 'error'}",
            "stdout_tail": ["Login URL: https://api-t1.fyers.in/api/v3/generate-authcode?state=swingtrade-login-test"],
            "stderr_tail": ["invalid auth code"],
            "command": ["python", "-m", "src.token_helper"],
            "cwd": "D:/fyers_api_integration",
            "proxy_policy": "direct",
            "proxy_env": {"NO_PROXY": "localhost,127.0.0.1"},
        }

    monkeypatch.setattr(service, "_run_fyers_module", fake_run)

    payload = service.fyers_authorize(force=True, line_logger=log_lines.append)

    assert payload["ok"] is False
    assert payload["status"] == "STALE_CALLBACK"
    assert payload["canExtract"] is False
    assert payload["stats"]["failed"] == 0
    assert len(calls) == 1
    assert any("Skipping automatic retry" in line for line in log_lines)


def test_fyers_authorize_reports_invalid_refresh_token_as_fresh_login_required(monkeypatch):
    monkeypatch.setattr(service, "FYERS_AUTH_RETRY_COUNT", 1)
    monkeypatch.setattr(service, "_resolve_fyers_project_dir", lambda: Path("D:/fyers_api_integration"))
    monkeypatch.setattr(service, "_mark_fyers_auth_pending", lambda *_args, **_kwargs: {})
    invalidations = []
    monkeypatch.setattr(
        service,
        "_mark_fyers_auth_failure",
        lambda project_dir, reason="": invalidations.append((project_dir, reason)) or {},
    )
    monkeypatch.setattr(service, "_run_fyers_module", lambda *_args, **_kwargs: {
        "ok": False,
        "returncode": 1,
        "timed_out": False,
        "duration_seconds": 0.2,
        "stdout": "",
        "stderr": "Refresh token failed: invalid grant type. Falling back to login.",
        "stdout_tail": [],
        "stderr_tail": ["Refresh token failed: invalid grant type. Falling back to login."],
        "command": ["python", "-m", "src.token_helper"],
        "cwd": "D:/fyers_api_integration",
        "proxy_policy": "direct",
        "proxy_env": {"NO_PROXY": "localhost,127.0.0.1"},
    })

    payload = service.fyers_authorize(force=True)

    assert payload["ok"] is False
    assert payload["status"] == "INVALID_REFRESH_TOKEN"
    assert payload["message"] == "FYERS refresh token failed. Fresh login required."
    assert payload["canExtract"] is False
    assert payload["stats"]["failed"] == 0
    assert invalidations == [(Path("D:/fyers_api_integration"), "INVALID_REFRESH_TOKEN")]


def test_fyers_authorize_timeout_recovers_token_saved_at_callback_deadline(monkeypatch):
    project_dir = Path("D:/fyers_api_integration")
    monkeypatch.setattr(service, "FYERS_AUTH_RETRY_COUNT", 1)
    monkeypatch.setattr(service, "_resolve_fyers_project_dir", lambda: project_dir)
    monkeypatch.setattr(service, "_mark_fyers_auth_pending", lambda *_args, **_kwargs: {
        "pending_created_at": "2026-06-21T13:14:05+05:30",
        "pending_expires_at": "2026-06-21T13:16:05+05:30",
    })
    monkeypatch.setattr(service, "_run_fyers_module", lambda *_args, **_kwargs: {
        "ok": False,
        "returncode": 124,
        "timed_out": True,
        "duration_seconds": 120.0,
        "stdout": "Login URL: https://api-t1.fyers.in/api/v3/generate-authcode?state=test",
        "stderr": "Process timed out after 120 seconds.",
        "stdout_tail": ["Login URL: https://api-t1.fyers.in/api/v3/generate-authcode?state=test"],
        "stderr_tail": ["Process timed out after 120 seconds."],
        "command": ["python", "-m", "src.token_helper"],
        "cwd": str(project_dir),
    })
    token_metadata = {
        "tokenExists": True,
        "expiryAvailable": True,
        "authenticated": True,
        "authExpired": False,
        "expiresAt": "2026-06-22T06:00:00+05:30",
        "expiresAtUtc": "2026-06-22T00:30:00Z",
        "expiresAtEpoch": int(time.time()) + 3600,
        "issuedAt": "2026-06-21T13:16:04+05:30",
        "issuedAtUtc": "2026-06-21T07:46:04Z",
    }
    monkeypatch.setattr(service, "_read_fyers_token_metadata", lambda _project_dir: token_metadata)
    monkeypatch.setattr(service, "_probe_fyers_profile_auth", lambda _project_dir: (
        True,
        {"status": "ok", "code": 200, "message": "FYERS profile validation succeeded."},
    ))
    successes = []
    monkeypatch.setattr(
        service,
        "_mark_fyers_auth_success",
        lambda _project_dir: successes.append(_project_dir) or {
            "last_auth_date": "2026-06-21",
            "last_auth_at": "2026-06-21T13:16:05+05:30",
        },
    )
    monkeypatch.setattr(service, "_write_cached_fyers_auth_status", lambda _payload: None)
    monkeypatch.setattr(
        service,
        "_mark_fyers_auth_failure",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("a valid token saved at the deadline must not be marked stale")
        ),
    )

    payload = service.fyers_authorize(force=True)

    assert payload["ok"] is True
    assert payload["status"] == "AUTHORIZED"
    assert payload["requiresAuthorization"] is False
    assert payload["expiresAt"] == token_metadata["expiresAt"]
    assert successes == [project_dir]


def test_live_auth_status_recovers_stale_state_when_new_valid_token_exists(monkeypatch):
    project_dir = Path("D:/fyers_api_integration")
    stale_state = {
        "last_auth_date": "",
        "invalidated_at": "2026-06-21T13:16:05+05:30",
        "invalidated_reason": "STALE_CALLBACK",
    }
    token_metadata = {
        "tokenExists": True,
        "expiryAvailable": True,
        "authenticated": True,
        "authExpired": False,
        "expiresAt": "2026-06-22T06:00:00+05:30",
        "expiresAtUtc": "2026-06-22T00:30:00Z",
        "expiresAtEpoch": int(time.time()) + 3600,
        "issuedAt": "2026-06-21T13:16:04+05:30",
        "issuedAtUtc": "2026-06-21T07:46:04Z",
        "tokenPath": str(project_dir / "src" / "token.json"),
    }
    monkeypatch.setattr(service, "_resolve_fyers_project_dir", lambda: project_dir)
    monkeypatch.setattr(service, "_is_fyers_authenticated_today", lambda _project_dir: (False, stale_state))
    monkeypatch.setattr(service, "_read_fyers_token_metadata", lambda _project_dir: token_metadata)
    monkeypatch.setattr(service, "_probe_fyers_profile_auth", lambda _project_dir: (
        True,
        {"status": "ok", "code": 200, "message": "FYERS profile validation succeeded."},
    ))
    monkeypatch.setattr(service, "_today_local_iso", lambda: "2026-06-21")
    monkeypatch.setattr(
        service,
        "_mark_fyers_auth_success",
        lambda _project_dir: {
            "last_auth_date": "2026-06-21",
            "last_auth_at": "2026-06-21T13:16:06+05:30",
        },
    )
    monkeypatch.setattr(service, "_write_cached_fyers_auth_status", lambda _payload: None)

    payload = service._refresh_fyers_auth_status_live()

    assert payload["status"] == "AUTHENTICATED"
    assert payload["authenticated"] is True
    assert payload["canExtract"] is True
    assert payload["lastAuthorizedDate"] == "2026-06-21"


def test_ensure_valid_fyers_auth_requires_same_day_unexpired_token_before_profile_probe(monkeypatch):
    monkeypatch.setattr(service, "_resolve_fyers_project_dir", lambda: Path("D:/fyers_api_integration"))
    monkeypatch.setattr(service, "_is_fyers_authenticated_today", lambda _project_dir: (False, {
        "invalidated_reason": "AUTH_REQUIRED",
    }))
    monkeypatch.setattr(service, "_read_fyers_token_metadata", lambda _project_dir: {
        "tokenExists": False,
        "authenticated": False,
        "authExpired": True,
        "expiryAvailable": False,
        "expiresAt": None,
        "expiresAtEpoch": None,
    })
    monkeypatch.setattr(
        service,
        "_probe_fyers_profile_auth",
        lambda _project_dir: (_ for _ in ()).throw(AssertionError("profile probe must not run")),
    )

    payload = service.ensure_valid_fyers_auth()

    assert payload == {
        "ok": False,
        "stage": "authorize",
        "status": "AUTH_REQUIRED",
        "code": "FYERS_AUTH_REQUIRED",
        "errorCode": "FYERS_AUTH_REQUIRED",
        "message": "Authentication Expired. Please authenticate FYERS before extracting symbols.",
        "authenticated": False,
        "canExtract": False,
        "requiresAuthorization": True,
        "shouldRetry": False,
        "expiresAt": None,
    }


def test_ensure_valid_fyers_auth_requires_successful_profile_probe(monkeypatch):
    expires_at = "2026-06-21T23:59:59+05:30"
    monkeypatch.setattr(service, "_resolve_fyers_project_dir", lambda: Path("D:/fyers_api_integration"))
    monkeypatch.setattr(service, "_is_fyers_authenticated_today", lambda _project_dir: (True, {
        "last_auth_date": service._today_local_iso(),
    }))
    monkeypatch.setattr(service, "_read_fyers_token_metadata", lambda _project_dir: {
        "tokenExists": True,
        "authenticated": True,
        "authExpired": False,
        "expiryAvailable": True,
        "expiresAt": expires_at,
        "expiresAtEpoch": int(time.time()) + 3600,
    })
    monkeypatch.setattr(service, "_probe_fyers_profile_auth", lambda _project_dir: (
        True,
        {"status": "ok", "code": 200, "message": "Profile validated."},
    ))

    payload = service.ensure_valid_fyers_auth()

    assert payload["ok"] is True
    assert payload["status"] == "AUTHENTICATED"
    assert payload["authenticated"] is True
    assert payload["canExtract"] is True
    assert payload["canExtract"] is True
    assert payload["expiresAt"] == expires_at


def test_fyers_start_batch_job_blocks_before_job_creation_when_auth_is_invalid(monkeypatch):
    service._FYERS_JOBS.clear()
    monkeypatch.setattr(service, "ensure_valid_fyers_auth", lambda **_kwargs: {
        "ok": False,
        "stage": "authorize",
        "status": "AUTH_REQUIRED",
        "code": "FYERS_AUTH_REQUIRED",
        "errorCode": "FYERS_AUTH_REQUIRED",
        "message": "Authentication Expired. Please authenticate FYERS before extracting symbols.",
        "authenticated": False,
        "canExtract": False,
        "requiresAuthorization": True,
        "shouldRetry": False,
        "expiresAt": None,
    })
    monkeypatch.setattr(
        service,
        "_run_fyers_job_async",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("job must not be created")),
    )

    payload = service.fyers_start_batch_job({
        "startDate": "2026-06-19",
        "endDate": "2026-06-19",
        "authorize": False,
    })

    assert payload["status"] == "AUTH_REQUIRED"
    assert payload["canExtract"] is False
    assert "jobId" not in payload
    assert service._FYERS_JOBS == {}


def test_authorize_job_does_not_persist_extraction_run_or_terminal_symbol_summary(monkeypatch):
    class FailPool:
        def acquire(self):
            raise AssertionError("authorization must not create an Oracle extraction run")

    monkeypatch.setattr(service, "pool", FailPool())
    service._persist_fyers_job_start("auth-job", "authorize", {"endDate": "2026-06-21"})

    job = {"stage": "authorize", "logs": []}
    service._append_fyers_terminal_summary(job, {
        "ok": False,
        "stage": "authorize",
        "status": "STALE_CALLBACK",
        "stats": {"inserted": 0, "skipped": 0, "failed": 0, "errors": 1},
    })

    assert job["logs"] == []
    assert "_terminal_summary_appended" not in job


def test_fyers_batch_auth_failure_fails_fast_without_skip_tracking(monkeypatch):
    monkeypatch.setattr(service, "_resolve_fyers_project_dir", lambda: Path("D:/fyers_api_integration"))
    monkeypatch.setattr(service, "ensure_valid_fyers_auth", lambda **_kwargs: {
        "ok": True,
        "status": "AUTHENTICATED",
        "authenticated": True,
        "canExtract": True,
        "expiresAt": "2026-05-21T23:59:59+05:30",
    })

    invalidations = []
    monkeypatch.setattr(
        service,
        "_mark_fyers_auth_failure",
        lambda project_dir, reason="": invalidations.append((project_dir, reason)) or {},
    )

    def fail_if_skip_tracking(*_args, **_kwargs):
        raise AssertionError("auth failures must not be written as skipped/rejected symbols")

    monkeypatch.setattr(service, "_insert_skipped_rejected_symbol", fail_if_skip_tracking)

    monkeypatch.setattr(service, "_run_fyers_history_auth_probe", lambda **_kwargs: (False, {"ok": True}))
    monkeypatch.setattr(service, "_load_fyers_batch_symbols", lambda _project_dir: ["NSE:360ONE-EQ"])
    monkeypatch.setattr(service, "fyers_run_single", lambda *_args, **_kwargs: {
        "ok": False,
        "stage": "single",
        "status": "FAILED",
        "message": service.FYERS_AUTH_EXPIRED_UI_MESSAGE,
        "errorCode": "FYERS_AUTH_FAILED",
        "requiresAuthorization": True,
        "stats": {"processed": 1, "inserted": 0, "skipped": 0, "failed": 1, "errors": 1},
        "details": {"auth_failed": True},
    })

    payload = service.fyers_run_batch({
        "startDate": "2026-05-21",
        "endDate": "2026-05-21",
        "authorize": False,
    })

    assert payload["ok"] is False
    assert "authentication failed" in payload["message"].lower()
    assert payload["stats"]["failed"] == 1
    assert payload["stats"]["errors"] == 1
    assert payload["details"]["auth_failed"] is True
    assert payload["details"]["error_code"] == "FYERS_AUTH_FAILED"
    assert payload["authStatus"] == "FAILED"
    assert payload["errorCode"] == "FYERS_AUTH_FAILED"
    assert payload["requiresAuthorization"] is True
    assert payload["shouldRetry"] is False
    assert payload["details"]["skipped_rejected_candidates"] == 1
    assert payload["details"]["file_storage"] == "disabled"
    assert invalidations == [(Path("D:/fyers_api_integration"), "fyers_history_auth_failure")]


def test_fyers_batch_auth_precheck_aborts_before_direct_batch(monkeypatch):
    monkeypatch.setattr(service, "_resolve_fyers_project_dir", lambda: Path("D:/fyers_api_integration"))
    monkeypatch.setattr(service, "ensure_valid_fyers_auth", lambda **_kwargs: {
        "ok": True,
        "status": "AUTHENTICATED",
        "authenticated": True,
        "canExtract": True,
        "expiresAt": "2026-05-21T23:59:59+05:30",
    })
    monkeypatch.setattr(service, "_insert_skipped_rejected_symbol", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not insert skip rows")))

    invalidations = []
    monkeypatch.setattr(
        service,
        "_mark_fyers_auth_failure",
        lambda project_dir, reason="": invalidations.append((project_dir, reason)) or {},
    )

    monkeypatch.setattr(service, "_run_fyers_history_auth_probe", lambda **_kwargs: (True, {
        "ok": False,
        "returncode": 1,
        "timed_out": False,
        "duration_seconds": 0.2,
        "stdout": "",
        "stderr": "FYERS history error: {'code': -16, 'message': 'Could not authenticate the user', 's': 'error'}",
        "stdout_tail": [],
        "stderr_tail": ["Could not authenticate the user"],
        "command": ["direct-fyers-auth-probe"],
        "cwd": "D:/fyers_api_integration",
    }))
    monkeypatch.setattr(service, "_load_fyers_batch_symbols", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("symbols should not load")))

    payload = service.fyers_run_batch({
        "startDate": "2026-05-21",
        "endDate": "2026-05-21",
        "authorize": False,
    })

    assert payload["ok"] is False
    assert payload["message"] == service.FYERS_BATCH_AUTH_ERROR_MESSAGE
    assert payload["uiMessage"] == service.FYERS_BATCH_AUTH_UI_MESSAGE
    assert payload["authStatus"] == "FAILED"
    assert payload["errorCode"] == "FYERS_AUTH_FAILED"
    assert payload["requiresAuthorization"] is True
    assert payload["shouldRetry"] is False
    assert invalidations == [(Path("D:/fyers_api_integration"), "fyers_history_auth_probe_failed")]


def test_fyers_auth_status_exposes_token_expiry(monkeypatch, tmp_path):
    project_dir = tmp_path / "fyers"
    token_dir = project_dir / "src"
    token_dir.mkdir(parents=True)
    monkeypatch.setattr(service, "FYERS_AUTH_STATUS_CACHE_FILE", str(tmp_path / "fyers_auth_status.json"))
    monkeypatch.setattr(service, "FYERS_AUTH_STATUS_FAST_WAIT_SEC", 1.0)
    monkeypatch.setattr(service, "_IN_MEMORY_AUTH_STATUS", None)
    monkeypatch.setattr(service, "_IN_MEMORY_AUTH_STATUS_TS", 0.0)
    monkeypatch.setattr(service, "_FYERS_AUTH_STATUS_REFRESH_ACTIVE", False)
    future_exp = int((dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=6)).timestamp())
    token_path = token_dir / "token.json"
    token_path.write_text(json.dumps({
        "raw_access_token": _build_test_jwt({"exp": future_exp, "iat": future_exp - 3600}),
    }), encoding="utf-8")
    today = service._today_local_iso()
    monkeypatch.setattr(service, "_resolve_fyers_project_dir", lambda: project_dir)
    monkeypatch.setattr(service, "_is_fyers_authenticated_today", lambda _dir: (True, {
        "last_auth_date": today,
        "last_auth_at": f"{today}T09:00:00",
    }))

    payload = service.fyers_auth_status()

    assert payload["ok"] is True
    assert payload["authenticated"] is True
    assert payload["canExtract"] is True
    assert payload["authExpired"] is False
    assert payload["expiryAvailable"] is True
    assert payload["expiresAt"]
    assert payload["expiresAtUtc"]
    assert payload["statusSource"] == "live"
    assert payload["tokenExists"] is True


def test_ensure_valid_fyers_auth_accepts_cached_validity_beyond_same_day(monkeypatch, tmp_path):
    project_dir = tmp_path / "fyers"
    token_dir = project_dir / "src"
    token_dir.mkdir(parents=True)
    future_exp = int((dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=20)).timestamp())
    token_path = token_dir / "token.json"
    token_path.write_text(json.dumps({
        "raw_access_token": _build_test_jwt({"exp": future_exp, "iat": future_exp - 3600}),
    }), encoding="utf-8")
    verified_at = dt.datetime.now(service.FYERS_IST).replace(microsecond=0) - dt.timedelta(hours=2)
    valid_until = verified_at.astimezone(dt.timezone.utc) + dt.timedelta(hours=24)

    monkeypatch.setattr(service, "_resolve_fyers_project_dir", lambda: project_dir)
    monkeypatch.setattr(service, "_get_fyers_auth_state", lambda _dir: {
        "last_auth_date": (verified_at.date() - dt.timedelta(days=1)).isoformat(),
        "last_auth_at": verified_at.isoformat(),
        "verified_at": verified_at.isoformat(),
        "verified_at_utc": verified_at.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "valid_until": valid_until.astimezone(service.FYERS_IST).replace(microsecond=0).isoformat(),
        "valid_until_utc": valid_until.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "valid_until_epoch": int(valid_until.timestamp()),
    })

    payload = service.ensure_valid_fyers_auth(profile_validated_at=time.time())

    assert payload["ok"] is True
    assert payload["authenticated"] is True
    assert payload["canExtract"] is True
    assert payload["cached"] is True
    assert payload["remainingValidityMinutes"] > 0


def test_fyers_auth_status_uses_cached_snapshot_when_live_refresh_exceeds_budget(monkeypatch, tmp_path):
    cache_path = tmp_path / "fyers_auth_status.json"
    monkeypatch.setattr(service, "FYERS_AUTH_STATUS_CACHE_FILE", str(cache_path))
    monkeypatch.setattr(service, "FYERS_AUTH_STATUS_CACHE_TTL_SEC", 0.0)
    monkeypatch.setattr(service, "FYERS_AUTH_STATUS_FAST_WAIT_SEC", 0.0)
    monkeypatch.setattr(service, "_IN_MEMORY_AUTH_STATUS", None)
    monkeypatch.setattr(service, "_IN_MEMORY_AUTH_STATUS_TS", 0.0)
    monkeypatch.setattr(service, "_FYERS_AUTH_STATUS_REFRESH_ACTIVE", False)

    service._write_cached_fyers_auth_status({
        "ok": True,
        "stage": "authorize",
        "message": "Authorization status loaded.",
        "statusSource": "authorize",
        "degraded": False,
        "lastAuthorizedDate": service._today_local_iso(),
        "lastAuthorizedAt": "2026-06-08T01:00:00+05:30",
        "authenticatedToday": True,
        "authenticated": True,
        "authExpired": False,
        "expiryAvailable": False,
        "expiresAtEpoch": None,
        "tokenExists": True,
        "tokenPath": "D:/fyers_api_integration/src/token.json",
        "issuedAt": None,
        "issuedAtUtc": None,
        "expiresAt": None,
        "expiresAtUtc": None,
    })
    monkeypatch.setattr(service, "_start_fyers_auth_status_refresh", lambda: (service.threading.Event(), {}))

    payload = service.fyers_auth_status()

    assert payload["ok"] is True
    assert payload["degraded"] is True
    assert payload["statusSource"] == "cache"
    assert payload["authenticated"] is False
    assert payload["canExtract"] is False
    assert "last cached snapshot" in payload["message"]


def test_fyers_auth_status_returns_cached_snapshot_when_refresh_already_active(monkeypatch, tmp_path):
    cache_path = tmp_path / "fyers_auth_status.json"
    monkeypatch.setattr(service, "FYERS_AUTH_STATUS_CACHE_FILE", str(cache_path))
    monkeypatch.setattr(service, "FYERS_AUTH_STATUS_CACHE_TTL_SEC", 0.0)
    monkeypatch.setattr(service, "FYERS_AUTH_STATUS_FAST_WAIT_SEC", 30.0)
    monkeypatch.setattr(service, "_IN_MEMORY_AUTH_STATUS", None)
    monkeypatch.setattr(service, "_IN_MEMORY_AUTH_STATUS_TS", 0.0)
    monkeypatch.setattr(service, "_FYERS_AUTH_STATUS_REFRESH_ACTIVE", True)

    service._write_cached_fyers_auth_status({
        "ok": True,
        "stage": "authorize",
        "message": "Authorization status loaded.",
        "statusSource": "authorize",
        "degraded": False,
        "lastAuthorizedDate": service._today_local_iso(),
        "lastAuthorizedAt": "2026-06-17T09:00:00+05:30",
        "authenticatedToday": True,
        "authenticated": True,
        "authExpired": False,
        "expiryAvailable": False,
        "expiresAtEpoch": None,
        "tokenExists": True,
        "tokenPath": "D:/fyers_api_integration/src/token.json",
        "issuedAt": None,
        "issuedAtUtc": None,
        "expiresAt": None,
        "expiresAtUtc": None,
    })

    started = time.perf_counter()
    payload = service.fyers_auth_status()
    elapsed = time.perf_counter() - started

    assert elapsed < 0.5
    assert payload["ok"] is True
    assert payload["degraded"] is True
    assert payload["statusSource"] == "cache"
    assert payload["authenticated"] is False
    assert payload["canExtract"] is False
    assert "already in progress" in payload["message"]


def test_cleanup_stale_persisted_fyers_jobs_marks_old_active_rows(monkeypatch):
    stale_calls = []
    old_updated_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=service.FYERS_ACTIVE_JOB_STALE_SEC + 60)
    fresh_updated_at = dt.datetime.now(dt.timezone.utc)

    class FakeCursor:
        description = [("JOB_ID",), ("STATUS",), ("UPDATED_AT",), ("STARTED_AT",)]

        def execute(self, _sql):
            return None

        def fetchall(self):
            return [
                ("stale-job", "RUNNING", old_updated_at, old_updated_at),
                ("fresh-job", "RUNNING", fresh_updated_at, fresh_updated_at),
            ]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeAcquire:
        def __enter__(self):
            return FakeConn()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(service.pool, "acquire", lambda: FakeAcquire())
    monkeypatch.setattr(service, "_persist_fyers_stale_job", lambda job_id, reason: stale_calls.append((job_id, reason)) or True)

    service._cleanup_stale_persisted_fyers_jobs()

    assert [job_id for job_id, _reason in stale_calls] == ["stale-job"]


def test_fyers_auth_status_preserves_stale_callback_message_in_degraded_cache():
    payload = service._build_fyers_auth_status_unavailable_payload(
        cached_payload={
            "ok": True,
            "stage": "authorize",
            "lastAuthorizedDate": None,
            "authenticatedToday": False,
            "authenticated": False,
            "canExtract": False,
            "authExpired": True,
            "expiryAvailable": False,
            "expiresAtEpoch": None,
            "tokenExists": False,
            "invalidatedReason": "STALE_CALLBACK",
        },
        error_message="Live status refresh is unavailable.",
    )

    assert payload["status"] == "STALE_CALLBACK"
    assert payload["canExtract"] is False
    assert payload["message"].startswith(service.FYERS_STALE_CALLBACK_MESSAGE)


def test_cleanup_fyers_data_files_only_deletes_old_allowlisted_files(monkeypatch, tmp_path):
    project_dir = tmp_path / "fyers"
    data_dir = project_dir / "data"
    nested_dir = data_dir / "nested"
    nested_dir.mkdir(parents=True)
    old_csv = data_dir / "old.csv"
    recent_json = data_dir / "recent.json"
    disallowed = data_dir / "keep.py"
    nested_file = nested_dir / "old.csv"
    old_csv.write_text("symbol\nRELIANCE\n", encoding="utf-8")
    recent_json.write_text("{}", encoding="utf-8")
    disallowed.write_text("print('keep')", encoding="utf-8")
    nested_file.write_text("nested", encoding="utf-8")
    old_ts = (dt.datetime.now() - dt.timedelta(days=14)).timestamp()
    os.utime(old_csv, (old_ts, old_ts))
    monkeypatch.setattr(service, "_resolve_fyers_project_dir", lambda: project_dir)
    monkeypatch.setattr(service, "FYERS_DATA_DIR", str(data_dir))

    dry_run = service.cleanup_fyers_data_files(dry_run=True, retention_days=7)
    assert dry_run["deleted_count"] == 1
    assert "old.csv" in dry_run["deleted_files"]
    assert old_csv.exists()

    result = service.cleanup_fyers_data_files(dry_run=False, retention_days=7)
    assert result["deleted_count"] == 1
    assert "old.csv" in result["deleted_files"]
    assert not old_csv.exists()
    assert recent_json.exists()
    assert disallowed.exists()
    assert nested_file.exists()


def test_append_job_log_hides_backend_only_fyers_lines():
    job = {
        "logs": [],
        "updated_at": "2026-05-23T09:00:00Z",
    }

    service._append_job_log(job, "[INFO] Raw Fyers symbol: NSE:ORCHPHARMA-EQ")
    service._append_job_log(job, "[INFO] Normalized DB symbol: ORCHPHARMA")
    service._append_job_log(
        job,
        "[INFO] merge_summary symbol=NSE:ORCHPHARMA-EQ selected_start_date=1998-01-01 selected_end_date=2026-05-26",
    )
    service._append_job_log(
        job,
        "[INFO] cache_coverage selected_start_date=1998-01-01 selected_end_date=2026-05-26 cache_min_date=2008-12-12 cache_max_date=2026-04-30 cache_records_count=4306 api_gap_ranges=['1998-01-01->2008-12-11']",
    )
    service._append_job_log(
        job,
        "[INFO] No XLSX produced for API gap 1998-01-01..2008-12-11 for NSE:STLTECH-EQ; skipping load-db for this segment.",
    )
    service._append_job_log(
        job,
        "[INFO] Loading cache segment from XLSX: 2008-12-12..2026-04-30",
    )
    service._append_job_log(
        job,
        "[INFO] direct_api_fetch symbol=NSE:ORCHPHARMA-EQ start_date=1998-01-01 end_date=2026-05-26 resolution=1D file_storage=disabled",
    )
    service._append_job_log(job, "[INFO] Processing 1/1: NSE:ORCHPHARMA-EQ (resolution=1D)")
    service._append_job_log(job, "FYERS rejected symbol 'NSE:STLTECH-EQ'. Use a valid FYERS symbol code (e.g., NSE:RELIANCE-EQ).")
    service._append_job_log(job, "Inserted 0 rows, Updated 0 rows for NSE:STLTECH-EQ into Oracle DB")

    assert job["logs"] == [
        "[INFO] Processing 1/1: NSE:ORCHPHARMA-EQ (resolution=1D)",
        "FYERS rejected symbol 'NSE:STLTECH-EQ'. Use a valid FYERS symbol code (e.g., NSE:RELIANCE-EQ).",
        "Inserted 0 rows, Updated 0 rows for NSE:STLTECH-EQ into Oracle DB",
    ]


def test_fyers_terminal_summary_uses_trade_date_totals_and_failed_symbols():
    result = {
        "request": {"endDate": "2026-06-03"},
        "stats": {"total": 778, "inserted": 776, "skipped": 2, "failed": 0},
        "results": [
            {"normalized_symbol": "NSE:ATLANTAELE-EQ", "status": "FAILED_INVALID_SYMBOL"},
            {"normalized_symbol": "NSE:BRIGADE-EQ", "status": "FAILED_NO_DATA"},
            {"normalized_symbol": "NSE:ATUL-EQ", "status": "SUCCESS"},
        ],
    }

    assert service._build_fyers_terminal_summary_lines(result) == [
        "<===>Summary Details Date:03-06-2026<====>",
        "symbols=778 ->total",
        "inserted=776 ->total",
        "skipped=2 ->total",
        "failed=0 ->total",
        "failed symbols=[ATLANTAELE,BRIGADE]",
    ]


def test_fyers_terminal_summary_appends_once_to_job_log():
    job = {
        "logs": ["Inserted 0 rows, Updated 1 rows for NSE:ATUL-EQ into Oracle DB"],
        "updated_at": "2026-06-04T10:00:00Z",
    }
    result = {
        "request": {"endDate": "2026-06-03"},
        "stats": {"total": 2, "inserted": 1, "skipped": 1, "failed": 0},
        "failedSymbols": ["NSE:ATLANTAELE-EQ"],
    }

    service._append_fyers_terminal_summary(job, result)
    service._append_fyers_terminal_summary(job, result)

    assert job["logs"].count("<===>Summary Details Date:03-06-2026<====>") == 1
    assert job["logs"][-1] == "failed symbols=[ATLANTAELE]"


def test_fyers_request_stop_marks_running_job():
    job_id = "job-stop-test"
    service._FYERS_JOBS.clear()
    service._FYERS_JOBS[job_id] = {
        "id": job_id,
        "stage": "batch",
        "status": "running",
        "message": "Running",
        "started_at": "2026-05-23T09:00:00Z",
        "updated_at": "2026-05-23T09:00:00Z",
        "finished_at": None,
        "finished_ts": 0.0,
        "stats": {"inserted": 0, "skipped": 0, "failed": 0, "errors": 0},
        "logs": [],
        "result": None,
        "login_url": None,
        "stop_requested": False,
        "stop_requested_at": None,
    }

    payload = service.fyers_request_stop(job_id)

    assert payload["stopAccepted"] is True
    assert payload["stopRequested"] is True
    assert payload["message"] == "Fyers automation stop requested. Stopping immediately."
    assert service._FYERS_JOBS[job_id]["stop_requested"] is True
    assert service._FYERS_JOBS[job_id]["message"] == "Fyers automation stop requested. Stopping immediately."
    assert service._FYERS_JOBS[job_id]["logs"][-1] == "[INFO] Stop requested. Stopping FYERS job immediately."
    service._FYERS_JOBS.clear()


def test_fyers_request_stop_finalizes_orphaned_persisted_job_immediately(monkeypatch):
    job_id = "persisted-stop-test"
    service._FYERS_JOBS.clear()
    calls = []
    monkeypatch.setattr(
        service,
        "_persist_fyers_orphaned_stop",
        lambda value: calls.append(value) or True,
    )
    monkeypatch.setattr(
        service,
        "_load_fyers_job_snapshot",
        lambda value, include_symbols=True: {
            "jobId": value,
            "status": "STOPPED",
            "done": True,
            "message": "Stopped by user after the FYERS worker session was no longer active.",
        },
    )

    payload = service.fyers_request_stop(job_id)

    assert calls == [job_id]
    assert payload["stopAccepted"] is True
    assert payload["stopRequested"] is True
    assert payload["status"] == "STOPPED"
    assert payload["done"] is True


def test_direct_fetch_fyers_rows_honours_immediate_stop_before_fetch(monkeypatch):
    with pytest.raises(service.FyersStopRequestedError):
        service._direct_fetch_fyers_rows(
            project_dir=Path("D:/fyers_api_integration"),
            symbol="NSE:RELIANCE-EQ",
            start_date=dt.date(2026, 6, 20),
            end_date=dt.date(2026, 6, 20),
            resolution="1D",
            should_stop=lambda: True,
        )


def test_fyers_start_batch_job_reuses_existing_running_insertion_job():
    job_id = "job-running-batch"
    service._FYERS_JOBS.clear()
    service._FYERS_JOBS[job_id] = {
        "id": job_id,
        "stage": "batch",
        "client_session_id": "session-1",
        "status": "running",
        "message": "Running",
        "started_at": "2026-06-08T10:00:00Z",
        "updated_at": "2026-06-08T10:00:05Z",
        "finished_at": None,
        "finished_ts": 0.0,
        "stats": {"inserted": 10, "skipped": 1, "failed": 0, "errors": 0},
        "logs": ["line-1"],
        "result": None,
        "login_url": None,
        "stop_requested": False,
        "stop_requested_at": None,
    }

    payload = service.fyers_start_batch_job({"clientSessionId": "session-1", "startDate": "2026-06-07", "endDate": "2026-06-08"})

    assert payload["ok"] is False
    assert payload["status"] == "RUNNING"
    assert payload["jobId"] == job_id
    assert payload["runId"] == job_id
    assert payload["job"]["jobId"] == job_id
    assert len(service._FYERS_JOBS) == 1
    service._FYERS_JOBS.clear()


def test_fyers_start_batch_job_allows_new_run_for_different_browser_session(monkeypatch):
    job_id = "job-running-batch"
    started_threads = []

    class FakeThread:
        def __init__(self, *, target, daemon, name):
            self.target = target
            self.daemon = daemon
            self.name = name

        def start(self):
            started_threads.append(self)

    service._FYERS_JOBS.clear()
    service._FYERS_JOBS[job_id] = {
        "id": job_id,
        "stage": "batch",
        "client_session_id": "session-1",
        "status": "running",
        "message": "Running",
        "started_at": "2026-06-08T10:00:00Z",
        "updated_at": "2026-06-08T10:00:05Z",
        "finished_at": None,
        "finished_ts": 0.0,
        "stats": {"inserted": 10, "skipped": 1, "failed": 0, "errors": 0},
        "logs": ["line-1"],
        "result": None,
        "login_url": None,
        "stop_requested": False,
        "stop_requested_at": None,
    }
    monkeypatch.setattr(service.threading, "Thread", FakeThread)
    monkeypatch.setattr(service, "ensure_valid_fyers_auth", lambda **_kwargs: {
        "ok": True,
        "status": "AUTHENTICATED",
        "authenticated": True,
        "canExtract": True,
        "expiresAt": "2026-06-17T23:59:59+05:30",
    })

    payload = service.fyers_start_batch_job({
        "clientSessionId": "session-2",
        "startDate": "2026-06-07",
        "endDate": "2026-06-08",
    })

    assert payload["ok"] is True
    assert payload["status"] == "STARTED"
    assert payload["jobId"] != job_id
    assert len(started_threads) == 1
    assert len(service._FYERS_JOBS) == 2
    service._FYERS_JOBS.clear()


def test_fyers_get_job_returns_running_payload_with_tail():
    job_id = "job-status-tail"
    service._FYERS_JOBS.clear()
    service._FYERS_JOBS[job_id] = {
        "id": job_id,
        "stage": "batch",
        "status": "running",
        "message": "Running",
        "started_at": "2026-05-23T09:00:00Z",
        "updated_at": "2026-05-23T09:01:00Z",
        "finished_at": None,
        "finished_ts": 0.0,
        "stats": {"inserted": 2, "skipped": 1, "failed": 0, "errors": 0},
        "logs": ["line-1", "line-2", "line-3"],
        "result": None,
        "login_url": None,
        "stop_requested": False,
        "stop_requested_at": None,
    }

    payload = service.fyers_get_job(job_id, tail_lines=2)

    assert payload["jobId"] == job_id
    assert payload["done"] is False
    assert payload["logs"]["tail"] == ["line-1", "line-2", "line-3"]
    assert payload["logs"]["totalLines"] == 3
    service._FYERS_JOBS.clear()


def test_fyers_get_job_snapshots_only_requested_log_tail():
    job_id = "job-status-long-tail"
    service._FYERS_JOBS.clear()
    service._FYERS_JOBS[job_id] = {
        "id": job_id,
        "stage": "batch",
        "status": "running",
        "message": "Running",
        "started_at": "2026-05-23T09:00:00Z",
        "updated_at": "2026-05-23T09:01:00Z",
        "finished_at": None,
        "finished_ts": 0.0,
        "stats": {"inserted": 2, "skipped": 1, "failed": 0, "errors": 0},
        "logs": [f"line-{index}" for index in range(1, 101)],
        "result": None,
        "login_url": None,
        "stop_requested": False,
        "stop_requested_at": None,
    }

    payload = service.fyers_get_job(job_id, tail_lines=20)

    assert payload["logs"]["tail"] == [f"line-{index}" for index in range(81, 101)]
    assert payload["logs"]["totalLines"] == 100
    service._FYERS_JOBS.clear()


def test_fyers_get_job_exposes_current_symbol_and_eta_timing(monkeypatch):
    job_id = "job-status-eta"
    service._FYERS_JOBS.clear()
    service._FYERS_JOBS[job_id] = {
        "id": job_id,
        "stage": "batch",
        "status": "running",
        "message": "Running",
        "started_at": "2026-05-23T09:00:00Z",
        "updated_at": "2026-05-23T09:09:30Z",
        "finished_at": None,
        "finished_ts": 0.0,
        "stats": {"completed": 5, "total": 10, "inserted": 5, "skipped": 0, "failed": 0, "errors": 0},
        "logs": ["line-1", "line-2"],
        "result": None,
        "currentSymbol": "NSE:BCLIND-EQ",
        "login_url": None,
        "stop_requested": False,
        "stop_requested_at": None,
    }
    monkeypatch.setattr(service.time, "time", lambda: dt.datetime(2026, 5, 23, 9, 10, tzinfo=dt.timezone.utc).timestamp())

    payload = service.fyers_get_job(job_id, tail_lines=50)

    assert payload["currentSymbol"] == "NSE:BCLIND-EQ"
    assert payload["timing"]["lastHeartbeatAt"] == "2026-05-23T09:09:30Z"
    assert payload["timing"]["completedSymbols"] == 5
    assert payload["timing"]["totalSymbols"] == 10
    assert payload["timing"]["etaTimestamp"] == "2026-05-23T09:20:00Z"
    service._FYERS_JOBS.clear()


def test_fyers_get_job_eta_excludes_first_symbol_startup_overhead(monkeypatch):
    job_id = "job-status-warm-eta"
    service._FYERS_JOBS.clear()
    service._FYERS_JOBS[job_id] = {
        "id": job_id,
        "stage": "batch",
        "status": "running",
        "message": "Running",
        "started_at": "2026-05-23T09:00:00Z",
        "first_completed_at": "2026-05-23T09:08:00Z",
        "updated_at": "2026-05-23T09:10:00Z",
        "finished_at": None,
        "finished_ts": 0.0,
        "stats": {"completed": 5, "total": 10, "inserted": 5, "skipped": 0, "failed": 0, "errors": 0},
        "logs": [],
        "result": None,
        "currentSymbol": "NSE:BCLIND-EQ",
        "login_url": None,
        "stop_requested": False,
        "stop_requested_at": None,
    }
    monkeypatch.setattr(service.time, "time", lambda: dt.datetime(2026, 5, 23, 9, 10, tzinfo=dt.timezone.utc).timestamp())

    payload = service.fyers_get_job(job_id, tail_lines=50)

    assert payload["timing"]["etaTimestamp"] == "2026-05-23T09:12:30Z"
    service._FYERS_JOBS.clear()


def test_fyers_get_job_returns_busy_payload_when_lock_is_held(monkeypatch):
    job_id = "job-status-busy"
    service._FYERS_JOBS.clear()
    service._FYERS_JOBS[job_id] = {
        "id": job_id,
        "stage": "batch",
        "status": "running",
        "message": "Running",
        "started_at": "2026-05-23T09:00:00Z",
        "updated_at": "2026-05-23T09:01:00Z",
        "finished_at": None,
        "finished_ts": 0.0,
        "stats": {"inserted": 0, "skipped": 0, "failed": 0, "errors": 0},
        "logs": [],
        "result": None,
        "login_url": None,
        "stop_requested": False,
        "stop_requested_at": None,
    }
    monkeypatch.setattr(service, "FYERS_JOB_LOCK_TIMEOUT_SEC", 0.2)

    lock = service._FYERS_JOBS_LOCK
    acquired = lock.acquire(timeout=1)
    assert acquired is True
    try:
        payload = service.fyers_get_job(job_id, tail_lines=50)
    finally:
        lock.release()
        service._FYERS_JOBS.clear()

    assert payload["jobId"] == job_id
    assert payload["busy"] is True
    assert payload["done"] is False
    assert "Retrying" in str(payload["message"])


def test_fyers_start_batch_job_returns_started_alias_without_running_request_thread(monkeypatch):
    started_threads = []

    class FakeThread:
        def __init__(self, *, target, daemon, name):
            self.target = target
            self.daemon = daemon
            self.name = name

        def start(self):
            started_threads.append(self)

    service._FYERS_JOBS.clear()
    monkeypatch.setattr(service.threading, "Thread", FakeThread)

    monkeypatch.setattr(service, "ensure_valid_fyers_auth", lambda **_kwargs: {
        "ok": True,
        "status": "AUTHENTICATED",
        "authenticated": True,
        "canExtract": True,
        "expiresAt": "2026-06-17T23:59:59+05:30",
    })

    payload = service.fyers_start_batch_job({
        "startDate": "2026-06-17",
        "endDate": "2026-06-17",
        "authorize": False,
    })

    assert payload["ok"] is True
    assert payload["status"] == "STARTED"
    assert payload["job_id"] == payload["jobId"]
    assert payload["message"] == "FYERS extraction started in background"
    assert len(started_threads) == 1
    assert started_threads[0].daemon is True
    service._FYERS_JOBS.clear()


def test_fyers_batch_start_route_returns_428_without_run_id_when_auth_required(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(marketdata_route.bp)
    client = app.test_client()
    monkeypatch.setattr(
        marketdata_route.svc,
        "fyers_start_batch_job",
        lambda _payload: {
            "ok": False,
            "stage": "authorize",
            "status": "AUTH_REQUIRED",
            "code": "FYERS_AUTH_REQUIRED",
            "errorCode": "FYERS_AUTH_REQUIRED",
            "message": "Authentication Expired. Please authenticate FYERS before extracting symbols.",
            "authenticated": False,
            "canExtract": False,
            "requiresAuthorization": True,
            "shouldRetry": False,
            "expiresAt": None,
        },
    )

    response = client.post(
        "/api/marketdata/fyers/automation/start",
        json={"startDate": "2026-06-19", "endDate": "2026-06-19"},
    )

    assert response.status_code == 428
    payload = response.get_json()
    assert payload["status"] == "AUTH_REQUIRED"
    assert payload["canExtract"] is False
    assert "jobId" not in payload


def test_fyers_get_job_recovers_persisted_snapshot_after_memory_restart(monkeypatch):
    service._FYERS_JOBS.clear()
    include_symbols_values = []
    monkeypatch.setattr(
        service,
        "_load_fyers_job_snapshot",
        lambda job_id, include_symbols=True: include_symbols_values.append(include_symbols) or {
            "jobId": job_id,
            "job_id": job_id,
            "stage": "batch",
            "status": "RUNNING",
            "done": False,
            "message": "Recovered from Oracle.",
            "tradingDate": "2026-06-17",
            "stats": {
                "total": 3,
                "inserted": 1,
                "remaining": 1,
                "failed": 0,
                "skipped": 1,
                "insertedSkipped": 1,
                "invalid": 0,
                "errors": 0,
            },
            "symbols": [],
            "logs": {"tail": [], "totalLines": 0},
            "stopRequested": False,
            "ok": True,
        },
        raising=False,
    )

    payload = service.fyers_get_job("persisted-job", tail_lines=20, include_symbols=False)

    assert payload["jobId"] == "persisted-job"
    assert payload["status"] == "RUNNING"
    assert payload["stats"]["remaining"] == 1
    assert payload["logs"]["tail"] == []
    assert include_symbols_values == [False]


def test_fyers_resume_and_rerun_modes_select_persisted_symbol_statuses(monkeypatch):
    selections = []

    def fake_start(payload, *, statuses, stage):
        selections.append((stage, tuple(statuses), payload["jobId"]))
        return {"ok": True, "jobId": f"{stage}-job", "status": "STARTED"}

    monkeypatch.setattr(service, "_start_fyers_persisted_selection_job", fake_start, raising=False)

    assert service.fyers_resume_job({"jobId": "source-job"})["status"] == "STARTED"
    assert service.fyers_rerun_failed_job({"jobId": "source-job"})["status"] == "STARTED"
    assert service.fyers_rerun_remaining_job({"jobId": "source-job"})["status"] == "STARTED"

    assert selections == [
        ("resume", ("PENDING", "RUNNING", "STOPPED", "FAILED", "INVALID", "ERROR"), "source-job"),
        ("rerun-failed", ("FAILED", "INVALID", "ERROR"), "source-job"),
        ("rerun-remaining", ("PENDING", "RUNNING", "STOPPED"), "source-job"),
    ]


def test_fyers_automation_alias_routes_delegate_to_service(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(marketdata_route.bp)
    client = app.test_client()
    calls = []

    monkeypatch.setattr(
        marketdata_route.svc,
        "fyers_start_authorize_job",
        lambda payload: calls.append(("authorize", payload)) or {"ok": True, "jobId": "auth-1"},
        raising=False,
    )
    monkeypatch.setattr(
        marketdata_route.svc,
        "fyers_start_batch_job",
        lambda payload: calls.append(("start", payload)) or {
            "ok": True,
            "jobId": "job-1",
            "job_id": "job-1",
            "status": "STARTED",
        },
    )
    monkeypatch.setattr(
        marketdata_route.svc,
        "fyers_get_job",
        lambda job_id, tail_lines=None, include_symbols=True: calls.append(("status", job_id, tail_lines, include_symbols)) or {
            "ok": True,
            "jobId": job_id,
        },
    )
    monkeypatch.setattr(
        marketdata_route.svc,
        "fyers_request_stop",
        lambda job_id: calls.append(("stop", job_id)) or {"ok": True, "jobId": job_id},
    )
    monkeypatch.setattr(
        marketdata_route.svc,
        "fyers_resume_job",
        lambda payload: calls.append(("resume", payload)) or {"ok": True, "jobId": "resume-1"},
        raising=False,
    )
    monkeypatch.setattr(
        marketdata_route.svc,
        "fyers_rerun_failed_job",
        lambda payload: calls.append(("rerun-failed", payload)) or {"ok": True, "jobId": "failed-1"},
        raising=False,
    )
    monkeypatch.setattr(
        marketdata_route.svc,
        "fyers_rerun_remaining_job",
        lambda payload: calls.append(("rerun-remaining", payload)) or {"ok": True, "jobId": "remaining-1"},
        raising=False,
    )
    monkeypatch.setattr(
        marketdata_route.svc,
        "fyers_get_latest_active_job",
        lambda: calls.append(("latest-active",)) or {"ok": True, "job": None},
        raising=False,
    )
    monkeypatch.setattr(
        marketdata_route.svc,
        "fyers_get_skipped_symbols",
        lambda job_id: calls.append(("skipped", job_id)) or {"ok": True, "jobId": job_id, "symbols": []},
        raising=False,
    )

    assert client.post("/api/marketdata/fyers/authorize", json={"force": True}).status_code == 200
    assert client.post("/api/marketdata/fyers/automation/start", json={"endDate": "2026-06-17"}).status_code == 200
    assert client.post("/api/marketdata/fyers/extract/start", json={"endDate": "2026-06-17"}).status_code == 200
    assert client.get("/api/marketdata/fyers/automation/status/job-1?tail=25").status_code == 200
    assert client.get("/api/marketdata/fyers/extract/status/job-1?tail=25").status_code == 200
    assert client.post("/api/marketdata/fyers/automation/stop/job-1").status_code == 200
    assert client.post("/api/marketdata/fyers/extract/stop/job-1").status_code == 200
    assert client.post("/api/marketdata/fyers/automation/resume", json={"jobId": "job-1"}).status_code == 200
    assert client.post("/api/marketdata/fyers/automation/rerun-failed", json={"jobId": "job-1"}).status_code == 200
    assert client.post("/api/marketdata/fyers/extract/rerun-failed", json={"jobId": "job-1"}).status_code == 200
    assert client.post("/api/marketdata/fyers/automation/rerun-remaining", json={"jobId": "job-1"}).status_code == 200
    assert client.post("/api/marketdata/fyers/extract/rerun-remaining", json={"jobId": "job-1"}).status_code == 200
    assert client.get("/api/marketdata/fyers/automation/latest-active-job").status_code == 200
    assert client.get("/api/marketdata/fyers/automation/skipped-symbols/job-1").status_code == 200

    assert calls == [
        ("authorize", {"force": True}),
        ("start", {"endDate": "2026-06-17"}),
        ("start", {"endDate": "2026-06-17"}),
        ("status", "job-1", 25, False),
        ("status", "job-1", 25, False),
        ("stop", "job-1"),
        ("stop", "job-1"),
        ("resume", {"jobId": "job-1"}),
        ("rerun-failed", {"jobId": "job-1"}),
        ("rerun-failed", {"jobId": "job-1"}),
        ("rerun-remaining", {"jobId": "job-1"}),
        ("rerun-remaining", {"jobId": "job-1"}),
        ("latest-active",),
        ("skipped", "job-1"),
    ]


def test_build_fyers_symbol_lookup_parses_headerless_master_and_manual_alias():
    master_df = service.pd.DataFrame(
        [
            ["1001", "AIMTRON ELECTRONICS", "NSE:AIMTRON-SM", "AIMTRON"],
            ["1002", "APTECH LIMITED", "NSE:APTECHT-BE", "APTECHT"],
            ["1003", "BOSCH HCIL", "NSE:BOSCH-HCIL-EQ", "BOSCH-HCIL"],
            ["1004", "AB S MARINE", "NSE:ABSMARINE-ST", "ABSMARINE"],
            ["1005", "BZ TEST", "NSE:BZTEST-BZ", "BZTEST"],
            ["1006", "IGNORE ME", "NSE:IGNORED-XX", "IGNORED"],
        ]
    )

    lookup = service._build_fyers_symbol_lookup(master_df)

    assert lookup["AIMTRON"] == "NSE:AIMTRON-SM"
    assert lookup["APTECHT"] == "NSE:APTECHT-BE"
    assert lookup["BOSCH-HCIL"] == "NSE:BOSCH-HCIL-EQ"
    assert lookup["BOSCHHCIL"] == "NSE:BOSCH-HCIL-EQ"
    assert lookup["ABSMARINE"] == "NSE:ABSMARINE-ST"
    assert lookup["BZTEST"] == "NSE:BZTEST-BZ"
    assert "IGNORED" not in lookup


def test_resolve_fyers_symbol_cleans_wrong_suffixes_and_manual_alias():
    lookup = {
        "AIMTRON": "NSE:AIMTRON-SM",
        "APTECHT": "NSE:APTECHT-BE",
        "ABSMARINE": "NSE:ABSMARINE-ST",
        "BZTEST": "NSE:BZTEST-BZ",
        "BODALCHEM": "NSE:BODALCHEM-EQ",
        "BOSCH-HCIL": "NSE:BOSCH-HCIL-EQ",
        "BOSCHHCIL": "NSE:BOSCH-HCIL-EQ",
        "CHOLAFIN": "NSE:CHOLAFIN-EQ",
        "RBLBANK": "NSE:RBLBANK-EQ",
        "SYSTMTXC": "NSE:SYSTMTXC-BE",
    }

    assert service.resolve_fyers_symbol("NSE:AIMTRON-EQ", lookup) == "NSE:AIMTRON-SM"
    assert service.resolve_fyers_symbol(" APTECHT ", lookup) == "NSE:APTECHT-BE"
    assert service.resolve_fyers_symbol("NSE:ABSMARINE-EQ", lookup) == "NSE:ABSMARINE-ST"
    assert service.resolve_fyers_symbol("NSE:BZTEST-EQ", lookup) == "NSE:BZTEST-BZ"
    assert service.resolve_fyers_symbol("NSE:BODALCHEM-EQ", lookup) == "NSE:BODALCHEM-EQ"
    assert service.resolve_fyers_symbol("NSE:BOSCHHCIL-EQ", lookup) == "NSE:BOSCH-HCIL-EQ"
    assert service.resolve_fyers_symbol("NSE:CHOLAINV-EQ", lookup) == "NSE:CHOLAFIN-EQ"
    assert service.resolve_fyers_symbol("NSE:RBL-EQ", lookup) == "NSE:RBLBANK-EQ"
    assert service.resolve_fyers_symbol("NSE:SYSTEMATIX-EQ", lookup) == "NSE:SYSTMTXC-BE"
    assert service.resolve_fyers_symbol("NSE:UNKNOWN-EQ", lookup) is None
    assert service._normalize_fyers_symbol("APTECHT-BE") == "NSE:APTECHT-BE"
    assert service._normalize_fyers_symbol("AIMTRON-SM") == "NSE:AIMTRON-SM"
    assert service._normalize_fyers_symbol("ABSMARINE-ST") == "NSE:ABSMARINE-ST"
    assert service._normalize_fyers_symbol("BZTEST-BZ") == "NSE:BZTEST-BZ"


def test_fyers_run_single_resolves_symbols_and_skips_missing_master_rows(monkeypatch):
    class FakeAcquire:
        def __enter__(self):
            return object()

        def __exit__(self, *_args):
            return False

    class FakePool:
        def acquire(self):
            return FakeAcquire()

    loaded_dates: dict[str, set[dt.date]] = {}
    fetch_calls: list[str] = []
    merged_failures: list[dict[str, object]] = []
    skipped_rows: list[dict[str, object]] = []
    log_lines: list[str] = []

    monkeypatch.setattr(service, "pool", FakePool())
    monkeypatch.setattr(service, "FYERS_REQUEST_SLEEP_SECONDS", 0)
    monkeypatch.setattr(service, "_get_fyers_symbol_lookup", lambda force_refresh=False: {
        "AIMTRON": "NSE:AIMTRON-SM",
    })
    monkeypatch.setattr(service, "ensure_valid_fyers_auth", lambda **_kwargs: {
        "ok": True,
        "cached": True,
        "message": "FYERS authenticated.",
        "authDate": "2026-06-03",
        "authenticated": True,
        "canExtract": True,
        "expiresAt": "2026-06-03T23:59:59+05:30",
    })
    monkeypatch.setattr(service, "_resolve_fyers_project_dir", lambda: Path("D:/fyers_api_integration"))
    monkeypatch.setattr(service, "_ensure_fyers_tracking_tables", lambda _conn: None)
    monkeypatch.setattr(service, "_fetch_actual_trading_dates", lambda *_args, **_kwargs: {dt.date(2026, 6, 3)})
    monkeypatch.setattr(service, "_db_init_extraction_run", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "_db_init_extraction_symbols", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "_db_update_extraction_symbol", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "_db_update_extraction_run_counts", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "_fetch_previously_failed_permanent_symbols", lambda *_args, **_kwargs: set())
    monkeypatch.setattr(
        service,
        "_build_fyers_fetch_ranges",
        lambda **_kwargs: [(dt.date(2026, 6, 3), dt.date(2026, 6, 3))],
    )
    monkeypatch.setattr(
        service,
        "_fetch_existing_symbol_dates_by_range",
        lambda _conn, symbol, *_args, **_kwargs: loaded_dates.get(symbol, set()),
    )
    monkeypatch.setattr(
        service,
        "_direct_fetch_fyers_rows",
        lambda *, symbol, **_kwargs: (
            fetch_calls.append(symbol) or [(symbol, dt.date(2026, 6, 3))],
            1,
            {"chunks": 1, "rate_limit_retries": 0},
        ),
    )
    monkeypatch.setattr(
        service,
        "_upsert_fyers_rows_direct",
        lambda _conn, rows: loaded_dates.setdefault(rows[0][0], set()).add(rows[0][1]) or 1,
    )
    monkeypatch.setattr(service, "_merge_success_symbol_dates", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "_merge_failed_symbol", lambda _conn, **kwargs: merged_failures.append(kwargs))
    monkeypatch.setattr(service, "_insert_skipped_rejected_symbol", lambda _conn, **kwargs: skipped_rows.append(kwargs))

    payload = service.fyers_run_single(
        {
            "symbol": "NSE:AIMTRON-EQ,NSE:UNKNOWN-EQ",
            "startDate": "2026-06-03",
            "endDate": "2026-06-03",
            "authorize": False,
        },
        line_logger=log_lines.append,
    )

    assert fetch_calls == ["NSE:AIMTRON-SM"]
    assert payload["ok"] is True
    assert payload["status"] == "PARTIAL_SUCCESS"
    assert payload["stats"]["processed"] == 2
    assert payload["stats"]["inserted"] == 1
    assert payload["stats"]["skipped"] == 1
    assert payload["stats"]["failed"] == 0
    assert [row["status"] for row in payload["results"]] == ["SUCCESS", "FAILED_INVALID_SYMBOL"]
    assert merged_failures == [
        {
            "input_symbol": "NSE:UNKNOWN-EQ",
            "normalized_symbol": "NSE:UNKNOWN-EQ",
            "status": "FAILED_INVALID_SYMBOL",
            "error_code": "INVALID_SYMBOL",
            "error_message": "Symbol UNKNOWN not found in FYERS symbol master.",
            "start_date": dt.date(2026, 6, 3),
            "end_date": dt.date(2026, 6, 3),
            "retry_count": 0,
        }
    ]
    assert skipped_rows[0]["symbol"] == "NSE:UNKNOWN-EQ"
    assert skipped_rows[0]["fyers_symbol"] == "NSE:UNKNOWN-EQ"
    assert skipped_rows[0]["error_code"] == "INVALID_SYMBOL"
    assert any(
        line == "[FYERS_SYMBOL_RESOLVE] Input=NSE:AIMTRON-EQ Clean=AIMTRON Resolved=NSE:AIMTRON-SM Status=OK"
        for line in log_lines
    )
    assert any(
        line == "[FYERS_SYMBOL_RESOLVE] Input=NSE:UNKNOWN-EQ Clean=UNKNOWN Resolved=None Status=MISSING"
        for line in log_lines
    )


def test_fyers_run_single_fetches_full_range_without_prefetching_stock_history(monkeypatch):
    class FakeAcquire:
        def __enter__(self):
            return object()

        def __exit__(self, *_args):
            return False

    class FakePool:
        def acquire(self):
            return FakeAcquire()

    existing_dates = {dt.date(2026, 6, 3), dt.date(2026, 6, 4)}
    actual_date_calls: list[bool] = []
    existing_lookup_calls: list[str] = []
    fetch_calls: list[tuple[dt.date, dt.date]] = []
    log_lines: list[str] = []

    monkeypatch.setattr(service, "pool", FakePool())
    monkeypatch.setattr(service, "FYERS_REQUEST_SLEEP_SECONDS", 0)
    monkeypatch.setattr(service, "_get_fyers_symbol_lookup", lambda force_refresh=False: {"ITC": "NSE:ITC-EQ"})
    monkeypatch.setattr(service, "ensure_valid_fyers_auth", lambda **_kwargs: {
        "ok": True,
        "cached": True,
        "authenticated": True,
        "canExtract": True,
    })
    monkeypatch.setattr(service, "_resolve_fyers_project_dir", lambda: Path("D:/fyers_api_integration"))
    monkeypatch.setattr(service, "_ensure_fyers_tracking_tables", lambda _conn: None)
    monkeypatch.setattr(
        service,
        "_fetch_actual_trading_dates",
        lambda *_args, **_kwargs: actual_date_calls.append(True) or set(existing_dates),
    )
    monkeypatch.setattr(service, "_db_init_extraction_run", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "_db_init_extraction_symbols", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "_db_update_extraction_symbol", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "_db_update_extraction_run_counts", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "_fetch_previously_failed_permanent_symbols", lambda *_args, **_kwargs: set())
    monkeypatch.setattr(
        service,
        "_fetch_existing_symbol_dates_by_range",
        lambda _conn, symbol, *_args, **_kwargs: existing_lookup_calls.append(symbol) or set(existing_dates),
    )
    monkeypatch.setattr(
        service,
        "_direct_fetch_fyers_rows",
        lambda *, start_date, end_date, **_kwargs: (
            fetch_calls.append((start_date, end_date))
            or ([
                ("NSE:ITC-EQ", dt.date(2026, 6, 3), 10.0, 11.0, 9.0, 10.5, 1000),
            ], 1, {"chunks": 1, "rate_limit_retries": 0})
        ),
    )
    monkeypatch.setattr(
        service,
        "_upsert_fyers_rows_direct",
        lambda _conn, _rows: {
            "inserted": 0,
            "updated": 0,
            "skipped": 0,
            "merged": 1,
            "inserted_dates": {dt.date(2026, 6, 3)},
            "duplicate_dates": set(),
        },
    )
    monkeypatch.setattr(service, "_merge_success_symbol_dates", lambda *_args, **_kwargs: None)

    payload = service.fyers_run_single(
        {
            "symbol": "ITC",
            "startDate": "2026-06-03",
            "endDate": "2026-06-04",
            "authorize": False,
        },
        line_logger=log_lines.append,
    )

    assert payload["ok"] is True
    assert actual_date_calls == []
    assert existing_lookup_calls == []
    assert fetch_calls == [(dt.date(2026, 6, 3), dt.date(2026, 6, 4))]
    assert payload["status"] == "SUCCESS"
    assert payload["stats"]["existing_rows"] == 0
    assert payload["stats"]["missing_ranges_count"] == 1
    assert payload["stats"]["skipped_existing_rows"] == 0
    assert payload["results"][0]["status"] == "SUCCESS"
    assert any("status=COVERAGE_CHECK" in line and "existing_rows=0" in line for line in log_lines)


def test_upsert_fyers_rows_deduplicates_symbol_and_trade_date_before_direct_merge(monkeypatch):
    monkeypatch.setattr(service, "_fetch_existing_fyers_ohlcv_by_range", lambda *_args, **_kwargs: {})

    class FakeCursor:
        def __init__(self):
            self.executemany_rows = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def executemany(self, _sql, rows):
            self.executemany_rows = list(rows)

    class FakeConnection:
        def __init__(self):
            self.cursor_instance = FakeCursor()
            self.commits = 0

        def cursor(self):
            return self.cursor_instance

        def commit(self):
            self.commits += 1

    connection = FakeConnection()
    result = service._upsert_fyers_rows_direct(
        connection,
        [
            ("nse:ITC-eq", dt.date(2026, 6, 3), 10, 11, 9, 10.5, 1000),
            ("NSE:ITC-EQ", dt.date(2026, 6, 3), 10.1, 11.1, 9.1, 10.6, 1100),
            ("NSE:ITC-EQ", dt.date(2026, 6, 4), 10.2, 11.2, 9.2, 10.7, 1200),
        ],
    )

    assert result["input_rows"] == 3
    assert result["merged"] == 2
    assert result["inserted"] == 2
    assert result["updated"] == 0
    assert result["skipped"] == 0
    assert len(connection.cursor_instance.executemany_rows) == 2
    assert {(row["symbol"], row["trade_date"]) for row in connection.cursor_instance.executemany_rows} == {
        ("NSE:ITC-EQ", dt.date(2026, 6, 3)),
        ("NSE:ITC-EQ", dt.date(2026, 6, 4)),
    }
    assert connection.commits == 1


def test_upsert_fyers_rows_reports_updated_and_unchanged_existing_rows(monkeypatch):
    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def executemany(self, _sql, _rows):
            return None

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

        def commit(self):
            return None

    monkeypatch.setattr(
        service,
        "_fetch_existing_fyers_ohlcv_by_range",
        lambda *_args, **_kwargs: {
            dt.date(2026, 6, 3): (10, 11, 9, 10.5, 1000),
            dt.date(2026, 6, 4): (10, 11, 9, 10.5, 1000),
        },
    )

    result = service._upsert_fyers_rows_direct(
        FakeConnection(),
        [
            ("NSE:ITC-EQ", dt.date(2026, 6, 3), 10, 11, 9, 10.5, 1000),
            ("NSE:ITC-EQ", dt.date(2026, 6, 4), 10, 11, 9, 10.6, 1000),
            ("NSE:ITC-EQ", dt.date(2026, 6, 5), 10, 11, 9, 10.7, 1000),
        ],
    )

    assert result["inserted"] == 1
    assert result["updated"] == 1
    assert result["skipped"] == 1
    assert result["inserted_dates"] == {dt.date(2026, 6, 5)}
    assert result["duplicate_dates"] == {dt.date(2026, 6, 3), dt.date(2026, 6, 4)}


def test_fetch_fyers_ohlcv_for_missing_ranges_continues_after_range_failure(monkeypatch):
    calls: list[tuple[dt.date, dt.date]] = []

    def fake_fetch(*, start_date, end_date, symbol, **_kwargs):
        calls.append((start_date, end_date))
        if start_date == dt.date(2026, 6, 3):
            raise RuntimeError("temporary FYERS range timeout")
        return (
            [(symbol, end_date, 10.0, 11.0, 9.0, 10.5, 1000)],
            1,
            {"chunks": 1, "rate_limit_retries": 0},
        )

    monkeypatch.setattr(service, "_direct_fetch_fyers_rows", fake_fetch)

    payload = service._fetch_fyers_ohlcv_for_missing_ranges(
        project_dir=Path("D:/fyers_api_integration"),
        symbol="NSE:ITC-EQ",
        fetch_ranges=[
            (dt.date(2026, 6, 3), dt.date(2026, 6, 3)),
            (dt.date(2026, 6, 4), dt.date(2026, 6, 4)),
        ],
        resolution="1D",
    )

    assert calls == [
        (dt.date(2026, 6, 3), dt.date(2026, 6, 3)),
        (dt.date(2026, 6, 4), dt.date(2026, 6, 4)),
    ]
    assert len(payload["rows"]) == 1
    assert payload["fetched_rows"] == 1
    assert payload["failed_ranges"] == [{
        "from": "2026-06-03",
        "to": "2026-06-03",
        "error_message": "temporary FYERS range timeout",
    }]


def test_fyers_value_change_detection_splits_changed_and_unchanged_rows():
    unchanged = ("10", "11", "9", "10.5", "1000")
    changed_close = ("10", "11", "9", "10.6", "1000")
    incoming = ("ITC", dt.date(2026, 6, 3), 10.0, 11.0, 9.0, 10.5, 1000)

    assert service._fyers_values_changed(None, incoming) is True
    assert service._fyers_values_changed(unchanged, incoming) is False
    assert service._fyers_values_changed(changed_close, incoming) is True
