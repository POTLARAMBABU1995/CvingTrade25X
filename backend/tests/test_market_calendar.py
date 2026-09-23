import datetime as dt
import json
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.utils import market_calendar


CONFIG_ROOT = BACKEND_ROOT.parent / 'config'


def test_market_calendar_blocks_weekends_and_2026_holidays():
    assert market_calendar.is_weekend(dt.date(2026, 5, 30)) is True
    assert market_calendar.is_market_working_day(dt.date(2026, 5, 30)) is False
    assert market_calendar.is_nse_holiday(dt.date(2026, 5, 28)) is True
    assert market_calendar.is_market_working_day(dt.date(2026, 5, 28)) is False


def test_market_calendar_matches_approved_2026_holiday_config():
    approved_payload = json.loads((CONFIG_ROOT / 'nse_holidays.json').read_text(encoding='utf-8'))
    approved_holidays = {
        dt.datetime.strptime(value, '%Y-%m-%d').date()
        for value in approved_payload['holidays']
    }

    assert market_calendar.get_nse_holidays(2026) == approved_holidays
    assert market_calendar.is_nse_holiday(dt.date(2026, 1, 15)) is True
    assert market_calendar.is_market_working_day(dt.date(2026, 1, 15)) is False
    assert market_calendar.is_market_working_day(dt.date(2026, 11, 10)) is True
    assert market_calendar.is_nse_holiday(dt.date(2026, 11, 11)) is True


def test_market_calendar_allows_budget_day_special_sunday_session():
    assert market_calendar.is_weekend(dt.date(2026, 2, 1)) is True
    assert market_calendar.is_special_market_working_day(dt.date(2026, 2, 1)) is True
    assert market_calendar.is_market_working_day(dt.date(2026, 2, 1)) is True
    assert market_calendar.validate_market_date('01-02-2026') == dt.date(2026, 2, 1)


def test_market_calendar_validate_requires_override_for_closed_days():
    with pytest.raises(ValueError, match='not an NSE market working day'):
        market_calendar.validate_market_date('2026-05-28')

    assert market_calendar.validate_market_date('2026-05-28', allow_override=True) == dt.date(2026, 5, 28)


def test_market_calendar_previous_working_day_skips_holiday_and_weekend():
    assert market_calendar.get_previous_market_working_day('2026-05-30') == dt.date(2026, 5, 29)
