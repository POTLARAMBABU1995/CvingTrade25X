import type { AppSortType } from '../components/app/AppDataTable';
import type { SrLevelsPayloadWire, SrLevelsWireRow } from '../types/api/technical';
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

export type SrLevelsColumnDef = {
  key: string;
  label: string;
  sortType: AppSortType;
};

export type SrLevelsViewCell = {
  sort: number | string | null;
  text: string;
  tone?: 'large' | 'mid' | 'small' | 'unknown';
};

export type SrLevelsViewRow = {
  cells: Record<string, SrLevelsViewCell>;
  id: string;
  raw: SrLevelsWireRow;
  symbol: string;
};

export type SrTrendCounts = {
  consolidation: number;
  downtrend: number;
  total: number;
  uptrend: number;
};

export type SrLevelsViewPayload = {
  page: number;
  rows: SrLevelsViewRow[];
  totalPages: number;
  totalRows: number;
  trendCounts: SrTrendCounts;
};

export const SR_LEVELS_COLUMNS: SrLevelsColumnDef[] = [
  { key: 'sNo', label: 'S.NO', sortType: 'number' },
  { key: 'symbol', label: 'SYMBOL', sortType: 'string' },
  { key: 'index', label: 'INDEX', sortType: 'string' },
  { key: 'mcap', label: 'MCAP', sortType: 'number' },
  { key: 'mcapRank', label: 'MCAP_RANK', sortType: 'number' },
  { key: 'price', label: 'PRICE', sortType: 'number' },
  { key: 'ath', label: 'ATH', sortType: 'number' },
  { key: 'gap', label: 'GAP', sortType: 'number' },
  { key: 'tradingDate', label: 'TRADING_DATE', sortType: 'date' },
  { key: 'ltcDate', label: 'LTC_DATE', sortType: 'date' },
  { key: 'tradingDays', label: 'T_D', sortType: 'number' },
  { key: 'support', label: 'SUPPORT', sortType: 'number' },
  { key: 'resistance', label: 'RESISTANCE', sortType: 'number' },
  { key: 'score', label: 'SCORE', sortType: 'number' },
  { key: 'trendDirection', label: 'TREND_DIRECTION', sortType: 'string' },
  { key: 'priceAction', label: 'PRICE ACTION', sortType: 'string' },
];

const DISABLED_SINCE_TARGET = { day: 1, month: 1, year: 1998 };

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object';
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

function formatIndexValue(value: unknown): string {
  return normalizeMarketCapIndex(value);
}

function parseDateValue(value: unknown): Date | null {
  if (value === undefined || value === null || value === '') return null;
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
  if (typeof value === 'number') {
    const normalized = value < 1000000000000 ? value * 1000 : value;
    const date = new Date(normalized);
    return Number.isNaN(date.getTime()) ? null : date;
  }
  const text = String(value).trim();
  if (!text) return null;
  if (/^\d+$/.test(text)) return parseDateValue(Number(text));
  const normalized = text.replace(/\//g, '-');
  const ddmmyyyy = normalized.match(/^(\d{1,2})-(\d{1,2})-(\d{4})$/);
  if (ddmmyyyy) {
    const [, d, m, y] = ddmmyyyy;
    const date = new Date(Number(y), Number(m) - 1, Number(d));
    return Number.isNaN(date.getTime()) ? null : date;
  }
  const parsed = new Date(normalized);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
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

function isDisabledSince(value: unknown): boolean {
  const parsed = parseDateValue(value);
  return Boolean(parsed &&
    parsed.getDate() === DISABLED_SINCE_TARGET.day &&
    parsed.getMonth() + 1 === DISABLED_SINCE_TARGET.month &&
    parsed.getFullYear() === DISABLED_SINCE_TARGET.year);
}

function formatNumber(value: number, options: Intl.NumberFormatOptions = { maximumFractionDigits: 2 }): string {
  return value.toLocaleString('en-IN', options);
}

function textCell(value: unknown): SrLevelsViewCell {
  if (value === undefined || value === null || String(value).trim() === '') return { text: '-', sort: null };
  return { text: String(value), sort: String(value) };
}

function numberCell(value: unknown): SrLevelsViewCell {
  const numeric = toNumber(value);
  if (numeric === null) return textCell(value);
  return { text: formatNumber(numeric), sort: numeric };
}

function integerOrTextCell(value: unknown): SrLevelsViewCell {
  const numeric = toNumber(value);
  if (numeric === null) return textCell(value);
  return { text: Math.round(numeric).toLocaleString('en-IN'), sort: numeric };
}

function supportResistanceCell(value: unknown): SrLevelsViewCell {
  const numeric = toNumber(value);
  if (numeric === null) return textCell(value);
  return { text: formatNumber(numeric), sort: numeric };
}

function athCell(value: unknown): SrLevelsViewCell {
  const numeric = toNumber(value);
  if (numeric === null) return textCell(value);
  return {
    text: formatNumber(numeric),
    sort: numeric,
    tone: undefined,
  };
}

function gapCell(priceValue: unknown, athValue: unknown, gapValue: unknown): SrLevelsViewCell {
  const explicitGap = toNumber(gapValue);
  const price = toNumber(priceValue);
  const ath = toNumber(athValue);
  const computedGap = explicitGap ?? (price !== null && ath !== null && ath !== 0 ? ((price - ath) / ath) * 100 : null);
  if (computedGap === null) return textCell(gapValue);
  return {
    text: `${computedGap > 0 ? '+' : ''}${computedGap.toFixed(2)}%`,
    sort: computedGap,
  };
}

function priceActionLabel(value: unknown, fallback: unknown): string {
  const candidate = value ?? fallback;
  if (isRecord(candidate)) {
    const label = candidate.label ?? candidate.state ?? candidate.summary;
    return label === undefined || label === null || String(label).trim() === '' ? '-' : String(label);
  }
  if (candidate === undefined || candidate === null || String(candidate).trim() === '') return '-';
  return String(candidate);
}

function trendCountsFromRows(rows: SrLevelsViewRow[]): SrTrendCounts {
  let uptrend = 0;
  let downtrend = 0;
  let consolidation = 0;
  rows.forEach((row) => {
    const value = row.cells.trendDirection?.text.toLowerCase() ?? '';
    if (value.includes('up')) uptrend += 1;
    else if (value.includes('down')) downtrend += 1;
    else if (value.includes('consolidation') || value.includes('range')) consolidation += 1;
  });
  return { uptrend, downtrend, consolidation, total: rows.length };
}

function trendCountsFromMeta(meta: Record<string, unknown> | undefined, rows: SrLevelsViewRow[]): SrTrendCounts {
  const counts = isRecord(meta?.trendCounts) ? meta.trendCounts : {};
  const fallback = trendCountsFromRows(rows);
  return {
    uptrend: toNumber(counts.uptrend ?? counts.up ?? counts.Uptrend) ?? fallback.uptrend,
    downtrend: toNumber(counts.downtrend ?? counts.down ?? counts.Downtrend) ?? fallback.downtrend,
    consolidation: toNumber(counts.consolidation ?? counts.range ?? counts.Consolidation) ?? fallback.consolidation,
    total: toNumber(counts.total ?? counts.Total) ?? fallback.total,
  };
}

function ensureRows(value: unknown): SrLevelsWireRow[] {
  return Array.isArray(value) ? value.filter(isRecord) as SrLevelsWireRow[] : [];
}

function numericMeta(value: unknown, fallback: number): number {
  const parsed = toNumber(value);
  return parsed === null ? fallback : parsed;
}

export function adaptSrLevelsRow(row: SrLevelsWireRow, rowIndex: number, page: number, pageSize: number): SrLevelsViewRow {
  const source = row as Record<string, unknown>;
  const absoluteIndex = ((page - 1) * pageSize) + rowIndex + 1;
  const symbol = String(firstValue(source, ['symbol', 'stock', 'SYMBOL']) ?? '').trim();
  const tradingDateRaw = firstValue(source, ['tradingDate', 'TRADING_DATE', 'trading_date', 'tradingDateMin']);
  const tradingDaysRaw = firstValue(source, ['tradingDays', 'T_D', 'td', 'trading_days']);
  const disabledSince = isDisabledSince(tradingDateRaw) && toNumber(tradingDaysRaw) === null;
  const indexValue = firstPresentValue(source, MARKET_CAP_INDEX_ALIASES);
  const index = formatIndexValue(indexValue);
  const mcapValue = firstPresentValue(source, MARKET_CAP_VALUE_ALIASES);
  const mcap = toNumber(mcapValue);
  const mcapRankValue = firstPresentValue(source, MARKET_CAP_RANK_ALIASES);
  const mcapRank = toNumber(mcapRankValue);
  const category = getMarketCapCategory(indexValue);
  const supportValue = firstValue(source, ['supportDisplay', 'supportSummary', 'support_summary', 'support', 'supportValue', 'support_value', 'supportPrice', 'support_price']);
  const resistanceValue = firstValue(source, ['resistanceDisplay', 'resistanceSummary', 'resistance_summary', 'resistance', 'resistanceValue', 'resistance_value', 'resistancePrice', 'resistance_price']);
  const scoreValue = firstValue(source, ['score', 'SCORE', 'scoreSort', 'SCORE_SORT', 'score_sort']);
  const trendValue = firstValue(source, ['trendDirection', 'trend_direction']);
  const priceAction = priceActionLabel(firstValue(source, ['priceAction']), firstValue(source, ['priceActionSummary']));
  const priceValue = firstValue(source, ['price', 'PRICE', 'close', 'CLOSE']);
  const athValue = firstValue(source, ['ath', 'ATH', 'athSort', 'ATH_SORT']);
  const gapValue = firstValue(source, ['gapSort', 'GAP_SORT', 'gap', 'GAP', 'distance_from_ath_percent', 'distanceFromAthPercent']);

  const cells: Record<string, SrLevelsViewCell> = {
    sNo: { text: String(absoluteIndex), sort: absoluteIndex },
    symbol: { text: symbol || '-', sort: symbol || '', tone: category },
    index: { text: index, sort: index, tone: category },
    mcap: { text: formatMarketCapValue(mcapValue), sort: mcap, tone: category },
    mcapRank: { text: formatMarketCapRankValue(mcapRankValue), sort: mcapRank, tone: category },
    price: numberCell(priceValue),
    ath: athCell(athValue),
    gap: gapCell(priceValue, athValue, gapValue),
    tradingDate: disabledSince
      ? { text: 'N/A', sort: null }
      : { text: formatDateDDMMYYYY(tradingDateRaw) || '-', sort: toEpochMs(tradingDateRaw) },
    ltcDate: {
      text: formatDateDDMMYYYY(firstValue(source, ['ltcDate', 'LTC_DATE', 'tradingDateMax', 'latestTradingDate'])) || '-',
      sort: toEpochMs(firstValue(source, ['ltcDate', 'LTC_DATE', 'tradingDateMax', 'latestTradingDate'])),
    },
    tradingDays: disabledSince ? { text: 'N/A', sort: null } : integerOrTextCell(tradingDaysRaw),
    support: supportResistanceCell(supportValue),
    resistance: supportResistanceCell(resistanceValue),
    score: numberCell(scoreValue),
    trendDirection: textCell(trendValue),
    priceAction: { text: priceAction, sort: priceAction },
  };

  return {
    cells,
    id: `${symbol || 'row'}-${absoluteIndex}`,
    raw: row,
    symbol,
  };
}

export function adaptSrLevelsPayload(
  payload: SrLevelsPayloadWire | null | undefined,
  currentPage: number,
  pageSize: number,
): SrLevelsViewPayload {
  const source: Record<string, unknown> = payload && isRecord(payload) ? payload : {};
  const meta = isRecord(source.meta) ? source.meta : {};
  const page = numericMeta(meta.page, currentPage);
  const rows = ensureRows(source.rows).map((row, index) => adaptSrLevelsRow(row, index, page, pageSize));
  const totalRows = numericMeta(meta.total_rows ?? meta.totalRows, rows.length);
  const totalPages = Math.max(1, numericMeta(meta.total_pages ?? meta.totalPages, Math.ceil(totalRows / pageSize) || 1));

  return {
    page,
    rows,
    totalPages,
    totalRows,
    trendCounts: trendCountsFromMeta(meta, rows),
  };
}
