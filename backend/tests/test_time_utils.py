from datetime import datetime, timezone

from app.utils.time import normalize_tf, to_epoch_seconds


def test_normalize_tf():
    assert normalize_tf('1D') == '1D'
    assert normalize_tf('1w') == '1W'
    assert normalize_tf('bad') == '1D'


def test_to_epoch_seconds():
    dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert to_epoch_seconds(dt) == 1704067200
