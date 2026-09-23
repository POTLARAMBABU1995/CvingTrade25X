from datetime import date, datetime, time, timezone
from typing import Optional


TF_TABLES = {
    '1D': 'OHLCV_D',
    '1W': 'OHLCV_W',
    '1M': 'OHLCV_M',
    '1Y': 'OHLCV_Y',
}

IND_TABLES = {
    '1D': 'INDICATORS_D',
    '1W': 'INDICATORS_W',
    '1M': 'INDICATORS_M',
    '1Y': 'INDICATORS_Y',
}

HISTORY_RANGE_YEARS = {
    '2Y': 2,
    '3Y': 3,
    '5Y': 5,
    'MAX': None,
}


def normalize_tf(value: str) -> str:
    if not value:
        return '1D'
    cleaned = value.strip().upper()
    return cleaned if cleaned in TF_TABLES else '1D'


def parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    return datetime.strptime(value, '%Y-%m-%d').date()


def normalize_history_range(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    token = value.strip().upper()
    return token if token in HISTORY_RANGE_YEARS else None


def _shift_years(base_date: date, years: int) -> date:
    if years <= 0:
        return base_date
    target_year = base_date.year - years
    month = base_date.month
    day = base_date.day
    while True:
        try:
            return date(target_year, month, day)
        except ValueError:
            day -= 1
            if day <= 0:
                return date(target_year, month, 1)


def resolve_history_window(from_value: Optional[str], to_value: Optional[str], range_value: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    if from_value or to_value:
        return from_value, to_value
    token = normalize_history_range(range_value)
    if not token or token == 'MAX':
        return from_value, to_value
    years = HISTORY_RANGE_YEARS[token]
    if years is None:
        return from_value, to_value
    end_date = date.today()
    start_date = _shift_years(end_date, years)
    return start_date.isoformat(), end_date.isoformat()


def to_epoch_seconds(value: Optional[datetime]) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        value = datetime.combine(value, time.min)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp())


def to_date_start(value: date) -> datetime:
    return datetime.combine(value, time.min)
