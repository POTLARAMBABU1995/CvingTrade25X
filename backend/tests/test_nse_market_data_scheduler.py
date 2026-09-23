import datetime as dt
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from automation import nse_market_data_scheduler as scheduler


def test_monday_automation_targets_previous_friday_for_all_enabled_modules(monkeypatch):
    config = dict(scheduler.DEFAULT_CONFIG)
    holidays = scheduler.market_calendar.get_nse_holidays(2026)

    monkeypatch.setattr(
        scheduler,
        '_missing_modules_for_date',
        lambda trade_date, _config: scheduler.MODULES if trade_date == dt.date(2026, 1, 16) else (),
    )

    target = scheduler._target_context(
        now_local=dt.datetime(2026, 1, 19, 8, 30),
        config=config,
        holidays=holidays,
        current_start_time=dt.time(17, 0),
    )

    assert target['should_run'] is True
    assert target['trade_date'] == dt.date(2026, 1, 16)
    assert target['target_date_type'] == scheduler.TARGET_PREVIOUS
    assert target['current_status'] == scheduler.RUNTIME_STATUS_PREVIOUS_PENDING
    assert all(module in target['message'] for module in scheduler.MODULES)


def test_recover_stale_running_status_marks_interrupted_run_failed(monkeypatch, tmp_path):
    stale_lock = tmp_path / 'nse_marketdata_automation.lock'
    stale_lock.write_text(
        '{"pid": 987654, "started_ts": 1781267126.0, "started_at": "2026-06-12T17:55:26"}',
        encoding='utf-8',
    )
    stale_status = {
        'current_status': scheduler.RUNTIME_STATUS_RUNNING,
        'is_running': True,
        'last_run_id': 'RUN_20260612_175526',
        'target_trade_date': '2026-06-12',
        'target_date_type': scheduler.TARGET_CURRENT,
        'message': 'Current trading date is eligible after 5 PM IST.',
        'modules': {
            scheduler.MODULE_MCAP: {
                'status': 'SKIPPED_ALREADY_LOADED',
                'message': 'Rows already exist for 2026-06-12.',
            },
            scheduler.MODULE_FFMC: {
                'status': 'PENDING_RETRY',
                'message': 'Pending module execution.',
            },
            scheduler.MODULE_DELIVERY: {
                'status': 'PENDING_RETRY',
                'message': 'Pending module execution.',
            },
        },
    }
    merged = {}

    monkeypatch.setattr(scheduler, 'LOCK_PATH', stale_lock)
    monkeypatch.setattr(scheduler.status_svc, 'load_status', lambda create_if_missing=True: stale_status)
    monkeypatch.setattr(scheduler.status_svc, 'merge_status', lambda payload: merged.update(payload) or payload)
    monkeypatch.setattr(scheduler, '_is_process_alive', lambda _pid: False)
    monkeypatch.setattr(scheduler, '_emit', lambda *_args, **_kwargs: None)

    recovered = scheduler._recover_stale_running_status(
        now_ts=1781278127.0,
        now_local=dt.datetime(2026, 6, 12, 21, 0, tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30))),
        lock_stale_seconds=3 * 60 * 60,
    )

    assert recovered is True
    assert merged['current_status'] == scheduler.RUNTIME_STATUS_FAILED
    assert merged['is_running'] is False
    assert merged['modules'][scheduler.MODULE_MCAP]['status'] == 'SKIPPED_ALREADY_LOADED'
    assert merged['modules'][scheduler.MODULE_FFMC]['status'] == 'FAILED'
    assert merged['modules'][scheduler.MODULE_DELIVERY]['status'] == 'FAILED'
    assert 'interrupted before completion' in merged['message']
