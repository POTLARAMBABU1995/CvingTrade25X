import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CvingLegacyHeader } from '@/components/navigation/CvingLegacyHeader';
import { fetchDashboardMovers } from '../../services/api/dashboardApi';
import { cn } from '../../lib/cn';
import { useTechnicalThemeMode } from '../technical/technicalPageGuards';

type UnknownRecord = Record<string, unknown>;
type LoadStatus = 'error' | 'loading' | 'online' | 'stale';

type DashboardMoverRow = {
  percentage: string;
  points: string;
  price: string;
  stock: string;
};

type DashboardBreadthRow = {
  advances: string;
  declines: string;
  index: string;
  segment: string;
  sNo: string;
  skip: string;
  total: string;
  unchanged: string;
};

type NormalizedDashboardPayload = {
  breadthRows: DashboardBreadthRow[];
  gainers: DashboardMoverRow[];
  losers: DashboardMoverRow[];
  tradingDate: string;
};

type DashboardPageProps = {
  disableFetch?: boolean;
  initialPayload?: unknown;
};

type DashboardKpiVariant = 'breadth' | 'gainers' | 'losers';
type TickerTone = 'down' | 'neutral' | 'up';

type TickerItem = {
  display: string;
  symbol: string;
  tone: TickerTone;
};

type TickerGroup = {
  items: TickerItem[];
  label: string;
};

type DashboardCacheEntry = {
  dateKey?: string | null;
  payload: unknown;
  ts: number;
};

type TickerCacheEntry = {
  dateKey?: string | null;
  moversPayload?: unknown;
  ts?: number;
};

type InitialDashboardState = {
  lastUpdatedAt: number | null;
  latestTradingDate: string | null;
  message: string;
  payload: unknown;
  status: LoadStatus;
  tickerPayload: unknown;
};

const DASHBOARD_CACHE_KEY = 'ct_dashboard_cache_v3';
const TICKER_CACHE_KEY = 'ct_ticker_cache_v2';
const DASHBOARD_CACHE_TTL_MS = 24 * 60 * 60 * 1000;
const AUTO_POLL_INTERVAL_MS = 150000;
const TICKER_LIMIT = 25;
const TICKER_SOURCE_LIMIT = 25;
const BREADTH_SEGMENT_ORDER = ['nifty50', 'next50', 'midcap', 'smallcap', 'nifty500', 'niftytotal'] as const;
const DASHBOARD_CARD_CLASS = 'cvt-dashboard-card dashboard-kpi-card flex h-full min-w-0 max-w-full flex-col overflow-hidden rounded-2xl p-4';
const DASHBOARD_TABLE_CLASS = 'app-data-table table-sticky-safe premium-table border-collapse text-[13px] md:text-[14px] dashboard-table--compact dashboard-table--premium dashboard-kpi-table';
const DASHBOARD_BREADTH_TABLE_CLASS = 'app-data-table table-sticky-safe premium-table border-collapse text-[13px] md:text-[14px] dashboard-table--compact dashboard-table--breadth dashboard-table--premium dashboard-breadth-table';

function asRecord(value: unknown): UnknownRecord {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as UnknownRecord : {};
}

function asArray(value: unknown): UnknownRecord[] {
  return Array.isArray(value) ? value.map(asRecord) : [];
}

function toNumber(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value === 'string') {
    const cleaned = value.replace(/[^0-9.-]+/g, '');
    if (!cleaned) return null;
    const parsed = Number(cleaned);
    return Number.isFinite(parsed) ? parsed : null;
  }
  if (value === null || value === undefined) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function pick(row: UnknownRecord, keys: readonly string[]): unknown {
  for (const key of keys) {
    const value = row[key];
    if (value !== null && value !== undefined && String(value).trim() !== '') return value;
  }
  return undefined;
}

function formatDecimal(value: unknown, digits = 2): string {
  const num = toNumber(value);
  return num === null ? '' : num.toFixed(digits);
}

function formatMagnitude(value: unknown, digits = 2, suffix = ''): string {
  const num = toNumber(value);
  return num === null ? '-' : `${Math.abs(num).toFixed(digits)}${suffix}`;
}

function formatTickerValue(value: unknown, digits = 2, suffix = ''): string {
  const num = toNumber(value);
  if (num === null) return '-';
  const sign = num < 0 ? '-' : '';
  return `${sign}${Math.abs(num).toFixed(digits)}${suffix}`;
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined || String(value).trim() === '') return '-';
  return String(value);
}

function breadthSegmentOf(row: UnknownRecord): string {
  return String(row.segment || '').trim().toLowerCase();
}

function isNiftyTotalRow(row: UnknownRecord): boolean {
  const segment = breadthSegmentOf(row);
  if (segment === 'niftytotal') return true;
  return String(pick(row, ['index']) || '').trim().toLowerCase() === 'niftytotal';
}

function determineSkipValue(row: UnknownRecord, fallbackTotal?: unknown): string {
  const direct = pick(row, ['skip']);
  const skip = toNumber(row.skip);
  return skip && skip > 0 ? String(skip) : '-';
}

function determineTotalValue(row: UnknownRecord, fallbackTotal?: unknown): string {
  const advances = toNumber(row.advances) ?? 0;
  const declines = toNumber(row.declines) ?? 0;
  const unchanged = toNumber(row.unchanged) ?? 0;
  const skip = toNumber(determineSkipValue(row, fallbackTotal)) ?? 0;
  const total = advances + declines + unchanged + skip;
  return Number.isFinite(total) ? String(total) : '-';
}

function normalizeMover(row: UnknownRecord): DashboardMoverRow {
  return {
    percentage: formatMagnitude(pick(row, ['percentage', 'percentChange', 'chg_pct']), 2, '%'),
    points: formatMagnitude(pick(row, ['points', 'change', 'chg'])),
    price: formatDecimal(pick(row, ['price', 'close', 'output'])),
    stock: formatCell(pick(row, ['stock', 'stockName', 'stockname', 'symbol'])),
  };
}

function breadthPayloadIsCurrent(payload: unknown): boolean {
  const rows = asArray(asRecord(payload).breadthRows);
  const segments = new Set(rows.map((row) => String(row.segment || '').trim().toLowerCase()).filter(Boolean));
  const required = ['nifty50', 'next50', 'midcap', 'smallcap', 'nifty500'];
  if (required.every((segment) => segments.has(segment))) return true;
  const constituent = ['nifty50', 'next50', 'midcap', 'smallcap'];
  const presentConstituents = constituent.filter((segment) => segments.has(segment)).length;
  return segments.has('nifty500') && presentConstituents >= 3;
}

function breadthSegments(payload: unknown): string[] {
  return asArray(asRecord(payload).breadthRows)
    .map((row) => breadthSegmentOf(row))
    .filter(Boolean)
    .sort();
}

function normalizeBreadthRows(payload: UnknownRecord): DashboardBreadthRow[] {
  const breadthRows = asArray(payload.breadthRows)
    .filter((row) => BREADTH_SEGMENT_ORDER.includes(breadthSegmentOf(row) as typeof BREADTH_SEGMENT_ORDER[number]))
    .sort((left, right) => BREADTH_SEGMENT_ORDER.indexOf(breadthSegmentOf(left) as typeof BREADTH_SEGMENT_ORDER[number]) - BREADTH_SEGMENT_ORDER.indexOf(breadthSegmentOf(right) as typeof BREADTH_SEGMENT_ORDER[number]));
  const rows: UnknownRecord[] = [...breadthRows];

  if (!rows.length) {
    const breadth = asRecord(payload.breadth);
    rows.push({
      advances: breadth.advances,
      declines: breadth.declines,
      index: 'Nifty500',
      segment: 'nifty500',
      sNo: 1,
      skip: breadth.skip,
      totalSymbols: breadth.totalSymbols,
      unchanged: breadth.unchanged,
    });
  }

  return rows.map((row, index) => ({
    advances: formatCell(row.advances),
    declines: formatCell(row.declines),
    index: formatCell(pick(row, ['index', 'segment']) ?? 'Index'),
    segment: formatCell(pick(row, ['segment']) ?? ''),
    sNo: formatCell(pick(row, ['sNo']) ?? index + 1),
    skip: determineSkipValue(row),
    total: determineTotalValue(row),
    unchanged: formatCell(row.unchanged),
  }));
}

export function normalizeDashboardPayload(payload: unknown, fallbackPayload?: unknown): NormalizedDashboardPayload {
  const source = asRecord(payload);
  const fallback = asRecord(fallbackPayload);
  const gainersSource = asArray(source.gainers).length ? source.gainers : fallback.gainers;
  const losersSource = asArray(source.losers).length ? source.losers : fallback.losers;
  return {
    breadthRows: normalizeBreadthRows(source),
    gainers: asArray(gainersSource).slice(0, 5).map(normalizeMover),
    losers: asArray(losersSource).slice(0, 5).map(normalizeMover),
    tradingDate: formatCell(source.tradingDate),
  };
}

function normalizeDateKey(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  const text = String(value).trim();
  if (!text || text === '-') return null;
  return text.length >= 10 ? text.slice(0, 10) : text;
}

function extractDashboardDateKey(payload: unknown): string | null {
  const source = asRecord(payload);
  const topLevel = normalizeDateKey(pick(source, ['tradingDate', 'tradeDate', 'ltcDate', 'ltc_date', 'LTC_DATE']));
  if (topLevel) return topLevel;

  const candidateRows = [
    ...asArray(source.gainers),
    ...asArray(source.losers),
    ...asArray(source.breadthRows),
  ];
  for (const row of candidateRows) {
    const rowDate = normalizeDateKey(pick(row, ['tradingDate', 'tradeDate', 'ltcDate', 'ltc_date', 'LTC_DATE']));
    if (rowDate) return rowDate;
  }
  return null;
}

function tickerArrow(value: unknown): string {
  const num = toNumber(value);
  if (num === null || num === 0) return '';
  return num > 0 ? '▲ ' : '▼ ';
}

function buildTickerList(items: UnknownRecord[], mode: 'percent' | 'points' | 'ratio'): string[] {
  return items.slice(0, TICKER_LIMIT).map((item) => {
    const symbol = formatCell(pick(item, ['symbol', 'stockName', 'stock']));
    if (symbol === '-') return '';
    const value = mode === 'ratio'
      ? pick(item, ['volumeRatio', 'volumeRatioSort'])
      : mode === 'points'
        ? pick(item, ['points', 'change'])
        : pick(item, ['percentage', 'percentChange']);
    const suffix = mode === 'ratio' ? 'x' : mode === 'percent' ? '%' : '';
    return `${symbol}: ${tickerArrow(value)}${formatTickerValue(value, 2, suffix)}`;
  }).filter(Boolean);
}

function tickerSegment(label: string, values: string[]): string {
  return `${label} (${values.length}): ${values.length ? values.join(', ') : '-'}`;
}

export function buildTickerSegments(moversPayload: unknown, _volumePayload?: unknown): string {
  const movers = asRecord(moversPayload);
  const gainers = asArray(movers.gainers);
  const losers = asArray(movers.losers);
  const combined = [...gainers, ...losers].sort((left, right) => {
    const leftValue = Math.abs(toNumber(pick(left, ['points', 'change'])) ?? 0);
    const rightValue = Math.abs(toNumber(pick(right, ['points', 'change'])) ?? 0);
    return rightValue - leftValue;
  });

  return [
    tickerSegment('Gainers', buildTickerList(gainers, 'percent')),
    tickerSegment('Losers', buildTickerList(losers, 'percent')),
    tickerSegment('Price Movers/Shockers', buildTickerList(combined, 'points')),
  ].join(' | ');
}

function tickerToneForValue(value: unknown): TickerTone {
  const num = toNumber(value);
  if (num === null || num === 0) return 'neutral';
  return num > 0 ? 'up' : 'down';
}

function buildTickerVisualItems(items: UnknownRecord[], mode: 'percent' | 'points' | 'ratio'): TickerItem[] {
  return items.slice(0, TICKER_LIMIT).map((item) => {
    const symbol = formatCell(pick(item, ['symbol', 'stockName', 'stock']));
    if (symbol === '-') return null;
    const value = mode === 'ratio'
      ? pick(item, ['volumeRatio', 'volumeRatioSort'])
      : mode === 'points'
        ? pick(item, ['points', 'change'])
        : pick(item, ['percentage', 'percentChange']);
    const suffix = mode === 'ratio' ? 'x' : mode === 'percent' ? '%' : '';
    return {
      display: formatTickerValue(value, 2, suffix),
      symbol,
      tone: tickerToneForValue(value),
    } satisfies TickerItem;
  }).filter((item): item is TickerItem => Boolean(item));
}

function buildTickerGroups(moversPayload: unknown, _volumePayload?: unknown): TickerGroup[] {
  const movers = asRecord(moversPayload);
  const gainers = asArray(movers.gainers);
  const losers = asArray(movers.losers);
  const combined = [...gainers, ...losers].sort((left, right) => {
    const leftValue = Math.abs(toNumber(pick(left, ['points', 'change'])) ?? 0);
    const rightValue = Math.abs(toNumber(pick(right, ['points', 'change'])) ?? 0);
    return rightValue - leftValue;
  });

  return [
    { items: buildTickerVisualItems(gainers, 'percent'), label: 'Gainers' },
    { items: buildTickerVisualItems(losers, 'percent'), label: 'Losers' },
    { items: buildTickerVisualItems(combined, 'points'), label: 'Price Movers/Shockers' },
  ];
}

export function shouldAnimateDashboardTicker(
  _tickerGroups: TickerGroup[],
): boolean {
  return true;
}

function TickerMarqueeContent({
  groups,
  hidden = false,
  keyPrefix,
}: {
  groups: TickerGroup[];
  hidden?: boolean;
  keyPrefix: string;
}) {
  const hasItems = groups.some((group) => group.items.length > 0);
  if (!hasItems) {
    return <span className="dashboard-react-ticker__content dashboard-react-ticker__content--fallback" aria-hidden={hidden || undefined}>Loading market movers...</span>;
  }
  return (
    <span className="dashboard-react-ticker__content dashboard-react-ticker__content--stream" aria-hidden={hidden || undefined}>
      {groups.map((group, groupIndex) => (
        <span key={`${keyPrefix}-${group.label}-${groupIndex}`} className="dashboard-react-ticker__group">
          <span className="dashboard-react-ticker__group-label">{group.label} ({group.items.length})</span>
          <span className="dashboard-react-ticker__group-divider">:</span>
          {group.items.length ? group.items.map((item, itemIndex) => (
            <span
              key={`${keyPrefix}-${group.label}-${item.symbol}-${itemIndex}`}
              className={cn(
                'dashboard-react-ticker__chip',
                item.tone === 'up' && 'dashboard-react-ticker__chip--up',
                item.tone === 'down' && 'dashboard-react-ticker__chip--down',
                item.tone === 'neutral' && 'dashboard-react-ticker__chip--neutral',
              )}
            >
              <span className="dashboard-react-ticker__symbol">{item.symbol}</span>
              <span className="dashboard-react-ticker__value">{item.display}</span>
            </span>
          )) : <span className="dashboard-react-ticker__chip dashboard-react-ticker__chip--neutral">-</span>}
        </span>
      ))}
    </span>
  );
}

function readCache<T>(key: string): T | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? JSON.parse(raw) as T : null;
  } catch {
    return null;
  }
}

function isFreshCacheTs(ts: unknown, now = Date.now()): ts is number {
  return typeof ts === 'number' && Number.isFinite(ts) && ts > 0 && now >= ts && now - ts < DASHBOARD_CACHE_TTL_MS;
}

function readFreshDashboardCache(): DashboardCacheEntry | null {
  const cached = readCache<DashboardCacheEntry>(DASHBOARD_CACHE_KEY);
  if (!cached?.payload || !isFreshCacheTs(cached.ts) || !breadthPayloadIsCurrent(cached.payload)) return null;
  return cached;
}

function readFreshTickerCache(): TickerCacheEntry | null {
  const cached = readCache<TickerCacheEntry>(TICKER_CACHE_KEY);
  if (!cached?.moversPayload || !isFreshCacheTs(cached.ts)) return null;
  return cached;
}

function writeCache(key: string, payload: unknown): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(key, JSON.stringify(payload));
  } catch {
    // localStorage is an optional fallback cache.
  }
}

function buildInitialDashboardState(initialPayload?: unknown): InitialDashboardState {
  if (initialPayload) {
    return {
      lastUpdatedAt: null,
      latestTradingDate: extractDashboardDateKey(initialPayload),
      message: 'Live',
      payload: initialPayload,
      status: 'online',
      tickerPayload: initialPayload,
    };
  }

  const cachedDashboard = readFreshDashboardCache();
  const cachedTicker = readFreshTickerCache();
  if (cachedDashboard?.payload) {
    return {
      lastUpdatedAt: cachedDashboard.ts,
      latestTradingDate: extractDashboardDateKey(cachedDashboard.payload),
      message: 'Live',
      payload: cachedDashboard.payload,
      status: 'online',
      tickerPayload: cachedTicker?.moversPayload ?? cachedDashboard.payload,
    };
  }

  return {
    lastUpdatedAt: null,
    latestTradingDate: null,
    message: 'Checking backend...',
    payload: null,
    status: 'loading',
    tickerPayload: null,
  };
}

function MiniTable({
  className,
  kind,
  rows,
  title,
}: {
  className?: string;
  kind?: 'green' | 'red';
  rows: DashboardMoverRow[];
  title: string;
}) {
  const variant: DashboardKpiVariant = kind === 'red' ? 'losers' : 'gainers';
  return (
    <section className={cn(DASHBOARD_CARD_CLASS, `dashboard-kpi-card--${variant}`, className)}>
      <div className="dashboard-kpi-card__header">
        <span className="dashboard-kpi-card__accent" aria-hidden="true" />
        <h3 className="cvt-dashboard-heading dashboard-kpi-card__title">{title}</h3>
      </div>
      <div className="premium-table-wrap">
        <table className={cn(DASHBOARD_TABLE_CLASS, kind === 'green' && 'dashboard-mini-table--green', kind === 'red' && 'dashboard-mini-table--red')}>
          <colgroup>
            <col className="dashboard-table__col--sno" data-col="sno" />
            <col className="dashboard-table__col--stock" data-col="stock" />
            <col className="dashboard-table__col--price" />
            <col className="dashboard-table__col--points" />
            <col className="dashboard-table__col--percentage" />
          </colgroup>
          <thead>
            <tr className="bg-sky-50 text-center text-sm uppercase tracking-wide text-slate-700">
              <th className="premium-col-index text-center" data-col="sno">S.NO</th>
              <th className="premium-col-text text-center dashboard-col-middle" data-col="stock">Stock</th>
              <th className="text-right">Price</th>
              <th className="text-right">Points</th>
              <th className="text-right dashboard-col-percentage">Percentage</th>
            </tr>
          </thead>
          <tbody>
            {rows.length ? rows.map((row, index) => (
              <tr key={`${row.stock}-${index}`} className="cvt-dashboard-row border-b border-slate-100 text-slate-900">
                <td className="text-center" data-col="sno">{index + 1}</td>
                <td className="premium-col-text text-center font-bold dashboard-col-middle" data-col="stock" title={row.stock}>{row.stock}</td>
                <td className="text-right">{row.price}</td>
                <td className="text-right">{row.points}</td>
                <td className="text-right font-black">{row.percentage}</td>
              </tr>
            )) : (
              <tr><td className="cvt-dashboard-muted py-6 text-center text-slate-500" colSpan={5}>No data</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function BreadthTable({ className, rows }: { className?: string; rows: DashboardBreadthRow[] }) {
  return (
    <section className={cn(DASHBOARD_CARD_CLASS, 'dashboard-kpi-card--breadth', className)}>
      <div className="dashboard-kpi-card__header">
        <span className="dashboard-kpi-card__accent" aria-hidden="true" />
        <h3 className="cvt-dashboard-heading dashboard-kpi-card__title">Market Breadth</h3>
      </div>
      <div className="premium-table-wrap">
        <table className={DASHBOARD_BREADTH_TABLE_CLASS}>
          <colgroup>
            <col className="dashboard-table__col--sno" data-col="sno" />
            <col className="dashboard-table__col--index" data-col="stock" />
            <col className="dashboard-table__col--advances" />
            <col className="dashboard-table__col--declines" />
            <col className="dashboard-table__col--unchanged" />
            <col className="dashboard-table__col--skip" />
            <col className="dashboard-table__col--total" />
          </colgroup>
          <thead>
            <tr className="bg-sky-50 text-center text-sm uppercase tracking-wide text-slate-700">
              <th className="premium-col-index" data-col="sno">S.NO</th>
              <th className="premium-col-text text-center dashboard-col-middle" data-col="stock">Index</th>
              <th>Advances</th>
              <th>Declines</th>
              <th>Unchanged</th>
              <th>Skip</th>
              <th>Total</th>
            </tr>
          </thead>
          <tbody>
            {rows.length ? rows.map((row) => (
              <tr key={`${row.sNo}-${row.index}`} className="cvt-dashboard-row border-b border-slate-100 text-center font-semibold text-slate-900">
                <td data-col="sno">{row.sNo}</td>
                <td className="premium-col-text text-center dashboard-col-middle" data-col="stock" title={row.index}>{row.index}</td>
                <td className="dashboard-breadth-table__advances">{row.advances}</td>
                <td className="dashboard-breadth-table__declines">{row.declines}</td>
                <td>{row.unchanged}</td>
                <td>{row.skip}</td>
                <td>{row.total}</td>
              </tr>
            )) : (
              <tr><td className="cvt-dashboard-muted py-6 text-center text-slate-500" colSpan={7}>No data</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function DashboardPage({ disableFetch = false, initialPayload }: DashboardPageProps) {
  const themeMode = useTechnicalThemeMode();
  const [initialState] = useState(() => buildInitialDashboardState(initialPayload));
  const [payload, setPayload] = useState<unknown>(initialState.payload);
  const [tickerPayload, setTickerPayload] = useState<unknown>(initialState.tickerPayload);
  const [status, setStatus] = useState<LoadStatus>(initialState.status);
  const [message, setMessage] = useState(initialState.message);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(initialState.lastUpdatedAt);
  const [refreshing, setRefreshing] = useState(false);
  const latestTradingDateRef = useRef<string | null>(initialState.latestTradingDate);

  const normalized = useMemo(() => normalizeDashboardPayload(payload, tickerPayload), [payload, tickerPayload]);
  const tickerGroups = useMemo(() => buildTickerGroups(tickerPayload), [tickerPayload]);
  const tickerText = useMemo(() => buildTickerSegments(tickerPayload), [tickerPayload]);

  const loadDashboard = useCallback(async (
    forceRefresh = false,
    signal?: AbortSignal,
    options: { silent?: boolean } = {},
  ): Promise<boolean> => {
    const silent = options.silent === true;
    if (!forceRefresh) {
      const cached = readFreshDashboardCache();
      if (cached?.payload) {
        setPayload(cached.payload);
        latestTradingDateRef.current = extractDashboardDateKey(cached.payload) ?? latestTradingDateRef.current;
        setLastUpdatedAt(cached.ts);
        setStatus('online');
        setMessage('Live');
        return false;
      }
    }
    if (!silent) {
      setStatus('loading');
      setMessage(forceRefresh ? 'Refreshing dashboard data...' : 'Loading dashboard data...');
    }
    try {
      const data = await fetchDashboardMovers<unknown>(forceRefresh ? { refresh: 1 } : {}, { signal });
      const payloadIsCurrent = breadthPayloadIsCurrent(data);
      const cached = readFreshDashboardCache();
      const latestDateKey = extractDashboardDateKey(data);
      const previousDateKey = latestTradingDateRef.current;
      const currentSegments = breadthSegments(payload);
      const nextSegments = breadthSegments(data);
      const sameSegmentShape = currentSegments.length === nextSegments.length && currentSegments.every((segment, index) => segment === nextSegments[index]);
      if (!forceRefresh && payloadIsCurrent && previousDateKey && latestDateKey && previousDateKey === latestDateKey && sameSegmentShape) {
        setStatus('online');
        setMessage('Live');
        return false;
      }
      if (payloadIsCurrent) {
        const now = Date.now();
        setPayload(data);
        latestTradingDateRef.current = latestDateKey ?? previousDateKey ?? null;
        setLastUpdatedAt(now);
        setStatus('online');
        setMessage('Live');
        writeCache(DASHBOARD_CACHE_KEY, { dateKey: latestDateKey, payload: data, ts: now });
        return true;
      } else if (cached?.payload) {
        setPayload(cached.payload);
        latestTradingDateRef.current = extractDashboardDateKey(cached.payload) ?? latestTradingDateRef.current;
        setLastUpdatedAt(cached.ts);
        setStatus('online');
        setMessage('Live');
        return true;
      } else {
        setStatus('stale');
        setMessage('Stale: dashboard response missing required breadth rows.');
        return false;
      }
    } catch (error) {
      if (error instanceof Error && /abort/i.test(error.message)) return false;
      const cached = readFreshDashboardCache();
      if (cached?.payload) {
        setPayload(cached.payload);
        latestTradingDateRef.current = extractDashboardDateKey(cached.payload) ?? latestTradingDateRef.current;
        setLastUpdatedAt(cached.ts);
        setStatus('online');
        setMessage('Live');
        return true;
      } else {
        setStatus('error');
        setMessage(error instanceof Error ? error.message : String(error));
        return false;
      }
    }
    return false;
  }, []);

  const loadTicker = useCallback(async (forceRefresh = false, signal?: AbortSignal) => {
    const cached = readFreshTickerCache();
    if (!forceRefresh && cached?.moversPayload) {
      setTickerPayload(cached.moversPayload);
      return;
    }
    try {
      const moversData = await fetchDashboardMovers<unknown>(
        { limit: TICKER_SOURCE_LIMIT, segment: 'nifty500', ...(forceRefresh ? { refresh: 1 } : {}) },
        { signal },
      );
      setTickerPayload(moversData ?? null);
      if (moversData) {
        writeCache(TICKER_CACHE_KEY, { dateKey: extractDashboardDateKey(moversData), moversPayload: moversData, ts: Date.now() });
      }
    } catch (error) {
      if (error instanceof Error && /abort/i.test(error.message)) return;
      setTickerPayload(cached?.moversPayload ?? null);
    }
  }, []);

  useEffect(() => {
    if (disableFetch) return undefined;
    const controller = new AbortController();
    void loadDashboard(false, controller.signal);
    void loadTicker(false, controller.signal);
    let pollInFlight = false;
    const pollId = window.setInterval(() => {
      if (document.visibilityState && document.visibilityState !== 'visible') return;
      if (pollInFlight) return;
      pollInFlight = true;
      void (async () => {
        try {
          const dashboardChanged = await loadDashboard(false, undefined, { silent: true });
          if (dashboardChanged) {
            await loadTicker(false);
          }
        } finally {
          pollInFlight = false;
        }
      })();
    }, AUTO_POLL_INTERVAL_MS);
    return () => {
      controller.abort();
      window.clearInterval(pollId);
    };
  }, [disableFetch, loadDashboard, loadTicker]);

  async function refresh() {
    setRefreshing(true);
    try {
      await Promise.allSettled([loadDashboard(true), loadTicker(true)]);
    } finally {
      setRefreshing(false);
    }
  }

  const statusClass = status === 'online'
    ? 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-800/80 dark:bg-emerald-950/60 dark:text-emerald-300'
    : status === 'loading'
      ? 'border-sky-200 bg-sky-50 text-sky-800 dark:border-sky-800/80 dark:bg-sky-950/60 dark:text-sky-300'
      : 'border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-800/80 dark:bg-rose-950/60 dark:text-rose-300';
  const metaText = [
    normalized.tradingDate !== '-' ? `Trading Date: ${normalized.tradingDate}` : '',
    lastUpdatedAt ? `Updated: ${new Date(lastUpdatedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}` : '',
  ].filter(Boolean).join(' | ');

  const isDark = themeMode === 'dark';

  return (
    <div className={cn(
      'dashboard-react-page legacy-react-shell fundamental-app flex h-screen min-h-0 flex-col overflow-hidden text-slate-950 dark:text-slate-100',
      isDark
        ? 'dashboard-react-page--dark bg-[radial-gradient(circle_at_18%_18%,rgba(59,130,246,0.16),transparent_22%),radial-gradient(circle_at_82%_16%,rgba(20,184,166,0.12),transparent_20%),radial-gradient(circle_at_50%_92%,rgba(99,102,241,0.12),transparent_24%),linear-gradient(180deg,#020617_0%,#0f172a_100%)] text-slate-100'
        : 'bg-[radial-gradient(circle_at_14%_4%,rgba(255,255,255,0.96),transparent_34%),radial-gradient(circle_at_86%_8%,rgba(191,219,254,0.32),transparent_34%),linear-gradient(180deg,#f5f9ff_0%,#eaf2ff_56%,#eef4ff_100%)] text-slate-950',
    )}>
      <CvingLegacyHeader activeSection="dashboard" />
      <main className="dashboard-react-main flex w-full max-w-none flex-1 flex-col overflow-hidden px-4 py-2 md:px-5 lg:px-6">
        <section className="dashboard-status-bar my-1 flex flex-wrap items-center gap-3">
          <span className={cn('rounded-full border px-3 py-1 text-sm font-black', statusClass)} title={message}>
            {status === 'online' ? 'Live' : status === 'loading' ? 'Syncing' : status === 'stale' ? 'Stale' : 'Check'}
          </span>
          <span className="cvt-dashboard-muted rounded-full border border-slate-200 bg-white px-3 py-1 text-sm font-bold text-slate-700 dark:border-slate-700 dark:bg-slate-900/90 dark:text-slate-200">{metaText}</span>
          <button
            className="rounded-full border border-sky-200 bg-sky-50 px-4 py-2 text-sm font-black text-sky-800 disabled:opacity-60 dark:border-sky-800/80 dark:bg-sky-950/60 dark:text-sky-300"
            type="button"
            disabled={refreshing}
            onClick={() => void refresh()}
          >
            {refreshing ? 'Refreshing' : 'Refresh'}
          </button>
          <span className="cvt-dashboard-muted text-sm font-semibold text-slate-600 dark:text-slate-400">{message}</span>
        </section>

        <section className="dashboard-kpi-grid grid w-full min-w-0 items-stretch gap-3 md:grid-cols-2 xl:grid-cols-[minmax(370px,1fr)_minmax(370px,1fr)_minmax(520px,1.3fr)]">
          <MiniTable kind="green" rows={normalized.gainers} title="Nifty50 Top 5 Gainers" />
          <MiniTable kind="red" rows={normalized.losers} title="Nifty50 Top 5 Losers" />
          <BreadthTable className="md:col-span-2 xl:col-span-1" rows={normalized.breadthRows} />
        </section>

        <section
          className="dashboard-react-ticker mt-auto flex h-[96px] w-full max-w-full items-center overflow-hidden border border-slate-200 font-bold text-slate-900 dark:border-slate-700 dark:text-slate-100"
          title={tickerText || 'Loading market movers...'}
        >
          <div className="dashboard-react-ticker__track">
            <TickerMarqueeContent groups={tickerGroups} keyPrefix="primary" />
            <TickerMarqueeContent groups={tickerGroups} hidden keyPrefix="shadow" />
          </div>
        </section>
      </main>
    </div>
  );
}
