import { useDeferredValue, useEffect, useMemo, useRef, useState } from 'react';
import { AppPagination } from '../../components/app/AppPagination';
import { type AppSortState, getNextSortState, sortRowsForTable } from '../../components/app/AppDataTable';
import { LiveStatusPill } from '../../components/app/LiveStatusPill';
import { AppToolbar } from '../../components/app/AppToolbar';
import { TechnicalSearchInput } from '../../components/app/TechnicalSearchInput';
import { CvingLegacyHeader } from '@/components/navigation/CvingLegacyHeader';
import { Button } from '../../components/ui/Button';
import { ErrorAlertCard } from '../../components/ui/ErrorAlertCard';
import { Select } from '../../components/ui/Select';
import {
  adaptSrLevelsPayload,
  SR_LEVELS_COLUMNS,
  type SrLevelsViewRow,
} from '../../adapters/srLevelsAdapter';
import { formatLocalRefreshTime, normalizeTimeframe } from '../../adapters/technicalEmaAdapter';
import { TechnicalMarketCapCell } from '../../components/app/TechnicalMarketCapCell';
import { fetchSrLevelsPayload } from '../../services/api/technicalApi';
import type { SrLevelsPayloadWire, TechnicalTimeframe } from '../../types/api/technical';
import { useProtectedPageAuth, useTechnicalThemeMode } from './technicalPageGuards';

const PAGE_SIZE = 25;

type LoadStatus = 'error' | 'loading' | 'online';

const PRICE_ACTION_OPTIONS = [
  { label: 'All Price Action', value: 'all' },
  { label: 'Breakout', value: 'breakout' },
  { label: 'Breakdown', value: 'breakdown' },
  { label: 'Bullish Rejection', value: 'bullish_rejection' },
  { label: 'Bearish Rejection', value: 'bearish_rejection' },
  { label: 'Bullish Engulfing', value: 'bullish_engulfing' },
  { label: 'Bearish Engulfing', value: 'bearish_engulfing' },
  { label: 'Inside Bar', value: 'inside_bar' },
  { label: 'Range', value: 'range' },
  { label: 'Neutral', value: 'neutral' },
];

const TREND_OPTIONS = [
  { label: 'All Trends', value: 'all' },
  { label: 'Uptrend', value: 'uptrend' },
  { label: 'Downtrend', value: 'downtrend' },
  { label: 'Consolidation', value: 'consolidation' },
];

function displayCount(value: number): string {
  return Math.max(0, value).toLocaleString('en-IN');
}

export function SupportResistance() {
  const authorized = useProtectedPageAuth();
  const [timeframe, setTimeframe] = useState<TechnicalTimeframe>('daily');
  const [search, setSearch] = useState('');
  const deferredSearch = useDeferredValue(search);
  const [priceAction, setPriceAction] = useState('all');
  const [trendDirection, setTrendDirection] = useState('all');
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState<AppSortState>({ key: 'score', direction: 'desc' });
  const [wirePayload, setWirePayload] = useState<SrLevelsPayloadWire | null>(null);
  const [status, setStatus] = useState<LoadStatus>('loading');
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState('');
  const [lastRefreshedAtMs, setLastRefreshedAtMs] = useState<number | null>(null);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const forceRefreshRef = useRef(true);
  const themeMode = useTechnicalThemeMode();

  useEffect(() => {
    setPage(1);
  }, [deferredSearch, priceAction, timeframe, trendDirection]);

  useEffect(() => {
    if (!toast) return undefined;
    const timeout = window.setTimeout(() => setToast(''), 8000);
    return () => window.clearTimeout(timeout);
  }, [toast]);

  useEffect(() => {
    if (!authorized) return undefined;
    const controller = new AbortController();
    const forceRefresh = forceRefreshRef.current;
    forceRefreshRef.current = false;
    setStatus('loading');
    setError(null);

    fetchSrLevelsPayload({
      timeframe,
      lookback_days: 'max',
      page,
      page_size: PAGE_SIZE,
      price_action: priceAction === 'all' ? undefined : priceAction,
      refresh: forceRefresh ? 1 : undefined,
      search: deferredSearch.trim() ? deferredSearch.trim().toUpperCase() : undefined,
      trend_direction: trendDirection === 'all' ? undefined : trendDirection,
    }, { signal: controller.signal })
      .then((payload) => {
        setWirePayload(payload);
        setLastRefreshedAtMs(Date.now());
        setStatus('online');
        if (forceRefresh) setToast(`Support & Resistance refreshed at ${formatLocalRefreshTime(Date.now())}`);
      })
      .catch((loadError: unknown) => {
        if (controller.signal.aborted) return;
        setWirePayload(null);
        setStatus('error');
        setError(loadError instanceof Error ? loadError.message : String(loadError));
      });

    return () => controller.abort();
  }, [authorized, deferredSearch, page, priceAction, refreshVersion, timeframe, trendDirection]);

  const payload = useMemo(() => adaptSrLevelsPayload(wirePayload, page, PAGE_SIZE), [page, wirePayload]);
  const sortColumns = useMemo(() => SR_LEVELS_COLUMNS.map((column) => ({
    getSortValue: (row: SrLevelsViewRow) => row.cells[column.key]?.sort ?? null,
    key: column.key,
    sortType: column.sortType,
  })), []);
  const sortedRows = useMemo(() => sortRowsForTable(payload.rows, sortColumns, sort), [payload.rows, sort, sortColumns]);
  const handleSortChange = (key: string, sortType: 'date' | 'number' | 'string') => {
    setPage(1);
    setSort((current) => getNextSortState(current, key, sortType));
  };

  const statusTitle = status === 'online'
    ? `Backend Online [tf:${timeframe}]`
    : status === 'loading'
      ? `Loading Price Action SR (${timeframe})...`
      : `Backend Down: ${error ?? 'Unknown error'}`;

  const handleCopySymbol = (symbol: string) => {
    if (!navigator.clipboard) return;
    navigator.clipboard.writeText(symbol).then(() => setToast(`Copied: ${symbol}`)).catch(() => undefined);
  };

  if (!authorized) return null;

  return (
    <div className={themeMode === 'dark' ? 'page-theme--technicals ema-page ema-page--dark support-resistance-page' : 'page-theme--technicals ema-page support-resistance-page'}>
      <CvingLegacyHeader activeSection="technicals" activeTechnicalPage="/app/technical/support-resistance" />

      <main className="container">
        <section className="section-title ema-section-title">
          <h2>Price Action SR</h2>
          <AppToolbar aria-label="Price Action SR controls">
            <div className="trend-toolbar__item trend-toolbar__item--status">
              <LiveStatusPill state={status === 'online' ? 'live' : status === 'loading' ? 'syncing' : 'stale'} title={statusTitle} />
              <div className="trend-toolbar__status-meta" aria-live="polite">
                {toast ? <span className="trend-sync-toast">{toast}</span> : null}
                <span>Last refreshed: {formatLocalRefreshTime(lastRefreshedAtMs)}</span>
              </div>
            </div>

            <div className="trend-toolbar__item trend-toolbar__item--search sr-toolbar__group sr-toolbar__group--search">
              <TechnicalSearchInput value={search} onChange={setSearch} />
            </div>

            <Select className="sr-select" variant="surface" aria-label="Timeframe" value={timeframe} onChange={(event) => setTimeframe(normalizeTimeframe(event.currentTarget.value))}>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
              <option value="yearly">Yearly</option>
            </Select>

            <Select className="sr-select" variant="surface" aria-label="Price action" value={priceAction} onChange={(event) => setPriceAction(event.currentTarget.value)}>
              {PRICE_ACTION_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </Select>

            <Select className="sr-select" variant="surface" aria-label="Trend direction" value={trendDirection} onChange={(event) => setTrendDirection(event.currentTarget.value)}>
              {TREND_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </Select>

            <Button
              className="preset-btn"
              variant="secondary"
              type="button"
              disabled={status === 'loading'}
              onClick={() => {
                forceRefreshRef.current = true;
                setRefreshVersion((current) => current + 1);
              }}
            >
              Refresh
            </Button>
            <span className="count-pill">TOTAL: {displayCount(payload.totalRows)}</span>
          </AppToolbar>
        </section>

        <section className="technical-summary-grid support-resistance-counts" aria-label="Trend counts">
          <article className="technical-summary-card"><span>Uptrend</span><strong>{displayCount(payload.trendCounts.uptrend)}</strong></article>
          <article className="technical-summary-card"><span>Downtrend</span><strong>{displayCount(payload.trendCounts.downtrend)}</strong></article>
          <article className="technical-summary-card"><span>Consolidation</span><strong>{displayCount(payload.trendCounts.consolidation)}</strong></article>
          <article className="technical-summary-card"><span>Total</span><strong>{displayCount(payload.trendCounts.total)}</strong></article>
        </section>

        {status === 'error' ? (
          <ErrorAlertCard context="Failed to load Price Action SR data" message={error} />
        ) : null}

        <section className="card">
          <div className="table-title">
            <h3>Price Action SR</h3>
            <span className="count-pill">PAGE {payload.page.toLocaleString('en-IN')} / {payload.totalPages.toLocaleString('en-IN')}</span>
          </div>
          <AppPagination currentPage={payload.page} totalPages={payload.totalPages} onPageChange={setPage} />
          <div className="table-wrapper">
            <table className="app-data-table table-sticky-safe data-table trend-table data-table--blue">
              <colgroup>
                {SR_LEVELS_COLUMNS.map((column) => (
                  <col key={column.key} data-col={column.key === 'tradingDays' ? 'td' : column.key} />
                ))}
              </colgroup>
              <thead>
                <tr>
                  {SR_LEVELS_COLUMNS.map((column) => {
                    const active = sort.key === column.key && sort.direction;
                    return (
                      <th
                        key={column.key}
                        data-col={column.key === 'tradingDays' ? 'td' : column.key}
                        data-sort-state={active ? sort.direction ?? 'none' : 'none'}
                        onClick={() => handleSortChange(column.key, column.sortType)}
                        scope="col"
                      >
                        {column.label}{active ? sort.direction === 'asc' ? ' ^' : ' v' : ''}
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {sortedRows.length ? sortedRows.map((row) => (
                  <tr key={row.id}>
                    {SR_LEVELS_COLUMNS.map((column) => {
                      const cell = row.cells[column.key] ?? { text: '-', sort: null };
                      const marketCapTone = column.key === 'symbol' || column.key === 'index' || column.key === 'mcap' || column.key === 'mcapRank'
                        ? (cell.tone === 'large' || cell.tone === 'mid' || cell.tone === 'small' || cell.tone === 'unknown'
                          ? cell.tone
                          : 'unknown')
                        : undefined;
                      return (
                        <td key={column.key} data-col={column.key === 'tradingDays' ? 'td' : column.key}>
                          {column.key === 'symbol' ? (
                            <TechnicalMarketCapCell
                              copyText={cell.text}
                              tone={marketCapTone}
                              onCopy={(value) => handleCopySymbol(value)}
                            >
                              {cell.text}
                            </TechnicalMarketCapCell>
                          ) : marketCapTone ? (
                            <TechnicalMarketCapCell tone={marketCapTone}>
                              {cell.text}
                            </TechnicalMarketCapCell>
                          ) : cell.text}
                        </td>
                      );
                    })}
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={SR_LEVELS_COLUMNS.length} className="empty">
                      {status === 'loading' ? 'Loading rows...' : 'No support/resistance rows found for selected filters.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <AppPagination currentPage={payload.page} totalPages={payload.totalPages} onPageChange={setPage} />
        </section>
      </main>
    </div>
  );
}
