from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
for _path in (PROJECT_ROOT, BACKEND_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}
FAILED_IMAGE_STATUSES = {'ocr_failed', 'unsupported_image_type'}
DEFAULT_STARTUP_DELAY_SECONDS = 15
DEFAULT_INTERVAL_SECONDS = 60

_LOGGER = logging.getLogger(__name__)
_RUN_LOCK = threading.Lock()
_SCHEDULER_LOCK = threading.Lock()
_AUTO_SCHEDULER_STARTED = False


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    try:
        value = int(str(os.getenv(name, str(default))).strip())
    except Exception:
        value = int(default)
    return max(int(minimum), value)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_queue_dirs():
    from batch.jobs.manage_manual_sr_image_queue import ensure_queue_dirs as _ensure_queue_dirs

    return _ensure_queue_dirs()


def scan_inbox(*, create_skeletons: bool = True, move_known: bool = True) -> Dict[str, Any]:
    from batch.jobs.manage_manual_sr_image_queue import scan_inbox as _scan_inbox

    return _scan_inbox(create_skeletons=create_skeletons, move_known=move_known)


def process_payloads(
    *,
    files: Sequence[str] | None,
    directory: str | None,
    pattern: str,
    overwrite: bool,
    insert_db: bool,
    only_missing: bool,
    move_processed: bool,
    sync_db_groups: bool,
) -> Dict[str, Any]:
    from batch.jobs.extract_manual_sr_levels_from_images import process_payloads as _process_payloads

    return _process_payloads(
        files=files,
        directory=directory,
        pattern=pattern,
        overwrite=overwrite,
        insert_db=insert_db,
        only_missing=only_missing,
        move_processed=move_processed,
        sync_db_groups=sync_db_groups,
    )


def move_image(image_name: str, target_status: str) -> Path:
    from batch.jobs.manage_manual_sr_image_queue import move_image as _move_image

    return _move_image(image_name, target_status)


def _is_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def _inbox_images(paths: Any) -> List[Path]:
    inbox = Path(paths.inbox)
    if not inbox.exists():
        return []
    return [path for path in sorted(inbox.iterdir()) if _is_image(path)]


def _pending_payload_paths(manifest: Dict[str, Any]) -> List[Path]:
    pending_rows = manifest.get('pending_images') if isinstance(manifest, dict) else []
    payload_paths: List[Path] = []
    seen: set[str] = set()
    if not isinstance(pending_rows, list):
        return payload_paths

    for row in pending_rows:
        if not isinstance(row, dict):
            continue
        payload_path = str(row.get('payload_path') or '').strip()
        if not payload_path:
            continue
        resolved = str(Path(payload_path).resolve(strict=False))
        if resolved in seen:
            continue
        payload_paths.append(Path(payload_path))
        seen.add(resolved)
    return payload_paths


def _move_failed_images(payload_results: Sequence[Dict[str, Any]]) -> List[str]:
    moved: List[str] = []
    seen: set[str] = set()
    for result in payload_results:
        updates = result.get('updates') if isinstance(result, dict) else []
        if not isinstance(updates, list):
            continue
        for update in updates:
            if not isinstance(update, dict):
                continue
            if str(update.get('status') or '') not in FAILED_IMAGE_STATUSES:
                continue
            image_name = str(update.get('source_image') or '').strip()
            if not image_name or image_name in seen:
                continue
            seen.add(image_name)
            try:
                destination = move_image(image_name, 'rejected')
            except FileNotFoundError:
                continue
            except Exception:
                _LOGGER.exception('Manual SR image auto-ingest failed moving rejected image: %s', image_name)
                continue
            moved.append(str(destination))
    return moved


def run_manual_sr_image_auto_ingest_once(reason: str = 'scheduler') -> Dict[str, Any]:
    if not _env_flag('MANUAL_SR_IMAGE_AUTO_INGEST_ENABLED', True):
        return {
            'status': 'disabled',
            'generated_at': _now_iso(),
            'reason': reason,
        }

    if not _RUN_LOCK.acquire(blocking=False):
        return {
            'status': 'busy',
            'generated_at': _now_iso(),
            'reason': reason,
        }

    started_at = time.perf_counter()
    try:
        paths = ensure_queue_dirs()
        inbox_images = _inbox_images(paths)
        if not inbox_images:
            return {
                'status': 'idle',
                'generated_at': _now_iso(),
                'reason': reason,
                'inbox_image_count': 0,
                'message': 'No manual SR inbox images found.',
            }

        manifest = scan_inbox(create_skeletons=True, move_known=True)
        pending_payloads = _pending_payload_paths(manifest)
        if not pending_payloads:
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            result = {
                'status': 'scanned',
                'generated_at': _now_iso(),
                'reason': reason,
                'inbox_image_count': len(inbox_images),
                'pending_payload_count': 0,
                'queue_manifest': manifest,
                'duration_ms': duration_ms,
            }
            _LOGGER.info(
                'Manual SR image auto-ingest scanned reason=%s inbox_images=%s pending_payloads=0 duration_ms=%s',
                reason,
                len(inbox_images),
                duration_ms,
            )
            return result

        process_result = process_payloads(
            files=[str(path) for path in pending_payloads],
            directory=None,
            pattern='*.json',
            overwrite=False,
            insert_db=True,
            only_missing=True,
            move_processed=True,
            sync_db_groups=False,
        )
        rejected_images = _move_failed_images(process_result.get('payload_results') or [])
        post_process_manifest: Dict[str, Any] | None = None
        post_process_manifest_error = None
        try:
            post_process_manifest = scan_inbox(create_skeletons=True, move_known=True)
        except Exception as exc:
            post_process_manifest_error = str(exc)
            _LOGGER.exception('Manual SR image auto-ingest failed refreshing post-process queue manifest')
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        result = {
            'status': 'processed',
            'generated_at': _now_iso(),
            'reason': reason,
            'inbox_image_count': len(inbox_images),
            'pending_payload_count': len(pending_payloads),
            'queue_manifest': manifest,
            'post_process_queue_manifest': post_process_manifest,
            'post_process_queue_manifest_error': post_process_manifest_error,
            'process_result': process_result,
            'rejected_images': rejected_images,
            'duration_ms': duration_ms,
        }
        _LOGGER.info(
            'Manual SR image auto-ingest processed reason=%s inbox_images=%s payloads=%s inserted_rows=%s moved_images=%s rejected_images=%s duration_ms=%s',
            reason,
            len(inbox_images),
            len(pending_payloads),
            process_result.get('inserted_rows'),
            len(process_result.get('moved_images') or []),
            len(rejected_images),
            duration_ms,
        )
        return result
    except Exception as exc:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        _LOGGER.exception('Manual SR image auto-ingest failed reason=%s duration_ms=%s', reason, duration_ms)
        return {
            'status': 'failed',
            'generated_at': _now_iso(),
            'reason': reason,
            'error': str(exc),
            'duration_ms': duration_ms,
        }
    finally:
        _RUN_LOCK.release()


def start_manual_sr_image_auto_ingest_scheduler(
    *,
    initial_delay_seconds: int | None = None,
    interval_seconds: int | None = None,
) -> None:
    global _AUTO_SCHEDULER_STARTED
    if not _env_flag('MANUAL_SR_IMAGE_AUTO_INGEST_ENABLED', True):
        return

    with _SCHEDULER_LOCK:
        if _AUTO_SCHEDULER_STARTED:
            return
        _AUTO_SCHEDULER_STARTED = True

    startup_delay = (
        max(0, int(initial_delay_seconds))
        if initial_delay_seconds is not None
        else _env_int('MANUAL_SR_IMAGE_AUTO_INGEST_STARTUP_DELAY_SEC', DEFAULT_STARTUP_DELAY_SECONDS, minimum=0)
    )
    interval = (
        max(5, int(interval_seconds))
        if interval_seconds is not None
        else _env_int('MANUAL_SR_IMAGE_AUTO_INGEST_INTERVAL_SEC', DEFAULT_INTERVAL_SECONDS, minimum=5)
    )
    _LOGGER.info(
        'Manual SR image auto-ingest scheduler starting enabled=true startup_delay_sec=%s interval_sec=%s',
        startup_delay,
        interval,
    )

    def _loop() -> None:
        if startup_delay:
            time.sleep(startup_delay)
        run_manual_sr_image_auto_ingest_once(reason='startup')
        while True:
            time.sleep(interval)
            run_manual_sr_image_auto_ingest_once(reason='schedule')

    threading.Thread(target=_loop, name='manual-sr-image-auto-ingest', daemon=True).start()


def main() -> int:
    parser = argparse.ArgumentParser(description='Unattended manual SR image inbox ingestion')
    parser.add_argument('--once', action='store_true', help='Run one unattended inbox ingestion cycle and exit')
    parser.add_argument('--watch', action='store_true', help='Continuously poll 01_inbox and process new images')
    parser.add_argument('--interval-seconds', type=int, default=DEFAULT_INTERVAL_SECONDS, help='Polling interval for --watch')
    args = parser.parse_args()

    if args.watch:
        interval = max(5, int(args.interval_seconds or DEFAULT_INTERVAL_SECONDS))
        while True:
            print(json.dumps(run_manual_sr_image_auto_ingest_once(reason='watch'), indent=2))
            time.sleep(interval)

    result = run_manual_sr_image_auto_ingest_once(reason='cli')
    print(json.dumps(result, indent=2))
    return 1 if result.get('status') == 'failed' else 0


__all__ = [
    'run_manual_sr_image_auto_ingest_once',
    'start_manual_sr_image_auto_ingest_scheduler',
]


if __name__ == '__main__':
    raise SystemExit(main())
