import type { AppSortType } from '../components/app/AppDataTable';
import type { DeliveryPayloadWire, TechnicalDeliveryWireRow } from '../types/api/technical';
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

export type DeliveryColumnDef = {
  key: string;
  label: string;
  sortBy: string;
  sortType: AppSortType;
};

export type DeliveryViewCell = {
  sort: number | string | null;
  text: string;
  tone?: 'high' | 'rising' | 'scoreHigh' | 'scoreMid';
  marketCapTone?: 'large' | 'mid' | 'small' | 'unknown';
};

export type DeliveryViewRow = {
  cells: Record<string, DeliveryViewCell>;
  id: string;
  raw: TechnicalDeliveryWireRow;
  symbol: string;
};

export type DeliverySummaryView = {
  deliveryPctEq100Count: number;
  deliveryPctGt90Count: number;
  deliveryPctGt80Count: number;
  deliveryPctGt70Count: number;
  deliveryPctGt60Count: number;
  deliveryPctGt50Count: number;
  deliveryPctGt40Count: number;
  deliveryScoreGt100Count: number;
  deliveryScoreGt90Count: number;
  deliveryScoreGt80Count: number;
  deliveryScoreGt70Count: number;
  deliveryScoreGt60Count: number;
  deliveryScoreGt50Count: number;
  strongAccumulationCount: number;
  totalStocks: number;
};

export type DeliveryViewPayload = {
  cached?: boolean;
  latestLtcDate: string | null;
  page: number;
  refreshing?: boolean;
  rows: DeliveryViewRow[];
  summary: DeliverySummaryView;
  totalPages: number;
  totalRecords: number;
};

export const DELIVERY_COLUMNS: DeliveryColumnDef[] = [
  { key: 'sNo', label: 'S.NO', sortBy: 's_no', sortType: 'number' },
  { key: 'symbol', label: 'SYMBOL', sortBy: 'symbol', sortType: 'string' },
  { key: 'index', label: 'INDEX', sortBy: 'index', sortType: 'string' },
  { key: 'mcap', label: 'MCAP', sortBy: 'mcap', sortType: 'number' },
  { key: 'mcapRank', label: 'MCAP_RANK', sortBy: 'mcap_rank', sortType: 'number' },
  { key: 'ltcDate', label: 'LTC', sortBy: 'ltc_date', sortType: 'date' },
  { key: 'price', label: 'PRICE', sortBy: 'price', sortType: 'number' },
  { key: 'deliveryQty', label: 'DELIVERY_QTY', sortBy: 'delivery_qty', sortType: 'number' },
  { key: 'deliveryPct', label: 'DELIVERY%', sortBy: 'delivery_pct', sortType: 'number' },
  { key: 'deliveryScore', label: 'DELIVERY_SCORE', sortBy: 'delivery_score', sortType: 'number' },
];

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
  if (!parsed) return '-';
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

function numberText(value: number, options: Intl.NumberFormatOptions = { maximumFractionDigits: 2 }): string {
  return value.toLocaleString('en-IN', options);
}

function numberCell(value: unknown): DeliveryViewCell {
  const numeric = toNumber(value);
  if (numeric === null) return { text: value === undefined || value === null || String(value).trim() === '' ? '-' : String(value), sort: null };
  return { text: numberText(numeric), sort: numeric };
}

function integerCell(value: unknown): DeliveryViewCell {
  const numeric = toNumber(value);
  if (numeric === null) return { text: value === undefined || value === null || String(value).trim() === '' ? '-' : String(value), sort: null };
  return { text: Math.round(numeric).toLocaleString(), sort: numeric };
}

function percentCell(value: unknown): DeliveryViewCell {
  const numeric = toNumber(value);
  if (numeric === null) return { text: '-', sort: null };
  return {
    text: `${numeric.toFixed(2)}%`,
    sort: numeric,
    tone: numeric > 40 ? 'high' : undefined,
  };
}

function scoreCell(value: unknown): DeliveryViewCell {
  const numeric = toNumber(value);
  if (numeric === null) return { text: '-', sort: null };
  return {
    text: String(Math.round(numeric)),
    sort: numeric,
    tone: numeric >= 70 ? 'scoreHigh' : numeric >= 50 ? 'scoreMid' : undefined,
  };
}

function boolValue(value: unknown): boolean {
  if (typeof value === 'boolean') return value;
  const text = String(value ?? '').trim().toLowerCase();
  return text === 'true' || text === '1' || text === 'yes';
}

function ensureRows(value: unknown): TechnicalDeliveryWireRow[] {
  return Array.isArray(value) ? value.filter(isRecord) as TechnicalDeliveryWireRow[] : [];
}

function numericMeta(value: unknown, fallback: number): number {
  const parsed = toNumber(value);
  return parsed === null ? fallback : parsed;
}

function latestLtcDateFromRows(rows: DeliveryViewRow[]): string | null {
  const latest = rows
    .map((row) => row.cells.ltcDate.sort)
    .filter((value): value is number => typeof value === 'number' && Number.isFinite(value))
    .sort((a, b) => b - a)[0];
  if (latest === undefined) return null;
  const date = new Date(latest);
  if (Number.isNaN(date.getTime())) return null;
  return date.toISOString().slice(0, 10);
}

function presentValue(value: unknown): unknown {
  if (value === undefined || value === null) return null;
  if (String(value).trim() === '') return null;
  return value;
}

export function adaptDeliveryRow(
  row: TechnicalDeliveryWireRow,
  index: number,
  page: number,
  pageSize: number,
  latestLtcDate?: unknown,
): DeliveryViewRow {
  const source = row as Record<string, unknown>;
  const absoluteIndex = ((page - 1) * pageSize) + index + 1;
  const symbol = String(firstValue(source, ['symbol', 'SYMBOL', 'stock', 'ticker']) ?? '').trim();
  const sNoRaw = firstValue(source, ['s_no', 'sNo', 'S_NO', 'serial']);
  const sNo = toNumber(sNoRaw) ?? absoluteIndex;
  const indexValue = firstPresentValue(source, MARKET_CAP_INDEX_ALIASES);
  const indexText = normalizeMarketCapIndex(indexValue);
  const category = getMarketCapCategory(indexValue);
  const mcapValue = firstPresentValue(source, MARKET_CAP_VALUE_ALIASES);
  const mcap = toNumber(mcapValue);
  const mcapRankValue = firstPresentValue(source, MARKET_CAP_RANK_ALIASES);
  const mcapRank = toNumber(mcapRankValue);
  const qty = integerCell(firstValue(source, ['delivery_qty', 'DELIVERY_QTY', 'deliveryQty']));
  const qtyRising = boolValue(firstValue(source, ['delivery_qty_rising', 'DELIVERY_QTY_RISING', 'deliveryQtyRising']));
  const deliveryQtyText = qtyRising && qty.text !== '-' ? `${qty.text} UP` : qty.text;
  const rowLtcDate = firstValue(source, ['ltc_date', 'LTC_DATE', 'ltcDate', 'latestTradingDate']);
  const effectiveLtcDate = presentValue(latestLtcDate) ?? rowLtcDate;

  const cells: Record<string, DeliveryViewCell> = {
    sNo: { text: String(Math.round(sNo)), sort: sNo },
    symbol: { text: symbol || '-', sort: symbol || '', marketCapTone: category },
    tradingDate: {
      text: formatDateDDMMYYYY(firstValue(source, ['trading_date', 'TRADING_DATE', 'tradingDate'])),
      sort: toEpochMs(firstValue(source, ['trading_date', 'TRADING_DATE', 'tradingDate'])),
    },
    ltcDate: {
      text: formatDateDDMMYYYY(effectiveLtcDate),
      sort: toEpochMs(effectiveLtcDate),
    },
    tradingDays: integerCell(firstValue(source, ['t_d', 'T_D', 'td', 'TD', 'tradingDays', 'TRADING_DAYS', 'trading_days'])),
    index: { text: indexText, sort: indexText, marketCapTone: category },
    mcap: { text: formatMarketCapValue(mcapValue), sort: mcap, marketCapTone: category },
    mcapRank: { text: formatMarketCapRankValue(mcapRankValue), sort: mcapRank, marketCapTone: category },
    price: numberCell(firstValue(source, ['price', 'PRICE', 'ltp', 'LTP'])),
    deliveryQty: { ...qty, text: deliveryQtyText, tone: qtyRising ? 'rising' : undefined },
    deliveryPct: percentCell(firstValue(source, ['delivery_pct', 'DELIVERY_PCT', 'deliveryPct'])),
    deliveryScore: scoreCell(firstValue(source, ['delivery_score', 'DELIVERY_SCORE', 'deliveryScore'])),
  };

  return {
    cells,
    id: `${symbol || 'row'}-${sNo}-${absoluteIndex}`,
    raw: row,
    symbol,
  };
}

export function adaptDeliveryPayload(
  payload: DeliveryPayloadWire | null | undefined,
  currentPage: number,
  pageSize: number,
): DeliveryViewPayload {
  const source: Record<string, unknown> = payload && isRecord(payload) ? payload : {};
  const summary = isRecord(source.summary) ? source.summary : {};
  const wireRows = ensureRows(source.data ?? source.rows);
  const totalRecords = numericMeta(source.total_records ?? source.totalRecords, wireRows.length);
  const payloadLatestLtcDate = String(firstValue(source, ['ltc_date', 'LTC_DATE']) ?? firstValue(summary, ['ltc_date']) ?? (isRecord(source.meta) ? source.meta.latest_ltc_date : '') ?? '').trim();
  const rows = wireRows.map((row, index) => adaptDeliveryRow(row, index, currentPage, pageSize, payloadLatestLtcDate));
  const latestLtcDate = payloadLatestLtcDate || latestLtcDateFromRows(rows);

  return {
    cached: Boolean(source.cached),
    latestLtcDate,
    page: currentPage,
    refreshing: Boolean(source.refreshing),
    rows,
    summary: {
      totalStocks: numericMeta(summary.total_stocks, totalRecords),
      deliveryPctEq100Count: numericMeta(summary.delivery_pct_eq_100_count, 0),
      deliveryPctGt90Count: numericMeta(summary.delivery_pct_gt_90_count, 0),
      deliveryPctGt80Count: numericMeta(summary.delivery_pct_gt_80_count, 0),
      deliveryPctGt70Count: numericMeta(summary.delivery_pct_gt_70_count, 0),
      deliveryPctGt60Count: numericMeta(summary.delivery_pct_gt_60_count, 0),
      deliveryPctGt50Count: numericMeta(summary.delivery_pct_gt_50_count, 0),
      deliveryPctGt40Count: numericMeta(summary.delivery_pct_gt_40_count, 0),
      deliveryScoreGt100Count: numericMeta(summary.delivery_score_gt_100_count, 0),
      deliveryScoreGt90Count: numericMeta(summary.delivery_score_gt_90_count, 0),
      deliveryScoreGt80Count: numericMeta(summary.delivery_score_gt_80_count, 0),
      deliveryScoreGt70Count: numericMeta(summary.delivery_score_gt_70_count, 0),
      deliveryScoreGt60Count: numericMeta(summary.delivery_score_gt_60_count, 0),
      deliveryScoreGt50Count: numericMeta(summary.delivery_score_gt_50_count, 0),
      strongAccumulationCount: numericMeta(summary.strong_accumulation_count, 0),
    },
    totalPages: Math.max(1, Math.ceil(Math.max(totalRecords, 1) / pageSize)),
    totalRecords,
  };
}
