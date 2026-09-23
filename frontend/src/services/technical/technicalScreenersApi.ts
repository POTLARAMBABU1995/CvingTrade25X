import { legacyApiGet } from '../../api/client';
import type {
  LegacyTechnicalPayload,
  TechnicalScreenerWireRow,
  TechnicalTimeframe,
  TrendLatestDateWireResponse,
} from '../../types';

export type ScreenerRequestOptions = {
  refresh?: boolean;
  signal?: AbortSignal;
  timeoutMs?: number;
  timeframe?: TechnicalTimeframe;
};

type TechnicalPayload = LegacyTechnicalPayload<TechnicalScreenerWireRow>;

function buildScreenerParams(options: ScreenerRequestOptions) {
  return {
    tf: options.timeframe ?? 'daily',
    refresh: options.refresh ? '1' : undefined,
  };
}

function fetchTechnicalPayload(path: string, options: ScreenerRequestOptions = {}): Promise<TechnicalPayload> {
  return legacyApiGet<TechnicalPayload>(path, buildScreenerParams(options), {
    signal: options.signal,
    timeoutMs: options.timeoutMs ?? 60000,
  });
}

export function fetchTrendLatestDate(refresh = false): Promise<TrendLatestDateWireResponse> {
  return legacyApiGet<TrendLatestDateWireResponse>('/api/trend/latestDate', {
    refresh: refresh ? '1' : undefined,
  }, { timeoutMs: 10000 });
}

export function fetchRsi50Screener(options: ScreenerRequestOptions = {}): Promise<TechnicalPayload> {
  return fetchTechnicalPayload('/api/rsi50', options);
}

export function fetchAdxScreener(options: ScreenerRequestOptions = {}): Promise<TechnicalPayload> {
  return fetchTechnicalPayload('/api/adx', options);
}

export function fetchAtr14Screener(options: ScreenerRequestOptions = {}): Promise<TechnicalPayload> {
  return fetchTechnicalPayload('/api/atr14', options);
}

export function fetchVolumeScreener(options: ScreenerRequestOptions = {}): Promise<TechnicalPayload> {
  return fetchTechnicalPayload('/api/volume', options);
}
