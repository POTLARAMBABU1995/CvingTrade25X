from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from batch.jobs.build_manual_sr_training_corpus import DEFAULT_MAX_BARS, DEFAULT_RAG_TEXT_BARS
from batch.jobs.manual_sr_ai_sync import sync_ai_exports
from batch.jobs.manage_manual_sr_image_queue import audit_processed_payloads, ensure_queue_dirs, scan_inbox


def _load_records(payload_dir: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
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
                row = dict(record)
                row['_payload_file'] = str(path)
                rows.append(row)
    return rows


def _counter_dict(values: List[str]) -> Dict[str, int]:
    cleaned = [value for value in values if value]
    return dict(sorted(Counter(cleaned).items()))


def summarize_annotations(payload_dir: Path) -> Dict[str, Any]:
    records = _load_records(payload_dir)
    trend_values: List[str] = []
    market_phase_values: List[str] = []
    pattern_values: List[str] = []
    state_values: List[str] = []
    symbols: List[str] = []
    annotated_records = 0
    training_enabled = 0
    rag_enabled = 0

    for record in records:
        symbols.append(str(record.get('symbol') or '').strip().upper())
        sr_levels = record.get('sr_levels') or []
        if sr_levels:
            annotated_records += 1
        agent_training = record.get('agent_training') or {}
        if agent_training.get('use_for_training', True):
            training_enabled += 1
        if agent_training.get('use_for_rag', True):
            rag_enabled += 1

        analysis = record.get('analysis') or {}
        trend_values.append(str(analysis.get('trend_direction') or '').strip())
        market_phase_values.append(str(analysis.get('market_phase') or '').strip())
        for pattern in analysis.get('chart_patterns') or []:
            pattern_values.append(str(pattern).strip())
        for state in analysis.get('price_action_state') or []:
            state_values.append(str(state).strip())

    return {
        'payload_dir': str(payload_dir),
        'payload_files': len(list(payload_dir.glob('*.json'))),
        'records_total': len(records),
        'records_with_sr_levels': annotated_records,
        'records_ready_for_training': training_enabled,
        'records_ready_for_rag': rag_enabled,
        'symbols': sorted(symbol for symbol in set(symbols) if symbol),
        'trend_direction_counts': _counter_dict(trend_values),
        'market_phase_counts': _counter_dict(market_phase_values),
        'chart_pattern_counts': _counter_dict(pattern_values),
        'price_action_state_counts': _counter_dict(state_values),
    }


def run_pipeline(
    scan_queue: bool,
    payload_dir: Path,
    skip_db: bool,
    max_bars: int,
    rag_bar_limit: int,
    verify_db: bool,
    retry_missing_db: bool,
) -> Dict[str, Any]:
    paths = ensure_queue_dirs()
    queue_manifest = None
    if scan_queue:
        queue_manifest = scan_inbox(create_skeletons=True)

    known_db_audit = None
    if verify_db or retry_missing_db:
        known_db_audit = audit_processed_payloads(retry_missing_db=retry_missing_db)

    annotation_summary = summarize_annotations(payload_dir)
    corpus_result = sync_ai_exports(payload_dir, skip_db=skip_db, max_bars=max_bars, rag_bar_limit=rag_bar_limit)

    run_manifest = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'scan_queue': scan_queue,
        'skip_db': skip_db,
        'verify_db': verify_db,
        'retry_missing_db': retry_missing_db,
        'payload_dir': str(payload_dir),
        'queue_manifest': queue_manifest,
        'known_db_audit': known_db_audit,
        'annotation_summary': annotation_summary,
        'corpus_result': corpus_result,
    }
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    manifest_path = paths.manifests / f'agent_learning_run_{stamp}.json'
    manifest_path.write_text(json.dumps(run_manifest, indent=2), encoding='utf-8')
    run_manifest['run_manifest_path'] = str(manifest_path)
    return run_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description='Run the reusable manual SR image learning pipeline')
    parser.add_argument('--scan', action='store_true', help='Refresh queue manifest and payload skeletons before building corpora')
    parser.add_argument('--payload-dir', default=str(ensure_queue_dirs().payloads), help='Directory containing payload JSON files')
    parser.add_argument('--skip-db', action='store_true', help='Do not fetch OHLCV context from Oracle')
    parser.add_argument('--verify-db', action='store_true', help='Audit already-processed images against Oracle SR inserts')
    parser.add_argument('--retry-missing-db', action='store_true', help='Reinsert missing SR rows for already-processed payloads')
    parser.add_argument('--max-bars', type=int, default=DEFAULT_MAX_BARS, help='Max OHLCV bars per record when DB context is available')
    parser.add_argument('--rag-bar-limit', type=int, default=DEFAULT_RAG_TEXT_BARS, help='Max recent bars to include in RAG text')
    args = parser.parse_args()

    result = run_pipeline(
        scan_queue=args.scan,
        payload_dir=Path(args.payload_dir),
        skip_db=args.skip_db,
        max_bars=args.max_bars,
        rag_bar_limit=args.rag_bar_limit,
        verify_db=args.verify_db,
        retry_missing_db=args.retry_missing_db,
    )
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

