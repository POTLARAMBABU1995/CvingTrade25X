import { fetchStrategyPayload } from './strategyApi';

const PRUDVI_STRATEGY_ENDPOINT = '/api/strategy/prudvi';

export function fetchPrudviStrategyPayload(options: { forceRefresh?: boolean; signal?: AbortSignal } = {}) {
  return fetchStrategyPayload<unknown>(PRUDVI_STRATEGY_ENDPOINT, undefined, {
    forceRefresh: options.forceRefresh,
    signal: options.signal,
  });
}

export function normalizePrudviStrategyError(error: unknown): string {
  const text = error instanceof Error ? error.message : String(error ?? '').trim();
  if (!text || /unexpected token|json|html|failed to fetch|networkerror/i.test(text)) {
    return 'Prudvi strategy scanner is unavailable right now. Please try again.';
  }
  return text;
}
