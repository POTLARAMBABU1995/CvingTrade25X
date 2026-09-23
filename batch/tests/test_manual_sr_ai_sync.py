from __future__ import annotations

import json
from pathlib import Path

from batch.jobs import manual_sr_ai_sync as ai_module


def test_sync_ai_exports_writes_ai_ready_rows(tmp_path, monkeypatch):
    dataset_path = tmp_path / 'manual_sr_training_dataset.jsonl'
    rag_path = tmp_path / 'manual_sr_rag_documents.jsonl'
    dataset_row = {
        'dataset_type': 'manual_sr_training_example',
        'taxonomy_version': 'manual-sr-annotation-v1',
        'symbol': 'ABC',
        'tf': '1D',
        'as_of_date': '2026-03-24',
        'source': 'manual_image',
        'source_timeframe': '1W',
        'source_image': 'ABC.png',
        'source_image_path': 'C:/tmp/ABC.png',
        'payload_path': 'C:/tmp/ABC.json',
        'sr_levels': [120.0, 100.0, 80.0],
        'analysis': {'cmp': 95.0, 'trend_direction': 'UP', 'price_action_state': ['compression']},
        'agent_training': {'use_for_rag': True, 'use_for_training': True},
        'ohlcv_context': {
            'summary': {'latest_close': 96.0, 'range_high': 120.0, 'range_low': 80.0, 'return_20d_pct': 4.5},
            'bars': [
                {'date': '2026-03-23', 'open': 94.0, 'high': 96.0, 'low': 93.0, 'close': 95.0, 'volume': 1000},
                {'date': '2026-03-24', 'open': 95.0, 'high': 97.0, 'low': 94.0, 'close': 96.0, 'volume': 1100},
            ],
        },
    }
    dataset_path.write_text(json.dumps(dataset_row) + '\n', encoding='utf-8')
    rag_path.write_text('', encoding='utf-8')

    monkeypatch.setattr(
        ai_module,
        'build_corpus',
        lambda payload_root, skip_db=False, max_bars=0, rag_bar_limit=0: {
            'dataset_path': str(dataset_path),
            'rag_path': str(rag_path),
            'training_rows_exported': 1,
            'rag_rows_exported': 0,
        },
    )

    result = ai_module.sync_ai_exports(tmp_path, skip_db=True, max_bars=10, rag_bar_limit=5)
    ai_path = Path(result['ai_export_path'])
    rows = [json.loads(line) for line in ai_path.read_text(encoding='utf-8').splitlines() if line.strip()]

    assert result['ai_rows_exported'] == 1
    assert rows[0]['sr_feature_summary']['nearest_support'] == 80.0
    assert rows[0]['sr_feature_summary']['nearest_resistance'] == 100.0
    assert rows[0]['workflow']['db_table'] == 'PRICE_ACTION_SR_LEVELS_MANUALLY'
    assert 'Nearest resistance: 100.0' in rows[0]['llm_text']
