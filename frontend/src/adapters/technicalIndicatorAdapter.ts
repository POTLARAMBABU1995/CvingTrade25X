import type { AppSortType } from '../components/app/AppDataTable';
import type {
  TechnicalIndicatorKind,
  TechnicalIndicatorPayloadWire,
  TechnicalIndicatorScreenWireRow,
  TechnicalTimeframe,
} from '../types/api/technical';
import {
  firstPresentValue,
  formatMarketCapRankValue,
  formatMarketCapValue,
  getMarketCapCategory,
  normalizeMarketCapIndex,
  MARKET_CAP_INDEX_ALIASES,
  MARKET_CAP_RANK_ALIASES,
  MARKET_CAP_VALUE_ALIASES,
  toNumber,
} from './technicalMarketCap';
import { normalizeLatestDateKey, normalizeTimeframe } from './technicalEmaAdapter';

export type IndicatorCellTone = 'large' | 'mid' | 'negative' | 'positive' | 'small' | 'unknown';

export type TechnicalIndicatorColumnDef = {
  dataCol?: string;
  key: string;
  label: string;
  showArrow?: boolean;
  sortType: AppSortType;
};

export type TechnicalIndicatorPageConfig = {
  activeTechnicalPage: string;
  emptyMessage: string;
  heading: string;
  kind: TechnicalIndicatorKind;
  pageSize: number;
  tableClassName?: string;
  tableId: string;
  tableTitle: string;
  columns: TechnicalIndicatorColumnDef[];
};

export type TechnicalIndicatorViewCell = {
  sort: number | string | null;
  text: string;
  tone?: IndicatorCellTone;
};

export type TechnicalIndicatorViewRow = {
  cells: Record<string, TechnicalIndicatorViewCell>;
  id: string;
  raw: TechnicalIndicatorScreenWireRow;
  symbol: string;
};

export type TechnicalIndicatorViewPayload = {
  cached?: boolean;
  cachedAt?: string | null;
  count: number;
  fallback?: boolean;
  latestLtcDateKey: string | null;
  refreshing?: boolean;
  rows: TechnicalIndicatorViewRow[];
  stale?: boolean;
  timeframe: TechnicalTimeframe;
};

const COMMON_COLUMNS: TechnicalIndicatorColumnDef[] = [
  { key: 'sNo', label: 'S.NO', sortType: 'number' },
  { key: 'symbol', label: 'SYMBOL', sortType: 'string' },
  { key: 'index', label: 'INDEX', sortType: 'string' },
  { key: 'mcap', label: 'MCAP', sortType: 'number' },
  { key: 'mcapRank', label: 'MCAP_RANK', sortType: 'number' },
  { key: 'price', label: 'PRICE', sortType: 'number' },
  { key: 'tradingDate', label: 'TRADING_DATE', sortType: 'date' },
  { key: 'ltcDate', label: 'LTC_DATE', sortType: 'date' },
  { key: 'tradingDays', label: 'T_D', sortType: 'number' },
];

const RETURN_COLUMNS: TechnicalIndicatorColumnDef[] = [
  { key: 'd5', label: '5D', showArrow: true, sortType: 'number' },
  { key: 'd10', label: '10D', showArrow: true, sortType: 'number' },
  { key: 'd15', label: '15D', showArrow: true, sortType: 'number' },
  { key: 'd22', label: '22D', showArrow: true, sortType: 'number' },
  { key: 'd44', label: '44D', showArrow: true, sortType: 'number' },
  { key: 'd66', label: '66D', showArrow: true, sortType: 'number' },
  { key: 'd88', label: '88D', showArrow: true, sortType: 'number' },
];

export const TECHNICAL_INDICATOR_CONFIGS = {
  adx: {
    activeTechnicalPage: '/app/technical/adx',
    columns: [
      ...COMMON_COLUMNS.map((column) => column.key === 'tradingDays' ? { ...column, dataCol: 'td' } : column),
      { key: 'adxGt20', label: 'ADX>20', sortType: 'number' },
      { key: 'adxGt25', label: 'ADX>25', sortType: 'number' },
      { key: 'plusDm', label: '+DM', sortType: 'number' },
      { key: 'minusDm', label: '-DM', sortType: 'number' },
      { key: 'adxScore', label: 'ADX_SCORE', sortType: 'number' },
    ],
    emptyMessage: 'No ADX rows returned from backend.',
    heading: 'ADX',
    kind: 'adx',
    pageSize: 15,
    tableClassName: 'data-table--blue',
    tableId: 'tblAdx',
    tableTitle: 'ADX',
  },
  atr14: {
    activeTechnicalPage: '/app/technical/atr14',
    columns: [
      ...COMMON_COLUMNS.map((column) => column.key === 'tradingDays' ? { ...column, dataCol: 'td' } : column),
      { key: 'atr', label: 'ATR', sortType: 'number' },
      { key: 'atrScore', label: 'ATR_SCORE', sortType: 'number' },
    ],
    emptyMessage: 'No ATR rows returned from backend.',
    heading: 'ATR 14',
    kind: 'atr14',
    pageSize: 15,
    tableClassName: 'data-table--orange',
    tableId: 'tblAtr',
    tableTitle: 'ATR14',
  },
  macd: {
    activeTechnicalPage: '/app/technical/macd',
    columns: [
      ...COMMON_COLUMNS,
      { key: 'macdScore', label: 'MACD', sortType: 'number' },
      ...RETURN_COLUMNS,
    ],
    emptyMessage: 'No MACD rows returned from backend.',
    heading: 'MACD > 0',
    kind: 'macd',
    pageSize: 10,
    tableClassName: 'data-table--yellow',
    tableId: 'tblMacd',
    tableTitle: 'MACD > 0',
  },
  volume: {
    activeTechnicalPage: '/app/technical/volume',
    columns: [
      ...COMMON_COLUMNS.map((column) => column.key === 'tradingDays' ? { ...column, dataCol: 'td' } : column),
      { key: 'volume', label: 'VOLUME', sortType: 'number' },
      { key: 'volumeAvg20', label: 'AVG_20', sortType: 'number' },
      { key: 'volumeRatio', label: 'RATIO', sortType: 'number' },
      { key: 'volumeScore', label: 'VOLUME_SCORE', sortType: 'number' },
    ],
    emptyMessage: 'No Volume MA>20 symbols returned from backend.',
    heading: 'Volume MA > 20',
    kind: 'volume',
    pageSize: 15,
    tableClassName: 'data-table--green',
    tableId: 'volumeTable',
    tableTitle: 'Volume MA > 20',
  },
  rsi50: {
    activeTechnicalPage: '/app/technical/rsi50',
    columns: [
      ...COMMON_COLUMNS,
      { key: 'rsi', label: 'RSI', sortType: 'number' },
      { key: 'rsiScore', label: 'RSI_SCORE', sortType: 'number' },
    ],
    emptyMessage: 'No RSI>50 symbols returned from backend.',
    heading: 'RSI > 50',
    kind: 'rsi50',
    pageSize: 15,
    tableId: 'rsi50Table',
    tableTitle: 'RSI > 50',
  },
} satisfies Record<TechnicalIndicatorKind, TechnicalIndicatorPageConfig>;

const DISABLED_SINCE_TARGET = { day: 1, month: 1, year: 1998 };

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object';
}

function ensureRows(value: unknown): TechnicalIndicatorScreenWireRow[] {
  return Array.isArray(value) ? value.filter(isRecord) as TechnicalIndicatorScreenWireRow[] : [];
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
  if (/^\d+$/.test(text)) return parseDateValue(Number(text));
  const normalized = text.replace(/[\/]/g, '-');
  const ddmmyyyy = normalized.match(/^(\d{1,2})-(\d{1,2})-(\d{4})$/);
  if (ddmmyyyy) {
    const [, d, m, y] = ddmmyyyy;
    const date = new Date(Number(y), Number(m) - 1, Number(d));
    return Number.isNaN(date.getTime()) ? null : date;
  }
  const iso = new Date(normalized);
  return Number.isNaN(iso.getTime()) ? null : iso;
}

function dateParts(value: unknown): { day: number; month: number; year: number } | null {
  const parsed = parseDateValue(value);
  if (!parsed) return null;
  return { day: parsed.getDate(), month: parsed.getMonth() + 1, year: parsed.getFullYear() };
}

function isDisabledSince(value: unknown): boolean {
  const parts = dateParts(value);
  return Boolean(parts &&
    parts.year === DISABLED_SINCE_TARGET.year &&
    parts.month === DISABLED_SINCE_TARGET.month &&
    parts.day === DISABLED_SINCE_TARGET.day);
}

function formatDateDDMMYYYY(value: unknown): string {
  const parsed = parseDateValue(value);
  if (!parsed) return '';
  const dd = String(parsed.getDate()).padStart(2, '0');
  const mm = String(parsed.getMonth() + 1).padStart(2, '0');
  return `${dd}-${mm}-${parsed.getFullYear()}`;
}

function toEpochMs(value: unknown): number | null {
  const parsed = parseDateValue(value);
  if (!parsed) return null;
  const ts = parsed.getTime();
  return Number.isNaN(ts) ? null : ts;
}

function formatPlainNumber(value: number): string {
  return Number.isInteger(value)
    ? value.toLocaleString()
    : value.toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 0 });
}

function toneFromNumber(value: number | null): IndicatorCellTone | undefined {
  if (!Number.isFinite(value)) return undefined;
  if ((value as number) > 0) return 'positive';
  if ((value as number) < 0) return 'negative';
  return undefined;
}

function indexTone(value: string): IndicatorCellTone | undefined {
  if (value === 'LARGE') return 'large';
  if (value === 'MID') return 'mid';
  if (value === 'SMALL') return 'small';
  if (value === '-') return 'unknown';
  return undefined;
}

function marketCapCells(row: Record<string, unknown>): Pick<Record<string, TechnicalIndicatorViewCell>, 'index' | 'mcap' | 'mcapRank'> {
  const indexValue = firstPresentValue(row, MARKET_CAP_INDEX_ALIASES);
  const mcapValue = firstPresentValue(row, MARKET_CAP_VALUE_ALIASES);
  const rankValue = firstPresentValue(row, MARKET_CAP_RANK_ALIASES);
  const indexText = normalizeMarketCapIndex(indexValue);
  const indexCategory = getMarketCapCategory(indexValue);
  const mcapNum = toNumber(mcapValue);
  const rankNum = toNumber(rankValue);
  return {
    index: { text: indexText, sort: indexText, tone: indexTone(indexText) ?? indexCategory },
    mcap: {
      text: formatMarketCapValue(mcapValue),
      sort: mcapNum,
      tone: indexCategory,
    },
    mcapRank: {
      text: formatMarketCapRankValue(rankValue),
      sort: rankNum,
      tone: indexCategory,
    },
  };
}

function symbolFromRow(row: Record<string, unknown>): string {
  const value = firstValue(row, ['symbol', 'SYMBOL', 'stock', 'ticker', 'name']);
  return value === undefined || value === null ? '' : String(value).trim();
}

function sNoCell(row: Record<string, unknown>, fallbackIndex: number): TechnicalIndicatorViewCell {
  const raw = firstValue(row, ['sNo', 'S_NO', 'sno', 'serial']);
  const value = raw === null ? fallbackIndex + 1 : raw;
  return { text: String(value), sort: toNumber(value) ?? fallbackIndex + 1 };
}

function numberCell(row: Record<string, unknown>, keys: string[], sortKeys = keys): TechnicalIndicatorViewCell {
  const raw = firstValue(row, keys);
  const sort = toNumber(firstValue(row, sortKeys)) ?? toNumber(raw);
  if (Number.isFinite(sort)) {
    return { text: formatPlainNumber(sort as number), sort };
  }
  return { text: raw === null ? '-' : String(raw), sort: null };
}

function fixedNumberCell(row: Record<string, unknown>, keys: string[], sortKeys = keys, digits = 2): TechnicalIndicatorViewCell {
  const raw = firstValue(row, keys);
  const sort = toNumber(firstValue(row, sortKeys)) ?? toNumber(raw);
  if (Number.isFinite(sort)) {
    return { text: (sort as number).toFixed(digits), sort };
  }
  return { text: raw === null ? '-' : String(raw), sort: null };
}

function integerCell(row: Record<string, unknown>, keys: string[], sortKeys = keys): TechnicalIndicatorViewCell {
  const raw = firstValue(row, keys);
  const sort = toNumber(firstValue(row, sortKeys)) ?? toNumber(raw);
  if (Number.isFinite(sort)) {
    return { text: Math.round(sort as number).toLocaleString(), sort };
  }
  return { text: raw === null ? '-' : String(raw), sort: null };
}

function metricCell(row: Record<string, unknown>, keys: string[], sortKeys = keys): TechnicalIndicatorViewCell {
  const cell = numberCell(row, keys, sortKeys);
  return { ...cell, tone: toneFromNumber(typeof cell.sort === 'number' ? cell.sort : null) };
}

function dateCell(row: Record<string, unknown>, keys: string[], sortKeys: string[]): TechnicalIndicatorViewCell {
  const primary = firstValue(row, keys);
  const fallbackSort = firstValue(row, sortKeys);
  const parsed = parseDateValue(primary);
  const sort = parsed ? parsed.getTime() : toEpochMs(fallbackSort);
  if (parsed) return { text: formatDateDDMMYYYY(parsed), sort: parsed.getTime() };
  if (Number.isFinite(sort)) return { text: formatDateDDMMYYYY(sort), sort };
  const text = primary === undefined || primary === null ? '' : String(primary).trim();
  return { text: text || '-', sort: null };
}

function returnCell(row: Record<string, unknown>, key: string): TechnicalIndicatorViewCell {
  const raw = firstValue(row, [key, key.toUpperCase()]);
  const sort = toNumber(firstValue(row, [`${key}Sort`, `${key.toUpperCase()}_SORT`])) ?? toNumber(raw);
  if (raw === null) return { text: '-', sort, tone: toneFromNumber(sort) };
  return { text: String(raw).trim() || '-', sort, tone: toneFromNumber(sort) };
}

function latestDateKeyFromRows(rows: TechnicalIndicatorScreenWireRow[]): string | null {
  let latest: string | null = null;
  rows.forEach((row) => {
    const source = row as Record<string, unknown>;
    const value = firstValue(source, [
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
    const key = normalizeLatestDateKey(value);
    if (key && (!latest || key > latest)) latest = key;
  });
  return latest;
}

export function adaptTechnicalIndicatorRow(
  row: TechnicalIndicatorScreenWireRow,
  index: number,
  kind: TechnicalIndicatorKind,
): TechnicalIndicatorViewRow {
  const source = row as Record<string, unknown>;
  const symbol = symbolFromRow(source);
  const marketCap = marketCapCells(source);
  const tradingDateRaw = firstValue(source, [
    'tradingDate',
    'TRADING_DATE',
    'trading_date',
    'tradingDateDisplay',
    'TRADING_DATE_DISPLAY',
    'tradingDateMin',
    'sinceDate',
    'SINCE_DATE',
  ]);
  const disabledSince = (kind === 'rsi50' || kind === 'adx' || kind === 'volume') && isDisabledSince(tradingDateRaw);
  const tradingDate = disabledSince
    ? { text: 'N/A', sort: null }
    : dateCell(source, [
      'tradingDate',
      'TRADING_DATE',
      'trading_date',
      'tradingDateDisplay',
      'TRADING_DATE_DISPLAY',
      'tradingDateMin',
      'sinceDate',
      'SINCE_DATE',
    ], ['tradingDateSort', 'TRADING_DATE_SORT', 'trading_date_sort']);
  const tradingDays = disabledSince
    ? { text: 'N/A', sort: null }
    : numberCell(source, ['td', 'T_D', 'tradingDays', 'TRADING_DAYS', 'trading_days'], ['tdSort', 'tradingDaysSort', 'TRADING_DAYS_SORT']);
  const cells: Record<string, TechnicalIndicatorViewCell> = {
    sNo: sNoCell(source, index),
    symbol: { text: symbol || '-', sort: symbol || '', tone: marketCap.index.tone ?? 'unknown' },
    index: marketCap.index,
    mcap: marketCap.mcap,
    mcapRank: marketCap.mcapRank,
    price: metricCell(source, ['price', 'PRICE'], ['priceSort', 'PRICE_SORT', 'price', 'PRICE']),
    tradingDate,
    ltcDate: dateCell(source, [
      'ltcDate',
      'LTC_DATE',
      'ltc_date',
      'ltcDateDisplay',
      'LTC_DATE_DISPLAY',
      'latestTradingDate',
      'latest_trade_date',
    ], ['ltcDateSort', 'LTC_DATE_SORT', 'ltc_date_sort']),
    tradingDays,
  };

  if (kind === 'rsi50') {
    cells.rsi = numberCell(source, ['rsi', 'RSI'], ['rsiSort', 'RSI_SORT', 'rsi', 'RSI']);
    cells.rsiScore = numberCell(source, ['rsiScore', 'RSI_SCORE'], ['rsiScoreSort', 'RSI_SCORE_SORT', 'rsiScore', 'RSI_SCORE']);
  }

  if (kind === 'macd') {
    cells.macdScore = metricCell(source, ['macdScore', 'MACD_SCORE'], ['macdScoreSort', 'MACD_SCORE_SORT', 'macdScore', 'MACD_SCORE']);
    RETURN_COLUMNS.forEach((column) => {
      cells[column.key] = returnCell(source, column.key);
    });
  }

  if (kind === 'atr14') {
    cells.atr = numberCell(source, ['atr', 'ATR'], ['atrSort', 'ATR_SORT', 'atr', 'ATR']);
    cells.atrScore = numberCell(source, ['atrScore', 'ATR_SCORE'], ['atrScoreSort', 'ATR_SCORE_SORT', 'atrScore', 'ATR_SCORE']);
  }

  if (kind === 'adx') {
    cells.adxGt20 = fixedNumberCell(source, ['adxGt20', 'ADX_GT20'], ['adxGt20Sort', 'ADX_GT20_SORT', 'adxGt20', 'ADX_GT20']);
    cells.adxGt25 = fixedNumberCell(source, ['adxGt25', 'ADX_GT25'], ['adxGt25Sort', 'ADX_GT25_SORT', 'adxGt25', 'ADX_GT25']);
    cells.plusDm = fixedNumberCell(source, ['plusDm', 'PLUS_DM', 'plusDI', 'PLUS_DI'], ['plusDmSort', 'PLUS_DM_SORT', 'plusDm', 'PLUS_DM']);
    cells.minusDm = fixedNumberCell(source, ['minusDm', 'MINUS_DM', 'minusDI', 'MINUS_DI'], ['minusDmSort', 'MINUS_DM_SORT', 'minusDm', 'MINUS_DM']);
    cells.adxScore = fixedNumberCell(source, ['adxScore', 'ADX_SCORE'], ['adxScoreSort', 'ADX_SCORE_SORT', 'adxScore', 'ADX_SCORE']);
  }

  if (kind === 'volume') {
    cells.volume = integerCell(source, ['volume', 'VOLUME'], ['volumeSort', 'VOLUME_SORT', 'volume', 'VOLUME']);
    cells.volumeAvg20 = integerCell(source, ['volumeAvg20', 'VOLUME_AVG20', 'avg20', 'AVG_20'], ['volumeAvg20Sort', 'VOLUME_AVG20_SORT', 'volumeAvg20', 'VOLUME_AVG20']);
    cells.volumeRatio = fixedNumberCell(source, ['volumeRatio', 'VOLUME_RATIO', 'ratio', 'RATIO'], ['volumeRatioSort', 'VOLUME_RATIO_SORT', 'volumeRatio', 'VOLUME_RATIO']);
    cells.volumeScore = fixedNumberCell(source, ['volumeScore', 'VOLUME_SCORE'], ['volumeScoreSort', 'VOLUME_SCORE_SORT', 'volumeScore', 'VOLUME_SCORE']);
  }

  return {
    cells,
    id: `${symbol || 'row'}-${index}`,
    raw: row,
    symbol,
  };
}

export function adaptTechnicalIndicatorPayload(
  payload: TechnicalIndicatorPayloadWire | null | undefined,
  kind: TechnicalIndicatorKind,
): TechnicalIndicatorViewPayload {
  const source: Record<string, unknown> = payload && isRecord(payload) ? payload : {};
  const wireRows = ensureRows(source.rows);
  const rows = wireRows.map((row, index) => adaptTechnicalIndicatorRow(row, index, kind));
  const cachedAt = source.cachedAt ?? source.generatedAt;

  return {
    cached: Boolean(source.cached),
    cachedAt: typeof cachedAt === 'string' ? cachedAt : null,
    count: typeof source.count === 'number' ? source.count : rows.length,
    fallback: Boolean(source.fallback),
    latestLtcDateKey: latestDateKeyFromRows(wireRows),
    refreshing: Boolean(source.refreshing),
    rows,
    stale: Boolean(source.stale),
    timeframe: normalizeTimeframe(source.timeframe),
  };
}

export function filterTechnicalIndicatorRowsBySymbol(rows: TechnicalIndicatorViewRow[], query: string): TechnicalIndicatorViewRow[] {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return rows;
  return rows.filter((row) => row.symbol.toLowerCase().includes(normalized));
}
