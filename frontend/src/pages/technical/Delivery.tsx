import { useDeferredValue, useEffect, useMemo, useRef, useState } from 'react';
import { AppPagination } from '../../components/app/AppPagination';
import { LiveStatusPill } from '../../components/app/LiveStatusPill';
import { AppToolbar } from '../../components/app/AppToolbar';
import { TechnicalSearchInput } from '../../components/app/TechnicalSearchInput';
import { CvingLegacyHeader } from '@/components/navigation/CvingLegacyHeader';
import { Button } from '../../components/ui/Button';
import { ErrorAlertCard } from '../../components/ui/ErrorAlertCard';
import { Input } from '../../components/ui/Input';
import {
  adaptDeliveryPayload,
  DELIVERY_COLUMNS,
  type DeliveryViewCell,
} from '../../adapters/deliveryAdapter';
import { formatLocalRefreshTime } from '../../adapters/technicalEmaAdapter';
import { TechnicalMarketCapCell } from '../../components/app/TechnicalMarketCapCell';
import { fetchDeliveryPayload } from '../../services/api/technicalApi';
import type { DeliveryPayloadWire } from '../../types/api/technical';
import { useProtectedPageAuth, useTechnicalThemeMode } from './technicalPageGuards';
import { readUrlSymbolSearch } from '../../utils/urlSymbolSearch';

const PAGE_SIZE = 25;
const DEFAULT_SORT_BY = 'delivery_score';
const DEFAULT_SORT_DIR: 'asc' | 'desc' = 'desc';
const DELIVERY_PCT_THRESHOLDS = [90, 80, 70, 60, 50, 40] as const;
const DELIVERY_SCORE_THRESHOLDS = [100, 90, 80, 70, 60, 50] as const;

type LoadStatus = 'error' | 'loading' | 'online';
type DeliveryPctThreshold = typeof DELIVERY_PCT_THRESHOLDS[number];
type DeliveryScoreThreshold = typeof DELIVERY_SCORE_THRESHOLDS[number];

function toIsoDateInput(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return '';
  if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) return trimmed;
  const normalized = trimmed.replace(/\//g, '-');
  const match = normalized.match(/^(\d{1,2})-(\d{1,2})-(\d{4})$/);
  if (!match) return trimmed;
  const [, d, m, y] = match;
  return `${y}-${m.padStart(2, '0')}-${d.padStart(2, '0')}`;
}

function formatDateDisplay(value: string | null): string {
  if (!value) return '-';
  const parsed = new Date(value.replace(/\//g, '-'));
  if (Number.isNaN(parsed.getTime())) return value;
  const dd = String(parsed.getDate()).padStart(2, '0');
  const mm = String(parsed.getMonth() + 1).padStart(2, '0');
  return `${dd}-${mm}-${parsed.getFullYear()}`;
}

function displayCount(value: number): string {
  return Math.max(0, value).toLocaleString('en-IN');
}

function deliveryCellClass(cell: DeliveryViewCell): string | undefined {
  switch (cell.tone) {
    case 'high':
      return 'delivery-cell--pct-high';
    case 'rising':
      return 'delivery-cell--qty-up';
    case 'scoreHigh':
      return 'delivery-score-badge delivery-score-badge--high';
    case 'scoreMid':
      return 'delivery-score-badge delivery-score-badge--mid';
    default:
      return undefined;
  }
}

export function Delivery() {
  const authorized = useProtectedPageAuth();
  const [search, setSearch] = useState(readUrlSymbolSearch);
  const deferredSearch = useDeferredValue(search);
  const [tradingDate, setTradingDate] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [latestOnly, setLatestOnly] = useState(true);
  const [deliveryPctEq100Only, setDeliveryPctEq100Only] = useState(false);
  const [deliveryPctThreshold, setDeliveryPctThreshold] = useState<DeliveryPctThreshold | null>(null);
  const [deliveryScoreThreshold, setDeliveryScoreThreshold] = useState<DeliveryScoreThreshold | null>(null);
  const [strongOnly, setStrongOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState(DEFAULT_SORT_BY);
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>(DEFAULT_SORT_DIR);
  const [wirePayload, setWirePayload] = useState<DeliveryPayloadWire | null>(null);
  const [status, setStatus] = useState<LoadStatus>('loading');
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState('');
  const [lastRefreshedAtMs, setLastRefreshedAtMs] = useState<number | null>(null);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const forceRefreshRef = useRef(false);
  const themeMode = useTechnicalThemeMode();

  useEffect(() => {
    setPage(1);
  }, [deferredSearch, deliveryPctEq100Only, deliveryPctThreshold, deliveryScoreThreshold, endDate, latestOnly, startDate, strongOnly, tradingDate]);

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

    const minScore = strongOnly ? 71 : deliveryScoreThreshold;
    const startDateIso = toIsoDateInput(startDate);
    const endDateIso = toIsoDateInput(endDate);
    const tradingDateIso = startDateIso || endDateIso ? '' : toIsoDateInput(tradingDate);

    fetchDeliveryPayload({
      page,
      page_size: PAGE_SIZE,
      sort_by: sortBy === 's_no' ? DEFAULT_SORT_BY : sortBy,
      sort_dir: sortDir,
      latest_only: latestOnly ? 'true' : 'false',
      symbol: deferredSearch.trim() ? deferredSearch.trim().toUpperCase() : undefined,
      trading_date: tradingDateIso || undefined,
      start_date: startDateIso || endDateIso || undefined,
      end_date: endDateIso || startDateIso || undefined,
      min_delivery_pct: deliveryPctEq100Only || deliveryPctThreshold === null ? undefined : String(deliveryPctThreshold),
      delivery_pct_eq_100: deliveryPctEq100Only ? 'true' : undefined,
      min_delivery_score: minScore === null ? undefined : String(minScore),
      strong_only: strongOnly ? 'true' : undefined,
    }, { signal: controller.signal })
      .then((payload) => {
        setWirePayload(payload);
        setLastRefreshedAtMs(Date.now());
        setStatus('online');
        if (forceRefresh || payload.refreshing) {
          setToast(`Delivery ${payload.refreshing ? 'refreshing cached data' : 'refreshed'} at ${formatLocalRefreshTime(Date.now())}`);
        }
      })
      .catch((loadError: unknown) => {
        if (controller.signal.aborted) return;
        setWirePayload(null);
        setStatus('error');
        setError(loadError instanceof Error ? loadError.message : String(loadError));
      });

    return () => controller.abort();
  }, [authorized, deferredSearch, deliveryPctEq100Only, deliveryPctThreshold, deliveryScoreThreshold, endDate, latestOnly, page, refreshVersion, sortBy, sortDir, startDate, strongOnly, tradingDate]);

  const payload = useMemo(() => adaptDeliveryPayload(wirePayload, page, PAGE_SIZE), [page, wirePayload]);
  const statusTitle = status === 'online'
    ? `Backend Online${payload.cached ? ' (cached)' : ''}${payload.refreshing ? ' [refreshing]' : ''}`
    : status === 'loading'
      ? 'Loading Delivery...'
      : `Backend Down: ${error ?? 'Unknown error'}`;

  const handleSort = (columnSortBy: string) => {
    setPage(1);
    setSortBy((current) => {
      if (current === columnSortBy) {
        setSortDir((currentDir) => currentDir === 'asc' ? 'desc' : 'asc');
        return current;
      }
      setSortDir(columnSortBy === 'symbol' ? 'asc' : 'desc');
      return columnSortBy;
    });
  };

  const setDateAndDisableLatest = (setter: (value: string) => void, value: string) => {
    setter(value);
    if (value.trim()) setLatestOnly(false);
  };

  const handleCopySymbol = (symbol: string) => {
    if (!navigator.clipboard) return;
    navigator.clipboard.writeText(symbol).then(() => setToast(`Copied: ${symbol}`)).catch(() => undefined);
  };

  if (!authorized) return null;

  return (
    <div className={themeMode === 'dark' ? 'page-theme--technicals ema-page ema-page--dark delivery-react-page' : 'page-theme--technicals ema-page delivery-react-page'}>
      <CvingLegacyHeader activeSection="technicals" activeTechnicalPage="/app/technical/delivery" />

      <main className="container">
        <section className="section-title ema-section-title">
          <h2>Delivery</h2>
          <AppToolbar className="delivery-main-toolbar" aria-label="Delivery controls">
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

            <div className="trend-toolbar__item trend-toolbar__item--actions delivery-toolbar__actions">
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
              <span className="count-pill">TOTAL: {displayCount(payload.totalRecords)}</span>
            </div>
          </AppToolbar>

          <div className="delivery-filter-panel" aria-label="Delivery filters">
            <div className="delivery-date-filter-row">
              <Input className="delivery-date-filter-input" variant="surface" type="text" placeholder="Trading Date DD/MM/YYYY" aria-label="Trading date" value={tradingDate} onChange={(event) => setDateAndDisableLatest(setTradingDate, event.currentTarget.value)} />
              <Input className="delivery-date-filter-input" variant="surface" type="text" placeholder="From Date DD/MM/YYYY" aria-label="From date" value={startDate} onChange={(event) => setDateAndDisableLatest(setStartDate, event.currentTarget.value)} />
              <Input className="delivery-date-filter-input" variant="surface" type="text" placeholder="To Date DD/MM/YYYY" aria-label="To date" value={endDate} onChange={(event) => setDateAndDisableLatest(setEndDate, event.currentTarget.value)} />
            </div>

            <div className="delivery-checkbox-row">
              <label className="delivery-filter-check">
                <input
                  type="checkbox"
                  checked={latestOnly}
                  onChange={(event) => {
                    setLatestOnly(event.currentTarget.checked);
                    if (event.currentTarget.checked) {
                      setTradingDate('');
                      setStartDate('');
                      setEndDate('');
                    }
                  }}
                />
                Latest Date Only
              </label>
              <label className="delivery-filter-check">
                <input
                  type="checkbox"
                  checked={deliveryPctEq100Only}
                  onChange={(event) => {
                    setDeliveryPctEq100Only(event.currentTarget.checked);
                    if (event.currentTarget.checked) setDeliveryPctThreshold(null);
                  }}
                />
                DELIVERY% = 100
              </label>
              {DELIVERY_PCT_THRESHOLDS.map((threshold) => (
                <label className="delivery-filter-check" key={threshold}>
                  <input
                    type="checkbox"
                    checked={deliveryPctThreshold === threshold}
                    onChange={(event) => {
                      setDeliveryPctThreshold(event.currentTarget.checked ? threshold : null);
                      if (event.currentTarget.checked) setDeliveryPctEq100Only(false);
                    }}
                  />
                  DELIVERY% &gt; {threshold}
                </label>
              ))}
              {DELIVERY_SCORE_THRESHOLDS.map((threshold) => (
                <label className="delivery-filter-check" key={`score-${threshold}`}>
                  <input
                    type="checkbox"
                    checked={deliveryScoreThreshold === threshold}
                    onChange={(event) => setDeliveryScoreThreshold(event.currentTarget.checked ? threshold : null)}
                  />
                  DELIVERY_SCORE &gt; {threshold}
                </label>
              ))}
              <label className="delivery-filter-check"><input type="checkbox" checked={strongOnly} onChange={(event) => setStrongOnly(event.currentTarget.checked)} /> Strong Accumulation Only</label>
            </div>
          </div>
        </section>

        <section className="technical-summary-grid delivery-summary-grid" aria-label="Delivery summary">
          <article className="technical-summary-card"><span>Latest LTC_DATE</span><strong>{formatDateDisplay(payload.latestLtcDate)}</strong></article>
          <article className="technical-summary-card"><span>Total Stocks</span><strong>{displayCount(payload.summary.totalStocks)}</strong></article>
          <article className="technical-summary-card"><span>DELIVERY% = 100</span><strong>{displayCount(payload.summary.deliveryPctEq100Count)}</strong></article>
          <article className="technical-summary-card"><span>DELIVERY% &gt; 90</span><strong>{displayCount(payload.summary.deliveryPctGt90Count)}</strong></article>
          <article className="technical-summary-card"><span>DELIVERY% &gt; 80</span><strong>{displayCount(payload.summary.deliveryPctGt80Count)}</strong></article>
          <article className="technical-summary-card"><span>DELIVERY% &gt; 70</span><strong>{displayCount(payload.summary.deliveryPctGt70Count)}</strong></article>
          <article className="technical-summary-card"><span>DELIVERY% &gt; 60</span><strong>{displayCount(payload.summary.deliveryPctGt60Count)}</strong></article>
          <article className="technical-summary-card"><span>DELIVERY% &gt; 50</span><strong>{displayCount(payload.summary.deliveryPctGt50Count)}</strong></article>
          <article className="technical-summary-card"><span>DELIVERY% &gt; 40</span><strong>{displayCount(payload.summary.deliveryPctGt40Count)}</strong></article>
          <article className="technical-summary-card"><span>Strong Accumulation</span><strong>{displayCount(payload.summary.strongAccumulationCount)}</strong></article>
          <article className="technical-summary-card"><span>DELIVERY_SCORE &gt; 100</span><strong>{displayCount(payload.summary.deliveryScoreGt100Count)}</strong></article>
          <article className="technical-summary-card"><span>DELIVERY_SCORE &gt; 90</span><strong>{displayCount(payload.summary.deliveryScoreGt90Count)}</strong></article>
          <article className="technical-summary-card"><span>DELIVERY_SCORE &gt; 80</span><strong>{displayCount(payload.summary.deliveryScoreGt80Count)}</strong></article>
          <article className="technical-summary-card"><span>DELIVERY_SCORE &gt; 70</span><strong>{displayCount(payload.summary.deliveryScoreGt70Count)}</strong></article>
          <article className="technical-summary-card"><span>DELIVERY_SCORE &gt; 60</span><strong>{displayCount(payload.summary.deliveryScoreGt60Count)}</strong></article>
          <article className="technical-summary-card"><span>DELIVERY_SCORE &gt; 50</span><strong>{displayCount(payload.summary.deliveryScoreGt50Count)}</strong></article>
        </section>

        {status === 'error' ? (
          <ErrorAlertCard context="Failed to load delivery data" message={error} />
        ) : null}

        <section className="card">
          <div className="table-title">
            <h3>Delivery</h3>
            <span className="count-pill">PAGE {payload.page.toLocaleString('en-IN')} / {payload.totalPages.toLocaleString('en-IN')}</span>
          </div>
          <AppPagination currentPage={payload.page} totalPages={payload.totalPages} onPageChange={setPage} />
          <div className="table-wrapper">
            <table className="app-data-table table-sticky-safe data-table trend-table data-table--green">
              <colgroup>
                {DELIVERY_COLUMNS.map((column) => (
                  <col key={column.key} data-col={column.key === 'tradingDays' ? 'td' : column.key} />
                ))}
              </colgroup>
              <thead>
                <tr>
                  {DELIVERY_COLUMNS.map((column) => {
                    const active = sortBy === column.sortBy;
                    return (
                      <th
                        key={column.key}
                        data-col={column.key === 'tradingDays' ? 'td' : column.key}
                        data-sort-state={active ? sortDir : 'none'}
                        onClick={() => handleSort(column.sortBy)}
                        scope="col"
                      >
                        {column.label}{active ? sortDir === 'asc' ? ' ^' : ' v' : ''}
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {payload.rows.length ? payload.rows.map((row) => (
                  <tr key={row.id}>
                    {DELIVERY_COLUMNS.map((column) => {
                      const cell = row.cells[column.key] ?? { text: '-', sort: null };
                      const className = deliveryCellClass(cell);
                      const marketCapTone = column.key === 'symbol' || column.key === 'index' || column.key === 'mcap' || column.key === 'mcapRank'
                        ? (cell.marketCapTone === 'large' || cell.marketCapTone === 'mid' || cell.marketCapTone === 'small' || cell.marketCapTone === 'unknown'
                          ? cell.marketCapTone
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
                          ) : className ? <span className={className}>{cell.text}</span> : cell.text}
                        </td>
                      );
                    })}
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={DELIVERY_COLUMNS.length} className="empty">
                      {status === 'loading' ? 'Loading rows...' : 'No delivery data available for selected filters.'}
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
