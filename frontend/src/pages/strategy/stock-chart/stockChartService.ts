import { chartApiGet } from '@/api/client';
import type { ChartOhlcvPayload, ChartWatchlistPayload, StockChartTimeframe } from './chartTypes';

const API_TIMEOUT_MS = 60_000;

type WrappedPayload<T> = T & { data?: T };

function unwrapPayload<T>(payload: T | WrappedPayload<T>): T {
  if (payload && typeof payload === 'object' && 'data' in payload) {
    const wrapped = payload as WrappedPayload<T>;
    if (wrapped.data && typeof wrapped.data === 'object') {
      return wrapped.data;
    }
  }
  return payload as T;
}

export async function fetchStockChartOhlcv(
  symbol: string,
  timeframe: StockChartTimeframe,
  signal: AbortSignal,
): Promise<ChartOhlcvPayload> {
  const payload = await chartApiGet<ChartOhlcvPayload | WrappedPayload<ChartOhlcvPayload>>(
    '/api/chart/ohlcv',
    { symbol, timeframe },
    {
      diagnostic: {
        action: 'stock-chart-ohlcv',
        component: 'StockChartPage',
      },
      signal,
      timeoutMs: API_TIMEOUT_MS,
    },
  );
  return unwrapPayload(payload);
}

export async function fetchStockChartWatchlist(signal: AbortSignal): Promise<ChartWatchlistPayload> {
  const payload = await chartApiGet<ChartWatchlistPayload | WrappedPayload<ChartWatchlistPayload>>(
    '/api/chart/watchlist',
    undefined,
    {
      diagnostic: {
        action: 'stock-chart-watchlist',
        component: 'StockChartPage',
      },
      signal,
      timeoutMs: API_TIMEOUT_MS,
    },
  );
  return unwrapPayload(payload);
}