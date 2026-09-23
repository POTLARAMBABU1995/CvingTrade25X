from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional

from batch.jobs.build_manual_sr_training_corpus import DEFAULT_MAX_BARS, DEFAULT_RAG_TEXT_BARS, build_corpus


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding='utf-8').splitlines():
        text = line.strip()
        if not text:
            continue
        rows.append(json.loads(text))
    return rows


def _pct_distance(base: Optional[float], level: Optional[float]) -> Optional[float]:
    if base in (None, 0) or level is None:
        return None
    return round(((level - base) / base) * 100, 2)


def _derive_sr_feature_summary(entry: Dict[str, Any]) -> Dict[str, Any]:
    raw_levels = [_safe_float(level) for level in (entry.get('sr_levels') or [])]
    levels = sorted({level for level in raw_levels if level is not None}, reverse=True)
    analysis = entry.get('analysis') or {}
    ohlcv_context = entry.get('ohlcv_context') or {}
    summary = ohlcv_context.get('summary') or {}
    cmp_value = _safe_float(analysis.get('cmp'))
    if cmp_value is None:
        cmp_value = _safe_float(summary.get('latest_close'))

    nearest_support = None
    nearest_resistance = None
    nearest_level = None
    levels_above_cmp = None
    levels_below_cmp = None
    if cmp_value is not None and levels:
        supports = [level for level in levels if level <= cmp_value]
        resistances = [level for level in levels if level >= cmp_value]
        nearest_support = max(supports) if supports else None
        nearest_resistance = min(resistances) if resistances else None
        nearest_level = min(levels, key=lambda level: abs(level - cmp_value))
        levels_above_cmp = sum(1 for level in levels if level > cmp_value)
        levels_below_cmp = sum(1 for level in levels if level < cmp_value)

    gaps = [round(levels[idx] - levels[idx + 1], 2) for idx in range(len(levels) - 1)]
    gap_mean = round(mean(gaps), 2) if gaps else None
    gap_min = min(gaps) if gaps else None
    gap_max = max(gaps) if gaps else None

    return {
        'level_count': len(levels),
        'levels_desc': levels,
        'highest_level': levels[0] if levels else None,
        'lowest_level': levels[-1] if levels else None,
        'cmp': cmp_value,
        'nearest_support': nearest_support,
        'nearest_resistance': nearest_resistance,
        'nearest_level': nearest_level,
        'nearest_support_distance_pct': _pct_distance(cmp_value, nearest_support),
        'nearest_resistance_distance_pct': _pct_distance(cmp_value, nearest_resistance),
        'nearest_level_distance_pct': _pct_distance(cmp_value, nearest_level),
        'levels_above_cmp': levels_above_cmp,
        'levels_below_cmp': levels_below_cmp,
        'mean_gap': gap_mean,
        'min_gap': gap_min,
        'max_gap': gap_max,
    }


def _build_llm_text(entry: Dict[str, Any], feature_summary: Dict[str, Any], rag_bar_limit: int) -> str:
    analysis = entry.get('analysis') or {}
    ohlcv_context = entry.get('ohlcv_context') or {}
    summary = ohlcv_context.get('summary') or {}
    recent_bars = (ohlcv_context.get('bars') or [])[-rag_bar_limit:]
    bar_text = '; '.join(
        f"{bar.get('date')} O:{bar.get('open')} H:{bar.get('high')} L:{bar.get('low')} C:{bar.get('close')} V:{bar.get('volume')}"
        for bar in recent_bars
    )
    lines = [
        f"Symbol: {entry.get('symbol')}",
        f"Target timeframe: {entry.get('tf')}",
        f"Source timeframe: {entry.get('source_timeframe')}",
        f"As of date: {entry.get('as_of_date')}",
        f"SR levels desc: {', '.join(str(level) for level in feature_summary.get('levels_desc') or [])}",
        f"CMP: {feature_summary.get('cmp')}",
        f"Nearest support: {feature_summary.get('nearest_support')}",
        f"Nearest resistance: {feature_summary.get('nearest_resistance')}",
        f"Levels above CMP: {feature_summary.get('levels_above_cmp')}",
        f"Levels below CMP: {feature_summary.get('levels_below_cmp')}",
        f"Trend direction: {analysis.get('trend_direction')}",
        f"Market phase: {analysis.get('market_phase')}",
        f"Price action state: {', '.join(analysis.get('price_action_state') or [])}",
        f"Chart patterns: {', '.join(analysis.get('chart_patterns') or [])}",
        f"Pattern bias: {analysis.get('pattern_bias')}",
        f"Narrative: {analysis.get('narrative')}",
        f"OHLCV summary: latest_close={summary.get('latest_close')}, range_high={summary.get('range_high')}, range_low={summary.get('range_low')}, return_20d_pct={summary.get('return_20d_pct')}, return_60d_pct={summary.get('return_60d_pct')}",
        f"Recent bars: {bar_text}",
    ]
    return '\n'.join(line for line in lines if line and line.strip())


def _build_ai_row(entry: Dict[str, Any], rag_bar_limit: int) -> Dict[str, Any]:
    feature_summary = _derive_sr_feature_summary(entry)
    agent_training = entry.get('agent_training') or {}
    ohlcv_context = entry.get('ohlcv_context') or {}
    recent_bars = (ohlcv_context.get('bars') or [])[-rag_bar_limit:]
    return {
        'id': f"{entry.get('symbol')}__{entry.get('as_of_date')}__manual_sr_ai",
        'record_type': 'manual_sr_ai_ready',
        'symbol': entry.get('symbol'),
        'tf': entry.get('tf'),
        'as_of_date': entry.get('as_of_date'),
        'source': entry.get('source'),
        'source_timeframe': entry.get('source_timeframe'),
        'sr_levels': entry.get('sr_levels') or [],
        'sr_feature_summary': feature_summary,
        'analysis': entry.get('analysis') or {},
        'ohlcv_summary': (ohlcv_context.get('summary') or {}),
        'recent_bars': recent_bars,
        'workflow': {
            'payload_path': entry.get('payload_path'),
            'source_image': entry.get('source_image'),
            'source_image_path': entry.get('source_image_path'),
            'db_table': 'PRICE_ACTION_SR_LEVELS_MANUALLY',
            'dataset_type': entry.get('dataset_type'),
            'taxonomy_version': entry.get('taxonomy_version'),
            'use_for_rag': bool(agent_training.get('use_for_rag', True)),
            'use_for_training': bool(agent_training.get('use_for_training', True)),
        },
        'llm_text': _build_llm_text(entry, feature_summary, rag_bar_limit),
    }


def sync_ai_exports(
    payload_dir: str | Path,
    skip_db: bool = False,
    max_bars: int = DEFAULT_MAX_BARS,
    rag_bar_limit: int = DEFAULT_RAG_TEXT_BARS,
) -> Dict[str, Any]:
    payload_root = Path(payload_dir)
    corpus_result = build_corpus(payload_root, skip_db=skip_db, max_bars=max_bars, rag_bar_limit=rag_bar_limit)
    dataset_path = Path(corpus_result['dataset_path'])
    ai_path = dataset_path.with_name('manual_sr_ai_ready_records.jsonl')
    dataset_rows = _read_jsonl(dataset_path)
    ai_rows = [_build_ai_row(entry, rag_bar_limit) for entry in dataset_rows]
    ai_path.write_text('\n'.join(json.dumps(row, ensure_ascii=False) for row in ai_rows), encoding='utf-8')

    result = dict(corpus_result)
    result['ai_export_path'] = str(ai_path)
    result['ai_rows_exported'] = len(ai_rows)
    return result
