import { useEffect, useMemo, useState } from 'react';
import { LocalStrategyScreenerTable } from '../../components/strategy/LocalStrategyScreenerTable';
import { PageHeader } from '../../components/ui/PageHeader';
import { getLocalStrategyRows } from '../../services/static/legacyMarketDataset';
import type { LegacyStaticNavKey } from '../../types';
import { StrategyMigrationLayout } from './StrategyMigrationLayout';
import { StrategyToolbar } from '../../components/strategy/StrategyToolbar';

type LocalStrategyScreenerPageProps = {
  activeNav: Exclude<LegacyStaticNavKey, 'portfolio'>;
  title: string;
};

export function LocalStrategyScreenerPage({ activeNav, title }: LocalStrategyScreenerPageProps) {
  const rows = useMemo(() => getLocalStrategyRows(), []);
  const [search, setSearch] = useState('');
  const [liveLoading, setLiveLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null);
  const [loadTimeMs, setLoadTimeMs] = useState<number | null>(null);
  const activeStrategyPage = activeNav === 'technicals'
    ? '/app/technical/ema'
    : `/app/strategy/${activeNav}`;
  const filteredRows = useMemo(() => {
    const query = search.trim().toUpperCase();
    if (!query) return rows;
    return rows.filter((row) => row.symbol.toUpperCase().includes(query));
  }, [rows, search]);

  useEffect(() => {
    const startedAt = performance.now();
    setLoadTimeMs(Math.max(0, Math.round(performance.now() - startedAt)));
    setLastRefreshedAt(new Date());
  }, []);

  function refetchLocalRows(mode: 'live' | 'refresh') {
    const startedAt = performance.now();
    if (mode === 'live') setLiveLoading(true);
    else setRefreshing(true);
    window.setTimeout(() => {
      setLoadTimeMs(Math.max(0, Math.round(performance.now() - startedAt)));
      setLastRefreshedAt(new Date());
      setLiveLoading(false);
      setRefreshing(false);
    }, 0);
  }

  return (
    <StrategyMigrationLayout activeStrategyPage={activeStrategyPage}>
      <div className="space-y-6">
        <PageHeader title={`${title} Strategy Screener`} />
        <StrategyToolbar
          apiTimeMs={null}
          dbTimeMs={null}
          isLoading={liveLoading || refreshing}
          lastRefreshed={lastRefreshedAt}
          liveLoading={liveLoading}
          loadTimeMs={loadTimeMs}
          ltcDate={null}
          onLiveRefresh={() => refetchLocalRows('live')}
          onRefresh={() => refetchLocalRows('refresh')}
          onSearchChange={setSearch}
          refreshing={refreshing}
          searchValue={search}
          showTotal
          total={filteredRows.length}
        />

        <LocalStrategyScreenerTable rows={filteredRows} />
      </div>
    </StrategyMigrationLayout>
  );
}
