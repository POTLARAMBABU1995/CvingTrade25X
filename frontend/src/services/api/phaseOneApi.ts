import { chartApiGet, legacyApiGet, type QueryParams } from '../../api/client';
import type { PhaseOnePageId } from '../../data/phaseOneNav';
import { normalizeDisplaySymbol } from '../../utils/symbols';

type ApiKind = 'chart' | 'legacy';

type PhaseOneRequest = {
  key: string;
  kind?: ApiKind;
  label: string;
  params?: QueryParams;
  path: string;
  timeoutMs?: number | null;
};

export type PhaseOneSourceResult = {
  endpoint: string;
  error?: string;
  key: string;
  label: string;
  payload?: unknown;
  status: 'error' | 'online';
};

const DEFAULT_SYMBOL = 'RELIANCE';

function resolvedSymbol(value: string): string {
  return normalizeDisplaySymbol(value) || DEFAULT_SYMBOL;
}

export function buildPhaseOneRequests(pageId: PhaseOnePageId, selectedSymbol = DEFAULT_SYMBOL): PhaseOneRequest[] {
  const symbol = resolvedSymbol(selectedSymbol);
  const daily = { tf: 'daily' } as const;

  switch (pageId) {
    case 'main-dashboard':
      return [
        { key: 'health', label: 'Application health', path: '/api/health', timeoutMs: 5000 },
        { key: 'movers', label: 'Market movers', path: '/api/dashboard/movers', timeoutMs: 15000 },
        { key: 'sync', label: 'Database synchronization', path: '/api/database/sync-status', timeoutMs: 10000 },
      ];
    case 'nifty-50-overview':
      return [
        { key: 'nifty50', label: 'NIFTY 50 movers', path: '/api/nifty50/top-movers', timeoutMs: 15000 },
        { key: 'breadth', label: 'Market breadth', path: '/api/dashboard/movers', timeoutMs: 15000 },
      ];
    case 'sector-rotation':
      return [
        { key: 'overview', label: 'Sector overview', path: '/api/sectors/overview', timeoutMs: 5000 },
        { key: 'sectors', label: 'Sector discovery', path: '/api/sector-rotation/sectors', timeoutMs: 30000 },
      ];
    case 'sector-breadth':
      return [
        { key: 'breadth', label: 'Sector breadth V3', path: '/api/sectors/breadth', params: { version: 'v3' }, timeoutMs: 60000 },
      ];
    case 'opportunity-ranking':
      return [
        {
          key: 'opportunities',
          label: 'Explainable opportunity candidates',
          path: '/api/technicals/strong',
          params: { latest_only: 1, page: 1, page_size: 25, sort_by: 'score', sort_dir: 'desc', tf: 'daily' },
          timeoutMs: 150000,
        },
      ];
    case 'stock-search':
      return [
        { key: 'symbols', kind: 'chart', label: 'Matching securities', path: '/api/symbols', params: { q: symbol }, timeoutMs: 15000 },
      ];
    case 'stock-360':
      return [
        { key: 'bars', kind: 'chart', label: 'Daily OHLCV', path: '/api/bars', params: { symbol, tf: '1D', range: '1y', limit: 260 }, timeoutMs: 30000 },
        { key: 'indicators', kind: 'chart', label: 'Technical indicators', path: '/api/indicators', params: { symbol, tf: '1D', range: '1y', names: 'ema20,ema50,ema100,ema200,rsi14,macd,atr14,adx14' }, timeoutMs: 30000 },
        { key: 'overlays', kind: 'chart', label: 'Research overlays', path: '/api/overlays', params: { symbol, tf: '1D', range: '1y' }, timeoutMs: 30000 },
        { key: 'levels', label: 'Support and resistance', path: '/api/sr-levels', params: { lookback_days: 'max', page: 1, page_size: 25, search: symbol, timeframe: 'daily' }, timeoutMs: 120000 },
      ];
    case 'technical-snapshot':
      return [
        { key: 'indicators', kind: 'chart', label: 'Indicator snapshot', path: '/api/indicators', params: { symbol, tf: '1D', range: '1y', names: 'ema20,ema50,ema100,ema200,rsi14,macd,atr14,adx14' }, timeoutMs: 30000 },
        { key: 'trend', label: 'Trend universe', path: '/api/trend', params: { ...daily }, timeoutMs: 30000 },
      ];
    case 'volume-delivery':
      return [
        { key: 'volume', label: 'Volume participation', path: '/api/volume', params: { ...daily, symbol }, timeoutMs: 60000 },
        { key: 'delivery', label: 'Delivery participation', path: '/api/technicals/delivery', params: { latest_only: 'true', page: 1, page_size: 25, sort_by: 'DELIVERY_SCORE', sort_dir: 'desc', symbol }, timeoutMs: 90000 },
      ];
    case 'support-resistance':
      return [
        { key: 'levels', label: 'Calculated levels', path: '/api/sr-levels', params: { lookback_days: 'max', page: 1, page_size: 25, search: symbol, timeframe: 'daily' }, timeoutMs: 120000 },
        { key: 'manual', label: 'Manual levels', path: '/api/price-action-sr-levels-manually', params: { search: symbol }, timeoutMs: 30000 },
      ];
    case 'historical-behaviour':
      return [
        { key: 'history', label: 'Historical table evidence', path: `/api/historical-data/symbol/${encodeURIComponent(symbol)}`, timeoutMs: 60000 },
        { key: 'bars', kind: 'chart', label: 'Long-window OHLCV', path: '/api/bars', params: { symbol, tf: '1D', range: '5y', limit: 1300 }, timeoutMs: 60000 },
      ];
    case 'data-freshness':
      return [
        { key: 'sync', label: 'Database synchronization', path: '/api/database/sync-status', timeoutMs: 10000 },
        { key: 'trendDate', label: 'Technical latest date', path: '/api/trend/latestDate', timeoutMs: 5000 },
      ];
    case 'data-quality':
      return [
        { key: 'stats', label: 'Stock history statistics', path: '/api/marketdata/stats', params: { source: 'stock_eod_history' }, timeoutMs: 45000 },
        { key: 'sync', label: 'Missing-source checks', path: '/api/database/sync-status', timeoutMs: 10000 },
      ];
    case 'job-monitor':
      return [
        { key: 'nseJob', label: 'NSE automation', path: '/api/automation/nse-marketdata/status', timeoutMs: 10000 },
        { key: 'fyersJob', label: 'FYERS automation', path: '/api/marketdata/fyers/automation/latest-active-job', timeoutMs: null },
      ];
    case 'security-master':
      return [
        { key: 'stockHistorySymbols', label: 'Stock-history symbols', path: '/api/marketdata/symbols', params: { limit: 5000, source: 'stock_eod_history' }, timeoutMs: 30000 },
        { key: 'nseSymbols', label: 'NSE symbols', path: '/api/nse-symbols', timeoutMs: 30000 },
      ];
    case 'user-profile':
      return [
        { key: 'session', label: 'Authenticated session', path: '/api/auth/session', timeoutMs: 10000 },
      ];
    case 'system-settings':
      return [
        { key: 'server', label: 'Server status', path: '/api/server-control/status', timeoutMs: 10000 },
        { key: 'health', label: 'Application health', path: '/api/health', timeoutMs: 5000 },
      ];
    default:
      return [];
  }
}

function errorMessage(error: unknown): string {
  return error instanceof Error && error.message.trim() ? error.message.trim() : 'The source did not return a usable response.';
}

export async function fetchPhaseOneSources(
  pageId: PhaseOnePageId,
  selectedSymbol: string,
  signal?: AbortSignal,
): Promise<PhaseOneSourceResult[]> {
  const requests = buildPhaseOneRequests(pageId, selectedSymbol);
  const responses = await Promise.allSettled(requests.map((request) => {
    const get = request.kind === 'chart' ? chartApiGet : legacyApiGet;
    return get<unknown>(request.path, request.params, {
      diagnostic: {
        action: 'phase-one-read',
        component: 'PhaseOneWorkspacePage',
        page: typeof window === 'undefined'
          ? request.path
          : `${window.location.pathname}${window.location.search}`,
      },
      signal,
      timeoutMs: request.timeoutMs,
    });
  }));

  return responses.map((response, index) => {
    const request = requests[index];
    if (response.status === 'fulfilled') {
      return {
        endpoint: request.path,
        key: request.key,
        label: request.label,
        payload: response.value,
        status: 'online',
      };
    }
    return {
      endpoint: request.path,
      error: errorMessage(response.reason),
      key: request.key,
      label: request.label,
      status: 'error',
    };
  });
}
