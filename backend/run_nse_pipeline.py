from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Callable, Dict, List

from services import nse_delivery_service as nse_delivery_svc
from services import nse_ffmc_service as nse_ffmc_svc
from services import nse_mcap_service as nse_mcap_svc


PipelineRunner = Callable[[Dict[str, Any]], Dict[str, Any]]


PIPELINES: dict[str, tuple[str, PipelineRunner]] = {
    'market-cap': ('NSE Market Cap', nse_mcap_svc.run_pipeline),
    'ffmc': ('NSE FFMC', nse_ffmc_svc.run_pipeline),
    'delivery': ('NSE Delivery', nse_delivery_svc.run_pipeline),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Run NSE ingestion pipelines without using the UI.')
    parser.add_argument('--dataset', choices=['market-cap', 'ffmc', 'delivery', 'all'], default='all', help='Pipeline to run.')
    parser.add_argument('--trade-date', dest='trade_date', help='Trade date in YYYY-MM-DD format. Defaults to the latest business date used by each service.')
    parser.add_argument('--symbols', help='Optional comma-separated symbol override for market-cap and FFMC pipelines.')
    parser.add_argument('--enrich-limit', dest='enrich_limit', type=int, help='Optional quote enrichment limit for market-cap and FFMC pipelines.')
    parser.add_argument('--eq-only', dest='eq_only', action='store_true', default=True, help='Process EQ series only.')
    parser.add_argument('--include-non-eq', dest='eq_only', action='store_false', help='Allow non-EQ series rows.')
    return parser


def _payload_from_args(args: argparse.Namespace) -> Dict[str, Any]:
    payload: Dict[str, Any] = {'eqOnly': bool(args.eq_only)}
    if args.trade_date:
        payload['tradeDate'] = args.trade_date
    if args.symbols:
        payload['symbols'] = args.symbols
    if args.enrich_limit is not None:
        payload['enrichLimit'] = int(args.enrich_limit)
    return payload


def _selected_datasets(value: str) -> List[str]:
    if value == 'all':
        return ['market-cap', 'ffmc', 'delivery']
    return [value]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    payload = _payload_from_args(args)

    results: Dict[str, Any] = {'ok': True, 'requestedDataset': args.dataset, 'payload': payload, 'pipelines': {}}
    for dataset in _selected_datasets(args.dataset):
        label, runner = PIPELINES[dataset]
        try:
            results['pipelines'][dataset] = {'label': label, 'result': runner(dict(payload))}
        except Exception as exc:
            results['ok'] = False
            results['pipelines'][dataset] = {'label': label, 'ok': False, 'message': str(exc)}

    stream = sys.stdout if results['ok'] else sys.stderr
    print(json.dumps(results, indent=2, default=str), file=stream)
    return 0 if results['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
