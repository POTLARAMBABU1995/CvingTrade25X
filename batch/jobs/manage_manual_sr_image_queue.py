from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set

from batch.jobs.load_manual_sr_levels import (
    build_merge_rows,
    insert_rows,
    load_payloads,
    split_rows_by_db_presence,
)

ROOT = Path(__file__).resolve().parents[1] / 'manual_sr_image_queue'
INBOX_DIR = ROOT / '01_inbox'
PROCESSED_DIR = ROOT / '02_processed'
REJECTED_DIR = ROOT / '03_rejected'
PAYLOADS_DIR = ROOT / '04_payloads'
MANIFESTS_DIR = ROOT / '05_manifests'
TRAINING_DIR = ROOT / '06_training_corpus'
RAG_DIR = ROOT / '07_rag_exports'
KNOWN_DIR = ROOT / '08_already_processed'
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}
TARGET_TF = '1D'
DOUBLE_UNDERSCORE_NAME_RE = re.compile(
    r'^(?P<symbol>[A-Za-z0-9&-]+)__(?P<source_tf>[^_]+)__(?P<as_of_date>\d{4}-\d{2}-\d{2})(?:[_-].+)?$'
)
TIMESTAMPED_NAME_RE = re.compile(
    r'^(?P<symbol>[A-Za-z0-9&-]+)_(?P<as_of_date>\d{4}-\d{2}-\d{2})(?:_(?P<time>\d{2}-\d{2}-\d{2}))?$'
)


@dataclass(frozen=True)
class QueuePaths:
    root: Path = ROOT
    inbox: Path = INBOX_DIR
    processed: Path = PROCESSED_DIR
    rejected: Path = REJECTED_DIR
    payloads: Path = PAYLOADS_DIR
    manifests: Path = MANIFESTS_DIR
    training: Path = TRAINING_DIR
    rag: Path = RAG_DIR
    known: Path = KNOWN_DIR


def ensure_queue_dirs() -> QueuePaths:
    paths = QueuePaths()
    for path in (
        paths.root,
        paths.inbox,
        paths.processed,
        paths.rejected,
        paths.payloads,
        paths.manifests,
        paths.training,
        paths.rag,
        paths.known,
    ):
        path.mkdir(parents=True, exist_ok=True)
    return paths


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def _safe_stem(value: str) -> str:
    return ''.join(ch if ch.isalnum() or ch in {'-', '_'} else '_' for ch in value).strip('_') or 'image'


def _listify(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _iter_payload_records(payload_dir: Path) -> Iterable[tuple[Path, Dict[str, Any]]]:
    for path in sorted(payload_dir.glob('*.json')):
        try:
            payload = json.loads(path.read_text(encoding='utf-8-sig'))
        except Exception:
            continue
        records = payload.get('records') if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            continue
        for record in records:
            if isinstance(record, dict):
                yield path, record


def _build_payload_index(payload_dir: Path) -> Dict[str, List[Path]]:
    index: Dict[str, List[Path]] = {}
    for path, record in _iter_payload_records(payload_dir):
        seen_for_record: Set[str] = set()
        for key in ('source_image', 'source_images'):
            for image_name in _listify(record.get(key)):
                if image_name in seen_for_record:
                    continue
                index.setdefault(image_name, []).append(path)
                seen_for_record.add(image_name)
    return {key: sorted(set(value)) for key, value in index.items()}


def _move_to_folder(source: Path, destination_dir: Path) -> Path:
    destination = destination_dir / source.name
    if destination.exists():
        stem = source.stem
        suffix = source.suffix
        index = 1
        while True:
            candidate = destination_dir / f'{stem}__dup{index}{suffix}'
            if not candidate.exists():
                destination = candidate
                break
            index += 1
    shutil.move(str(source), str(destination))
    return destination


def infer_metadata_from_name(path: Path) -> Dict[str, Any]:
    stem = path.stem
    symbol = stem.strip().upper()
    source_tf = None
    as_of_date = datetime.now().strftime('%Y-%m-%d')

    double_underscore_match = DOUBLE_UNDERSCORE_NAME_RE.match(stem)
    if double_underscore_match:
        symbol = double_underscore_match.group('symbol').strip().upper()
        source_tf = double_underscore_match.group('source_tf').strip().upper()
        as_of_date = double_underscore_match.group('as_of_date')
    else:
        timestamped_match = TIMESTAMPED_NAME_RE.match(stem)
        if timestamped_match:
            symbol = timestamped_match.group('symbol').strip().upper()
            as_of_date = timestamped_match.group('as_of_date')

    payload_name = f"{_safe_stem(stem)}.json"
    return {
        'image_name': path.name,
        'symbol_guess': symbol,
        'source_timeframe_guess': source_tf,
        'as_of_date_guess': as_of_date,
        'target_tf': TARGET_TF,
        'suggested_payload_file': payload_name,
    }


def build_payload_skeleton(image_path: Path, inferred: Dict[str, Any]) -> Dict[str, Any]:
    record = {
        'symbol': inferred['symbol_guess'],
        'tf': TARGET_TF,
        'as_of_date': inferred['as_of_date_guess'],
        'source': 'manual_image',
        'level_type': 'MANUAL',
        'exchange': 'NSE',
        'chart_provider': 'TradingView',
        'accuracy_estimate': None,
        'notes': 'Fill sr_levels manually after reading the TradingView image.',
        'source_timeframe': inferred['source_timeframe_guess'],
        'source_image': image_path.name,
        'sr_levels': [],
        'analysis': {
            'cmp': None,
            'trend_direction': None,
            'market_phase': None,
            'price_action_state': [],
            'chart_patterns': [],
            'pattern_bias': None,
            'entry_bias': None,
            'confidence': None,
            'narrative': '',
            'review_notes': '',
        },
        'agent_training': {
            'task_type': 'manual_sr_from_image',
            'supervision_status': 'annotated',
            'reviewer': None,
            'quality_score': None,
            'use_for_rag': True,
            'use_for_training': True,
        },
    }
    return {
        'dataset_version': 'manual-sr-image-v2',
        'taxonomy_version': 'manual-sr-annotation-v1',
        'created_at': _now_iso(),
        'records': [record],
    }


def _summarize_payload_db_sync(payload_paths: List[Path], retry_missing_db: bool = False) -> Dict[str, Any]:
    try:
        records = load_payloads(files=[str(path) for path in payload_paths])
        rows = build_merge_rows(records)
        missing_rows, present_rows = split_rows_by_db_presence(rows)
        inserted_count = 0
        if retry_missing_db and missing_rows:
            inserted_count = insert_rows(missing_rows)
            missing_rows, present_rows = split_rows_by_db_presence(rows)
        status = 'db_synced'
        if missing_rows:
            status = 'db_missing'
        elif inserted_count:
            status = 'db_reinserted'
        return {
            'payload_files': [str(path) for path in payload_paths],
            'payload_count': len(payload_paths),
            'expected_rows': len(rows),
            'present_rows': len(present_rows),
            'missing_rows': len(missing_rows),
            'inserted_rows': inserted_count,
            'status': status,
        }
    except Exception as exc:
        return {
            'payload_files': [str(path) for path in payload_paths],
            'payload_count': len(payload_paths),
            'expected_rows': 0,
            'present_rows': 0,
            'missing_rows': 0,
            'inserted_rows': 0,
            'status': 'db_error',
            'error': str(exc),
        }


def audit_processed_payloads(retry_missing_db: bool = False) -> Dict[str, Any]:
    paths = ensure_queue_dirs()
    payload_index = _build_payload_index(paths.payloads)
    audit_rows: List[Dict[str, Any]] = []

    for image_path in sorted(paths.known.iterdir()):
        if not _is_image(image_path):
            continue
        payload_paths = payload_index.get(image_path.name, [])
        if not payload_paths:
            audit_rows.append({
                'image_name': image_path.name,
                'image_path': str(image_path),
                'status': 'payload_missing',
                'payload_count': 0,
                'expected_rows': 0,
                'present_rows': 0,
                'missing_rows': 0,
                'inserted_rows': 0,
                'payload_files': [],
            })
            continue
        sync_summary = _summarize_payload_db_sync(payload_paths, retry_missing_db=retry_missing_db)
        audit_rows.append({
            'image_name': image_path.name,
            'image_path': str(image_path),
            **sync_summary,
        })

    db_missing_rows = [row for row in audit_rows if row['status'] == 'db_missing']
    db_reinserted_rows = [row for row in audit_rows if row['status'] == 'db_reinserted']
    payload_missing_rows = [row for row in audit_rows if row['status'] == 'payload_missing']
    db_error_rows = [row for row in audit_rows if row['status'] == 'db_error']

    return {
        'generated_at': _now_iso(),
        'known_dir': str(paths.known),
        'images_audited': len(audit_rows),
        'db_missing_count': len(db_missing_rows),
        'db_reinserted_count': len(db_reinserted_rows),
        'payload_missing_count': len(payload_missing_rows),
        'db_error_count': len(db_error_rows),
        'db_missing_images': db_missing_rows,
        'db_reinserted_images': db_reinserted_rows,
        'payload_missing_images': payload_missing_rows,
        'db_error_images': db_error_rows,
    }


def scan_inbox(create_skeletons: bool = True, move_known: bool = False) -> Dict[str, Any]:
    paths = ensure_queue_dirs()
    payload_index = _build_payload_index(paths.payloads)
    manifest_rows: List[Dict[str, Any]] = []
    pending_count = 0
    known_count = 0

    for image_path in sorted(paths.inbox.iterdir()):
        if not _is_image(image_path):
            continue

        inferred = infer_metadata_from_name(image_path)
        payload_path = paths.payloads / inferred['suggested_payload_file']
        status = 'pending'
        moved_to = None
        active_image_path = image_path

        if image_path.name in payload_index:
            status = 'already_processed'
            known_count += 1
            if move_known:
                active_image_path = _move_to_folder(image_path, paths.known)
                moved_to = str(active_image_path)
        else:
            pending_count += 1
            if create_skeletons and not payload_path.exists():
                skeleton = build_payload_skeleton(image_path, inferred)
                payload_path.write_text(json.dumps(skeleton, indent=2), encoding='utf-8')

        manifest_rows.append({
            'image_name': image_path.name,
            'image_path': str(active_image_path if moved_to else image_path),
            'symbol_guess': inferred['symbol_guess'],
            'source_timeframe_guess': inferred['source_timeframe_guess'],
            'as_of_date_guess': inferred['as_of_date_guess'],
            'target_tf': TARGET_TF,
            'payload_path': str(payload_path),
            'status': status,
            'moved_to': moved_to,
        })

    manifest = {
        'generated_at': _now_iso(),
        'root': str(paths.root),
        'pending_count': pending_count,
        'already_processed_count': known_count,
        'pending_images': [row for row in manifest_rows if row['status'] == 'pending'],
        'already_processed_images': [row for row in manifest_rows if row['status'] == 'already_processed'],
    }
    manifest_path = paths.manifests / 'queue_index.json'
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


def move_image(image_name: str, target_status: str) -> Path:
    paths = ensure_queue_dirs()
    source = paths.inbox / image_name
    if not source.exists():
        raise FileNotFoundError(f'Image not found in inbox: {source}')

    if target_status == 'processed':
        destination_dir = paths.processed
    elif target_status == 'rejected':
        destination_dir = paths.rejected
    elif target_status == 'already_processed':
        destination_dir = paths.known
    else:
        raise ValueError("target_status must be 'processed', 'rejected', or 'already_processed'")

    return _move_to_folder(source, destination_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description='Manage the manual SR TradingView image queue')
    parser.add_argument('--scan', action='store_true', help='Scan inbox and generate queue_index.json plus payload skeletons')
    parser.add_argument('--move-known', action='store_true', help='Move inbox images that already exist in payloads into 08_already_processed')
    parser.add_argument('--no-skeletons', action='store_true', help='Do not create payload skeleton JSON files during scan')
    parser.add_argument('--verify-db', action='store_true', help='Audit 08_already_processed images against Oracle SR inserts')
    parser.add_argument('--retry-missing-db', action='store_true', help='Reinsert missing SR rows for 08_already_processed payloads without creating duplicates')
    parser.add_argument('--move', help='Image filename to move out of inbox')
    parser.add_argument('--status', choices=['processed', 'rejected', 'already_processed'], help='Target status when using --move')
    args = parser.parse_args()

    ensure_queue_dirs()

    if args.move:
        if not args.status:
            raise SystemExit('--status is required when using --move')
        destination = move_image(args.move, args.status)
        print(json.dumps({'moved_to': str(destination), 'status': args.status}, indent=2))
        return

    result: Dict[str, Any] = {}
    if args.scan or (not args.verify_db and not args.retry_missing_db):
        result['queue_manifest'] = scan_inbox(create_skeletons=not args.no_skeletons, move_known=args.move_known)
    if args.verify_db or args.retry_missing_db:
        result['known_db_audit'] = audit_processed_payloads(retry_missing_db=args.retry_missing_db)
    if not result:
        result['queue_manifest'] = scan_inbox(create_skeletons=not args.no_skeletons, move_known=args.move_known)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()


