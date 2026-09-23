import type {
  StrongUptrendReversalFilters,
  StrongUptrendReversalMeta,
  StrongUptrendReversalPayload,
  StrongUptrendReversalRow,
  StrongUptrendSignal,
} from '../types/strategy/strongUptrendReversal';
import {
  firstPresentValue,
  MARKET_CAP_INDEX_ALIASES,
  MARKET_CAP_RANK_ALIASES,
  MARKET_CAP_VALUE_ALIASES,
  normalizeMarketCapIndex,
} from './technicalMarketCap';
import { normalizeDisplaySymbol } from '../utils/symbols';

const SIGNAL_ORDER: StrongUptrendSignal[] = ['STRONG_BUY_SETUP', 'WATCHLIST', 'WEAK_SETUP', 'AVOID'];

const CSV_COLUMNS: Array<{ key: keyof StrongUptrendReversalRow | 'S_NO'; label: string }> = [
  { key: 'S_NO', label: 'S.NO' },
  { key: 'SYMBOL', label: 'SYMBOL' },
  { key: 'INDEX', label: 'INDEX' },
  { key: 'MCAP', label: 'MCAP' },
  { key: 'MCAP_RANK', label: 'MCAP_RANK' },
  { key: 'TRADING_DATE', label: 'TRADING_DATE' },
  { key: 'CLOSE', label: 'CLOSE' },
  { key: 'EMA20', label: 'EMA20' },
  { key: 'EMA50', label: 'EMA50' },
  { key: 'RSI14', label: 'RSI14' },
  { key: 'ADX14', label: 'ADX14' },
  { key: 'MACD', label: 'MACD' },
  { key: 'DELIVERY_PCT', label: 'DELIVERY_PCT' },
  { key: 'VOLUME', label: 'VOLUME' },
  { key: 'HH_HL_STRUCTURE', label: 'HH_HL_STRUCTURE' },
  { key: 'SUPPORT_CONFIRMED', label: 'SUPPORT_CONFIRMED' },
  { key: 'BULLISH_REVERSAL_CANDLE', label: 'BULLISH_REVERSAL_CANDLE' },
  { key: 'BREAKOUT_OK', label: 'BREAKOUT_OK' },
  { key: 'SCORE', label: 'SCORE' },
  { key: 'SIGNAL', label: 'SIGNAL' },
  { key: 'ENTRY_PRICE', label: 'ENTRY_PRICE' },
  { key: 'STOP_LOSS', label: 'STOP_LOSS' },
  { key: 'TARGET_1', label: 'TARGET_1' },
  { key: 'TARGET_2', label: 'TARGET_2' },
  { key: 'REJECT_REASON', label: 'REJECT_REASON' },
];

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function toNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const numeric = typeof value === 'number' ? value : Number(String(value).replace(/,/g, ''));
  return Number.isFinite(numeric) ? numeric : null;
}

function toBoolean(value: unknown): boolean {
  if (typeof value === 'boolean') return value;
  const text = String(value ?? '').trim().toLowerCase();
  return ['1', 'true', 'yes', 'y', 'on'].includes(text);
}

function toText(value: unknown): string {
  return String(value ?? '').trim();
}

function normalizeSymbolToken(value: unknown): string {
  return normalizeDisplaySymbol(toText(value));
}

function symbolFromMarketCapRow(row: Record<string, unknown>): string {
  return normalizeSymbolToken(firstPresentValue(row, ['SYMBOL', 'symbol', 'script', 'SCRIPT', 'stock', 'STOCK']));
}

function marketCapField(row: Record<string, unknown>, aliases: string[]): unknown {
  const value = firstPresentValue(row, aliases);
  if (String(value ?? '').trim() === '-') return null;
  return value;
}

function extractRowsCandidate(payload: unknown): unknown[] {
  if (Array.isArray(payload)) return payload;
  if (!isObject(payload)) return [];
  if (Array.isArray(payload.data)) return payload.data;
  if (Array.isArray(payload.rows)) return payload.rows;
  if (Array.isArray(payload.results)) return payload.results;
  if (Array.isArray(payload.items)) return payload.items;
  if (isObject(payload.data)) {
    if (Array.isArray(payload.data.rows)) return payload.data.rows;
    if (Array.isArray(payload.data.results)) return payload.data.results;
  }
  return [];
}

function enrichRowWithMarketCap(row: unknown, lookup: Map<string, Record<string, unknown>>): unknown {
  if (!isObject(row)) return row;
  const symbol = symbolFromMarketCapRow(row);
  const meta = symbol ? lookup.get(symbol) : undefined;
  if (!meta) return row;
  return {
    ...row,
    INDEX: marketCapField(row, MARKET_CAP_INDEX_ALIASES) ?? marketCapField(meta, MARKET_CAP_INDEX_ALIASES),
    MCAP: marketCapField(row, MARKET_CAP_VALUE_ALIASES) ?? marketCapField(meta, MARKET_CAP_VALUE_ALIASES),
    MCAP_RANK: marketCapField(row, MARKET_CAP_RANK_ALIASES) ?? marketCapField(meta, MARKET_CAP_RANK_ALIASES),
  };
}

export function mergeStrongUptrendMarketCapPayload(payload: unknown, marketCapPayload: unknown): unknown {
  const marketCapRows = extractRowsCandidate(marketCapPayload).filter(isObject);
  if (!marketCapRows.length) return payload;

  const lookup = new Map<string, Record<string, unknown>>();
  marketCapRows.forEach((row) => {
    const symbol = symbolFromMarketCapRow(row);
    if (symbol) lookup.set(symbol, row);
  });
  if (!lookup.size) return payload;

  if (Array.isArray(payload)) {
    return payload.map((row) => enrichRowWithMarketCap(row, lookup));
  }
  if (!isObject(payload)) return payload;

  const output = { ...payload };
  for (const key of ['data', 'rows', 'results', 'items']) {
    if (Array.isArray(output[key])) {
      output[key] = output[key].map((row) => enrichRowWithMarketCap(row, lookup));
    }
  }
  if (isObject(output.data)) {
    const nested = { ...output.data };
    for (const key of ['rows', 'results', 'items']) {
      if (Array.isArray(nested[key])) {
        nested[key] = nested[key].map((row) => enrichRowWithMarketCap(row, lookup));
      }
    }
    output.data = nested;
  }
  return output;
}

function normalizeSignal(signal: unknown, score: number): StrongUptrendSignal {
  const text = toText(signal).toUpperCase() as StrongUptrendSignal;
  return SIGNAL_ORDER.includes(text) ? text : classifySignalFromScore(score);
}

function normalizeRow(row: unknown): StrongUptrendReversalRow | null {
  if (!isObject(row)) return null;
  const score = toNumber(row.SCORE) ?? 0;
  return {
    SYMBOL: toText(row.SYMBOL),
    INDEX: normalizeMarketCapIndex(firstPresentValue(row, MARKET_CAP_INDEX_ALIASES)),
    MCAP: toNumber(firstPresentValue(row, MARKET_CAP_VALUE_ALIASES)),
    MCAP_RANK: toNumber(firstPresentValue(row, MARKET_CAP_RANK_ALIASES)),
    TRADING_DATE: toText(row.TRADING_DATE) || null,
    CLOSE: toNumber(row.CLOSE),
    EMA20: toNumber(row.EMA20),
    EMA50: toNumber(row.EMA50),
    EMA100: toNumber(row.EMA100),
    EMA200: toNumber(row.EMA200),
    RSI14: toNumber(row.RSI14),
    MACD: toNumber(row.MACD),
    MACD_HIST: toNumber(row.MACD_HIST),
    ADX14: toNumber(row.ADX14),
    PLUS_DI: toNumber(row.PLUS_DI),
    MINUS_DI: toNumber(row.MINUS_DI),
    VOLUME: toNumber(row.VOLUME),
    VOLUME_SMA20: toNumber(row.VOLUME_SMA20),
    DELIVERY_PCT: toNumber(row.DELIVERY_PCT),
    HH_HL_STRUCTURE: toBoolean(row.HH_HL_STRUCTURE),
    SUPPORT_CONFIRMED: toBoolean(row.SUPPORT_CONFIRMED),
    BULLISH_REVERSAL_CANDLE: toBoolean(row.BULLISH_REVERSAL_CANDLE),
    BREAKOUT_OK: toBoolean(row.BREAKOUT_OK),
    SCORE: Math.round(score),
    SIGNAL: normalizeSignal(row.SIGNAL, Math.round(score)),
    ENTRY_TRIGGER: toBoolean(row.ENTRY_TRIGGER),
    ENTRY_PRICE: toNumber(row.ENTRY_PRICE),
    STOP_LOSS: toNumber(row.STOP_LOSS),
    TARGET_1: toNumber(row.TARGET_1),
    TARGET_2: toNumber(row.TARGET_2),
    REJECT_REASON: toText(row.REJECT_REASON),
  };
}

function normalizeMeta(payload: unknown, rowCount: number): StrongUptrendReversalMeta {
  const meta = isObject(payload) && isObject(payload.meta) ? payload.meta : {};
  return {
    tradingDate: toText(meta.tradingDate) || null,
    rows: toNumber(meta.rows) ?? rowCount,
    cacheState: toText(meta.cacheState) || undefined,
    durationMs: toNumber(meta.durationMs) ?? undefined,
    symbolUniverse: toNumber(meta.symbolUniverse) ?? undefined,
    refreshing: Boolean(meta.refreshing || (isObject(payload) && payload.refreshing === true)),
    stale: Boolean(meta.stale || meta.is_stale || (isObject(payload) && (payload.stale === true || payload.is_stale === true))),
    deliveryHits: toNumber(meta.deliveryHits) ?? undefined,
    deliveryMissing: toNumber(meta.deliveryMissing) ?? undefined,
    oracleLoadMs: toNumber(meta.oracleLoadMs) ?? undefined,
    deliveryLoadMs: toNumber(meta.deliveryLoadMs) ?? undefined,
    computeMs: toNumber(meta.computeMs) ?? undefined,
  };
}

export function classifySignalFromScore(score: number | null | undefined): StrongUptrendSignal {
  const numeric = Number(score ?? 0);
  if (numeric >= 80) return 'STRONG_BUY_SETUP';
  if (numeric >= 65) return 'WATCHLIST';
  if (numeric >= 50) return 'WEAK_SETUP';
  return 'AVOID';
}

export function adaptStrongUptrendReversalPayload(payload: unknown): StrongUptrendReversalPayload {
  const rows = extractRowsCandidate(payload)
    .map(normalizeRow)
    .filter((row): row is StrongUptrendReversalRow => Boolean(row && row.SYMBOL));
  const status = isObject(payload) ? toText(payload.status) || 'SUCCESS' : 'SUCCESS';
  const error = isObject(payload) ? toText(payload.error) : '';
  return {
    rows,
    status,
    error,
    meta: normalizeMeta(payload, rows.length),
  };
}

export function hasMissingStrongUptrendMarketCap(rows: StrongUptrendReversalRow[]): boolean {
  return rows.some((row) => row.INDEX === '-' || row.MCAP === null || row.MCAP_RANK === null);
}

export function filterStrongUptrendReversalRows(
  rows: StrongUptrendReversalRow[],
  filters: StrongUptrendReversalFilters,
): StrongUptrendReversalRow[] {
  const query = filters.search.trim().toUpperCase();
  const minimumScore = Number(filters.minimumScore);
  const hasMinimumScore = Number.isFinite(minimumScore);
  return rows.filter((row) => {
    if (filters.signal !== 'ALL' && row.SIGNAL !== filters.signal) return false;
    if (filters.strongBuyOnly && row.SIGNAL !== 'STRONG_BUY_SETUP') return false;
    if (filters.entryTriggerOnly && !row.ENTRY_TRIGGER) return false;
    if (hasMinimumScore && row.SCORE < minimumScore) return false;
    if (query && !row.SYMBOL.toUpperCase().includes(query)) return false;
    return true;
  });
}

export function formatStrongUptrendValue(
  value: number | string | null | undefined,
  options: { digits?: number; kind?: 'number' | 'percent' | 'volume' } = {},
): string {
  if (value === null || value === undefined || value === '') return '-';
  if (typeof value === 'string' && options.kind !== 'number' && options.kind !== 'percent' && options.kind !== 'volume') {
    return value.trim() || '-';
  }
  const numeric = toNumber(value);
  if (numeric === null) return '-';
  if (options.kind === 'volume') return Math.round(numeric).toLocaleString('en-US');
  if (options.kind === 'percent') return numeric.toFixed(options.digits ?? 2);
  return numeric.toFixed(options.digits ?? 2);
}

export function getStrongUptrendSignalClass(signal: StrongUptrendSignal): string {
  if (signal === 'STRONG_BUY_SETUP') return 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-700/70 dark:bg-emerald-950/40 dark:text-emerald-200';
  if (signal === 'WATCHLIST') return 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-700/70 dark:bg-amber-950/40 dark:text-amber-200';
  if (signal === 'WEAK_SETUP') return 'border-sky-200 bg-sky-50 text-sky-800 dark:border-sky-700/70 dark:bg-sky-950/40 dark:text-sky-200';
  return 'border-slate-200 bg-slate-100 text-slate-700 dark:border-slate-700/70 dark:bg-slate-900 dark:text-slate-300';
}

export function getStrongUptrendScoreClass(score: number): string {
  if (score >= 80) return 'text-emerald-700 dark:text-emerald-300';
  if (score >= 65) return 'text-amber-700 dark:text-amber-300';
  if (score >= 50) return 'text-sky-700 dark:text-sky-300';
  return 'text-slate-600 dark:text-slate-300';
}

function escapeCsv(value: string): string {
  if (/[",\n]/.test(value)) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

export function buildStrongUptrendReversalCsv(rows: StrongUptrendReversalRow[]): string {
  const header = CSV_COLUMNS.map((column) => column.label).join(',');
  const lines = rows.map((row, index) => CSV_COLUMNS.map((column) => {
    if (column.key === 'S_NO') return String(index + 1);
    const value = row[column.key];
    if (typeof value === 'boolean') return value ? 'TRUE' : 'FALSE';
    if (typeof value === 'number') return String(value);
    return escapeCsv(String(value ?? ''));
  }).join(','));
  return [header, ...lines].join('\n');
}
