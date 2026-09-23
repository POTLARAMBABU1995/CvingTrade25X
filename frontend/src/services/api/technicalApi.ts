import { apiGet, apiPost } from '../../api/client';
import type {
  DeliveryPayloadWire,
  EmaTrendPayloadWire,
  PriceActionManualPayloadWire,
  PriceActionManualSaveResponse,
  SrLevelsPayloadWire,
  TechnicalIndicatorKind,
  TechnicalIndicatorPayloadWire,
  TechnicalScreenerPayloadWire,
  TechnicalTimeframe,
  TrendLatestDateWireResponse,
  TrendPingWireResponse,
  TrendTradingDaysPayloadWire,
} from '../../types/api/technical';

const API_TIMEOUT_MS = 30000;
const LATEST_DATE_TIMEOUT_MS = 5000;
const REFRESH_TIMEOUT_MS = 150000;
const MACD_TIMEOUT_MS = 180000;
const STRONG_TECHNICALS_TIMEOUT_MS = 150000;
const VOLUME_TIMEOUT_MS = 60000;
const SR_LEVELS_TIMEOUT_MS = 120000;
const DELIVERY_TIMEOUT_MS = 90000;

const INDICATOR_ENDPOINTS = {
  adx: '/api/adx',
  atr14: '/api/atr14',
  macd: '/api/momentum/macd',
  rsi50: '/api/rsi50',
  volume: '/api/volume',
} satisfies Record<TechnicalIndicatorKind, string>;

export type TechnicalScreenerQuery = {
  tf: TechnicalTimeframe;
  page: number;
  page_size: number;
  latest_only: 1;
  sort_by: string;
  sort_dir: 'asc' | 'desc';
  symbol?: string;
  min_score?: string;
  pattern?: string;
  breakout_flag?: string;
  breakout_status?: string;
  trendline_status?: string;
  risk_level?: string;
  refresh?: 1;
};

export type SrLevelsQuery = {
  timeframe: TechnicalTimeframe;
  lookback_days: 'max';
  page: number;
  page_size: number;
  price_action?: string;
  refresh?: 1;
  search?: string;
  symbols?: string;
  tolerance?: string;
  trend_direction?: string;
};

export type DeliveryQuery = {
  page: number;
  page_size: number;
  sort_by: string;
  sort_dir: 'asc' | 'desc';
  latest_only: 'true' | 'false';
  symbol?: string;
  trading_date?: string;
  start_date?: string;
  end_date?: string;
  min_delivery_pct?: string;
  delivery_pct_eq_100?: 'true';
  min_delivery_score?: string;
  strong_only?: 'true';
};

export function fetchEmaTrendPayload(
  timeframe: TechnicalTimeframe,
  options: { forceRefresh?: boolean; signal?: AbortSignal } = {},
): Promise<EmaTrendPayloadWire> {
  return apiGet<EmaTrendPayloadWire>(
    '/api/trend',
    {
      tf: timeframe,
      refresh: options.forceRefresh ? 1 : undefined,
    },
    {
      signal: options.signal,
      timeoutMs: options.forceRefresh ? REFRESH_TIMEOUT_MS : API_TIMEOUT_MS,
    },
  );
}

export function fetchTrendTradingDays(
  timeframe: TechnicalTimeframe,
  options: { forceRefresh?: boolean; signal?: AbortSignal } = {},
): Promise<TrendTradingDaysPayloadWire> {
  return apiGet<TrendTradingDaysPayloadWire>(
    '/api/trend/trading-days',
    {
      tf: timeframe,
      refresh: options.forceRefresh ? 1 : undefined,
    },
    {
      signal: options.signal,
      timeoutMs: API_TIMEOUT_MS,
    },
  );
}

export function fetchTrendLatestDate(options: { signal?: AbortSignal } = {}): Promise<TrendLatestDateWireResponse> {
  return apiGet<TrendLatestDateWireResponse>('/api/trend/latestDate', undefined, {
    signal: options.signal,
    timeoutMs: LATEST_DATE_TIMEOUT_MS,
  });
}

export function pingTrendBackend(options: { signal?: AbortSignal } = {}): Promise<TrendPingWireResponse> {
  return apiGet<TrendPingWireResponse>('/api/trend/ping', undefined, {
    signal: options.signal,
    timeoutMs: LATEST_DATE_TIMEOUT_MS,
  });
}

export function fetchTechnicalIndicatorPayload(
  kind: TechnicalIndicatorKind,
  timeframe: TechnicalTimeframe,
  options: { forceRefresh?: boolean; signal?: AbortSignal; timeoutMs?: number | null } = {},
): Promise<TechnicalIndicatorPayloadWire> {
  const defaultTimeoutMs = kind === 'macd'
    ? MACD_TIMEOUT_MS
    : kind === 'volume'
      ? VOLUME_TIMEOUT_MS
    : options.forceRefresh ? REFRESH_TIMEOUT_MS : API_TIMEOUT_MS;

  return apiGet<TechnicalIndicatorPayloadWire>(
    INDICATOR_ENDPOINTS[kind],
    {
      tf: timeframe,
      refresh: options.forceRefresh ? 1 : undefined,
    },
    {
      signal: options.signal,
      timeoutMs: options.timeoutMs ?? defaultTimeoutMs,
    },
  );
}

export function fetchTechnicalScreenerPayload(
  endpoint: string,
  params: TechnicalScreenerQuery,
  options: { signal?: AbortSignal; timeoutMs?: number | null } = {},
): Promise<TechnicalScreenerPayloadWire> {
  return apiGet<TechnicalScreenerPayloadWire>(endpoint, params, {
    signal: options.signal,
    timeoutMs: options.timeoutMs ?? STRONG_TECHNICALS_TIMEOUT_MS,
  });
}

export function fetchPriceActionManualPayload(options: { signal?: AbortSignal; search?: string } = {}): Promise<PriceActionManualPayloadWire> {
  return apiGet<PriceActionManualPayloadWire>('/api/price-action-sr-levels-manually', options.search ? { search: options.search } : undefined, {
    signal: options.signal,
    timeoutMs: API_TIMEOUT_MS,
  });
}

export function fetchSrLevelsPayload(params: SrLevelsQuery, options: { signal?: AbortSignal; timeoutMs?: number | null } = {}): Promise<SrLevelsPayloadWire> {
  return apiGet<SrLevelsPayloadWire>('/api/sr-levels', params, {
    signal: options.signal,
    timeoutMs: options.timeoutMs ?? SR_LEVELS_TIMEOUT_MS,
  });
}

export function fetchDeliveryPayload(params: DeliveryQuery, options: { signal?: AbortSignal; timeoutMs?: number | null } = {}): Promise<DeliveryPayloadWire> {
  return apiGet<DeliveryPayloadWire>('/api/technicals/delivery', params, {
    signal: options.signal,
    timeoutMs: options.timeoutMs ?? DELIVERY_TIMEOUT_MS,
  });
}

export function savePriceActionManualPayload(
  body: Record<string, unknown>,
  options: { signal?: AbortSignal } = {},
): Promise<PriceActionManualSaveResponse> {
  return apiPost<PriceActionManualSaveResponse>('/api/price-action-sr-levels-manually', body, {
    signal: options.signal,
    timeoutMs: API_TIMEOUT_MS,
  });
}
