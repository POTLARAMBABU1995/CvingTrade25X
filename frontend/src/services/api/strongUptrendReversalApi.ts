import { fetchStrategyPayload } from './strategyApi';

const STRONG_UPTREND_REVERSAL_ENDPOINT = '/api/strategy/strong-uptrend-reversal';

export function fetchStrongUptrendReversalPayload(options: { forceRefresh?: boolean; signal?: AbortSignal } = {}) {
  return fetchStrategyPayload<unknown>(STRONG_UPTREND_REVERSAL_ENDPOINT, undefined, {
    forceRefresh: options.forceRefresh,
    signal: options.signal,
  });
}

export function normalizeStrongUptrendReversalError(error: unknown): string {
  const text = error instanceof Error ? error.message : String(error ?? '').trim();
  if (!text) {
    return 'Strong uptrend scanner is unavailable right now. Please try again.';
  }
  if (/unexpected token|json|html|failed to fetch|networkerror/i.test(text)) {
    return 'Strong uptrend scanner is unavailable right now. Please try again.';
  }
  return text;
}
