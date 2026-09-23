from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Set, Tuple

from batch.common.manual_price_action_sr_levels_sql import (
    build_manual_sr_levels_delete_sql,
    build_manual_sr_levels_merge_sql,
    build_manual_sr_levels_presence_sql,
    get_manual_sr_levels_value_column,
)

SCREENSHOT_TIMESTAMP_SUFFIX_RE = re.compile(r'_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$')

NaturalKey = Tuple[str, str, str, float]
GroupKey = Tuple[str, str, str]
QUEUE_PAYLOAD_DIR = Path(__file__).resolve().parents[1] / 'manual_sr_image_queue' / '04_payloads'

def _is_tablespace_full_error(exc: Exception) -> bool:
    return 'ORA-01653' in str(exc or '')


def normalize_symbol(symbol: str) -> str:
    value = str(symbol or '').strip().upper()
    if value.startswith('NSE:'):
        value = value[4:]
    if value.endswith('-EQ'):
        value = value[:-3]
    value = SCREENSHOT_TIMESTAMP_SUFFIX_RE.sub('', value)
    return value.strip()


def normalize_tf(tf: str | None) -> str:
    value = str(tf or '1D').strip().upper()
    return value or '1D'


def _resolve_ai_payload_dir(files: Sequence[str] | None = None, directory: str | None = None) -> Path | None:
    queue_dir = QUEUE_PAYLOAD_DIR.resolve()
    if directory:
        dir_path = Path(directory).resolve()
        if dir_path == queue_dir:
            return queue_dir
    file_paths = [Path(file_path).resolve() for file_path in files or []]
    if file_paths and all(path.parent == queue_dir for path in file_paths):
        return queue_dir
    return None


def _sync_ai_exports_if_supported(files: Sequence[str] | None = None, directory: str | None = None) -> Dict[str, Any] | None:
    payload_dir = _resolve_ai_payload_dir(files=files, directory=directory)
    if payload_dir is None:
        return None
    from batch.jobs.manual_sr_ai_sync import sync_ai_exports

    return sync_ai_exports(payload_dir)


def load_payload(path: str | Path) -> List[Dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get('records'), list):
        return payload['records']
    raise ValueError("Manual SR payload must be a list or an object with a 'records' array")


def collect_payload_files(files: Sequence[str] | None = None, directory: str | None = None, pattern: str = '*.json') -> List[Path]:
    paths: List[Path] = []
    seen: Set[str] = set()

    for file_path in files or []:
        path = Path(file_path)
        resolved = str(path.resolve())
        if resolved not in seen:
            paths.append(path)
            seen.add(resolved)

    if directory:
        dir_path = Path(directory)
        for path in sorted(dir_path.glob(pattern)):
            if not path.is_file():
                continue
            resolved = str(path.resolve())
            if resolved not in seen:
                paths.append(path)
                seen.add(resolved)

    if not paths:
        raise ValueError('Provide at least one --file or --dir with matching JSON payloads')
    return paths


def load_payloads(files: Sequence[str] | None = None, directory: str | None = None, pattern: str = '*.json') -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for path in collect_payload_files(files=files, directory=directory, pattern=pattern):
        records.extend(load_payload(path))
    return records


def prime_db_env_from_oracle_env() -> None:
    if not os.getenv('DB_USER') and os.getenv('ORACLE_USER'):
        os.environ['DB_USER'] = os.environ['ORACLE_USER']
    if not os.getenv('DB_PASSWORD') and os.getenv('ORACLE_PASSWORD'):
        os.environ['DB_PASSWORD'] = os.environ['ORACLE_PASSWORD']
    if os.getenv('DB_DSN'):
        return
    if os.getenv('ORACLE_DSN'):
        os.environ['DB_DSN'] = os.environ['ORACLE_DSN']
        return
    host = os.getenv('ORACLE_HOST')
    port = os.getenv('ORACLE_PORT')
    service_name = os.getenv('ORACLE_SERVICE_NAME') or os.getenv('ORACLE_SERVICE')
    sid = os.getenv('ORACLE_SID')
    if host and port and (service_name or sid):
        os.environ['DB_DSN'] = f"{host}:{port}/{service_name or sid}"


def _stable_level_id(symbol: str, tf: str, level_type: str, sr_levels: float) -> str:
    seed = f"{symbol}|{tf}|{level_type}|{sr_levels:.6f}"
    return hashlib.md5(seed.encode('utf-8')).hexdigest()


def _natural_key(symbol: str, tf: str, level_type: str, sr_levels: float) -> NaturalKey:
    return symbol, tf, level_type, round(float(sr_levels), 6)


def _extract_level_entries(record: Dict[str, Any]) -> List[Any]:
    flat_levels = record.get('sr_levels')
    if isinstance(flat_levels, list):
        return list(flat_levels)

    levels = record.get('levels')
    if isinstance(levels, list):
        return list(levels)

    raise ValueError("Manual SR record must include a non-empty 'sr_levels' or 'levels' array")


def _resolve_sr_levels_value(level: Any) -> float:
    if isinstance(level, dict):
        if 'sr_levels' in level:
            return float(level['sr_levels'])
        if 'sr_level' in level:
            return float(level['sr_level'])
        if 'price' in level:
            return float(level['price'])
        if 'price_low' in level and 'price_high' in level:
            price_low = float(level['price_low'])
            price_high = float(level['price_high'])
            return round((price_low + price_high) / 2.0, 6)
        raise ValueError("Manual SR level dict must provide 'sr_levels', 'sr_level', 'price', or both 'price_low' and 'price_high'")
    return float(level)


def _dedupe_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: Dict[NaturalKey, Dict[str, Any]] = {}
    for row in rows:
        key = _natural_key(row['symbol'], row['tf'], row['level_type'], row['sr_levels'])
        if key not in deduped:
            deduped[key] = dict(row)
    return list(deduped.values())


def build_merge_rows(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    for record in records:
        symbol = normalize_symbol(record.get('symbol', ''))
        if not symbol:
            raise ValueError('Each manual SR record must include a symbol')

        tf = normalize_tf(record.get('tf'))
        level_type = str(record.get('level_type') or 'MANUAL').strip().upper()[:8] or 'MANUAL'

        level_entries = _extract_level_entries(record)
        if not level_entries:
            continue

        for level in level_entries:
            sr_levels = _resolve_sr_levels_value(level)
            rows.append(
                {
                    'level_id': _stable_level_id(symbol=symbol, tf=tf, level_type=level_type, sr_levels=sr_levels),
                    'symbol': symbol,
                    'tf': tf,
                    'level_type': level_type,
                    'sr_levels': sr_levels,
                }
            )

    return _dedupe_rows(rows)


def _group_rows(rows: Iterable[Dict[str, Any]]) -> Dict[GroupKey, Set[float]]:
    grouped: Dict[GroupKey, Set[float]] = defaultdict(set)
    for row in rows:
        key = (row['symbol'], row['tf'], row['level_type'])
        grouped[key].add(round(float(row['sr_levels']), 6))
    return grouped


def fetch_existing_natural_keys(rows: Iterable[Dict[str, Any]]) -> Set[NaturalKey]:
    prime_db_env_from_oracle_env()
    from batch.common.db import fetch_all

    row_list = list(rows)
    if not row_list:
        return set()

    value_column = get_manual_sr_levels_value_column()
    sql = build_manual_sr_levels_presence_sql(value_column)
    existing_keys: Set[NaturalKey] = set()

    for (symbol, tf, level_type), expected_levels in _group_rows(row_list).items():
        db_rows = fetch_all(sql, {'symbol': symbol, 'tf': tf, 'level_type': level_type})
        for db_row in db_rows:
            level_value = db_row.get('level_value')
            if level_value is None:
                continue
            rounded_value = round(float(level_value), 6)
            if rounded_value in expected_levels:
                existing_keys.add((symbol, tf, level_type, rounded_value))

    return existing_keys


def fetch_all_natural_keys(rows: Iterable[Dict[str, Any]]) -> Set[NaturalKey]:
    prime_db_env_from_oracle_env()
    from batch.common.db import fetch_all

    row_list = list(rows)
    if not row_list:
        return set()

    value_column = get_manual_sr_levels_value_column()
    sql = build_manual_sr_levels_presence_sql(value_column)
    existing_keys: Set[NaturalKey] = set()

    for symbol, tf, level_type in _group_rows(row_list):
        db_rows = fetch_all(sql, {'symbol': symbol, 'tf': tf, 'level_type': level_type})
        for db_row in db_rows:
            level_value = db_row.get('level_value')
            if level_value is None:
                continue
            existing_keys.add((symbol, tf, level_type, round(float(level_value), 6)))

    return existing_keys


def split_rows_by_db_presence(rows: Iterable[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    row_list = list(rows)
    existing_keys = fetch_existing_natural_keys(row_list)
    missing_rows: List[Dict[str, Any]] = []
    present_rows: List[Dict[str, Any]] = []

    for row in row_list:
        key = _natural_key(row['symbol'], row['tf'], row['level_type'], row['sr_levels'])
        if key in existing_keys:
            present_rows.append(row)
        else:
            missing_rows.append(row)

    return missing_rows, present_rows


def _insert_rows_best_effort(sql: str, rows: List[Dict[str, Any]]) -> int:
    from batch.common.db import execute_many

    if not rows:
        return 0
    try:
        return execute_many(sql, rows)
    except Exception as exc:
        if not _is_tablespace_full_error(exc):
            raise
        if len(rows) == 1:
            return 0
        midpoint = max(1, len(rows) // 2)
        return _insert_rows_best_effort(sql, rows[:midpoint]) + _insert_rows_best_effort(sql, rows[midpoint:])


def insert_rows(rows: List[Dict[str, Any]]) -> int:
    prime_db_env_from_oracle_env()
    return _insert_rows_best_effort(build_manual_sr_levels_merge_sql(), rows)


def delete_rows(rows: List[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    prime_db_env_from_oracle_env()
    from batch.common.db import execute_many

    return execute_many(build_manual_sr_levels_delete_sql(), rows)


def sync_rows_to_db(rows: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    row_list = _dedupe_rows(rows)
    if not row_list:
        return {
            'expected_rows': 0,
            'present_rows': 0,
            'missing_rows': 0,
            'inserted_rows': 0,
            'stale_rows': 0,
            'deleted_rows': 0,
        }

    existing_keys = fetch_all_natural_keys(row_list)
    expected_keys = {_natural_key(row['symbol'], row['tf'], row['level_type'], row['sr_levels']) for row in row_list}
    missing_rows = [row for row in row_list if _natural_key(row['symbol'], row['tf'], row['level_type'], row['sr_levels']) not in existing_keys]
    stale_keys = existing_keys - expected_keys
    stale_rows = [
        {
            'symbol': symbol,
            'tf': tf,
            'level_type': level_type,
            'sr_levels': sr_levels,
        }
        for symbol, tf, level_type, sr_levels in sorted(stale_keys)
    ]

    deleted_rows = delete_rows(stale_rows)
    inserted_rows = insert_rows(missing_rows)

    return {
        'expected_rows': len(row_list),
        'present_rows': len(row_list) - len(missing_rows),
        'missing_rows': len(missing_rows),
        'inserted_rows': inserted_rows,
        'stale_rows': len(stale_rows),
        'deleted_rows': deleted_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='MERGE manual support/resistance levels into PRICE_ACTION_SR_LEVELS_MANUALLY')
    parser.add_argument('--file', action='append', help='JSON file with manual SR level records; repeatable')
    parser.add_argument('--dir', help='Directory containing JSON payload files to process together')
    parser.add_argument('--pattern', default='*.json', help='Glob pattern used with --dir')
    parser.add_argument('--dry-run', action='store_true', help='Validate and print rows without inserting')
    parser.add_argument('--check-only', action='store_true', help='Check which payload rows are already present in Oracle')
    parser.add_argument('--only-missing', action='store_true', help='Insert only rows that are currently missing in Oracle')
    args = parser.parse_args()

    rows = build_merge_rows(load_payloads(files=args.file, directory=args.dir, pattern=args.pattern))
    if not rows:
        print('No annotated SR levels found in the supplied payloads; nothing to insert into PRICE_ACTION_SR_LEVELS_MANUALLY.')
        return

    if args.dry_run:
        print(json.dumps({'rows': rows, 'count': len(rows)}, indent=2, default=str))
        return

    if args.check_only or args.only_missing:
        missing_rows, present_rows = split_rows_by_db_presence(rows)
        if args.check_only:
            print(json.dumps({
                'total_rows': len(rows),
                'present_count': len(present_rows),
                'missing_count': len(missing_rows),
                'missing_rows': missing_rows,
            }, indent=2, default=str))
            return
        rows = missing_rows
        if not rows:
            print('All payload rows already exist in PRICE_ACTION_SR_LEVELS_MANUALLY; nothing to insert.')
            return

    affected = insert_rows(rows)
    print(f"Merged {len(rows)} manual SR levels into PRICE_ACTION_SR_LEVELS_MANUALLY; affected rows reported by driver: {affected}")
    ai_export_result = _sync_ai_exports_if_supported(files=args.file, directory=args.dir)
    if ai_export_result:
        print(
            f"AI exports refreshed: training={ai_export_result['training_rows_exported']}, "
            f"rag={ai_export_result['rag_rows_exported']}, ai_ready={ai_export_result['ai_rows_exported']}"
        )


if __name__ == '__main__':
    main()




