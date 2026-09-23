from __future__ import annotations

import argparse
import json
import math
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from batch.common.db import fetch_all
from batch.jobs.load_manual_sr_levels import normalize_symbol, prime_db_env_from_oracle_env
from batch.jobs.manage_manual_sr_image_queue import QueuePaths, ensure_queue_dirs

DEFAULT_OHLCV_TABLE = os.getenv('SR_TRAINING_OHLCV_TABLE', 'OHLCV_D')
DEFAULT_MAX_BARS = 180
DEFAULT_RAG_TEXT_BARS = 20


def _parse_date(value: str | None) -> Optional[date]:
    raw = str(value or '').strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except ValueError:
        return None


def _iso(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return None


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _read_payload_records(payload_dir: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for path in sorted(payload_dir.glob('*.json')):
        payload = json.loads(path.read_text(encoding='utf-8-sig'))
        records = payload.get('records') if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            row = dict(record)
            row['_payload_path'] = str(path)
            row['_dataset_version'] = payload.get('dataset_version') if isinstance(payload, dict) else None
            row['_taxonomy_version'] = payload.get('taxonomy_version') if isinstance(payload, dict) else None
            rows.append(row)
    return rows


def _find_image_path(paths: QueuePaths, image_name: str | None) -> Optional[str]:
    if not image_name:
        return None
    for folder in (paths.inbox, paths.processed, paths.rejected):
        candidate = folder / image_name
        if candidate.exists():
            return str(candidate)
    return None


def _fetch_ohlcv(symbol: str, as_of_date: Optional[date], max_bars: int, skip_db: bool) -> Dict[str, Any]:
    if skip_db:
        return {'available': False, 'reason': 'skip_db'}

    prime_db_env_from_oracle_env()
    if not (os.getenv('DB_USER') and os.getenv('DB_PASSWORD') and os.getenv('DB_DSN')):
        return {'available': False, 'reason': 'db_env_missing'}

    where_date = ''
    params: Dict[str, Any] = {'symbol': symbol, 'limit': max_bars}
    if as_of_date is not None:
        where_date = ' AND BAR_DATE <= :as_of_date'
        params['as_of_date'] = as_of_date

    sql = f"""
        SELECT * FROM (
          SELECT BAR_DATE,
                 OPEN_PRICE,
                 HIGH_PRICE,
                 LOW_PRICE,
                 CLOSE_PRICE,
                 VOLUME
          FROM {DEFAULT_OHLCV_TABLE}
          WHERE SYMBOL = :symbol
          {where_date}
          ORDER BY BAR_DATE DESC
        )
        WHERE ROWNUM <= :limit
    """

    try:
        rows = fetch_all(sql, params)
    except Exception as exc:
        return {'available': False, 'reason': f'db_error: {exc}'}

    rows.reverse()
    bars: List[Dict[str, Any]] = []
    for row in rows:
        bars.append({
            'date': _iso(row.get('bar_date')),
            'open': _safe_float(row.get('open_price')),
            'high': _safe_float(row.get('high_price')),
            'low': _safe_float(row.get('low_price')),
            'close': _safe_float(row.get('close_price')),
            'volume': _safe_float(row.get('volume')),
        })
    return {
        'available': True,
        'table': DEFAULT_OHLCV_TABLE,
        'bars': bars,
    }


def _compute_ohlcv_summary(bars: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not bars:
        return {'bars_count': 0}

    closes = [bar['close'] for bar in bars if bar.get('close') is not None]
    highs = [bar['high'] for bar in bars if bar.get('high') is not None]
    lows = [bar['low'] for bar in bars if bar.get('low') is not None]
    volumes = [bar['volume'] for bar in bars if bar.get('volume') is not None]
    latest = bars[-1]

    def _pct_return(window: int) -> Optional[float]:
        if len(closes) <= window:
            return None
        start = closes[-window - 1]
        end = closes[-1]
        if start in (None, 0) or end is None:
            return None
        return round(((end - start) / start) * 100, 2)

    avg_volume_20 = None
    if len(volumes) >= 20:
        recent = volumes[-20:]
        avg_volume_20 = round(sum(recent) / len(recent), 2)

    daily_vol_20 = None
    if len(closes) >= 21:
        returns: List[float] = []
        for idx in range(len(closes) - 20, len(closes)):
            prev_close = closes[idx - 1]
            curr_close = closes[idx]
            if prev_close and curr_close:
                returns.append((curr_close / prev_close) - 1)
        if returns:
            mean_ret = sum(returns) / len(returns)
            variance = sum((ret - mean_ret) ** 2 for ret in returns) / len(returns)
            daily_vol_20 = round(math.sqrt(variance) * 100, 2)

    return {
        'bars_count': len(bars),
        'latest_bar_date': latest.get('date'),
        'latest_close': latest.get('close'),
        'range_high': max(highs) if highs else None,
        'range_low': min(lows) if lows else None,
        'return_20d_pct': _pct_return(20),
        'return_60d_pct': _pct_return(60),
        'return_120d_pct': _pct_return(120),
        'avg_volume_20': avg_volume_20,
        'daily_volatility_20_pct': daily_vol_20,
    }


def _build_rag_text(entry: Dict[str, Any], rag_bar_limit: int) -> str:
    analysis = entry.get('analysis') or {}
    ohlcv = entry.get('ohlcv_context') or {}
    summary = ohlcv.get('summary') or {}
    levels = ', '.join(str(level) for level in entry.get('sr_levels', []))
    bars = ohlcv.get('bars') or []
    last_bars = bars[-rag_bar_limit:] if bars else []
    bar_text = '; '.join(
        f"{bar.get('date')} O:{bar.get('open')} H:{bar.get('high')} L:{bar.get('low')} C:{bar.get('close')} V:{bar.get('volume')}"
        for bar in last_bars
    )
    lines = [
        f"Symbol: {entry.get('symbol')}",
        f"Target timeframe: {entry.get('tf')}",
        f"Source timeframe: {entry.get('source_timeframe')}",
        f"As of date: {entry.get('as_of_date')}",
        f"SR levels: {levels}",
        f"Trend direction: {analysis.get('trend_direction')}",
        f"Market phase: {analysis.get('market_phase')}",
        f"Price action state: {', '.join(analysis.get('price_action_state') or [])}",
        f"Chart patterns: {', '.join(analysis.get('chart_patterns') or [])}",
        f"Pattern bias: {analysis.get('pattern_bias')}",
        f"Narrative: {analysis.get('narrative')}",
        f"OHLCV summary: latest_close={summary.get('latest_close')}, range_high={summary.get('range_high')}, range_low={summary.get('range_low')}, return_20d_pct={summary.get('return_20d_pct')}, return_60d_pct={summary.get('return_60d_pct')}, avg_volume_20={summary.get('avg_volume_20')}, daily_volatility_20_pct={summary.get('daily_volatility_20_pct')}",
        f"Recent bars: {bar_text}",
    ]
    return '\n'.join(line for line in lines if line and line.strip())


def build_corpus(payload_dir: Path, skip_db: bool, max_bars: int, rag_bar_limit: int) -> Dict[str, Any]:
    paths = ensure_queue_dirs()
    records = _read_payload_records(payload_dir)
    dataset_rows: List[Dict[str, Any]] = []
    rag_rows: List[Dict[str, Any]] = []

    for record in records:
        symbol = normalize_symbol(record.get('symbol', ''))
        if not symbol:
            continue
        as_of_date = _parse_date(record.get('as_of_date'))
        source_image = record.get('source_image')
        image_path = _find_image_path(paths, source_image)
        sr_levels = [float(level) for level in (record.get('sr_levels') or []) if level is not None]
        ohlcv_context = _fetch_ohlcv(symbol, as_of_date, max_bars, skip_db)
        bars = ohlcv_context.get('bars') or []
        summary = _compute_ohlcv_summary(bars) if ohlcv_context.get('available') else {'bars_count': 0}
        ohlcv_context['summary'] = summary
        agent_training = record.get('agent_training') or {}
        use_for_training = bool(agent_training.get('use_for_training', True))
        use_for_rag = bool(agent_training.get('use_for_rag', True))

        dataset_entry = {
            'dataset_type': 'manual_sr_training_example',
            'dataset_version': record.get('_dataset_version') or 'manual-sr-image-v2',
            'taxonomy_version': record.get('_taxonomy_version') or 'manual-sr-annotation-v1',
            'symbol': symbol,
            'tf': record.get('tf') or '1D',
            'as_of_date': record.get('as_of_date'),
            'source': record.get('source'),
            'source_timeframe': record.get('source_timeframe'),
            'source_image': source_image,
            'source_image_path': image_path,
            'payload_path': record.get('_payload_path'),
            'sr_levels': sr_levels,
            'analysis': record.get('analysis') or {},
            'agent_training': agent_training,
            'notes': record.get('notes'),
            'ohlcv_context': ohlcv_context,
        }
        if use_for_training:
            dataset_rows.append(dataset_entry)
        if use_for_rag:
            rag_rows.append({
                'id': f"{symbol}__{record.get('as_of_date')}__manual_sr",
                'symbol': symbol,
                'tf': dataset_entry['tf'],
                'source_timeframe': dataset_entry['source_timeframe'],
                'as_of_date': dataset_entry['as_of_date'],
                'text': _build_rag_text(dataset_entry, rag_bar_limit),
                'metadata': {
                    'source_image': source_image,
                    'source_image_path': image_path,
                    'payload_path': record.get('_payload_path'),
                    'source': record.get('source'),
                    'dataset_type': 'manual_sr_training_example',
                    'taxonomy_version': dataset_entry['taxonomy_version'],
                    'use_for_rag': True,
                },
            })

    dataset_path = paths.training / 'manual_sr_training_dataset.jsonl'
    rag_path = paths.rag / 'manual_sr_rag_documents.jsonl'
    dataset_path.write_text('\n'.join(json.dumps(row, ensure_ascii=False) for row in dataset_rows), encoding='utf-8')
    rag_path.write_text('\n'.join(json.dumps(row, ensure_ascii=False) for row in rag_rows), encoding='utf-8')

    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'payload_dir': str(payload_dir),
        'dataset_path': str(dataset_path),
        'rag_path': str(rag_path),
        'training_rows_exported': len(dataset_rows),
        'rag_rows_exported': len(rag_rows),
        'records_exported': len(dataset_rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='Build reusable training and RAG corpus from manual SR image payloads')
    parser.add_argument('--payload-dir', default=str(ensure_queue_dirs().payloads), help='Directory containing payload JSON files')
    parser.add_argument('--skip-db', action='store_true', help='Do not fetch OHLCV context from Oracle')
    parser.add_argument('--max-bars', type=int, default=DEFAULT_MAX_BARS, help='Max OHLCV bars per record when DB context is available')
    parser.add_argument('--rag-bar-limit', type=int, default=DEFAULT_RAG_TEXT_BARS, help='Max recent bars to inline into RAG text')
    args = parser.parse_args()

    result = build_corpus(Path(args.payload_dir), skip_db=args.skip_db, max_bars=args.max_bars, rag_bar_limit=args.rag_bar_limit)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
