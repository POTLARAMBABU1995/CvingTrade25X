import { useDeferredValue, useEffect, useMemo, useRef, useState } from 'react';
import { AppDataTable, type AppDataTableColumn, type AppSortState } from '../../components/app/AppDataTable';
import { LiveStatusPill } from '../../components/app/LiveStatusPill';
import { TechnicalSearchInput } from '../../components/app/TechnicalSearchInput';
import { CvingLegacyHeader } from '@/components/navigation/CvingLegacyHeader';
import { Button } from '../../components/ui/Button';
import { DataBadge } from '../../components/ui/DataBadge';
import { ErrorAlertCard } from '../../components/ui/ErrorAlertCard';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import {
  adaptTechnicalScreenerPayload,
  type TechnicalScreenerPageConfig,
  type TechnicalScreenerViewPayload,
  type TechnicalScreenerViewRow,
} from '../../adapters/technicalScreenerAdapter';
import {
  formatLatestDateDisplay,
  formatLocalRefreshTime,
  normalizeLatestDateKey,
  normalizeTimeframe,
  readLatestDateCache,
  saveLatestDateCache,
  TREND_LATEST_DATE_POLL_INTERVAL_MS,
} from '../../adapters/technicalEmaAdapter';
import { TechnicalMarketCapCell } from '../../components/app/TechnicalMarketCapCell';
import {
  fetchTechnicalScreenerPayload,
  fetchTrendLatestDate,
  type TechnicalScreenerQuery,
} from '../../services/api/technicalApi';
import type { TechnicalScreenerPayloadWire, TechnicalTimeframe } from '../../types/api/technical';
import { useProtectedPageAuth, useTechnicalThemeMode } from './technicalPageGuards';
import { readUrlSymbolSearch } from '../../utils/urlSymbolSearch';

const SCREENER_TRANSIENT_RETRY_DELAYS_MS = [750, 1500, 3000];
const BREAKOUT_FLAG_FILTERS = [
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
] as const;

type LoadStatus = 'error' | 'loading' | 'online';
type LatestDateState = {
  fetchedAtMs: number | null;
  key: string | null;
};

function lowerText(value: unknown): string {
  return String(value ?? '').trim().toLowerCase();
}

function numeric(value: unknown): number | null {
  const parsed = Number(String(value ?? '').replace(/,/g, '').replace(/%/g, ''));
  return Number.isFinite(parsed) ? parsed : null;
}

function containsAny(value: unknown, tokens: string[]): boolean {
  const text = lowerText(value);
  return tokens.some((token) => text.includes(token));
}

function computeSummaryValue(key: string, payload: TechnicalScreenerViewPayload): number {
  if (key === 'totalSymbols') return payload.total;
  const rows = payload.rows;
  const count = (fn: (row: TechnicalScreenerViewRow) => boolean) => rows.filter(fn).length;
  const cell = (row: TechnicalScreenerViewRow, name: string) => row.cells[name]?.text ?? '';
  const raw = (row: TechnicalScreenerViewRow, name: string) => (row.raw as Record<string, unknown>)[name];
  const rawAny = (row: TechnicalScreenerViewRow, names: string[]) => {
    const source = row.raw as Record<string, unknown>;
    for (const name of names) {
      const value = source[name];
      if (value === undefined || value === null) continue;
      if (String(value).trim() === '') continue;
      return value;
    }
    return '';
  };
  switch (key) {
    case 'strongUptrend':
      return count((row) => lowerText(cell(row, 'trendStructure')) === 'strong uptrend');
    case 'hhHlStructure':
      return count((row) => containsAny(raw(row, 'priceActionLabels'), ['higher high']) && containsAny(raw(row, 'priceActionLabels'), ['higher low']));
    case 'accumulation':
      return count((row) => lowerText(cell(row, 'trendStructure')) === 'accumulation');
    case 'rangeBound':
      return count((row) => containsAny(cell(row, 'trendStructure'), ['range']));
    case 'downtrend':
      return count((row) => containsAny(cell(row, 'trendStructure'), ['downtrend']));
    case 'nearSupport':
      return count((row) => {
        const price = numeric(row.cells.price?.sort);
        const support = numeric(row.cells.support?.sort);
        return Boolean(price && support && ((price - support) / price * 100) <= 3);
      });
    case 'weakStructure':
      return count((row) => containsAny(raw(row, 'techStatus'), ['weak', 'avoid']) || containsAny(cell(row, 'trendStructure'), ['downtrend', 'range']));
    case 'strongSupportTrendline':
      return count((row) => lowerText(cell(row, 'trendlineStatus')) === 'strong support trendline');
    case 'nearTrendlineSupport':
      return count((row) => lowerText(cell(row, 'trendlineStatus')) === 'near trendline support');
    case 'trendlineBreakRisk':
      return count((row) => lowerText(cell(row, 'trendlineStatus')) === 'trendline break risk');
    case 'trendlineBroken':
      return count((row) => lowerText(cell(row, 'trendlineStatus')) === 'trendline broken');
    case 'positiveSlope':
      return count((row) => (numeric(row.cells.slope?.sort) ?? 0) > 0);
    case 'touch3Trendlines':
      return count((row) => (numeric(row.cells.touchCount?.sort) ?? 0) >= 3);
    case 'noCleanTrendline':
      return count((row) => lowerText(cell(row, 'trendlineStatus')) === 'no clean trendline');
    case 'freshBreakouts':
      return count((row) => containsAny(cell(row, 'breakoutStatus'), ['breakout']) && !containsAny(cell(row, 'breakoutStatus'), ['failed', 'no breakout']));
    case 'confirmedBreakouts':
      return count((row) => containsAny(cell(row, 'breakoutStatus'), ['confirmed']));
    case 'retestSuccess':
      return count((row) => containsAny(cell(row, 'breakoutStatus'), ['retest success']) || containsAny(rawAny(row, ['breakoutFlags', 'BREAKOUT_FLAGS']), ['retest success']));
    case 'nearBreakout':
      return count((row) => containsAny(cell(row, 'breakoutStatus'), ['near breakout']));
    case 'week52Breakouts':
      return count((row) => containsAny(rawAny(row, ['breakoutFlags', 'BREAKOUT_FLAGS']), ['52-week', '52w']));
    case 'athBreakouts':
      return count((row) => rawAny(row, ['athBreakout', 'ATH_BREAKOUT']) === true || containsAny(cell(row, 'breakoutStatus'), ['ath']));
    case 'failedBreakouts':
      return count((row) => containsAny(cell(row, 'breakoutStatus'), ['failed']));
    case 'weeklyBO':
      return count((row) => rawAny(row, ['weeklyBO', 'Weekly_BO']) === true || lowerText(rawAny(row, ['Weekly_BO'])) === 'y');
    case 'monthlyBO':
      return count((row) => rawAny(row, ['monthlyBO', 'Monthly_BO']) === true || lowerText(rawAny(row, ['Monthly_BO'])) === 'y' || containsAny(rawAny(row, ['breakoutFlags', 'BREAKOUT_FLAGS']), ['20-day high breakout']));
    case 'threeMonthBO':
      return count((row) => rawAny(row, ['threeMonthBO', '3M_BO']) === true || lowerText(rawAny(row, ['3M_BO'])) === 'y');
    case 'sixMonthBO':
      return count((row) => rawAny(row, ['sixMonthBO', '6M_BO']) === true || lowerText(rawAny(row, ['6M_BO'])) === 'y');
    case 'nineMonthBO':
      return count((row) => rawAny(row, ['nineMonthBO', '9M_BO']) === true || lowerText(rawAny(row, ['9M_BO'])) === 'y');
    case 'week52Low':
      return count((row) => rawAny(row, ['week52Low', '52WL']) === true || lowerText(rawAny(row, ['52WL'])) === 'y');
    case 'week52High':
      return count((row) => rawAny(row, ['week52High', '52WH']) === true || lowerText(rawAny(row, ['52WH'])) === 'y' || containsAny(rawAny(row, ['breakoutFlags', 'BREAKOUT_FLAGS']), ['52-week high breakout', '52w']));
    case 'twoYearBO':
      return count((row) => rawAny(row, ['twoYearBO', '2Y_BO']) === true || lowerText(rawAny(row, ['2Y_BO'])) === 'y');
    case 'threeYearBO':
      return count((row) => rawAny(row, ['threeYearBO', '3Y_BO']) === true || lowerText(rawAny(row, ['3Y_BO'])) === 'y');
    case 'fourYearBO':
      return count((row) => rawAny(row, ['fourYearBO', '4Y_BO']) === true || lowerText(rawAny(row, ['4Y_BO'])) === 'y');
    case 'fiveYearBO':
      return count((row) => rawAny(row, ['fiveYearBO', '5Y_BO']) === true || lowerText(rawAny(row, ['5Y_BO'])) === 'y');
    case 'tenYearBO':
      return count((row) => rawAny(row, ['tenYearBO', '10Y_BO']) === true || lowerText(rawAny(row, ['10Y_BO'])) === 'y');
    case 'ath':
      return count((row) => rawAny(row, ['athBreakout', 'ATH_BREAKOUT']) === true || containsAny(cell(row, 'breakoutStatus'), ['ath']));
    case 'atl':
      return count((row) => rawAny(row, ['atlBreakout', 'ATL_BREAKOUT']) === true || lowerText(rawAny(row, ['ATL'])) === 'y');
    case 'bullishPatterns':
      return count((row) => !['', '-'].includes(cell(row, 'patternName').trim()));
    case 'ascendingTriangle':
      return count((row) => lowerText(cell(row, 'patternName')) === 'ascending triangle');
    case 'rectangleBox':
      return count((row) => containsAny(cell(row, 'patternName'), ['rectangle', 'box']));
    case 'bullishFlag':
      return count((row) => lowerText(cell(row, 'patternName')) === 'bullish flag');
    case 'uptrendChannel':
      return count((row) => lowerText(cell(row, 'patternName')) === 'uptrend channel');
    case 'fallingWedge':
      return count((row) => containsAny(cell(row, 'patternName'), ['falling wedge']));
    case 'breakoutPatterns':
      return count((row) => !['', '-'].includes(cell(row, 'patternName').trim()) && !containsAny(cell(row, 'breakoutStatus'), ['no breakout']));
    case 'veryStrongTechnicals':
      return count((row) => lowerText(cell(row, 'techStatus')) === 'very strong technicals');
    case 'strongTechnicals':
      return count((row) => lowerText(cell(row, 'techStatus')) === 'strong technicals');
    case 'trendlineSupport':
      return count((row) => ['strong support trendline', 'near trendline support'].includes(lowerText(cell(row, 'trendlineStatus'))));
    case 'volumeConfirmed':
      return count((row) => containsAny(cell(row, 'breakoutStatus'), ['volume confirmed']));
    case 'highRiskAvoid':
      return count((row) => containsAny(cell(row, 'riskLevel'), ['high', 'avoid']) || containsAny(cell(row, 'techStatus'), ['avoid']));
    default:
      return 0;
  }
}

function asSummaryDisplay(value: unknown): string {
  if (value === null || value === undefined || String(value).trim() === '') return '0';
  if (typeof value === 'number') return value.toLocaleString('en-IN');
  return String(value);
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (error && typeof error === 'object' && 'message' in error) {
    const message = String((error as { message?: unknown }).message ?? '').trim();
    if (message) return message;
  }
  return String(error ?? 'Unknown error');
}

function errorStatus(error: unknown): number {
  if (!error || typeof error !== 'object') return 0;
  const status = Number((error as { status?: unknown; httpStatus?: unknown }).status ?? (error as { httpStatus?: unknown }).httpStatus);
  return Number.isFinite(status) ? status : 0;
}

export function isTransientScreenerLoadError(error: unknown): boolean {
  const status = errorStatus(error);
  if (status >= 400) return false;
  const message = errorMessage(error);
  return status === 0 || /failed to fetch|networkerror|load failed|network request failed/i.test(message);
}

export function formatScreenerLoadError(error: unknown, hasStaleRows: boolean): string {
  if (!isTransientScreenerLoadError(error)) return errorMessage(error);
  return hasStaleRows
    ? 'Backend connection interrupted. Showing the last loaded rows; use Refresh after the local server is back online.'
    : 'Backend connection interrupted before rows loaded. Keep the local server running, then use Refresh.';
}

function waitForScreenerRetry(delayMs: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException('Aborted', 'AbortError'));
      return;
    }
    const timerId = window.setTimeout(resolve, delayMs);
    signal.addEventListener('abort', () => {
      window.clearTimeout(timerId);
      reject(new DOMException('Aborted', 'AbortError'));
    }, { once: true });
  });
}

function trendDirectionTone(value: string): 'default' | 'success' | 'warn' | 'danger' {
  const normalized = lowerText(value).toUpperCase();
  if (normalized === 'UPTREND') return 'success';
  if (normalized === 'DOWNTREND') return 'danger';
  if (normalized === 'SIDEWAYS') return 'warn';
  return 'default';
}

function normalizedTrendDirection(value: string): 'UPTREND' | 'DOWNTREND' | 'SIDEWAYS' | '-' {
  const normalized = lowerText(value).toUpperCase();
  if (normalized === 'UPTREND') return 'UPTREND';
  if (normalized === 'DOWNTREND') return 'DOWNTREND';
  if (normalized === 'SIDEWAYS' || normalized === 'RANGE' || normalized === 'CONSOLIDATION') return 'SIDEWAYS';
  return '-';
}

function cellToneClass(tone: TechnicalScreenerViewRow['cells'][string]['tone']): string | undefined {
  switch (tone) {
    case 'positive':
      return 'trend-price--up';
    case 'negative':
      return 'trend-price--down';
    default:
      return undefined;
  }
}

function buildCsv(rows: TechnicalScreenerViewRow[], config: TechnicalScreenerPageConfig): string {
  const escapeCsv = (value: unknown) => `"${String(value ?? '').replace(/"/g, '""')}"`;
  const header = config.columns.map((column) => escapeCsv(column.label)).join(',');
  const body = rows.map((row) => config.columns.map((column) => escapeCsv(row.cells[column.key]?.text ?? '')).join(','));
  return [header, ...body].join('\n');
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

function resolveScreenerLatestDateKey(payload: TechnicalScreenerPayloadWire | null | undefined): string | null {
  const meta = (payload?.meta ?? {}) as Record<string, unknown>;
  const metaLatest = normalizeLatestDateKey(
    meta.latestTradingDate ??
    meta.latest_trade_date ??
    meta.LTC_DATE ??
    meta.ltc_date,
  );
  if (metaLatest) return metaLatest;
  const rows = Array.isArray(payload?.rows) ? payload.rows : [];
  let latestKey: string | null = null;
  rows.forEach((row) => {
    const source = row as Record<string, unknown>;
    const key = normalizeLatestDateKey(
      source.ltcDate ??
      source.LTC_DATE ??
      source.TRADING_DATE ??
      source.tradingDate ??
      source.trading_date,
    );
    if (key && (!latestKey || key > latestKey)) {
      latestKey = key;
    }
  });
  return latestKey;
}

type TechnicalScreenerPageProps = {
  config: TechnicalScreenerPageConfig;
};

export function TechnicalScreenerPage({ config }: TechnicalScreenerPageProps) {
  const supportsLatestDate = config.kind === 'trendline';
  const authorized = useProtectedPageAuth();
  const [timeframe, setTimeframe] = useState<TechnicalTimeframe>('daily');
  const [search, setSearch] = useState(readUrlSymbolSearch);
  const deferredSearch = useDeferredValue(search);
  const [minScore, setMinScore] = useState('');
  const [pattern, setPattern] = useState('');
  const [breakoutFlag, setBreakoutFlag] = useState('');
  const [breakoutStatus, setBreakoutStatus] = useState('');
  const [trendlineStatus, setTrendlineStatus] = useState('');
  const [riskLevel, setRiskLevel] = useState('');
  const [sortBy, setSortBy] = useState(config.defaultSort);
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>(config.defaultSortDir);
  const [page, setPage] = useState(1);
  const [wirePayload, setWirePayload] = useState<TechnicalScreenerPayloadWire | null>(null);
  const [status, setStatus] = useState<LoadStatus>('loading');
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshedAtMs, setLastRefreshedAtMs] = useState<number | null>(null);
  const [latestDate, setLatestDate] = useState<LatestDateState>(() => latestStateFromCache());
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [toast, setToast] = useState('');
  const forceRefreshRef = useRef(config.initialForceRefresh ?? true);
  const wirePayloadRef = useRef<TechnicalScreenerPayloadWire | null>(null);
  const themeMode = useTechnicalThemeMode();

  useEffect(() => {
    setPage(1);
  }, [breakoutFlag, breakoutStatus, deferredSearch, minScore, pattern, riskLevel, timeframe, trendlineStatus]);

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

    const query: TechnicalScreenerQuery = {
      tf: timeframe,
      latest_only: 1,
      page,
      page_size: config.pageSize,
      sort_by: sortBy,
      sort_dir: sortDir,
      symbol: deferredSearch.trim() || undefined,
      min_score: minScore.trim() || undefined,
      pattern: pattern || undefined,
      breakout_flag: breakoutFlag || undefined,
      breakout_status: breakoutStatus || undefined,
      trendline_status: trendlineStatus || undefined,
      risk_level: riskLevel || undefined,
      refresh: forceRefresh ? 1 : undefined,
    };

    async function loadWithTransientRetry(): Promise<TechnicalScreenerPayloadWire> {
      for (let attempt = 0; attempt <= SCREENER_TRANSIENT_RETRY_DELAYS_MS.length; attempt += 1) {
        try {
          return await fetchTechnicalScreenerPayload(config.endpoint, query, { signal: controller.signal });
        } catch (loadError) {
          if (controller.signal.aborted) throw loadError;
          const shouldRetry = isTransientScreenerLoadError(loadError) && attempt < SCREENER_TRANSIENT_RETRY_DELAYS_MS.length;
          if (!shouldRetry) throw loadError;
          await waitForScreenerRetry(SCREENER_TRANSIENT_RETRY_DELAYS_MS[attempt], controller.signal);
        }
      }
      throw new Error('Failed to load technical screener payload');
    }

    loadWithTransientRetry()
      .then((payload) => {
        wirePayloadRef.current = payload;
        setWirePayload(payload);
        const fetchedAtMs = Date.now();
        setLastRefreshedAtMs(fetchedAtMs);
        setStatus('online');
        if (supportsLatestDate) {
          const payloadLatestKey = resolveScreenerLatestDateKey(payload);
          if (payloadLatestKey) {
            saveLatestDateCache(payloadLatestKey, fetchedAtMs, window.localStorage);
            setLatestDate({ fetchedAtMs, key: payloadLatestKey });
          }
        }
        if (forceRefresh) setToast(`${config.title}: refreshed at ${formatLocalRefreshTime(fetchedAtMs)}`);
      })
      .catch((loadError: unknown) => {
        if (controller.signal.aborted) return;
        const hasStaleRows = Boolean(wirePayloadRef.current?.rows?.length);
        if (!isTransientScreenerLoadError(loadError) || !hasStaleRows) {
          wirePayloadRef.current = null;
          setWirePayload(null);
        }
        setStatus('error');
        setError(formatScreenerLoadError(loadError, hasStaleRows));
      });

    return () => controller.abort();
  }, [authorized, breakoutFlag, breakoutStatus, config.endpoint, config.pageSize, config.title, deferredSearch, minScore, page, pattern, refreshVersion, riskLevel, sortBy, sortDir, supportsLatestDate, timeframe, trendlineStatus]);

  const payload = useMemo(
    () => adaptTechnicalScreenerPayload(wirePayload, config, page, config.pageSize),
    [config, page, wirePayload],
  );

  useEffect(() => {
    if (!authorized || !supportsLatestDate) return undefined;
    let cancelled = false;
    const controller = new AbortController();

    async function syncLatestDate(triggerReload: boolean) {
      try {
        const latestPayload = await fetchTrendLatestDate({ signal: controller.signal });
        const latestKey = normalizeLatestDateKey(latestPayload.ltc_date ?? latestPayload.ltcDate ?? latestPayload.LTC_DATE);
        if (!latestKey || cancelled) return;
        const fetchedAtMs = Date.now();
        saveLatestDateCache(latestKey, fetchedAtMs, window.localStorage);
        setLatestDate({ fetchedAtMs, key: latestKey });
        if (!triggerReload) return;
        if (payload.latestLtcDateKey && payload.latestLtcDateKey >= latestKey) return;
        forceRefreshRef.current = true;
        setRefreshVersion((current) => current + 1);
      } catch {
        // Latest-date polling is metadata-only. Keep current rows rendered.
      }
    }

    syncLatestDate(true);
    const interval = window.setInterval(() => syncLatestDate(true), TREND_LATEST_DATE_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      controller.abort();
      window.clearInterval(interval);
    };
  }, [authorized, payload.latestLtcDateKey, supportsLatestDate]);

  const statusTitle = status === 'online'
    ? `Backend Online${payload.cached ? ' (cached)' : ''}${payload.refreshing ? ' [refreshing]' : ''} [tf:${timeframe}]`
    : status === 'loading'
      ? `Loading ${config.title}...`
      : `Backend Down: ${error ?? 'Unknown error'}`;
  const latestMeta = supportsLatestDate ? `LTC_DATE: ${formatLatestDateDisplay(latestDate.key ?? payload.latestLtcDateKey)}` : null;
  const refreshMeta = supportsLatestDate
    ? `Last refreshed: ${formatLocalRefreshTime(latestDate.fetchedAtMs ?? lastRefreshedAtMs)}`
    : `Last refreshed: ${formatLocalRefreshTime(lastRefreshedAtMs)}`;

  const tableSortState: AppSortState = useMemo(() => ({
    direction: sortDir,
    key: sortBy,
  }), [sortBy, sortDir]);

  const columns = useMemo<Array<AppDataTableColumn<TechnicalScreenerViewRow>>>(() => config.columns.map((column) => ({
    cellClassName: () => column.sortType === 'number' ? 'technical-screener-table__cell--number' : undefined,
    dataCol: column.key,
    getSortValue: (row) => row.cells[column.key]?.sort ?? null,
    key: column.key,
    label: column.label,
    renderCell: (row) => {
      const cell = row.cells[column.key] ?? { text: '-', sort: null };
      const marketCapTone = column.key === 'symbol' || column.key === 'index' || column.key === 'mcap' || column.key === 'mcapRank'
        ? (cell.tone === 'large' || cell.tone === 'mid' || cell.tone === 'small' || cell.tone === 'unknown'
          ? cell.tone
          : 'unknown')
        : undefined;
      const toneClass = cellToneClass(cell.tone);

      if (column.key === 'symbol') {
        return (
          <TechnicalMarketCapCell
            copyText={cell.text}
            tone={marketCapTone}
            onCopy={(value) => {
              if (!navigator.clipboard) return;
              navigator.clipboard.writeText(value).then(() => setToast(`Copied: ${value}`)).catch(() => undefined);
            }}
          >
            {cell.text}
          </TechnicalMarketCapCell>
        );
      }
      if (marketCapTone) {
        return (
          <TechnicalMarketCapCell tone={marketCapTone}>
            {cell.text}
          </TechnicalMarketCapCell>
        );
      }
      if (column.key === 'trendDirection') {
        return <DataBadge tone={trendDirectionTone(cell.text)}>{normalizedTrendDirection(cell.text)}</DataBadge>;
      }
      if (toneClass || cell.title) {
        return <span className={toneClass} title={cell.title}>{cell.text}</span>;
      }
      return cell.text;
    },
    sortType: column.sortType,
  })), [config.columns]);

  const handleTableSortChange = (nextSort: AppSortState) => {
    if (!nextSort.key || !nextSort.direction) return;
    setPage(1);
    setSortBy(nextSort.key);
    setSortDir(nextSort.direction);
  };

  const handleExport = async () => {
    try {
      setToast('Preparing CSV export...');
      const rows: TechnicalScreenerViewRow[] = [];
      let exportPage = 1;
      let totalPages = 1;
      do {
        const exportPayload = await fetchTechnicalScreenerPayload(config.endpoint, {
          tf: timeframe,
          latest_only: 1,
          page: exportPage,
          page_size: 500,
          sort_by: sortBy,
          sort_dir: sortDir,
          symbol: deferredSearch.trim() || undefined,
          min_score: minScore.trim() || undefined,
          pattern: pattern || undefined,
          breakout_flag: breakoutFlag || undefined,
          breakout_status: breakoutStatus || undefined,
          trendline_status: trendlineStatus || undefined,
          risk_level: riskLevel || undefined,
        });
        const adapted = adaptTechnicalScreenerPayload(exportPayload, config, exportPage, 500);
        rows.push(...adapted.rows);
        totalPages = adapted.totalPages;
        exportPage += 1;
      } while (exportPage <= totalPages);

      const blob = new Blob([buildCsv(rows, config)], { type: 'text/csv;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${config.fileName}_${timeframe}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setToast('CSV exported');
    } catch (exportError) {
      setToast(exportError instanceof Error ? exportError.message : 'CSV export failed');
    }
  };

  return (
    <div className={themeMode === 'dark' ? `page-theme--technicals ema-page ema-page--dark technical-screener-page technical-screener-page--${config.kind}` : `page-theme--technicals ema-page technical-screener-page technical-screener-page--${config.kind}`}>
      <CvingLegacyHeader activeSection="technicals" activeTechnicalPage={config.activeTechnicalPage} />

      <main className="container technical-screener-shell">
        <section className="technical-screener-header">
          <h1>{config.title}</h1>
          <div className="trend-toolbar__status-meta" aria-live="polite">
            {toast ? <span className="trend-sync-toast">{toast}</span> : null}
            {latestMeta ? <span>{latestMeta}</span> : null}
            <span>{refreshMeta}</span>
          </div>
        </section>

        <section className="technical-screener-filters" aria-label={`${config.title} filters`}>
          <div className="technical-screener-filters__search flex min-w-[280px] flex-1 items-center gap-3">
            <LiveStatusPill state={status === 'online' ? 'live' : status === 'loading' ? 'syncing' : 'stale'} title={statusTitle} />
            <TechnicalSearchInput value={search} onChange={setSearch} />
          </div>
          <Select
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
          <Input
            variant="surface"
            type="number"
            min="0"
            max="100"
            step="1"
            placeholder="Min score"
            aria-label="Minimum score"
            value={minScore}
            onChange={(event) => setMinScore(event.currentTarget.value)}
          />
          {config.patternOptions?.length ? (
            <Select variant="surface" aria-label="Pattern" value={pattern} onChange={(event) => setPattern(event.currentTarget.value)}>
              <option value="">All Patterns</option>
              {config.patternOptions.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </Select>
          ) : null}
          {config.breakoutStatusOptions?.length ? (
            <Select variant="surface" aria-label="Breakout status" value={breakoutStatus} onChange={(event) => setBreakoutStatus(event.currentTarget.value)}>
              <option value="">All Breakouts</option>
              {config.breakoutStatusOptions.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </Select>
          ) : null}
            <Select variant="surface" aria-label="Trendline status" value={trendlineStatus} onChange={(event) => setTrendlineStatus(event.currentTarget.value)}>
            <option value="">All Trendlines</option>
            {(config.trendlineStatusOptions ?? []).map((option) => (
              <option key={option} value={option}>{option}</option>
            ))}
          </Select>
            <Select variant="surface" aria-label="Risk level" value={riskLevel} onChange={(event) => setRiskLevel(event.currentTarget.value)}>
            <option value="">All Risk</option>
            <option value="Low">Low</option>
            <option value="Medium">Medium</option>
            <option value="High">High</option>
            <option value="Unknown">Unknown</option>
          </Select>
          <Button
            className="preset-btn"
            variant="secondary"
            disabled={status === 'loading'}
            onClick={() => {
              forceRefreshRef.current = true;
              setRefreshVersion((current) => current + 1);
            }}
          >
            Refresh
          </Button>
          <Button className="preset-btn" variant="secondary" disabled={status === 'loading'} onClick={handleExport}>
            CSV
          </Button>
          <span className="count-pill">TOTAL: {payload.total.toLocaleString('en-IN')}</span>
        </section>

        {config.kind === 'breakout' ? (
          <section className="delivery-filter-panel breakout-filter-panel" aria-label="Breakout flag filters">
            <div className="delivery-checkbox-row">
              {BREAKOUT_FLAG_FILTERS.map((filter) => (
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
        ) : null}

        <section className={config.kind === 'breakout' ? 'technical-summary-grid delivery-summary-grid breakout-summary-grid' : 'technical-summary-grid'} aria-label={`${config.title} summary`}>
          {(config.kind === 'breakout'
            ? [{ key: 'totalSymbols', label: 'Total Symbols' }, ...BREAKOUT_FLAG_FILTERS.map((filter) => ({ key: filter.summaryKey, label: filter.label }))]
            : config.summaryCards).map((card) => (
            <article key={card.key} className="technical-summary-card">
              <span>{card.label}</span>
              <strong>{asSummaryDisplay(payload.summary[card.key] ?? computeSummaryValue(card.key, payload))}</strong>
            </article>
          ))}
        </section>

        {status === 'error' ? (
          <ErrorAlertCard context={`Failed to load ${config.title}`} message={error} />
        ) : null}

        <section className="card">
          <div className="table-title">
            <h3>{config.title}</h3>
            <span className="count-pill">PAGE {payload.page.toLocaleString('en-IN')} / {payload.totalPages.toLocaleString('en-IN')}</span>
          </div>
          <AppDataTable
            className="technical-screener-table-shell"
            columns={columns}
            currentPage={payload.page}
            disableClientSort
            emptyMessage={status === 'loading' ? 'Loading rows...' : config.emptyMessage}
            getRowKey={(row, index) => `${row.id}-${index}`}
            onPageChange={setPage}
            onSortChange={handleTableSortChange}
            pageSize={config.pageSize}
            paginationSummaryLabel="symbols"
            rows={payload.rows}
            showTopPagination
            sortState={tableSortState}
            tableClassName="data-table--blue"
            tableId={`${config.kind}-table`}
            totalRows={payload.total}
          />
        </section>
      </main>
    </div>
  );
}
