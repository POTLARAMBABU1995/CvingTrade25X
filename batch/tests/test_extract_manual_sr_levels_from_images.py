import platform
from pathlib import Path

import pytest

from batch.jobs.extract_manual_sr_levels_from_images import cleanup_extracted_levels, detect_level_centers, extract_levels_from_image, parse_ocr_price

ROOT = Path(__file__).resolve().parents[2]
SAMPLE_IMAGE = ROOT / 'batch' / 'manual_sr_image_queue' / '01_inbox' / 'BAJAJELEC_2026-03-18_22-34-24.png'


def test_parse_ocr_price_repairs_separator_noise():
    assert parse_ocr_price('1*137.65') == 1137.65
    assert parse_ocr_price('1,244.30') == 1244.30
    assert parse_ocr_price('') is None


def test_detect_level_centers_on_tradingview_png():
    if not SAMPLE_IMAGE.exists():
        pytest.skip('BAJAJELEC sample PNG is not available in 01_inbox')
    centers = detect_level_centers(SAMPLE_IMAGE)

    assert len(centers) == 10
    assert centers[0] < centers[-1]


@pytest.mark.skipif(platform.system() != 'Windows', reason='Windows OCR is required for TradingView PNG extraction')
def test_extract_levels_from_current_png_sample():
    if not SAMPLE_IMAGE.exists():
        pytest.skip('BAJAJELEC sample PNG is not available in 01_inbox')
    levels = extract_levels_from_image(SAMPLE_IMAGE)

    assert levels[:4] == [1432.65, 1244.30, 1137.65, 930.25]
    assert 341.75 in levels


def test_process_payloads_inserts_payloads_incrementally(monkeypatch, tmp_path):
    payload_a = tmp_path / 'one.json'
    payload_b = tmp_path / 'two.json'
    payload_a.write_text('{}', encoding='utf-8')
    payload_b.write_text('{}', encoding='utf-8')

    from batch.jobs import extract_manual_sr_levels_from_images as image_module

    monkeypatch.setattr(
        image_module,
        'update_payload_file',
        lambda path, overwrite=False: {'payload_path': str(path), 'changed': True, 'updates': []},
    )
    monkeypatch.setattr(image_module, 'build_merge_rows', lambda records: list(records))
    monkeypatch.setattr(
        image_module,
        'load_payloads',
        lambda files=None, directory=None, pattern='*.json': [
            {'level_id': str(files[0]), 'symbol': Path(files[0]).stem.upper(), 'tf': '1D', 'level_type': 'MANUAL', 'sr_levels': 10.0}
        ],
    )
    monkeypatch.setattr(
        image_module,
        'split_rows_by_db_presence',
        lambda rows: (list(rows), []),
    )

    inserted_calls = []

    def fake_insert_rows(rows):
        inserted_calls.append(rows[0]['symbol'])
        return len(rows)

    monkeypatch.setattr(image_module, 'insert_rows', fake_insert_rows)
    monkeypatch.setattr(image_module, 'move_image', lambda image_name, status: tmp_path / image_name)
    monkeypatch.setattr(
        image_module,
        '_load_payload_document',
        lambda path: {'records': [{'source_image': f"{Path(path).stem}.png"}]},
    )
    monkeypatch.setattr(image_module, '_find_image_path', lambda image_name: tmp_path / image_name)
    monkeypatch.setattr(image_module, '_sync_ai_exports', lambda payload_dir: {'ai_rows_exported': 2})

    result = image_module.process_payloads(
        files=[str(payload_a), str(payload_b)],
        directory=None,
        pattern='*.json',
        overwrite=False,
        insert_db=True,
        only_missing=True,
        move_processed=False,
    )

    assert result['inserted_rows'] == 2
    assert inserted_calls == ['ONE', 'TWO']
    assert result['ai_export_result'] == {'ai_rows_exported': 2}



def test_process_payloads_retries_db_for_existing_levels(monkeypatch, tmp_path):
    payload_a = tmp_path / 'one.json'
    payload_a.write_text('{}', encoding='utf-8')

    from batch.jobs import extract_manual_sr_levels_from_images as image_module

    monkeypatch.setattr(
        image_module,
        'update_payload_file',
        lambda path, overwrite=False: {'payload_path': str(path), 'changed': False, 'updates': [{'status': 'skipped_existing', 'level_count': 2}]},
    )
    monkeypatch.setattr(image_module, 'build_merge_rows', lambda records: list(records))
    monkeypatch.setattr(
        image_module,
        'load_payloads',
        lambda files=None, directory=None, pattern='*.json': [
            {'level_id': str(files[0]), 'symbol': 'ONE', 'tf': '1D', 'level_type': 'MANUAL', 'sr_levels': 10.0}
        ],
    )
    monkeypatch.setattr(image_module, 'split_rows_by_db_presence', lambda rows: (list(rows), []))

    inserted_calls = []
    monkeypatch.setattr(image_module, 'insert_rows', lambda rows: inserted_calls.append(len(rows)) or len(rows))
    monkeypatch.setattr(image_module, '_sync_ai_exports', lambda payload_dir: {'ai_rows_exported': 1})

    result = image_module.process_payloads(
        files=[str(payload_a)],
        directory=None,
        pattern='*.json',
        overwrite=False,
        insert_db=True,
        only_missing=True,
        move_processed=False,
    )

    assert result['payloads_changed'] == 0
    assert result['inserted_rows'] == 1
    assert inserted_calls == [1]
    assert result['ai_export_result'] == {'ai_rows_exported': 1}

def test_cleanup_extracted_levels_rejects_common_ocr_outliers():
    assert cleanup_extracted_levels([1531.95, 1217.95, 1138.55, 1035.85, 936.05, 832.15, 830.35, 757.1, 611.75, 519.9, 438.15, 341.1, 104.3, 304.3, 256.8, 216.13, 169.91]) == [1531.95, 1217.95, 1138.55, 1035.85, 936.05, 832.15, 830.35, 757.1, 611.75, 519.9, 438.15, 341.1, 304.3, 256.8, 216.13, 169.91]
    assert cleanup_extracted_levels([7.31, 6571.9, 5971.4, 5461.95, 5149.45, 4694.55, 4231.5, 4.18, 3850.55, 2713.7, 2409.75, 2121.4, 1762.95, 1521.35, 1264.15, 735.0]) == [6571.9, 5971.4, 5461.95, 5149.45, 4694.55, 4231.5, 3850.55, 2713.7, 2409.75, 2121.4, 1762.95, 1521.35, 1264.15, 735.0]
    assert cleanup_extracted_levels([139.82, 122.42, 112.45, 99.29, 87.01, 70.89, 62.42, 49.87, 41.27, 3.65]) == [139.82, 122.42, 112.45, 99.29, 87.01, 70.89, 62.42, 49.87, 41.27]


def test_process_payloads_syncs_groups_when_requested(monkeypatch, tmp_path):
    payload_a = tmp_path / 'one.json'
    payload_a.write_text('{}', encoding='utf-8')

    from batch.jobs import extract_manual_sr_levels_from_images as image_module

    monkeypatch.setattr(
        image_module,
        'update_payload_file',
        lambda path, overwrite=False: {'payload_path': str(path), 'changed': False, 'updates': [{'status': 'skipped_existing', 'level_count': 2}]},
    )
    monkeypatch.setattr(image_module, '_collect_group_payload_paths', lambda payload_paths, pattern: [payload_a])
    monkeypatch.setattr(image_module, 'build_merge_rows', lambda records: list(records))
    monkeypatch.setattr(
        image_module,
        'load_payloads',
        lambda files=None, directory=None, pattern='*.json': [
            {'level_id': str(files[0]), 'symbol': 'ONE', 'tf': '1D', 'level_type': 'MANUAL', 'sr_levels': 10.0}
        ],
    )
    monkeypatch.setattr(
        image_module,
        'sync_rows_to_db',
        lambda rows: {'expected_rows': 1, 'present_rows': 0, 'missing_rows': 1, 'inserted_rows': 1, 'stale_rows': 1, 'deleted_rows': 1},
    )
    monkeypatch.setattr(image_module, '_sync_ai_exports', lambda payload_dir: {'ai_rows_exported': 1})

    result = image_module.process_payloads(
        files=[str(payload_a)],
        directory=None,
        pattern='*.json',
        overwrite=False,
        insert_db=True,
        only_missing=True,
        move_processed=False,
        sync_db_groups=True,
    )

    assert result['inserted_rows'] == 1
    assert result['sync_result']['deleted_rows'] == 1
    assert result['ai_export_result'] == {'ai_rows_exported': 1}

