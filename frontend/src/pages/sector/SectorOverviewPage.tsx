import { useEffect, useMemo, useState } from 'react';
import { AppDataTable, type AppDataTableColumn } from '../../components/app/AppDataTable';
import { formatSectorDate, formatSectorPrice, sectorTrendClass } from '../../adapters/sectorPageAdapter';
import { StrategyToolbar } from '../../components/strategy/StrategyToolbar';
import {
  fetchDatabaseSyncStatus,
  fetchSectorOverview,
  type SectorOverviewPayload,
  type SectorOverviewRow,
} from '../../services/api/sectorApi';
import { SectorMigrationLayout } from './SectorMigrationLayout';
import { resolveSectorLiveToolbarStatus } from './SectorRotationPage';

type LoadStatus = 'error' | 'loading' | 'online' | 'refreshing';

type OverviewCard = {
  label: string;
  value: number | string;
};

type OverviewTrendFilter = 'Downtrend' | 'Pullback in Uptrend' | 'Sideways' | 'Strong Uptrend' | 'Unknown / Insufficient Data' | 'Uptrend';

type OverviewTableRow = {
  ltcDate: string;
  price: number | null;
  serialNo: number;
  stock: string;
  trend: OverviewTrendFilter;
};

export const STATIC_TREND_ORDER: readonly OverviewTrendFilter[] = [
  'Strong Uptrend',
  'Uptrend',
  'Downtrend',
  'Sideways',
  'Pullback in Uptrend',
  'Unknown / Insufficient Data',
] as const;

const HIDDEN_OVERVIEW_TRENDS = new Set(['Consolidation', 'Insufficient']);
const OVERVIEW_TABLE_PAGE_SIZE = 25;

function toDateToken(value: string | null | undefined): string {
  const match = String(value || '').match(/^(\d{4})-(\d{2})-(\d{2})/);
  return match ? `${match[1]}-${match[2]}-${match[3]}` : '';
}

export function isSectorOverviewOlderThanDev(
  overview: Pick<SectorOverviewPayload, 'source_dev_ltc_date'>,
  devLtcDate: string | null | undefined,
): boolean {
  const overviewDate = toDateToken(overview.source_dev_ltc_date);
  const devDate = toDateToken(devLtcDate);
  return Boolean(overviewDate && devDate && devDate > overviewDate);
}

export function sectorOverviewRequestStatus(refreshVersion: number): LoadStatus {
  return refreshVersion > 0 ? 'refreshing' : 'loading';
}

const EMPTY_OVERVIEW: SectorOverviewPayload = {
  dynamic_trend_counts: {},
  ltc_date: '',
  ltc_date_consistent: true,
  rows: [],
  total_sectors: 0,
  total_stocks: 0,
  trend_counts: {},
};

const DEFAULT_TREND_FILTERS = STATIC_TREND_ORDER.reduce<Record<OverviewTrendFilter, boolean>>((accumulator, trend) => {
  accumulator[trend] = true;
  return accumulator;
}, {} as Record<OverviewTrendFilter, boolean>);

function asCount(value: unknown): number {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

function normalizeOverviewTrendLabel(value: unknown): OverviewTrendFilter {
  const text = String(value ?? '').trim();
  const token = text.toUpperCase();
  if (token.includes('STRONG') && token.includes('UP')) return 'Strong Uptrend';
  if (token.includes('PULLBACK') && token.includes('UP')) return 'Pullback in Uptrend';
  if (token.includes('UP')) return 'Uptrend';
  if (token.includes('DOWN')) return 'Downtrend';
  if (token.includes('SIDEWAY')) return 'Sideways';
  return 'Unknown / Insufficient Data';
}

function countForTrend(payload: SectorOverviewPayload, trend: OverviewTrendFilter): number {
  const trendCounts = payload.trend_counts ?? {};
  if (trend === 'Sideways') {
    return asCount(trendCounts.Sideways) + asCount(trendCounts.Sideway);
  }
  return asCount(trendCounts[trend]);
}

function adaptOverviewRows(rows: SectorOverviewPayload['rows']): OverviewTableRow[] {
  return (rows ?? []).map((row, index) => {
    const entry = row as SectorOverviewRow;
    const numericPrice = Number(entry.price ?? NaN);
    return {
      serialNo: index + 1,
      stock: String(entry.stock ?? '').trim(),
      ltcDate: String(entry.ltc_date ?? '').trim(),
      price: Number.isFinite(numericPrice) ? numericPrice : null,
      trend: normalizeOverviewTrendLabel(entry.trend),
    };
  }).filter((row) => row.stock);
}

export function buildOverviewCards(payload: SectorOverviewPayload): OverviewCard[] {
  const cards: OverviewCard[] = [
    { label: 'Sectors', value: asCount(payload.total_sectors).toLocaleString('en-IN') },
    { label: 'Total', value: asCount(payload.total_stocks).toLocaleString('en-IN') },
    { label: 'LTC_DATE', value: payload.ltc_date ? formatSectorDate(payload.ltc_date) : '-' },
  ];

  STATIC_TREND_ORDER.forEach((trend) => {
    cards.push({
      label: trend,
      value: countForTrend(payload, trend).toLocaleString('en-IN'),
    });
  });

  Object.entries(payload.dynamic_trend_counts ?? {}).forEach(([label, count]) => {
    if (HIDDEN_OVERVIEW_TRENDS.has(label)) return;
    cards.push({
      label,
      value: asCount(count).toLocaleString('en-IN'),
    });
  });

  return cards;
}

function buildStatusMessage(payload: SectorOverviewPayload, error: string, status: LoadStatus): string {
  if (error) return error;
  if (status === 'loading') return 'Loading sector overview metrics...';
  if (!payload.total_sectors && !payload.total_stocks) return 'No sector overview metrics are available.';

  const notes: string[] = [];
  if (status === 'refreshing') {
    notes.push('Refreshing sector overview in the background.');
  }
  if (payload.is_stale) {
    notes.push(`Stale data warning: source=${payload.sector_data_source || 'unknown'}`);
  }
  if (payload.ltc_date && payload.ltc_date_consistent === false) {
    notes.push(`Mixed LTC_DATE values detected (${payload.ltc_date_count || 0} unique dates).`);
  }
  if (payload.generated_at) {
    notes.push(`Generated: ${formatSectorDate(payload.generated_at)}`);
  }
  return notes.join(' | ');
}

function buildDownloadFilename(extension: 'csv' | 'txt'): string {
  const stamp = new Date().toISOString().slice(0, 10);
  return `sector_overview_${stamp}.${extension}`;
}

function triggerDownload(contents: string, filename: string, contentType: string) {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  const blob = new Blob([contents], { type: contentType });
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.URL.revokeObjectURL(url);
}

export function buildOverviewCsv(rows: OverviewTableRow[]): string {
  const header = ['S.NO', 'STOCK', 'LTC_DATE', 'PRICE', 'TREND'];
  const body = rows.map((row) => [
    String(row.serialNo),
    row.stock,
    row.ltcDate,
    row.price === null ? '-' : formatSectorPrice(row.price),
    row.trend,
  ].map((value) => `"${String(value).replace(/"/g, '""')}"`).join(','));
  return [header.join(','), ...body].join('\n');
}

export function buildOverviewTxt(rows: OverviewTableRow[]): string {
  return rows.map((row) => row.stock.trim()).filter(Boolean).join(',');
}

const tableColumns: Array<AppDataTableColumn<OverviewTableRow>> = [
  {
    key: 'S_NO',
    dataCol: 'sno',
    label: 'S.NO',
    sortType: 'number',
    getSortValue: (row) => row.serialNo,
    renderCell: (row) => row.serialNo,
  },
  {
    key: 'STOCK',
    dataCol: 'stock',
    label: 'STOCK',
    sortType: 'string',
    getSortValue: (row) => row.stock,
    renderCell: (row) => row.stock,
  },
  {
    key: 'LTC_DATE',
    dataCol: 'ltc_date',
    label: 'LTC_DATE',
    sortType: 'date',
    getSortValue: (row) => row.ltcDate,
    renderCell: (row) => row.ltcDate || '-',
  },
  {
    key: 'PRICE',
    dataCol: 'price',
    label: 'PRICE',
    sortType: 'number',
    getSortValue: (row) => row.price,
    renderCell: (row) => (row.price === null ? '-' : formatSectorPrice(row.price)),
    cellClassName: (row) => (row.price === null ? undefined : 'text-right'),
  },
  {
    key: 'TREND',
    dataCol: 'trend',
    label: 'TREND',
    sortType: 'string',
    getSortValue: (row) => row.trend,
    renderCell: (row) => <span className={sectorTrendClass({ trend: row.trend, trendSort: row.trend })}>{row.trend}</span>,
  },
];

export function SectorOverviewPage() {
  const [error, setError] = useState('');
  const [overview, setOverview] = useState<SectorOverviewPayload>(EMPTY_OVERVIEW);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState<LoadStatus>('loading');
  const [trendFilters, setTrendFilters] = useState<Record<OverviewTrendFilter, boolean>>(DEFAULT_TREND_FILTERS);

  useEffect(() => {
    const controller = new AbortController();
    const requestStatus = sectorOverviewRequestStatus(refreshVersion);
    setStatus(requestStatus);
    setError('');
    fetchSectorOverview(
      refreshVersion > 0 ? { refresh: 1 } : undefined,
      {
        diagnostic: {
          action: 'GET /api/sectors/overview',
          component: 'SectorOverviewPage',
          page: 'CvingTrade25X - Sector_Overview',
        },
        signal: controller.signal,
      },
    )
      .then((payload) => {
        if (controller.signal.aborted) return;
        setOverview(payload);
        setStatus('online');

        // Keep the fast snapshot-first response, but publish a current overview
        // when the database status proves DEV has advanced to a newer trading day.
        if (refreshVersion === 0) {
          void fetchDatabaseSyncStatus({ signal: controller.signal })
            .then((syncStatus) => {
              if (!controller.signal.aborted && isSectorOverviewOlderThanDev(payload, syncStatus.dev_ltc_date)) {
                setRefreshVersion(1);
              }
            })
            .catch(() => {
              // The persisted overview remains usable if sync-status is unavailable.
            });
        }
      })
      .catch((loadError: unknown) => {
        if (controller.signal.aborted) return;
        setStatus('error');
        setError(loadError instanceof Error ? loadError.message : String(loadError));
        if (requestStatus === 'loading') {
          setOverview(EMPTY_OVERVIEW);
        }
      });
    return () => controller.abort();
  }, [refreshVersion]);

  const cards = useMemo(() => buildOverviewCards(overview), [overview]);
  const overviewRows = useMemo(() => adaptOverviewRows(overview.rows), [overview.rows]);
  const filteredRows = useMemo(() => {
    const token = search.trim().toUpperCase();
    return overviewRows.filter((row) => {
      if (!trendFilters[row.trend]) return false;
      if (!token) return true;
      return row.stock.toUpperCase().includes(token) || row.trend.toUpperCase().includes(token) || row.ltcDate.toUpperCase().includes(token);
    }).map((row, index) => ({
      ...row,
      serialNo: index + 1,
    }));
  }, [overviewRows, search, trendFilters]);
  const statusMessage = buildStatusMessage(overview, error, status);
  const selectedTrendCount = STATIC_TREND_ORDER.filter((trend) => trendFilters[trend]).length;
  const canExport = filteredRows.length > 0;

  function toggleTrendFilter(trend: OverviewTrendFilter) {
    setTrendFilters((current) => ({
      ...current,
      [trend]: !current[trend],
    }));
  }

  function downloadCsv() {
    if (!canExport) return;
    triggerDownload(buildOverviewCsv(filteredRows), buildDownloadFilename('csv'), 'text/csv;charset=utf-8;');
  }

  function downloadTxt() {
    if (!canExport) return;
    triggerDownload(buildOverviewTxt(filteredRows), buildDownloadFilename('txt'), 'text/plain;charset=utf-8;');
  }

  return (
    <SectorMigrationLayout activeSectorPage="/app/sector/overview" className="sector-overview-react-page">
      <StrategyToolbar
        className="sector-overview-toolbar"
        isLoading={status === 'loading'}
        lastRefreshed={overview.generated_at || null}
        ltcDate={overview.ltc_date || null}
        onLive={() => setRefreshVersion((current) => current + 1)}
        onRefresh={() => setRefreshVersion((current) => current + 1)}
        onSearchChange={setSearch}
        refreshing={status === 'loading' || status === 'refreshing'}
        searchPlaceholder="Search Card"
        searchValue={search}
        showTotal
        singleSurface
        status={resolveSectorLiveToolbarStatus(Boolean(error))}
        total={filteredRows.length}
      />

      <div className="sector-compact-page-header">
        <h1 className="sector-compact-page-title">SECTOR_OVERVIEW</h1>
        <div className="sector-compact-controls" aria-label="Sector overview controls">
          <span className="database-badge">ROWS: {filteredRows.length.toLocaleString('en-IN')}</span>
        </div>
      </div>

      {statusMessage ? (
        <p className={error ? 'sector-rotation-page-meta is-error' : 'sector-rotation-page-meta'} aria-live="polite">
          {statusMessage}
        </p>
      ) : null}

      <section className="card sector-overview-card">
        {status === 'loading' ? (
          <div className="sector-overview-state">
            <span className="count-pill">Loading overview cards...</span>
          </div>
        ) : null}

        {status !== 'loading' && !cards.length ? (
          <div className="sector-overview-state">
            <span className="count-pill">No overview cards available.</span>
          </div>
        ) : null}

        {status !== 'loading' && cards.length ? (
          <div className="sector-overview-grid">
            {cards.map((card) => (
              <article
                key={card.label}
                className={`sector-overview-stat${card.label === 'LTC_DATE' ? ' sector-overview-stat--ltc-date' : ''}`}
              >
                <span className="sector-overview-stat__label">{card.label}</span>
                <strong className="sector-overview-stat__value">{card.value}</strong>
              </article>
            ))}
          </div>
        ) : null}
      </section>

      <section className="card sector-overview-card">
        <div className="sector-overview-export-controls">
          <div className="sector-overview-trend-filters" aria-label="Trend filters">
            {STATIC_TREND_ORDER.map((trend) => (
              <label
                key={trend}
                className={`sector-overview-trend-filter ${trendFilters[trend] ? 'is-selected' : ''}`}
              >
                <input
                  checked={trendFilters[trend]}
                  type="checkbox"
                  onChange={() => toggleTrendFilter(trend)}
                />
                <span>{trend}</span>
              </label>
            ))}
          </div>
          <div className="sector-overview-download-actions">
            <button
              className="sector-overview-download-button sector-overview-download-button--txt"
              type="button"
              onClick={downloadTxt}
              disabled={!canExport}
            >
              Download TXT
            </button>
            <button
              className="sector-overview-download-button sector-overview-download-button--csv"
              type="button"
              onClick={downloadCsv}
              disabled={!canExport}
            >
              Download CSV
            </button>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-[18px] border border-slate-700/70 bg-slate-900/40 px-4 py-3 text-sm text-slate-300">
          <span>Selected trends: {selectedTrendCount} of {STATIC_TREND_ORDER.length}</span>
          <span>Filtered stocks: {filteredRows.length.toLocaleString('en-IN')} of {overviewRows.length.toLocaleString('en-IN')}</span>
        </div>

        {status !== 'loading' && !filteredRows.length ? (
          <div className="sector-overview-state mt-4">
            <span className="count-pill">No stocks match the selected trend filters.</span>
          </div>
        ) : null}

        {filteredRows.length ? (
          <div className="mt-4">
            <AppDataTable
              columns={tableColumns}
              emptyMessage="No sector overview rows available."
              getRowKey={(row) => `${row.stock}-${row.ltcDate}-${row.trend}`}
              pageSize={OVERVIEW_TABLE_PAGE_SIZE}
              paginationSummaryLabel="stocks"
              rows={filteredRows}
              tableClassName="data-table--blue"
              tableId="sector-overview-table"
            />
          </div>
        ) : null}
      </section>
    </SectorMigrationLayout>
  );
}
