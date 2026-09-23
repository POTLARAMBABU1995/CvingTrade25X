from pathlib import Path

from batch.jobs import manage_manual_sr_image_queue as queue_module


def test_summarize_payload_db_sync_marks_reinserted(monkeypatch):
    rows = [
        {
            'level_id': 'abc',
            'symbol': 'ABC',
            'tf': '1D',
            'level_type': 'MANUAL',
            'sr_levels': 10.0,
        }
    ]
    split_calls = {'count': 0}

    monkeypatch.setattr(queue_module, 'load_payloads', lambda files: [{'symbol': 'ABC', 'sr_levels': [10.0]}])
    monkeypatch.setattr(queue_module, 'build_merge_rows', lambda records: rows)

    def fake_split(candidate_rows):
        split_calls['count'] += 1
        if split_calls['count'] == 1:
            return (rows, [])
        return ([], rows)

    monkeypatch.setattr(queue_module, 'split_rows_by_db_presence', fake_split)
    monkeypatch.setattr(queue_module, 'insert_rows', lambda candidate_rows: len(candidate_rows))

    summary = queue_module._summarize_payload_db_sync([Path('payload.json')], retry_missing_db=True)

    assert summary['status'] == 'db_reinserted'
    assert summary['inserted_rows'] == 1
    assert summary['missing_rows'] == 0
    assert summary['present_rows'] == 1


def test_infer_metadata_from_timestamped_name():
    inferred = queue_module.infer_metadata_from_name(Path('DALBHARAT_2026-03-23_21-10-00.png'))

    assert inferred['symbol_guess'] == 'DALBHARAT'
    assert inferred['source_timeframe_guess'] is None
    assert inferred['as_of_date_guess'] == '2026-03-23'


def test_infer_metadata_from_double_underscore_name():
    inferred = queue_module.infer_metadata_from_name(Path('ADANIENT__1W__2026-03-14_a.png'))

    assert inferred['symbol_guess'] == 'ADANIENT'
    assert inferred['source_timeframe_guess'] == '1W'
    assert inferred['as_of_date_guess'] == '2026-03-14'