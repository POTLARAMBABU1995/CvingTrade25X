import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import { legacyApiGet } from '../src/api/client';

type FetchCall = {
  init?: RequestInit;
};

const fetchCalls: FetchCall[] = [];

beforeEach(() => {
  fetchCalls.length = 0;
  vi.useFakeTimers();
  vi.stubGlobal('fetch', vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
    fetchCalls.push({ init });
    return {
      headers: new Headers(),
      json: async () => ({ ok: true }),
      ok: true,
      text: async () => '',
    } as Response;
  }));
});

afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('API client timeout policy', () => {
  test('timeoutMs null keeps only the caller lifecycle signal and creates no timer', async () => {
    const controller = new AbortController();

    await legacyApiGet('/api/test/no-timeout-null', undefined, {
      signal: controller.signal,
      timeoutMs: null,
    });

    expect(fetchCalls[0]?.init?.signal).toBe(controller.signal);
    expect(vi.getTimerCount()).toBe(0);
  });

  test('timeoutMs zero disables the synthetic timeout when no caller signal exists', async () => {
    await legacyApiGet('/api/test/no-timeout-zero', undefined, { timeoutMs: 0 });

    expect(fetchCalls[0]?.init?.signal).toBeUndefined();
    expect(vi.getTimerCount()).toBe(0);
  });

  test('default and positive timeout budgets still create abort signals', async () => {
    await legacyApiGet('/api/test/default-timeout');
    await legacyApiGet('/api/test/positive-timeout', undefined, { timeoutMs: 2500 });

    expect(fetchCalls[0]?.init?.signal).toBeInstanceOf(AbortSignal);
    expect(fetchCalls[1]?.init?.signal).toBeInstanceOf(AbortSignal);
    expect(vi.getTimerCount()).toBe(2);
  });
});
