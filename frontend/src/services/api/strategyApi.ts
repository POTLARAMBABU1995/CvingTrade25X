import { legacyApiGet, legacyApiPost, type QueryParams, type RequestOptions } from '../../api/client';

const STRATEGY_TIMEOUT_MS = 90000;
const STRATEGY_REFRESH_TIMEOUT_MS = 180000;
const STRATEGY_INSERT_TIMEOUT_MS = 180000;
const STRATEGY_AGENT_TIMEOUT_MS = 120000;

export function fetchStrategyPayload<T>(
  endpoint: string,
  params?: QueryParams,
  options: RequestOptions & { forceRefresh?: boolean } = {},
): Promise<T> {
  return legacyApiGet<T>(endpoint, {
    ...params,
    refresh: options.forceRefresh ? 1 : undefined,
  }, {
    signal: options.signal,
    timeoutMs: options.forceRefresh ? STRATEGY_REFRESH_TIMEOUT_MS : options.timeoutMs ?? STRATEGY_TIMEOUT_MS,
  });
}

export function postStrategyRows<T>(
  endpoint: string,
  rows: Array<Record<string, unknown>>,
  options: RequestOptions = {},
): Promise<T> {
  return legacyApiPost<T>(endpoint, { rows, source: 'react-ui' }, {
    signal: options.signal,
    timeoutMs: options.timeoutMs ?? STRATEGY_INSERT_TIMEOUT_MS,
  });
}

export function postYamunaIngest<T>(body: Record<string, unknown>, options: RequestOptions = {}): Promise<T> {
  return legacyApiPost<T>('/api/yamuna/ingest', body, {
    signal: options.signal,
    timeoutMs: options.timeoutMs ?? STRATEGY_INSERT_TIMEOUT_MS,
  });
}

export function fetchStrategyAgentStatus<T>(strategy: string, options: RequestOptions = {}): Promise<T> {
  return legacyApiGet<T>('/api/strategy-agent/status', { strategy }, {
    signal: options.signal,
    timeoutMs: options.timeoutMs ?? STRATEGY_AGENT_TIMEOUT_MS,
  });
}

export function fetchStrategyAgentBacktests<T>(strategy: string, limit = 50, options: RequestOptions = {}): Promise<T> {
  return legacyApiGet<T>('/api/strategy-agent/backtests', { limit, strategy }, {
    signal: options.signal,
    timeoutMs: options.timeoutMs ?? STRATEGY_AGENT_TIMEOUT_MS,
  });
}

export function runStrategyAgent<T>(strategy: string, options: RequestOptions = {}): Promise<T> {
  return legacyApiPost<T>('/api/strategy-agent/run', { source: 'react-ui', strategy }, {
    signal: options.signal,
    timeoutMs: options.timeoutMs ?? STRATEGY_INSERT_TIMEOUT_MS,
  });
}

export function cancelStrategyAgent<T>(strategy: string, jobId?: string, options: RequestOptions = {}): Promise<T> {
  return legacyApiPost<T>('/api/strategy-agent/cancel', { jobId, strategy }, {
    signal: options.signal,
    timeoutMs: options.timeoutMs ?? STRATEGY_INSERT_TIMEOUT_MS,
  });
}
