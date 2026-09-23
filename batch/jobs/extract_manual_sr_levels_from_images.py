from __future__ import annotations

import argparse
import json
import platform
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np
from PIL import Image

from batch.jobs.load_manual_sr_levels import build_merge_rows, insert_rows, load_payloads, split_rows_by_db_presence, sync_rows_to_db
from batch.jobs.manage_manual_sr_image_queue import IMAGE_EXTENSIONS, ensure_queue_dirs, move_image

CHART_TOP_OFFSET = 40
CHART_BOTTOM_OFFSET = 60
RIGHT_LABEL_WIDTH = 80
RIGHT_LABEL_GAP = 5
REGULAR_LABEL_HALF_HEIGHT = 12
TOP_LABEL_UPSHIFT = 25
TOP_LABEL_DOWNSHIFT = 5
OCR_SCALE = 6
MIN_SOLID_LINE_PIXELS = 600
NUMERIC_TOKEN_RE = re.compile(r'(\d[\d,]*\.\d{2})')


def _cluster_rows(mask: np.ndarray, min_count: int = MIN_SOLID_LINE_PIXELS) -> List[Tuple[int, int]]:
    counts = mask.sum(axis=1)
    ys = np.where(counts > min_count)[0]
    if len(ys) == 0:
        return []

    clusters: List[Tuple[int, int]] = []
    start = prev = int(ys[0])
    for raw_y in ys[1:]:
        y = int(raw_y)
        if y <= prev + 2:
            prev = y
            continue
        clusters.append((start, prev))
        start = prev = y
    clusters.append((start, prev))
    return clusters


def detect_level_centers(image_path: str | Path) -> List[int]:
    arr = np.array(Image.open(image_path).convert('RGB'))
    height, width, _ = arr.shape
    chart = arr[CHART_TOP_OFFSET:max(CHART_TOP_OFFSET + 1, height - CHART_BOTTOM_OFFSET), 0:max(1, width - RIGHT_LABEL_WIDTH)]
    red = (chart[:, :, 0] > 200) & (chart[:, :, 1] < 110) & (chart[:, :, 2] < 130)
    green = (chart[:, :, 1] > 120) & (chart[:, :, 0] < 140) & (chart[:, :, 2] < 130)

    centers: List[int] = []
    for mask in (red, green):
        for start, end in _cluster_rows(mask):
            centers.append(int((start + end) // 2) + CHART_TOP_OFFSET)
    return sorted(set(centers))


def _build_crop_box(width: int, height: int, y: int) -> Tuple[int, int, int, int]:
    left = max(0, width - RIGHT_LABEL_WIDTH)
    right = max(left + 1, width - RIGHT_LABEL_GAP)
    if y < 100:
        top = max(0, y - TOP_LABEL_UPSHIFT)
        bottom = min(height, y + TOP_LABEL_DOWNSHIFT)
    else:
        top = max(0, y - REGULAR_LABEL_HALF_HEIGHT)
        bottom = min(height, y + REGULAR_LABEL_HALF_HEIGHT + 1)
    return left, top, right, max(top + 1, bottom)


def _ocr_pngs_with_windows_ocr(image_paths: Sequence[Path]) -> List[str]:
    if not image_paths:
        return []
    if platform.system() != 'Windows':
        raise RuntimeError('TradingView PNG OCR is only supported on Windows hosts.')

    script_body = r'''
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null=[Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
$null=[Windows.Storage.Streams.IRandomAccessStream,Windows.Storage.Streams,ContentType=WindowsRuntime]
$null=[Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
$null=[Windows.Graphics.Imaging.SoftwareBitmap,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
$null=[Windows.Media.Ocr.OcrEngine,Windows.Media.Ocr,ContentType=WindowsRuntime]
function Await([object]$WinRtTask,[type]$ResultType){
  $asTaskGeneric = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 } | Select-Object -First 1
  $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
  $netTask = $asTask.Invoke($null, @($WinRtTask))
  $netTask.Wait(-1) | Out-Null
  return $netTask.Result
}
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
$out = @()
foreach ($path in $args) {
  $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($path)) ([Windows.Storage.StorageFile])
  $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
  $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
  $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
  $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
  $out += [pscustomobject]@{ path = $path; text = $result.Text }
}
$out | ConvertTo-Json -Depth 4
'''

    with tempfile.TemporaryDirectory() as temp_dir:
        script_path = Path(temp_dir) / 'ocr.ps1'
        script_path.write_text(script_body, encoding='utf-8')
        command = [
            'powershell',
            '-NoProfile',
            '-ExecutionPolicy',
            'Bypass',
            '-File',
            str(script_path),
            *[str(path) for path in image_paths],
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or 'Windows OCR command failed')
        payload = result.stdout.strip()
        if not payload:
            return ['' for _ in image_paths]
        decoded = json.loads(payload)
        rows = decoded if isinstance(decoded, list) else [decoded]
        text_by_path = {str(row.get('path')): str(row.get('text') or '') for row in rows if isinstance(row, dict)}
        return [text_by_path.get(str(path), '') for path in image_paths]


def normalize_ocr_numeric_text(text: str) -> str:
    cleaned = str(text or '').replace('\r', '').replace('\n', '').replace(' ', '').strip()
    if not cleaned:
        return ''
    cleaned = cleaned.translate(str.maketrans({'O': '0', 'o': '0', 'I': '1', 'l': '1', '|': '1', 'S': '5'}))
    cleaned = re.sub(r'(?<=\d)[^\d,\.](?=\d{3}\.\d{2}\b)', ',', cleaned)
    cleaned = re.sub(r'(?<=\d),(?=\d{2}\.\d{2}\b)', '', cleaned)
    return cleaned


def parse_ocr_price(text: str) -> float | None:
    cleaned = normalize_ocr_numeric_text(text)
    match = NUMERIC_TOKEN_RE.search(cleaned)
    if not match:
        return None
    token = match.group(1).replace(',', '')
    try:
        return round(float(token), 2)
    except ValueError:
        return None


def _dedupe_exact_levels(levels: Sequence[float]) -> List[float]:
    deduped: List[float] = []
    seen: set[float] = set()
    for level in levels:
        rounded = round(float(level), 2)
        if rounded in seen:
            continue
        deduped.append(rounded)
        seen.add(rounded)
    return deduped


def _longest_descending_subsequence(levels: Sequence[float]) -> List[float]:
    values = [round(float(level), 2) for level in levels]
    if len(values) < 2:
        return values

    lengths = [1] * len(values)
    previous = [-1] * len(values)

    for index in range(len(values)):
        for candidate in range(index):
            if values[candidate] <= values[index] + 0.01:
                continue
            next_length = lengths[candidate] + 1
            if next_length > lengths[index]:
                lengths[index] = next_length
                previous[index] = candidate

    best_index = max(range(len(values)), key=lambda idx: (lengths[idx], values[idx]))
    sequence: List[float] = []
    while best_index >= 0:
        sequence.append(values[best_index])
        best_index = previous[best_index]
    return list(reversed(sequence))


def _drop_extreme_trailing_outliers(levels: Sequence[float]) -> List[float]:
    cleaned = list(levels)
    while len(cleaned) >= 3:
        highest = cleaned[0]
        second_lowest = cleaned[-2]
        lowest = cleaned[-1]
        if highest < 100:
            break
        if lowest >= second_lowest * 0.25:
            break
        if lowest >= highest * 0.10:
            break
        cleaned.pop()
    return cleaned


def cleanup_extracted_levels(levels: Sequence[float]) -> List[float]:
    deduped = _dedupe_exact_levels(levels)
    if not deduped:
        return []
    cleaned = _longest_descending_subsequence(deduped)
    cleaned = _drop_extreme_trailing_outliers(cleaned)
    return cleaned


def extract_levels_from_image(image_path: str | Path) -> List[float]:
    source_path = Path(image_path)
    base_image = Image.open(source_path).convert('RGB')
    centers = detect_level_centers(source_path)
    if not centers:
        return []

    crop_paths: List[Path] = []
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        for index, y in enumerate(centers):
            crop_box = _build_crop_box(base_image.width, base_image.height, y)
            crop = base_image.crop(crop_box)
            enlarged = crop.resize((crop.width * OCR_SCALE, crop.height * OCR_SCALE), Image.Resampling.NEAREST)
            crop_path = temp_root / f'{index:03d}.png'
            enlarged.save(crop_path)
            crop_paths.append(crop_path)

        ocr_texts = _ocr_pngs_with_windows_ocr(crop_paths)

    levels: List[float] = []
    for text in ocr_texts:
        price = parse_ocr_price(text)
        if price is None:
            continue
        levels.append(price)

    return cleanup_extracted_levels(levels)


def _find_image_path(image_name: str | None) -> Path | None:
    if not image_name:
        return None
    paths = ensure_queue_dirs()
    for folder in (paths.inbox, paths.processed, paths.known, paths.rejected):
        candidate = folder / image_name
        if candidate.exists():
            return candidate
    return None


def _load_payload_document(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8-sig'))


def _iter_records(document: Dict[str, Any]) -> List[Dict[str, Any]]:
    records = document.get('records') if isinstance(document, dict) else None
    if not isinstance(records, list):
        return []
    return [record for record in records if isinstance(record, dict)]


def _collect_group_payload_paths(payload_paths: Sequence[Path], pattern: str) -> List[Path]:
    candidate_paths = [Path(path) for path in payload_paths]
    if not candidate_paths:
        return []

    parent_dirs = {path.resolve().parent for path in candidate_paths}
    if len(parent_dirs) != 1:
        return candidate_paths

    payload_dir = next(iter(parent_dirs))
    group_keys = set()
    for payload_path in candidate_paths:
        rows = build_merge_rows(load_payloads(files=[str(payload_path)]))
        for row in rows:
            group_keys.add((row['symbol'], row['tf'], row['level_type']))

    if not group_keys:
        return candidate_paths

    matching_paths: List[Path] = []
    for payload_path in sorted(payload_dir.glob(pattern)):
        rows = build_merge_rows(load_payloads(files=[str(payload_path)]))
        if any((row['symbol'], row['tf'], row['level_type']) in group_keys for row in rows):
            matching_paths.append(payload_path)
    return matching_paths


def update_payload_file(payload_path: str | Path, overwrite: bool = False) -> Dict[str, Any]:
    path = Path(payload_path)
    document = _load_payload_document(path)
    records = _iter_records(document)
    updates: List[Dict[str, Any]] = []
    changed = False

    for record in records:
        existing_levels = record.get('sr_levels') or []
        if existing_levels and not overwrite:
            updates.append({
                'symbol': record.get('symbol'),
                'source_image': record.get('source_image'),
                'status': 'skipped_existing',
                'level_count': len(existing_levels),
            })
            continue

        image_path = _find_image_path(record.get('source_image'))
        if image_path is None:
            updates.append({
                'symbol': record.get('symbol'),
                'source_image': record.get('source_image'),
                'status': 'image_missing',
                'level_count': 0,
            })
            continue

        if image_path.suffix.lower() not in IMAGE_EXTENSIONS:
            updates.append({
                'symbol': record.get('symbol'),
                'source_image': record.get('source_image'),
                'status': 'unsupported_image_type',
                'level_count': 0,
            })
            continue

        levels = extract_levels_from_image(image_path)
        if not levels:
            updates.append({
                'symbol': record.get('symbol'),
                'source_image': record.get('source_image'),
                'status': 'ocr_failed',
                'level_count': 0,
            })
            continue

        record['sr_levels'] = levels
        if record.get('accuracy_estimate') is None:
            record['accuracy_estimate'] = 0.9
        note = str(record.get('notes') or '').strip()
        auto_note = 'Auto-extracted from TradingView screenshot into flat daily SR levels.'
        if 'Auto-extracted from TradingView screenshot' not in note:
            if not note or 'Fill sr_levels manually after reading the TradingView image.' in note:
                record['notes'] = auto_note
            else:
                record['notes'] = f'{note} {auto_note}'
        updates.append({
            'symbol': record.get('symbol'),
            'source_image': record.get('source_image'),
            'status': 'updated',
            'level_count': len(levels),
            'levels': levels,
        })
        changed = True

    if changed:
        path.write_text(json.dumps(document, indent=2), encoding='utf-8')

    return {
        'payload_path': str(path),
        'changed': changed,
        'updates': updates,
    }


def _sync_ai_exports(payload_dir: str | Path | None) -> Dict[str, Any]:
    from batch.jobs.manual_sr_ai_sync import sync_ai_exports

    target_dir = Path(payload_dir) if payload_dir else ensure_queue_dirs().payloads
    return sync_ai_exports(target_dir)


def process_payloads(files: Sequence[str] | None, directory: str | None, pattern: str, overwrite: bool, insert_db: bool, only_missing: bool, move_processed: bool, sync_db_groups: bool = False) -> Dict[str, Any]:
    from batch.jobs.load_manual_sr_levels import collect_payload_files

    payload_paths = collect_payload_files(files=files, directory=directory, pattern=pattern)
    payload_results = [update_payload_file(path, overwrite=overwrite) for path in payload_paths]
    changed_payloads = [result for result in payload_results if result['changed']]
    changed_paths = [result['payload_path'] for result in changed_payloads]
    db_candidate_paths = [str(path) for path in payload_paths]

    inserted_rows = 0
    present_rows = 0
    missing_rows = 0
    moved_images: List[str] = []
    partial_insert_payloads: List[Dict[str, Any]] = []
    ai_export_result: Dict[str, Any] | None = None
    sync_result: Dict[str, Any] | None = None

    if insert_db and db_candidate_paths:
        if sync_db_groups:
            group_payload_paths = _collect_group_payload_paths(payload_paths, pattern)
            sync_rows = build_merge_rows(load_payloads(files=[str(path) for path in group_payload_paths]))
            sync_result = sync_rows_to_db(sync_rows)
            inserted_rows = sync_result['inserted_rows']
            present_rows = sync_result['present_rows']
            missing_rows = sync_result['missing_rows']
        else:
            for payload_path in db_candidate_paths:
                rows = build_merge_rows(load_payloads(files=[payload_path]))
                if not rows:
                    continue

                if only_missing:
                    candidate_rows, present = split_rows_by_db_presence(rows)
                    present_rows += len(present)
                    missing_rows += len(candidate_rows)
                else:
                    candidate_rows = rows

                if not candidate_rows:
                    continue

                inserted_now = insert_rows(candidate_rows)
                inserted_rows += inserted_now

                if inserted_now < len(candidate_rows):
                    still_missing, now_present = split_rows_by_db_presence(candidate_rows)
                    partial_insert_payloads.append(
                        {
                            'payload_path': str(payload_path),
                            'requested_rows': len(candidate_rows),
                            'inserted_rows': len(now_present),
                            'missing_rows': len(still_missing),
                        }
                    )

    if move_processed and db_candidate_paths:
        for payload_path in db_candidate_paths:
            rows = build_merge_rows(load_payloads(files=[payload_path]))
            if not rows:
                continue
            missing, _present = split_rows_by_db_presence(rows)
            if missing:
                continue
            payload_doc = _load_payload_document(Path(payload_path))
            for record in _iter_records(payload_doc):
                image_name = record.get('source_image')
                if not image_name:
                    continue
                image_path = _find_image_path(image_name)
                if image_path is None or image_path.parent.name != '01_inbox':
                    continue
                destination = move_image(image_name, 'processed')
                moved_images.append(str(destination))

    if payload_paths and (changed_paths or insert_db):
        ai_export_result = _sync_ai_exports(directory or payload_paths[0].parent)

    return {
        'payloads_scanned': len(payload_paths),
        'payloads_changed': len(changed_paths),
        'payload_results': payload_results,
        'inserted_rows': inserted_rows,
        'present_rows_before_insert': present_rows,
        'missing_rows_before_insert': missing_rows,
        'moved_images': moved_images,
        'partial_insert_payloads': partial_insert_payloads,
        'sync_result': sync_result,
        'ai_export_result': ai_export_result,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='Extract TradingView screenshot SR labels into manual SR payloads')
    parser.add_argument('--file', action='append', help='Payload JSON file to update; repeatable')
    parser.add_argument('--dir', default=str(ensure_queue_dirs().payloads), help='Directory containing payload JSON files')
    parser.add_argument('--pattern', default='*.json', help='Glob pattern used with --dir')
    parser.add_argument('--overwrite', action='store_true', help='Overwrite payloads that already contain sr_levels')
    parser.add_argument('--insert-db', action='store_true', help='Insert extracted SR levels into PRICE_ACTION_SR_LEVELS_MANUALLY after updating payloads')
    parser.add_argument('--only-missing', action='store_true', help='When used with --insert-db, insert only rows that are missing in Oracle')
    parser.add_argument('--sync-db-groups', action='store_true', help='When used with --insert-db, sync the affected symbol/timeframe groups by deleting stale OCR rows and inserting missing rows')
    parser.add_argument('--move-processed', action='store_true', help='Move inbox images to 02_processed after their SR rows are confirmed in Oracle')
    args = parser.parse_args()

    result = process_payloads(
        files=args.file,
        directory=args.dir,
        pattern=args.pattern,
        overwrite=args.overwrite,
        insert_db=args.insert_db,
        only_missing=args.only_missing,
        move_processed=args.move_processed,
        sync_db_groups=args.sync_db_groups,
    )
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()








