import { chartApiGet } from './client';
import type { IndicatorsResponse, Timeframe } from '../types';

export type IndicatorsParams = {
  symbol: string;
  tf: Timeframe;
  names: string[];
  from?: string;
  to?: string;
  range?: string;
};

export function fetchIndicators(params: IndicatorsParams): Promise<IndicatorsResponse> {
  return chartApiGet<IndicatorsResponse>('/api/indicators', {
    symbol: params.symbol,
    tf: params.tf,
    names: params.names.join(','),
    from: params.from,
    to: params.to,
    range: params.range,
  });
}
