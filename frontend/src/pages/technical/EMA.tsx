import { useDeferredValue, useEffect, useMemo, useRef, useState } from 'react';
import { AppDataTable, type AppDataTableColumn } from '../../components/app/AppDataTable';
import { LiveStatusPill } from '../../components/app/LiveStatusPill';
import { AppToolbar } from '../../components/app/AppToolbar';
import { CvingLegacyHeader } from '@/components/navigation/CvingLegacyHeader';
import { Button } from '../../components/ui/Button';
import { ErrorAlertCard } from '../../components/ui/ErrorAlertCard';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import {
  EMA_DOWNLOAD_TENURE_OPTIONS,
  EMA_PAGE_SIZE,
  EMA_TABLE_CONFIGS,
  EMA_TABLE_KEYS,
  TREND_LATEST_DATE_POLL_INTERVAL_MS,
  TREND_TIMEFRAME_STORAGE_KEY,
  adaptEmaTrendRow,
  adaptEmaTrendPayload,
  buildEmaColumns,
  buildEmaSymbolsCsv,
  buildEmaSymbolsTxt,
  buildTenureOptions,
  filterEmaRowsForDownload,
  filterEmaRowsBySymbol,
  formatLatestDateDisplay,
  formatLocalRefreshTime,
  getLatestLtcDateKey,
  normalizeLatestDateKey,
  normalizeTimeframe,
  readLatestDateCache,
  saveLatestDateCache,
  toNumber,
  type EmaCellTone,
  type EmaDownloadTenureYears,
  type EmaViewCell,
  type EmaViewRow,
} from '../../adapters/technicalEmaAdapter';
import { TechnicalMarketCapCell } from '../../components/app/TechnicalMarketCapCell';
import { fetchEmaTrendPayload, fetchTrendLatestDate, fetchTrendTradingDays } from '../../services/api/technicalApi';
import type { EmaTrendPayloadWire, EmaTrendTableKey, EmaTrendWireRow, TechnicalTimeframe } from '../../types/api/technical';
import { useProtectedPageAuth, useTechnicalThemeMode } from './technicalPageGuards';
import { readUrlSymbolSearch } from '../../utils/urlSymbolSearch';

const SYNC_TOAST_VISIBLE_MS = 10000;
const EMA_BREAKOUT_FLAG_FILTERS = [
  { key: 'ema_gt_20', summaryKey: 'emaGt20', label: 'EMA>20' },
  { key: 'ema_gt_50', summaryKey: 'emaGt50', label: 'EMA>50' },
  { key: 'ema_gt_50_20', summaryKey: 'emaGt5020', label: 'EMA>20>50' },
  { key: 'ema_gt_100', summaryKey: 'emaGt100', label: 'EMA>100' },
  { key: 'ema_gt_200', summaryKey: 'emaGt200', label: 'EMA>200' },
  { key: 'ema_gt_200_100_50', summaryKey: 'emaGt20010050', label: 'EMA>50>100>200' },
  { key: 'ema_gt_200_100_50_20', summaryKey: 'emaGt2001005020', label: 'EMA>20>50>100>200' },
  { key: 'weekly_bo', summaryKey: 'weeklyBO', label: 'Weekly_BO' },
  { key: 'monthly_bo', summaryKey: 'monthlyBO', label: 'Monthly_BO' },
  { key: '3m_bo', summaryKey: 'threeMonthBO', label: '3M_BO' },
  { key: '6m_bo', summaryKey: 'sixMonthBO', label: '6M_BO' },
  { key: '9m_bo', summaryKey: 'nineMonthBO', label: '9M_BO' },
  { key: '52wl', summaryKey: 'week52Low', label: '52WL' },
  { key: '52wh', summaryKey: 'week52High', label: '52WH' },
  { key: '2y_bo', summaryKey: 'twoYearBO', label: '2Y_BO' },
  { key: '3y_bo', summaryKey: 'threeYearBO', label: '3Y_BO' },
  { key: '4y_bo', summaryKey: 'fourYearBO', label: '4Y_BO' },
  { key: '5y_bo', summaryKey: 'fiveYearBO', label: '5Y_BO' },
  { key: '10y_bo', summaryKey: 'tenYearBO', label: '10Y_BO' },
  { key: 'ath', summaryKey: 'ath', label: 'ATH' },
  { key: 'atl', summaryKey: 'atl', label: 'ATL' },
  { key: 'gap10', summaryKey: 'gap10', label: 'GAP=10%' },
  { key: 'gap20', summaryKey: 'gap20', label: 'GAP=20%' },
  { key: 'gap30', summaryKey: 'gap30', label: 'GAP=30%' },
  { key: 'gap40', summaryKey: 'gap40', label: 'GAP=40%' },
  { key: 'gap50', summaryKey: 'gap50', label: 'GAP=50%' },
] as const;

type LoadStatus = 'error' | 'loading' | 'online';
type EmaBreakoutFlagKey = typeof EMA_BREAKOUT_FLAG_FILTERS[number]['key'];

type LatestDateState = {
  fetchedAtMs: number | null;
  key: string | null;
};

function triggerDownload(contents: string, filename: string, contentType: string): void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  const blob = new Blob([contents], { type: contentType });
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.URL.revokeObjectURL(url);
}

const EMA_STACK_SUMMARY_TABLES: Partial<Record<string, EmaTrendTableKey>> = {
  emaGt20: 'ema20',
  emaGt50: 'ema50',
  emaGt200: 'ema200',
  emaGt20010050: 'ema20010050',
  emaGt2001005020: 'ema2001005020',
};

function symbolKey(row: EmaViewRow): string {
  return row.symbol.trim().toUpperCase();
}

function intersectRows(primary: EmaViewRow[], secondary: EmaViewRow[]): EmaViewRow[] {
  const secondarySymbols = new Set(secondary.map(symbolKey).filter(Boolean));
  return primary.filter((row) => secondarySymbols.has(symbolKey(row)));
}

function emaStackRowsForFilter(
  key: EmaBreakoutFlagKey,
  tables: Record<EmaTrendTableKey, EmaViewRow[]>,
): EmaViewRow[] | null {
  switch (key) {
    case 'ema_gt_20':
      return tables.ema20 ?? [];
    case 'ema_gt_50':
      return tables.ema50 ?? [];
    case 'ema_gt_50_20':
      return (tables.ema5020 ?? []).length
        ? tables.ema5020
        : intersectRows(tables.ema50 ?? [], tables.ema20 ?? []);
    case 'ema_gt_100':
      return (tables.ema100 ?? []).length
        ? tables.ema100
        : tables.ema200100 ?? [];
    case 'ema_gt_200':
      return tables.ema200 ?? [];
    case 'ema_gt_200_100_50':
      return tables.ema20010050 ?? [];
    case 'ema_gt_200_100_50_20':
      return tables.ema2001005020 ?? [];
    default:
      return null;
  }
}

function uniqueEmaSymbolCount(tables: Record<EmaTrendTableKey, EmaViewRow[]>): number {
  const symbols = new Set<string>();
  EMA_TABLE_KEYS.forEach((key) => {
    (tables[key] ?? []).forEach((row) => {
      const symbol = symbolKey(row);
      if (symbol) symbols.add(symbol);
    });
  });
  return symbols.size;
}

function loadStoredTimeframe(): TechnicalTimeframe {
  try {
    return normalizeTimeframe(window.localStorage.getItem(TREND_TIMEFRAME_STORAGE_KEY));
  } catch {
    return 'daily';
  }
}

function persistTimeframe(timeframe: TechnicalTimeframe): void {
  try {
    window.localStorage.setItem(TREND_TIMEFRAME_STORAGE_KEY, timeframe);
  } catch {
    // Storage persistence is optional; API requests remain unchanged.
  }
}

function cellToneClass(tone?: EmaCellTone): string | undefined {
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

function EmaCell({ cell }: { cell: EmaViewCell }) {
  const className = cellToneClass(cell.tone);
  if (!className && !cell.title) {
    return <>{cell.text}</>;
  }
  return (
    <span className={className} title={cell.title}>
      {cell.text}
    </span>
  );
}

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

function rowCellClass(row: EmaViewRow, key: string): string | undefined {
  const tone = row.cells[key]?.tone;
  return tone === 'large' || tone === 'mid' || tone === 'small' || tone === 'unknown' ? 'trend-mcap-cell' : undefined;
}

function lowerText(value: unknown): string {
  return String(value ?? '').trim().toLowerCase();
}

function containsAny(value: unknown, tokens: string[]): boolean {
  const text = lowerText(value);
  return tokens.some((token) => text.includes(token));
}

function rawAny(row: EmaViewRow, names: string[]): unknown {
  const source = row.raw as Record<string, unknown>;
  for (const name of names) {
    const value = source[name];
    if (value === undefined || value === null) continue;
    if (String(value).trim() === '') continue;
    return value;
  }
  return '';
}

function isTruthyFlag(value: unknown): boolean {
  if (value === true) return true;
  if (typeof value === 'number') return value === 1;
  return ['1', 'true', 'y', 'yes'].includes(lowerText(value));
}

function emaCellNumber(row: EmaViewRow, key: string): number | null {
  return toNumber(row.cells[key]?.sort ?? row.cells[key]?.text);
}

function emaGapDistancePercent(row: EmaViewRow): number | null {
  const ath = emaCellNumber(row, 'ath');
  const price = emaCellNumber(row, 'price');
  if (ath !== null && ath > 0 && price !== null) {
    return ((ath - price) / ath) * 100;
  }
  const rawDistance = toNumber(rawAny(row, ['distance_from_ath_percent', 'distanceFromAthPercent']));
  if (rawDistance !== null) {
    return rawDistance;
  }
  const gap = emaCellNumber(row, 'gap');
  if (gap !== null) {
    return gap <= 0 ? Math.abs(gap) : 0;
  }
  return null;
}

function emaWithinGap(row: EmaViewRow, maxGapPercent: number): boolean {
  const gap = emaGapDistancePercent(row);
  return gap !== null && gap >= 0 && gap <= maxGapPercent;
}

function emaMatchesBreakoutFlag(row: EmaViewRow, key: EmaBreakoutFlagKey): boolean {
  switch (key) {
    case 'weekly_bo':
      return isTruthyFlag(rawAny(row, ['weeklyBO', 'Weekly_BO'])) || (emaCellNumber(row, 'd5') ?? 0) > 0;
    case 'monthly_bo':
      return isTruthyFlag(rawAny(row, ['monthlyBO', 'Monthly_BO'])) || (emaCellNumber(row, 'd22') ?? 0) > 0;
    case '3m_bo':
      return isTruthyFlag(rawAny(row, ['threeMonthBO', '3M_BO'])) || (emaCellNumber(row, 'd66') ?? 0) > 0;
    case '6m_bo':
      return isTruthyFlag(rawAny(row, ['sixMonthBO', '6M_BO'])) || (emaCellNumber(row, 'd132') ?? 0) > 0;
    case '9m_bo':
      return isTruthyFlag(rawAny(row, ['nineMonthBO', '9M_BO'])) || (emaCellNumber(row, 'd198') ?? 0) > 0;
    case '52wl':
      return isTruthyFlag(rawAny(row, ['week52Low', '52WL'])) ||
        containsAny(rawAny(row, ['breakoutFlags', 'BREAKOUT_FLAGS']), ['52-week low', '52w low']) ||
        (emaCellNumber(row, 'y1') ?? 0) < 0;
    case '52wh':
      return isTruthyFlag(rawAny(row, ['week52High', '52WH'])) ||
        containsAny(rawAny(row, ['breakoutFlags', 'BREAKOUT_FLAGS']), ['52-week high', '52w high']) ||
        (emaCellNumber(row, 'y1') ?? 0) > 0;
    case '2y_bo':
      return isTruthyFlag(rawAny(row, ['twoYearBO', '2Y_BO'])) || (emaCellNumber(row, 'y2') ?? 0) > 0;
    case '3y_bo':
      return isTruthyFlag(rawAny(row, ['threeYearBO', '3Y_BO'])) || (emaCellNumber(row, 'y3') ?? 0) > 0;
    case '4y_bo':
      return isTruthyFlag(rawAny(row, ['fourYearBO', '4Y_BO'])) || (emaCellNumber(row, 'y4') ?? 0) > 0;
    case '5y_bo':
      return isTruthyFlag(rawAny(row, ['fiveYearBO', '5Y_BO'])) || (emaCellNumber(row, 'y5') ?? 0) > 0;
    case '10y_bo':
      return isTruthyFlag(rawAny(row, ['tenYearBO', '10Y_BO'])) || (emaCellNumber(row, 'y10') ?? 0) > 0;
    case 'ath':
      return isTruthyFlag(rawAny(row, ['athBreakout', 'ATH_BREAKOUT'])) ||
        (emaCellNumber(row, 'gap') ?? Number.NEGATIVE_INFINITY) >= 0 ||
        emaWithinGap(row, 10);
    case 'atl':
      return isTruthyFlag(rawAny(row, ['atlBreakout', 'ATL_BREAKOUT', 'ATL'])) ||
        containsAny(rawAny(row, ['breakoutFlags', 'BREAKOUT_FLAGS']), ['atl', 'all-time low']) ||
        ((emaGapDistancePercent(row) ?? 0) > 50);
    case 'gap10':
      return emaWithinGap(row, 10);
    case 'gap20':
      return emaWithinGap(row, 20);
    case 'gap30':
      return emaWithinGap(row, 30);
    case 'gap40':
      return emaWithinGap(row, 40);
    case 'gap50':
      return emaWithinGap(row, 50);
    default:
      return false;
  }
}

function emaSummaryCards(tables: Record<EmaTrendTableKey, EmaViewRow[]>, totalSymbols: number | null): Record<string, number> {
  return EMA_BREAKOUT_FLAG_FILTERS.reduce((acc, filter) => {
    const summaryTable = EMA_STACK_SUMMARY_TABLES[filter.summaryKey];
    const stackRows = emaStackRowsForFilter(filter.key, tables);
    acc[filter.summaryKey] = stackRows
      ? stackRows.length
      : summaryTable
        ? (tables[summaryTable] ?? []).length
        : (tables.ema20 ?? []).filter((row) => emaMatchesBreakoutFlag(row, filter.key)).length;
    return acc;
  }, { totalSymbols: totalSymbols ?? uniqueEmaSymbolCount(tables) } as Record<string, number>);
}

export function EMA() {
  const [timeframe, setTimeframe] = useState<TechnicalTimeframe>(() => typeof window === 'undefined' ? 'daily' : loadStoredTimeframe());
  const [search, setSearch] = useState(readUrlSymbolSearch);
  const deferredSearch = useDeferredValue(search);
  const [breakoutFlag, setBreakoutFlag] = useState<EmaBreakoutFlagKey | ''>('');
  const [downloadTenureYears, setDownloadTenureYears] = useState<EmaDownloadTenureYears | null>(null);
  const [wirePayload, setWirePayload] = useState<EmaTrendPayloadWire | null>(null);
  const [tradingDayWireRows, setTradingDayWireRows] = useState<EmaTrendWireRow[]>([]);
  const [tradingDayError, setTradingDayError] = useState<string | null>(null);
  const [latestDate, setLatestDate] = useState<LatestDateState>(() => latestStateFromCache());
  const authorized = useProtectedPageAuth();
  const [status, setStatus] = useState<LoadStatus>('loading');
  const [error, setError] = useState<string | null>(null);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [syncMessage, setSyncMessage] = useState('');
  const forceRefreshRef = useRef(true);
  const latestRef = useRef(latestDate);
  const previousCachedAtRef = useRef<string | null>(null);
  const themeMode = useTechnicalThemeMode();

  useEffect(() => {
    latestRef.current = latestDate;
  }, [latestDate]);

  useEffect(() => {
    persistTimeframe(timeframe);
  }, [timeframe]);

  useEffect(() => {
    if (!syncMessage) return undefined;
    const timeout = window.setTimeout(() => setSyncMessage(''), SYNC_TOAST_VISIBLE_MS);
    return () => window.clearTimeout(timeout);
  }, [syncMessage]);

  useEffect(() => {
    if (!authorized) return undefined;
    let cancelled = false;
    const controller = new AbortController();

    async function syncLatestDate(triggerTrendReload: boolean) {
      try {
        const payload = await fetchTrendLatestDate({ signal: controller.signal });
        const key = normalizeLatestDateKey(payload.ltc_date ?? payload.ltcDate ?? payload.LTC_DATE);
        if (!key || cancelled) return;
        const previous = latestRef.current.key;
        const fetchedAtMs = Date.now();
        saveLatestDateCache(key, fetchedAtMs, window.localStorage);
        setLatestDate({ fetchedAtMs, key });
        if (previous && previous !== key) {
          setSyncMessage(`LTC_DATE: ${formatLatestDateDisplay(key)} | Last refreshed: ${formatLocalRefreshTime(fetchedAtMs)}`);
          if (triggerTrendReload) {
            forceRefreshRef.current = true;
            setRefreshVersion((current) => current + 1);
          }
        }
      } catch {
        // Latest-date polling is metadata-only. Keep the table data path untouched.
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

  useEffect(() => {
    if (!authorized) return undefined;
    const controller = new AbortController();
    const forceRefresh = forceRefreshRef.current;
    forceRefreshRef.current = false;
    setStatus('loading');
    setError(null);

    fetchEmaTrendPayload(timeframe, { forceRefresh, signal: controller.signal })
      .then((payload) => {
        setWirePayload(payload);
        setStatus('online');
        const fetchedAtMs = Date.now();
        const payloadLatest = getLatestLtcDateKey(payload);
        const previousLatest = latestRef.current.key;
        if (payloadLatest) {
          saveLatestDateCache(payloadLatest, fetchedAtMs, window.localStorage);
          setLatestDate({ fetchedAtMs, key: payloadLatest });
        }
        const cachedAtChanged = previousCachedAtRef.current && payload.cachedAt && previousCachedAtRef.current !== payload.cachedAt;
        const latestChanged = previousLatest && payloadLatest && previousLatest !== payloadLatest;
        if (cachedAtChanged || latestChanged) {
          setSyncMessage(`LTC_DATE: ${formatLatestDateDisplay(payloadLatest ?? previousLatest)} | Last refreshed: ${formatLocalRefreshTime(fetchedAtMs)}`);
        }
        previousCachedAtRef.current = typeof payload.cachedAt === 'string' ? payload.cachedAt : previousCachedAtRef.current;
      })
      .catch((loadError: unknown) => {
        if (controller.signal.aborted) return;
        setWirePayload(null);
        setStatus('error');
        setError(loadError instanceof Error ? loadError.message : String(loadError));
      });

    return () => controller.abort();
  }, [authorized, refreshVersion, timeframe]);

  useEffect(() => {
    if (!authorized) return undefined;
    const controller = new AbortController();
    setTradingDayError(null);

    fetchTrendTradingDays(timeframe, {
      forceRefresh: refreshVersion > 0,
      signal: controller.signal,
    }).then((payload) => {
      if (controller.signal.aborted) return;
      setTradingDayWireRows(Array.isArray(payload.rows) ? payload.rows : []);
    }).catch((loadError: unknown) => {
      if (controller.signal.aborted) return;
      setTradingDayWireRows([]);
      setTradingDayError(loadError instanceof Error ? loadError.message : String(loadError));
    });

    return () => controller.abort();
  }, [authorized, refreshVersion, timeframe]);

  const viewPayload = useMemo(() => adaptEmaTrendPayload(wirePayload), [wirePayload]);
  const tenureOptions = useMemo(() => buildTenureOptions(wirePayload), [wirePayload]);
  const emaColumns = useMemo(() => buildEmaColumns(wirePayload), [wirePayload]);
  const filteredTables = useMemo(() => EMA_TABLE_KEYS.reduce((acc, key) => {
    acc[key] = filterEmaRowsBySymbol(viewPayload.tables[key], deferredSearch);
    return acc;
  }, {} as Record<EmaTrendTableKey, EmaViewRow[]>), [deferredSearch, viewPayload.tables]);
  const summaryTotalSymbols = deferredSearch.trim() ? null : viewPayload.totalSymbols;
  const breakoutSummary = useMemo(() => emaSummaryCards(filteredTables, summaryTotalSymbols), [filteredTables, summaryTotalSymbols]);
  const displayTables = useMemo(() => {
    if (!breakoutFlag) return filteredTables;
    const stackRows = emaStackRowsForFilter(breakoutFlag, filteredTables);
    if (stackRows) {
      const stackSymbols = new Set(stackRows.map(symbolKey).filter(Boolean));
      return EMA_TABLE_KEYS.reduce((acc, key) => {
        acc[key] = filteredTables[key].filter((row) => stackSymbols.has(symbolKey(row)));
        return acc;
      }, {} as Record<EmaTrendTableKey, EmaViewRow[]>);
    }
    return EMA_TABLE_KEYS.reduce((acc, key) => {
      acc[key] = filteredTables[key].filter((row) => emaMatchesBreakoutFlag(row, breakoutFlag));
      return acc;
    }, {} as Record<EmaTrendTableKey, EmaViewRow[]>);
  }, [breakoutFlag, filteredTables]);
  const tradingDayViewRows = useMemo(
    () => tradingDayWireRows.map((row, index) => adaptEmaTrendRow(row, index, [])),
    [tradingDayWireRows],
  );
  const tdDownloadRows = useMemo(
    () => filterEmaRowsForDownload(tradingDayViewRows, downloadTenureYears),
    [downloadTenureYears, tradingDayViewRows],
  );

  const columns = useMemo<Array<AppDataTableColumn<EmaViewRow>>>(() => emaColumns.map((column) => ({
    cellClassName: (row) => rowCellClass(row, column.key),
    dataCol: column.key,
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
      return <EmaCell cell={cell} />;
    },
    showArrow: /^(d|y)\d+$/.test(column.key),
    sortType: column.sortType,
  })), [emaColumns]);

  const statusTitle = status === 'online'
    ? `Backend Online${viewPayload.cached ? ' (cached)' : ''}${viewPayload.refreshing ? ' [refreshing]' : ''} [tf:${timeframe}]`
    : status === 'loading'
      ? `Loading trend stacks (${timeframe})...`
      : `Backend Down: ${error ?? 'Unknown error'}`;

  const statusLabel = status === 'online' ? 'Live' : status === 'loading' ? 'Syncing' : 'Check';
  const latestMeta = `LTC_DATE: ${formatLatestDateDisplay(latestDate.key ?? viewPayload.latestLtcDateKey)}`;
  const refreshMeta = `Last refreshed: ${formatLocalRefreshTime(latestDate.fetchedAtMs)}`;

  return (
    <div className={themeMode === 'dark' ? 'page-theme--technicals ema-page ema-page--dark ema-screen' : 'page-theme--technicals ema-page ema-screen'}>
      <CvingLegacyHeader activeSection="technicals" activeTechnicalPage="/app/technical/ema" />

      <main className="container">
        <section className="section-title ema-section-title">
          <h2>EMA</h2>
          <AppToolbar aria-label="EMA controls">
            <div className="trend-toolbar__item trend-toolbar__item--status">
              <LiveStatusPill state={status === 'online' ? 'live' : status === 'loading' ? 'syncing' : 'stale'} title={statusTitle} label={statusLabel} />
              <div className="trend-toolbar__status-meta" aria-live="polite">
                {syncMessage ? <span className="trend-sync-toast">{syncMessage}</span> : null}
                <span id="trendLatestDateMeta">{latestMeta}</span>
                <span id="trendLastRefreshedMeta">{refreshMeta}</span>
              </div>
            </div>
            <div className="trend-toolbar__item trend-toolbar__item--search sr-toolbar__group sr-toolbar__group--search">
              <div className="sr-search">
                <span className="sr-search__decor" aria-hidden="true">⌕</span>
                <Input
                  id="trendSearch"
                  className="sr-search__input"
                  variant="surface"
                  type="search"
                  placeholder="Search NSE/BSE symbols"
                  autoComplete="off"
                  aria-label="Search stocks"
                  value={search}
                  onChange={(event) => setSearch(event.currentTarget.value)}
                />
              </div>
            </div>
            <div className="trend-toolbar__item trend-toolbar__item--timeframe sr-toolbar__group sr-toolbar__group--timeframe trend-toolbar__select">
              <Select
                id="trendTimeframe"
                className="sr-select"
                variant="surface"
                title="Pick timeframe for EMA views"
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
            <div className="trend-toolbar__item trend-toolbar__item--tenure sr-toolbar__group sr-toolbar__group--tenure trend-toolbar__select">
              <Select
                id="trendTenure"
                className="sr-select sr-select--tenure"
                variant="surface"
                aria-label="Tenure counts"
                disabled={tenureOptions.length === 0}
                value={tenureOptions[0]?.value ?? ''}
                onChange={() => undefined}
              >
                {tenureOptions.length ? tenureOptions.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                )) : (
                  <option>No tenure data</option>
                )}
              </Select>
            </div>
            <div className="trend-toolbar__item trend-toolbar__item--actions sr-toolbar__group sr-toolbar__group--actions">
              <Button
                id="refreshTrend"
                className="preset-btn"
                variant="secondary"
                loading={status === 'loading'}
                title="Refresh data from backend"
                onClick={() => {
                  forceRefreshRef.current = true;
                  setRefreshVersion((current) => current + 1);
                }}
              >
                Refresh
              </Button>
            </div>
          </AppToolbar>
        </section>

        {!authorized ? (
          <section className="card" role="status">
            Checking session...
          </section>
        ) : null}

        {error ? (
          <ErrorAlertCard context="Failed to load EMA data" message={error} />
        ) : null}

        {authorized ? (
          <>
            <section className="delivery-filter-panel ema-breakout-filter-panel" aria-label="EMA breakout flag filters">
              <div className="delivery-checkbox-row">
                {EMA_BREAKOUT_FLAG_FILTERS.map((filter) => (
                  <label className="delivery-filter-check" key={filter.key}>
                    <input
                      type="checkbox"
                      checked={breakoutFlag === filter.key}
                      onChange={(event) => setBreakoutFlag(event.currentTarget.checked ? filter.key : '')}
                    />
                    {filter.label}
                  </label>
                ))}
              </div>
            </section>

            <section className="delivery-filter-panel ema-breakout-filter-panel ema-td-download-panel" aria-label="T_D symbol downloads">
              <strong>T_D Symbol Downloads</strong>
              {tradingDayError ? <span className="trend-sync-toast">T_D data unavailable: {tradingDayError}</span> : null}
              <div className="ema-download-controls">
                <div className="ema-download-tenure-options" aria-label="Maximum trading day tenure">
                  {EMA_DOWNLOAD_TENURE_OPTIONS.map((option) => (
                    <label className="delivery-filter-check ema-download-filter" key={option.years}>
                      <input
                        type="checkbox"
                        checked={downloadTenureYears === option.years}
                        onChange={(event) => setDownloadTenureYears(event.currentTarget.checked ? option.years : null)}
                      />
                      {option.label}
                    </label>
                  ))}
                </div>
                <span className="count-pill">MATCHES: {tdDownloadRows.length.toLocaleString('en-IN')}</span>
                <div className="ema-download-actions">
                  <Button
                    className="ema-download-button"
                    size="sm"
                    variant="secondary"
                    disabled={tdDownloadRows.length === 0}
                    title={`Download ${tdDownloadRows.length} T_D-matched symbols as comma-separated text`}
                    onClick={() => triggerDownload(
                      buildEmaSymbolsTxt(tdDownloadRows),
                      `ema-symbols-td-under-${downloadTenureYears}y.txt`,
                      'text/plain;charset=utf-8;',
                    )}
                  >
                    Download TXT
                  </Button>
                  <Button
                    className="ema-download-button"
                    size="sm"
                    disabled={tdDownloadRows.length === 0}
                    title={`Download ${tdDownloadRows.length} T_D-matched symbols as CSV`}
                    onClick={() => triggerDownload(
                      buildEmaSymbolsCsv(tdDownloadRows),
                      `ema-symbols-td-under-${downloadTenureYears}y.csv`,
                      'text/csv;charset=utf-8;',
                    )}
                  >
                    Download CSV
                  </Button>
                </div>
              </div>
            </section>

            <section className="technical-summary-grid delivery-summary-grid ema-breakout-summary-grid" aria-label="EMA breakout summary">
              {[{ key: 'totalSymbols', label: 'Total Symbols' }, ...EMA_BREAKOUT_FLAG_FILTERS.map((filter) => ({ key: filter.summaryKey, label: filter.label }))].map((card) => (
                <article key={card.key} className="technical-summary-card">
                  <span>{card.label}</span>
                  <strong>{(breakoutSummary[card.key] ?? 0).toLocaleString('en-IN')}</strong>
                </article>
              ))}
            </section>
          </>
        ) : null}

        {authorized ? EMA_TABLE_CONFIGS.map((config) => {
          const rows = displayTables[config.key];
          return (
            <section className="card ema-table-card" key={config.key}>
              <div className="table-title">
                <h3>
                  {config.title} <span className="count-pill">TOTAL STOCKS: {rows.length}</span>
                </h3>
              </div>
              <AppDataTable
                className={`ema-table-shell ema-table-shell--${config.color}`}
                columns={columns}
                emptyMessage="No records returned from backend."
                getRowKey={(row, index) => `${config.key}-${row.id}-${index}`}
                pageSize={EMA_PAGE_SIZE}
                rows={rows}
                showTopPagination={config.showTopPagination}
                tableClassName={`data-table--${config.color}`}
                tableId={`tbl-${config.key}`}
              />
            </section>
          );
        }) : null}
      </main>

      <section className="disclaimer">
        <div className="container">
          <p>Investments in securities market are subject to market risk, read all the related documents carefully before investing.</p>
          <p>We collect, retain, and use your contact information for legitimate business purposes only, to contact you and to provide you information & latest updates regarding our products & services.</p>
          <p>We do not sell or rent your contact information to third parties.</p>
          <p>Please note that by submitting the above-mentioned details, you are authorizing us to Call/SMS you even though you may be registered under DND. We shall Call/SMS you for a period of 12 months.</p>
          <p>Copyright@2026-CvingTrade25X - All rights reserved.</p>
        </div>
      </section>
    </div>
  );
}
