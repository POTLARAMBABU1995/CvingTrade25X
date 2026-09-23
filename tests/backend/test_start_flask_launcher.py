from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = PROJECT_ROOT / "start_flask_cvingtrade25x.bat"
HIDDEN_VBS = PROJECT_ROOT / "start_cvingtrade25x_hidden.vbs"


def _launcher_text() -> str:
  return LAUNCHER.read_text(encoding="utf-8")


def _hidden_vbs_text() -> str:
  return HIDDEN_VBS.read_text(encoding="utf-8")


def test_generated_runner_receives_configured_port():
  text = _launcher_text()

  assert 'echo set "PORT=%PORT%"' in text


def test_launcher_logs_are_visible_in_console_and_file():
  text = _launcher_text()
  log_block = text.split("\n:log\n", 1)[1].split("\n:is_port_listening\n", 1)[0]
  lines = {line.strip() for line in log_block.splitlines()}

  assert 'echo [%DATE% %TIME%] %~1' in lines
  assert '>> "%STARTUP_LOG%" echo [%DATE% %TIME%] %~1' in lines


def test_health_wait_uses_one_bounded_deadline():
  text = _launcher_text()
  wait_block = text.split("\n:wait_http_healthy\n", 1)[1].split("\n:stop_stale_python_listener\n", 1)[0]

  assert "AddSeconds($waitSeconds)" in wait_block
  assert "for /L %%I in (1,1,%WAIT_SECONDS%)" not in wait_block


def test_failure_log_printing_does_not_mix_powershell_encoding_into_startup_log():
  text = _launcher_text()
  tail_block = text.split("\n:append_flask_tail\n", 1)[1]

  assert "Tee-Object -FilePath '%STARTUP_LOG%'" not in tail_block


def test_hidden_vbs_explicitly_requests_hidden_launcher_mode():
  text = _hidden_vbs_text()

  assert 'call """ & launcher & """ --hidden' in text


def test_manual_double_click_reopens_in_interactive_shell():
  text = _launcher_text()

  assert 'start "CvingTrade25X Startup" "%ComSpec%" /d /k call "%~f0" --interactive' in text


def test_launcher_acquires_startup_lock_before_generating_runner():
  text = _launcher_text()

  assert 'set "STARTUP_LOCK_DIR=%LOG_DIR%\\cvingtrade25x_startup.lock"' in text
  assert 'call :acquire_startup_lock "%STARTUP_LOCK_WAIT_SECONDS%"' in text
  assert 'call :clear_stale_startup_lock "%STARTUP_LOCK_STALE_SECONDS%"' in text
