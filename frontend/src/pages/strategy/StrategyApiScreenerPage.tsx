import { useEffect, useMemo, useRef, useState } from 'react';
import { AppDataTable, type AppDataTableColumn, type AppSortState } from '../../components/app/AppDataTable';
import { TechnicalMarketCapCell } from '../../components/app/TechnicalMarketCapCell';
import { Card } from '../../components/ui/Card';
import { PageHeader } from '../../components/ui/PageHeader';
import {
  extractStrategyRows,
  extractStrategyMetaNumber,
  extractStrategyTotal,
  formatStrategyCell,
  getStrategySortValue,
  isStrategyPayloadRefreshing,
  isStrategyPayloadStale,
  pickStrategyField,
  type StrategyTableColumn,
  type StrategyWireRow,
} from '../../adapters/strategyPageAdapter';
import { adaptEmaTrendRow, type EmaCellTone, type EmaViewCell } from '../../adapters/technicalEmaAdapter';
import type { MarketCapCategory } from '../../adapters/technicalMarketCap';
import { fetchStrategyPayload, postStrategyRows } from '../../services/api/strategyApi';
import type { QueryParams } from '../../api/client';
import { cn } from '../../lib/cn';
import { recordDiagnostic } from '../../lib/diagnostics';
import { StrategyMigrationLayout } from './StrategyMigrationLayout';
import { StrategyToolbar, type StrategyToolbarStatus } from '../../components/strategy/StrategyToolbar';

type Timeframe = 'daily' | 'weekly' | 'monthly' | 'yearly';
type SortDirection = 'asc' | 'desc' | null;

export type StrategyApiScreenerConfig = {
  activeStrategyPage: string;
  defaultSort?: string;
  description: string;
  enableLiveToolbar?: boolean;
  endpoint: string;
  insertEndpoint?: string;
  lastBuyingDateEndpoint?: string;
  pageSize?: number;
  pollWhileRefreshing?: boolean;
  refreshPollIntervalMs?: number;
  refreshPollMaxAttempts?: number;
  refreshingEmptyMessage?: string;
  queryMode?: 'timeframe' | 'tf';
  serverPagination?: boolean;
  showToolbarTotal?: boolean;
  tableVariant?: 'default' | 'ema';
  title: string;
  columns: ReadonlyArray<StrategyTableColumn>;
  extraParams?: Record<string, string | number | boolean>;
};

type StrategyApiScreenerPageProps = {
  config: StrategyApiScreenerConfig;
};

const TIMEFRAMES: Timeframe[] = ['daily', 'weekly', 'monthly', 'yearly'];
const EMA_CELL_KEYS = new Set(['index', 'mcap', 'mcap_rank', 'mcapRank', 'ath', 'gap']);
const STRATEGY_PAYLOAD_INFLIGHT = new Map<string, Promise<unknown>>();

type StrategyLoadMode = 'initial' | 'live' | 'poll' | 'refresh';
type AsuraLastBuyingDateWire = {
  maxBuyingDate?: string | null;
  maxLtcDate?: string | null;
  latestLtcDate?: string | null;
  ltc_date?: string | null;
};
type StrategyRuntimeDateState = {
  dataDateKey: string | null;
  dataIsCurrent: boolean;
  expectedDateKey: string | null;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

function firstPresent(source: Record<string, unknown>, keys: readonly string[]): unknown {
  for (const key of keys) {
    const value = source[key];
    if (value !== undefined && value !== null && String(value).trim() !== '') {
      return value;
    }
  }
  return null;
}

function parseTradingDate(value?: unknown): Date | null {
  if (value === undefined || value === null || value === '') return null;
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : new Date(value.getTime());
  }
  if (typeof value === 'number') {
    const normalized = value < 1000000000000 ? value * 1000 : value;
    const date = new Date(normalized);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  const text = String(value).trim();
  if (!text) return null;
  const ddmmyyyy = text.match(/^(\d{1,2})[-/](\d{1,2})[-/](\d{4})(?:\s.*)?$/);
  if (ddmmyyyy) {
    const [, dd, mm, yyyy] = ddmmyyyy;
    const date = new Date(Number(yyyy), Number(mm) - 1, Number(dd));
    return Number.isNaN(date.getTime()) ? null : date;
  }
  const yyyymmdd = text.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:[T\s].*)?$/);
  if (yyyymmdd) {
    const [, yyyy, mm, dd] = yyyymmdd;
    const date = new Date(Number(yyyy), Number(mm) - 1, Number(dd));
    return Number.isNaN(date.getTime()) ? null : date;
  }

  const parsed = new Date(text);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function formatLocalDateKey(date: Date): string {
  const yyyy = String(date.getFullYear());
  const mm = String(date.getMonth() + 1).padStart(2, '0');
  const dd = String(date.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

function formatDisplayDateKey(dateKey: string | null): string {
  if (!dateKey) return '-';
  const [yyyy, mm, dd] = dateKey.split('-');
  return yyyy && mm && dd ? `${dd}-${mm}-${yyyy}` : dateKey;
}

function formatStrategyDateCell(value: unknown): string {
  const dateKey = tradingDateKey(value);
  return dateKey ? formatDisplayDateKey(dateKey) : formatStrategyCell(value);
}

function tradingDateKey(value?: unknown): string | null {
  const parsed = parseTradingDate(value);
  return parsed ? formatLocalDateKey(parsed) : null;
}

function latestStrategyDateKey(payload: unknown, rows: readonly StrategyWireRow[]): string | null {
  const source = isRecord(payload) ? payload : {};
  const meta = isRecord(source.meta) ? source.meta : {};
  const candidates = [
    firstPresent(source, ['ltcDate', 'ltc_date', 'LTC_DATE', 'latestLtcDate', 'latest_ltc_date', 'maxLtcDate', 'as_of_date', 'tradingDate', 'tradeDate']),
    firstPresent(meta, ['ltcDate', 'ltc_date', 'LTC_DATE', 'latestLtcDate', 'latest_ltc_date', 'maxLtcDate', 'as_of_date', 'tradingDate', 'tradeDate', 'endDate']),
    ...rows.map((row) => firstPresent(row, ['ltcDate', 'LTC_DATE', 'ltc_date', 'latestTradingDate', 'latest_trade_date', 'tradeDate', 'trade_date', 'TRADING_DATE', 'buyingDate', 'BUYING_DATE'])),
  ];
  return candidates.reduce<string | null>((latest, candidate) => {
    const key = tradingDateKey(candidate);
    return key && (!latest || key > latest) ? key : latest;
  }, null);
}

export function resolveStrategyRuntimeDates({
  hasLoadedRows,
  now = new Date(),
  payloadLatestDateKey,
  toolbarLtcDateKey,
}: {
  hasLoadedRows: boolean;
  now?: Date;
  payloadLatestDateKey: string | null;
  toolbarLtcDateKey: string | null;
}): StrategyRuntimeDateState {
  const dataDateKey = payloadLatestDateKey ?? toolbarLtcDateKey;
  const expectedDateKey = toolbarLtcDateKey ?? payloadLatestDateKey ?? formatLocalDateKey(now);
  return {
    dataDateKey,
    expectedDateKey,
    dataIsCurrent: Boolean(hasLoadedRows && dataDateKey && expectedDateKey && dataDateKey >= expectedDateKey),
  };
}

function stableQueryKey(params: QueryParams): string {
  const entries = Object.entries(params || {}).filter(([, value]) => value !== undefined && value !== null && value !== '');
  entries.sort(([left], [right]) => left.localeCompare(right));
  return entries.map(([key, value]) => `${key}=${String(value)}`).join('&');
}

function buildUrlForDiagnostics(endpoint: string, params: QueryParams, forceRefresh: boolean): string {
  const query = new URLSearchParams();
  const diagnosticParams: QueryParams = { ...params, refresh: forceRefresh ? 1 : undefined };
  Object.entries(diagnosticParams).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      query.set(key, String(value));
    }
  });
  const suffix = query.toString();
  return suffix ? `${endpoint}?${suffix}` : endpoint;
}

function dedupedStrategyPayloadRequest<T>(
  endpoint: string,
  params: QueryParams,
  forceRefresh: boolean,
): Promise<T> {
  const inflightKey = `${endpoint}|refresh=${forceRefresh ? 1 : 0}|${stableQueryKey(params)}`;
  const existing = STRATEGY_PAYLOAD_INFLIGHT.get(inflightKey);
  if (existing) {
    return existing as Promise<T>;
  }
  const promise = fetchStrategyPayload<T>(endpoint, params, { forceRefresh });
  STRATEGY_PAYLOAD_INFLIGHT.set(inflightKey, promise as Promise<unknown>);
  promise.finally(() => {
    if (STRATEGY_PAYLOAD_INFLIGHT.get(inflightKey) === promise) {
      STRATEGY_PAYLOAD_INFLIGHT.delete(inflightKey);
    }
  });
  return promise;
}

function isTimeout90sError(message: string): boolean {
  const normalized = String(message || '').toLowerCase();
  const hasDuration = normalized.includes('90000ms') || normalized.includes('90s');
  return hasDuration && (normalized.includes('timeout') || normalized.includes('aborted') || normalized.includes('taking too long'));
}

function sortRows(rows: StrategyWireRow[], columns: ReadonlyArray<StrategyTableColumn>, sortKey: string | null, sortDirection: SortDirection) {
  if (!sortKey || !sortDirection) return rows;
  const column = columns.find((item) => item.key === sortKey);
  if (!column) return rows;
  const multiplier = sortDirection === 'asc' ? 1 : -1;

  return [...rows].sort((left, right) => {
    const leftValue = getStrategySortValue(left, column);
    const rightValue = getStrategySortValue(right, column);
    if (typeof leftValue === 'string' || typeof rightValue === 'string') {
      return String(leftValue).localeCompare(String(rightValue)) * multiplier;
    }
    return (leftValue - rightValue) * multiplier;
  });
}

function filterRows(rows: StrategyWireRow[], search: string) {
  const query = search.trim().toUpperCase();
  if (!query) return rows;
  return rows.filter((row) => {
    const symbol = formatStrategyCell(pickStrategyField(row, ['symbol', 'stock', 'stockName', 'stock_name', 'STOCK']));
    return symbol.toUpperCase().includes(query);
  });
}

function normalizeInsertMessage(payload: unknown): string {
  if (!payload || typeof payload !== 'object') return 'Insert request completed.';
  const source = payload as Record<string, unknown>;
  const inserted = source.insertedCount ?? source.inserted ?? source.inserted_count;
  const updated = source.updatedCount ?? source.updated ?? source.updated_count;
  const skipped = source.skippedCount ?? source.skipped ?? source.skipped_count;
  return `Insert completed. Inserted: ${formatStrategyCell(inserted)}, Updated: ${formatStrategyCell(updated)}, Skipped: ${formatStrategyCell(skipped)}.`;
}

function getColumnFieldCandidates(column: StrategyTableColumn): string[] {
  return [column.key, ...(column.fields ?? []), column.key.toUpperCase()];
}

type StrategyAppTableRow = {
  emaCells: Record<string, EmaViewCell>;
  raw: StrategyWireRow;
  serialNo: number;
};

function columnDataCol(column: StrategyTableColumn): string {
  if (column.dataCol) return column.dataCol;
  if (column.key === 'mcap_rank') return 'mcapRank';
  return column.key;
}

function columnSortType(column: StrategyTableColumn): AppDataTableColumn<StrategyAppTableRow>['sortType'] {
  if (column.sortType) return column.sortType;
  if (column.align === 'right' || column.key === 'sNo') return 'number';
  return 'string';
}

function emaCellKey(column: StrategyTableColumn): string | null {
  if (column.renderAs === 'marketCapIndex') return 'index';
  if (column.renderAs === 'marketCapValue') return 'mcap';
  if (column.renderAs === 'marketCapRank') return 'mcapRank';
  if (column.renderAs === 'ath') return 'ath';
  if (column.renderAs === 'gap') return 'gap';
  if (column.key === 'mcap_rank') return 'mcapRank';
  return EMA_CELL_KEYS.has(column.key) ? column.key : null;
}

function marketCapToneFromCell(cell?: EmaViewCell): MarketCapCategory {
  const tone = cell?.tone;
  if (tone === 'large' || tone === 'mid' || tone === 'small' || tone === 'unknown') return tone;
  return 'unknown';
}

function emaValueToneClass(tone?: EmaCellTone): string | undefined {
  if (tone === 'positive') return 'trend-price--up';
  if (tone === 'negative') return 'trend-price--down';
  return undefined;
}

function strategyTableId(activeStrategyPage: string): string {
  const slug = activeStrategyPage
    .replace(/^\/+/, '')
    .replace(/[^a-z0-9/_-]+/gi, '-')
    .replace(/[\/]+/g, '-')
    .toLowerCase();
  return `${slug || 'strategy'}-react-table`;
}

function StrategyEmaValueCell({ cell }: { cell: EmaViewCell }) {
  const className = emaValueToneClass(cell.tone);
  if (!className && !cell.title) return <>{cell.text}</>;
  return (
    <span className={className} title={cell.title}>
      {cell.text}
    </span>
  );
}

function parseStrategyNumber(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  const text = String(value ?? '').replace(/,/g, '').replace(/%/g, '').trim();
  if (!text) return null;
  const parsed = Number(text);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatSignedPercentCell(value: unknown) {
  const numeric = parseStrategyNumber(value);
  if (numeric === null) return <>{formatStrategyCell(value)}</>;
  const className = numeric > 0 ? 'trend-price--up' : numeric < 0 ? 'trend-price--down' : undefined;
  const text = `${numeric.toLocaleString('en-IN', { maximumFractionDigits: 2 })}%`;
  if (!className) return <>{text}</>;
  return <span className={className}>{text}</span>;
}

export function StrategyApiScreenerPage({ config }: StrategyApiScreenerPageProps) {
  const liveToolbarEnabled = config.enableLiveToolbar !== false;
  const isAsuraPage = config.activeStrategyPage === '/app/strategy/asura';
  const pageSize = config.pageSize ?? 25;
  const [timeframe, setTimeframe] = useState<Timeframe>('daily');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [sortKey, setSortKey] = useState<string | null>(config.defaultSort ?? null);
  const [sortDirection, setSortDirection] = useState<SortDirection>(config.defaultSort ? 'desc' : null);
  const [payload, setPayload] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [insertStatus, setInsertStatus] = useState('');
  const [insertFailed, setInsertFailed] = useState(false);
  const [inserting, setInserting] = useState(false);
  const [autoPollTick, setAutoPollTick] = useState(0);
  const [autoPollAttempts, setAutoPollAttempts] = useState(0);
  const [liveLoading, setLiveLoading] = useState(false);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null);
  const [ltcDate, setLtcDate] = useState<string | null>(null);
  const [loadDurationMs, setLoadDurationMs] = useState<number | null>(null);
  const [backendApiMs, setBackendApiMs] = useState<number | null>(null);
  const [backendDbMs, setBackendDbMs] = useState<number | null>(null);
  const requestSeqRef = useRef(0);
  const refreshInFlightRef = useRef(false);
  const refreshTimerRef = useRef<number | null>(null);
  const lastApiUrlRef = useRef(config.endpoint);
  const mountedRef = useRef(true);

  useEffect(() => () => {
    mountedRef.current = false;
    if (refreshTimerRef.current !== null) {
      window.clearTimeout(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }
  }, []);

  function buildQueryParams(mode?: StrategyLoadMode): QueryParams {
    const queryKey = config.queryMode === 'tf' ? 'tf' : 'timeframe';
    const extraParams: Record<string, string | number | boolean> = { ...(config.extraParams ?? {}) };
    if (isAsuraPage && (mode === 'initial' || mode === 'live' || mode === 'refresh')) {
      extraParams.skip_sync = 0;
    }
    return {
      [queryKey]: timeframe,
      page: config.serverPagination ? page : undefined,
      page_size: config.serverPagination ? pageSize : undefined,
      sort: config.serverPagination ? sortKey ?? config.defaultSort : undefined,
      order: config.serverPagination ? sortDirection ?? 'desc' : undefined,
      search: config.serverPagination ? search.trim() || undefined : undefined,
      ...extraParams,
    };
  }

  function normalizeLoadErrorMessage(loadError: unknown): string {
    const base = loadError instanceof Error ? loadError.message : String(loadError || 'Request failed.');
    if (liveToolbarEnabled && isTimeout90sError(base)) {
      return `${config.title} API timeout after 90s. Backend query/sync is taking too long. Please check strategy performance logs.`;
    }
    return base;
  }

  async function loadLastBuyingDate(fallbackDate: string | null = null, requestSeq?: number): Promise<void> {
    if (!liveToolbarEnabled || !config.lastBuyingDateEndpoint) return;
    try {
      const payload = await fetchStrategyPayload<AsuraLastBuyingDateWire>(config.lastBuyingDateEndpoint);
      const nextDate = String(payload?.latestLtcDate ?? payload?.maxLtcDate ?? payload?.ltc_date ?? payload?.maxBuyingDate ?? '').trim();
      if (mountedRef.current && (requestSeq === undefined || requestSeq === requestSeqRef.current)) {
        setLtcDate(nextDate || fallbackDate || null);
      }
    } catch {
      if (mountedRef.current && fallbackDate && (requestSeq === undefined || requestSeq === requestSeqRef.current)) {
        setLtcDate(fallbackDate);
      }
    }
  }

  async function runLoad(mode: StrategyLoadMode): Promise<void> {
    if ((mode === 'refresh' || mode === 'live' || mode === 'poll') && refreshInFlightRef.current) {
      return;
    }
    const requestSeq = requestSeqRef.current + 1;
    requestSeqRef.current = requestSeq;
    const isRefresh = mode === 'refresh';
    const isLive = mode === 'live';
    const isPoll = mode === 'poll';
    const isInitial = mode === 'initial' || mode === 'poll';
    if (isRefresh || isLive || isPoll) {
      refreshInFlightRef.current = true;
    }
    if (isInitial) setLoading(true);
    if (isRefresh) setRefreshing(true);
    if (isLive) setLiveLoading(true);
    setError('');
    setInsertFailed(false);
    if (mode === 'refresh' || mode === 'live') {
      setAutoPollAttempts(0);
    }
    const startedAt = performance.now();
    const forceRefresh = isRefresh || (isAsuraPage && (isInitial || isLive));
    const queryParams = buildQueryParams(mode);
    lastApiUrlRef.current = buildUrlForDiagnostics(config.endpoint, queryParams, forceRefresh);
    try {
      const data = await dedupedStrategyPayloadRequest<unknown>(
        config.endpoint,
        queryParams,
        forceRefresh,
      );
      if (!mountedRef.current || requestSeq !== requestSeqRef.current) return;

      const elapsedMs = Math.max(0, Math.round(performance.now() - startedAt));
      const meta = isRecord(data) && isRecord(data.meta) ? data.meta : {};
      const metaLtcDate = String(
        meta.ltc_date
        ?? meta.ltcDate
        ?? meta.maxLtcDate
        ?? meta.tradingDate
        ?? meta.endDate
        ?? '',
      ).trim();
      const loadedRows = extractStrategyRows(data);
      const fallbackLtcDate = metaLtcDate || latestStrategyDateKey(data, loadedRows);

      setPayload(data);
      setLoadDurationMs(elapsedMs);
      setBackendApiMs(extractStrategyMetaNumber(data, ['api_time_ms', 'request_ms', 'duration_ms', 'durationMs', 'load_time_ms']));
      setBackendDbMs(extractStrategyMetaNumber(data, ['db_time_ms', 'oracle_ms', 'oracleLoadMs', 'query_ms']));
      setLastRefreshedAt(new Date());
      if (fallbackLtcDate) {
        setLtcDate(fallbackLtcDate);
      }

      void loadLastBuyingDate(fallbackLtcDate, requestSeq);
    } catch (loadError) {
      if (!mountedRef.current || requestSeq !== requestSeqRef.current) return;
      const message = normalizeLoadErrorMessage(loadError);
      setError(message);
    } finally {
      if (isRefresh || isLive || isPoll) {
        refreshInFlightRef.current = false;
      }
      if (!mountedRef.current || requestSeq !== requestSeqRef.current) return;
      if (isInitial) setLoading(false);
      if (isRefresh) setRefreshing(false);
      if (isLive) setLiveLoading(false);
    }
  }

  useEffect(() => {
    void runLoad(autoPollTick > 0 ? 'poll' : 'initial');
  }, [autoPollTick, config, config.defaultSort, config.endpoint, config.extraParams, config.pageSize, config.queryMode, config.serverPagination, page, pageSize, search, sortDirection, sortKey, timeframe]);

  async function refresh() {
    await runLoad('refresh');
  }

  async function liveRefresh() {
    await runLoad('live');
  }

  async function insertCurrentRows() {
    if (!config.insertEndpoint) return;
    setInserting(true);
    setInsertStatus('');
    setInsertFailed(false);
    try {
      const result = await postStrategyRows<Record<string, unknown>>(config.insertEndpoint, visibleRows);
      setInsertStatus(normalizeInsertMessage(result));
    } catch (insertError) {
      setInsertFailed(true);
      setInsertStatus(insertError instanceof Error ? insertError.message : String(insertError));
    } finally {
      setInserting(false);
    }
  }

  const rawRows = useMemo(() => extractStrategyRows(payload), [payload]);
  const payloadLatestDateKey = useMemo(() => latestStrategyDateKey(payload, rawRows), [payload, rawRows]);
  const payloadRefreshing = useMemo(() => isStrategyPayloadRefreshing(payload), [payload]);
  const payloadStale = useMemo(() => isStrategyPayloadStale(payload), [payload]);
  const filteredRows = useMemo(
    () => (config.serverPagination ? rawRows : filterRows(rawRows, search)),
    [config.serverPagination, rawRows, search],
  );
  const sortedRows = useMemo(
    () => (config.serverPagination ? filteredRows : sortRows(filteredRows, config.columns, sortKey, sortDirection)),
    [config.columns, config.serverPagination, filteredRows, sortDirection, sortKey],
  );
  const totalRows = config.serverPagination ? extractStrategyTotal(payload, rawRows.length) : sortedRows.length;
  const toolbarLtcDateKey = tradingDateKey(ltcDate);
  const hasLoadedRows = rawRows.length > 0;
  const { dataDateKey, dataIsCurrent, expectedDateKey } = resolveStrategyRuntimeDates({
    hasLoadedRows,
    payloadLatestDateKey,
    toolbarLtcDateKey,
  });
  const effectivePayloadRefreshing = payloadRefreshing && !dataIsCurrent;
  const effectivePayloadStale = payloadStale && !dataIsCurrent;
  const totalPages = Math.max(1, Math.ceil(totalRows / pageSize));
  const visibleRows = useMemo(() => {
    if (config.serverPagination) return sortedRows;
    const start = (page - 1) * pageSize;
    return sortedRows.slice(start, start + pageSize);
  }, [config.serverPagination, page, pageSize, sortedRows]);
  const emptyMessage = effectivePayloadRefreshing
    ? config.refreshingEmptyMessage ?? 'Preparing latest strategy rows...'
    : 'No rows found.';
  const appTableRows = useMemo<StrategyAppTableRow[]>(() => visibleRows.map((row, rowIndex) => {
    const serialNo = (page - 1) * pageSize + rowIndex + 1;
    return {
      emaCells: adaptEmaTrendRow(row, serialNo - 1).cells,
      raw: row,
      serialNo,
    };
  }), [page, pageSize, visibleRows]);
  const appSortState = useMemo<AppSortState>(() => ({
    direction: sortDirection,
    key: sortKey,
  }), [sortDirection, sortKey]);
  const appColumns = useMemo<Array<AppDataTableColumn<StrategyAppTableRow>>>(() => config.columns.map((column) => {
    const cellKey = emaCellKey(column);
    const isMarketCapCell = cellKey === 'index' || cellKey === 'mcap' || cellKey === 'mcapRank';
    const isMarketCapToneCell = column.key === 'symbol' || isMarketCapCell;
    const alignClass = column.align === 'right'
      ? 'text-right'
      : column.align === 'center' || isMarketCapCell
        ? 'text-center'
        : 'text-left';
    return {
      cellClassName: cn('align-middle whitespace-nowrap', alignClass, isMarketCapToneCell && 'trend-mcap-cell'),
      dataCol: columnDataCol(column),
      getSortValue: (row) => {
        if (column.key === 'sNo') return row.serialNo;
        if (column.renderAs === 'srLevels') {
          const numericValue = pickStrategyField(row.raw, column.fields ?? []);
          if (typeof numericValue === 'number') return numericValue;
          const parsedValue = Number(numericValue);
          if (Number.isFinite(parsedValue) && String(numericValue).trim() !== '') return parsedValue;
          return formatStrategyCell(pickStrategyField(row.raw, [column.key, column.key.toUpperCase()]));
        }
        if (cellKey) return row.emaCells[cellKey]?.sort ?? null;
        return getStrategySortValue(row.raw, column);
      },
      key: column.key,
      label: <span className={cn('block', alignClass)}>{column.label}</span>,
      renderCell: (row) => {
        if (column.key === 'sNo') {
          return <span className="block text-center font-semibold">{row.serialNo}</span>;
        }
        if (column.key === 'symbol') {
          const cell = row.emaCells.symbol ?? { text: formatStrategyCell(pickStrategyField(row.raw, getColumnFieldCandidates(column))), sort: null };
          return (
            <TechnicalMarketCapCell tone={marketCapToneFromCell(row.emaCells.index)}>
              {cell.text}
            </TechnicalMarketCapCell>
          );
        }
        if (isMarketCapCell && cellKey) {
          const cell = row.emaCells[cellKey] ?? { text: '-', sort: null };
          return (
            <TechnicalMarketCapCell tone={marketCapToneFromCell(row.emaCells.index)}>
              {cell.text}
            </TechnicalMarketCapCell>
          );
        }
        if ((cellKey === 'ath' || cellKey === 'gap')) {
          return <StrategyEmaValueCell cell={row.emaCells[cellKey] ?? { text: '-', sort: null }} />;
        }
        if (column.renderAs === 'signedPercent') {
          return formatSignedPercentCell(pickStrategyField(row.raw, getColumnFieldCandidates(column)));
        }
        if (column.renderAs === 'srLevels') {
          const displayValue = pickStrategyField(row.raw, [column.key, column.key.toUpperCase()]);
          if (displayValue !== undefined) return formatStrategyCell(displayValue);
          return formatStrategyCell(pickStrategyField(row.raw, column.fields ?? []));
        }
        const value = pickStrategyField(row.raw, getColumnFieldCandidates(column));
        return column.key === 'ltcDate' ? formatStrategyDateCell(value) : formatStrategyCell(value);
      },
      sortable: column.sortable,
      sortType: columnSortType(column),
      sticky: column.sticky ? true : undefined,
      stickyWidthPx: column.sticky === 'sno' ? 88 : column.sticky === 'symbol' ? 180 : undefined,
    };
  }), [config.columns]);

  useEffect(() => {
    setAutoPollAttempts(0);
  }, [page, search, sortDirection, sortKey, timeframe]);

  useEffect(() => {
    if (dataIsCurrent && refreshTimerRef.current !== null) {
      window.clearTimeout(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }
    if (!config.pollWhileRefreshing || loading || refreshing || liveLoading || error || !effectivePayloadRefreshing) {
      return undefined;
    }
    const maxAttempts = config.refreshPollMaxAttempts ?? 24;
    if (autoPollAttempts >= maxAttempts) {
      return undefined;
    }
    const intervalMs = config.refreshPollIntervalMs ?? 5000;
    refreshTimerRef.current = window.setTimeout(() => {
      refreshTimerRef.current = null;
      setAutoPollAttempts((current) => current + 1);
      setAutoPollTick((current) => current + 1);
    }, intervalMs);
    return () => {
      if (refreshTimerRef.current !== null) {
        window.clearTimeout(refreshTimerRef.current);
        refreshTimerRef.current = null;
      }
    };
  }, [
    autoPollAttempts,
    config.pollWhileRefreshing,
    config.refreshPollIntervalMs,
    config.refreshPollMaxAttempts,
    dataIsCurrent,
    effectivePayloadRefreshing,
    error,
    liveLoading,
    loading,
    refreshing,
  ]);

  function toggleSort(column: StrategyTableColumn) {
    if (column.sortable === false) return;
    if (sortKey !== column.key) {
      setSortKey(column.key);
      setSortDirection('desc');
      setPage(1);
      return;
    }
    if (sortDirection === 'desc') {
      setSortDirection('asc');
      setPage(1);
      return;
    }
    setSortKey(null);
    setSortDirection(null);
    setPage(1);
  }

  function handleAppSortChange(nextSort: AppSortState) {
    setSortKey(nextSort.key);
    setSortDirection(nextSort.direction);
    setPage(1);
  }

  const toolbarLoading = loading || refreshing || liveLoading;
  const toolbarStatus: StrategyToolbarStatus = toolbarLoading
    ? 'syncing'
    : error || insertFailed
      ? 'error'
      : effectivePayloadStale || (lastRefreshedAt && !dataIsCurrent)
        ? 'stale'
        : lastRefreshedAt
          ? 'live'
          : 'idle';

  useEffect(() => {
    if (config.activeStrategyPage !== '/app/strategy/asura' || !lastRefreshedAt) return;
    recordDiagnostic({
      action: 'asura_runtime_state',
      component: 'StrategyApiScreenerPage',
      endpoint: lastApiUrlRef.current,
      kind: 'runtime',
      message: [
        `Status: ${toolbarStatus.toUpperCase()}`,
        `LTC_DATE: ${formatDisplayDateKey(dataDateKey)}`,
        `Expected Date: ${formatDisplayDateKey(expectedDateKey)}`,
        `Last refreshed: ${lastRefreshedAt.toLocaleTimeString('en-IN', { hour12: false })}`,
        `Load: ${loadDurationMs ?? '-'}ms`,
        `API: ${backendApiMs ?? '-'}ms`,
        `DB: ${backendDbMs ?? '-'}ms`,
        `Rows: ${rawRows.length}`,
        `In-flight: ${toolbarLoading}`,
        `Last API URL: ${lastApiUrlRef.current}`,
        `Last error: ${error || '-'}`,
      ].join('\n'),
      page: '/app/strategy/asura',
      severity: error ? 'error' : 'info',
    });
  }, [
    backendApiMs,
    backendDbMs,
    config.activeStrategyPage,
    dataDateKey,
    error,
    expectedDateKey,
    lastRefreshedAt,
    loadDurationMs,
    rawRows.length,
    toolbarLoading,
    toolbarStatus,
  ]);

  return (
    <StrategyMigrationLayout activeStrategyPage={config.activeStrategyPage} fullWidth>
      <div className="space-y-6">
        <PageHeader title={config.title} />

        <Card variant="light" padding="md" className="border-slate-200 shadow-sm dark:border-slate-700/70">
          <StrategyToolbar
            apiTimeMs={backendApiMs}
            dbTimeMs={backendDbMs}
            inserting={inserting}
            insertDisabled={visibleRows.length === 0}
            isLoading={toolbarLoading}
            lastRefreshed={lastRefreshedAt}
            liveLoading={liveLoading}
            loadTimeMs={loadDurationMs}
            ltcDate={dataDateKey}
            status={toolbarStatus}
            onInsertDb={config.insertEndpoint ? insertCurrentRows : undefined}
            onLiveRefresh={liveToolbarEnabled ? liveRefresh : undefined}
            onRefresh={refresh}
            onSearchChange={(value) => {
              setSearch(value);
              setPage(1);
            }}
            onTimeframeChange={(value) => {
              setTimeframe(value as Timeframe);
              setPage(1);
            }}
            refreshing={refreshing}
            searchValue={search}
            showInsertDb={Boolean(config.insertEndpoint)}
            showTimeframe
            showTotal={config.showToolbarTotal}
            timeframe={timeframe}
            timeframeOptions={TIMEFRAMES}
            total={totalRows}
          />
          {error ? <p className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-semibold text-rose-800">{error}</p> : null}
          {insertStatus ? <p className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-700 dark:border-slate-700/70 dark:bg-slate-900/80 dark:text-slate-300">{insertStatus}</p> : null}
        </Card>

        <Card variant="light" padding="none" className="overflow-hidden border-slate-200 shadow-sm dark:border-slate-700/70">
          {config.tableVariant === 'ema' ? (
            <AppDataTable
              className="px-4 pb-4 pt-1"
              columns={appColumns}
              currentPage={page}
              disableClientSort={config.serverPagination}
              emptyMessage={loading ? 'Loading strategy rows...' : emptyMessage}
              getRowKey={(row, index) => `${formatStrategyCell(pickStrategyField(row.raw, ['symbol', 'stock', 'stockName']))}-${row.serialNo}-${index}`}
              onPageChange={setPage}
              onSortChange={handleAppSortChange}
              pageSize={pageSize}
              paginationSummaryLabel="stocks"
              rows={loading ? [] : appTableRows}
              showTopPagination
              sortState={appSortState}
              tableClassName="data-table--green min-w-[2500px] text-sm [&_tbody_td]:align-middle [&_thead_th]:align-middle"
              tableId={strategyTableId(config.activeStrategyPage)}
              totalRows={totalRows}
            />
          ) : (
            <>
          <div className="overflow-x-auto">
            <table className="strategy-react-table min-w-full border-separate border-spacing-0 text-sm">
              <thead>
                <tr>
                  {config.columns.map((column) => (
                    <th
                      key={column.key}
                      className={cn(
                        'whitespace-nowrap border-b border-slate-200 bg-sky-50 px-3 py-3 text-left text-xs font-black uppercase tracking-[0.16em] text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200',
                        column.align === 'right' && 'text-right',
                        column.align === 'center' && 'text-center',
                        column.sticky === 'sno' && 'sticky left-0 z-30 min-w-[72px]',
                        column.sticky === 'symbol' && 'sticky left-[72px] z-30 min-w-[140px]',
                      )}
                    >
                      <button type="button" className="font-inherit text-inherit" onClick={() => toggleSort(column)}>
                        {column.label}
                        {sortKey === column.key && sortDirection ? ` ${sortDirection === 'asc' ? '↑' : '↓'}` : ''}
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td className="px-4 py-8 text-center text-slate-500 dark:text-slate-300" colSpan={config.columns.length}>Loading strategy rows...</td>
                  </tr>
                ) : visibleRows.length === 0 ? (
                  <tr>
                    <td className="px-4 py-8 text-center text-slate-500 dark:text-slate-300" colSpan={config.columns.length}>{emptyMessage}</td>
                  </tr>
                ) : visibleRows.map((row, rowIndex) => (
                  <tr
                    key={`${formatStrategyCell(pickStrategyField(row, ['symbol', 'stock', 'stockName']))}-${rowIndex}`}
                    className="odd:bg-white even:bg-slate-50 hover:bg-sky-50/70 dark:odd:bg-slate-950 dark:even:bg-slate-900/70 dark:hover:bg-slate-800/70"
                  >
                    {config.columns.map((column) => {
                      const value = column.key === 'sNo'
                        ? (page - 1) * pageSize + rowIndex + 1
                        : pickStrategyField(row, getColumnFieldCandidates(column));
                      return (
                        <td
                          key={`${column.key}-${rowIndex}`}
                          className={cn(
                            'whitespace-nowrap border-b border-slate-100 px-3 py-3 text-slate-700 dark:border-slate-800 dark:text-slate-200',
                            column.align === 'right' && 'text-right',
                            column.align === 'center' && 'text-center',
                            column.sticky === 'sno' && 'sticky left-0 z-20 bg-inherit font-semibold',
                            column.sticky === 'symbol' && 'sticky left-[72px] z-20 bg-inherit font-bold text-slate-950 shadow-[1px_0_0_rgba(148,163,184,0.25)] dark:text-slate-100 dark:shadow-[1px_0_0_rgba(51,65,85,0.75)]',
                          )}
                        >
                          {formatStrategyCell(value)}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex flex-col gap-3 border-t border-slate-200 px-4 py-4 sm:flex-row sm:items-center sm:justify-between dark:border-slate-700/70">
            <p className="text-sm font-semibold text-slate-500 dark:text-slate-300">
              Page {Math.min(page, totalPages)} of {totalPages} - Showing {visibleRows.length} rows
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900/80 dark:text-slate-200"
                disabled={page <= 1}
                onClick={() => setPage((current) => Math.max(1, current - 1))}
              >
                Prev
              </button>
              <button
                type="button"
                className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900/80 dark:text-slate-200"
                disabled={page >= totalPages}
                onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
              >
                Next
              </button>
            </div>
          </div>
            </>
          )}
        </Card>
      </div>
    </StrategyMigrationLayout>
  );
}
