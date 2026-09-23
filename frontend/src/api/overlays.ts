import { chartApiGet } from './client';
import type { OverlaysResponse, Timeframe } from '../types';

export type OverlaysParams = {
  symbol: string;
  tf: Timeframe;
  from?: string;
  to?: string;
  range?: string;
};

export function fetchOverlays(params: OverlaysParams): Promise<OverlaysResponse> {
  return chartApiGet<OverlaysResponse>('/api/overlays', {
    symbol: params.symbol,
    tf: params.tf,
    from: params.from,
    to: params.to,
    range: params.range,
  });
}
