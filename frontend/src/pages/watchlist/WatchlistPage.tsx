import { useEffect, useMemo, useRef, useState } from 'react';
import { CvingLegacyHeader } from '../../components/navigation/CvingLegacyHeader';
import { StrategyToolbar } from '../../components/strategy/StrategyToolbar';
import { TrashIcon } from '../../components/ui/Icons';
import { cn } from '../../lib/cn';
import { handleInternalNavigationClick } from '../../utils/internalNavigation';
import { normalizeDisplaySymbol } from '../../utils/symbols';
import { fetchSymbols } from '../../api/symbols';
import { fetchWatchlistDataRow, type WatchlistDataRow, type WatchlistLevelSource, type WatchlistSetupState, type WatchlistSourceState, type WatchlistSourceStatus, validateNseWatchlistSymbol } from '../../services/api/watchlistData';
import { fetchPriceActionManualPayload, savePriceActionManualPayload } from '../../services/api/technicalApi';
import type { PriceActionManualLevelWire } from '../../types/api/technical';
import { useTechnicalThemeMode } from '../technical/technicalPageGuards';

type SetupState = WatchlistSetupState;
type TableTab = 'overview' | 'targets' | 'levels' | 'confirmation';
type WatchlistRow = WatchlistDataRow;
type ManualSrLevel = { levelId: string; value: string };
type ManualSrModal = { error: string; levels: ManualSrLevel[]; mode: 'edit' | 'insert'; selectedLevelId: string; symbol: string; value: string };

const WATCHLIST_STORAGE_KEY = 'ct_watchlist_strategy_symbols_v1';
const MAIN_NSE_SYMBOLS_CACHE_KEY = 'ct_watchlist_main_nse_symbols_v1';
const WATCHLIST_ROWS_SESSION_CACHE_KEY = 'ct_watchlist_strategy_rows_snapshot_v1';
const WATCHLIST_ROWS_SESSION_CACHE_TTL_MS = 24 * 60 * 60 * 1000;

type WatchlistPageProps = {
  initialSymbols?: readonly string[];
};

export function normalizeWatchlistSymbols(values: readonly unknown[]): string[] {
  return Array.from(new Set(values.map(normalizeDisplaySymbol).filter(Boolean)));
}

function sortNseSymbols(values: readonly unknown[]): string[] {
  return normalizeWatchlistSymbols(values)
    .sort((left, right) => left.localeCompare(right, undefined, { sensitivity: 'base' }));
}

function hydrateManualSrLevel(level: PriceActionManualLevelWire): ManualSrLevel {
  return { levelId: String(level.level_id || ''), value: String(level.value ?? '') };
}

function readCachedMainNseSymbols(): string[] {
  if (typeof window === 'undefined') return [];
  try {
    const parsed = JSON.parse(window.localStorage.getItem(MAIN_NSE_SYMBOLS_CACHE_KEY) || '{}') as { symbols?: unknown };
    return Array.isArray(parsed.symbols) ? sortNseSymbols(parsed.symbols) : [];
  } catch {
    return [];
  }
}

function persistMainNseSymbols(symbols: readonly string[]): void {
  if (typeof window === 'undefined' || !symbols.length) return;
  try {
    window.localStorage.setItem(MAIN_NSE_SYMBOLS_CACHE_KEY, JSON.stringify({ symbols, updatedAt: new Date().toISOString() }));
  } catch {
    // Browser storage is optional; a live symbol response remains usable.
  }
}

function emptyWatchlistRow(symbol: string, sector = '-'): WatchlistRow {
  return {
    confidence: 0,
    delivery: 0,
    entryHigh: 0,
    entryLow: 0,
    ffmc: '-',
    index: '-',
    ltp: 0,
    mcap: '-',
    pattern: 'Awaiting existing technical sources',
    resistance: [0, 0, 0],
    resistanceSources: ['DYNAMIC', 'DYNAMIC', 'DYNAMIC'],
    sector,
    sectorTrend: '-',
    setup: 'DEVELOPING',
    sourceStatus: {
      bars: 'LOADING', delivery: 'LOADING', metadata: 'LOADING', sectorWise: 'LOADING',
      sr: 'LOADING', targetHistory: 'LOADING', technical: 'LOADING', volume: 'LOADING',
    },
    strongResistance: 0,
    strongResistanceSource: 'DYNAMIC',
    strongSupport: 0,
    strongSupportSource: 'DYNAMIC',
    support: [0, 0, 0],
    supportSources: ['DYNAMIC', 'DYNAMIC', 'DYNAMIC'],
    symbol,
    targetDays: [0, 0, 0],
    targetPrices: [0, 0, 0],
    targetSources: ['DYNAMIC', 'DYNAMIC', 'DYNAMIC'],
    trend: '-',
    volumeRatio: 0,
  };
}

function cleanCachedText(value: unknown, fallback: string): string {
  const text = String(value ?? '').trim();
  const normalized = text.toLowerCase();
  return text && !normalized.includes('load failed') && !normalized.includes('request failed') && !normalized.includes('error')
    ? text
    : fallback;
}

function normalizeCachedWatchlistRow(symbol: string, value: unknown): WatchlistRow {
  const fallback = emptyWatchlistRow(symbol);
  if (!value || typeof value !== 'object' || Array.isArray(value)) return fallback;
  const row = value as Partial<WatchlistRow>;
  const normalizedRow = {
    ...fallback,
    ...row,
    resistanceSources: row.resistanceSources || fallback.resistanceSources,
    sourceStatus: { ...fallback.sourceStatus, ...row.sourceStatus },
    strongResistanceSource: row.strongResistanceSource || fallback.strongResistanceSource,
    strongSupportSource: row.strongSupportSource || fallback.strongSupportSource,
    supportSources: row.supportSources || fallback.supportSources,
    symbol,
    targetPrices: row.targetPrices || row.resistance || fallback.targetPrices,
    targetSources: row.targetSources || fallback.targetSources,
  };
  return {
    ...normalizedRow,
    ffmc: cleanCachedText(normalizedRow.ffmc, fallback.ffmc),
    index: cleanCachedText(normalizedRow.index, fallback.index),
    mcap: cleanCachedText(normalizedRow.mcap, fallback.mcap),
    pattern: cleanCachedText(normalizedRow.pattern, fallback.pattern),
    sector: cleanCachedText(normalizedRow.sector, fallback.sector),
    sectorTrend: cleanCachedText(normalizedRow.sectorTrend, fallback.sectorTrend),
    trend: cleanCachedText(normalizedRow.trend, fallback.trend),
  };
}

function mergeNumber(previous: number, next: number): number {
  return next > 0 ? next : previous;
}

function mergeText(previous: string, next: string): string {
  return next && next !== '-' && !next.startsWith('Awaiting ') ? next : previous;
}

function mergeNumberTuple(previous: [number, number, number], next: [number, number, number]): [number, number, number] {
  return [mergeNumber(previous[0], next[0]), mergeNumber(previous[1], next[1]), mergeNumber(previous[2], next[2])];
}

function mergeWatchlistRow(previous: WatchlistRow | undefined, next: WatchlistRow): WatchlistRow {
  if (!previous) return next;
  return {
    ...next,
    confidence: mergeNumber(previous.confidence, next.confidence),
    delivery: mergeNumber(previous.delivery, next.delivery),
    entryHigh: mergeNumber(previous.entryHigh, next.entryHigh),
    entryLow: mergeNumber(previous.entryLow, next.entryLow),
    ffmc: mergeText(previous.ffmc, next.ffmc),
    index: mergeText(previous.index, next.index),
    ltp: mergeNumber(previous.ltp, next.ltp),
    mcap: mergeText(previous.mcap, next.mcap),
    pattern: mergeText(previous.pattern, next.pattern),
    resistance: mergeNumberTuple(previous.resistance, next.resistance),
    sector: mergeText(previous.sector, next.sector),
    sectorTrend: mergeText(previous.sectorTrend, next.sectorTrend),
    strongResistance: mergeNumber(previous.strongResistance, next.strongResistance),
    strongSupport: mergeNumber(previous.strongSupport, next.strongSupport),
    support: mergeNumberTuple(previous.support, next.support),
    targetDays: mergeNumberTuple(previous.targetDays, next.targetDays),
    targetPrices: mergeNumberTuple(previous.targetPrices, next.targetPrices),
    trend: mergeText(previous.trend, next.trend),
    volumeRatio: mergeNumber(previous.volumeRatio, next.volumeRatio),
  };
}

function readStoredSymbols(): string[] {
  if (typeof window === 'undefined') return [];
  try {
    const stored = JSON.parse(window.localStorage.getItem(WATCHLIST_STORAGE_KEY) || '[]');
    return normalizeWatchlistSymbols(Array.isArray(stored) ? stored : []);
  } catch {
    return [];
  }
}

function persistSymbols(symbols: readonly string[]): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(WATCHLIST_STORAGE_KEY, JSON.stringify(symbols));
  } catch {
    // Browser storage is optional; the visible list still works in memory.
  }
}

type WatchlistRowsSessionSnapshot = {
  rows: Record<string, WatchlistRow>;
  updatedAt: Date | null;
};

function readWatchlistRowsSessionSnapshot(): WatchlistRowsSessionSnapshot {
  if (typeof window === 'undefined') return { rows: {}, updatedAt: null };
  try {
    const cached = JSON.parse(window.localStorage.getItem(WATCHLIST_ROWS_SESSION_CACHE_KEY) || '{}') as {
      rows?: unknown;
      updatedAt?: unknown;
    };
    const updatedAt = typeof cached.updatedAt === 'string' ? new Date(cached.updatedAt) : null;
    if (!updatedAt || Number.isNaN(updatedAt.getTime()) || Date.now() - updatedAt.getTime() > WATCHLIST_ROWS_SESSION_CACHE_TTL_MS || !cached.rows || typeof cached.rows !== 'object' || Array.isArray(cached.rows)) {
      window.localStorage.removeItem(WATCHLIST_ROWS_SESSION_CACHE_KEY);
      return { rows: {}, updatedAt: null };
    }
    return {
      rows: Object.fromEntries(Object.entries(cached.rows as Record<string, unknown>)
        .map(([symbol, row]) => [symbol, normalizeCachedWatchlistRow(symbol, row)])),
      updatedAt,
    };
  } catch {
    return { rows: {}, updatedAt: null };
  }
}

function persistWatchlistRowsSessionSnapshot(symbols: readonly string[], rows: Record<string, WatchlistRow>): void {
  if (typeof window === 'undefined') return;
  try {
    const activeRows = Object.fromEntries(symbols.flatMap((symbol) => rows[symbol] ? [[symbol, rows[symbol]]] : []));
    if (!Object.keys(activeRows).length) {
      window.localStorage.removeItem(WATCHLIST_ROWS_SESSION_CACHE_KEY);
      return;
    }
    window.localStorage.setItem(WATCHLIST_ROWS_SESSION_CACHE_KEY, JSON.stringify({ rows: activeRows, updatedAt: new Date().toISOString() }));
  } catch {
    // Browser storage is optional; live source results remain usable.
  }
}

const setupLabel: Record<SetupState, string> = {
  BREAKOUT_CONFIRMED: 'Breakout confirmed',
  DEVELOPING: 'Developing',
  NEAR_SUPPORT: 'Near strong support',
  RETEST_ENTRY_ZONE: 'Retest entry zone',
  RISK_WARNING: 'Breakdown risk',
};

function formatPrice(value: number): string {
  return value > 0 ? `₹${value.toLocaleString('en-IN', { maximumFractionDigits: 2 })}` : '-';
}

function LevelSourceBadge({ source }: { source: WatchlistLevelSource }) {
  return <span className={cn('mt-1 block text-[10px] font-black tracking-wide', source === 'MANUAL' ? 'text-emerald-700 dark:text-emerald-300' : 'text-sky-700 dark:text-sky-300')}>{source}</span>;
}

function sourceStateLabel(state: WatchlistSourceState): string {
  if (state === 'LOADING') return 'Loading…';
  if (state === 'LOAD_FAILED' || state === 'NOT_AVAILABLE') return 'No Data';
  return 'Loaded';
}

export function missingWatchlistValueLabel(state: WatchlistSourceState): string {
  return sourceStateLabel(state === 'LOADED' ? 'NOT_AVAILABLE' : state);
}

function combinedSourceState(...states: WatchlistSourceState[]): WatchlistSourceState {
  if (states.some((state) => state === 'LOADING')) return 'LOADING';
  if (states.some((state) => state === 'LOAD_FAILED')) return 'LOAD_FAILED';
  if (states.some((state) => state === 'LOADED')) return 'LOADED';
  return 'NOT_AVAILABLE';
}

function MissingData({ state }: { state: WatchlistSourceState }) {
  const displayState = state === 'LOADED' ? 'NOT_AVAILABLE' : state;
  return <span className={cn('whitespace-nowrap text-xs font-bold', displayState === 'LOAD_FAILED' ? 'text-slate-500 dark:text-slate-400' : 'text-slate-500 dark:text-slate-400')}>{missingWatchlistValueLabel(state)}</span>;
}

function LevelCell({ price, source, state }: { price: number; source: WatchlistLevelSource; state: WatchlistSourceState }) {
  return price > 0 ? <span className="inline-block whitespace-nowrap font-bold">{formatPrice(price)}<LevelSourceBadge source={source} /></span> : <MissingData state={state} />;
}

function TargetCell({ day, durationState, entry, price, source, state }: { day: number; durationState: WatchlistSourceState; entry: number; price: number; source: WatchlistLevelSource; state: WatchlistSourceState }) {
  if (entry <= 0 || price <= 0) return <MissingData state={state} />;
  const points = price - entry;
  const upside = (points / entry) * 100;
  const durationLabel = day > 0
    ? `${day} TD`
    : durationState === 'LOADING'
      ? 'Calculating…'
      : durationState === 'LOAD_FAILED'
        ? 'Estimate unavailable'
        : 'Estimate unavailable';
  return (
    <span className="whitespace-nowrap text-xs font-bold text-slate-700 dark:text-slate-200">
      {formatPrice(price)} <span className="text-emerald-700 dark:text-emerald-300">{points >= 0 ? '+' : ''}₹{points.toFixed(0)} · {upside >= 0 ? '+' : ''}{upside.toFixed(1)}%</span> · {durationLabel}<LevelSourceBadge source={source} />
    </span>
  );
}

function SourceStatusStrip({ row, tab }: { row: WatchlistRow; tab: TableTab }) {
  const sourceKeys: Array<[keyof WatchlistSourceStatus, string]> = tab === 'overview'
    ? [['bars', 'Bars'], ['metadata', 'NSE Metadata'], ['sectorWise', 'Sector Rotation'], ['technical', 'Technicals']]
    : tab === 'targets'
      ? [['bars', 'Bars'], ['sr', 'S&R'], ['targetHistory', 'OHLCV History']]
      : tab === 'levels'
        ? [['sr', 'S&R']]
        : [['volume', 'Volume'], ['delivery', 'Delivery'], ['technical', 'Technicals']];
  return (
    <div className="flex flex-wrap gap-2 border-b border-slate-200 px-3 py-2 text-[11px] font-black dark:border-slate-700" data-testid="watchlist-source-status">
      {sourceKeys.map(([key, label]) => {
        const state = row.sourceStatus[key];
        return <span key={key} className={cn('rounded-full border px-2 py-1', state === 'LOADED' ? 'border-emerald-500 text-emerald-700 dark:text-emerald-300' : state === 'LOAD_FAILED' ? 'border-amber-500 text-amber-700 dark:text-amber-300' : 'border-slate-400 text-slate-500 dark:text-slate-300')}>{label}: {sourceStateLabel(state)}</span>;
      })}
    </div>
  );
}

function Kpi({ label, value, tone }: { label: string; value: number; tone: 'emerald' | 'amber' | 'blue' | 'sky' }) {
  const toneClass = {
    amber: 'border-amber-200 bg-amber-50 text-amber-950 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100',
    blue: 'border-blue-200 bg-blue-50 text-blue-950 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-100',
    emerald: 'border-emerald-200 bg-emerald-50 text-emerald-950 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-100',
    sky: 'border-sky-200 bg-sky-50 text-sky-950 dark:border-sky-800 dark:bg-sky-950/40 dark:text-sky-100',
  }[tone];
  return <article className={cn('rounded-2xl border p-4 shadow-sm', toneClass)}><div className="text-3xl font-black">{value}</div><div className="mt-1 text-sm font-bold">{label}</div></article>;
}

function SelectedAnalysisContent({ row, tab, midpoint, onManual }: { row: WatchlistRow; tab: string; midpoint: number; onManual: (mode: 'edit' | 'insert') => void }) {
  if (tab === 'Overview') {
    return <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4"><Kpi label={`Strong buying zone · ${formatPrice(row.strongSupport)}`} tone="emerald" value={row.strongSupport > 0 ? 1 : 0} /><Kpi label={`Strong selling zone · ${formatPrice(row.strongResistance)}`} tone="blue" value={row.strongResistance > 0 ? 1 : 0} /><Kpi label={`Available upside to T1 · ${midpoint > 0 && row.targetPrices[0] > 0 ? `${(((row.targetPrices[0] - midpoint) / midpoint) * 100).toFixed(1)}%` : 'No Data'}`} tone="sky" value={row.targetDays[0]} /><Kpi label="Historical estimate (trading days)" tone="amber" value={row.targetDays[1]} /></div>;
  }
  if (tab === 'S&R Ladder') {
    return <div className="grid gap-4 md:grid-cols-2"><div><h3 className="font-black text-emerald-700 dark:text-emerald-300">Support</h3><div className="mt-2 grid gap-2">{row.support.map((value, index) => <div key={`analysis-support-${index}`} className="rounded-lg border p-3 font-bold">S{index + 1}: {value > 0 ? formatPrice(value) : <MissingData state={row.sourceStatus.sr} />}</div>)}<div className="rounded-lg border-2 border-emerald-600 p-3 font-black">Strong Support: {row.strongSupport > 0 ? formatPrice(row.strongSupport) : <MissingData state={row.sourceStatus.sr} />}</div></div></div><div><h3 className="font-black text-sky-700 dark:text-sky-300">Resistance</h3><div className="mt-2 grid gap-2">{row.resistance.map((value, index) => <div key={`analysis-resistance-${index}`} className="rounded-lg border p-3 font-bold">R{index + 1}: {value > 0 ? formatPrice(value) : <MissingData state={row.sourceStatus.sr} />}</div>)}<div className="rounded-lg border-2 border-sky-600 p-3 font-black">Strong Resistance: {row.strongResistance > 0 ? formatPrice(row.strongResistance) : <MissingData state={row.sourceStatus.sr} />}</div></div></div></div>;
  }
  if (tab === 'Chart & Evidence') {
    return <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{[['LTP', row.ltp > 0 ? formatPrice(row.ltp) : 'No Data'], ['Trend', row.trend], ['Sector trend', row.sectorTrend], ['Pattern', row.pattern], ['Volume ratio', row.volumeRatio > 0 ? `${row.volumeRatio.toFixed(1)}x` : 'No Data'], ['Delivery', row.delivery > 0 ? `${row.delivery.toFixed(1)}%` : 'No Data'], ['Confidence', row.confidence > 0 ? `${row.confidence}%` : 'No Data'], ['Setup', setupLabel[row.setup]]].map(([label, value]) => <div key={label} className="rounded-lg border p-3"><div className="text-xs font-black uppercase text-slate-500">{label}</div><div className="mt-1 font-bold">{value}</div></div>)}</div>;
  }
  if (tab === 'Swing & Duration') {
    return <div className="grid gap-3 md:grid-cols-3">{row.targetPrices.map((price, index) => <div key={`analysis-target-${index}`} className="rounded-lg border p-4"><div className="font-black">T{index + 1}</div><div className="mt-2 text-lg font-bold">{price > 0 ? formatPrice(price) : 'No Data'}</div><div className="text-sm text-slate-500">{row.targetDays[index] > 0 ? `${row.targetDays[index]} trading days` : 'No Data'}</div></div>)}</div>;
  }
  if (tab === 'Manual S&R Editor') {
    return <div><p className="text-sm text-slate-600 dark:text-slate-300">Manual levels are read from the existing Price Action S&amp;R database table.</p><div className="mt-4 flex gap-2"><button type="button" className="rounded-lg border border-sky-600 px-4 py-2 font-bold text-sky-800 dark:text-sky-300" onClick={() => onManual('edit')}>Edit</button><button type="button" className="rounded-lg bg-emerald-700 px-4 py-2 font-bold text-white" onClick={() => onManual('insert')}>Insert</button></div></div>;
  }
  return <div className="grid gap-3 sm:grid-cols-2"><div className="rounded-lg border p-4"><div className="text-xs font-black uppercase text-slate-500">Setup</div><div className="mt-1 font-bold">{setupLabel[row.setup]}</div></div><div className="rounded-lg border p-4"><div className="text-xs font-black uppercase text-slate-500">Sources</div><div className="mt-1 font-bold">Bars: {sourceStateLabel(row.sourceStatus.bars)} · S&amp;R: {sourceStateLabel(row.sourceStatus.sr)}</div></div></div>;
}

export function WatchlistPage({ initialSymbols }: WatchlistPageProps = {}) {
  const themeMode = useTechnicalThemeMode();
  const [sessionSnapshot] = useState(readWatchlistRowsSessionSnapshot);
  const [symbols, setSymbols] = useState<string[]>(() => initialSymbols === undefined
    ? readStoredSymbols()
    : normalizeWatchlistSymbols(initialSymbols));
  const [symbolInput, setSymbolInput] = useState('');
  const [availableSymbols, setAvailableSymbols] = useState<string[]>(readCachedMainNseSymbols);
  const [isSymbolMenuOpen, setIsSymbolMenuOpen] = useState(false);
  const [symbolSearch, setSymbolSearch] = useState('');
  const [editingSymbol, setEditingSymbol] = useState('');
  const [addMessage, setAddMessage] = useState('');
  const [savingSymbol, setSavingSymbol] = useState(false);
  const [toolbarSearch, setToolbarSearch] = useState('');
  const [toolbarRefreshing, setToolbarRefreshing] = useState(false);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(sessionSnapshot.updatedAt);
  const [resolvedRows, setResolvedRows] = useState<Record<string, WatchlistRow>>(sessionSnapshot.rows);
  const hydratingSymbols = useRef(new Map<string, Promise<void>>());
  const selectedHydrationController = useRef<AbortController | null>(null);
  const toolbarRefreshSequence = useRef(0);
  const symbolMenuRef = useRef<HTMLDivElement>(null);
  const [setup, setSetup] = useState<'ALL' | SetupState>('ALL');
  const [tableTab, setTableTab] = useState<TableTab>('overview');
  const [selectedSymbol, setSelectedSymbol] = useState(() => symbols[0] || '');
  const [drawerTab, setDrawerTab] = useState('Overview');
  const [manualSrModal, setManualSrModal] = useState<ManualSrModal | null>(null);
  const watchlistRows = useMemo(() => symbols
    .map((symbol) => resolvedRows[symbol] || emptyWatchlistRow(symbol)), [resolvedRows, symbols]);
  const filteredRows = useMemo(() => {
    const query = toolbarSearch.trim().toLowerCase();
    return watchlistRows.filter((row) => {
      if (setup !== 'ALL' && row.setup !== setup) return false;
      if (!query) return true;
      return [row.symbol, row.sector, row.index, row.trend, row.sectorTrend, row.pattern, setupLabel[row.setup]]
        .some((value) => String(value || '').toLowerCase().includes(query));
    });
  }, [setup, toolbarSearch, watchlistRows]);
  // Keep every saved row visible. The selected symbol controls the source
  // badges and analysis drawer; it must not hide snapshot-backed rows from
  // the cards or any table tab while live sources hydrate in the background.
  const displayedRows = filteredRows;
  const filteredAvailableSymbols = useMemo(() => {
    const query = symbolSearch.trim().toUpperCase();
    return query ? availableSymbols.filter((symbol) => symbol.includes(query)) : availableSymbols;
  }, [availableSymbols, symbolSearch]);
  const selected = watchlistRows.find((row) => row.symbol === selectedSymbol) || watchlistRows[0] || null;
  const midpoint = selected ? (selected.entryLow + selected.entryHigh) / 2 : 0;
  const kpis = {
    breakout: watchlistRows.filter((row) => row.setup === 'BREAKOUT_CONFIRMED' || row.setup === 'RETEST_ENTRY_ZONE').length,
    momentum: watchlistRows.filter((row) => row.trend.includes('Bullish') || row.trend.includes('bullish')).length,
    nearSupport: watchlistRows.filter((row) => row.setup === 'NEAR_SUPPORT' || row.setup === 'RETEST_ENTRY_ZONE').length,
    risk: watchlistRows.filter((row) => row.setup === 'RISK_WARNING').length,
  };

  const hydrateSymbol = (symbol: string, sector = '-', force = false, signal?: AbortSignal): Promise<void> => {
    if (!force && resolvedRows[symbol]) return Promise.resolve();
    const existing = hydratingSymbols.current.get(symbol);
    if (existing) return existing;
    const request = (async () => {
      const applyRow = (row: WatchlistRow) => {
        setResolvedRows((current) => ({
          ...current,
          [symbol]: mergeWatchlistRow(current[symbol], { ...row, sector: row.sector === '-' ? sector : row.sector }),
        }));
      };
      try {
        const row = await fetchWatchlistDataRow(symbol, applyRow, { returnAfterInitial: true, signal });
        const hasVisibleData = row.ltp > 0
          || row.entryHigh > 0
          || row.sector !== '-'
          || row.trend !== '-'
          || row.support.some((value) => value > 0)
          || row.resistance.some((value) => value > 0);
        if (hasVisibleData) applyRow(row);
      } catch (error) {
        if (signal?.aborted) return;
        setResolvedRows((current) => ({
          ...current,
          [symbol]: {
            ...emptyWatchlistRow(symbol, sector),
            pattern: current[symbol]?.pattern || 'Awaiting existing technical sources',
          },
        }));
      } finally {
        setLastRefreshedAt(new Date());
      }
    })();
    hydratingSymbols.current.set(symbol, request);
    void request.finally(() => {
      if (hydratingSymbols.current.get(symbol) === request) hydratingSymbols.current.delete(symbol);
    });
    return request;
  };

  const startSelectedHydration = (symbol: string, sector = '-'): Promise<void> => {
    selectedHydrationController.current?.abort('Watchlist symbol changed');
    const controller = new AbortController();
    selectedHydrationController.current = controller;
    return hydrateSymbol(symbol, sector, true, controller.signal);
  };

  const refreshWatchlist = async () => {
    if (!symbols.length) return;
    const refreshSequence = ++toolbarRefreshSequence.current;
    setToolbarRefreshing(true);
    try {
      await Promise.all(symbols.map((symbol) => hydrateSymbol(symbol, '-', true)));
      setLastRefreshedAt(new Date());
    } finally {
      if (toolbarRefreshSequence.current === refreshSequence) setToolbarRefreshing(false);
    }
  };

  const selectWatchlistSymbol = (symbol: string) => {
    setSelectedSymbol(symbol);
  };

  const openManualSrModal = async (symbol: string, mode: 'edit' | 'insert') => {
    setSelectedSymbol(symbol);
    setManualSrModal({ error: '', levels: [], mode, selectedLevelId: '', symbol, value: '' });
    try {
      const payload = await fetchPriceActionManualPayload();
      const source = payload.rows?.find((item) => normalizeDisplaySymbol(item.symbol || item.stock) === symbol);
      const levels = (source?.levels || []).map(hydrateManualSrLevel).filter((level) => level.levelId && level.value);
      setManualSrModal((current) => current ? { ...current, levels, value: mode === 'edit' ? (levels[0]?.value || '') : '' , selectedLevelId: mode === 'edit' ? (levels[0]?.levelId || '') : '' } : current);
    } catch {
      setManualSrModal((current) => current ? { ...current, error: 'Existing manual levels are not available right now. You can still insert a new level.' } : current);
    }
  };

  const saveManualSrModal = async () => {
    if (!manualSrModal) return;
    const value = Number(manualSrModal.value.trim().replace(/,/g, ''));
    if (!Number.isFinite(value) || value <= 0) {
      setManualSrModal({ ...manualSrModal, error: 'Enter one valid SR level.' });
      return;
    }
    if (manualSrModal.mode === 'edit' && !manualSrModal.selectedLevelId) {
      setManualSrModal({ ...manualSrModal, error: 'Select an existing SR level.' });
      return;
    }
    const body = manualSrModal.mode === 'edit'
      ? { mode: 'update', symbol: manualSrModal.symbol, sr_level: String(value), level_id: manualSrModal.selectedLevelId }
      : { mode: 'insert', symbol: manualSrModal.symbol, sr_level: String(value) };
    try {
      const response = await savePriceActionManualPayload(body);
      if (response.ok === false) throw new Error(response.error || response.detail || 'Save failed');
      setManualSrModal(null);
      void startSelectedHydration(manualSrModal.symbol);
    } catch (error) {
      setManualSrModal({ ...manualSrModal, error: error instanceof Error ? error.message : 'Unable to save the SR level.' });
    }
  };

  useEffect(() => {
    let active = true;
    const symbol = selectedSymbol || symbols[0];
    if (!symbol) return () => { active = false; };

    // Refresh only the selected saved symbol. Optional analytics continue
    // progressively without fanning out across the entire saved list.
    const refreshSequence = ++toolbarRefreshSequence.current;
    setToolbarRefreshing(true);
    const requestController = new AbortController();
    selectedHydrationController.current?.abort('Watchlist symbol changed');
    selectedHydrationController.current = requestController;
    void hydrateSymbol(symbol, '-', true, requestController.signal).finally(() => {
      if (active && toolbarRefreshSequence.current === refreshSequence) setToolbarRefreshing(false);
    });
    const loadingBudget = window.setTimeout(() => {
      if (!active) return;
      setLastRefreshedAt(new Date());
      if (toolbarRefreshSequence.current === refreshSequence) setToolbarRefreshing(false);
    }, 1000);

    return () => {
      active = false;
      requestController.abort('Watchlist symbol changed');
      window.clearTimeout(loadingBudget);
    };
  }, [selectedSymbol]);

  useEffect(() => {
    let active = true;
    void fetchSymbols('', { limit: 5000 })
      .then((payload) => {
        if (!active) return;
        const nextSymbols = sortNseSymbols(payload.symbols.map((item) => item.symbol));
        setAvailableSymbols(nextSymbols);
        persistMainNseSymbols(nextSymbols);
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!isSymbolMenuOpen) return undefined;
    const closeOnOutsidePointer = (event: PointerEvent) => {
      if (symbolMenuRef.current?.contains(event.target as Node)) return;
      setIsSymbolMenuOpen(false);
      setSymbolSearch('');
    };
    document.addEventListener('pointerdown', closeOnOutsidePointer);
    return () => document.removeEventListener('pointerdown', closeOnOutsidePointer);
  }, [isSymbolMenuOpen]);

  useEffect(() => {
    if (selectedSymbol && !symbols.includes(selectedSymbol)) {
      setSelectedSymbol(symbols[0] || '');
    }
  }, [selectedSymbol, symbols]);

  useEffect(() => {
    persistWatchlistRowsSessionSnapshot(symbols, resolvedRows);
  }, [resolvedRows, symbols]);

  const saveSymbol = async () => {
    const rawInput = symbolInput.trim();
    if (/^BSE(?::|-)/i.test(rawInput)) {
      setAddMessage('BSE symbols are not allowed. Add an NSE symbol only.');
      return;
    }
    const symbol = normalizeDisplaySymbol(symbolInput);
    if (!symbol) {
      setAddMessage('Enter a symbol to add.');
      return;
    }
    if (symbols.includes(symbol) && symbol !== editingSymbol) {
      setSelectedSymbol(symbol);
      setAddMessage(`${symbol} is already in your watchlist. Refreshing its existing data.`);
      void startSelectedHydration(symbol);
      return;
    }
    setSavingSymbol(true);
    try {
      const match = availableSymbols.includes(symbol)
        ? { exchange: 'NSE', symbol }
        : await validateNseWatchlistSymbol(symbol);
      if (!match) {
        setAddMessage(`${symbol} was not found in the existing NSE symbol or OHLCV sources.`);
        return;
      }
      const previousSymbol = editingSymbol;
      const nextSymbols = previousSymbol
        ? symbols.map((item) => item === previousSymbol ? symbol : item)
        : [...symbols, symbol];
      setSymbols(nextSymbols);
      persistSymbols(nextSymbols);
      setResolvedRows((current) => {
        const next = { ...current };
        if (previousSymbol && previousSymbol !== symbol) delete next[previousSymbol];
        return next;
      });
      setSelectedSymbol(symbol);
      setSymbolInput('');
      setEditingSymbol('');
      setAddMessage(previousSymbol ? `${previousSymbol} updated to ${symbol}.` : `${symbol} added to your watchlist.`);
      void startSelectedHydration(symbol);
    } catch (error) {
      setAddMessage(error instanceof Error ? `Unable to validate NSE symbol: ${error.message}` : 'Unable to validate NSE symbol.');
    } finally {
      setSavingSymbol(false);
    }
  };

  const editSymbol = (symbol: string) => {
    setEditingSymbol(symbol);
    setSymbolInput(symbol);
    setAddMessage(`Editing ${symbol}. Choose another symbol and select Update.`);
  };

  const removeSymbol = (symbol: string) => {
    const nextSymbols = symbols.filter((item) => item !== symbol);
    setSymbols(nextSymbols);
    persistSymbols(nextSymbols);
    setResolvedRows((current) => {
      const next = { ...current };
      delete next[symbol];
      return next;
    });
    if (selectedSymbol === symbol) setSelectedSymbol(nextSymbols[0] || '');
    if (editingSymbol === symbol) {
      setEditingSymbol('');
      setSymbolInput('');
    }
    setAddMessage(`${symbol} removed from your watchlist.`);
  };

  return (
    <div className={cn('page-theme--strategy legacy-react-shell min-h-screen bg-slate-50 text-slate-950 dark:bg-slate-950 dark:text-slate-100', themeMode === 'dark' && 'dashboard-react-page--dark')}>
      <style>{'#watchlist-symbol{cursor:pointer}'}</style>
       
      <CvingLegacyHeader activeSection="tradesetup" />
      <main className="mx-auto w-full max-w-[1880px] px-4 py-5 lg:px-8">
        <StrategyToolbar
          className="mb-4"
          lastRefreshed={lastRefreshedAt}
          ltcDate={null}
          onLive={() => void refreshWatchlist()}
          onRefresh={() => void refreshWatchlist()}
          onSearchChange={setToolbarSearch}
          refreshing={toolbarRefreshing}
          searchPlaceholder="Search My Watchlist"
          searchValue={toolbarSearch}
          showTotal
          singleSurface
          status={toolbarRefreshing ? 'syncing' : 'live'}
          total={filteredRows.length}
        />

        <section className="mb-5 flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
          <h1 className="text-3xl font-black">Dynamic Swing-Trading Watchlist</h1>
        </section>

        <section className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Kpi label="Near strong buying zone" tone="emerald" value={kpis.nearSupport} />
          <Kpi label="Breakout / retest candidates" tone="sky" value={kpis.breakout} />
          <Kpi label="Confirmed momentum / uptrend" tone="amber" value={kpis.momentum} />
          <Kpi label="Selling zone / breakdown risk" tone="blue" value={kpis.risk} />
        </section>

        <section className="mb-4 max-w-[900px] rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900" data-testid="watchlist-symbol-controls">
          <form className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-end gap-3 lg:grid-cols-[minmax(160px,0.5fr)_auto_minmax(160px,0.5fr)_minmax(150px,0.5fr)_auto]" data-testid="watchlist-add-symbol-form" onSubmit={(event) => { event.preventDefault(); void saveSymbol(); }}>
            <div ref={symbolMenuRef} className="relative min-w-0 text-xs font-black uppercase tracking-wide text-slate-500" onMouseLeave={() => { setIsSymbolMenuOpen(false); setSymbolSearch(''); }}><span id="watchlist-symbol-label">{editingSymbol ? `Update ${editingSymbol}` : 'Main NSE symbols'}</span><button id="watchlist-symbol" type="button" className="mt-1 flex w-full min-w-0 items-center justify-between rounded-xl border border-slate-300 px-3 py-2 text-left text-sm font-semibold uppercase text-slate-700 focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-200 disabled:cursor-wait disabled:opacity-60 dark:border-slate-600 dark:bg-slate-950 dark:text-slate-100 dark:focus:ring-sky-900" aria-labelledby="watchlist-symbol-label" aria-haspopup="listbox" aria-expanded={isSymbolMenuOpen} disabled={!availableSymbols.length} onClick={() => { setIsSymbolMenuOpen((open) => !open); setSymbolSearch(''); }}>{symbolInput || (availableSymbols.length ? 'Select NSE symbol' : 'Loading NSE symbols...')}<span aria-hidden="true" className="ml-3 text-slate-400">⌄</span></button>{isSymbolMenuOpen ? <div className="absolute z-50 mt-2 w-full rounded-xl border border-slate-200 bg-white p-2 shadow-xl dark:border-slate-700 dark:bg-slate-900"><input type="search" autoFocus value={symbolSearch} onChange={(event) => setSymbolSearch(event.target.value)} onKeyDown={(event) => { if (event.key === 'Escape') { setIsSymbolMenuOpen(false); setSymbolSearch(''); } }} placeholder="Search NSE symbol..." className="mb-2 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold uppercase focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-200 dark:border-slate-600 dark:bg-slate-950 dark:focus:ring-sky-900" aria-label="Search NSE symbols" /><div role="listbox" aria-label="Main NSE symbols" className="max-h-64 overflow-y-auto pr-1">{filteredAvailableSymbols.length ? filteredAvailableSymbols.map((symbol) => <button key={symbol} type="button" role="option" aria-selected={symbol === symbolInput} className="block w-full rounded-md px-3 py-2 text-left text-sm font-semibold text-slate-700 hover:bg-sky-50 focus:bg-sky-50 focus:outline-none dark:text-slate-100 dark:hover:bg-sky-950/40 dark:focus:bg-sky-950/40" onClick={() => { setSymbolInput(symbol); setAddMessage(''); setIsSymbolMenuOpen(false); setSymbolSearch(''); }}>{symbol}</button>) : <p className="px-3 py-2 text-sm font-semibold normal-case text-slate-500">No matching NSE symbols.</p>}</div></div> : null}</div>
            <div className="flex gap-2">
              <button type="submit" data-testid="watchlist-add-symbol-button" disabled={savingSymbol} className="inline-flex min-w-11 items-center justify-center rounded-xl bg-emerald-600 px-4 py-2 text-lg font-black text-white hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-300 disabled:cursor-wait disabled:opacity-60 dark:focus:ring-emerald-900" aria-label={editingSymbol ? 'Update watchlist symbol' : 'Add symbol to watchlist'} title={editingSymbol ? 'Update symbol' : 'Add symbol'}>{savingSymbol ? '...' : editingSymbol ? 'Update' : '+'}</button>
              {editingSymbol ? <button type="button" className="rounded-xl border border-slate-300 px-3 py-2 text-sm font-bold dark:border-slate-600" onClick={() => { setEditingSymbol(''); setSymbolInput(''); setAddMessage('Update cancelled.'); }}>Cancel</button> : null}
            </div>
            <label className="col-span-2 min-w-0 text-xs font-black uppercase tracking-wide text-slate-500 lg:col-span-1" htmlFor="watchlist-saved-symbols">My Watchlist symbols<select id="watchlist-saved-symbols" data-testid="watchlist-saved-symbols" className="mt-1 block w-full min-w-0 rounded-xl border border-slate-300 px-3 py-2 text-sm font-semibold uppercase focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-200 dark:border-slate-600 dark:bg-slate-950 dark:focus:ring-sky-900" value={selected?.symbol || ''} onChange={(event) => selectWatchlistSymbol(event.target.value)} disabled={!symbols.length}><option value="">{symbols.length ? 'Select symbol' : 'No symbols added'}</option>{symbols.map((symbol) => <option key={symbol} value={symbol}>{symbol}</option>)}</select></label>
            <label className="col-span-2 min-w-0 text-xs font-black uppercase tracking-wide text-slate-500 lg:col-span-1" htmlFor="watchlist-setup-state">Setup state<select id="watchlist-setup-state" className="mt-1 block w-full rounded-xl border border-slate-300 px-3 py-2 text-sm font-semibold focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-200 dark:border-slate-600 dark:bg-slate-950 dark:focus:ring-sky-900" value={setup} onChange={(event) => setSetup(event.target.value as 'ALL' | SetupState)}><option value="ALL">All setups</option>{Object.entries(setupLabel).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            {addMessage ? <p className="col-span-2 min-h-5 text-xs font-semibold text-slate-600 dark:text-slate-300 lg:col-span-5" role="status">{addMessage}</p> : null}
          </form>
        </section>

        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900">
          <div className="flex flex-wrap gap-2 border-b border-slate-200 p-3 dark:border-slate-700" role="tablist" aria-label="Watchlist table views">
            {([
              ['overview', 'Overview', 'Identity · Market · Setup'],
              ['targets', 'Targets', 'Targets'],
              ['levels', 'S&R Levels', 'Support · Resistance'],
              ['confirmation', 'Confirmation', 'Confirmation · Actions'],
            ] as const).map(([value, label, description]) => (
              <button
                key={value}
                type="button"
                role="tab"
                aria-selected={tableTab === value}
                aria-controls="watchlist-data-table"
                className={cn(
                  'rounded-xl border px-4 py-2 text-left transition',
                  tableTab === value
                    ? 'border-sky-600 bg-sky-600 text-white shadow-sm'
                    : 'border-slate-300 bg-white text-slate-700 hover:border-sky-300 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200',
                )}
                onClick={() => setTableTab(value)}
              >
                <span className="block text-sm font-black">{label}</span>
                <span className={cn('block text-[11px] font-semibold', tableTab === value ? 'text-sky-50' : 'text-slate-500 dark:text-slate-400')}>{description}</span>
              </button>
            ))}
          </div>
          {selected ? <SourceStatusStrip row={selected} tab={tableTab} /> : null}
          <div className={tableTab === 'overview' ? 'overflow-x-hidden' : 'overflow-x-auto'} data-testid="watchlist-table-scroll">
            <table id="watchlist-data-table" className={cn('app-data-table table-sticky-safe watchlist-tabbed-table border-collapse text-sm', `watchlist-tabbed-table--${tableTab}`)}>
              <thead><tr><th>S.No</th><th className="sticky left-0 z-20 bg-slate-100 dark:bg-slate-800">Symbol</th><th>Sector</th><th>MCAP</th><th>FFMC</th><th>Index</th><th>Trend</th><th>Sector Trend</th><th>Pattern</th><th>Setup State</th><th>LTP</th><th>Entry Zone</th><th>Distance</th><th>T1</th><th>T2</th><th>T3</th><th>S1</th><th>S2</th><th>S3</th><th>Strong Support</th><th>R1</th><th>R2</th><th>R3</th><th>Strong Resistance</th><th>Volume Ratio</th><th>Delivery %</th><th>Confidence</th><th>Actions</th></tr></thead>
              <tbody>{displayedRows.map((row, index) => {
                const reference = (row.entryLow + row.entryHigh) / 2;
                const distance = reference > 0 ? ((row.ltp - reference) / reference) * 100 : null;
                const sectorState = combinedSourceState(row.sourceStatus.sectorWise, row.sourceStatus.metadata, row.sourceStatus.technical);
                const targetState = combinedSourceState(row.sourceStatus.bars, row.sourceStatus.sr);
                const targetPrices = row.targetPrices.map((price, targetIndex) => price || (reference > 0
                  ? Number((reference * (1 + ([5, 10, 15][targetIndex] / 100))).toFixed(2))
                  : 0)) as [number, number, number];
                return (
                  <tr key={row.symbol} className={cn('border-t border-slate-200 dark:border-slate-700', selected?.symbol === row.symbol && 'bg-sky-50/60 dark:bg-sky-950/20')}>
                    <td>{index + 1}</td>
                    <td className="sticky left-0 z-10 bg-white font-black text-sky-700 dark:bg-slate-900 dark:text-sky-300">{normalizeDisplaySymbol(row.symbol)}</td>
                    <td>{row.sector !== '-' ? row.sector : <MissingData state={sectorState} />}</td>
                    <td>{row.mcap !== '-' ? row.mcap : <MissingData state={sectorState} />}</td>
                    <td>{row.ffmc !== '-' ? row.ffmc : <MissingData state={row.sourceStatus.technical} />}</td>
                    <td>{row.index !== '-' ? row.index : <MissingData state={sectorState} />}</td>
                    <td>{row.trend !== '-' ? row.trend : <MissingData state={combinedSourceState(row.sourceStatus.sectorWise, row.sourceStatus.technical)} />}</td>
                    <td>{row.sectorTrend !== '-' ? row.sectorTrend : <MissingData state={combinedSourceState(row.sourceStatus.sectorWise, row.sourceStatus.technical)} />}</td>
                    <td>{row.pattern !== '-' ? row.pattern : <MissingData state={row.sourceStatus.technical} />}</td>
                    <td><span className="rounded-full border border-slate-300 px-2 py-1 text-xs font-black">{setupLabel[row.setup]}</span></td>
                    <td className="sticky left-[110px] z-10 bg-white font-black dark:bg-slate-900">{row.ltp > 0 ? formatPrice(row.ltp) : <MissingData state={row.sourceStatus.bars} />}</td>
                    <td>{reference > 0 ? `${formatPrice(row.entryLow)}–${formatPrice(row.entryHigh)}` : <MissingData state={row.sourceStatus.bars} />}</td>
                    <td>{distance === null ? <MissingData state={row.sourceStatus.bars} /> : `${distance >= 0 ? '+' : ''}${distance.toFixed(1)}%`}</td>
                    <td><TargetCell day={row.targetDays[0]} durationState={row.sourceStatus.targetHistory} entry={reference} price={targetPrices[0]} source={row.targetSources[0]} state={targetState} /></td>
                    <td><TargetCell day={row.targetDays[1]} durationState={row.sourceStatus.targetHistory} entry={reference} price={targetPrices[1]} source={row.targetSources[1]} state={targetState} /></td>
                    <td><TargetCell day={row.targetDays[2]} durationState={row.sourceStatus.targetHistory} entry={reference} price={targetPrices[2]} source={row.targetSources[2]} state={targetState} /></td>
                    {row.support.map((value, supportIndex) => <td key={`support-${supportIndex}`}><LevelCell price={value} source={row.supportSources[supportIndex]} state={row.sourceStatus.sr} /></td>)}
                    <td>{row.strongSupport > 0 ? <span className="inline-block border-2 border-emerald-600 bg-emerald-50 px-2 py-1 font-black text-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-100">STRONG · {formatPrice(row.strongSupport)}<LevelSourceBadge source={row.strongSupportSource} /></span> : <MissingData state={row.sourceStatus.sr} />}</td>
                    {row.resistance.map((value, resistanceIndex) => <td key={`resistance-${resistanceIndex}`}><LevelCell price={value} source={row.resistanceSources[resistanceIndex]} state={row.sourceStatus.sr} /></td>)}
                    <td>{row.strongResistance > 0 ? <span className="inline-block border-2 border-sky-600 bg-sky-50 px-2 py-1 font-black text-sky-900 dark:bg-sky-950/40 dark:text-sky-100">STRONG · {formatPrice(row.strongResistance)}<LevelSourceBadge source={row.strongResistanceSource} /></span> : <MissingData state={row.sourceStatus.sr} />}</td>
                    <td>{row.volumeRatio > 0 ? `${row.volumeRatio.toFixed(1)}x` : <MissingData state={row.sourceStatus.volume} />}</td>
                    <td>{row.delivery > 0 ? `${row.delivery.toFixed(1)}%` : <MissingData state={row.sourceStatus.delivery} />}</td>
                    <td><strong>{row.confidence > 0 ? `${row.confidence}%` : <MissingData state={row.sourceStatus.technical} />}</strong></td>
                    <td><div className="flex flex-wrap gap-2"><button type="button" className="rounded-lg bg-slate-900 px-3 py-2 text-xs font-black text-white dark:bg-slate-100 dark:text-slate-900" onClick={() => setSelectedSymbol(row.symbol)}>View</button>{tableTab === 'levels' ? <><button type="button" className="rounded-lg border border-sky-600 px-3 py-2 text-xs font-black text-sky-800 dark:text-sky-300" onClick={() => void openManualSrModal(row.symbol, 'edit')}>Edit</button><button type="button" className="rounded-lg border border-emerald-600 px-3 py-2 text-xs font-black text-emerald-800 dark:text-emerald-300" onClick={() => void openManualSrModal(row.symbol, 'insert')}>Insert</button></> : null}<button type="button" className="inline-flex items-center gap-1 rounded-lg border border-blue-600 px-3 py-2 text-xs font-black text-blue-800 hover:bg-blue-50 dark:text-blue-300 dark:hover:bg-blue-950/40" onClick={() => removeSymbol(row.symbol)}><TrashIcon className="h-3.5 w-3.5" />Remove</button><a className="rounded-lg border border-emerald-600 px-3 py-2 text-xs font-black text-emerald-800 dark:text-emerald-300" href="/app/technical/price-action" onClick={(event) => handleInternalNavigationClick(event, '/app/technical/price-action')}>Manual S&amp;R</a></div></td>
                  </tr>
                );
              })}</tbody>
            </table>
          </div>
          {!displayedRows.length ? <div className="p-10 text-center font-bold text-slate-500">{watchlistRows.length ? 'The selected symbol does not match the current search or setup filter.' : 'Your watchlist is empty. Select a main NSE symbol above and select + to add it.'}</div> : null}
        </section>

        {selected ? <aside className="mt-5 rounded-2xl border border-slate-200 bg-white p-5 shadow-lg dark:border-slate-700 dark:bg-slate-900" aria-label="Selected stock analysis">
          <div className="flex flex-wrap items-start justify-between gap-3"><div><div className="text-xs font-black uppercase tracking-wide text-sky-700 dark:text-sky-300">Selected-stock analysis</div><h2 className="text-2xl font-black">{normalizeDisplaySymbol(selected.symbol)} · {selected.pattern}</h2><p className="text-sm text-slate-500">{midpoint > 0 ? `Latest candle range midpoint ${formatPrice(midpoint)} · not an executed transaction` : 'Existing NSE technical data is not available for this symbol yet.'}</p></div><div className="rounded-xl border-2 border-emerald-600 px-4 py-2 text-center"><div className="text-xs font-black">CONFIDENCE</div><div className="text-2xl font-black">{selected.confidence > 0 ? `${selected.confidence}%` : '-'}</div></div></div>
          <div className="my-4 flex flex-wrap gap-2">{['Overview', 'S&R Ladder', 'Chart & Evidence', 'Swing & Duration', 'Manual S&R Editor', 'Why this setup?'].map((tab) => <button key={tab} type="button" onClick={() => setDrawerTab(tab)} className={cn('rounded-full border px-3 py-2 text-sm font-bold', drawerTab === tab ? 'border-blue-600 bg-blue-600 text-white' : 'border-slate-300 dark:border-slate-600')}>{tab}</button>)}</div>
          <SelectedAnalysisContent row={selected} tab={drawerTab} midpoint={midpoint} onManual={(mode) => void openManualSrModal(selected.symbol, mode)} />
        </aside> : null}
        {manualSrModal ? <div className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-950/50 p-4" role="dialog" aria-modal="true" aria-labelledby="watchlist-manual-sr-title" onMouseDown={(event) => { if (event.target === event.currentTarget) setManualSrModal(null); }}>
          <form className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-5 shadow-2xl dark:border-slate-700 dark:bg-slate-900" onSubmit={(event) => { event.preventDefault(); void saveManualSrModal(); }}>
            <div className="flex items-center justify-between gap-3"><h2 id="watchlist-manual-sr-title" className="text-xl font-black">{manualSrModal.mode === 'edit' ? 'Edit' : 'Insert'} {manualSrModal.symbol} S&amp;R level</h2><button type="button" className="rounded-lg border px-3 py-1 font-black" onClick={() => setManualSrModal(null)}>×</button></div>
            {manualSrModal.mode === 'edit' ? <label className="mt-5 block text-sm font-bold">Existing level<select className="mt-1 block w-full rounded-lg border p-2 dark:border-slate-600 dark:bg-slate-950" value={manualSrModal.selectedLevelId} onChange={(event) => { const level = manualSrModal.levels.find((item) => item.levelId === event.target.value); setManualSrModal({ ...manualSrModal, selectedLevelId: event.target.value, value: level?.value || manualSrModal.value, error: '' }); }}><option value="">Select an SR level</option>{manualSrModal.levels.map((level) => <option key={level.levelId} value={level.levelId}>{level.value}</option>)}</select></label> : null}
            <label className="mt-4 block text-sm font-bold">SR level<input autoFocus type="text" inputMode="decimal" className="mt-1 block w-full rounded-lg border p-2 dark:border-slate-600 dark:bg-slate-950" value={manualSrModal.value} onChange={(event) => setManualSrModal({ ...manualSrModal, value: event.target.value, error: '' })} placeholder="e.g. 577.25" /></label>
            {manualSrModal.error ? <p className="mt-3 text-sm font-bold text-amber-700 dark:text-amber-300" role="alert">{manualSrModal.error}</p> : null}
            <div className="mt-5 flex justify-end gap-2"><button type="button" className="rounded-lg border px-4 py-2 font-bold" onClick={() => setManualSrModal(null)}>Cancel</button><button type="submit" className="rounded-lg bg-emerald-700 px-4 py-2 font-black text-white">{manualSrModal.mode === 'edit' ? 'Update' : 'Insert'}</button></div>
          </form>
        </div> : null}
      </main>
    </div>
  );
}
