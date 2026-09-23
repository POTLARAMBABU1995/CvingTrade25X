import type {
  EmaTrendPayloadWire,
  EmaTrendTableKey,
  EmaTrendWireRow,
  TechnicalTimeframe,
} from '../types/api/technical';
import {
  firstPresentValue,
  formatMarketCapRankValue,
  formatMarketCapValue,
  getMarketCapCategory,
  MARKET_CAP_INDEX_ALIASES,
  MARKET_CAP_RANK_ALIASES,
  MARKET_CAP_VALUE_ALIASES,
  normalizeMarketCapIndex,
} from './technicalMarketCap';

export const EMA_PAGE_SIZE = 15;
export const TREND_TIMEFRAME_STORAGE_KEY = 'TREND_TIMEFRAME';
export const TREND_LATEST_DATE_STORAGE_KEY = 'trend:lastKnownLtcDate';
export const TREND_LATEST_DATE_STORAGE_MAX_AGE_MS = 24 * 60 * 60 * 1000;
export const TREND_LATEST_DATE_POLL_INTERVAL_MS = 150000;

export const EMA_TABLE_KEYS: EmaTrendTableKey[] = [
  'ema20',
  'ema50',
  'ema5020',
  'ema100',
  'ema200',
  'ema200100',
  'ema20010050',
  'ema2001005020',
];

export type EmaTableTone = 'green' | 'orange' | 'yellow' | 'blue';

export type EmaTableConfig = {
  color: EmaTableTone;
  key: EmaTrendTableKey;
  showTopPagination: boolean;
  title: string;
};

export const EMA_TABLE_CONFIGS: EmaTableConfig[] = [
  { key: 'ema20', title: 'EMA>20', color: 'green', showTopPagination: true },
  { key: 'ema50', title: 'EMA>50', color: 'orange', showTopPagination: true },
  { key: 'ema200', title: 'EMA>200', color: 'yellow', showTopPagination: true },
  { key: 'ema200100', title: 'EMA>100>200', color: 'blue', showTopPagination: false },
  { key: 'ema20010050', title: 'EMA>50>100>200', color: 'orange', showTopPagination: true },
  { key: 'ema2001005020', title: 'EMA>20>50>100>200', color: 'green', showTopPagination: true },
];

export type EmaBaseColumnKey =
  | 'sNo'
  | 'symbol'
  | 'index'
  | 'mcap'
  | 'mcapRank'
  | 'ath'
  | 'price'
  | 'gap'
  | 'tradingDate'
  | 'ltcDate'
  | 'tradingDays';

export type EmaReturnColumnKey = `d${number}` | `y${number}`;
export type EmaColumnKey = EmaBaseColumnKey | EmaReturnColumnKey;

export type EmaSortType = 'date' | 'number' | 'string';
export type EmaCellTone = 'large' | 'mid' | 'negative' | 'positive' | 'small' | 'unknown';

export type EmaColumnDef = {
  key: EmaColumnKey;
  label: string;
  sortType: EmaSortType;
};

export type EmaViewCell = {
  sort: number | string | null;
  text: string;
  title?: string;
  tone?: EmaCellTone;
};

export type EmaViewRow = {
  cells: Record<string, EmaViewCell>;
  id: string;
  raw: EmaTrendWireRow;
  symbol: string;
};

export type EmaTrendViewPayload = {
  athSource?: string | null;
  cached?: boolean;
  cachedAt?: string | null;
  fallback?: boolean;
  latestLtcDateKey: string | null;
  returnColumns: EmaColumnDef[];
  refreshing?: boolean;
  stale?: boolean;
  tables: Record<EmaTrendTableKey, EmaViewRow[]>;
  timeframe: TechnicalTimeframe;
  totalSymbols: number | null;
};

export type EmaTenureOption = {
  count: number;
  label: string;
  value: number;
};

export type EmaDownloadTenureYears = 1 | 2 | 3 | 4 | 5;

export const EMA_DOWNLOAD_TENURE_OPTIONS: Array<{
  label: string;
  maximumTradingDays: number;
  years: EmaDownloadTenureYears;
}> = [1, 2, 3, 4, 5].map((years) => ({
  label: `T_D < ${years}Y`,
  maximumTradingDays: years * 252,
  years: years as EmaDownloadTenureYears,
}));

const TIMEFRAMES: TechnicalTimeframe[] = ['daily', 'weekly', 'monthly', 'yearly'];
const MIN_YEAR_RETURN_COLUMNS = 27;
const YEAR_RETURN_KEY_PATTERN = /^y([1-9]\d*)$/i;

const DAY_RETURN_COLUMNS: EmaColumnDef[] = [
  { key: 'd5', label: '5D', sortType: 'number' },
  { key: 'd10', label: '10D', sortType: 'number' },
  { key: 'd15', label: '15D', sortType: 'number' },
  { key: 'd22', label: '22D', sortType: 'number' },
  { key: 'd44', label: '44D', sortType: 'number' },
  { key: 'd66', label: '66D', sortType: 'number' },
  { key: 'd88', label: '88D', sortType: 'number' },
  { key: 'd132', label: '132D', sortType: 'number' },
  { key: 'd198', label: '198D', sortType: 'number' },
];

function createYearRange(maxYear: number): number[] {
  const safeMax = Math.max(MIN_YEAR_RETURN_COLUMNS, Math.floor(Number(maxYear) || 0));
  return Array.from({ length: safeMax }, (_, index) => index + 1);
}

function createYearReturnColumns(maxYear: number): EmaColumnDef[] {
  return createYearRange(maxYear).map((year) => ({
    key: `y${year}` as EmaReturnColumnKey,
    label: `${year}Y`,
    sortType: 'number',
  }));
}

export const RETURN_COLUMNS: EmaColumnDef[] = [
  ...DAY_RETURN_COLUMNS,
  ...createYearReturnColumns(MIN_YEAR_RETURN_COLUMNS),
];

const BASE_COLUMNS: EmaColumnDef[] = [
  { key: 'sNo', label: 'S.NO', sortType: 'number' },
  { key: 'symbol', label: 'SYMBOL', sortType: 'string' },
  { key: 'index', label: 'INDEX', sortType: 'string' },
  { key: 'mcap', label: 'MCAP', sortType: 'number' },
  { key: 'mcapRank', label: 'MCAP_RANK', sortType: 'number' },
  { key: 'ath', label: 'ATH', sortType: 'number' },
  { key: 'price', label: 'PRICE', sortType: 'number' },
  { key: 'gap', label: 'GAP', sortType: 'number' },
  { key: 'tradingDate', label: 'TRADING_DATE', sortType: 'date' },
  { key: 'ltcDate', label: 'LTC_DATE', sortType: 'date' },
  { key: 'tradingDays', label: 'T_D', sortType: 'number' },
];

export const EMA_COLUMNS: EmaColumnDef[] = [
  ...BASE_COLUMNS,
  ...RETURN_COLUMNS,
];

export function getEmaTradingDays(row: EmaViewRow): number | null {
  return toNumber(
    row.cells.tradingDays?.sort ??
    row.cells.tradingDays?.text ??
    row.raw.tradingDays ??
    row.raw.TRADING_DAYS ??
    row.raw.trading_days ??
    row.raw.T_D ??
    row.raw.t_d,
  );
}

export function filterEmaRowsForDownload(
  rows: EmaViewRow[],
  tenureYears: EmaDownloadTenureYears | null,
): EmaViewRow[] {
  if (tenureYears === null) return [];
  const maximumTradingDays = tenureYears * 252;
  return rows.filter((row) => {
    if (!row.symbol.trim()) return false;
    const tradingDays = getEmaTradingDays(row);
    return tradingDays !== null && tradingDays > 0 && tradingDays < maximumTradingDays;
  });
}

export function buildEmaSymbolsTxt(rows: EmaViewRow[]): string {
  return rows.map((row) => row.symbol.trim()).filter(Boolean).join(',');
}

function csvValue(value: string): string {
  return /[",\r\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

export function buildEmaSymbolsCsv(rows: EmaViewRow[]): string {
  const body = rows.map((row, index) => [
    String(index + 1),
    csvValue(row.symbol.trim()),
    String(getEmaTradingDays(row) ?? ''),
  ].join(','));
  return ['s.no,symbol,t_d', ...body].join('\n');
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object';
}

function ensureRows(value: unknown): EmaTrendWireRow[] {
  return Array.isArray(value) ? value.filter(isRecord) as EmaTrendWireRow[] : [];
}

function yearFromReturnKey(value: unknown): number | null {
  const match = String(value ?? '').trim().match(YEAR_RETURN_KEY_PATTERN);
  if (!match) return null;
  const year = Number(match[1]);
  return Number.isInteger(year) && year > 0 ? year : null;
}

function collectMetadataYears(value: unknown): number[] {
  if (!Array.isArray(value)) return [];
  const years: number[] = [];
  value.forEach((item) => {
    if (isRecord(item)) {
      const fromKey = yearFromReturnKey(item.key);
      const fromYears = Number(item.years);
      if (fromKey) years.push(fromKey);
      if (Number.isInteger(fromYears) && fromYears > 0) years.push(fromYears);
      return;
    }
    const fromKey = yearFromReturnKey(item);
    if (fromKey) years.push(fromKey);
  });
  return years;
}

function collectRowYears(source: Record<string, unknown>): number[] {
  const years: number[] = [];
  EMA_TABLE_KEYS.forEach((tableKey) => {
    ensureRows(source[tableKey]).forEach((row) => {
      Object.keys(row).forEach((key) => {
        const baseKey = key.replace(/Sort$/i, '');
        const year = yearFromReturnKey(baseKey);
        if (year) years.push(year);
      });
    });
  });
  return years;
}

function maxNumber(defaultValue: number, values: number[]): number {
  return values.reduce((maxValue, value) => (
    Number.isFinite(value) && value > maxValue ? value : maxValue
  ), defaultValue);
}

function maxYearReturnColumn(payload: EmaTrendPayloadWire | null | undefined): number {
  const source = payload && isRecord(payload) ? payload : {};
  const maxFromPayload = Number(source.yearReturnMaxYear);
  const years = [
    ...(Number.isInteger(maxFromPayload) && maxFromPayload > 0 ? [maxFromPayload] : []),
    ...collectMetadataYears(source.yearReturnColumns),
    ...collectMetadataYears(source.returnColumns),
    ...collectRowYears(source),
  ];
  return maxNumber(MIN_YEAR_RETURN_COLUMNS, years);
}

export function buildReturnColumns(payload: EmaTrendPayloadWire | null | undefined): EmaColumnDef[] {
  return [
    ...DAY_RETURN_COLUMNS,
    ...createYearReturnColumns(maxYearReturnColumn(payload)),
  ];
}

export function buildEmaColumns(payload: EmaTrendPayloadWire | null | undefined): EmaColumnDef[] {
  return [
    ...BASE_COLUMNS,
    ...buildReturnColumns(payload),
  ];
}

function firstValue(row: Record<string, unknown>, keys: string[]): unknown {
  for (const key of keys) {
    const value = row[key];
    if (value === undefined || value === null) continue;
    if (String(value).trim() === '') continue;
    return value;
  }
  return null;
}

export function toNumber(value: unknown): number | null {
  if (value === undefined || value === null || value === '') return null;
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  const cleaned = String(value).replace(/,/g, '').replace(/%/g, '').trim();
  if (!cleaned || cleaned === '-') return null;
  const parsed = Number(cleaned);
  return Number.isFinite(parsed) ? parsed : null;
}

function toIntegerCount(value: unknown): number | null {
  const parsed = toNumber(value);
  if (!Number.isFinite(parsed)) return null;
  return Math.max(0, Math.floor(parsed as number));
}

function parseDateValue(value: unknown): Date | null {
  if (value === undefined || value === null || value === '') return null;
  if (value instanceof Date) {
    const ts = value.getTime();
    return Number.isNaN(ts) ? null : new Date(ts);
  }
  if (typeof value === 'number') {
    const normalized = value < 1000000000000 ? value * 1000 : value;
    const date = new Date(normalized);
    return Number.isNaN(date.getTime()) ? null : date;
  }
  const text = String(value).trim();
  if (!text) return null;
  const ddmmyyyy = text.match(/^(\d{1,2})-(\d{1,2})-(\d{4})$/);
  if (ddmmyyyy) {
    const [, d, m, y] = ddmmyyyy;
    const date = new Date(Number(y), Number(m) - 1, Number(d));
    return Number.isNaN(date.getTime()) ? null : date;
  }
  const iso = new Date(text);
  return Number.isNaN(iso.getTime()) ? null : iso;
}

function toEpochMs(value: unknown): number | null {
  const parsed = parseDateValue(value);
  if (!parsed) return null;
  const ts = parsed.getTime();
  return Number.isNaN(ts) ? null : ts;
}

function formatDateDDMMYYYY(value: unknown): string {
  const parsed = parseDateValue(value);
  if (!parsed) return '';
  const dd = String(parsed.getDate()).padStart(2, '0');
  const mm = String(parsed.getMonth() + 1).padStart(2, '0');
  return `${dd}-${mm}-${parsed.getFullYear()}`;
}

function formatDateKey(value: unknown): string | null {
  const parsed = parseDateValue(value);
  if (!parsed) return null;
  const yyyy = String(parsed.getFullYear());
  const mm = String(parsed.getMonth() + 1).padStart(2, '0');
  const dd = String(parsed.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

function resolveDateCell(row: Record<string, unknown>, keys: string[], sortKeys: string[]): EmaViewCell {
  const primary = firstValue(row, keys);
  const fallbackSort = firstValue(row, sortKeys);
  const parsed = parseDateValue(primary);
  const sort = parsed ? parsed.getTime() : toEpochMs(fallbackSort);
  if (parsed) {
    return { text: formatDateDDMMYYYY(parsed), sort: parsed.getTime() };
  }
  if (Number.isFinite(sort)) {
    return { text: formatDateDDMMYYYY(sort), sort };
  }
  const text = primary === undefined || primary === null ? '' : String(primary).trim();
  return { text: text || '-', sort: Number.isFinite(sort) ? sort : null };
}

function formatPlainNumber(value: number): string {
  return Number.isInteger(value)
    ? value.toLocaleString()
    : value.toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 0 });
}

function toneFromNumber(value: number | null): EmaCellTone | undefined {
  if (!Number.isFinite(value)) return undefined;
  if ((value as number) > 0) return 'positive';
  if ((value as number) < 0) return 'negative';
  return undefined;
}

function indexTone(value: string): EmaCellTone | undefined {
  if (value === 'LARGE') return 'large';
  if (value === 'MID') return 'mid';
  if (value === 'SMALL') return 'small';
  if (value === '-') return 'unknown';
  return undefined;
}

function marketCapCells(row: Record<string, unknown>): Pick<Record<EmaBaseColumnKey, EmaViewCell>, 'index' | 'mcap' | 'mcapRank'> {
  const indexValue = firstPresentValue(row, MARKET_CAP_INDEX_ALIASES);
  const mcapValue = firstPresentValue(row, MARKET_CAP_VALUE_ALIASES);
  const rankValue = firstPresentValue(row, MARKET_CAP_RANK_ALIASES);
  const indexText = normalizeMarketCapIndex(indexValue);
  const indexCategory = getMarketCapCategory(indexValue);
  const mcapNum = toNumber(mcapValue);
  const rankNum = toNumber(rankValue);
  return {
    index: { text: indexText, sort: indexText, tone: indexTone(indexText) ?? indexCategory },
    mcap: { text: formatMarketCapValue(mcapValue), sort: mcapNum, tone: indexCategory },
    mcapRank: { text: formatMarketCapRankValue(rankValue), sort: rankNum, tone: indexCategory },
  };
}

function symbolFromRow(row: Record<string, unknown>): string {
  const value = firstValue(row, ['symbol', 'SYMBOL', 'stock', 'ticker', 'name']);
  return value === undefined || value === null ? '' : String(value).trim();
}

function sNoCell(row: Record<string, unknown>, fallbackIndex: number): EmaViewCell {
  const raw = firstValue(row, ['sNo', 'S_NO', 'sno', 'serial']);
  const value = raw === null ? fallbackIndex + 1 : raw;
  return { text: String(value), sort: toNumber(value) ?? fallbackIndex + 1 };
}

function priceCell(row: Record<string, unknown>): EmaViewCell {
  const num = toNumber(firstValue(row, ['priceSort', 'PRICE_SORT', 'price', 'PRICE']));
  if (Number.isFinite(num)) {
    return { text: formatPlainNumber(num as number), sort: num, tone: toneFromNumber(num) };
  }
  const raw = firstValue(row, ['price', 'PRICE']);
  return { text: raw === null ? '-' : String(raw), sort: null };
}

function athCell(row: Record<string, unknown>): EmaViewCell {
  const num = toNumber(firstValue(row, ['athSort', 'ATH_SORT', 'ath', 'ATH']));
  const athDate = firstValue(row, ['ath_date', 'athDate', 'ATH_DATE']);
  if (Number.isFinite(num)) {
    return {
      text: Number.isInteger(num as number)
        ? (num as number).toLocaleString()
        : (num as number).toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 2 }),
      sort: num,
      title: athDate ? `ATH Date: ${String(athDate)}` : undefined,
    };
  }
  const raw = firstValue(row, ['ath', 'ATH']);
  return { text: raw === null ? '-' : String(raw), sort: null };
}

function gapCell(row: Record<string, unknown>, price: EmaViewCell, ath: EmaViewCell): EmaViewCell {
  let num = toNumber(firstValue(row, ['gapSort', 'GAP_SORT', 'gap', 'GAP']));
  const priceNum = typeof price.sort === 'number' ? price.sort : null;
  const athNum = typeof ath.sort === 'number' ? ath.sort : null;
  if (!Number.isFinite(num) && Number.isFinite(priceNum) && Number.isFinite(athNum) && athNum !== 0) {
    num = (((priceNum as number) - (athNum as number)) / (athNum as number)) * 100;
  }
  if (Number.isFinite(num)) {
    return { text: `${(num as number) > 0 ? '+' : ''}${(num as number).toFixed(2)}%`, sort: num, tone: toneFromNumber(num) };
  }
  const raw = firstValue(row, ['gap', 'GAP']);
  return { text: raw === null ? '-' : String(raw), sort: null };
}

function numericTextCell(row: Record<string, unknown>, keys: string[]): EmaViewCell {
  const raw = firstValue(row, keys);
  const num = toNumber(raw);
  if (Number.isFinite(num)) {
    return { text: raw === null ? '-' : String(raw), sort: num };
  }
  return { text: raw === null ? '-' : String(raw), sort: null };
}

function returnCell(row: Record<string, unknown>, key: EmaColumnKey): EmaViewCell {
  const raw = firstValue(row, [key, key.toUpperCase()]);
  const sort = toNumber(firstValue(row, [`${key}Sort`, `${key.toUpperCase()}_SORT`])) ?? toNumber(raw);
  if (raw === null) {
    return { text: '-', sort, tone: toneFromNumber(sort) };
  }
  const text = String(raw).trim() || '-';
  return { text, sort, tone: toneFromNumber(sort) };
}

export function adaptEmaTrendRow(row: EmaTrendWireRow, index: number, returnColumns: EmaColumnDef[] = RETURN_COLUMNS): EmaViewRow {
  const source = row as Record<string, unknown>;
  const symbol = symbolFromRow(source);
  const marketCap = marketCapCells(source);
  const price = priceCell(source);
  const ath = athCell(source);
  const gap = gapCell(source, price, ath);
  const tradingDate = resolveDateCell(source, [
    'tradingDate',
    'TRADING_DATE',
    'trading_date',
    'firstTradeDate',
    'first_trade_date',
    'tradingDateMin',
    'sinceDate',
    'SINCE_DATE',
  ], ['tradingDateSort', 'TRADING_DATE_SORT', 'trading_date_sort', 'firstTradeDateSort']);
  const ltcDate = resolveDateCell(source, [
    'ltcDate',
    'LTC_DATE',
    'ltc_date',
    'latestTradingDate',
    'latest_trade_date',
    'tradingDateMax',
    'lastTradeDate',
    'LAST_TRADE_DATE',
  ], ['ltcDateSort', 'LTC_DATE_SORT', 'ltc_date_sort']);

  const cells: Record<string, EmaViewCell> = {
    sNo: sNoCell(source, index),
    symbol: { text: symbol || '-', sort: symbol || '', tone: marketCap.index.tone ?? 'unknown' },
    index: marketCap.index,
    mcap: marketCap.mcap,
    mcapRank: marketCap.mcapRank,
    ath,
    price,
    gap,
    tradingDate,
    ltcDate,
    tradingDays: numericTextCell(source, ['tradingDays', 'TRADING_DAYS', 'trading_days']),
  };

  returnColumns.forEach((column) => {
    cells[column.key] = returnCell(source, column.key);
  });

  return {
    cells,
    id: `${symbol || 'row'}-${index}`,
    raw: row,
    symbol,
  };
}

export function normalizeTimeframe(value: unknown): TechnicalTimeframe {
  const text = String(value || '').toLowerCase();
  return TIMEFRAMES.includes(text as TechnicalTimeframe) ? text as TechnicalTimeframe : 'daily';
}

export function adaptEmaTrendPayload(payload: EmaTrendPayloadWire | null | undefined): EmaTrendViewPayload {
  const source = payload && isRecord(payload) ? payload : {};
  const summary = isRecord(source.summary) ? source.summary : {};
  const returnColumns = buildReturnColumns(payload);
  const tables = EMA_TABLE_KEYS.reduce((acc, key) => {
    acc[key] = ensureRows(source[key]).map((row, rowIndex) => adaptEmaTrendRow(row, rowIndex, returnColumns));
    return acc;
  }, {} as Record<EmaTrendTableKey, EmaViewRow[]>);
  const totalSymbols = toIntegerCount(
    firstValue(source, ['totalSymbols', 'total_symbols']) ??
    firstValue(summary, ['totalSymbols', 'total_symbols']),
  );

  return {
    athSource: typeof source.athSource === 'string' ? source.athSource : null,
    cached: Boolean(source.cached),
    cachedAt: typeof source.cachedAt === 'string' ? source.cachedAt : null,
    fallback: Boolean(source.fallback),
    latestLtcDateKey: getLatestLtcDateKey(payload),
    returnColumns,
    refreshing: Boolean(source.refreshing),
    stale: Boolean(source.stale),
    tables,
    timeframe: normalizeTimeframe(source.timeframe),
    totalSymbols,
  };
}

export function filterEmaRowsBySymbol(rows: EmaViewRow[], query: string): EmaViewRow[] {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return rows;
  return rows.filter((row) => row.symbol.toLowerCase().includes(normalized));
}

export function normalizeLatestDateKey(value: unknown): string | null {
  if (value === undefined || value === null) return null;
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value.trim())) return value.trim();
  return formatDateKey(value);
}

export function formatLatestDateDisplay(dateKey: string | null | undefined): string {
  const key = normalizeLatestDateKey(dateKey);
  if (!key) return '--';
  const [yyyy, mm, dd] = key.split('-');
  return `${dd}-${mm}-${yyyy}`;
}

export function formatLocalRefreshTime(epochMs: number | null | undefined): string {
  if (!Number.isFinite(epochMs)) return '--';
  const date = new Date(epochMs as number);
  if (Number.isNaN(date.getTime())) return '--';
  const hh = String(date.getHours()).padStart(2, '0');
  const mm = String(date.getMinutes()).padStart(2, '0');
  const ss = String(date.getSeconds()).padStart(2, '0');
  return `${hh}:${mm}:${ss}`;
}

function getRowTradeMs(row: EmaTrendWireRow): number | null {
  const source = row as Record<string, unknown>;
  return toEpochMs(source.ltcDateSort) ??
    toEpochMs(source.LTC_DATE_SORT) ??
    toEpochMs(source.ltc_date_sort) ??
    toEpochMs(source.ltcDate) ??
    toEpochMs(source.LTC_DATE) ??
    toEpochMs(source.ltc_date) ??
    toEpochMs(source.latestTradingDate) ??
    toEpochMs(source.latest_trade_date) ??
    toEpochMs(source.tradingDateMax) ??
    toEpochMs(source.tradingDateSort) ??
    toEpochMs(source.TRADING_DATE_SORT) ??
    toEpochMs(source.tradingDate) ??
    toEpochMs(source.TRADING_DATE) ??
    toEpochMs(source.trading_date);
}

export function getLatestLtcDateKey(payload: EmaTrendPayloadWire | null | undefined): string | null {
  if (!payload || !isRecord(payload)) return null;
  let latestKey: string | null = null;
  EMA_TABLE_KEYS.forEach((key) => {
    ensureRows(payload[key]).forEach((row) => {
      const source = row as Record<string, unknown>;
      const raw = firstValue(source, [
        'ltcDate',
        'LTC_DATE',
        'ltc_date',
        'latestTradingDate',
        'latest_trade_date',
        'tradingDateMax',
        'lastTradeDate',
        'LAST_TRADE_DATE',
        'ltcDateSort',
        'LTC_DATE_SORT',
        'ltc_date_sort',
      ]);
      const dateKey = normalizeLatestDateKey(raw) ?? normalizeLatestDateKey(getRowTradeMs(row));
      if (dateKey && (!latestKey || dateKey > latestKey)) {
        latestKey = dateKey;
      }
    });
  });
  return latestKey;
}

export function estimateTenureYears(row: EmaTrendWireRow): number | null {
  const source = row as Record<string, unknown>;
  const firstTradeRaw = firstValue(source, [
    'firstTradeDate',
    'first_trade_date',
    'tradingDate',
    'TRADING_DATE',
    'trading_date',
    'firstTradeDateSort',
    'tradingDateSort',
  ]);
  const referenceDateRaw = firstValue(source, [
    'ltcDate',
    'LTC_DATE',
    'ltc_date',
    'latestTradingDate',
    'latest_trade_date',
    'tradingDateMax',
    'ltcDateSort',
  ]);
  const firstTrade = parseDateValue(firstTradeRaw);
  const referenceDate = parseDateValue(referenceDateRaw) ?? new Date();
  if (firstTrade && referenceDate) {
    const diffMs = referenceDate.getTime() - firstTrade.getTime();
    if (diffMs > 0) {
      return Math.floor(diffMs / (365.25 * 24 * 60 * 60 * 1000));
    }
  }
  const calendarDays = Number(source.calendarDays ?? source.calendarDaysSort);
  if (Number.isFinite(calendarDays) && calendarDays > 0) {
    return Math.floor(calendarDays / 365);
  }
  const tradingDays = Number(source.tradingDays ?? source.tradingDaysSort);
  if (Number.isFinite(tradingDays) && tradingDays > 0) {
    return Math.floor(tradingDays / 252);
  }
  return null;
}

export function buildTenureOptions(payload: EmaTrendPayloadWire | null | undefined): EmaTenureOption[] {
  const source = payload && isRecord(payload) ? payload : {};
  const rows = ensureRows(source.ema20 ?? source.ema50 ?? source.ema200);
  const tenureYears = createYearRange(maxNumber(
    maxYearReturnColumn(payload),
    rows.map((row) => estimateTenureYears(row) ?? 0),
  ));
  const counts = tenureYears.map(() => 0);
  rows.forEach((row) => {
    const rowTenureYears = estimateTenureYears(row);
    if (!Number.isFinite(rowTenureYears)) return;
    const capped = Math.max(1, Math.min(rowTenureYears as number, tenureYears.length));
    if (capped >= 1) {
      counts[capped - 1] += 1;
    }
  });
  return tenureYears.map((year, index) => ({
    count: counts[index],
    label: `${year}Y : ${counts[index]}`,
    value: year,
  }));
}

export type LatestDateCache = {
  fetchedAtMs: number;
  ltcDate: string;
};

export function readLatestDateCache(storage: Storage = window.localStorage): LatestDateCache | null {
  try {
    const raw = storage.getItem(TREND_LATEST_DATE_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { fetched_at_ms?: unknown; ltc_date?: unknown };
    const ltcDate = normalizeLatestDateKey(parsed.ltc_date);
    const fetchedAtMs = Number(parsed.fetched_at_ms);
    if (!ltcDate || !Number.isFinite(fetchedAtMs)) return null;
    if (Date.now() - fetchedAtMs > TREND_LATEST_DATE_STORAGE_MAX_AGE_MS) return null;
    return { fetchedAtMs, ltcDate };
  } catch {
    return null;
  }
}

export function saveLatestDateCache(ltcDate: string, fetchedAtMs: number, storage: Storage = window.localStorage): void {
  try {
    storage.setItem(TREND_LATEST_DATE_STORAGE_KEY, JSON.stringify({
      fetched_at_ms: Number.isFinite(fetchedAtMs) ? fetchedAtMs : Date.now(),
      ltc_date: normalizeLatestDateKey(ltcDate),
    }));
  } catch {
    // Storage can fail in private mode; the network contract remains unchanged.
  }
}
