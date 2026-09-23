import { chartApiGet, type RequestOptions } from './client';
import type { BarsResponse, Timeframe } from '../types';

export type BarsParams = {
  symbol: string;
  tf: Timeframe;
  from?: string;
  to?: string;
  range?: string;
  limit?: number;
  cursor?: string | null;
};

export function fetchBars(params: BarsParams, options: RequestOptions = {}): Promise<BarsResponse> {
  return chartApiGet<BarsResponse>('/api/bars', {
    symbol: params.symbol,
    tf: params.tf,
    from: params.from,
    to: params.to,
    range: params.range,
    limit: params.limit,
    cursor: params.cursor ?? undefined,
  }, options);
}
