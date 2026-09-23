import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

type CacheEntry<T> = {
  cachedAt: number;
  value: T;
};

type SnapshotStatus = 'error' | 'idle' | 'loading' | 'success';

type UseSnapshotQueryOptions<T> = {
  cacheKey: string;
  enabled?: boolean;
  fetcher: (signal: AbortSignal) => Promise<T>;
  ttlMs?: number;
};

type UseSnapshotQueryResult<T> = {
  data: T | null;
  error: string | null;
  isColdLoading: boolean;
  isRefreshing: boolean;
  refresh: () => void;
  status: SnapshotStatus;
};

const snapshotCache = new Map<string, CacheEntry<unknown>>();
const inFlight = new Map<string, Promise<unknown>>();

function readCache<T>(key: string, ttlMs: number): CacheEntry<T> | null {
  const entry = snapshotCache.get(key) as CacheEntry<T> | undefined;
  if (!entry) return null;
  if (Date.now() - entry.cachedAt > ttlMs) return null;
  return entry;
}

export function useSnapshotQuery<T>({
  cacheKey,
  enabled = true,
  fetcher,
  ttlMs = 30_000,
}: UseSnapshotQueryOptions<T>): UseSnapshotQueryResult<T> {
  const [data, setData] = useState<T | null>(() => readCache<T>(cacheKey, ttlMs)?.value ?? null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<SnapshotStatus>('idle');
  const [pending, setPending] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);
  const seqRef = useRef(0);

  const hasCachedData = useMemo(() => data !== null, [data]);

  const refresh = useCallback(() => {
    setRefreshToken((current) => current + 1);
  }, []);

  useEffect(() => {
    if (!enabled) return undefined;

    const currentSeq = ++seqRef.current;
    const controller = new AbortController();
    const freshCache = readCache<T>(cacheKey, ttlMs);
    if (freshCache && refreshToken === 0) {
      setData(freshCache.value);
      setStatus('success');
    } else {
      setStatus(hasCachedData ? 'success' : 'loading');
    }
    setPending(true);
    setError(null);

    const run = (() => {
      const existing = inFlight.get(cacheKey) as Promise<T> | undefined;
      if (existing) return existing;
      const next = fetcher(controller.signal).finally(() => {
        inFlight.delete(cacheKey);
      });
      inFlight.set(cacheKey, next);
      return next;
    })();

    run
      .then((nextData) => {
        if (controller.signal.aborted || currentSeq !== seqRef.current) return;
        snapshotCache.set(cacheKey, { cachedAt: Date.now(), value: nextData });
        setData(nextData);
        setStatus('success');
        setPending(false);
      })
      .catch((loadError: unknown) => {
        if (controller.signal.aborted || currentSeq !== seqRef.current) return;
        setError(loadError instanceof Error ? loadError.message : String(loadError));
        setStatus(hasCachedData ? 'success' : 'error');
        setPending(false);
      });

    return () => {
      controller.abort();
    };
  }, [cacheKey, enabled, fetcher, hasCachedData, refreshToken, ttlMs]);

  return {
    data,
    error,
    isColdLoading: status === 'loading' && !hasCachedData,
    isRefreshing: pending && hasCachedData,
    refresh,
    status,
  };
}
