from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Iterable, Sequence, Set

logger = logging.getLogger(__name__)

_NSE_2026_HOLIDAY_TEXT = (
  "2026-01-15",
  "2026-01-26",
  "2026-03-03",
  "2026-03-26",
  "2026-03-31",
  "2026-04-03",
  "2026-04-14",
  "2026-05-01",
  "2026-05-28",
  "2026-06-26",
  "2026-09-14",
  "2026-10-02",
  "2026-10-20",
  "2026-11-11",
  "2026-11-24",
  "2026-12-25",
)
_NSE_2026_SPECIAL_WORKING_TEXT = (
  "2026-02-01",
)

NSE_HOLIDAYS_2026: Set[dt.date] = {
  dt.datetime.strptime(value, "%Y-%m-%d").date()
  for value in _NSE_2026_HOLIDAY_TEXT
}
NSE_SPECIAL_WORKING_DAYS_2026: Set[dt.date] = {
  dt.datetime.strptime(value, "%Y-%m-%d").date()
  for value in _NSE_2026_SPECIAL_WORKING_TEXT
}


def _coerce_date(value: Any) -> dt.date:
  if isinstance(value, dt.datetime):
    return value.date()
  if isinstance(value, dt.date):
    return value
  text = str(value or "").strip()
  if not text:
    raise ValueError("Market date is required.")
  normalized = text.replace("Z", "+00:00")
  for candidate in (normalized, normalized.split("T", 1)[0], normalized.split(" ", 1)[0]):
    try:
      return dt.datetime.fromisoformat(candidate).date()
    except ValueError:
      continue
  for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d-%b-%Y", "%d-%b-%y", "%d%m%Y"):
    try:
      return dt.datetime.strptime(text, fmt).date()
    except ValueError:
      continue
  raise ValueError("Invalid market date. Expected YYYY-MM-DD.")


def get_nse_holidays(year: int | None = None) -> Set[dt.date]:
  holidays = set(NSE_HOLIDAYS_2026)
  if year is None:
    return holidays
  return {holiday for holiday in holidays if holiday.year == int(year)}


def get_nse_special_working_days(year: int | None = None) -> Set[dt.date]:
  days = set(NSE_SPECIAL_WORKING_DAYS_2026)
  if year is None:
    return days
  return {day for day in days if day.year == int(year)}


def _dates_for_year(year: int) -> list[dt.date]:
  start = dt.date(int(year), 1, 1)
  end = dt.date(int(year), 12, 31)
  total_days = (end - start).days + 1
  return [start + dt.timedelta(days=offset) for offset in range(total_days)]


def is_weekend(value: Any) -> bool:
  return _coerce_date(value).weekday() >= 5


def is_special_market_working_day(value: Any) -> bool:
  return _coerce_date(value) in NSE_SPECIAL_WORKING_DAYS_2026


def is_nse_holiday(value: Any) -> bool:
  return _coerce_date(value) in NSE_HOLIDAYS_2026


def is_market_working_day(value: Any) -> bool:
  target_date = _coerce_date(value)
  if is_special_market_working_day(target_date):
    return True
  return not is_weekend(target_date) and not is_nse_holiday(target_date)


def get_market_calendar_for_year(year: int, current_date: Any | None = None) -> dict[str, Any]:
  target_year = int(year)
  as_of_date = _coerce_date(current_date) if current_date is not None else dt.date.today()
  all_dates = _dates_for_year(target_year)
  trading_dates = [value for value in all_dates if is_market_working_day(value)]
  trading_set = set(trading_dates)
  non_trading_dates = [value for value in all_dates if value not in trading_set]
  weekend_dates = [
    value for value in all_dates
    if is_weekend(value) and not is_special_market_working_day(value)
  ]
  holiday_dates = sorted(get_nse_holidays(target_year))
  special_working_dates = sorted(get_nse_special_working_days(target_year))

  if as_of_date.year < target_year:
    completed_cutoff = dt.date(target_year, 1, 1) - dt.timedelta(days=1)
  elif as_of_date.year > target_year:
    completed_cutoff = dt.date(target_year, 12, 31)
  else:
    ist_now = dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30)))
    ist_today = ist_now.date()
    is_before_5pm = ist_now.time() < dt.time(17, 0, 0)
    if as_of_date == ist_today and is_before_5pm:
      completed_cutoff = as_of_date - dt.timedelta(days=1)
    else:
      completed_cutoff = as_of_date

  trading_days_completed = [value for value in trading_dates if value <= completed_cutoff]
  trading_days_remaining = [value for value in trading_dates if value > completed_cutoff]

  return {
    "year": target_year,
    "as_of_date": as_of_date,
    "calendar_days": len(all_dates),
    "weekend_count": len(weekend_dates),
    "holiday_count": len(holiday_dates),
    "special_working_day_count": len(special_working_dates),
    "non_trading_days": len(non_trading_dates),
    "trading_days_cy": len(trading_dates),
    "trading_days_completed_cy": len(trading_days_completed),
    "trading_days_remaining_cy": len(trading_days_remaining),
    "trading_dates": trading_dates,
    "non_trading_dates": non_trading_dates,
    "holiday_dates": holiday_dates,
    "special_working_dates": special_working_dates,
  }


def split_missing_dates_by_current_date(missing_dates: Sequence[Any], current_date: Any | None = None) -> dict[str, list[dt.date]]:
  as_of_date = _coerce_date(current_date) if current_date is not None else dt.date.today()
  normalized = sorted({_coerce_date(value) for value in missing_dates})
  ist_now = dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30)))
  ist_today = ist_now.date()
  is_before_5pm = ist_now.time() < dt.time(17, 0, 0)
  if as_of_date == ist_today and is_before_5pm:
    cutoff = as_of_date - dt.timedelta(days=1)
  else:
    cutoff = as_of_date
  return {
    "historical_missing_dates": [value for value in normalized if value <= cutoff],
    "future_pending_dates": [value for value in normalized if value > cutoff],
  }


def get_trading_day_verification(
  year: int,
  actual_dates: Iterable[Any],
  current_date: Any | None = None,
) -> dict[str, Any]:
  calendar = get_market_calendar_for_year(year, current_date=current_date)
  expected_dates = set(calendar["trading_dates"])
  actual_date_set = {_coerce_date(value) for value in actual_dates}
  actual_trading_dates = sorted(expected_dates.intersection(actual_date_set))
  missing_dates = sorted(expected_dates.difference(actual_date_set))
  split_missing = split_missing_dates_by_current_date(missing_dates, calendar["as_of_date"])
  historical_missing_dates = split_missing["historical_missing_dates"]
  future_pending_dates = split_missing["future_pending_dates"]

  if not actual_trading_dates:
    verification_status = "MISSING"
  elif historical_missing_dates:
    verification_status = "PARTIAL"
  elif future_pending_dates:
    verification_status = "FUTURE_PENDING"
  else:
    verification_status = "COMPLETE"

  return {
    **calendar,
    "actual_dates": sorted(actual_date_set),
    "actual_trading_dates": actual_trading_dates,
    "invalid_non_trading_dates": sorted(actual_date_set.difference(expected_dates)),
    "missing_trading_dates": historical_missing_dates,
    "historical_missing_dates": historical_missing_dates,
    "future_pending_dates": future_pending_dates,
    "trading_days_available_in_table": len(actual_trading_dates),
    "trading_days_missing_count": len(historical_missing_dates),
    "historical_missing_count": len(historical_missing_dates),
    "future_pending_count": len(future_pending_dates),
    "verification_status": verification_status,
  }


def market_closed_reason(value: Any) -> str:
  target_date = _coerce_date(value)
  if is_special_market_working_day(target_date):
    return ""
  if is_weekend(target_date):
    return "Saturday/Sunday market weekend"
  if is_nse_holiday(target_date):
    return "NSE market holiday"
  return ""


def validate_market_date(value: Any, allow_override: bool = False) -> dt.date:
  target_date = _coerce_date(value)
  reason = market_closed_reason(target_date)
  if not reason:
    return target_date
  if allow_override:
    logger.warning(
      "NSE market date manual override accepted trade_date=%s reason=%s",
      target_date.isoformat(),
      reason,
    )
    return target_date
  raise ValueError(
    f"{target_date.isoformat()} is not an NSE market working day ({reason}). "
    "Enable Allow market holiday or weekend date only for an explicit manual override."
  )


def get_previous_market_working_day(value: Any) -> dt.date:
  current = _coerce_date(value)
  while not is_market_working_day(current):
    current -= dt.timedelta(days=1)
  return current


def filter_market_working_days(values: Iterable[Any]) -> list[dt.date]:
  return [_coerce_date(value) for value in values if is_market_working_day(value)]
