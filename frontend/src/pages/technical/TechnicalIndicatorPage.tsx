import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from 'react';
import { AppDataTable, type AppDataTableColumn } from '../../components/app/AppDataTable';
import { LiveStatusPill } from '../../components/app/LiveStatusPill';
import { AppToolbar } from '../../components/app/AppToolbar';
import { TechnicalSearchInput } from '../../components/app/TechnicalSearchInput';
import { CvingLegacyHeader } from '@/components/navigation/CvingLegacyHeader';
import { Button } from '../../components/ui/Button';
import { ErrorAlertCard } from '../../components/ui/ErrorAlertCard';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import {
  adaptTechnicalIndicatorPayload,
  filterTechnicalIndicatorRowsBySymbol,
  type IndicatorCellTone,
  type TechnicalIndicatorPageConfig,
  type TechnicalIndicatorViewCell,
  type TechnicalIndicatorViewRow,
} from '../../adapters/technicalIndicatorAdapter';
import {
  TREND_LATEST_DATE_POLL_INTERVAL_MS,
  formatLatestDateDisplay,
  formatLocalRefreshTime,
  normalizeLatestDateKey,
  normalizeTimeframe,
  readLatestDateCache,
  saveLatestDateCache,
} from '../../adapters/technicalEmaAdapter';
import { TechnicalMarketCapCell } from '../../components/app/TechnicalMarketCapCell';
import { useSnapshotQuery } from '../../hooks/useSnapshotQuery';
import { fetchTechnicalIndicatorPayload, fetchTrendLatestDate } from '../../services/api/technicalApi';
import type { TechnicalIndicatorPayloadWire, TechnicalTimeframe } from '../../types/api/technical';
import { useProtectedPageAuth, useTechnicalThemeMode } from './technicalPageGuards';
import { readUrlSymbolSearch } from '../../utils/urlSymbolSearch';

const SYNC_TOAST_VISIBLE_MS = 10000;
const VOLUME_RATIO_THRESHOLDS = [5, 4, 3, 2, 1.5, 1] as const;
const VOLUME_SCORE_THRESHOLDS = [5, 4, 3, 2, 1] as const;

type LoadStatus = 'error' | 'loading' | 'online';
type VolumeRatioThreshold = typeof VOLUME_RATIO_THRESHOLDS[number];
type VolumeScoreThreshold = typeof VOLUME_SCORE_THRESHOLDS[number];
type LatestDateState = {
  fetchedAtMs: number | null;
  key: string | null;
};

function latestStateFromCache(): LatestDateState {
  if (typeof window === 'undefined') {
    return { fetchedAtMs: null, key: null };
  }
  const cached = readLatestDateCache(window.localStorage);
  return {
    fetchedAtMs: cached?.fetchedAtMs ?? null,
    key: cached?.ltcDate ?? null,
  };
}

function cellToneClass(tone?: IndicatorCellTone): string | undefined {
  switch (tone) {
    case 'positive':
      return 'trend-price--up';
    case 'negative':
      return 'trend-price--down';
    case 'large':
      return 'trend-mcap-index-value trend-mcap-index-value--large';
    case 'mid':
      return 'trend-mcap-index-value trend-mcap-index-value--mid';
    case 'small':
      return 'trend-mcap-index-value trend-mcap-index-value--small';
    case 'unknown':
      return 'trend-mcap-index-value trend-mcap-index-value--unknown';
    default:
      return undefined;
  }
}

function TechnicalIndicatorCell({ cell }: { cell: TechnicalIndicatorViewCell }) {
  const className = cellToneClass(cell.tone);
  if (!className) {
    return <>{cell.text}</>;
  }
  return <span className={className}>{cell.text}</span>;
}

function toFiniteNumber(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  const parsed = Number(String(value ?? '').replace(/,/g, '').replace(/%/g, ''));
  return Number.isFinite(parsed) ? parsed : null;
}

function toDateInputKey(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return '';
  if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) return trimmed;
  const normalized = trimmed.replace(/\//g, '-');
  const match = normalized.match(/^(\d{1,2})-(\d{1,2})-(\d{4})$/);
  if (!match) return trimmed;
  const [, d, m, y] = match;
  return `${y}-${m.padStart(2, '0')}-${d.padStart(2, '0')}`;
}

function rowDateKey(row: TechnicalIndicatorViewRow, key: string): string | null {
  const cellText = row.cells[key]?.text;
  if (!cellText || cellText === '-' || cellText === 'N/A') return null;
  return normalizeLatestDateKey(cellText);
}

function rowNumber(row: TechnicalIndicatorViewRow, key: string): number | null {
  return toFiniteNumber(row.cells[key]?.sort ?? row.cells[key]?.text);
}

function latestVolumeDateKey(rows: TechnicalIndicatorViewRow[]): string | null {
  return rows.reduce<string | null>((latest, row) => {
    const key = rowDateKey(row, 'ltcDate');
    return key && (!latest || key > latest) ? key : latest;
  }, null);
}

function formatVolumeDate(value: string | null): string {
  if (!value) return '-';
  const key = normalizeLatestDateKey(value);
  if (!key) return value;
  const [year, month, day] = key.split('-');
  return `${day}-${month}-${year}`;
}

function readAdxThresholdCounts(payload: TechnicalIndicatorPayloadWire | null, rows: TechnicalIndicatorViewRow[]) {
  const thresholdCounts = payload?.meta?.thresholdCounts;
  const meta = thresholdCounts && typeof thresholdCounts === 'object' ? thresholdCounts as Record<string, unknown> : {};
  const adx20 = toFiniteNumber(meta.adx20) ?? rows.filter((row) => {
    const raw = row.raw as Record<string, unknown>;
    return (toFiniteNumber(raw.adxValueSort) ?? toFiniteNumber(raw.adxValue) ?? toFiniteNumber(row.cells.adxGt20?.sort)) !== null;
  }).length;
  const adx25 = toFiniteNumber(meta.adx25) ?? rows.filter((row) => {
    const raw = row.raw as Record<string, unknown>;
    const value = toFiniteNumber(raw.adxValueSort) ?? toFiniteNumber(raw.adxValue) ?? toFiniteNumber(row.cells.adxGt25?.sort);
    return value !== null && value >= 25;
  }).length;

  return { adx20, adx25 };
}

type TechnicalIndicatorPageProps = {
  config: TechnicalIndicatorPageConfig;
};

export function TechnicalIndicatorPage({ config }: TechnicalIndicatorPageProps) {
  const [timeframe, setTimeframe] = useState<TechnicalTimeframe>('daily');
  const [search, setSearch] = useState(readUrlSymbolSearch);
  const deferredSearch = useDeferredValue(search);
  const [wirePayload, setWirePayload] = useState<TechnicalIndicatorPayloadWire | null>(null);
  const authorized = useProtectedPageAuth();
  const [error, setError] = useState<string | null>(null);
  const [syncMessage, setSyncMessage] = useState('');
  const [lastRefreshedAtMs, setLastRefreshedAtMs] = useState<number | null>(null);
  const [latestDate, setLatestDate] = useState<LatestDateState>(() => latestStateFromCache());
  const forceRefreshRef = useRef(false);
  const latestRef = useRef(latestDate);
  const [latestDateVersion, setLatestDateVersion] = useState(0);
  const [volumeTradingDate, setVolumeTradingDate] = useState('');
  const [volumeStartDate, setVolumeStartDate] = useState('');
  const [volumeEndDate, setVolumeEndDate] = useState('');
  const [volumeLatestOnly, setVolumeLatestOnly] = useState(true);
  const [volumeRatioThreshold, setVolumeRatioThreshold] = useState<VolumeRatioThreshold | null>(null);
  const [volumeScoreThreshold, setVolumeScoreThreshold] = useState<VolumeScoreThreshold | null>(null);
  const themeMode = useTechnicalThemeMode();

  useEffect(() => {
    latestRef.current = latestDate;
  }, [latestDate]);

  useEffect(() => {
    if (!syncMessage) return undefined;
    const timeout = window.setTimeout(() => setSyncMessage(''), SYNC_TOAST_VISIBLE_MS);
    return () => window.clearTimeout(timeout);
  }, [syncMessage]);

  useEffect(() => {
    if (!authorized) return undefined;
    let cancelled = false;
    const controller = new AbortController();

    async function syncLatestDate(triggerReload: boolean) {
      try {
        const payload = await fetchTrendLatestDate({ signal: controller.signal });
        const key = normalizeLatestDateKey(payload.ltc_date ?? payload.ltcDate ?? payload.LTC_DATE);
        if (!key || cancelled) return;
        const previous = latestRef.current.key;
        const fetchedAtMs = Date.now();
        saveLatestDateCache(key, fetchedAtMs, window.localStorage);
        setLatestDate({ fetchedAtMs, key });
        if (previous && previous !== key && triggerReload) {
          forceRefreshRef.current = true;
          setLatestDateVersion((current) => current + 1);
        }
      } catch {
        // Metadata polling should not interrupt existing table data flow.
      }
    }

    syncLatestDate(false);
    const interval = window.setInterval(() => syncLatestDate(true), TREND_LATEST_DATE_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      controller.abort();
      window.clearInterval(interval);
    };
  }, [authorized]);

  const fetcher = useCallback(
    (signal: AbortSignal) => fetchTechnicalIndicatorPayload(config.kind, timeframe, { forceRefresh: forceRefreshRef.current, signal }),
    [config.kind, timeframe],
  );
  const snapshot = useSnapshotQuery<TechnicalIndicatorPayloadWire>({
    cacheKey: `technical-indicator:${config.kind}:${timeframe}:${latestDate.key ?? 'na'}:${latestDateVersion}`,
    enabled: authorized,
    fetcher,
    ttlMs: 45_000,
  });

  useEffect(() => {
    setError(snapshot.error);
  }, [snapshot.error]);

  useEffect(() => {
    if (!snapshot.data) return;
    const fetchedAtMs = Date.now();
    const requestedRefresh = forceRefreshRef.current;
    forceRefreshRef.current = false;
    setWirePayload(snapshot.data);
    setLastRefreshedAtMs(fetchedAtMs);
    const payloadLatest = normalizeLatestDateKey(
      snapshot.data.ltc_date
      ?? snapshot.data.latestDate
      ?? snapshot.data.latest_date,
    );
    if (payloadLatest) {
      saveLatestDateCache(payloadLatest, fetchedAtMs, window.localStorage);
      setLatestDate({ fetchedAtMs, key: payloadLatest });
    }
    if (requestedRefresh || snapshot.data.refreshing) {
      setSyncMessage(`${config.heading}: ${snapshot.data.refreshing ? 'refreshing cached data' : 'refreshed'} at ${formatLocalRefreshTime(fetchedAtMs)}`);
    }
  }, [config.heading, snapshot.data]);

  const viewPayload = useMemo(() => adaptTechnicalIndicatorPayload(wirePayload, config.kind), [config.kind, wirePayload]);
  const filteredRows = useMemo(
    () => filterTechnicalIndicatorRowsBySymbol(viewPayload.rows, deferredSearch),
    [deferredSearch, viewPayload.rows],
  );
  const volumeLatestKey = useMemo(() => latestVolumeDateKey(viewPayload.rows), [viewPayload.rows]);
  const volumeDateFilteredRows = useMemo(() => {
    if (config.kind !== 'volume') return filteredRows;
    const tradingDateKey = toDateInputKey(volumeTradingDate);
    const startKey = toDateInputKey(volumeStartDate);
    const endKey = toDateInputKey(volumeEndDate);
    const hasRange = Boolean(startKey || endKey);
    const rangeStart = startKey || endKey;
    const rangeEnd = endKey || startKey;

    return filteredRows.filter((row) => {
      const ltcDate = rowDateKey(row, 'ltcDate');
      const tradingDate = rowDateKey(row, 'tradingDate');
      if (volumeLatestOnly && volumeLatestKey && ltcDate !== volumeLatestKey) return false;
      if (tradingDateKey && ltcDate !== tradingDateKey && tradingDate !== tradingDateKey) return false;
      if (hasRange && (!ltcDate || ltcDate < rangeStart || ltcDate > rangeEnd)) return false;
      return true;
    });
  }, [config.kind, filteredRows, volumeEndDate, volumeLatestKey, volumeLatestOnly, volumeStartDate, volumeTradingDate]);
  const visibleRows = useMemo(() => {
    if (config.kind !== 'volume') return filteredRows;
    return volumeDateFilteredRows.filter((row) => {
      const ratio = rowNumber(row, 'volumeRatio');
      const score = rowNumber(row, 'volumeScore');
      if (volumeRatioThreshold !== null && (ratio === null || ratio <= volumeRatioThreshold)) return false;
      if (volumeScoreThreshold !== null && (score === null || score <= volumeScoreThreshold)) return false;
      return true;
    });
  }, [config.kind, filteredRows, volumeDateFilteredRows, volumeRatioThreshold, volumeScoreThreshold]);
  const volumeSummary = useMemo(() => {
    const rows = config.kind === 'volume' ? volumeDateFilteredRows : [];
    const countBy = (key: string, threshold: number) => rows.filter((row) => {
      const value = rowNumber(row, key);
      return value !== null && value > threshold;
    }).length;
    return {
      latestDate: volumeLatestKey ?? latestDate.key ?? viewPayload.latestLtcDateKey,
      ratioGt1: countBy('volumeRatio', 1),
      ratioGt15: countBy('volumeRatio', 1.5),
      ratioGt2: countBy('volumeRatio', 2),
      ratioGt3: countBy('volumeRatio', 3),
      ratioGt4: countBy('volumeRatio', 4),
      ratioGt5: countBy('volumeRatio', 5),
      scoreGt1: countBy('volumeScore', 1),
      scoreGt2: countBy('volumeScore', 2),
      scoreGt3: countBy('volumeScore', 3),
      scoreGt4: countBy('volumeScore', 4),
      scoreGt5: countBy('volumeScore', 5),
      totalStocks: rows.length,
    };
  }, [config.kind, latestDate.key, viewPayload.latestLtcDateKey, volumeDateFilteredRows, volumeLatestKey]);

  const columns = useMemo<Array<AppDataTableColumn<TechnicalIndicatorViewRow>>>(() => config.columns.map((column) => ({
    cellClassName: (row) => {
      const tone = row.cells[column.key]?.tone;
      return tone === 'large' || tone === 'mid' || tone === 'small' ? 'trend-mcap-cell' : undefined;
    },
    dataCol: column.dataCol ?? column.key,
    getSortValue: (row) => row.cells[column.key]?.sort ?? null,
    key: column.key,
    label: column.label,
    renderCell: (row) => {
      const cell = row.cells[column.key] ?? { text: '-', sort: null };
      if (column.key === 'symbol') {
        const tone = cell.tone === 'large' || cell.tone === 'mid' || cell.tone === 'small' || cell.tone === 'unknown'
          ? cell.tone
          : 'unknown';
        return (
          <TechnicalMarketCapCell
            copyText={cell.text}
            tone={tone}
            onCopy={(value) => {
              if (!navigator.clipboard) return;
              navigator.clipboard.writeText(value).then(() => {
                setSyncMessage(`Copied: ${value}`);
              }).catch(() => undefined);
            }}
          >
            {cell.text}
          </TechnicalMarketCapCell>
        );
      }
      return <TechnicalIndicatorCell cell={cell} />;
    },
    showArrow: column.showArrow,
    sortType: column.sortType,
  })), [config.columns]);

  const status: LoadStatus = snapshot.status === 'error' ? 'error' : snapshot.isColdLoading ? 'loading' : 'online';
  const statusTitle = status === 'online'
    ? `Backend Online${viewPayload.cached ? ' (cached)' : ''}${viewPayload.refreshing ? ' [refreshing]' : ''} [tf:${timeframe}]`
    : status === 'loading'
      ? `Loading ${config.heading} (${timeframe})...`
      : `Backend Down: ${error ?? 'Unknown error'}`;
  const statusLabel = status === 'online' ? 'Live' : status === 'loading' ? 'Syncing' : 'Check';
  const latestMeta = `LTC_DATE: ${formatLatestDateDisplay(latestDate.key ?? viewPayload.latestLtcDateKey)}`;
  const refreshMeta = `Last refreshed: ${formatLocalRefreshTime(lastRefreshedAtMs)}`;
  const totalLabelRows = config.kind === 'volume' ? visibleRows : filteredRows;
  const totalLabel = viewPayload.rows.length > 0 && totalLabelRows.length !== viewPayload.rows.length
    ? `TOTAL: ${totalLabelRows.length.toLocaleString()} / ${viewPayload.rows.length.toLocaleString()}`
    : `TOTAL: ${totalLabelRows.length.toLocaleString()}`;
  const adxCounts = config.kind === 'adx' ? readAdxThresholdCounts(wirePayload, viewPayload.rows) : null;
  const setVolumeDateAndDisableLatest = (setter: (value: string) => void, value: string) => {
    setter(value);
    if (value.trim()) setVolumeLatestOnly(false);
  };

  return (
    <div className={themeMode === 'dark' ? `page-theme--technicals ema-page ema-page--dark technical-indicator-page technical-indicator-page--${config.kind}` : `page-theme--technicals ema-page technical-indicator-page technical-indicator-page--${config.kind}`}>
      <CvingLegacyHeader activeSection="technicals" activeTechnicalPage={config.activeTechnicalPage} />

      <main className="container">
        <section className="section-title ema-section-title">
          <h2>{config.heading}</h2>
          <AppToolbar aria-label={`${config.heading} controls`}>
            <div className="trend-toolbar__item trend-toolbar__item--status">
              <LiveStatusPill state={status === 'online' ? 'live' : status === 'loading' ? 'syncing' : 'stale'} title={statusTitle} label={statusLabel} />
              <div className="trend-toolbar__status-meta" aria-live="polite">
                {syncMessage ? <span className="trend-sync-toast">{syncMessage}</span> : null}
                <span>{latestMeta}</span>
                <span>{refreshMeta}</span>
              </div>
            </div>

            <div className="trend-toolbar__item trend-toolbar__item--search sr-toolbar__group sr-toolbar__group--search">
              <TechnicalSearchInput value={search} onChange={setSearch} />
            </div>

            <div className="trend-toolbar__item trend-toolbar__item--timeframe">
              <Select
                className="sr-select"
                variant="surface"
                aria-label="Timeframe"
                value={timeframe}
                onChange={(event) => setTimeframe(normalizeTimeframe(event.currentTarget.value))}
              >
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
                <option value="monthly">Monthly</option>
                <option value="yearly">Yearly</option>
              </Select>
            </div>

            <div className="trend-toolbar__item trend-toolbar__item--actions">
              <Button
                className="preset-btn"
                variant="secondary"
                type="button"
                disabled={status === 'loading'}
                onClick={() => {
                  forceRefreshRef.current = true;
                  snapshot.refresh();
                }}
              >
                Refresh
              </Button>
              <span className="count-pill">{totalLabel}</span>
              {adxCounts ? (
                <>
                  <span className="count-pill">ADX&gt;20: {adxCounts.adx20.toLocaleString()}</span>
                  <span className="count-pill">ADX&gt;25: {adxCounts.adx25.toLocaleString()}</span>
                </>
              ) : null}
            </div>
          </AppToolbar>

          {config.kind === 'volume' ? (
            <div className="delivery-filter-panel volume-filter-panel" aria-label="Volume filters">
              <div className="delivery-date-filter-row">
                <Input className="delivery-date-filter-input" variant="surface" type="text" placeholder="Trading Date DD/MM/YYYY" aria-label="Trading date" value={volumeTradingDate} onChange={(event) => setVolumeDateAndDisableLatest(setVolumeTradingDate, event.currentTarget.value)} />
                <Input className="delivery-date-filter-input" variant="surface" type="text" placeholder="From Date DD/MM/YYYY" aria-label="From date" value={volumeStartDate} onChange={(event) => setVolumeDateAndDisableLatest(setVolumeStartDate, event.currentTarget.value)} />
                <Input className="delivery-date-filter-input" variant="surface" type="text" placeholder="To Date DD/MM/YYYY" aria-label="To date" value={volumeEndDate} onChange={(event) => setVolumeDateAndDisableLatest(setVolumeEndDate, event.currentTarget.value)} />
              </div>

              <div className="delivery-checkbox-row">
                <label className="delivery-filter-check">
                  <input
                    type="checkbox"
                    checked={volumeLatestOnly}
                    onChange={(event) => {
                      setVolumeLatestOnly(event.currentTarget.checked);
                      if (event.currentTarget.checked) {
                        setVolumeTradingDate('');
                        setVolumeStartDate('');
                        setVolumeEndDate('');
                      }
                    }}
                  />
                  Latest Date Only
                </label>
                {VOLUME_RATIO_THRESHOLDS.map((threshold) => (
                  <label className="delivery-filter-check" key={`ratio-${threshold}`}>
                    <input
                      type="checkbox"
                      checked={volumeRatioThreshold === threshold}
                      onChange={(event) => setVolumeRatioThreshold(event.currentTarget.checked ? threshold : null)}
                    />
                    VOLUME_RATIO &gt; {threshold}
                  </label>
                ))}
                {VOLUME_SCORE_THRESHOLDS.map((threshold) => (
                  <label className="delivery-filter-check" key={`score-${threshold}`}>
                    <input
                      type="checkbox"
                      checked={volumeScoreThreshold === threshold}
                      onChange={(event) => setVolumeScoreThreshold(event.currentTarget.checked ? threshold : null)}
                    />
                    VOLUME_SCORE &gt; {threshold}
                  </label>
                ))}
              </div>
            </div>
          ) : null}
        </section>

        {config.kind === 'volume' ? (
          <section className="technical-summary-grid delivery-summary-grid volume-summary-grid" aria-label="Volume summary">
            <article className="technical-summary-card"><span>Latest LTC_DATE</span><strong>{formatVolumeDate(volumeSummary.latestDate)}</strong></article>
            <article className="technical-summary-card"><span>Total Stocks</span><strong>{volumeSummary.totalStocks.toLocaleString('en-IN')}</strong></article>
            <article className="technical-summary-card"><span>VOLUME_RATIO &gt; 5</span><strong>{volumeSummary.ratioGt5.toLocaleString('en-IN')}</strong></article>
            <article className="technical-summary-card"><span>VOLUME_RATIO &gt; 4</span><strong>{volumeSummary.ratioGt4.toLocaleString('en-IN')}</strong></article>
            <article className="technical-summary-card"><span>VOLUME_RATIO &gt; 3</span><strong>{volumeSummary.ratioGt3.toLocaleString('en-IN')}</strong></article>
            <article className="technical-summary-card"><span>VOLUME_RATIO &gt; 2</span><strong>{volumeSummary.ratioGt2.toLocaleString('en-IN')}</strong></article>
            <article className="technical-summary-card"><span>VOLUME_RATIO &gt; 1.5</span><strong>{volumeSummary.ratioGt15.toLocaleString('en-IN')}</strong></article>
            <article className="technical-summary-card"><span>VOLUME_RATIO &gt; 1</span><strong>{volumeSummary.ratioGt1.toLocaleString('en-IN')}</strong></article>
            <article className="technical-summary-card"><span>VOLUME_SCORE &gt; 5</span><strong>{volumeSummary.scoreGt5.toLocaleString('en-IN')}</strong></article>
            <article className="technical-summary-card"><span>VOLUME_SCORE &gt; 4</span><strong>{volumeSummary.scoreGt4.toLocaleString('en-IN')}</strong></article>
            <article className="technical-summary-card"><span>VOLUME_SCORE &gt; 3</span><strong>{volumeSummary.scoreGt3.toLocaleString('en-IN')}</strong></article>
            <article className="technical-summary-card"><span>VOLUME_SCORE &gt; 2</span><strong>{volumeSummary.scoreGt2.toLocaleString('en-IN')}</strong></article>
            <article className="technical-summary-card"><span>VOLUME_SCORE &gt; 1</span><strong>{volumeSummary.scoreGt1.toLocaleString('en-IN')}</strong></article>
          </section>
        ) : null}

        {status === 'error' ? (
          <ErrorAlertCard context={`Failed to load ${config.heading} data`} message={error} />
        ) : null}

        <section className="card">
          <div className="table-title">
            <h3>{config.tableTitle}</h3>
            <span className="count-pill">TOTAL STOCKS: {filteredRows.length.toLocaleString()}</span>
          </div>
          <AppDataTable
            columns={columns}
            emptyMessage={config.emptyMessage}
            getRowKey={(row, index) => `${row.id}-${index}`}
            pageSize={config.pageSize}
            rows={visibleRows}
            showTopPagination
            tableClassName={config.tableClassName}
            tableId={config.tableId}
          />
        </section>

        <section className="disclaimer disclaimer--light">
          <p>Investments in securities market are subject to market risk, read all the related documents carefully before investing.</p>
          <p>We collect, retain, and use your contact information for legitimate business purposes only, to contact you and provide product and service updates.</p>
          <p>We do not sell or rent your contact information to third parties.</p>
          <p>Please note that by submitting details, you authorize us to call or SMS you even if you are registered under DND for a period of 12 months.</p>
          <p>Copyright@2026-CvingTrade25X - All rights reserved.</p>
        </section>
      </main>
    </div>
  );
}
