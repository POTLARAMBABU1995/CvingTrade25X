import { chartApiGet } from './client';
import type { SymbolsResponse } from '../types';

export function fetchSymbols(query: string, options: { limit?: number } = {}): Promise<SymbolsResponse> {
  return chartApiGet<SymbolsResponse>('/api/symbols', { q: query, limit: options.limit });
}
