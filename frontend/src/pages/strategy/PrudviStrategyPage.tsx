import { startTransition, useDeferredValue, useEffect, useMemo, useState } from 'react';
import { PageHeader } from '../../components/ui/PageHeader';
import { PrudviStrategyTable } from '../../components/strategy/PrudviStrategyTable';
import {
  adaptPrudviStrategyPayload,
  calculatePrudviKpiCounts,
  filterPrudviRows,
  isStrongPrudviUptrendRow,
  prioritizePrudviRowsForDisplay,
} from '../../adapters/prudviStrategyAdapter';
import { fetchPrudviStrategyPayload, normalizePrudviStrategyError } from '../../services/api/prudviStrategyApi';
import type { PrudviStrategyFilters, PrudviStrategyMeta, PrudviStrategyRow } from '../../types/strategy/prudvi';
import { StrategyMigrationLayout } from './StrategyMigrationLayout';
import { StrategyToolbar, type StrategyToolbarStatus } from '../../components/strategy/StrategyToolbar';

const EMPTY_META: PrudviStrategyMeta = {
  rows: 0,
  tradingDate: null,
};

const DEFAULT_FILTERS: PrudviStrategyFilters = {
  minimumScore: '',
  search: '',
  trend: 'ALL',
};

export function PrudviStrategyPage() {
  const [rows, setRows] = useState<PrudviStrategyRow[]>([]);
  const [meta, setMeta] = useState<PrudviStrategyMeta>(EMPTY_META);
  const [filters, setFilters] = useState<PrudviStrategyFilters>(DEFAULT_FILTERS);
  const [strongUptrendOnly, setStrongUptrendOnly] = useState(false);
  const deferredSearch = useDeferredValue(filters.search);
  const deferredFilters = useMemo(() => ({
    ...filters,
    search: deferredSearch,
  }), [deferredSearch, filters]);
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
      const rawPayload = await fetchPrudviStrategyPayload({ forceRefresh, signal });
      const payload = adaptPrudviStrategyPayload(rawPayload);
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
      setErrorMessage(normalizePrudviStrategyError(error));
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

  const kpiCounts = useMemo(() => calculatePrudviKpiCounts(rows), [rows]);
  const filteredRows = useMemo(() => filterPrudviRows(rows, deferredFilters), [deferredFilters, rows]);
  const displayRows = useMemo(() => {
    const prioritizedRows = prioritizePrudviRowsForDisplay(filteredRows);
    if (!strongUptrendOnly) return prioritizedRows;
    return prioritizedRows.filter(isStrongPrudviUptrendRow);
  }, [filteredRows, strongUptrendOnly]);
  const toolbarStatus: StrategyToolbarStatus = loading || refreshing || liveLoading || meta.refreshing
    ? 'syncing'
    : errorMessage
      ? 'error'
      : meta.stale
        ? 'stale'
        : lastRefreshedAt
          ? 'live'
          : 'idle';

  return (
    <StrategyMigrationLayout activeStrategyPage="/app/strategy/prudvi" fullWidth>
      <div className="space-y-4">
        <PageHeader title="Prudvi - Bullish Candlestick Support Reversal Strategy" />
        <StrategyToolbar
          apiTimeMs={meta.durationMs ?? null}
          dbTimeMs={null}
          isLoading={loading || refreshing || liveLoading}
          lastRefreshed={lastRefreshedAt}
          liveLoading={liveLoading}
          loadTimeMs={loadTimeMs}
          ltcDate={meta.tradingDate}
          status={toolbarStatus}
          onLiveRefresh={() => load(false, undefined, 'live')}
          onRefresh={() => load(true, undefined, 'refresh')}
          onSearchChange={(value) => setFilters((current) => ({ ...current, search: value }))}
          refreshing={refreshing}
          searchValue={filters.search}
          showTotal
          total={meta.rows || rows.length}
        />
        <PrudviStrategyTable
          errorMessage={errorMessage}
          externalToolbar
          filters={filters}
          isLoading={loading}
          isRefreshing={refreshing || liveLoading}
          kpiCounts={kpiCounts}
          onFiltersChange={setFilters}
          onRefresh={() => load(true, undefined, 'refresh')}
          onStrongUptrendOnlyChange={setStrongUptrendOnly}
          rows={displayRows}
          strongUptrendOnly={strongUptrendOnly}
          totalRows={meta.rows || rows.length}
        />
      </div>
    </StrategyMigrationLayout>
  );
}
