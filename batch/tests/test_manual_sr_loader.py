import os

from batch.jobs import load_manual_sr_levels as loader_module
from batch.jobs.load_manual_sr_levels import (
    build_merge_rows,
    collect_payload_files,
    load_payloads,
    prime_db_env_from_oracle_env,
    split_rows_by_db_presence,
    sync_rows_to_db,
)


def test_build_merge_rows_for_flat_sr_levels():
    records = [
        {
            'symbol': 'NSE:ADANIPOWER-EQ',
            'tf': '1d',
            'as_of_date': '2026-03-13',
            'source': 'manual_image',
            'accuracy_estimate': 0.95,
            'sr_levels': [180.01, 113.34],
        }
    ]

    rows = build_merge_rows(records)

    assert len(rows) == 2
    assert rows[0]['symbol'] == 'ADANIPOWER'
    assert rows[0]['tf'] == '1D'
    assert rows[0]['level_type'] == 'MANUAL'
    assert rows[0]['sr_levels'] == 180.01
    assert set(rows[0].keys()) == {'level_id', 'symbol', 'tf', 'level_type', 'sr_levels'}


def test_build_merge_rows_dedupes_same_stock_level_across_images():
    records = [
        {
            'symbol': 'ADANIENT',
            'tf': '1D',
            'as_of_date': '2026-03-14',
            'source_image': 'ADANIENT__1W__2026-03-14_a.png',
            'sr_levels': [398.10, 317.30, 254.05],
        },
        {
            'symbol': 'ADANIENT',
            'tf': '1D',
            'as_of_date': '2026-03-14',
            'source_image': 'ADANIENT__1W__2026-03-14_b.png',
            'sr_levels': [398.10, 213.47, 176.48],
        },
    ]

    rows = build_merge_rows(records)

    assert len(rows) == 5
    assert sorted(row['sr_levels'] for row in rows) == [176.48, 213.47, 254.05, 317.30, 398.10]


def test_collect_payload_files_and_load_payloads_from_dir(tmp_path):
    payload_a = tmp_path / 'one.json'
    payload_b = tmp_path / 'two.json'
    payload_a.write_text('{"records": [{"symbol": "ABC", "sr_levels": [10]}]}', encoding='utf-8')
    payload_b.write_text('{"records": [{"symbol": "ABC", "sr_levels": [20]}]}', encoding='utf-8')

    paths = collect_payload_files(directory=str(tmp_path))
    records = load_payloads(directory=str(tmp_path))

    assert len(paths) == 2
    assert len(records) == 2
    assert records[0]['symbol'] == 'ABC'


def test_build_merge_rows_skips_empty_queue_skeletons():
    rows = build_merge_rows([
        {'symbol': 'ABC', 'tf': '1D', 'level_type': 'MANUAL', 'sr_levels': []},
        {'symbol': 'ABC', 'tf': '1D', 'level_type': 'MANUAL', 'sr_levels': [10.0, 20.0]},
    ])

    assert [row['sr_levels'] for row in rows] == [10.0, 20.0]


def test_prime_db_env_from_oracle_env(monkeypatch):
    monkeypatch.delenv('DB_USER', raising=False)
    monkeypatch.delenv('DB_PASSWORD', raising=False)
    monkeypatch.delenv('DB_DSN', raising=False)
    monkeypatch.setenv('ORACLE_USER', 'market_user')
    monkeypatch.setenv('ORACLE_PASSWORD', 'secret')
    monkeypatch.setenv('ORACLE_HOST', '127.0.0.1')
    monkeypatch.setenv('ORACLE_PORT', '1521')
    monkeypatch.setenv('ORACLE_SERVICE_NAME', 'cvingpdb.local')

    prime_db_env_from_oracle_env()

    assert os.environ['DB_USER'] == 'market_user'
    assert os.environ['DB_PASSWORD'] == 'secret'
    assert os.environ['DB_DSN'] == '127.0.0.1:1521/cvingpdb.local'


def test_split_rows_by_db_presence(monkeypatch):
    rows = build_merge_rows([
        {'symbol': 'ABC', 'tf': '1D', 'level_type': 'MANUAL', 'sr_levels': [10.0, 20.0]},
    ])

    monkeypatch.setattr(
        loader_module,
        'fetch_existing_natural_keys',
        lambda candidate_rows: {('ABC', '1D', 'MANUAL', 10.0)},
    )

    missing_rows, present_rows = split_rows_by_db_presence(rows)

    assert [row['sr_levels'] for row in present_rows] == [10.0]
    assert [row['sr_levels'] for row in missing_rows] == [20.0]


def test_build_merge_rows_strips_screenshot_timestamp_suffix():
    rows = build_merge_rows([
        {
            'symbol': 'CANFINHOME_2026-03-21_17-36-02',
            'tf': '1D',
            'level_type': 'MANUAL',
            'sr_levels': [812.4],
        }
    ])

    assert rows[0]['symbol'] == 'CANFINHOME'

def test_insert_rows_splits_tablespace_full_batches(monkeypatch):
    rows = build_merge_rows([
        {'symbol': 'ABC', 'tf': '1D', 'level_type': 'MANUAL', 'sr_levels': [10.0, 20.0, 30.0, 40.0]},
    ])
    calls = []

    monkeypatch.setattr(loader_module, 'prime_db_env_from_oracle_env', lambda: None)
    monkeypatch.setattr(loader_module, 'build_manual_sr_levels_merge_sql', lambda: 'MERGE SQL')

    from batch.common import db as db_module

    def fake_execute_many(sql, params):
        calls.append(len(params))
        if len(params) > 2:
            raise RuntimeError('ORA-01653: unable to extend table')
        return len(params)

    monkeypatch.setattr(db_module, 'execute_many', fake_execute_many)

    inserted = loader_module.insert_rows(rows)

    assert inserted == 4
    assert calls == [4, 2, 2]


def test_insert_rows_skips_single_row_when_tablespace_is_full(monkeypatch):
    rows = build_merge_rows([
        {'symbol': 'ABC', 'tf': '1D', 'level_type': 'MANUAL', 'sr_levels': [10.0]},
    ])

    monkeypatch.setattr(loader_module, 'prime_db_env_from_oracle_env', lambda: None)
    monkeypatch.setattr(loader_module, 'build_manual_sr_levels_merge_sql', lambda: 'MERGE SQL')

    from batch.common import db as db_module

    monkeypatch.setattr(
        db_module,
        'execute_many',
        lambda sql, params: (_ for _ in ()).throw(RuntimeError('ORA-01653: unable to extend table')),
    )

    assert loader_module.insert_rows(rows) == 0

def test_sync_rows_to_db_reconciles_stale_and_missing(monkeypatch):
    rows = build_merge_rows([
        {'symbol': 'ABC', 'tf': '1D', 'level_type': 'MANUAL', 'sr_levels': [10.0, 20.0]},
    ])

    monkeypatch.setattr(
        loader_module,
        'fetch_all_natural_keys',
        lambda candidate_rows: {('ABC', '1D', 'MANUAL', 10.0), ('ABC', '1D', 'MANUAL', 30.0)},
    )

    deleted_rows = []
    inserted_rows = []
    monkeypatch.setattr(loader_module, 'delete_rows', lambda rows: deleted_rows.extend(row['sr_levels'] for row in rows) or len(rows))
    monkeypatch.setattr(loader_module, 'insert_rows', lambda rows: inserted_rows.extend(row['sr_levels'] for row in rows) or len(rows))

    result = sync_rows_to_db(rows)

    assert deleted_rows == [30.0]
    assert inserted_rows == [20.0]
    assert result == {
        'expected_rows': 2,
        'present_rows': 1,
        'missing_rows': 1,
        'inserted_rows': 1,
        'stale_rows': 1,
        'deleted_rows': 1,
    }

