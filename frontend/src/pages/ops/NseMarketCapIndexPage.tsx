import { useDeferredValue, useEffect, useMemo, useState } from 'react';
import { AppDataTable, type AppDataTableColumn } from '../../components/app/AppDataTable';
import { AppToolbar } from '../../components/app/AppToolbar';
import { ErrorAlertCard } from '../../components/ui/ErrorAlertCard';
import { legacyApiGet } from '../../api/client';
import {
  adaptMarketCapIndexPayload,
  type MarketCapIndexRowView,
  type UnknownRecord,
} from '../../adapters/databasePageAdapter';
import { OpsPageShell } from './OpsPageShell';
import { ActionButton, KpiGrid, PageHero, SearchInput } from './opsPageHelpers';

type LoadStatus = 'error' | 'loading' | 'online';

const columns: Array<AppDataTableColumn<MarketCapIndexRowView>> = [
  { key: 'serialNo', dataCol: 'serialNo', label: 'S.NO', sortType: 'number', getSortValue: (row) => row.serialNo, renderCell: (row) => String(row.serialNo) },
  { key: 'symbol', dataCol: 'symbol', label: 'SYMBOL', sortType: 'string', getSortValue: (row) => row.symbol, renderCell: (row) => row.symbol },
  { key: 'index', dataCol: 'index', label: 'INDEX', sortType: 'string', getSortValue: (row) => row.index, renderCell: (row) => row.index },
  { key: 'mcap', dataCol: 'mcap', label: 'MCAP', sortType: 'number', getSortValue: (row) => row.mcap, renderCell: (row) => row.mcap },
  { key: 'mcapRank', dataCol: 'mcapRank', label: 'MCAP_RANK', sortType: 'number', getSortValue: (row) => row.mcapRank, renderCell: (row) => row.mcapRank },
  { key: 'ltcDate', dataCol: 'ltcDate', label: 'LTC_DATE', sortType: 'date', getSortValue: (row) => row.ltcDate, renderCell: (row) => row.ltcDate },
  { key: 'securityName', dataCol: 'securityName', label: 'SECURITY NAME', sortType: 'string', getSortValue: (row) => row.securityName, renderCell: (row) => row.securityName },
  { key: 'mcapSeries', dataCol: 'mcapSeries', label: 'MCAP SERIES', sortType: 'string', getSortValue: (row) => row.mcapSeries, renderCell: (row) => row.mcapSeries },
];

export function NseMarketCapIndexPage() {
  const [error, setError] = useState('');
  const [payload, setPayload] = useState<UnknownRecord>({});
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState<LoadStatus>('loading');
  const deferredSearch = useDeferredValue(search);

  useEffect(() => {
    const controller = new AbortController();
    setStatus('loading');
    setError('');
    legacyApiGet<UnknownRecord>('/api/marketdata/nse-mcap-index/latest', { refresh: refreshVersion || Date.now() }, {
      signal: controller.signal,
      timeoutMs: 60000,
    }).then((loadedPayload) => {
      setPayload(loadedPayload);
      setStatus('online');
    }).catch(async (primaryError) => {
      if (controller.signal.aborted) return;
      try {
        const fallback = await legacyApiGet<UnknownRecord>('/api/nse-marketcap-index/latest', { refresh: Date.now() }, {
          signal: controller.signal,
          timeoutMs: 60000,
        });
        setPayload(fallback);
        setStatus('online');
      } catch (fallbackError) {
        if (controller.signal.aborted) return;
        const message = fallbackError instanceof Error ? fallbackError.message : primaryError instanceof Error ? primaryError.message : String(fallbackError);
        setError(message);
        setStatus('error');
      }
    });
    return () => controller.abort();
  }, [refreshVersion]);

  const view = useMemo(() => adaptMarketCapIndexPayload(payload), [payload]);
  const filteredRows = useMemo(() => {
    const token = deferredSearch.trim().toLowerCase();
    if (!token) return view.rows;
    return view.rows.filter((row) => [
      row.symbol,
      row.index,
      row.ltcDate,
      row.mcapSeries,
      row.securityName,
    ].some((part) => part.toLowerCase().includes(token)));
  }, [deferredSearch, view.rows]);

  return (
    <OpsPageShell activeDatabasePage="/app/database/nse-market-cap-index" className="mcap-index-react-page">
      <PageHero title="NSE Market Cap Index Classification" />

      <AppToolbar aria-label="NSE Market Cap Index controls">
        <div className="trend-toolbar__item trend-toolbar__item--search">
          <SearchInput value={search} onChange={setSearch} />
        </div>
        <ActionButton disabled={status === 'loading'} onClick={() => setRefreshVersion((current) => current + 1)}>Refresh</ActionButton>
        <span className="count-pill">TOTAL: {filteredRows.length.toLocaleString('en-IN')}</span>
        <span className="count-pill">Latest Date: {view.latestDate}</span>
      </AppToolbar>

      {error ? <ErrorAlertCard message={error} /> : null}

      <KpiGrid items={view.kpis} />

      <section className="card">
        <div className="table-title">
          <h3>NSE Market Cap Index</h3>
          <span className="count-pill">TOTAL: {filteredRows.length.toLocaleString('en-IN')}</span>
        </div>
        <AppDataTable
          columns={columns}
          emptyMessage="No market-cap index rows returned."
          getRowKey={(row, index) => `${row.symbol}-${index}`}
          pageSize={25}
          rows={filteredRows}
          showTopPagination
          tableClassName="data-table--blue"
          tableId="mcapIndexTable"
        />
      </section>
    </OpsPageShell>
  );
}


