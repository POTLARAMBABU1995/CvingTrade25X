from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from backend.automation import manual_sr_image_auto_ingest as auto_ingest


def _queue_paths(root: Path) -> SimpleNamespace:
    paths = SimpleNamespace(
        root=root,
        inbox=root / '01_inbox',
        processed=root / '02_processed',
        rejected=root / '03_rejected',
        payloads=root / '04_payloads',
        manifests=root / '05_manifests',
        training=root / '06_training_corpus',
        rag=root / '07_rag_exports',
        known=root / '08_already_processed',
    )
    for path in vars(paths).values():
        if isinstance(path, Path):
            path.mkdir(parents=True, exist_ok=True)
    return paths


def test_run_once_is_idle_when_inbox_has_no_images(tmp_path, monkeypatch):
    paths = _queue_paths(tmp_path / 'queue')
    monkeypatch.setattr(auto_ingest, 'ensure_queue_dirs', lambda: paths)
    monkeypatch.setattr(auto_ingest, 'scan_inbox', lambda **_kwargs: (_ for _ in ()).throw(AssertionError('scan should not run')))
    monkeypatch.setattr(auto_ingest, 'process_payloads', lambda **_kwargs: (_ for _ in ()).throw(AssertionError('process should not run')))

    result = auto_ingest.run_manual_sr_image_auto_ingest_once(reason='test')

    assert result['status'] == 'idle'
    assert result['inbox_image_count'] == 0


def test_run_once_processes_pending_inbox_images(tmp_path, monkeypatch):
    paths = _queue_paths(tmp_path / 'queue')
    image_path = paths.inbox / 'ABC__1D__2026-06-01.png'
    image_path.write_bytes(b'fake-image')
    payload_path = paths.payloads / 'ABC__1D__2026-06-01.json'
    calls = {'scan_kwargs': []}
    scan_results = [
        {
            'pending_images': [{'payload_path': str(payload_path)}],
            'pending_count': 1,
            'already_processed_count': 0,
        },
        {
            'pending_images': [],
            'pending_count': 0,
            'already_processed_count': 0,
        },
    ]

    monkeypatch.setattr(auto_ingest, 'ensure_queue_dirs', lambda: paths)

    def fake_scan_inbox(**kwargs):
        calls['scan_kwargs'].append(kwargs)
        return scan_results.pop(0)

    monkeypatch.setattr(auto_ingest, 'scan_inbox', fake_scan_inbox)

    def fake_process_payloads(**kwargs):
        calls['kwargs'] = kwargs
        return {
            'payloads_scanned': 1,
            'payloads_changed': 1,
            'payload_results': [{'changed': True, 'updates': [{'source_image': image_path.name, 'status': 'updated'}]}],
            'inserted_rows': 3,
            'moved_images': [str(paths.processed / image_path.name)],
        }

    monkeypatch.setattr(auto_ingest, 'process_payloads', fake_process_payloads)

    result = auto_ingest.run_manual_sr_image_auto_ingest_once(reason='test')

    assert result['status'] == 'processed'
    assert result['pending_payload_count'] == 1
    assert result['post_process_queue_manifest']['pending_count'] == 0
    assert calls['scan_kwargs'] == [
        {'create_skeletons': True, 'move_known': True},
        {'create_skeletons': True, 'move_known': True},
    ]
    assert calls['kwargs']['files'] == [str(payload_path)]
    assert calls['kwargs']['insert_db'] is True
    assert calls['kwargs']['only_missing'] is True
    assert calls['kwargs']['move_processed'] is True


def test_run_once_moves_ocr_failed_images_to_rejected(tmp_path, monkeypatch):
    paths = _queue_paths(tmp_path / 'queue')
    image_path = paths.inbox / 'ABC__1D__2026-06-01.png'
    image_path.write_bytes(b'fake-image')
    payload_path = paths.payloads / 'ABC__1D__2026-06-01.json'
    moved = []

    monkeypatch.setattr(auto_ingest, 'ensure_queue_dirs', lambda: paths)
    monkeypatch.setattr(
        auto_ingest,
        'scan_inbox',
        lambda **_kwargs: {
            'pending_images': [{'payload_path': str(payload_path)}],
            'pending_count': 1,
            'already_processed_count': 0,
        },
    )
    monkeypatch.setattr(
        auto_ingest,
        'process_payloads',
        lambda **_kwargs: {
            'payloads_scanned': 1,
            'payloads_changed': 0,
            'payload_results': [{'changed': False, 'updates': [{'source_image': image_path.name, 'status': 'ocr_failed'}]}],
            'inserted_rows': 0,
            'moved_images': [],
        },
    )

    def fake_move_image(image_name: str, target_status: str):
        moved.append((image_name, target_status))
        return paths.rejected / image_name

    monkeypatch.setattr(auto_ingest, 'move_image', fake_move_image)

    result = auto_ingest.run_manual_sr_image_auto_ingest_once(reason='test')

    assert result['status'] == 'processed'
    assert moved == [(image_path.name, 'rejected')]
    assert result['rejected_images'] == [str(paths.rejected / image_path.name)]
