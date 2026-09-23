import { startTransition, useEffect, useState } from 'react';
import { PageHeader } from '../../components/ui/PageHeader';
import { StrongUptrendReversalDashboard } from '../../components/strategy/StrongUptrendReversalDashboard';
import {
  adaptStrongUptrendReversalPayload,
  hasMissingStrongUptrendMarketCap,
  mergeStrongUptrendMarketCapPayload,
} from '../../adapters/strongUptrendReversalAdapter';
import { legacyApiGet } from '../../api/client';
import { fetchStrongUptrendReversalPayload, normalizeStrongUptrendReversalError } from '../../services/api/strongUptrendReversalApi';
import type { StrongUptrendReversalMeta, StrongUptrendReversalRow } from '../../types/strategy/strongUptrendReversal';
import { StrategyMigrationLayout } from './StrategyMigrationLayout';

const EMPTY_META: StrongUptrendReversalMeta = {
  tradingDate: null,
  rows: 0,
};

async function fetchMarketCapIndexPayload(signal?: AbortSignal): Promise<unknown> {
  try {
    return await legacyApiGet('/api/marketdata/nse-mcap-index/latest', { refresh: Date.now() }, {
      signal,
      timeoutMs: 60000,
    });
  } catch (primaryError) {
    if (signal?.aborted) throw primaryError;
    return legacyApiGet('/api/nse-marketcap-index/latest', { refresh: Date.now() }, {
      signal,
      timeoutMs: 60000,
    });
  }
}

export function StrongUptrendReversalPage() {
  const [rows, setRows] = useState<StrongUptrendReversalRow[]>([]);
  const [meta, setMeta] = useState<StrongUptrendReversalMeta>(EMPTY_META);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [liveLoading, setLiveLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null);
  const [loadTimeMs, setLoadTimeMs] = useState<number | null>(null);

  async function load(forceRefresh = false, signal?: AbortSignal, mode: 'initial' | 'live' | 'refresh' = forceRefresh ? 'refresh' : 'initial') {
    setErrorMessage('');
    if (mode === 'live') setLiveLoading(true);
    else if (forceRefresh) setRefreshing(true);
    else setLoading(true);
    const startedAt = performance.now();
    try {
      const rawPayload = await fetchStrongUptrendReversalPayload({ forceRefresh, signal });
      let payload = adaptStrongUptrendReversalPayload(rawPayload);
      if (!signal?.aborted && payload.rows.length && hasMissingStrongUptrendMarketCap(payload.rows)) {
        try {
          const marketCapPayload = await fetchMarketCapIndexPayload(signal);
          payload = adaptStrongUptrendReversalPayload(mergeStrongUptrendMarketCapPayload(rawPayload, marketCapPayload));
        } catch {
          if (signal?.aborted) return;
          // Market-cap enrichment is non-critical; keep the scanner rows visible with '-' fallbacks.
        }
      }
      if (signal?.aborted) return;
      startTransition(() => {
        setRows(payload.rows);
        setMeta(payload.meta);
      });
      setLoadTimeMs(Math.max(0, Math.round(performance.now() - startedAt)));
      setLastRefreshedAt(new Date());
      if (payload.status === 'FAILED' && payload.error) {
        setErrorMessage(payload.error);
      }
    } catch (error) {
      if (signal?.aborted) return;
      setErrorMessage(normalizeStrongUptrendReversalError(error));
      setLoadTimeMs(Math.max(0, Math.round(performance.now() - startedAt)));
      if (!forceRefresh) {
        startTransition(() => {
          setRows([]);
          setMeta(EMPTY_META);
        });
      }
    } finally {
      if (!signal?.aborted) {
        setLoading(false);
        setRefreshing(false);
        setLiveLoading(false);
      }
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    load(false, controller.signal, 'initial');
    return () => controller.abort();
  }, []);

  return (
    <StrategyMigrationLayout activeStrategyPage="/app/strategy/kaveri" fullWidth>
      <div className="space-y-6">
        <PageHeader title="Strong Uptrend Pullback Reversal Scanner" />
        <StrongUptrendReversalDashboard
          errorMessage={errorMessage}
          isLoading={loading}
          isRefreshing={refreshing}
          lastRefreshed={lastRefreshedAt}
          liveLoading={liveLoading}
          loadTimeMs={loadTimeMs}
          meta={meta}
          onLiveRefresh={() => load(false, undefined, 'live')}
          onRefresh={() => load(true, undefined, 'refresh')}
          rows={rows}
        />
      </div>
    </StrategyMigrationLayout>
  );
}
